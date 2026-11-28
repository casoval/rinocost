import unittest
from decimal import Decimal

from app.costos import obtener_predefinido
from app.exportadores.pdf import _calcular_exacto
from app.services.hoja_b2 import construir_hoja_b2
from tests import test_exportar_pdf as _pdf
from tests.test_exportar_pdf import proyecto


class TestHojaB2(unittest.TestCase):
    def test_completo_coincide_con_el_motor_de_costos(self):
        p = proyecto()
        it = p["modulos"][0]["items"][0]
        h = construir_hoja_b2(p, it)
        esperado = _calcular_exacto(p["modelo_costos"], it["apu"])
        self.assertTrue(h["completo"])
        self.assertEqual(Decimal(h["precio_adoptado"]), esperado.precio)
        self.assertEqual(Decimal(h["total_sin_redondeo"]), esperado.total)
        self.assertEqual([s["tipo_recurso"] for s in h["secciones"]][:3], ["material", "mano_obra", "equipo"])
        self.assertEqual(h["secciones"][0]["lineas"][0]["costo"], "9.75")  # 7.5 × 1.3

    def test_incompleto_no_inventa_precio(self):
        p = proyecto()
        h = construir_hoja_b2(p, p["modulos"][0]["items"][1])
        self.assertFalse(h["completo"])
        self.assertEqual(h["pendientes"], 1)
        self.assertIsNone(h["precio_adoptado"])
        self.assertIsNone(h["secciones"][1]["total"])

    def test_sin_apu(self):
        p = proyecto()
        h = construir_hoja_b2(p, p["modulos"][0]["items"][2])
        self.assertFalse(h["tiene_apu"])
        self.assertIsNone(h["precio_adoptado"])


class TestApiHojaB2(unittest.TestCase):
    def setUp(self):
        _pdf.TestApiPdf.setUp(self)  # misma base en memoria y cliente que las pruebas de PDF

    def tearDown(self):
        _pdf.TestApiPdf.tearDown(self)

    def test_endpoint_item_sin_apu(self):
        item_id = self.proyecto.modulos[0].items[0].id
        r = self.cliente.get(f"/proyectos/items/{item_id}/hoja-b2")
        self.assertEqual(r.status_code, 200, r.text)
        h = r.json()
        self.assertFalse(h["tiene_apu"])
        self.assertEqual(h["item"]["id"], item_id)

    def test_pdf_del_item_se_abre_en_la_pestana(self):
        item_id = self.proyecto.modulos[0].items[0].id
        r = self.cliente.get(f"/proyectos/items/{item_id}/pdf-b2")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.headers["content-type"], "application/pdf")
        self.assertTrue(r.headers["content-disposition"].startswith("inline"))
        self.assertTrue(r.content.startswith(b"%PDF"))
        self.assertTrue(self.cliente.get(f"/proyectos/{self.pid}/pdf/b1").headers["content-disposition"].startswith("inline"))

    def test_pdf_item_con_apu_trae_el_precio(self):
        from app.exportadores.pdf import exportar_b2_item_pdf
        from tests.test_exportar_pdf import texto
        p = proyecto()
        t = texto(exportar_b2_item_pdf(p, p["modulos"][0]["items"][0]))
        self.assertIn("1. MATERIALES", t)
        self.assertEqual(t.count("FORMULARIO B-2"), 1)  # solo la hoja de ese ítem

    def test_endpoint_item_inexistente(self):
        self.assertEqual(self.cliente.get("/proyectos/items/99999/hoja-b2").status_code, 404)


if __name__ == "__main__":
    unittest.main()
