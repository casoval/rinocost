import importlib.util
import io
import unittest
from datetime import date
from decimal import Decimal as D
from types import SimpleNamespace as NS

HAY = all(importlib.util.find_spec(m) for m in ("sqlalchemy", "pydantic", "reportlab", "pdfplumber"))
if HAY:
    import pdfplumber

    from app.exportadores.pdf_cronograma import exportar_cronograma_pdf
    from app.schemas import CronogramaIn
    from app.services.cronograma import calcular_cronograma


def _proyecto(extra=0):
    n = [0]

    def item(desc, hh):
        n[0] += 1
        return NS(id=n[0], numero=n[0], descripcion=desc, cantidad=D(1),
                  apu=NS(lineas=[NS(tipo="mano_obra", cantidad=D(hh), unidad="h")]), datos_tecnicos=[])

    m1 = NS(id=1, codigo="M01", nombre="PRELIMINARES", items=[item("RETIRO", 24), item("DEMOLICION", 40)])
    m2 = NS(id=2, codigo="M02", nombre="OBRA FINA", items=[item("PINTURA", 160)] + [item(f"EXTRA {k}", 30) for k in range(extra)])
    return NS(modulos=[m1, m2], nombre="Proyecto de prueba", entidad="GAD")


def _datos(**kw):
    kw.setdefault("personas_por_defecto", 2)
    return CronogramaIn(fecha_inicio=date(2026, 12, 7), **kw)


def _texto(pdf: bytes) -> str:
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        return "\n".join(p.extract_text() or "" for p in doc.pages)


@unittest.skipUnless(HAY, "Faltan dependencias.")
class TestServicioPlazo(unittest.TestCase):
    def test_sin_plazo_no_hay_veredicto(self):
        out = calcular_cronograma(_proyecto(), _datos())
        self.assertIsNone(out.cumple_plazo)
        self.assertGreater(out.dias_calendario, out.dias_habiles)  # los fines de semana cuentan como calendario

    def test_cumplir_plazo_en_dias_calendario(self):
        base = calcular_cronograma(_proyecto(), _datos())
        meta = base.dias_calendario - 4
        out = calcular_cronograma(_proyecto(), _datos(plazo_maximo=meta, objetivo="cumplir_plazo"))
        self.assertTrue(out.cumple_plazo)
        self.assertLessEqual(out.dias_calendario, meta)
        self.assertTrue(any("Se sumaron" in a for a in out.avisos))

    def test_plazo_en_dias_habiles(self):
        base = calcular_cronograma(_proyecto(), _datos())
        out = calcular_cronograma(_proyecto(), _datos(plazo_maximo=base.dias_habiles - 3, tipo_plazo="habiles", objetivo="cumplir_plazo"))
        self.assertTrue(out.cumple_plazo)
        self.assertLessEqual(out.dias_habiles, base.dias_habiles - 3)

    def test_plazo_imposible_avisa_el_minimo(self):
        out = calcular_cronograma(_proyecto(), _datos(plazo_maximo=1, objetivo="cumplir_plazo", max_personas=3))
        self.assertFalse(out.cumple_plazo)
        self.assertTrue(any("No se alcanza el plazo" in a for a in out.avisos))

    def test_manual_con_plazo_corto_sugiere_cumplir_plazo(self):
        out = calcular_cronograma(_proyecto(), _datos(plazo_maximo=5, tipo_plazo="habiles"))
        self.assertFalse(out.cumple_plazo)
        self.assertTrue(any("Cumplir el plazo" in a for a in out.avisos))

    def test_mas_rapido_es_mas_corto_que_manual(self):
        base = calcular_cronograma(_proyecto(), _datos())
        out = calcular_cronograma(_proyecto(), _datos(objetivo="mas_rapido"))
        self.assertLess(out.dias_habiles, base.dias_habiles)
        self.assertGreater(out.pico_personas, base.pico_personas)

    def test_escenarios_marcan_el_elegido(self):
        out = calcular_cronograma(_proyecto(), _datos(plazo_maximo=30, objetivo="mas_rapido", costo_indirecto_dia=100))
        self.assertEqual({e.clave for e in out.escenarios}, {"manual", "mas_rapido", "cumplir_plazo", "menor_costo"})
        self.assertEqual([e.clave for e in out.escenarios if e.seleccionado], ["mas_rapido"])

    def test_menor_costo_cuesta_menos_que_el_plan_manual(self):
        out = calcular_cronograma(_proyecto(), _datos(objetivo="menor_costo", costo_indirecto_dia=2000, costo_por_persona=100))
        costo = {e.clave: D(e.costo_total) for e in out.escenarios}
        self.assertLessEqual(costo["menor_costo"], costo["manual"])

    def test_serie_que_no_alcanza_abre_frentes_con_cuadrillas_y_personal(self):
        p = _proyecto(extra=10)  # 13 ítems en fila
        base = calcular_cronograma(p, _datos(secuencia="todo_en_serie"))
        meta = base.dias_habiles // 4
        sin = calcular_cronograma(p, _datos(secuencia="todo_en_serie", plazo_maximo=meta, tipo_plazo="habiles",
                                            objetivo="cumplir_plazo", abrir_frentes=False))
        self.assertFalse(sin.cumple_plazo)
        out = calcular_cronograma(p, _datos(secuencia="todo_en_serie", plazo_maximo=meta, tipo_plazo="habiles", objetivo="cumplir_plazo"))
        self.assertTrue(out.cumple_plazo)
        self.assertTrue(out.frentes_abiertos)
        self.assertGreaterEqual(out.frentes, 2)
        self.assertEqual(len(out.frentes_detalle), out.frentes)
        self.assertEqual(out.personal_total, sum(f.personas for f in out.frentes_detalle))
        self.assertEqual(sorted(n for f in out.frentes_detalle for n in f.numeros), sorted(a.numero for a in out.actividades))
        self.assertTrue(all(a.frente >= 1 for a in out.actividades))
        self.assertTrue(any("frentes de trabajo en paralelo" in a for a in out.avisos))
        self.assertIn("frentes", next(e.titulo for e in out.escenarios if e.clave == "cumplir_plazo"))

    def test_alternativas_de_frentes_y_usar_una(self):
        p = _proyecto(extra=10)
        base = calcular_cronograma(p, _datos(secuencia="todo_en_serie"))
        meta = base.dias_habiles // 4
        out = calcular_cronograma(p, _datos(secuencia="todo_en_serie", plazo_maximo=meta, tipo_plazo="habiles", objetivo="cumplir_plazo"))
        self.assertGreaterEqual(len(out.alternativas_frentes), 2)
        self.assertEqual(out.alternativas_frentes[0].frentes, out.frentes)
        k = out.alternativas_frentes[1].frentes
        usa = calcular_cronograma(p, _datos(secuencia="frentes_de_trabajo", frentes=k, plazo_maximo=meta, tipo_plazo="habiles",
                                            objetivo="cumplir_plazo"))
        self.assertEqual(usa.frentes, k)
        self.assertTrue(usa.cumple_plazo)
        self.assertFalse(usa.frentes_abiertos)
        self.assertEqual([a.frentes for a in usa.alternativas_frentes if a.seleccionado], [k])

    def test_plazo_imposible_con_frentes_explica_el_limite_real(self):
        out = calcular_cronograma(_proyecto(), _datos(secuencia="todo_en_serie", plazo_maximo=1, tipo_plazo="habiles", objetivo="cumplir_plazo", max_personas=3))
        self.assertFalse(out.cumple_plazo)
        self.assertFalse(out.frentes_abiertos)
        self.assertTrue(any("todos los ítems en paralelo" in a for a in out.avisos))

    def test_sin_serie_no_hay_frentes_abiertos(self):
        out = calcular_cronograma(_proyecto(), _datos(secuencia="todo_en_paralelo"))
        self.assertEqual(out.frentes, 0)
        self.assertEqual(out.alternativas_frentes, [])

    def test_errores_de_datos_incompletos(self):
        with self.assertRaises(ValueError):
            calcular_cronograma(_proyecto(), _datos(objetivo="cumplir_plazo"))
        with self.assertRaises(ValueError):
            calcular_cronograma(_proyecto(), _datos(objetivo="menor_costo"))

    def test_las_personas_indicadas_por_el_usuario_son_el_piso(self):
        out = calcular_cronograma(_proyecto(), _datos(personas={3: 6}, objetivo="mas_rapido"))
        pintura = next(a for a in out.actividades if a.item_id == 3)
        self.assertGreaterEqual(pintura.personas, 6)

    def test_sin_actividades(self):
        out = calcular_cronograma(NS(modulos=[], nombre="x", entidad=None), _datos(plazo_maximo=10))
        self.assertIsNone(out.cumple_plazo)
        self.assertEqual(out.escenarios, [])


@unittest.skipUnless(HAY, "Faltan dependencias.")
class TestPdfCronograma(unittest.TestCase):
    def _pdf(self, proyecto=None, **kw):
        proyecto = proyecto or _proyecto()
        datos = _datos(**kw)
        out = calcular_cronograma(proyecto, datos).model_dump(mode="json")
        return exportar_cronograma_pdf({"nombre": proyecto.nombre, "entidad": proyecto.entidad}, out, "MI EMPRESA S.R.L.",
                                       datos.trabaja_sabados, [], datos.tipo_plazo), out

    def test_es_un_pdf_con_titulo_plazo_y_filas(self):
        pdf, out = self._pdf()
        self.assertTrue(pdf.startswith(b"%PDF"))
        t = _texto(pdf)
        self.assertIn("CRONOGRAMA DE ACTIVIDADES", t)
        self.assertIn(f"PLAZO DE EJECUCIÓN: {out['dias_calendario']} DÍAS CALENDARIO", t)
        for esperado in ("M01 - PRELIMINARES", "1. RETIRO", "3. PINTURA", "FIN DE OBRA", "MI EMPRESA S.R.L.", "Ruta crítica:"):
            self.assertIn(esperado, t)

    def test_plazo_en_habiles_se_rotula_asi(self):
        pdf, out = self._pdf(plazo_maximo=40, tipo_plazo="habiles")
        self.assertIn(f"{out['dias_habiles']} DÍAS HÁBILES", _texto(pdf))

    def test_proyecto_grande_se_pagina_y_repite_columnas(self):
        pdf, _ = self._pdf(_proyecto(extra=70))
        with pdfplumber.open(io.BytesIO(pdf)) as doc:
            self.assertGreaterEqual(len(doc.pages), 3)
            self.assertTrue(all("Predecesoras" in (p.extract_text() or "") for p in doc.pages))
        self.assertIn("Página 3 de", _texto(pdf))

    def test_obra_larga_usa_escala_de_meses(self):
        pdf, out = self._pdf(_proyecto(extra=70), personas_por_defecto=1, horas_jornada=4)
        self.assertGreater(out["dias_calendario"], 56)  # más de 8 semanas: escala por meses
        self.assertRegex(_texto(pdf), r"ene 2027")

    def test_pdf_con_frentes_muestra_frente_y_personal(self):
        p = _proyecto(extra=10)
        meta = calcular_cronograma(p, _datos(secuencia="todo_en_serie")).dias_habiles // 4
        datos = _datos(secuencia="todo_en_serie", plazo_maximo=meta, tipo_plazo="habiles", objetivo="cumplir_plazo")
        out = calcular_cronograma(p, datos).model_dump(mode="json")
        t = _texto(exportar_cronograma_pdf({"nombre": "P"}, out, None, False, [], "habiles"))
        self.assertRegex(t, r"\d+ frentes · \d+ personas")
        self.assertIn("F1", t)
        self.assertIn("F2", t)

    def test_sin_actividades_no_falla(self):
        vacio = NS(modulos=[], nombre="Vacío", entidad=None)
        datos = _datos()
        out = calcular_cronograma(vacio, datos).model_dump(mode="json")
        pdf = exportar_cronograma_pdf({"nombre": "Vacío"}, out)
        self.assertIn("SIN ACTIVIDADES", _texto(pdf))


@unittest.skipUnless(HAY, "Faltan dependencias.")
class TestApiCronograma(unittest.TestCase):
    def setUp(self):
        from tests import test_exportar_pdf as _pdf
        self._pdf = _pdf
        _pdf.TestApiPdf.setUp(self)  # base en memoria y cliente reales

    def tearDown(self):
        self._pdf.TestApiPdf.tearDown(self)

    def _cuerpo(self, **kw):
        return {"fecha_inicio": "2026-12-07", **kw}

    def test_pdf_se_abre_en_la_pestana(self):
        r = self.cliente.post(f"/proyectos/{self.pid}/cronograma/pdf", json=self._cuerpo(empresa="ACME", plazo_maximo=30))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.headers["content-type"], "application/pdf")
        self.assertTrue(r.headers["content-disposition"].startswith("inline"))
        self.assertTrue(r.content.startswith(b"%PDF"))

    def test_calcular_devuelve_los_campos_nuevos(self):
        r = self.cliente.post(f"/proyectos/{self.pid}/cronograma", json=self._cuerpo(plazo_maximo=30, tipo_plazo="habiles"))
        self.assertEqual(r.status_code, 200, r.text)
        j = r.json()
        for campo in ("dias_calendario", "plazo_maximo", "tipo_plazo", "cumple_plazo", "objetivo", "escenarios", "pico_personas"):
            self.assertIn(campo, j)
        self.assertEqual(j["tipo_plazo"], "habiles")

    def test_objetivo_sin_datos_da_error_claro(self):
        r = self.cliente.post(f"/proyectos/{self.pid}/cronograma", json=self._cuerpo(objetivo="cumplir_plazo"))
        self.assertIn(r.status_code, (400, 422))
        self.assertIn("plazo", r.text.lower())

    def test_valores_fuera_de_rango_se_rechazan(self):
        self.assertEqual(self.cliente.post(f"/proyectos/{self.pid}/cronograma", json=self._cuerpo(plazo_maximo=0)).status_code, 422)
        self.assertEqual(self.cliente.post(f"/proyectos/{self.pid}/cronograma", json=self._cuerpo(objetivo="otro")).status_code, 422)


if __name__ == "__main__":
    unittest.main()
