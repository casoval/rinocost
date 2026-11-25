import unittest
from decimal import Decimal

from app.matching import LineaBib, RequisitoRef, armar_lineas, costo_unitario

D = Decimal
REQ = [
    RequisitoRef("material", "Cemento portland", "kg", 6),
    RequisitoRef("material", "Arena común", "m3", 6),
    RequisitoRef("equipo", "Hormigonera", None, 7),
    RequisitoRef("mano_obra", "Albañil", None, 7),
    RequisitoRef("mano_obra", "Ayudante", None, 7),
]
BIB = [
    LineaBib("material", "Cemento portland IP-30", "kg", D("12"), D("1.30"), recurso_id=11),
    LineaBib("material", "Arena común", "m3", D("0.04"), D("150")),
    LineaBib("mano_obra", "Albañil", "h", D("1.5"), D("40")),
    LineaBib("mano_obra", "Ayudante", "h", D("1.5"), D("25")),
    LineaBib("equipo", "Herramientas menores", "%", D("0.05"), D("100")),
]


def por_nombre(res):
    return {l.descripcion: l for l in res.lineas}


class TestModos(unittest.TestCase):
    def test_pliego_usa_solo_lo_que_pide_el_pliego(self):
        res = armar_lineas("pliego", REQ, BIB)
        self.assertEqual([l.descripcion for l in res.lineas],
                         ["Cemento portland", "Arena común", "Hormigonera", "Albañil", "Ayudante"])
        cem = por_nombre(res)["Cemento portland"]
        # el mismo recurso en la biblioteca aporta cantidad y precio, pero el origen del recurso es el pliego
        self.assertEqual((cem.cantidad, cem.precio_unitario, cem.origen_dato, cem.origen_rendimiento, cem.estado),
                         (D("12"), D("1.30"), "pliego", "biblioteca", "completo"))
        self.assertEqual(cem.recurso_id, 11)
        self.assertEqual(cem.fuente, "Especificaciones, p. 6")
        hormigonera = por_nombre(res)["Hormigonera"]
        self.assertEqual((hormigonera.cantidad, hormigonera.origen_rendimiento, hormigonera.estado), (None, "pendiente", "pendiente"))
        self.assertTrue(all(l.requerido_por_pliego for l in res.lineas))
        self.assertEqual(costo_unitario(res.lineas), (None, 1))  # falta la hormigonera: no hay precio

    def test_pliego_sin_tomar_cantidades_de_la_biblioteca(self):
        res = armar_lineas("pliego", REQ, BIB, tomar_de_biblioteca=False)
        self.assertTrue(all(l.cantidad is None and l.estado == "pendiente" for l in res.lineas))

    def test_biblioteca_conserva_su_apu_y_avisa_lo_que_falta(self):
        res = armar_lineas("biblioteca", REQ, BIB)
        self.assertEqual(len(res.lineas), 5)
        n = por_nombre(res)
        self.assertEqual((n["Cemento portland IP-30"].origen_dato, n["Cemento portland IP-30"].requerido_por_pliego), ("ambos", True))
        self.assertEqual((n["Herramientas menores"].origen_dato, n["Herramientas menores"].requerido_por_pliego), ("biblioteca", False))
        self.assertEqual(len(res.avisos), 1)
        self.assertIn("Hormigonera", res.avisos[0])
        self.assertIn("p. 7", res.avisos[0])
        # 12×1,30 + 0,04×150 + 1,5×40 + 1,5×25 + 0,05×100
        self.assertEqual(costo_unitario(res.lineas), (D("124.10"), 0))

    def test_hibrido_suma_lo_que_falta_sin_duplicar(self):
        res = armar_lineas("hibrido", REQ, BIB)
        self.assertEqual(len(res.lineas), 6)
        n = por_nombre(res)
        self.assertEqual((n["Hormigonera"].origen_dato, n["Hormigonera"].estado, n["Hormigonera"].requerido_por_pliego),
                         ("pliego", "pendiente", True))
        self.assertEqual(n["Herramientas menores"].origen_dato, "biblioteca")  # lo propio del usuario se conserva
        self.assertEqual(sum(1 for l in res.lineas if l.descripcion in ("Ayudante", "Albañil")), 2)
        self.assertEqual(res.avisos, [])
        self.assertEqual(costo_unitario(res.lineas), (None, 1))

    def test_hibrido_sin_faltantes_queda_completo(self):
        req = [r for r in REQ if r.nombre != "Hormigonera"]
        self.assertEqual(costo_unitario(armar_lineas("hibrido", req, BIB).lineas), (D("124.10"), 0))

    def test_sin_apu_en_la_biblioteca_se_usa_el_pliego(self):
        for modo in ("biblioteca", "hibrido"):
            with self.subTest(modo=modo):
                res = armar_lineas(modo, REQ, None)
                self.assertEqual(len(res.lineas), 5)
                self.assertTrue(all(l.origen_dato == "pliego" and l.cantidad is None for l in res.lineas))
                self.assertTrue(any("No hay APU" in a for a in res.avisos))

    def test_sin_requisitos(self):
        res = armar_lineas("pliego", [], None)
        self.assertEqual(res.lineas, [])
        self.assertTrue(any("queda vacío" in a for a in res.avisos))
        self.assertEqual(len(armar_lineas("biblioteca", [], BIB).lineas), 5)

    def test_una_linea_de_biblioteca_no_se_usa_dos_veces(self):
        req = [RequisitoRef("mano_obra", "Albañil", None, 1), RequisitoRef("mano_obra", "Albañil", None, 2)]
        res = armar_lineas("hibrido", req, [BIB[2]])
        self.assertEqual(len(res.lineas), 2)
        self.assertEqual(sorted(l.origen_dato for l in res.lineas), ["ambos", "pliego"])

    def test_modo_invalido(self):
        with self.assertRaises(ValueError):
            armar_lineas("otro", REQ, BIB)

    def test_costo_exige_todo_completo(self):
        self.assertEqual(costo_unitario([]), (None, 0))


if __name__ == "__main__":
    unittest.main()
