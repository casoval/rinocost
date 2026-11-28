"""Lector de la revista PresNet. Usa páginas SINTÉTICAS (el PDF real es de terceros y no va al repositorio): el texto se genera
con el mismo formato que entrega pdfplumber y con los totales calculados por el motor B-2."""
import importlib.util
import os
import tempfile
import unittest
from decimal import Decimal as D

from app.costos import b2_con_porcentajes, calcular
from app.importers.biblioteca_excel import leer_biblioteca_excel
from app.importers.presnet_parser import escribir_excel, leer_paginas

HAY_DB = all(importlib.util.find_spec(m) for m in ("sqlalchemy", "openpyxl"))


def _f(x):
    return f"{D(x):,.2f}"


def _filas(items):
    out, costo = [], D(0)
    for i, it in enumerate(items, 1):
        desc, unid, cant, precio = it[:4]
        antes, despues = (it[4] if len(it) > 4 else None), (it[5] if len(it) > 5 else None)
        c = D(str(cant)) * D(str(precio))
        costo += c
        if antes:
            out.append(antes)
        out.append(f"{i} {desc + ' ' if desc else ''}{unid} {D(str(cant)):.3f} {_f(precio)} {_f(c)}")
        if despues:
            out.append(despues)
    return out, costo


def pagina(nombre, mat, mo, eq=(), unidad="M", pct=None, impreso=None, total_mat=None, nombre_arriba=None, n=1, cierre=True):
    pct = pct or {}
    modelo = b2_con_porcentajes(**pct)
    fm, cm = _filas(mat)
    fo, co = _filas(mo)
    fe, ce = _filas(eq)
    r = calcular(modelo, cm, co, ce)
    p = {"pct_cargas": "55", "pct_iva_mo": "14.94", "pct_herr": "5", "pct_gg": "10", "pct_util": "10", "pct_it": "3.09", **pct}
    L = ["ANÁLISIS DE PRECIOS UNITARIOS", "DATOS GENERALES", "REVISTA DE PRUEBA ENERO 2030 -", "Proyecto :",
         "EXCEL GENERADO POR PRESNET", "Módulo :"]
    if nombre_arriba:
        L += [nombre_arriba, "Actividad :", nombre]
    else:
        L += [f"Actividad : {nombre}"]
    L += ["Cantidad :", f"Unidad : {unidad}", "Moneda : Bs.", "1. MATERIALES", "DESCRIPCIÓN UNIDAD CANTIDAD PRECIO COSTO",
          "PRODUCTIVO TOTAL", *fm, f"TOTAL MATERIALES {_f(total_mat if total_mat is not None else cm)}", "2. MANO DE OBRA", *fo,
          f"SUBTOTAL MANO DE OBRA {_f(co)}",
          f"CARGAS SOCIALES = ( {p['pct_cargas']}% DEL SUBTOTAL DE MANO DE OBRA) ( 55% al 71.18% ) {_f(r.lineas[2].valor)}",
          f"IMPUESTOS IVA MANO DE OBRA = ( {p['pct_iva_mo']}% DE SUMA DE; SUBTOTAL DE MANO DE OBRA + CARGAS SOCIALES) {_f(r.lineas[3].valor)}",
          f"TOTAL MANO DE OBRA {_f(r.secciones['mano_obra'])}", "3. EQUIPO, MAQUINARIA Y HERRAMIENTAS", *fe,
          f"* HERRAMIENTAS = ( {p['pct_herr']}% DEL TOTAL MANO DE OBRA ) 1.00",
          "TOTAL EQUIPO, MAQUINARIA Y HERRAMIENTAS 1.00", "4. GASTOS GENERALES Y ADMINISTRATIVOS",
          f"* GASTOS GENERALES = {p['pct_gg']}% DE 1+2+3 1.00", "TOTAL GASTOS GENERALES Y ADMINISTRATIVOS 1.00", "5. UTILIDAD",
          f"* UTILIDAD = {p['pct_util']}% DE 1+2+3+4 1.00", "TOTAL UTILIDAD 1.00", "6. IMPUESTOS",
          f"* IMPUESTOS IT = {p['pct_it']}% DE 1+2+3+4+5 1.00", "TOTAL IMPUESTOS 1.00"]
    if cierre:
        L += [f"TOTAL PRECIO UNITARIO 1+2+3+4+5+6 {_f(impreso if impreso is not None else r.precio)}",
              f"TOTAL PRECIO UNITARIO ADOPTADO (Con dos (2) decimales) {_f(impreso if impreso is not None else r.precio)}",
              "Son : Prueba", f"Pág. {n} de 9"]
    else:
        L += [f"Pág. {n} de 9"]
    return "\n".join(L)


MAT = [("CEMENTO PORTLAND", "KG", 7, "1.92"), ("ARENA COMÚN", "M3", "0.04", 194)]
MO = [("ALBAÑIL", "HR", "0.5", 23), ("AYUDANTE", "Hr", "0.5", 17)]
EQ = [("MEZCLADORA", "HR", "0.1", 25)]


class TestPresnet(unittest.TestCase):
    def test_lee_un_analisis_y_comprueba_el_precio(self):
        r = leer_paginas([pagina("REVOQUE FINO", MAT, MO, EQ)])
        a = r.apus[0]
        self.assertEqual((len(r.apus), a.nombre, a.codigo), (1, "REVOQUE FINO", "REV-001"))
        self.assertEqual([(l.tipo, l.recurso, l.unidad) for l in a.lineas],
                         [("material", "CEMENTO PORTLAND", "KG"), ("material", "ARENA COMÚN", "M3"), ("mano_obra", "ALBAÑIL", "HR"),
                          ("mano_obra", "AYUDANTE", "Hr"), ("equipo", "MEZCLADORA", "HR")])
        self.assertEqual((a.lineas[0].cantidad, a.lineas[0].precio_unitario, a.lineas[0].origen_rendimiento), (D("7.000"), D("1.92"), "referencial"))
        self.assertEqual(a.precio_recalculado, a.precio_impreso)
        self.assertFalse([x for x in r.alertas if x.nivel == "advertencia"])

    def test_descripciones_partidas_en_varias_lineas(self):
        mat = [("", "Pza", 2, 85, 'ESPIGA P/CRUCETA CUERPO 1"', 'ROSCA 3/4"'), ("MALLA PREF.", "Pza", 2, 15),
               ("", "Pza", 1, 5, "VOLANDAS CUADRADAS CURVOS DE", '11/16"'), ("ALAMBRE", "Mtr", "3.6", 11)]
        r = leer_paginas([pagina("ARMADO", mat, MO)])
        nombres = [l.recurso for l in r.apus[0].lineas if l.tipo == "material"]
        self.assertEqual(nombres, ['ESPIGA P/CRUCETA CUERPO 1" ROSCA 3/4"', "MALLA PREF.", 'VOLANDAS CUADRADAS CURVOS DE 11/16"', "ALAMBRE"])
        self.assertEqual(r.apus[0].precio_recalculado, r.apus[0].precio_impreso)

    def test_comienzo_y_continuacion_de_filas_consecutivas(self):
        eq = [("CAMIONETA", "Hr", "0.4", "39.55"), ("", "Hr", "0.5", 10, "CINTURÓN, CASCO,", "GUANTES DE CUERO"), ("ALICATES", "Hr", "0.5", 10)]
        r = leer_paginas([pagina("X", MAT, MO, eq)])
        self.assertEqual([l.recurso for l in r.apus[0].lineas if l.tipo == "equipo"], ["CAMIONETA", "CINTURÓN, CASCO, GUANTES DE CUERO", "ALICATES"])

    def test_un_analisis_repartido_en_dos_paginas(self):
        p1 = pagina("DOS PÁGINAS", MAT, MO, cierre=False, n=1)
        p2 = "\n".join(["5. UTILIDAD", "* UTILIDAD = 10% DE 1+2+3+4 1.00", "TOTAL UTILIDAD 1.00", "6. IMPUESTOS", "* IMPUESTOS IT = 3.09% DE 1+2+3+4+5 1.00",
                        "TOTAL IMPUESTOS 1.00", "TOTAL PRECIO UNITARIO ADOPTADO (Con dos (2) decimales) %s" % _f(calcular(b2_con_porcentajes(), 13.44 + 7.76, 20, 0).precio), "Pág. 2 de 9"])
        r = leer_paginas([p1, p2])
        self.assertEqual(len(r.apus), 1)
        self.assertEqual(r.apus[0].precio_recalculado, r.apus[0].precio_impreso)

    def test_nombre_que_empieza_arriba_de_actividad(self):
        r = leer_paginas([pagina("(SIN REVOQUE)", MAT, MO, nombre_arriba="MURO EXTERIOR AUTOPORTANTE E= 100MM")])
        self.assertEqual(r.apus[0].nombre, "MURO EXTERIOR AUTOPORTANTE E= 100MM (SIN REVOQUE)")

    def test_inconsistencia_de_la_fuente_se_avisa_y_no_se_corrige(self):
        r = leer_paginas([pagina("BARANDA", [("BARANDA INOX", "M", 1, 590)], MO, total_mat=1180, impreso=1819.04)])
        codigos = {x.codigo for x in r.alertas}
        self.assertIn("total_materiales_distinto", codigos)
        self.assertIn("precio_distinto", codigos)
        self.assertEqual(r.apus[0].lineas[0].cantidad, D("1.000"))  # los datos quedan como están en la fuente
        self.assertNotEqual(r.apus[0].precio_recalculado, r.apus[0].precio_impreso)

    def test_costo_de_fila_distinto(self):
        t = pagina("X", MAT, MO).replace("CEMENTO PORTLAND KG 7.000 1.92 13.44", "CEMENTO PORTLAND KG 7.000 1.92 15.00")
        self.assertIn("costo_de_fila_distinto", {x.codigo for x in leer_paginas([t]).alertas})

    def test_unidad_repetida_en_casi_todos_no_es_confiable(self):
        r = leer_paginas([pagina(f"ITEM {i}", MAT, MO, unidad="M") for i in range(10)])
        self.assertTrue(all(a.unidad == "" for a in r.apus))
        self.assertIn("unidad_no_publicada", {x.codigo for x in r.alertas})

    def test_unidades_variadas_se_respetan(self):
        r = leer_paginas([pagina("A", MAT, MO, unidad="M2"), pagina("B", MAT, MO, unidad="M3"), pagina("C", MAT, MO, unidad="PZA")])
        self.assertEqual([a.unidad for a in r.apus], ["M2", "M3", "PZA"])

    def test_porcentajes_distintos_se_leen_y_comprueban(self):
        r = leer_paginas([pagina("X", MAT, MO, pct={"pct_cargas": "71.18", "pct_util": "7"})])
        self.assertEqual(r.apus[0].precio_recalculado, r.apus[0].precio_impreso)
        self.assertNotIn("precio_distinto", {x.codigo for x in r.alertas})

    def test_nombre_repetido_se_avisa(self):
        r = leer_paginas([pagina("IGUAL", MAT, MO), pagina("IGUAL", MAT, MO)])
        self.assertEqual([a.codigo for a in r.apus], ["REV-001", "REV-002"])
        self.assertIn("apu_repetido", {x.codigo for x in r.alertas})

    def test_excel_ida_y_vuelta_con_el_importador_de_la_app(self):
        r = leer_paginas([pagina("UNO", MAT, MO, EQ), pagina("DOS", MAT, MO)])
        with tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "b.xlsx")
            escribir_excel(r, ruta)
            e = leer_biblioteca_excel(ruta)
        self.assertEqual([a.nombre for a in e.apus], ["UNO", "DOS"])
        self.assertEqual([len(a.lineas) for a in e.apus], [5, 4])
        self.assertFalse(e.hay_errores)
        self.assertEqual(e.apus[0].lineas[0].origen_rendimiento, "referencial")


@unittest.skipUnless(HAY_DB, "Faltan dependencias.")
class TestPresnetEnBiblioteca(unittest.TestCase):
    def test_se_carga_como_biblioteca_sin_duplicar_recursos(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        from app.db.base import Base
        from app.services import bibliotecas as bib

        e = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
        Base.metadata.create_all(e)
        db = sessionmaker(bind=e, expire_on_commit=False)()
        r = leer_paginas([pagina("UNO", MAT, MO, EQ), pagina("DOS", MAT, MO)])
        b = bib.crear_desde_excel(db, "Revista de prueba", r)
        self.assertEqual((len(b.apus), len(b.recursos)), (2, 5))  # cemento, arena, albañil, ayudante, mezcladora
        # costo directo = 7×1,92 + 0,04×194 + 0,5×23 + 0,5×17 + 0,1×25 = 13,44 + 7,76 + 20 + 2,5 = 43,70
        self.assertEqual(bib.costo_apu(b.apus[0]), D("43.70"))
        db.close()


if __name__ == "__main__":
    unittest.main()
