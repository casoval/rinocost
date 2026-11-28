from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from contextlib import contextmanager

from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import func, select

from ..db.models import Apu, ApuLinea, Biblioteca, GrupoApu, Recurso
from ..db.session import get_db
from ..importers.biblioteca_excel import crear_plantilla_bytes
from ..schemas import (AlertaFilaOut, ApuBibDetalleOut, ApuBibIn, ApuResumenOut, BibliotecaCambios, BibliotecaIn, BibliotecaOut, GrupoIn,
                       GrupoOut, ImportacionBibliotecaOut, LineaBibIn, LineaBibOut, RecursoBibIn, RecursoBibOut)
from ..services import bibliotecas as srv
from ..services import editor_biblioteca as ed
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


# ======================================================================================================================
# Editor: bibliotecas desde cero, grupos, recursos (materiales, mano de obra, equipo), ítems y sus líneas
# ======================================================================================================================
@contextmanager
def _errores():
    try:
        yield
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


def _txt(v) -> Optional[str]:
    return None if v is None else format(Decimal(str(v)).normalize(), "f")


def _grupo_404(db: Session, gid: int) -> GrupoApu:
    g = db.get(GrupoApu, gid)
    if g is None:
        raise HTTPException(status_code=404, detail="Grupo no encontrado.")
    return g


def _recurso_404(db: Session, rid: int) -> Recurso:
    r = db.get(Recurso, rid)
    if r is None:
        raise HTTPException(status_code=404, detail="Recurso no encontrado.")
    return r


def _apu_404(db: Session, aid: int) -> Apu:
    a = db.get(Apu, aid)
    if a is None or a.biblioteca_id is None:
        raise HTTPException(status_code=404, detail="Ítem de biblioteca no encontrado.")
    return a


def _detalle(a: Apu, avisos: Optional[list[str]] = None) -> ApuBibDetalleOut:
    costo = ed.costo_directo(a)
    lineas = []
    for l in a.lineas:
        imp = None if l.cantidad is None or l.precio_unitario is None else f"{l.cantidad * l.precio_unitario:.2f}"
        lineas.append(LineaBibOut(id=l.id, recurso_id=l.recurso_id, tipo=l.tipo, descripcion=l.descripcion, unidad=l.unidad,
                                  cantidad=_txt(l.cantidad), precio_unitario=_txt(l.precio_unitario), importe=imp,
                                  origen_rendimiento=l.origen_rendimiento))
    return ApuBibDetalleOut(id=a.id, biblioteca_id=a.biblioteca_id, codigo=a.codigo, nombre=a.nombre, unidad=a.unidad, grupo_id=a.grupo_id,
                            costo_directo=None if costo is None else f"{costo:.2f}", lineas=lineas, avisos=avisos or [])


def _recurso_out(r: Recurso, usos: int = 0, biblioteca: Optional[str] = None) -> RecursoBibOut:
    return RecursoBibOut(id=r.id, tipo=r.tipo, nombre=r.nombre, unidad=r.unidad, precio_referencia=_txt(r.precio_referencia),
                         usos=usos, biblioteca_nombre=biblioteca)


class GrupoCambios(BaseModel):
    nombre: Optional[str] = None
    padre_id: Optional[int] = None
    orden: Optional[int] = None


class RecursoCambios(BaseModel):
    nombre: Optional[str] = None
    unidad: Optional[str] = None
    precio_referencia: Optional[Decimal] = None


class ApuCambios(BaseModel):
    nombre: Optional[str] = None
    unidad: Optional[str] = None
    grupo_id: Optional[int] = None
    codigo: Optional[str] = None


class LineaCambios(BaseModel):
    cantidad: Optional[Decimal] = None
    precio_unitario: Optional[Decimal] = None
    origen_rendimiento: Optional[str] = None


class CopiarRecursoIn(BaseModel):
    recurso_id: int


@router.post("", response_model=BibliotecaOut, status_code=201)
def crear_vacia(datos: BibliotecaIn, db: Session = Depends(get_db)):
    """Biblioteca nueva y vacía: la persona crea sus propios ítems y recursos."""
    with _errores():
        return srv.a_biblioteca_out(ed.crear_biblioteca(db, datos.nombre, datos.descripcion))


@router.patch("/{biblioteca_id}", response_model=BibliotecaOut)
def renombrar(biblioteca_id: int, datos: BibliotecaCambios, db: Session = Depends(get_db)):
    with _errores():
        return srv.a_biblioteca_out(ed.actualizar_biblioteca(db, _o_404(db, biblioteca_id), datos.nombre, datos.descripcion))


# ---- grupos
@router.get("/{biblioteca_id}/grupos", response_model=list[GrupoOut])
def grupos(biblioteca_id: int, db: Session = Depends(get_db)):
    b = _o_404(db, biblioteca_id)
    cuentas = dict(db.execute(select(Apu.grupo_id, func.count()).where(Apu.biblioteca_id == b.id, Apu.grupo_id.is_not(None)).group_by(Apu.grupo_id)).all())
    return [GrupoOut(id=g.id, nombre=g.nombre, padre_id=g.padre_id, orden=g.orden, items=int(cuentas.get(g.id, 0))) for g in b.grupos]


@router.post("/{biblioteca_id}/grupos", response_model=GrupoOut, status_code=201)
def crear_grupo(biblioteca_id: int, datos: GrupoIn, db: Session = Depends(get_db)):
    with _errores():
        g = ed.crear_grupo(db, _o_404(db, biblioteca_id), datos.nombre, datos.padre_id)
    return GrupoOut(id=g.id, nombre=g.nombre, padre_id=g.padre_id, orden=g.orden, items=0)


@router.patch("/grupos/{grupo_id}", response_model=GrupoOut)
def cambiar_grupo(grupo_id: int, datos: GrupoCambios, db: Session = Depends(get_db)):
    g = _grupo_404(db, grupo_id)
    with _errores():
        ed.actualizar_grupo(db, g, datos.nombre, datos.padre_id, "padre_id" in datos.model_fields_set, datos.orden)
    n = db.scalar(select(func.count()).select_from(Apu).where(Apu.grupo_id == g.id)) or 0
    return GrupoOut(id=g.id, nombre=g.nombre, padre_id=g.padre_id, orden=g.orden, items=int(n))


@router.delete("/grupos/{grupo_id}", status_code=204)
def borrar_grupo(grupo_id: int, db: Session = Depends(get_db)):
    ed.borrar_grupo(db, _grupo_404(db, grupo_id))
    return Response(status_code=204)


# ---- recursos
@router.get("/{biblioteca_id}/recursos", response_model=list[RecursoBibOut])
def recursos(biblioteca_id: int, tipo: Optional[str] = None, q: Optional[str] = None, db: Session = Depends(get_db)):
    return [_recurso_out(r, usos) for r, usos in ed.listar_recursos(db, _o_404(db, biblioteca_id), tipo, q)]


@router.post("/{biblioteca_id}/recursos", response_model=RecursoBibOut, status_code=201)
def crear_recurso(biblioteca_id: int, datos: RecursoBibIn, db: Session = Depends(get_db)):
    with _errores():
        return _recurso_out(ed.crear_recurso(db, _o_404(db, biblioteca_id), datos.tipo, datos.nombre, datos.unidad, datos.precio_referencia))


@router.get("/{biblioteca_id}/recursos-de-otras", response_model=list[RecursoBibOut])
def recursos_de_otras(biblioteca_id: int, q: str, tipo: Optional[str] = None, db: Session = Depends(get_db)):
    """Busca en tus OTRAS bibliotecas, para traer un recurso a esta."""
    _o_404(db, biblioteca_id)
    return [_recurso_out(r, 0, nombre) for r, nombre in ed.buscar_recursos_otras_bibliotecas(db, q, tipo, biblioteca_id)]


@router.post("/{biblioteca_id}/recursos/copiar", response_model=RecursoBibOut, status_code=201)
def copiar_recurso(biblioteca_id: int, datos: CopiarRecursoIn, db: Session = Depends(get_db)):
    with _errores():
        return _recurso_out(ed.copiar_recurso(db, _o_404(db, biblioteca_id), datos.recurso_id))


@router.patch("/recursos/{recurso_id}", response_model=RecursoBibOut)
def cambiar_recurso(recurso_id: int, datos: RecursoCambios, db: Session = Depends(get_db)):
    r = _recurso_404(db, recurso_id)
    with _errores():
        ed.actualizar_recurso(db, r, datos.nombre, datos.unidad, datos.precio_referencia, "precio_referencia" in datos.model_fields_set)
    return _recurso_out(r)


@router.delete("/recursos/{recurso_id}", status_code=204)
def borrar_recurso(recurso_id: int, forzar: bool = False, db: Session = Depends(get_db)):
    with _errores():
        ed.borrar_recurso(db, _recurso_404(db, recurso_id), forzar)
    return Response(status_code=204)


# ---- ítems y líneas
@router.post("/{biblioteca_id}/apus", response_model=ApuBibDetalleOut, status_code=201)
def crear_apu(biblioteca_id: int, datos: ApuBibIn, db: Session = Depends(get_db)):
    with _errores():
        return _detalle(ed.crear_apu(db, _o_404(db, biblioteca_id), datos.nombre, datos.unidad, datos.grupo_id, datos.codigo))


@router.get("/apus/{apu_id}", response_model=ApuBibDetalleOut)
def detalle_apu(apu_id: int, db: Session = Depends(get_db)):
    return _detalle(_apu_404(db, apu_id))


@router.patch("/apus/{apu_id}", response_model=ApuBibDetalleOut)
def cambiar_apu(apu_id: int, datos: ApuCambios, db: Session = Depends(get_db)):
    a = _apu_404(db, apu_id)
    with _errores():
        ed.actualizar_apu(db, a, datos.nombre, datos.unidad, datos.grupo_id, "grupo_id" in datos.model_fields_set, datos.codigo)
    return _detalle(a)


@router.delete("/apus/{apu_id}", status_code=204)
def borrar_apu(apu_id: int, db: Session = Depends(get_db)):
    ed.borrar_apu(db, _apu_404(db, apu_id))
    return Response(status_code=204)


@router.post("/apus/{apu_id}/duplicar", response_model=ApuBibDetalleOut, status_code=201)
def duplicar_apu(apu_id: int, db: Session = Depends(get_db)):
    return _detalle(ed.duplicar_apu(db, _apu_404(db, apu_id)))


@router.post("/apus/{apu_id}/lineas", response_model=ApuBibDetalleOut, status_code=201)
def agregar_linea(apu_id: int, datos: LineaBibIn, db: Session = Depends(get_db)):
    a = _apu_404(db, apu_id)
    with _errores():
        _l, avisos = ed.agregar_linea(db, a, recurso_id=datos.recurso_id, tipo=datos.tipo, nombre=datos.nombre, unidad=datos.unidad,
                                      cantidad=datos.cantidad, precio=datos.precio_unitario, origen_rendimiento=datos.origen_rendimiento)
    return _detalle(a, avisos)


@router.patch("/lineas/{linea_id}", response_model=ApuBibDetalleOut)
def cambiar_linea(linea_id: int, datos: LineaCambios, db: Session = Depends(get_db)):
    l = db.get(ApuLinea, linea_id)
    if l is None:
        raise HTTPException(status_code=404, detail="Línea no encontrada.")
    with _errores():
        ed.actualizar_linea(db, l, datos.cantidad, datos.precio_unitario, datos.origen_rendimiento,
                            "cantidad" in datos.model_fields_set, "precio_unitario" in datos.model_fields_set)
    return _detalle(l.apu)


@router.delete("/lineas/{linea_id}", response_model=ApuBibDetalleOut)
def borrar_linea(linea_id: int, db: Session = Depends(get_db)):
    l = db.get(ApuLinea, linea_id)
    if l is None:
        raise HTTPException(status_code=404, detail="Línea no encontrada.")
    a = l.apu
    ed.borrar_linea(db, l)
    db.refresh(a)
    return _detalle(a)
