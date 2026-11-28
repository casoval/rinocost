from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..schemas import UnidadIn, UnidadOut
from ..services import unidades as srv

router = APIRouter(prefix="/unidades", tags=["unidades"])


def _out(u) -> UnidadOut:
    return UnidadOut(id=u.id, tipo=u.tipo, simbolo=u.simbolo, nombre=u.nombre, predefinida=u.predefinida)


@router.get("", response_model=list[UnidadOut])
def listar(tipo: Optional[str] = None, db: Session = Depends(get_db)):
    """Unidades para elegir: primero las predefinidas del tipo (material, mano_obra, equipo, item) y luego las tuyas.
    Siempre se puede escribir otra: se agrega sola."""
    return [_out(u) for u in srv.listar(db, tipo)]


@router.post("", response_model=UnidadOut, status_code=201)
def agregar(datos: UnidadIn, db: Session = Depends(get_db)):
    try:
        return _out(srv.agregar(db, datos.tipo, datos.simbolo, datos.nombre))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.delete("/{unidad_id}", status_code=204)
def borrar(unidad_id: int, db: Session = Depends(get_db)):
    try:
        srv.borrar(db, unidad_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return Response(status_code=204)
