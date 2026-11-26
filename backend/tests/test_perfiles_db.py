import importlib.util
import unittest
from decimal import Decimal

HAY_DEPS = all(importlib.util.find_spec(m) for m in ("sqlalchemy", "pydantic"))
if HAY_DEPS:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.costos import ModeloCostos, obtener_predefinido
    from app.db.base import Base
    from app.services import costos as srv
    from tests.test_bibliotecas_db import _b1
    from app.services import proyectos as proy


@unittest.skipUnless(HAY_DEPS, "Faltan dependencias.")
class TestPerfiles(unittest.TestCase):
    def setUp(self):
        e = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
        Base.metadata.create_all(e)
        self.db = sessionmaker(bind=e, expire_on_commit=False)()

    def tearDown(self):
        self.db.close()

    def _mio(self):
        m = obtener_predefinido("bolivia_b2")
        m.paso("cargas_sociales").porcentaje = Decimal("71.18")
        m.paso("util").porcentaje = Decimal("7")
        return m.a_dict()

    def test_guardar_listar_y_resolver(self):
        p = srv.guardar_perfil(self.db, "Licitación Potosí", self._mio())
        claves = [m["clave"] for m in srv.listar_modelos(self.db)]
        self.assertEqual(claves[:3], ["predefinido:bolivia_b2", "predefinido:privado_simple", "predefinido:costo_directo"])
        self.assertIn(f"perfil:{p.id}", claves)
        m = srv.resolver_modelo(self.db, f"perfil:{p.id}")
        self.assertEqual(m.paso("cargas_sociales").porcentaje, Decimal("71.18"))
        self.assertEqual(srv.resolver_modelo(self.db, None).codigo, "bolivia_b2")
        with self.assertRaises(LookupError):
            srv.resolver_modelo(self.db, "perfil:999")

    def test_nombre_repetido_vacio_y_modelo_invalido(self):
        srv.guardar_perfil(self.db, "A", self._mio())
        with self.assertRaises(ValueError):
            srv.guardar_perfil(self.db, "A", self._mio())
        with self.assertRaises(ValueError):
            srv.guardar_perfil(self.db, "  ", self._mio())
        malo = self._mio(); malo["secciones"][1]["pasos"][0]["base"] = ["nada"]
        with self.assertRaises(ValueError):
            srv.guardar_perfil(self.db, "B", malo)

    def test_actualizar_y_borrar_no_afecta_proyectos(self):
        perfil = srv.guardar_perfil(self.db, "Mío", self._mio())
        proyecto = proy.crear_desde_b1(self.db, _b1(), "P", None, srv.resolver_modelo(self.db, f"perfil:{perfil.id}").a_dict())
        cambiado = self._mio(); cambiado["secciones"][1]["pasos"][0]["porcentaje"] = "60"
        srv.guardar_perfil(self.db, "Mío", cambiado, perfil.id)  # mismo nombre, mismo id: permitido
        self.assertEqual(proyecto.modelo_costos["secciones"][1]["pasos"][0]["porcentaje"], "71.18")  # copia congelada
        srv.borrar_perfil(self.db, perfil.id)
        self.assertEqual(proyecto.modelo_costos["codigo"], "bolivia_b2")
        with self.assertRaises(LookupError):
            srv.borrar_perfil(self.db, perfil.id)

    def test_metadatos_de_rango_viajan_en_el_modelo(self):
        d = obtener_predefinido("bolivia_b2").a_dict()
        cs = d["secciones"][1]["pasos"][0]
        self.assertEqual((cs["minimo"], cs["maximo"]), ("55", "71.18"))
        self.assertEqual(ModeloCostos.desde_dict(d).paso("gg").maximo, Decimal("15"))


if __name__ == "__main__":
    unittest.main()
