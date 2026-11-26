from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..costos import obtener_predefinido, validar_modelo
from ..db.session import get_db
from ..services import costos as srv

router = APIRouter(prefix="/modelos-costos", tags=["modelos de costos"])


class PerfilIn(BaseModel):
    nombre: str
    modelo: dict


@router.get("")
def listar(db: Session = Depends(get_db)) -> list[dict]:
    """Modelos predefinidos + perfiles propios. Al crear un proyecto se copia el elegido."""
    return srv.listar_modelos(db)


@router.get("/{codigo}")
def obtener(codigo: str) -> dict:
    try:
        m = obtener_predefinido(codigo)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {**m.a_dict(), "problemas": validar_modelo(m)}


def _perfil_out(p) -> dict:
    return {**p.definicion, "nombre": p.nombre, "clave": f"perfil:{p.id}", "propio": True, "id": p.id}


@router.post("/perfiles", status_code=201)
def crear_perfil(datos: PerfilIn, db: Session = Depends(get_db)) -> dict:
    try:
        return _perfil_out(srv.guardar_perfil(db, datos.nombre, datos.modelo))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.put("/perfiles/{perfil_id}")
def actualizar_perfil(perfil_id: int, datos: PerfilIn, db: Session = Depends(get_db)) -> dict:
    try:
        return _perfil_out(srv.guardar_perfil(db, datos.nombre, datos.modelo, perfil_id))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.delete("/perfiles/{perfil_id}", status_code=204)
def borrar_perfil(perfil_id: int, db: Session = Depends(get_db)):
    try:
        srv.borrar_perfil(db, perfil_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return Response(status_code=204)
