"""Crea (o reinicia) las tablas.   python -m app.db.init_db [--reset]"""
import argparse

from sqlalchemy import select

from . import models
from .base import Base
from .session import DATABASE_URL, SessionLocal, engine

DEPARTAMENTOS = ["La Paz", "Cochabamba", "Santa Cruz", "Oruro", "Potosí", "Chuquisaca", "Tarija", "Beni", "Pando"]


def crear() -> None:
    Base.metadata.create_all(engine)


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
