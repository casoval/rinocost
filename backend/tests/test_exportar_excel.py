import io
import unittest
from datetime import date
from decimal import Decimal

from openpyxl import load_workbook

from app.cronograma import Actividad, Parametros, calcular
from app.exportadores.excel import exportar_xlsx
from app.exportadores.letras import numero_a_letras


class TestLetras(unittest.TestCase):
    def test_importes(self):
        casos = {
            "0": "Cero 00/100 Bolivianos", "1": "Un 00/100 Bolivianos", "12.5": "Doce 50/100 Bolivianos",
            "16.80": "Dieciséis 80/100 Bolivianos", "21": "Veintiún 00/100 Bolivianos",
            "31.5": "Treinta y un 50/100 Bolivianos", "75.8": "Setenta y cinco 80/100 Bolivianos",
            "100": "Cien 00/100 Bolivianos", "101": "Ciento un 00/100 Bolivianos",
            "543.31": "Quinientos cuarenta y tres 31/100 Bolivianos", "1000": "Mil 00/100 Bolivianos",
            "1001": "Mil un 00/100 Bolivianos", "21000": "Veintiún mil 00/100 Bolivianos",
            "1000000": "Un millón 00/100 Bolivianos", "2500000.75": "Dos millones quinientos mil 75/100 Bolivianos",
            "1999.999": "Dos mil 00/100 Bolivianos", "0.5": "Cero 50/100 Bolivianos",
        }
        for valor, esperado in casos.items():
            with self.subTest(valor=valor):
                self.assertEqual(numero_a_letras(Decimal(valor)), esperado)

    def test_negativo(self):
        with self.assertRaises(ValueError):
            numero_a_letras(-1)


def linea(tipo, desc, unidad, cant, precio, origen_dato="manual", origen_r="manual", req=False):
    estado = "completo" if cant is not None and precio is not None else "pendiente"
    return {"tipo": tipo, "descripcion": desc, "unidad": unidad, "cantidad": cant, "precio_unitario": precio,
            "origen_dato": origen_dato, "origen_rendimiento": origen_r, "requerido_por_pliego": req, "estado": estado}


def proyecto():
    apu1 = {"estado": "completo", "pendientes": 0, "costo": "16.80", "lineas": [
        linea("mano_obra", "Peón", "h", "0.8", "20", "ambos", "biblioteca", True),
        linea("material", "Cemento portland", "kg", "2", "1.3")]}
    apu2 = {"estado": "incompleto", "pendientes": 1, "costo": None, "lineas": [
        linea("material", "Cemento Portland", "kg", "3", "1.3"), linea("mano_obra", "Albañil", "h", None, None)]}
    items = [
        {"id": 11, "numero": 1, "descripcion": "RETIRO DE CIELO RASO DE YESO", "unidad": "m²", "cantidad": "10.0000",
         "cantidad_texto": "10,00", "precio_unitario": "16.80", "total": "168.00", "apu": apu1},
        {"id": 12, "numero": 2, "descripcion": "CONTRAPISO", "unidad": "m²", "cantidad": "5.0000",
         "cantidad_texto": "5,00", "precio_unitario": None, "total": None, "apu": apu2},
        {"id": 13, "numero": 3, "descripcion": "MESON", "unidad": "pza", "cantidad": "1.0000", "cantidad_texto": "1,00",
         "precio_unitario": "250.00", "total": "250.00", "apu": None},
    ]
    return {"nombre": "Obra de prueba", "modulos": [
        {"id": 1, "codigo": "M01", "nombre": "PRELIMINARES", "items": items[:2]},
        {"id": 2, "codigo": "M02", "nombre": "VACÍO", "items": []},
        {"id": 3, "codigo": "M03", "nombre": "OBRA GRUESA", "items": items[2:]},
    ]}


def cronograma():
    acts = [Actividad(11, 1, 1, "RETIRO DE CIELO", Decimal("80"), 2), Actividad(13, 3, 3, "MESON", Decimal("16"), 2)]
    r = calcular(acts, [1, 2, 3], Parametros(date(2026, 12, 7)), hitos={3: date(2026, 12, 8)})
    return {
        "fecha_inicio": "2026-12-07", "fecha_fin": r.fecha_fin.isoformat(), "dias_habiles": r.dias_habiles,
        "actividades": [{"item_id": c.actividad.id, "numero": c.actividad.numero, "nombre": c.actividad.nombre,
                         "modulo_id": c.actividad.modulo, "modulo_codigo": f"M0{c.actividad.modulo}",
                         "horas_hombre": f"{c.actividad.horas_hombre:.2f}", "personas": c.actividad.personas,
                         "duracion_dias": c.duracion, "inicio": c.inicio.isoformat(), "fin": c.fin.isoformat(),
                         "holgura_dias": c.holgura, "critica": c.critica, "espera_dias": 0, "nota": ""}
                        for c in r.actividades],
        "modulos": [{"id": m.id, "codigo": f"M0{m.id}", "nombre": f"Módulo {m.id}", "inicio": m.inicio and m.inicio.isoformat(),
                     "fin": m.fin and m.fin.isoformat(), "hito": m.hito and m.hito.isoformat(), "atraso_dias": m.atraso_dias}
                    for m in r.modulos],
        "sin_programar": [{"item_id": 12, "numero": 2, "nombre": "CONTRAPISO", "motivo": "Faltan cantidades de mano de obra en su APU."}],
        "avisos": ["Aviso de prueba"],
    }


def abrir(datos):
    return load_workbook(io.BytesIO(datos))


class TestExcel(unittest.TestCase):
    def test_hojas(self):
        self.assertEqual(abrir(exportar_xlsx(proyecto())).sheetnames,
                         ["Formulario B-1", "Resumen", "Análisis de precios", "Materiales y recursos"])
        self.assertEqual(abrir(exportar_xlsx(proyecto(), cronograma())).sheetnames[-1], "Cronograma")

    def test_formulario_b1(self):
        ws = abrir(exportar_xlsx(proyecto()))["Formulario B-1"]
        self.assertEqual([c.value for c in ws[5]], ["Ítem", "Descripción", "Unidad", "Cantidad", "Precio Unitario (Numeral)",
                                                    "Precio Unitario (Literal)", "Precio Total (Numeral)"])
        self.assertEqual(ws["A6"].value, "> M01 - PRELIMINARES")
        fila = [c.value for c in ws[7]]
        self.assertEqual(fila[:6], [1, "RETIRO DE CIELO RASO DE YESO", "m²", 10.0, 16.8, "Dieciséis 80/100 Bolivianos"])
        self.assertEqual(fila[6], '=IF(ISNUMBER(E7),ROUND(D7*E7,2),"")')  # fórmula viva
        sin_precio = [c.value for c in ws[8]]
        self.assertEqual((sin_precio[4], sin_precio[5]), (None, None))      # sin precio: celdas vacías, fórmula lista
        self.assertEqual(ws["G8"].value, '=IF(ISNUMBER(E8),ROUND(D8*E8,2),"")')
        self.assertEqual(ws["A9"].value, "> M02 - VACÍO")                    # un módulo vacío no rompe nada
        self.assertEqual(ws["A10"].value, "> M03 - OBRA GRUESA")
        self.assertEqual(ws["F13"].value, "PRECIO TOTAL (Numeral)")
        self.assertEqual(ws["G13"].value, "=SUM(G6:G11)")

    def test_resumen_apunta_a_los_rangos_del_b1(self):
        ws = abrir(exportar_xlsx(proyecto()))["Resumen"]
        self.assertEqual(ws["E4"].value, "=SUM('Formulario B-1'!G7:G8)")
        self.assertEqual(ws["D4"].value, "=COUNT('Formulario B-1'!E7:E8)")
        self.assertEqual((ws["E5"].value, ws["D5"].value), (0, 0))           # módulo sin ítems
        self.assertEqual(ws["E6"].value, "=SUM('Formulario B-1'!G11:G11)")
        self.assertEqual(ws["E7"].value, "=SUM(E4:E6)")

    def test_analisis_de_precios(self):
        ws = abrir(exportar_xlsx(proyecto()))["Análisis de precios"]
        textos = [ws.cell(r, 1).value for r in range(1, 30)]
        self.assertIn("ÍTEM 1 — RETIRO DE CIELO RASO DE YESO   [m²]", textos)
        self.assertIn("ÍTEM 2 — CONTRAPISO   [m²]", textos)
        self.assertNotIn("ÍTEM 3 — MESON   [pza]", textos)                  # sin APU: no aparece
        fila_peon = next(r for r in range(1, 30) if ws.cell(r, 2).value == "Peón")
        self.assertEqual(ws.cell(fila_peon, 4).value, 0.8)
        self.assertEqual(ws.cell(fila_peon, 6).value, f'=IF(AND(ISNUMBER(D{fila_peon}),ISNUMBER(E{fila_peon})),D{fila_peon}*E{fila_peon},"")')
        self.assertEqual(ws.cell(fila_peon, 8).value, "Pliego + biblioteca (lo pide el pliego)")
        pendiente = next(r for r in range(1, 30) if ws.cell(r, 2).value == "Albañil")
        self.assertEqual((ws.cell(pendiente, 4).value, ws.cell(pendiente, 5).value), ("pendiente", "pendiente"))
        todos = [ws.cell(r, c).value for r in range(1, 30) for c in range(1, 9)]
        self.assertIn("Incompleto: faltan 1 línea(s)", todos)

    def test_materiales_consolidados(self):
        ws = abrir(exportar_xlsx(proyecto()))["Materiales y recursos"]
        filas = {ws.cell(r, 2).value: [c.value for c in ws[r]] for r in range(4, 10) if ws.cell(r, 2).value}
        # cemento: 10 × 2 + 5 × 3 = 35 kg (mismo recurso aunque se escriba distinto); la mano de obra pendiente no suma
        self.assertEqual(filas["Cemento portland"][3:5], [35.0, 1.3])
        self.assertEqual(filas["Peón"][3], 8.0)                               # 10 × 0,8
        self.assertNotIn("Albañil", filas)
        notas = [ws.cell(r, 1).value for r in range(1, 20)]
        self.assertTrue(any(n and "1 línea(s) de APU que aún no tienen cantidad" in n for n in notas))

    def test_cronograma(self):
        ws = abrir(exportar_xlsx(proyecto(), cronograma()))["Cronograma"]
        self.assertIn("Inicio: 07/12/2026", ws["A2"].value)
        self.assertEqual(ws["A5"].value, "M01 Módulo 1")                      # banda del módulo
        actividad = [c.value for c in ws[6]]
        self.assertEqual(actividad[:5], [1, "RETIRO DE CIELO", 2, 80.0, 5])
        self.assertEqual((actividad[5].date(), actividad[6].date()), (date(2026, 12, 7), date(2026, 12, 11)))
        self.assertEqual(actividad[8], "Sí")                                  # crítica
        self.assertEqual(ws.cell(6, 11).fill.fgColor.rgb[-6:], "E57373")      # barra roja en la primera semana
        banda3 = [ws.cell(r, 1).value for r in range(1, 20) if ws.cell(r, 1).value and "ATRASO" in str(ws.cell(r, 1).value)]
        self.assertEqual(len(banda3), 1)                                      # el módulo con hito vencido
        todos = [ws.cell(r, 1).value for r in range(1, 30)]
        self.assertIn("Aviso de prueba", todos)
        self.assertTrue(any(t and "Ítem 2: CONTRAPISO" in str(t) for t in todos))

    def test_proyecto_vacio(self):
        datos = exportar_xlsx({"nombre": "Vacío", "modulos": []})
        ws = abrir(datos)["Formulario B-1"]
        self.assertEqual(ws["G7"].value, "=SUM(G6:G6)")


if __name__ == "__main__":
    unittest.main()
