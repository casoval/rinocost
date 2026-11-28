import re
from pathlib import Path
from typing import Literal, Optional

from fastapi import Body, APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy.orm import Session

from ..db.models import Item, Proyecto
from ..db.session import get_db
from ..schemas import (
    CandidatoOut, CronogramaIn, CronogramaOut, CronogramaPdfIn, ExportarIn, LineaEditIn, LineaNuevaIn, PrecioIn, PrecioRecursoIn, ProyectoOut, ProyectoResumen, VincularAutoIn,
    VincularAutoOut, VincularIn,
)
from ..exportadores.excel import exportar_xlsx
from ..exportadores.pdf import exportar_b1_pdf, exportar_b2_item_pdf, exportar_b2_pdf
from ..exportadores.pdf_cronograma import exportar_cronograma_pdf
from ..services import costos as costos_srv
from ..services import apu as apu_srv
from ..services import cronograma as crono_srv
from ..services import proyectos as srv
from ..services.hoja_b2 import construir_hoja_b2
from .subida import leer_b1_subido, leer_especificaciones_subidas

router = APIRouter(prefix="/proyectos", tags=["proyectos"])


def _nombre_seguro(texto: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", texto).strip("_") or "proyecto"


def _o_404(db: Session, proyecto_id: int) -> Proyecto:
    p = db.get(Proyecto, proyecto_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado.")
    return p


@router.get("", response_model=list[ProyectoResumen])
def listar(db: Session = Depends(get_db)):
    return srv.listar_resumenes(db)


@router.post("/importar-b1", response_model=ProyectoOut, status_code=201)
def importar_b1(
    archivo: UploadFile = File(...), nombre: Optional[str] = Form(None), modelo: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """`modelo`: 'predefinido:bolivia_b2' | 'perfil:<id>' (si no se envía, B-2 de Bolivia)."""
    try:
        definicion = costos_srv.resolver_modelo(db, modelo).a_dict()
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    resultado = leer_b1_subido(archivo)
    titulo = (nombre or "").strip() or Path(archivo.filename or "proyecto").stem
    return srv.a_proyecto_out(srv.crear_desde_b1(db, resultado, titulo, archivo.filename, definicion))


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


@router.put("/{proyecto_id}/modelo-costos", response_model=ProyectoOut)
def fijar_modelo_costos(proyecto_id: int, modelo: dict = Body(...), db: Session = Depends(get_db)):
    """Guarda el modelo de cálculo del proyecto (copia editada de un predefinido) y recalcula los precios."""
    proyecto = _o_404(db, proyecto_id)
    problemas = costos_srv.asignar_modelo(db, proyecto, modelo)
    if problemas:
        raise HTTPException(status_code=422, detail=" | ".join(problemas))
    return srv.a_proyecto_out(proyecto)


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


@router.post("/{proyecto_id}/cronograma/pdf")
def cronograma_pdf(proyecto_id: int, datos: CronogramaPdfIn, db: Session = Depends(get_db)):
    """PDF del cronograma con diseño tipo MS Project (tabla + Gantt, ruta crítica en rojo); se abre en la pestaña."""
    proyecto = _o_404(db, proyecto_id)
    crono = _convertir_errores(lambda: crono_srv.calcular_cronograma(proyecto, datos)).model_dump(mode="json")
    contenido = exportar_cronograma_pdf(
        {"nombre": proyecto.nombre, "entidad": proyecto.entidad}, crono, datos.empresa, datos.trabaja_sabados,
        [f.isoformat() for f in datos.feriados], datos.tipo_plazo)
    return Response(
        content=contenido, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="cronograma-{_nombre_seguro(proyecto.nombre)}.pdf"'},
    )


@router.post("/{proyecto_id}/exportar")
def exportar(proyecto_id: int, datos: ExportarIn, db: Session = Depends(get_db)):
    """Excel con el B-1 lleno (precios y literal), resumen, análisis de precios, recursos y, si se pide, cronograma."""
    proyecto = _o_404(db, proyecto_id)
    crono = None
    if datos.cronograma is not None:
        crono = _convertir_errores(lambda: crono_srv.calcular_cronograma(proyecto, datos.cronograma)).model_dump(mode="json")
    contenido = exportar_xlsx(srv.a_proyecto_out(proyecto).model_dump(mode="json"), crono, datos.solo)
    nombre = _nombre_seguro(proyecto.nombre)
    prefijo = {"b1": "formulario-B1", "b2": "formulario-B2"}.get(datos.solo or "", "presupuesto")
    return Response(
        content=contenido,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{prefijo}-{nombre}.xlsx"'},
    )


@router.get("/{proyecto_id}/pdf/{formulario}")
def exportar_pdf(proyecto_id: int, formulario: Literal["b1", "b2"], db: Session = Depends(get_db)):
    """PDF listo para imprimir del Formulario B-1 (presupuesto) o B-2 (análisis de precios, uno por ítem), con el formato del DBC."""
    proyecto = _o_404(db, proyecto_id)
    datos = srv.a_proyecto_out(proyecto).model_dump(mode="json")
    contenido = exportar_b1_pdf(datos) if formulario == "b1" else exportar_b2_pdf(datos)
    return Response(
        content=contenido, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="formulario-{formulario.upper()}-{_nombre_seguro(proyecto.nombre)}.pdf"'},  # inline: se abre en la pestaña
    )


@router.get("/items/{item_id}/hoja-b2")
def hoja_b2_del_item(item_id: int, db: Session = Depends(get_db)):
    """Hoja B-2 (análisis de precio unitario) de un ítem con el modelo de cálculo del proyecto, calculada en el servidor."""
    item = _item_o_404(db, item_id)
    proyecto = db.get(Proyecto, item.modulo.proyecto_id)
    datos = srv.a_proyecto_out(proyecto).model_dump(mode="json")
    fila = next((it for m in datos["modulos"] for it in m["items"] if it["id"] == item_id), None)
    return construir_hoja_b2(datos, fila)


@router.get("/items/{item_id}/pdf-b2")
def pdf_b2_del_item(item_id: int, db: Session = Depends(get_db)):
    """PDF de la hoja B-2 de un ítem; se abre en el visor del navegador (inline)."""
    item = _item_o_404(db, item_id)
    proyecto = db.get(Proyecto, item.modulo.proyecto_id)
    datos = srv.a_proyecto_out(proyecto).model_dump(mode="json")
    fila = next((it for m in datos["modulos"] for it in m["items"] if it["id"] == item_id), None)
    return Response(
        content=exportar_b2_item_pdf(datos, fila), media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="B2-item{item.numero}-{_nombre_seguro(proyecto.nombre)}.pdf"'},
    )
