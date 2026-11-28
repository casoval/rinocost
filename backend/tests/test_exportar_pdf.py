import io
import unittest
from decimal import Decimal

import pdfplumber
from fastapi.testclient import TestClient

from app.costos import obtener_predefinido
from app.exportadores.pdf import _cant, _num, exportar_b1_pdf, exportar_b2_pdf


def linea(tipo, desc, unidad, cant, precio):
    return {"tipo": tipo, "descripcion": desc, "unidad": unidad, "cantidad": cant, "precio_unitario": precio}


def proyecto():
    completo = {"lineas": [
        linea("material", "Cemento portland", "kg", "7.5", "1.3"), linea("mano_obra", "Albañil", "h", "0.8", "18"),
        linea("equipo", "Mezcladora", "h", "0.1", "35")]}
    incompleto = {"lineas": [linea("mano_obra", "Peón", "h", "0.8", None)]}
    items = [
        {"id": 1, "numero": 1, "descripcion": "CONTRAPISO", "unidad": "m²", "cantidad": "10.0000", "cantidad_texto": "10,00",
         "precio_unitario": "200.00", "total": "2000.00", "apu": completo},
        {"id": 2, "numero": 2, "descripcion": "REVOQUE", "unidad": "m²", "cantidad": "5", "cantidad_texto": "5",
         "precio_unitario": None, "total": None, "apu": incompleto},
        {"id": 3, "numero": 3, "descripcion": "MESÓN Ø 3/4\"", "unidad": "pza", "cantidad": "1", "cantidad_texto": "1",
         "precio_unitario": "250.00", "total": "250.00", "apu": None},
    ]
    return {"nombre": "Obra de prueba", "total": "2250.00", "modelo_costos": obtener_predefinido("bolivia_b2").a_dict(),
            "modulos": [{"id": 1, "codigo": "M01", "nombre": "PRELIMINARES", "items": items}]}


def texto(pdf: bytes) -> str:
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        return "\n".join(p.extract_text() or "" for p in doc.pages)


class TestFormatoNumeros(unittest.TestCase):
    def test_formato_boliviano(self):
        self.assertEqual(_num("420434.65"), "420.434,65")
        self.assertEqual(_num("0.5"), "0,50")
        self.assertEqual(_num(None), "—")
        self.assertEqual(_cant("10.0000"), "10,00")
        self.assertEqual(_cant("1234.5"), "1.234,50")
        self.assertEqual(_cant("0.045"), "0,045")
        self.assertEqual(_cant(None, "s/c"), "s/c")


class TestPdfB1(unittest.TestCase):
    def test_contiene_el_formato_del_dbc(self):
        pdf = exportar_b1_pdf(proyecto())
        self.assertTrue(pdf.startswith(b"%PDF"))
        t = texto(pdf)
        for esperado in ("FORMULARIO B-1", "PRESUPUESTO POR ÍTEMS Y GENERAL DE LA OBRA", "(En bolivianos)",
                         "Precio Unitario (Literal)", "PRECIO TOTAL (Numeral)", "PRECIO TOTAL (Literal)",
                         "2.250,00", "Dos mil doscientos cincuenta 00/100 Bolivianos", "Doscientos cincuenta 00/100", "CONTRAPISO"):
            self.assertIn(esperado, t)

    def test_avisa_si_faltan_precios(self):
        self.assertIn("1 ítem(s) todavía no tienen precio", texto(exportar_b1_pdf(proyecto())))

    def test_muchos_items_paginan(self):
        p = proyecto()
        p["modulos"][0]["items"] = [dict(p["modulos"][0]["items"][0], id=i, numero=i) for i in range(1, 121)]
        with pdfplumber.open(io.BytesIO(exportar_b1_pdf(p))) as doc:
            self.assertGreater(len(doc.pages), 2)
            self.assertIn("Descripción Unidad Cantidad", doc.pages[1].extract_text())  # el encabezado se repite


class TestPdfB2(unittest.TestCase):
    def test_estructura_y_precio_adoptado(self):
        t = texto(exportar_b2_pdf(proyecto()))
        for esperado in ("FORMULARIO B-2", "ANÁLISIS DE PRECIOS UNITARIOS", "DATOS GENERALES", "1. MATERIALES",
                         "2. MANO DE OBRA", "SUBTOTAL MANO DE OBRA", "CARGAS SOCIALES = 55,00%",
                         "3. EQUIPO, MAQUINARIA Y HERRAMIENTAS", "6. IMPUESTOS", "TOTAL PRECIO UNITARIO ADOPTADO",
                         "Bolivianos"):
            self.assertIn(esperado, t)

    def test_precio_coincide_con_el_motor(self):
        from app.exportadores.pdf import _calcular_exacto
        p = proyecto()
        esperado = _num(_calcular_exacto(p["modelo_costos"], p["modulos"][0]["items"][0]["apu"]).precio)
        self.assertIn(esperado, texto(exportar_b2_pdf(p)))

    def test_incompleto_no_inventa_precio(self):
        t = texto(exportar_b2_pdf(proyecto()))
        self.assertIn("no se puede calcular hasta completarlas", t)

    def test_items_sin_apu_se_listan(self):
        t = texto(exportar_b2_pdf(proyecto()))
        self.assertIn("ÍTEMS SIN ANÁLISIS DE PRECIOS", t)
        self.assertIn("3. MESÓN", t)

    def test_sin_ningun_apu(self):
        p = proyecto()
        for it in p["modulos"][0]["items"]:
            it["apu"] = None
        self.assertIn("Todavía no hay ítems con análisis de precios", texto(exportar_b2_pdf(p)))

    def test_proyecto_sin_modelo_usa_costo_directo(self):
        p = proyecto()
        p["modelo_costos"] = None
        t = texto(exportar_b2_pdf(p))
        self.assertIn("1. MATERIALES", t)
        self.assertNotIn("CARGAS SOCIALES", t)


class TestApiPdf(unittest.TestCase):
    """Endpoints reales con una base SQLite en memoria."""

    def setUp(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        from app.db.base import Base
        from app.db.session import get_db
        from app.importers.b1_parser import ItemB1, ModuloB1, ResultadoB1
        from app.main import app
        from app.services import proyectos as srv

        engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        self.Sesion = sessionmaker(bind=engine, expire_on_commit=False)
        db = self.Sesion()
        item = ItemB1(numero=1, descripcion="RETIRO DE CIELO", descripcion_original="RETIRO DE CIELO", unidad="m²",
                      unidad_normalizada="m2", cantidad=Decimal("10"), cantidad_texto="10,00", orden=1, pagina=1,
                      modulo_codigo="M01")
        self.proyecto = srv.crear_desde_b1(db, ResultadoB1(modulos=[ModuloB1("M01", "PRELIMINARES", 1, [item])], alertas=[],
                                                          estrategia="demo"), "Demo PDF", "demo.pdf")
        srv.actualizar_precio(db, self.proyecto.modulos[0].items[0].id, "12.50")
        self.pid = self.proyecto.id

        def sesion():
            s = self.Sesion()
            try:
                yield s
            finally:
                s.close()

        app.dependency_overrides[get_db] = sesion
        self.app, self.get_db = app, get_db
        self.cliente = TestClient(app)

    def tearDown(self):
        self.app.dependency_overrides.pop(self.get_db, None)

    def test_pdf_b1(self):
        r = self.cliente.get(f"/proyectos/{self.pid}/pdf/b1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["content-type"], "application/pdf")
        self.assertIn("formulario-B1-Demo_PDF.pdf", r.headers["content-disposition"])
        t = texto(r.content)
        self.assertIn("125,00", t)  # 10 × 12,50
        self.assertIn("Doce 50/100 Bolivianos", t)

    def test_pdf_b2_sin_apu_no_falla(self):
        r = self.cliente.get(f"/proyectos/{self.pid}/pdf/b2")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Todavía no hay ítems con análisis de precios", texto(r.content))

    def test_formulario_invalido(self):
        self.assertEqual(self.cliente.get(f"/proyectos/{self.pid}/pdf/b3").status_code, 422)

    def test_proyecto_inexistente(self):
        self.assertEqual(self.cliente.get("/proyectos/9999/pdf/b1").status_code, 404)

    def test_excel_solo_b1_y_solo_b2(self):
        from openpyxl import load_workbook
        for solo, hojas in (("b1", ["Formulario B-1"]), ("b2", ["Análisis de precios"]), (None, None)):
            r = self.cliente.post(f"/proyectos/{self.pid}/exportar", json={"solo": solo})
            self.assertEqual(r.status_code, 200, r.text)
            nombres = load_workbook(io.BytesIO(r.content)).sheetnames
            if hojas:
                self.assertEqual(nombres, hojas)
            else:
                self.assertGreater(len(nombres), 2)

    def test_excel_solo_invalido(self):
        self.assertEqual(self.cliente.post(f"/proyectos/{self.pid}/exportar", json={"solo": "b9"}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
