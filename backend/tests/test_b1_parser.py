"""Pruebas del lector del B-1.

Ejecutar desde la carpeta backend/:
    python -m unittest discover -s tests -v

Para la prueba con el PDF real, apuntar la variable B1_PDF al archivo:
    B1_PDF=/ruta/items_san_pedro_.pdf python -m unittest discover -s tests -v
"""
import os
import unittest
from decimal import Decimal
from pathlib import Path

from app.importers import b1_parser as p

PDF_REAL = Path(os.environ.get("B1_PDF", "/mnt/user-data/uploads/items_san_pedro_.pdf"))


class TestNumerosYUnidades(unittest.TestCase):
    def test_cantidades(self):
        casos = {
            "32,34": Decimal("32.34"),
            "0,09": Decimal("0.09"),
            "1.234,56": Decimal("1234.56"),
            "1,234.56": Decimal("1234.56"),
            "87.3": Decimal("87.3"),
            "1.500": Decimal("1500"),
            "185,15": Decimal("185.15"),
            " 7,30 ": Decimal("7.30"),
        }
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(p.parse_cantidad(texto), esperado)

    def test_cantidades_invalidas(self):
        for texto in ["", "abc", "12a", None]:
            with self.subTest(texto=texto):
                self.assertIsNone(p.parse_cantidad(texto))

    def test_unidades(self):
        for original, normal in [("m²", "m2"), ("M2", "m2"), ("mts2", "m2"), ("m³", "m3"),
                                 ("GLB", "glb"), ("Pza.", "pza"), ("ml", "m")]:
            with self.subTest(original=original):
                self.assertEqual(p.normalizar_unidad(original), normal)

    def test_unir_lineas(self):
        self.assertEqual(p._unir_lineas(["CABLE Cu-", "Unifilar 6mm2"]), "CABLE Cu-Unifilar 6mm2")
        self.assertEqual(p._unir_lineas(["REVOQUE ARENA -", "CEMENTO"]), "REVOQUE ARENA - CEMENTO")
        self.assertEqual(p._unir_lineas(["EXTRACTORA+ DUCTO Y", "EOLICO"]), "EXTRACTORA+ DUCTO Y EOLICO")


class TestFilasDeTabla(unittest.TestCase):
    def leer(self, filas):
        c = p._Constructor()
        p._procesar_filas_tabla(c, filas, 1, dict(p._COLUMNAS_POR_DEFECTO))
        return c.resultado("tablas")

    def test_modulos_e_items(self):
        r = self.leer([
            ["Ítem", "Descripción", "Unidad", "Cantidad", "", "", ""],
            [">", "M01 - OBRAS PRELIMINARES", "", "", "", "", ""],
            ["1", "RETIRO DE X", "m²", "10,50", "", "", ""],
            [">", "M02 – OBRA GRUESA", "", "", "", "", ""],
            ["2", "MURO", "m³", "2,00", "", "", ""],
        ])
        self.assertEqual([m.codigo for m in r.modulos], ["M01", "M02"])
        self.assertEqual(r.items()[0].cantidad, Decimal("10.50"))
        self.assertEqual(r.items()[1].unidad_normalizada, "m3")
        self.assertEqual(r.alertas, [])

    def test_descripcion_en_fila_aparte(self):
        r = self.leer([
            [">", "M01 - A", "", "", "", "", ""],
            ["1", "INSTALACION CAMPANA DUCTO Y", "glb", "1,00", "", "", ""],
            ["", "EOLICO", "", "", "", "", ""],
        ])
        self.assertEqual(r.items()[0].descripcion, "INSTALACION CAMPANA DUCTO Y EOLICO")

    def test_columnas_en_otro_orden(self):
        r = self.leer([
            ["Cantidad", "Unidad", "Descripción", "Ítem"],
            ["5,5", "m", "TUBERIA", "1"],
        ])
        it = r.items()[0]
        self.assertEqual((it.numero, it.descripcion, it.unidad, it.cantidad), (1, "TUBERIA", "m", Decimal("5.5")))

    def test_item_antes_de_modulo(self):
        r = self.leer([["1", "ALGO", "m", "1,00"]])
        self.assertEqual(r.modulos[0].nombre, "(Sin módulo)")
        self.assertIn("item_sin_modulo", [a.codigo for a in r.alertas])

    def test_alertas_de_validacion(self):
        r = self.leer([
            [">", "M01 - A", "", ""],
            ["1", "UNO", "m", "1,00"],
            ["1", "REPETIDO", "m", "1,00"],
            ["4", "SALTO", "m", "0,00"],
            ["5", "MALA CANTIDAD", "m", "abc"],
            ["6", "SIN UNIDAD", "", "2,00"],
        ])
        codigos = {a.codigo for a in r.alertas}
        for esperado in ["numero_duplicado", "numeracion_salteada", "cantidad_cero", "cantidad_invalida", "unidad_vacia"]:
            self.assertIn(esperado, codigos)


@unittest.skipUnless(PDF_REAL.exists(), f"No se encontró el PDF real: {PDF_REAL}")
class TestPdfReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paginas = p._extraer_paginas(PDF_REAL)
        cls.res = p.parse_b1(PDF_REAL)

    def test_estructura(self):
        self.assertEqual(self.res.total_items, 24)
        self.assertEqual([m.codigo for m in self.res.modulos], [f"M0{i}" for i in range(1, 8)])
        self.assertEqual([len(m.items) for m in self.res.modulos], [5, 1, 1, 5, 5, 6, 1])
        self.assertEqual([it.numero for it in self.res.items()], list(range(1, 25)))

    def test_sin_alertas(self):
        self.assertEqual(self.res.alertas, [], [a.mensaje for a in self.res.alertas])

    def test_datos_clave(self):
        it = {i.numero: i for i in self.res.items()}
        self.assertEqual((it[5].unidad, it[5].cantidad), ("m³", Decimal("0.09")))
        self.assertEqual(it[1].cantidad, Decimal("32.34"))
        self.assertEqual(it[18].cantidad, Decimal("185.15"))
        self.assertEqual(it[15].descripcion, "PROV. E INST. CONDUCTOR (Cable) N° 10 AWG Cu-Unifilar 6mm2")
        self.assertEqual(it[19].descripcion, "INSTALACION CAMPANA EXTRACTORA+ DUCTO Y EOLICO")
        self.assertEqual(it[23].descripcion, "PINTURA AL ÓLEO S/CARPINTERIA DE MADERA+ BARNIZADO")
        self.assertEqual(self.res.modulos[2].nombre, "INST. AGUA FRÍA")
        self.assertEqual(self.res.modulos[6].nombre, "OBRAS COMPLEMENTARIAS")  # separador con raya larga

    def test_las_dos_lecturas_coinciden(self):
        a = p._desde_tablas(self.paginas)
        b = p._desde_texto(self.paginas)
        self.assertEqual(p._firma(a), p._firma(b))
        self.assertEqual(p.comparar_lecturas(a, b), [])

    def test_lectura_por_texto_sola(self):
        b = p._desde_texto(self.paginas)
        self.assertEqual(b.total_items, 24)
        self.assertEqual(len(b.modulos), 7)

    def test_resultado_serializable(self):
        import json
        d = json.loads(json.dumps(self.res.to_dict(), ensure_ascii=False))
        self.assertEqual(d["total_items"], 24)
        self.assertEqual(d["modulos"][0]["items"][0]["cantidad"], "32.34")


if __name__ == "__main__":
    unittest.main()
