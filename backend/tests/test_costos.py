import unittest
from decimal import Decimal

from app.costos import (ModeloCostos, Paso, Seccion, calcular, controlar_propuesta, obtener_predefinido,
                        validar_modelo)

D = Decimal


class TestModeloB2(unittest.TestCase):
    def test_reproduce_el_b2_de_la_planilla_item_6(self):
        # Valores de 'B-2 06' (pintura látex interior) de APU_Alonso_de_Ibanez_D11_corregido.xlsx
        r = calcular(obtener_predefinido("bolivia_b2"), materiales="12.315", mano_obra="18.76")
        self.assertEqual(r.secciones["mano_obra"].quantize(D("0.0000001")), D("33.4222532"))
        self.assertEqual(r.secciones["equipo"].quantize(D("0.00000001")), D("1.67111266"))
        self.assertEqual(r.secciones["gastos_generales"].quantize(D("0.000001")), D("4.740837"))
        self.assertEqual(r.secciones["utilidad"].quantize(D("0.0000001")), D("5.2149202"))
        self.assertEqual(r.secciones["impuestos"].quantize(D("0.00001")), D("1.77255"))
        self.assertEqual(r.precio, D("59.14"))

    def test_las_etiquetas_llevan_el_porcentaje_vigente(self):
        r = calcular(obtener_predefinido("bolivia_b2"), 10, 10, 0)
        textos = {l.codigo: l.etiqueta for l in r.lineas}
        self.assertEqual(textos["cargas_sociales"], "CARGAS SOCIALES = 55,00% DEL SUBTOTAL DE MANO DE OBRA")
        self.assertIn("14,94%", textos["iva_mo"])

    def test_cambiar_un_porcentaje_cambia_el_precio(self):
        m = obtener_predefinido("bolivia_b2")
        base = calcular(m, 100, 100, 0).precio
        m.paso("cargas_sociales").porcentaje = D("60")
        self.assertGreater(calcular(m, 100, 100, 0).precio, base)

    def test_desactivar_un_paso_o_una_seccion(self):
        m = obtener_predefinido("bolivia_b2")
        m.paso("util").activo = False
        m.paso("it").activo = False
        r = calcular(m, 100, 0, 0)
        self.assertEqual(r.precio, D("110.00"))  # 100 + 10 % de gastos generales
        m.secciones[3].activo = False  # gastos generales
        self.assertEqual(calcular(m, 100, 0, 0).precio, D("100.00"))

    def test_el_predefinido_se_entrega_como_copia(self):
        a = obtener_predefinido("bolivia_b2")
        a.paso("gg").porcentaje = D("99")
        self.assertEqual(obtener_predefinido("bolivia_b2").paso("gg").porcentaje, D("10"))

    def test_otros_modelos(self):
        self.assertEqual(calcular(obtener_predefinido("costo_directo"), 10, 20, 5).precio, D("35.00"))
        # privado: (35 + 10 %) -> 38.5 ; utilidad 10 % de 38.5 = 3.85 ; 35 + 3.5 + 3.85 = 42.35
        self.assertEqual(calcular(obtener_predefinido("privado_simple"), 10, 20, 5).precio, D("42.35"))

    def test_ida_y_vuelta_json(self):
        m = obtener_predefinido("bolivia_b2")
        m2 = ModeloCostos.desde_dict(m.a_dict())
        self.assertEqual(calcular(m, 7, 9, 3).precio, calcular(m2, 7, 9, 3).precio)

    def test_decimales_configurables(self):
        m = obtener_predefinido("bolivia_b2")
        m.decimales = 4
        self.assertEqual(calcular(m, "12.315", "18.76").precio, D("59.1367"))


class TestValidacion(unittest.TestCase):
    def test_base_inexistente_o_posterior(self):
        m = ModeloCostos("x", "x", secciones=[
            Seccion("a", "A", "material", pasos=[Paso("p", "P", D(5), ["b"])]),
            Seccion("b", "B", "mano_obra"),
        ])
        self.assertTrue(any("no existe todavía" in e for e in validar_modelo(m)))
        with self.assertRaises(ValueError):
            calcular(m, 1, 1, 1)

    def test_tipo_de_recurso_repetido_y_porcentaje_negativo(self):
        m = ModeloCostos("x", "x", secciones=[
            Seccion("a", "A", "material"),
            Seccion("b", "B", "material", pasos=[Paso("p", "P", D(-1), ["b.directo"])]),
        ])
        e = " ".join(validar_modelo(m))
        self.assertIn("doble", e)
        self.assertIn("negativo", e)

    def test_codigos_repetidos(self):
        m = ModeloCostos("x", "x", secciones=[Seccion("a", "A", "material"), Seccion("a", "A2", "mano_obra")])
        self.assertTrue(any("repetido" in e for e in validar_modelo(m)))


class TestControlPropuesta(unittest.TestCase):
    def test_caso_de_la_planilla(self):
        c = controlar_propuesta("53710.15", "53710.02")
        self.assertEqual((c.umbral_85, c.garantia_adicional, c.garantia_cumplimiento), (D("45653.63"), D("0.00"), D("3759.70")))
        self.assertEqual((c.diferencia, c.garantia_seriedad), (D("-0.13"), D("537.10")))
        self.assertTrue(c.estado.startswith("OK"))

    def test_garantia_adicional_bajo_85(self):
        c = controlar_propuesta(100000, 80000)
        self.assertEqual(c.garantia_adicional, D("5000.00"))
        self.assertIn("garantía adicional", c.estado)

    def test_excede_el_referencial(self):
        c = controlar_propuesta(1000, 1001)
        self.assertTrue(c.excede_referencial)
        self.assertTrue(c.avisos)

    def test_mype_hasta_un_millon(self):
        c = controlar_propuesta(500000, 480000, micro_pequena_empresa=True)
        self.assertEqual(c.garantia_cumplimiento, D("16800.00"))  # 3,5 % de 480.000
        c2 = controlar_propuesta(2000000, 1900000, micro_pequena_empresa=True)
        self.assertEqual(c2.garantia_cumplimiento, D("133000.00"))  # 7 %: supera el tope


if __name__ == "__main__":
    unittest.main()
