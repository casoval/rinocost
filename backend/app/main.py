"""API de la app de presupuestos de construcción.

Ejecutar desde backend/:
    uvicorn app.main:app --reload
Documentación interactiva:  http://127.0.0.1:8000/docs
"""
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse

from .api import bibliotecas, modelos, proyectos
from .api.subida import leer_b1_subido
from .db.init_db import crear, sembrar_regiones

PANTALLA = Path(__file__).parent / "static" / "index.html"


@asynccontextmanager
async def ciclo_de_vida(_app: FastAPI):
    # Crea las tablas que falten (no modifica las que ya existen; para eso: init_db --reset).
    if os.environ.get("AUTO_CREATE_DB", "1") == "1":
        crear()
        sembrar_regiones()
    yield


app = FastAPI(title="Presupuestos de Construcción", version="0.3.0", lifespan=ciclo_de_vida)
app.include_router(proyectos.router)
app.include_router(bibliotecas.router)
app.include_router(modelos.router)


@app.get("/", include_in_schema=False)
def inicio() -> FileResponse:
    """Pantalla simple de vista previa del B-1 (el frontend React corre aparte, en el puerto 5173)."""
    return FileResponse(PANTALLA)


@app.get("/salud")
def salud() -> dict:
    return {"estado": "ok"}


@app.post("/importar/b1")
def vista_previa_b1(archivo: UploadFile = File(...)) -> dict:
    """Lee el B-1 y devuelve el resultado sin guardar nada."""
    return leer_b1_subido(archivo).to_dict()
