import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy.orm import Session

from ..db.models import Item, Proyecto
from ..db.session import get_db
from ..schemas import (
    CandidatoOut, CronogramaIn, CronogramaOut, ExportarIn, LineaEditIn, LineaNuevaIn, PrecioIn, PrecioRecursoIn, ProyectoOut, ProyectoResumen, VincularAutoIn,
    VincularAutoOut, VincularIn,
)
from ..exportadores.excel import exportar_xlsx
from ..services import apu as apu_srv
from ..services import cronograma as crono_srv
from ..services import proyectos as srv
from .subida import leer_b1_subido, leer_especificaciones_subidas

router = APIRouter(prefix="/proyectos", tags=["proyectos"])


def _o_404(db: Session, proyecto_id: int) -> Proyecto:
    p = db.get(Proyecto, proyecto_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado.")
    return p


@router.get("", response_model=list[ProyectoResumen])
def listar(db: Session = Depends(get_db)):
    return srv.listar_resumenes(db)


@router.post("/importar-b1", response_model=ProyectoOut, status_code=201)
def importar_b1(archivo: UploadFile = File(...), nombre: Optional[str] = Form(None), db: Session = Depends(get_db)):
    resultado = leer_b1_subido(archivo)
    titulo = (nombre or "").strip() or Path(archivo.filename or "proyecto").stem
    return srv.a_proyecto_out(srv.crear_desde_b1(db, resultado, titulo, archivo.filename))


@router.get("/{proyecto_id}", response_model=ProyectoOut)
def obtener(proyecto_id: int, db: Session = Depends(get_db)):
    return srv.a_proyecto_out(_o_404(db, proyecto_id))


@router.post("/{proyecto_id}/especificaciones", response_model=ProyectoOut)
def importar_especificaciones(proyecto_id: int, archivo: UploadFile = File(...), db: Session = Depends(get_db)):
    """Lee el PDF de especificaciones y lo asigna a los ítems del proyecto por número de ítem."""
    proyecto = _o_404(db, proyecto_id)
    esp = leer_especificaciones_subidas(archivo)
    srv.guardar_especificaciones(db, proyecto, esp, archivo.filename)
    return srv.a_proyecto_out(proyecto)


@router.delete("/{proyecto_id}", status_code=204)
def borrar(proyecto_id: int, db: Session = Depends(get_db)):
    db.delete(_o_404(db, proyecto_id))
    db.commit()
    return Response(status_code=204)


@router.patch("/items/{item_id}/precio", response_model=ProyectoOut)
def fijar_precio(item_id: int, datos: PrecioIn, db: Session = Depends(get_db)):
    try:
        item = srv.actualizar_precio(db, item_id, datos.precio_unitario)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return srv.a_proyecto_out(db.get(Proyecto, item.modulo.proyecto_id))


def _item_o_404(db: Session, item_id: int) -> Item:
    item = db.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Ítem no encontrado.")
    return item


@router.get("/items/{item_id}/candidatos", response_model=list[CandidatoOut])
def candidatos(item_id: int, biblioteca_ids: Optional[list[int]] = Query(None), db: Session = Depends(get_db)):
    """APU de la biblioteca que podrían corresponder al ítem, del más al menos probable."""
    item = _item_o_404(db, item_id)
    return [
        CandidatoOut(apu_id=c.apu_id, nombre=c.nombre, unidad=c.unidad_normalizada, puntaje=c.puntaje,
                     confianza=c.confianza, motivo=c.motivo, compatible_unidad=c.compatible_unidad, avisos=c.avisos)
        for c in apu_srv.candidatos_para_item(db, item, biblioteca_ids)
    ]


@router.post("/items/{item_id}/vincular", response_model=ProyectoOut)
def vincular(item_id: int, datos: VincularIn, db: Session = Depends(get_db)):
    """Copia el APU elegido al ítem, armado según el modo de recursos (pliego, biblioteca o híbrido)."""
    item = _item_o_404(db, item_id)
    try:
        apu_srv.vincular_item(db, item, datos.apu_id, datos.modo, datos.recordar, confianza=datos.confianza, confirmado=True)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return srv.a_proyecto_out(db.get(Proyecto, item.modulo.proyecto_id))


@router.post("/{proyecto_id}/vincular-auto", response_model=VincularAutoOut)
def vincular_auto(proyecto_id: int, datos: VincularAutoIn, db: Session = Depends(get_db)):
    """Vincula solo las coincidencias seguras (confianza alta, misma unidad del B-1). El resto queda para revisar."""
    proyecto = _o_404(db, proyecto_id)
    try:
        resumen = apu_srv.vincular_automatico(db, proyecto, datos.modo, datos.biblioteca_ids, datos.minimo_confianza)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return VincularAutoOut(**resumen, proyecto=srv.a_proyecto_out(proyecto))


def _proyecto_actualizado(db: Session, proyecto_id: int) -> ProyectoOut:
    return srv.a_proyecto_out(db.get(Proyecto, proyecto_id))


def _convertir_errores(accion):
    try:
        return accion()
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.patch("/apu-lineas/{linea_id}", response_model=ProyectoOut)
def editar_linea(linea_id: int, datos: LineaEditIn, db: Session = Depends(get_db)):
    """Cambia la cantidad (rendimiento o consumo por unidad del ítem), el precio, la unidad o el origen de una línea."""
    cambios = datos.model_dump(exclude_unset=True)
    aplicar = cambios.pop("aplicar_precio_a_recurso", True)
    proyecto_id = _convertir_errores(lambda: apu_srv.editar_linea(db, linea_id, cambios, aplicar))
    return _proyecto_actualizado(db, proyecto_id)


@router.delete("/apu-lineas/{linea_id}", response_model=ProyectoOut)
def eliminar_linea(linea_id: int, db: Session = Depends(get_db)):
    proyecto_id = _convertir_errores(lambda: apu_srv.eliminar_linea(db, linea_id))
    return _proyecto_actualizado(db, proyecto_id)


@router.post("/items/{item_id}/lineas", response_model=ProyectoOut)
def agregar_linea(item_id: int, datos: LineaNuevaIn, db: Session = Depends(get_db)):
    item = _item_o_404(db, item_id)
    proyecto_id = _convertir_errores(lambda: apu_srv.agregar_linea(
        db, item, datos.tipo, datos.descripcion, datos.unidad, datos.cantidad, datos.precio_unitario))
    return _proyecto_actualizado(db, proyecto_id)


@router.post("/{proyecto_id}/precio-recurso", response_model=ProyectoOut)
def precio_recurso(proyecto_id: int, datos: PrecioRecursoIn, db: Session = Depends(get_db)):
    """Fija el precio de un recurso en todos los APU del proyecto que lo usan."""
    proyecto = _o_404(db, proyecto_id)
    _convertir_errores(lambda: apu_srv.fijar_precio_recurso(db, proyecto, datos.clave, datos.precio_unitario))
    return _proyecto_actualizado(db, proyecto_id)


@router.post("/{proyecto_id}/cronograma", response_model=CronogramaOut)
def cronograma(proyecto_id: int, datos: CronogramaIn, db: Session = Depends(get_db)):
    """Cronograma desde la mano de obra de los APU: personas, jornada, calendario, secuencia y hitos por módulo."""
    proyecto = _o_404(db, proyecto_id)
    return _convertir_errores(lambda: crono_srv.calcular_cronograma(proyecto, datos))


@router.post("/{proyecto_id}/exportar")
def exportar(proyecto_id: int, datos: ExportarIn, db: Session = Depends(get_db)):
    """Excel con el B-1 lleno (precios y literal), resumen, análisis de precios, recursos y, si se pide, cronograma."""
    proyecto = _o_404(db, proyecto_id)
    crono = None
    if datos.cronograma is not None:
        crono = _convertir_errores(lambda: crono_srv.calcular_cronograma(proyecto, datos.cronograma)).model_dump(mode="json")
    contenido = exportar_xlsx(srv.a_proyecto_out(proyecto).model_dump(mode="json"), crono)
    nombre = re.sub(r"[^A-Za-z0-9_-]+", "_", proyecto.nombre).strip("_") or "proyecto"
    return Response(
        content=contenido,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="presupuesto-{nombre}.xlsx"'},
    )
