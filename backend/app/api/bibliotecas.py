from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from ..db.models import Biblioteca
from ..db.session import get_db
from ..importers.biblioteca_excel import crear_plantilla_bytes
from ..schemas import AlertaFilaOut, ApuResumenOut, BibliotecaOut, ImportacionBibliotecaOut
from ..services import bibliotecas as srv
from .subida import leer_biblioteca_subida

router = APIRouter(prefix="/bibliotecas", tags=["bibliotecas"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("", response_model=list[BibliotecaOut])
def listar(db: Session = Depends(get_db)):
    return srv.listar(db)


@router.get("/plantilla.xlsx")
def plantilla():
    """Plantilla de Excel para cargar una biblioteca (una fila por recurso de cada APU)."""
    return Response(content=crear_plantilla_bytes(), media_type=XLSX,
                    headers={"Content-Disposition": 'attachment; filename="plantilla-biblioteca.xlsx"'})


@router.post("/importar-excel", response_model=ImportacionBibliotecaOut, status_code=201)
def importar_excel(archivo: UploadFile = File(...), nombre: Optional[str] = Form(None), db: Session = Depends(get_db)):
    resultado = leer_biblioteca_subida(archivo)
    titulo = (nombre or "").strip() or Path(archivo.filename or "Biblioteca").stem
    biblioteca = srv.crear_desde_excel(db, titulo, resultado)
    return ImportacionBibliotecaOut(
        biblioteca=srv.a_biblioteca_out(biblioteca),
        alertas=[AlertaFilaOut(nivel=a.nivel, codigo=a.codigo, mensaje=a.mensaje, fila=a.fila) for a in resultado.alertas],
    )


def _o_404(db: Session, biblioteca_id: int) -> Biblioteca:
    b = db.get(Biblioteca, biblioteca_id)
    if b is None:
        raise HTTPException(status_code=404, detail="Biblioteca no encontrada.")
    return b


@router.get("/{biblioteca_id}/apus", response_model=list[ApuResumenOut])
def apus(biblioteca_id: int, db: Session = Depends(get_db)):
    return srv.listar_apus(db, _o_404(db, biblioteca_id))


@router.delete("/{biblioteca_id}", status_code=204)
def borrar(biblioteca_id: int, db: Session = Depends(get_db)):
    db.delete(_o_404(db, biblioteca_id))
    db.commit()
    return Response(status_code=204)
