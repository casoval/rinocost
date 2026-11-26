"""Modelo de costos del proyecto: del costo directo del APU al precio unitario (B-2).

Cada proyecto guarda una COPIA del modelo (JSON). Sin modelo (proyectos anteriores) el precio sigue siendo el costo
directo, como antes. Cambiar el modelo recalcula todos los ítems con APU.
"""
from decimal import Decimal
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..costos import ModeloCostos, ResultadoCostos, calcular, obtener_predefinido, validar_modelo
from ..db.models import Item, PerfilCostos, Proyecto
from ..matching import LineaApuNueva, costos_directos


def modelo_del_proyecto(proyecto: Optional[Proyecto]) -> ModeloCostos:
    if proyecto is None or not proyecto.modelo_costos:
        return obtener_predefinido("costo_directo")
    return ModeloCostos.desde_dict(proyecto.modelo_costos)


def calcular_apu(modelo: ModeloCostos, lineas: Sequence[LineaApuNueva]) -> Optional[ResultadoCostos]:
    """None si el APU está incompleto (nunca se inventa un precio)."""
    d = costos_directos(lineas)
    if d is None:
        return None
    return calcular(modelo, d["material"], d["mano_obra"], d["equipo"])


def precio_unitario(modelo: ModeloCostos, lineas: Sequence[LineaApuNueva]) -> Optional[Decimal]:
    r = calcular_apu(modelo, lineas)
    return None if r is None else r.precio


def asignar_modelo(db: Session, proyecto: Proyecto, definicion: dict) -> list[str]:
    """Valida y guarda el modelo del proyecto, y recalcula sus ítems. Devuelve los problemas (vacío = guardado)."""
    try:
        modelo = ModeloCostos.desde_dict(definicion)
    except (KeyError, TypeError, ValueError, ArithmeticError) as e:
        return [f"El modelo no tiene el formato esperado ({e!r})."]
    problemas = validar_modelo(modelo)
    if problemas:
        return problemas
    proyecto.modelo_costos = modelo.a_dict()
    db.flush()
    from .apu import recalcular_item  # import tardío: apu.py usa este módulo
    for it in db.scalars(select(Item).join(Item.modulo).where(Item.modulo.has(proyecto_id=proyecto.id))).all():
        if it.apu_id is not None:
            recalcular_item(it)
    db.commit()
    return []


# ---- Perfiles del usuario y elección del modelo ------------------------------------------------------------

def _validado(definicion: dict) -> ModeloCostos:
    try:
        m = ModeloCostos.desde_dict(definicion)
    except (KeyError, TypeError, ValueError, ArithmeticError) as e:
        raise ValueError(f"El modelo no tiene el formato esperado ({e!r}).") from e
    problemas = validar_modelo(m)
    if problemas:
        raise ValueError(" | ".join(problemas))
    return m


def listar_modelos(db: Session) -> list[dict]:
    """Predefinidos + perfiles propios, cada uno con su `clave` (predefinido:<codigo> | perfil:<id>)."""
    from ..costos import MODELOS_PREDEFINIDOS
    out = [{**obtener_predefinido(c).a_dict(), "clave": f"predefinido:{c}", "propio": False, "id": None}
           for c in MODELOS_PREDEFINIDOS]
    for p in db.scalars(select(PerfilCostos).order_by(PerfilCostos.nombre)).all():
        out.append({**p.definicion, "nombre": p.nombre, "descripcion": p.descripcion or p.definicion.get("descripcion", ""),
                    "clave": f"perfil:{p.id}", "propio": True, "id": p.id})
    return out


def resolver_modelo(db: Session, clave: Optional[str]) -> ModeloCostos:
    """'predefinido:bolivia_b2' | 'perfil:3' | None (= B-2 de Bolivia). Lanza LookupError si no existe."""
    if not clave:
        return obtener_predefinido("bolivia_b2")
    tipo, _, valor = clave.partition(":")
    if tipo == "predefinido":
        try:
            return obtener_predefinido(valor)
        except KeyError as e:
            raise LookupError(str(e)) from e
    if tipo == "perfil" and valor.isdigit():
        perfil = db.get(PerfilCostos, int(valor))
        if perfil is None:
            raise LookupError("Ese perfil de cálculo ya no existe.")
        return ModeloCostos.desde_dict(perfil.definicion)
    raise LookupError(f"Modelo desconocido: '{clave}'.")


def guardar_perfil(db: Session, nombre: str, definicion: dict, perfil_id: Optional[int] = None) -> PerfilCostos:
    nombre = (nombre or "").strip()
    if not nombre:
        raise ValueError("El perfil necesita un nombre.")
    m = _validado(definicion)
    existente = db.scalar(select(PerfilCostos).where(PerfilCostos.nombre == nombre))
    if existente is not None and existente.id != perfil_id:
        raise ValueError(f"Ya tienes un perfil llamado «{nombre}».")
    perfil = db.get(PerfilCostos, perfil_id) if perfil_id is not None else None
    if perfil_id is not None and perfil is None:
        raise LookupError("Ese perfil ya no existe.")
    if perfil is None:
        perfil = PerfilCostos(nombre=nombre, definicion=m.a_dict())
        db.add(perfil)
    perfil.nombre, perfil.definicion, perfil.descripcion = nombre, m.a_dict(), m.descripcion
    db.commit()
    return perfil


def borrar_perfil(db: Session, perfil_id: int) -> None:
    perfil = db.get(PerfilCostos, perfil_id)
    if perfil is None:
        raise LookupError("Ese perfil ya no existe.")
    db.delete(perfil)  # los proyectos conservan su copia
    db.commit()
