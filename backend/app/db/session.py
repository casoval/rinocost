"""Conexión a la base de datos.

Por defecto usa SQLite (cero instalación, ideal para probar).
Para PostgreSQL:  DATABASE_URL=postgresql+psycopg://usuario:clave@localhost:5432/presupuestos
"""
import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./presupuestos.db")
_es_sqlite = DATABASE_URL.startswith("sqlite")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if _es_sqlite else {})

if _es_sqlite:

    @event.listens_for(engine, "connect")
    def _activar_claves_foraneas(dbapi_conn, _registro):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
