"""Lógica de proyectos. Los cálculos viven aquí (servidor = fuente de verdad)."""
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..costos import obtener_predefinido
from ..db.models import (
    AlertaImportacion, DatoTecnicoItem, EspecificacionItem, Item, Modulo, Proyecto, RequisitoRecurso,
)
from ..importers.b1_parser import ResultadoB1, parse_cantidad
from ..importers.spec_parser import ResultadoEspecificaciones, cruzar_con_b1
from ..schemas import (
    AlertaOut, ApuProyectoOut, DatoTecnicoOut, DesgloseOut, ItemOut, LineaApuOut, ModuloOut, ProyectoOut, ProyectoResumen,
    RequisitoOut,
)
from .apu import recursos_del_proyecto
from .bibliotecas import costo_apu
from . import costos as costos_srv
from ..matching import LineaApuNueva

_DOS = Decimal("0.01")


def _redondear(valor: Decimal) -> Decimal:
    return valor.quantize(_DOS, rounding=ROUND_HALF_UP)


def _dos(valor: Optional[Decimal]) -> Optional[str]:
    return None if valor is None else f"{Decimal(valor):.2f}"


def _txt(valor) -> Optional[str]:
    """Decimal -> texto sin ceros sobrantes ('12.0000' -> '12', '0.0400' -> '0.04')."""
    return None if valor is None else format(Decimal(valor).normalize(), "f")


def _apu_out(apu) -> Optional[ApuProyectoOut]:
    if apu is None:
        return None
    pendientes = sum(1 for l in apu.lineas if l.cantidad is None or l.precio_unitario is None)
    costo = costo_apu(apu)
    res = costos_srv.calcular_apu(
        costos_srv.modelo_del_proyecto(apu.proyecto),
        [LineaApuNueva(l.tipo, l.descripcion, l.unidad, None if l.cantidad is None else Decimal(l.cantidad),
                       None if l.precio_unitario is None else Decimal(l.precio_unitario), l.origen_dato,
                       l.origen_rendimiento, l.requerido_por_pliego, l.estado) for l in apu.lineas],
    )
    desglose = None if res is None else [
        DesgloseOut(codigo=l.codigo, etiqueta=l.etiqueta, porcentaje=None if l.porcentaje is None else _txt(l.porcentaje),
                    valor=_dos(l.valor)) for l in res.lineas]
    return ApuProyectoOut(
        id=apu.id, origen_apu_id=apu.origen_apu_id, pendientes=pendientes, costo=_dos(costo),
        precio=None if res is None else _dos(res.precio), desglose=desglose,
        estado="vacio" if not apu.lineas else ("completo" if pendientes == 0 else "incompleto"),
        lineas=[
            LineaApuOut(
                id=l.id, tipo=l.tipo, descripcion=l.descripcion, unidad=l.unidad, cantidad=_txt(l.cantidad),
                precio_unitario=_txt(l.precio_unitario), origen_dato=l.origen_dato,
                origen_rendimiento=l.origen_rendimiento, requerido_por_pliego=l.requerido_por_pliego,
                estado=l.estado, fuente=l.fuente,
            )
            for l in apu.lineas
        ],
    )


def crear_desde_b1(
    db: Session, resultado: ResultadoB1, nombre: str, archivo: Optional[str], modelo: Optional[dict] = None
) -> Proyecto:
    proyecto = Proyecto(nombre=nombre, archivo_b1=archivo, modelo_costos=modelo or obtener_predefinido("bolivia_b2").a_dict())
    for m in resultado.modulos:
        modulo = Modulo(codigo=m.codigo, nombre=m.nombre, orden=m.orden)
        for it in m.items:
            modulo.items.append(
                Item(
                    numero=it.numero,
                    orden=it.orden,
                    descripcion=it.descripcion,
                    descripcion_original=it.descripcion_original,
                    unidad=it.unidad,
                    unidad_normalizada=it.unidad_normalizada,
                    cantidad=it.cantidad,
                    cantidad_texto=it.cantidad_texto,
                    pagina=it.pagina,
                )
            )
        proyecto.modulos.append(modulo)
    for a in resultado.alertas:
        proyecto.alertas.append(
            AlertaImportacion(nivel=a.nivel, codigo=a.codigo, mensaje=a.mensaje, item_numero=a.item_numero)
        )
    db.add(proyecto)
    db.commit()
    db.refresh(proyecto)
    return proyecto


def total_item(item: Item) -> Optional[Decimal]:
    if item.cantidad is None or item.precio_unitario is None:
        return None
    return _redondear(Decimal(item.cantidad) * Decimal(item.precio_unitario))


def a_proyecto_out(p: Proyecto) -> ProyectoOut:
    modulos, total, n_items, con_precio = [], Decimal("0"), 0, 0
    for m in p.modulos:
        items, total_m, con_m = [], Decimal("0"), 0
        for it in m.items:
            t = total_item(it)
            if t is not None:
                total_m += t
            if it.precio_unitario is not None:
                con_m += 1
            items.append(
                ItemOut(
                    id=it.id, numero=it.numero, descripcion=it.descripcion, unidad=it.unidad,
                    unidad_normalizada=it.unidad_normalizada,
                    cantidad=None if it.cantidad is None else str(it.cantidad),
                    cantidad_texto=it.cantidad_texto, pagina=it.pagina, bloqueado=it.bloqueado,
                    modo_precio=it.modo_precio, precio_unitario=_dos(it.precio_unitario), total=_dos(t),
                    tiene_especificacion=it.especificacion is not None,
                    sin_materiales=bool(it.especificacion and it.especificacion.sin_materiales),
                    caracteristicas=list((it.especificacion.caracteristicas or []) if it.especificacion else []),
                    requisitos=[
                        RequisitoOut(id=r.id, tipo=r.tipo, nombre=r.nombre, unidad=r.unidad, detalle=r.detalle,
                                     pagina=r.pagina, fragmento=r.fragmento, estado=r.estado)
                        for r in it.requisitos
                    ],
                    datos_tecnicos=[
                        DatoTecnicoOut(tipo=d.tipo, valor=d.valor, fragmento=d.fragmento, pagina=d.pagina)
                        for d in it.datos_tecnicos
                    ],
                    apu=_apu_out(it.apu), vinculo_confianza=it.vinculo_confianza,
                    vinculo_confirmado=it.vinculo_confirmado,
                )
            )
        modulos.append(
            ModuloOut(id=m.id, codigo=m.codigo, nombre=m.nombre, orden=m.orden, items=items,
                      total=_dos(total_m) or "0.00", items_con_precio=con_m)
        )
        total += total_m
        n_items += len(items)
        con_precio += con_m
    return ProyectoOut(
        id=p.id, nombre=p.nombre, entidad=p.entidad, archivo_b1=p.archivo_b1, creado_en=p.creado_en,
        modulos=modulos,
        alertas=[AlertaOut(id=a.id, item_numero=a.item_numero, origen=a.origen, nivel=a.nivel, codigo=a.codigo,
                           mensaje=a.mensaje) for a in p.alertas],
        total=_dos(total) or "0.00", total_items=n_items, items_con_precio=con_precio,
        items_con_especificacion=sum(1 for m in p.modulos for it in m.items if it.especificacion is not None),
        items_con_apu=sum(1 for m in p.modulos for it in m.items if it.apu_id is not None),
        modo_recursos=p.modo_recursos, modelo_costos=p.modelo_costos,
        recursos=recursos_del_proyecto(p),
    )


def listar_resumenes(db: Session) -> list[ProyectoResumen]:
    resumenes = []
    for p in db.scalars(select(Proyecto).order_by(Proyecto.id.desc())).all():
        out = a_proyecto_out(p)
        resumenes.append(
            ProyectoResumen(id=p.id, nombre=p.nombre, archivo_b1=p.archivo_b1, creado_en=p.creado_en,
                            total_modulos=len(out.modulos), total_items=out.total_items, total=out.total)
        )
    return resumenes


def actualizar_precio(db: Session, item_id: int, texto: Optional[str]) -> Item:
    """Fija el precio unitario directo de un ítem (2 decimales). Vacío = quitar precio."""
    item = db.get(Item, item_id)
    if item is None:
        raise LookupError(f"No existe el ítem {item_id}.")
    if texto is None or texto.strip() == "":
        item.precio_unitario, item.modo_precio = None, "pendiente"
    else:
        valor = parse_cantidad(texto)
        if valor is None or valor < 0:
            raise ValueError("Precio no válido. Usa solo números, con coma para los decimales (por ejemplo 12,50).")
        item.precio_unitario, item.modo_precio = _redondear(valor), "directo"
    db.commit()
    return item


def guardar_especificaciones(
    db: Session, proyecto: Proyecto, esp: ResultadoEspecificaciones, archivo: Optional[str]
) -> Proyecto:
    """Asigna cada especificación a su ítem por NÚMERO. El B-1 manda: no se toca nombre, unidad ni cantidad.
    Volver a importar reemplaza lo anterior (la especificación nueva es la vigente)."""
    items = [it for m in proyecto.modulos for it in m.items]
    por_numero: dict[int, Item] = {}
    for it in items:
        por_numero.setdefault(it.numero, it)

    for it in items:  # limpiar lo importado antes
        it.especificacion = None
        it.requisitos.clear()
        it.datos_tecnicos.clear()
    for a in [a for a in proyecto.alertas if a.origen == "especificaciones"]:
        proyecto.alertas.remove(a)
    db.flush()

    for sp in esp.items:
        item = por_numero.get(sp.numero)
        if item is None or item.especificacion is not None:  # sin ítem en el B-1, o número repetido
            continue
        item.especificacion = EspecificacionItem(
            titulo=sp.titulo, unidad_spec=sp.unidad_spec, modulo_spec=sp.modulo_spec, pagina=sp.pagina_inicio,
            archivo=archivo, sin_materiales=sp.sin_materiales, caracteristicas=list(sp.caracteristicas),
        )
        for r in sp.recursos:
            item.requisitos.append(RequisitoRecurso(
                tipo=r.tipo, nombre=r.nombre, unidad=r.unidad, unidad_normalizada=r.unidad_normalizada,
                detalle=r.detalle, pagina=r.pagina, fragmento=r.fragmento,
            ))
        for d in sp.datos_tecnicos:
            item.datos_tecnicos.append(DatoTecnicoItem(tipo=d.tipo, valor=d.valor, fragmento=d.fragmento, pagina=d.pagina))

    for a in list(esp.alertas) + cruzar_con_b1(esp, items):
        proyecto.alertas.append(AlertaImportacion(
            origen="especificaciones", nivel=a.nivel, codigo=a.codigo, mensaje=a.mensaje, item_numero=a.item_numero))
    db.commit()
    return proyecto
