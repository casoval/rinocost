"""Pruebas del lector de especificaciones técnicas.

    cd backend
    B1_PDF=ruta/b1.pdf ESP_PDF=ruta/especificaciones.pdf python -m unittest discover -s tests -v
"""
import os
import unittest
from pathlib import Path

from app.importers import b1_parser as b1
from app.importers import spec_parser as sp

B1_REAL = Path(os.environ.get("B1_PDF", "/mnt/user-data/uploads/items_san_pedro_.pdf"))
ESP_REAL = Path(os.environ.get("ESP_PDF", "/mnt/user-data/uploads/ESP_TECNICAS_MANT_C_C_SAN_PEDRO_D-7_12_DE_OCTUBRE.pdf"))


def lineas(texto):
    return [(1, x) for x in texto.strip("\n").splitlines()]


class TestEncabezados(unittest.TestCase):
    def test_encabezados_de_item(self):
        casos = {
            "ITEM N°1 RETIRO DE CIELO RASO": (1, "RETIRO DE CIELO RASO"),
            "ITEM N°2: RETIRO DE PISO": (2, "RETIRO DE PISO"),
            "ITEM 4.- DEMOLICIÓN DE H°C°": (4, "DEMOLICIÓN DE H°C°"),
            "ITEM N5 DEMOLICION DE MURO": (5, "DEMOLICION DE MURO"),
            "ITEM 6 . - MESÓN DE H° A°": (6, "MESÓN DE H° A°"),
            "ÍTEM 12.- CONTRAPISO": (12, "CONTRAPISO"),
            "ITEM 13 .-PICADO DE MUROS": (13, "PICADO DE MUROS"),
            "ITEM 18.- . - PINTURA LÁTEX": (18, "PINTURA LÁTEX"),
            "ITEM N°24 .- LIMPIEZA GENERAL": (24, "LIMPIEZA GENERAL"),
        }
        for texto, (num, titulo) in casos.items():
            with self.subTest(texto=texto):
                m = sp._ITEM_RE.match(texto)
                self.assertIsNotNone(m)
                self.assertEqual((int(m.group(1)), m.group(2)), (num, titulo))

    def test_no_son_encabezados(self):
        for texto in ["item Descripcion del Accesorio Material Diametro",
                      "Ítem el tratado de la madera, desde el reparo",
                      "Este ítem ejecutado en un todo de acuerdo"]:
            with self.subTest(texto=texto):
                self.assertIsNone(sp._ITEM_RE.match(texto))

    def test_encabezados_de_modulo(self):
        for texto, num in [("MOD-1: OBRAS PRELIMINARES", 1), ("MOD- 3 : INSTALACION AGUA FRIA", 3),
                           ("MOD-8: INST. DESAGUE SANITARIO", 8), ("MOD-07 OBRAS COMPLEMENTARIAS", 7)]:
            with self.subTest(texto=texto):
                self.assertEqual(int(sp._MODULO_RE.match(texto).group(1)), num)

    def test_secciones(self):
        for titulo, tipo in [("DESCRIPCIÓN", "descripcion"), ("Definición del ítem:", "descripcion"),
                             ("MATERIALES, HERRAMIENTAS Y EQUIPOS", "materiales"),
                             ("Procedimiento para la ejecución", "procedimiento"), ("FORMA DE EJECUCIÓN", "procedimiento"),
                             ("MEDICIÓN", "medicion"), ("F0RMA DE PAGO", "pago"), ("Codo 90° PVC 2\"", None)]:
            with self.subTest(titulo=titulo):
                self.assertEqual(sp._tipo_seccion(titulo), tipo)

    def test_pagina_sin_encabezado_ni_numero(self):
        out = sp._lineas_limpias([(2, "Especificaciones Técnicas\nuna línea\notra\n2")])
        self.assertEqual([x for _, x in out], ["una línea", "otra"])


class TestRecursos(unittest.TestCase):
    def leer(self, texto):
        return sp._leer_recursos(lineas(texto))

    def nombres(self, recursos):
        return [(r.tipo, r.nombre, r.unidad) for r in recursos]

    def test_viñetas_etiquetas_y_unidades(self):
        rec, _, _ = self.leer("""
Materiales
-Cemento portland ( kg)
--Lija para pared ( hoja)
 -Masilla para madera [Kg]
-Ladrillo Gambote ( 24 x 11 x 6 cm ) (pza)
Mano de Obra
-Albañil
- Ayudante
Equipo
Hormigonera
El Contratista proveerá todos los materiales
""")
        self.assertEqual(self.nombres(rec), [
            ("material", "Cemento portland", "kg"), ("material", "Lija para pared", "hoja"),
            ("material", "Masilla para madera", "Kg"), ("material", "Ladrillo Gambote ( 24 x 11 x 6 cm )", "pza"),
            ("mano_obra", "Albañil", None), ("mano_obra", "Ayudante", None), ("equipo", "Hormigonera", None)])

    def test_mano_de_obra_en_la_misma_linea(self):
        for texto, esperado in [("Mano de obra peón.", ["Peón"]),
                                ("Mano de Obra: Albañil, Ayudante", ["Albañil", "Ayudante"]),
                                ("Mano de obra\nAyudante eléctrico, Especialista eléctrico", ["Ayudante eléctrico", "Especialista eléctrico"])]:
            with self.subTest(texto=texto):
                rec, _, _ = self.leer(texto)
                self.assertEqual([r.nombre for r in rec], esperado)

    def test_no_requiere(self):
        rec, _, sin = self.leer("Materiales Mínimos:\n- No requiere\nMano De Obra Mínima:\n- Peón\nNota: el listado no es limitativo")
        self.assertTrue(sin)
        self.assertEqual(self.nombres(rec), [("mano_obra", "Peón", None)])

    def test_la_prosa_y_los_titulos_cortan_la_lista(self):
        rec, _, _ = self.leer("""
Equipo o maquinaria :
- Mezcladora,
Contrapisos:
La piedra a emplearse será de canto rodado
-algo que no es recurso
""")
        self.assertEqual(self.nombres(rec), [("equipo", "Mezcladora", None)])

    def test_materiales_minimos_en_prosa_y_caracteristicas(self):
        rec, car, _ = self.leer("""
Materiales
-Placa tomacorriente doble 15A. (pza)
-Caja plástica rectangular (pza)
El Contratista suministrará todos los materiales.
Este ítem deberá contar con los siguientes materiales mínimos:
➢ Placa tomacorriente doble de 15A
➢ Caja plástica rectangular de 10x6 cm.
Los tomacorrientes deberán tener las siguientes características mínimas.
• Bornes de cobre
• Voltaje: 220 V
Las marcas que se dan a continuación son solo una guía
""")
        self.assertEqual(len(rec), 2)  # las menciones repetidas se unen
        self.assertEqual(rec[1].detalle, "Caja plástica rectangular de 10x6 cm")
        self.assertEqual(rec[0].unidad, "pza")
        self.assertEqual(car, ["Bornes de cobre", "Voltaje: 220 V"])

    def test_mano_de_obra_solo_se_une_si_el_nombre_es_igual(self):
        rec, _, _ = self.leer("Mano de Obra\n-Ayudante\n-Ayudante de plomero\nMano de obra peón.\n-Peón")
        self.assertEqual([r.nombre for r in rec], ["Ayudante", "Ayudante de plomero", "Peón"])


class TestDatosTecnicos(unittest.TestCase):
    def test_datos(self):
        datos = sp._buscar_datos(lineas("""
El hormigón se preparará con cemento Portland, arena media y grava en la proporción 1:2:3 en volumen
de materiales sueltos y con un contenido mínimo de cemento de 350 kilogramos
por metro cúbico de hormigón.
Rendimiento 5 m2 por bolsa de 20 kg, aplicado en una capa fina.
Espesor de losa de 7cm con fierro de diámetro 10mm
Posteriormente se dejará fraguar durante 21 días antes de proceder al desencofrado.
permitiendo un tiempo de secado entre manos de 3 a 4 horas.
"""))
        d = {(x.tipo, x.valor) for x in datos}
        for esperado in [("dosificacion", "1:2:3"), ("cemento_minimo", "350 kg/m3"),
                         ("rendimiento_declarado", "5 m2 por bolsa de 20 kg"), ("espesor", "7 cm"),
                         ("espera", "21 dias"), ("espera", "3 a 4 horas")]:
            self.assertIn(esperado, d)

    def test_no_confunde_una_hora_con_dosificacion(self):
        self.assertEqual(sp._buscar_datos(lineas("La reunión de la mezcla será a las 1:30")), [])


@unittest.skipUnless(ESP_REAL.exists(), f"No se encontró el PDF real: {ESP_REAL}")
class TestPdfReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res = sp.parse_especificaciones(ESP_REAL)
        cls.por_n = cls.res.por_numero()

    def test_estructura(self):
        self.assertEqual([i.numero for i in self.res.items], list(range(1, 25)))
        self.assertEqual(self.por_n[1].unidad_spec, "m2")
        self.assertEqual(self.por_n[6].modulo_spec, "MOD-2 OBRA GRUESA")
        self.assertEqual(self.por_n[8].modulo_spec, "MOD-8 INST. DESAGUE SANITARIO")  # el B-1 lo llama M04

    def test_recursos_por_item(self):
        def cuenta(n, tipo):
            return sum(1 for r in self.por_n[n].recursos if r.tipo == tipo)
        self.assertEqual((cuenta(6, "material"), cuenta(6, "mano_obra"), cuenta(6, "equipo")), (10, 2, 1))
        self.assertEqual((cuenta(7, "material"), cuenta(7, "mano_obra")), (12, 2))
        self.assertEqual((cuenta(24, "material"), cuenta(24, "mano_obra"), cuenta(24, "equipo")), (1, 2, 1))
        self.assertEqual([r.nombre for r in self.por_n[1].recursos], ["Peón"])
        self.assertTrue(self.por_n[5].sin_materiales)
        # la lista que cruza el salto de página en el ítem 6 está completa
        self.assertIn("Alambre de amarre", [r.nombre for r in self.por_n[6].recursos])
        # 95 = total recontado a mano, ítem por ítem, contra el texto del PDF
        self.assertEqual(sum(len(i.recursos) for i in self.res.items), 95)

    def test_todo_recurso_tiene_origen(self):
        for it in self.res.items:
            for r in it.recursos:
                self.assertGreaterEqual(r.pagina, it.pagina_inicio)
                self.assertTrue(r.fragmento)

    def test_datos_tecnicos_clave(self):
        d6 = {(x.tipo, x.valor) for x in self.por_n[6].datos_tecnicos}
        for esperado in [("dosificacion", "1:2:3"), ("cemento_minimo", "350 kg/m3"),
                         ("rendimiento_declarado", "5 m2 por bolsa de 20 kg"), ("espera", "21 dias")]:
            self.assertIn(esperado, d6)
        self.assertIn(("dosificacion", "1:4"), {(x.tipo, x.valor) for x in self.por_n[17].datos_tecnicos})
        self.assertIn(("espera", "48 horas"), {(x.tipo, x.valor) for x in self.por_n[23].datos_tecnicos})

    def test_caracteristicas_y_precisiones(self):
        self.assertIn("Voltaje: 220 V", self.por_n[16].caracteristicas)
        caja = [r for r in self.por_n[16].recursos if r.nombre.startswith("Caja")][0]
        self.assertIn("10x6", caja.detalle)

    @unittest.skipUnless(B1_REAL.exists(), "No se encontró el B-1 real.")
    def test_cruce_con_b1(self):
        alertas = sp.cruzar_con_b1(self.res, b1.parse_b1(B1_REAL).items())
        self.assertEqual([a.item_numero for a in alertas if a.codigo == "unidad_distinta"], [5])
        self.assertEqual([a.item_numero for a in alertas if a.codigo == "nombre_distinto"], [3])
        self.assertFalse([a for a in alertas if a.codigo in ("item_sin_especificacion", "especificacion_sin_item")])
        sospechosas = {a.item_numero for a in self.res.alertas if a.codigo == "unidad_sospechosa"}
        self.assertEqual(sospechosas, {17})

    def test_cruce_detecta_faltantes(self):
        falso = [type("I", (), dict(numero=n, descripcion="X", unidad="m", unidad_normalizada="m"))() for n in (1, 2, 99)]
        codigos = {(a.codigo, a.item_numero) for a in sp.cruzar_con_b1(self.res, falso)}
        self.assertIn(("item_sin_especificacion", 99), codigos)
        self.assertIn(("especificacion_sin_item", 3), codigos)


if __name__ == "__main__":
    unittest.main()
