import unittest

from app.matching import ApuRef, RecursoRef, clave_equivalencia, emparejar_recurso, preparar, puntaje, sugerir
from app.matching.texto import especificaciones_criticas, sin_tildes

APUS = [
    ApuRef(1, "Retiro de cielo falso de yeso", "m2"),
    ApuRef(2, "Retiro de piso de cerámica", "m2"),
    ApuRef(3, "Contrapiso de hormigón e=5 cm con empedrado", "m2"),
    ApuRef(4, "Contrapiso de hormigón e=10 cm con empedrado", "m2"),
    ApuRef(5, "Provisión y colocado de tubería PVC DN 50", "m"),
    ApuRef(6, "Provisión y colocado de tubería PVC DN 40", "m"),
    ApuRef(7, "Pintura al óleo sobre carpintería de madera", "m2"),
    ApuRef(8, "Pintura látex interior", "m2"),
    ApuRef(9, "Demolición de muro de ladrillo", "m2"),
    ApuRef(10, "Excavación manual en suelo semiduro 0 a 2 m", "m3"),
]


class TestNormalizacion(unittest.TestCase):
    def test_abreviaturas_y_sinonimos(self):
        t = preparar("MESON H° A° C/REVESTIMIENTO CERAMICA ESMALTADA").tokens
        for palabra in ("hormigon", "armado", "revestimiento", "ceramica"):
            self.assertIn(palabra, t)
        self.assertEqual(preparar("Cielo falso").tokens, preparar("CIELO RASO").tokens)
        self.assertEqual(preparar("Concreto armado").tokens, preparar("Hormigón armado").tokens)
        self.assertEqual(preparar("PROV. Y COLOC. de tuberías").tokens, preparar("Provisión y colocado de tubería").tokens)

    def test_especificaciones_criticas(self):
        base = lambda s: especificaciones_criticas(sin_tildes(s.lower()))
        self.assertEqual(base("Contrapiso E=5 CM"), {"espesor": "50mm"})
        self.assertEqual(base("espesor de 0,5 cm")["espesor"], "5mm")
        self.assertEqual(base("TUBERIA PVC DN 50")["dn"], "50")
        self.assertEqual(base('Tubo corrugado D=3/4”')["diametro"], "3/4")
        self.assertEqual(base("Cable N° 10 AWG Cu-Unifilar 6mm2"), {"awg": "10", "seccion": "6"})
        self.assertEqual(base("hormigón 1:2:3")["dosificacion"], "1:2:3")
        self.assertEqual(base("Ladrillo de 6H 24 x 11 x 6 cm")["hueco"], "6")
        self.assertEqual(base("Excavación 0-2 M")["profundidad"], "0-2")
        self.assertEqual(base("excavación 0 a 2 m")["profundidad"], "0-2")
        self.assertEqual(base("Toma doble 15A 220 V"), {"amperaje": "15", "voltaje": "220"})

    def test_puntaje_extremos(self):
        self.assertEqual(puntaje(preparar("Retiro de piso"), preparar("RETIRO DE PISO")).valor, 1.0)
        self.assertLess(puntaje(preparar("Pintura látex interior"), preparar("Excavación manual")).valor, 0.2)
        # tolera el error de tipeo del propio pliego (EOLICO / HEOLICO)
        self.assertGreater(puntaje(preparar("Eolico de 6 plg"), preparar("Heolico 6 plg")).valor, 0.8)


class TestSugerir(unittest.TestCase):
    def top(self, nombre, unidad, **kw):
        r = sugerir(nombre, unidad, APUS, **kw)
        return r[0] if r else None

    def test_encuentra_el_apu_aunque_el_nombre_cambie(self):
        c = self.top("RETIRO DE CIELO RASO DE YESO", "m2")
        self.assertEqual((c.apu_id, c.confianza), (1, "alta"))
        c = self.top("EXCAVACION MANUAL 0-2 M SUELO SEMIDURO", "m3")
        self.assertEqual((c.apu_id, c.confianza), (10, "alta"))

    def test_espesor_distinto_nunca_es_alta(self):
        r = sugerir("CONTRAPISO DE HORMIGON E=5 CM + EMPEDRADO", "m2", APUS)
        self.assertEqual((r[0].apu_id, r[0].confianza), (3, "alta"))
        otro = [c for c in r if c.apu_id == 4][0]
        self.assertNotEqual(otro.confianza, "alta")
        self.assertTrue(any("Espesor" in a for a in otro.avisos))

    def test_diametro_distinto_no_gana(self):
        r = sugerir("PROV. Y COLOC. TUBERIA PVC DN 50 DESAGUE", "m", APUS)
        self.assertEqual(r[0].apu_id, 5)
        self.assertIn(r[0].confianza, ("media", "alta"))
        dn40 = [c for c in r if c.apu_id == 6]
        self.assertTrue(not dn40 or dn40[0].confianza != "alta")

    def test_la_unidad_del_b1_filtra(self):
        # Ítem 5 del B-1: demolición de muro de ladrillo en m3; el APU del usuario está en m2.
        r = sugerir("DEMOLICION DE MURO DE LADRILLO", "m3", APUS)
        c = [x for x in r if x.apu_id == 9][0]
        self.assertFalse(c.compatible_unidad)
        self.assertEqual(c.confianza, "baja")
        self.assertIn("'m2'", c.avisos[0])
        self.assertIn("'m3'", c.avisos[0])

    def test_compatibles_van_primero(self):
        apus = [ApuRef(1, "Muro de ladrillo", "m3"), ApuRef(2, "Muro de ladrillo 6H", "m2")]
        r = sugerir("Muro de ladrillo", "m2", apus)
        self.assertEqual(r[0].apu_id, 2)

    def test_equivalencia_aprendida_gana(self):
        nombre = "PINTURA LATEX TRADICIONAL INTERIOR"
        self.assertEqual(self.top(nombre, "m2").confianza, "media")
        eq = {clave_equivalencia(nombre, "m2"): 8}
        c = self.top(nombre, "m2", equivalencias=eq)
        self.assertEqual((c.apu_id, c.confianza, c.motivo), (8, "alta", "equivalencia"))
        # la misma equivalencia no se aplica a otra unidad
        self.assertNotEqual(self.top(nombre, "m3", equivalencias=eq).motivo, "equivalencia")

    def test_apus_casi_identicos_piden_confirmacion(self):
        apus = [ApuRef(20, "Revoque de yeso interior", "m2"), ApuRef(21, "Revoque de yeso interior", "m2")]
        r = sugerir("REVOQUE DE YESO INTERIOR", "m2", apus)
        self.assertEqual(r[0].confianza, "media")
        self.assertTrue(any("casi igual" in a for a in r[0].avisos))

    def test_sin_candidatos_parecidos(self):
        self.assertEqual(sugerir("MESON H° A° C/REVESTIMIENTO CERAMICA ESMALTADA", "m2", APUS), [])

    def test_maximo(self):
        self.assertLessEqual(len(sugerir("Pintura", "m2", APUS, maximo=1)), 1)


class TestRecursos(unittest.TestCase):
    def emparejar(self, nombre, tipo, *cands):
        refs = [RecursoRef(i, t, n) for i, (t, n) in enumerate(cands)]
        m = emparejar_recurso(nombre, tipo, refs)
        return None if m is None else cands[m[0].clave][1]

    def test_mismo_recurso_con_mas_detalle(self):
        self.assertEqual(self.emparejar("Cemento portland", "material", ("material", "Cemento portland IP-30")),
                         "Cemento portland IP-30")
        self.assertEqual(self.emparejar("Ladrillo Gambote ( 24 x 11 x 6 cm )", "material", ("material", "Ladrillo gambote")),
                         "Ladrillo gambote")
        self.assertEqual(self.emparejar("Peón", "mano_obra", ("mano_obra", "Peon")), "Peon")

    def test_recursos_distintos_no_se_mezclan(self):
        self.assertIsNone(self.emparejar("Cemento", "material", ("material", "Cemento blanco")))
        self.assertIsNone(self.emparejar("Cemento cola", "material", ("material", "Cemento portland")))
        self.assertIsNone(self.emparejar("Ayudante", "mano_obra", ("mano_obra", "Ayudante de plomero")))
        self.assertIsNone(self.emparejar("Arena común", "material", ("material", "Arena fina")))

    def test_especificacion_critica_distinta_no_empareja(self):
        self.assertIsNone(self.emparejar("Tubería pvc sanitaria dn 50", "material", ("material", "Tubería pvc sanitaria dn 40")))
        self.assertIsNone(self.emparejar("Cable N° 10 AWG", "material", ("material", "Cable N° 12 AWG")))

    def test_el_tipo_debe_coincidir(self):
        self.assertIsNone(self.emparejar("Albañil", "equipo", ("mano_obra", "Albañil")))

    def test_elige_el_mejor(self):
        self.assertEqual(self.emparejar("Arena común", "material", ("material", "Arena fina"), ("material", "Arena común")),
                         "Arena común")


if __name__ == "__main__":
    unittest.main()
