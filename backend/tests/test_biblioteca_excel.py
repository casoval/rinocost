import io
import unittest
from decimal import Decimal

from openpyxl import Workbook

from app.importers.biblioteca_excel import crear_plantilla_bytes, leer_biblioteca_excel


def libro(filas, hoja="Biblioteca"):
    wb = Workbook()
    ws = wb.active
    ws.title = hoja
    for f in filas:
        ws.append(f)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


CAB = ["APU", "Unidad del APU", "Tipo", "Recurso", "Unidad", "Cantidad", "Precio unitario"]


class TestPlantilla(unittest.TestCase):
    def test_la_plantilla_se_lee_sin_errores(self):
        r = leer_biblioteca_excel(crear_plantilla_bytes())
        self.assertFalse(r.hay_errores)
        self.assertEqual([a.nombre for a in r.apus], ["RETIRO DE CIELO RASO DE YESO", "CONTRAPISO DE HORMIGON E=5 CM + EMPEDRADO"])
        self.assertEqual([len(a.lineas) for a in r.apus], [2, 7])
        self.assertEqual(r.apus[1].unidad, "m2")
        self.assertEqual(r.apus[1].lineas[0].cantidad, Decimal("17.5"))  # sin artefactos de float
        self.assertEqual(r.apus[1].lineas[0].origen_rendimiento, "calculado")
        self.assertEqual(r.apus[0].codigo, "A-001")


class TestLectura(unittest.TestCase):
    def test_apu_vacio_continua_el_anterior_y_textos_con_coma(self):
        r = leer_biblioteca_excel(libro([
            CAB,
            ["Revoque de yeso", "m2", "Material", "Yeso", "kg", "8,5", "1,2"],
            [None, None, "Mano de obra", "Albañil", "h", 0.4, 30],
            ["Pintura látex", "m2", "Material", "Pintura", "l", 0.25, 40],
        ]))
        self.assertEqual([(a.nombre, len(a.lineas)) for a in r.apus], [("Revoque de yeso", 2), ("Pintura látex", 1)])
        self.assertEqual(r.apus[0].lineas[0].cantidad, Decimal("8.5"))
        self.assertEqual(r.apus[0].lineas[0].precio_unitario, Decimal("1.2"))
        self.assertEqual(r.apus[0].lineas[1].tipo, "mano_obra")
        self.assertEqual(r.apus[0].lineas[0].origen_rendimiento, "biblioteca")  # por omisión
        self.assertEqual(r.alertas, [])

    def test_encabezado_en_otra_fila_y_nombres_alternativos(self):
        r = leer_biblioteca_excel(libro([
            ["Biblioteca de Juan"], [],
            ["Ítem", "Unidad del ítem", "Categoría", "Insumo", "Und", "Rendimiento", "P.U."][:6] + ["Precio"],
            ["Excavación manual", "m3", "Mano de Obra", "Peón", "h", 2, 20],
        ]))
        self.assertEqual(len(r.apus), 1)
        self.assertEqual((r.apus[0].unidad, r.apus[0].lineas[0].recurso, r.apus[0].lineas[0].precio_unitario),
                         ("m3", "Peón", Decimal("20")))

    def test_errores_y_advertencias_con_numero_de_fila(self):
        r = leer_biblioteca_excel(libro([
            CAB,
            ["Muro", "m2", "Material", "Ladrillo", "pza", "abc", 1],      # fila 2: cantidad ilegible
            [None, None, "Cosa rara", "Algo", "u", 1, 1],                  # fila 3: tipo desconocido
            [None, None, "Material", "Cemento", "kg", -3, 1],              # fila 4: negativo
            [None, None, "Material", None, "kg", 1, 1],                    # fila 5: sin recurso
            ["Vacío", "m2", None, None, None, None, None],                 # fila 6: APU sin recursos
        ]))
        codigos = {(a.codigo, a.fila) for a in r.alertas}
        for esperado in [("cantidad_ilegible", 2), ("tipo_desconocido", 3), ("valor_negativo", 4),
                         ("sin_recurso", 5), ("apu_sin_lineas", 6)]:
            self.assertIn(esperado, codigos)
        self.assertEqual(len(r.apus[0].lineas), 1)           # solo quedó la fila 2 (con cantidad pendiente)
        self.assertIsNone(r.apus[0].lineas[0].cantidad)

    def test_sin_encabezado(self):
        r = leer_biblioteca_excel(libro([["a", "b"], [1, 2]]))
        self.assertEqual([a.codigo for a in r.alertas], ["sin_encabezado"])
        self.assertTrue(r.hay_errores)

    def test_archivo_que_no_es_excel(self):
        r = leer_biblioteca_excel(b"esto no es un excel")
        self.assertEqual(r.alertas[0].codigo, "archivo_ilegible")

    def test_apu_repetido_y_sin_unidad(self):
        r = leer_biblioteca_excel(libro([
            CAB,
            ["Revoque", "m2", "Material", "Yeso", "kg", 1, 1],
            ["Pintura", None, "Material", "Pintura", "l", 1, 1],
            ["Revoque", "m2", "Material", "Yeso", "kg", 1, 1],
        ]))
        codigos = [a.codigo for a in r.alertas]
        self.assertIn("apu_repetido", codigos)
        self.assertIn("apu_sin_unidad", codigos)
        self.assertEqual(len(r.apus), 3)

    def test_origen_desconocido(self):
        r = leer_biblioteca_excel(libro([CAB + ["Origen del rendimiento"],
                                         ["Muro", "m2", "Material", "Ladrillo", "pza", 40, 1, "de memoria"]]))
        self.assertEqual(r.apus[0].lineas[0].origen_rendimiento, "manual")
        self.assertIn("origen_desconocido", [a.codigo for a in r.alertas])


if __name__ == "__main__":
    unittest.main()
