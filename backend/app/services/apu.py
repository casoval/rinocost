"""Vinculación de ítems del proyecto con APU de la biblioteca, según el modo de recursos."""
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import AlertaImportacion, Apu, ApuLinea, Equivalencia, Item, Proyecto
from ..importers.b1_parser import parse_cantidad
from ..matching import (
    ApuRef, Candidato, LineaApuNueva, LineaBib, RequisitoRef, armar_lineas, clave_equivalencia, costo_unitario,
    preparar, sugerir,
)
from ..schemas import RecursoProyectoOut
from . import costos as costos_srv
from ..matching.motor import ORDEN_CONFIANZA


def _dec(v) -> Optional[Decimal]:
    return None if v is None else Decimal(v)


def _requisitos(item: Item) -> list[RequisitoRef]:
    return [RequisitoRef(r.tipo, r.nombre, r.unidad, r.pagina, r.detalle) for r in item.requisitos]


def _lineas_biblioteca(apu: Apu) -> list[LineaBib]:
    return [LineaBib(l.tipo, l.descripcion, l.unidad, _dec(l.cantidad), _dec(l.precio_unitario),
                     l.origen_rendimiento or "biblioteca", l.recurso_id) for l in apu.lineas]


def _apus_de_biblioteca(db: Session, biblioteca_ids: Optional[Sequence[int]]) -> list[Apu]:
    consulta = select(Apu).where(Apu.biblioteca_id.is_not(None))
    if biblioteca_ids:
        consulta = consulta.where(Apu.biblioteca_id.in_(list(biblioteca_ids)))
    return list(db.scalars(consulta).all())


def _equivalencias(db: Session) -> dict[str, int]:
    return {e.clave: e.apu_id for e in db.scalars(select(Equivalencia)).all()}


def candidatos_para_item(
    db: Session, item: Item, biblioteca_ids: Optional[Sequence[int]] = None, maximo: int = 5
) -> list[Candidato]:
    apus = _apus_de_biblioteca(db, biblioteca_ids)
    refs = [ApuRef(a.id, a.nombre, a.unidad_normalizada) for a in apus]
    return sugerir(item.descripcion, item.unidad_normalizada, refs, _equivalencias(db), maximo)


def _guardar_equivalencia(db: Session, item: Item, apu_id: int) -> None:
    clave = clave_equivalencia(item.descripcion, item.unidad_normalizada)
    existente = db.scalar(select(Equivalencia).where(Equivalencia.clave == clave))
    if existente:
        existente.apu_id = apu_id
    else:
        db.add(Equivalencia(clave=clave, apu_id=apu_id))


def vincular_item(
    db: Session, item: Item, apu_id: Optional[int], modo: str, recordar: bool = True,
    confianza: Optional[str] = None, confirmado: bool = True,
) -> list[str]:
    """Crea para el ítem una COPIA del APU de la biblioteca (editarla no altera la biblioteca), armada según el
    modo: 'pliego', 'biblioteca' o 'hibrido'. Con apu_id=None se usan solo los recursos del pliego."""
    proyecto: Proyecto = item.modulo.proyecto
    apu_bib = db.get(Apu, apu_id) if apu_id is not None else None
    if apu_id is not None and (apu_bib is None or apu_bib.biblioteca_id is None):
        raise LookupError("El APU elegido no existe en ninguna biblioteca.")

    res = armar_lineas(modo, _requisitos(item), _lineas_biblioteca(apu_bib) if apu_bib else None)

    if item.apu_id is not None:  # reemplazar el APU anterior del ítem
        viejo = db.get(Apu, item.apu_id)
        item.apu_id = None
        db.flush()
        if viejo is not None and viejo.proyecto_id == proyecto.id:
            db.delete(viejo)

    nuevo = Apu(
        proyecto_id=proyecto.id, origen_apu_id=apu_bib.id if apu_bib else None, nombre=item.descripcion,
        nombre_normalizado=" ".join(preparar(item.descripcion).tokens), unidad=item.unidad,
        unidad_normalizada=item.unidad_normalizada,
    )
    for l in res.lineas:
        nuevo.lineas.append(ApuLinea(
            recurso_id=l.recurso_id, tipo=l.tipo, descripcion=l.descripcion, unidad=l.unidad, cantidad=l.cantidad,
            precio_unitario=l.precio_unitario, origen_dato=l.origen_dato, origen_rendimiento=l.origen_rendimiento,
            requerido_por_pliego=l.requerido_por_pliego, estado=l.estado, fuente=l.fuente,
        ))
    db.add(nuevo)
    db.flush()

    costo = costos_srv.precio_unitario(costos_srv.modelo_del_proyecto(proyecto), res.lineas)
    item.apu = nuevo  # asigna la relación (no solo el id) para que no quede en caché un None
    item.modo_precio = "apu"
    item.precio_unitario = costo  # solo si TODAS las líneas están completas; si no, queda sin precio
    item.vinculo_confianza, item.vinculo_confirmado = confianza, confirmado
    proyecto.modo_recursos = modo

    for a in [a for a in proyecto.alertas if a.origen == "apu" and a.item_numero == item.numero]:
        proyecto.alertas.remove(a)
    for aviso in res.avisos:
        proyecto.alertas.append(AlertaImportacion(
            origen="apu", nivel="advertencia", codigo="apu_aviso", mensaje=f"Ítem {item.numero}: {aviso}",
            item_numero=item.numero))
    if recordar and apu_bib is not None:
        _guardar_equivalencia(db, item, apu_bib.id)
    db.commit()
    return res.avisos


def vincular_automatico(
    db: Session, proyecto: Proyecto, modo: str, biblioteca_ids: Optional[Sequence[int]] = None,
    minimo_confianza: str = "alta",
) -> dict[str, int]:
    """Aplica solo lo seguro: candidatos de la confianza pedida (por omisión 'alta') con la unidad del B-1.
    Lo demás queda para revisar. Los vínculos automáticos NO se recuerdan como equivalencias."""
    if minimo_confianza not in ORDEN_CONFIANZA:
        raise ValueError("minimo_confianza debe ser alta, media o baja.")
    resumen = {"vinculados": 0, "solo_pliego": 0, "por_revisar": 0, "sin_candidato": 0}
    apus = _apus_de_biblioteca(db, biblioteca_ids)
    refs = [ApuRef(a.id, a.nombre, a.unidad_normalizada) for a in apus]
    equiv = _equivalencias(db)
    for item in [it for m in proyecto.modulos for it in m.items]:
        if item.apu_id is not None:
            continue  # ya tiene APU: no se pisa
        cands = sugerir(item.descripcion, item.unidad_normalizada, refs, equiv, maximo=1)
        mejor = cands[0] if cands else None
        if mejor and mejor.compatible_unidad and ORDEN_CONFIANZA[mejor.confianza] >= ORDEN_CONFIANZA[minimo_confianza]:
            vincular_item(db, item, mejor.apu_id, modo, recordar=False, confianza=mejor.confianza, confirmado=False)
            resumen["vinculados"] += 1
        elif modo == "pliego" and item.requisitos:
            vincular_item(db, item, None, "pliego", recordar=False, confianza=None, confirmado=False)
            resumen["solo_pliego"] += 1
        elif mejor:
            resumen["por_revisar"] += 1
        else:
            resumen["sin_candidato"] += 1
    return resumen


# ======================================================================================================
# Edición de las líneas del APU del proyecto (cantidad/rendimiento, precio, origen) y precios de recursos
# ======================================================================================================

_TIPOS = {"material", "mano_obra", "equipo"}
_ORIGENES = {"biblioteca", "medido", "calculado", "similar", "comunitario", "referencial", "manual", "pendiente"}
_CUATRO, _SEIS = Decimal("0.0001"), Decimal("0.000001")


def _num(texto: Optional[str], escala: Decimal, nombre: str) -> Optional[Decimal]:
    """Texto -> Decimal (coma o punto decimal). Vacío = None (queda pendiente). Negativos no se aceptan."""
    if texto is None or str(texto).strip() == "":
        return None
    valor = parse_cantidad(str(texto))
    if valor is None or valor < 0:
        raise ValueError(f"{nombre} no es válido. Usa solo números, con coma para los decimales (por ejemplo 0,25).")
    return valor.quantize(escala, rounding=ROUND_HALF_UP)


def clave_recurso(tipo: str, descripcion: str) -> str:
    """Identifica 'el mismo recurso' dentro de un proyecto (Albañil = albañil = ALBAÑIL)."""
    nombre = " ".join(preparar(descripcion).tokens) or descripcion.strip().lower()
    return f"{tipo}|{nombre}"


def _estado_linea(linea: ApuLinea) -> None:
    linea.estado = "completo" if linea.cantidad is not None and linea.precio_unitario is not None else "pendiente"


def recalcular_item(item: Item) -> None:
    """El precio del ítem sale del APU y solo existe si TODAS sus líneas están completas."""
    if item.apu is None:
        return
    lineas = [
        LineaApuNueva(l.tipo, l.descripcion, l.unidad, _dec(l.cantidad), _dec(l.precio_unitario), l.origen_dato,
                      l.origen_rendimiento, l.requerido_por_pliego, l.estado)
        for l in item.apu.lineas
    ]
    item.modo_precio = "apu"
    item.precio_unitario = costos_srv.precio_unitario(costos_srv.modelo_del_proyecto(item.apu.proyecto), lineas)


def _recalcular_apus(db: Session, apu_ids: set[int]) -> None:
    db.flush()
    if apu_ids:
        for item in db.scalars(select(Item).where(Item.apu_id.in_(list(apu_ids)))).all():
            recalcular_item(item)


def _lineas_del_proyecto(db: Session, proyecto_id: int) -> list[ApuLinea]:
    consulta = select(ApuLinea).join(Apu, ApuLinea.apu_id == Apu.id).where(Apu.proyecto_id == proyecto_id)
    return list(db.scalars(consulta).all())


def _linea_editable(db: Session, linea_id: int) -> ApuLinea:
    linea = db.get(ApuLinea, linea_id)
    if linea is None:
        raise LookupError("No existe esa línea del APU.")
    if linea.apu.proyecto_id is None:
        raise ValueError("Solo se editan los APU del proyecto; los de la biblioteca no se tocan desde aquí.")
    return linea


def editar_linea(db: Session, linea_id: int, cambios: dict, aplicar_precio_a_recurso: bool = True) -> int:
    """Cambia cantidad (consumo o rendimiento por unidad del ítem), precio, unidad u origen de una línea.
    `cambios` solo trae lo que se quiere cambiar. Devuelve el id del proyecto.
    - Si cambia la cantidad y no se indica el origen, el origen pasa a 'manual'.
    - Con aplicar_precio_a_recurso, un precio nuevo se aplica a TODAS las líneas del mismo recurso en el proyecto."""
    linea = _linea_editable(db, linea_id)
    apu = linea.apu
    proyecto_id = apu.proyecto_id
    afectados = {apu.id}
    origen = cambios.get("origen_rendimiento")
    if origen is not None and origen not in _ORIGENES:
        raise ValueError("Origen del rendimiento no válido.")

    if "unidad" in cambios:
        linea.unidad = (cambios["unidad"] or "").strip()[:20]
    if "cantidad" in cambios:
        nueva = _num(cambios["cantidad"], _SEIS, "La cantidad")
        linea.cantidad = nueva
        linea.origen_rendimiento = origen or ("manual" if nueva is not None else "pendiente")
    elif origen is not None:
        linea.origen_rendimiento = origen
    if "precio_unitario" in cambios:
        nuevo = _num(cambios["precio_unitario"], _CUATRO, "El precio")
        objetivo = [linea]
        if aplicar_precio_a_recurso and nuevo is not None:
            clave = clave_recurso(linea.tipo, linea.descripcion)
            objetivo = [l for l in _lineas_del_proyecto(db, proyecto_id) if clave_recurso(l.tipo, l.descripcion) == clave]
        for l in objetivo:
            l.precio_unitario = nuevo
            _estado_linea(l)
            afectados.add(l.apu_id)
    _estado_linea(linea)
    _recalcular_apus(db, afectados)
    db.commit()
    return proyecto_id


def agregar_linea(
    db: Session, item: Item, tipo: str, descripcion: str, unidad: str = "",
    cantidad: Optional[str] = None, precio: Optional[str] = None,
) -> int:
    """Agrega un recurso propio al APU del ítem (si el ítem no tiene APU, se crea uno vacío del proyecto).
    Si no se da precio y el mismo recurso ya tiene precio en el proyecto, se reutiliza."""
    if tipo not in _TIPOS:
        raise ValueError("Tipo no válido: usa material, mano_obra o equipo.")
    descripcion = (descripcion or "").strip()
    if not descripcion:
        raise ValueError("Escribe el nombre del recurso.")
    cant = _num(cantidad, _SEIS, "La cantidad")
    prec = _num(precio, _CUATRO, "El precio")
    proyecto = item.modulo.proyecto

    if item.apu is None:
        apu = Apu(proyecto_id=proyecto.id, nombre=item.descripcion, nombre_normalizado=" ".join(preparar(item.descripcion).tokens),
                  unidad=item.unidad, unidad_normalizada=item.unidad_normalizada)
        db.add(apu)
        db.flush()
        item.apu = apu
    apu = item.apu

    if prec is None:
        clave = clave_recurso(tipo, descripcion)
        for l in _lineas_del_proyecto(db, proyecto.id):
            if l.precio_unitario is not None and clave_recurso(l.tipo, l.descripcion) == clave:
                prec = Decimal(l.precio_unitario)
                break
    linea = ApuLinea(
        tipo=tipo, descripcion=descripcion, unidad=(unidad or "").strip()[:20], cantidad=cant, precio_unitario=prec,
        origen_dato="manual", origen_rendimiento="manual" if cant is not None else "pendiente",
        requerido_por_pliego=False,
    )
    _estado_linea(linea)
    apu.lineas.append(linea)
    _recalcular_apus(db, {apu.id})
    db.commit()
    return proyecto.id


def eliminar_linea(db: Session, linea_id: int) -> int:
    linea = _linea_editable(db, linea_id)
    apu = linea.apu
    proyecto_id = apu.proyecto_id
    apu.lineas.remove(linea)  # delete-orphan la borra
    _recalcular_apus(db, {apu.id})
    db.commit()
    return proyecto_id


def fijar_precio_recurso(db: Session, proyecto: Proyecto, clave: str, texto: Optional[str]) -> None:
    """Pone (o quita) el precio de UN recurso en todas las líneas del proyecto que lo usan."""
    precio = _num(texto, _CUATRO, "El precio")
    lineas = [l for l in _lineas_del_proyecto(db, proyecto.id) if clave_recurso(l.tipo, l.descripcion) == clave]
    if not lineas:
        raise LookupError("Ese recurso no está en los APU del proyecto.")
    for l in lineas:
        l.precio_unitario = precio
        _estado_linea(l)
    _recalcular_apus(db, {l.apu_id for l in lineas})
    db.commit()


def recursos_del_proyecto(proyecto: Proyecto) -> list[RecursoProyectoOut]:
    """Lista única de los recursos que usan los APU del proyecto, con su precio (para cargarlos de una vez)."""
    grupos: dict[str, dict] = {}
    for m in proyecto.modulos:
        for it in m.items:
            if it.apu is None:
                continue
            for l in it.apu.lineas:
                g = grupos.setdefault(clave_recurso(l.tipo, l.descripcion),
                                      {"tipo": l.tipo, "nombre": l.descripcion, "unidad": "", "items": set(), "precios": []})
                g["items"].add(it.id)
                g["precios"].append(None if l.precio_unitario is None else Decimal(l.precio_unitario))
                if not g["unidad"] and l.unidad:
                    g["unidad"] = l.unidad
    salida = []
    for clave, g in grupos.items():
        distintos = {p for p in g["precios"] if p is not None}
        faltan = any(p is None for p in g["precios"])
        unico = format(next(iter(distintos)).normalize(), "f") if len(distintos) == 1 else None
        if not distintos:
            estado = "sin_precio"
        elif len(distintos) == 1 and not faltan:
            estado = "completo"
        else:
            estado = "varios"
        salida.append(RecursoProyectoOut(clave=clave, tipo=g["tipo"], nombre=g["nombre"], unidad=g["unidad"],
                                         usos=len(g["items"]), precio=unico, estado=estado))
    orden = {"material": 0, "mano_obra": 1, "equipo": 2}
    salida.sort(key=lambda r: (orden.get(r.tipo, 9), r.nombre.lower()))
    return salida
