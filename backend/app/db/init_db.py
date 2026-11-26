"""Crea (o reinicia) las tablas.   python -m app.db.init_db [--reset]"""
import argparse

from sqlalchemy import inspect, select, text

from . import models
from .base import Base
from .session import DATABASE_URL, SessionLocal, engine

DEPARTAMENTOS = ["La Paz", "Cochabamba", "Santa Cruz", "Oruro", "Potosí", "Chuquisaca", "Tarija", "Beni", "Pando"]


def _agregar_columnas_faltantes() -> None:
    """Agrega columnas nuevas a tablas que ya existen (create_all no lo hace), para no perder los proyectos."""
    insp = inspect(engine)
    nuevas = {"proyecto": [("modelo_costos", "JSON")]}
    with engine.begin() as con:
        for tabla, columnas in nuevas.items():
            if not insp.has_table(tabla):
                continue
            existentes = {c["name"] for c in insp.get_columns(tabla)}
            for nombre, tipo in columnas:
                if nombre not in existentes:
                    con.execute(text(f"ALTER TABLE {tabla} ADD COLUMN {nombre} {tipo}"))


def crear() -> None:
    Base.metadata.create_all(engine)
    _agregar_columnas_faltantes()


def reiniciar() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def sembrar_regiones() -> None:
    with SessionLocal() as db:
        if db.scalars(select(models.Region).limit(1)).first():
            return
        pais = models.Region(nombre="Bolivia", tipo="pais")
        db.add(pais)
        db.flush()
        db.add_all(models.Region(nombre=d, tipo="departamento", padre_id=pais.id) for d in DEPARTAMENTOS)
        db.commit()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="BORRA todo y vuelve a crear las tablas")
    args = ap.parse_args()
    reiniciar() if args.reset else crear()
    sembrar_regiones()
    print(("Base reiniciada: " if args.reset else "Base lista: ") + DATABASE_URL)


if __name__ == "__main__":
    main()
