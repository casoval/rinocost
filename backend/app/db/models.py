"""Modelo de datos (primera versión).

Ya incluye lo que se usa hoy (proyecto, módulos, ítems del B-1, alertas) y la base
de lo que viene (regiones, bibliotecas, recursos con precio por región, APU con
origen por línea). Mientras el esquema cambie seguido, se reinicia con:
    python -m app.db.init_db --reset
"""
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


class Region(Base):
    __tablename__ = "region"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    tipo: Mapped[str] = mapped_column(String(20))  # pais | departamento | ciudad | zona
    padre_id: Mapped[Optional[int]] = mapped_column(ForeignKey("region.id"))


# ---- Proyecto importado desde la convocatoria ------------------------------


class Proyecto(Base):
    __tablename__ = "proyecto"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(200))
    entidad: Mapped[Optional[str]] = mapped_column(String(200))
    region_id: Mapped[Optional[int]] = mapped_column(ForeignKey("region.id"))
    archivo_b1: Mapped[Optional[str]] = mapped_column(String(255))
    modo_recursos: Mapped[str] = mapped_column(String(20), default="hibrido")  # pliego | biblioteca | hibrido
    modelo_costos: Mapped[Optional[dict]] = mapped_column(JSON)  # copia congelada del modelo de cálculo (None = solo costo directo)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)

    modulos: Mapped[list["Modulo"]] = relationship(
        back_populates="proyecto", cascade="all, delete-orphan", order_by="Modulo.orden"
    )
    alertas: Mapped[list["AlertaImportacion"]] = relationship(
        back_populates="proyecto", cascade="all, delete-orphan", order_by="AlertaImportacion.id"
    )
    apus: Mapped[list["Apu"]] = relationship(back_populates="proyecto", cascade="all, delete-orphan")


class Modulo(Base):
    __tablename__ = "modulo"
    id: Mapped[int] = mapped_column(primary_key=True)
    proyecto_id: Mapped[int] = mapped_column(ForeignKey("proyecto.id", ondelete="CASCADE"), index=True)
    codigo: Mapped[str] = mapped_column(String(20))
    nombre: Mapped[str] = mapped_column(String(200))
    orden: Mapped[int] = mapped_column(Integer)

    proyecto: Mapped["Proyecto"] = relationship(back_populates="modulos")
    items: Mapped[list["Item"]] = relationship(
        back_populates="modulo", cascade="all, delete-orphan", order_by="Item.orden"
    )


class Item(Base):
    """Ítem del proyecto. Los campos del B-1 son de solo lectura (bloqueado=True)."""

    __tablename__ = "item"
    id: Mapped[int] = mapped_column(primary_key=True)
    modulo_id: Mapped[int] = mapped_column(ForeignKey("modulo.id", ondelete="CASCADE"), index=True)
    numero: Mapped[int] = mapped_column(Integer)  # numeración original del B-1
    orden: Mapped[int] = mapped_column(Integer)
    descripcion: Mapped[str] = mapped_column(Text)
    descripcion_original: Mapped[str] = mapped_column(Text)
    unidad: Mapped[str] = mapped_column(String(20))
    unidad_normalizada: Mapped[str] = mapped_column(String(20))
    cantidad: Mapped[Optional[float]] = mapped_column(Numeric(18, 4))
    cantidad_texto: Mapped[str] = mapped_column(String(40))
    pagina: Mapped[int] = mapped_column(Integer, default=1)
    bloqueado: Mapped[bool] = mapped_column(Boolean, default=True)
    origen: Mapped[str] = mapped_column(String(20), default="b1")  # b1 | biblioteca | manual | ifc | plantilla
    modo_precio: Mapped[str] = mapped_column(String(20), default="pendiente")  # pendiente | directo | apu | global
    precio_unitario: Mapped[Optional[float]] = mapped_column(Numeric(18, 4))
    apu_id: Mapped[Optional[int]] = mapped_column(ForeignKey("apu.id", ondelete="SET NULL"))
    vinculo_confianza: Mapped[Optional[str]] = mapped_column(String(10))  # alta | media | baja (del vínculo con la biblioteca)
    vinculo_confirmado: Mapped[bool] = mapped_column(Boolean, default=False)  # True si la persona lo eligió o confirmó

    modulo: Mapped["Modulo"] = relationship(back_populates="items")
    apu: Mapped[Optional["Apu"]] = relationship(foreign_keys="Item.apu_id")
    especificacion: Mapped[Optional["EspecificacionItem"]] = relationship(cascade="all, delete-orphan", uselist=False)
    requisitos: Mapped[list["RequisitoRecurso"]] = relationship(
        cascade="all, delete-orphan", order_by="RequisitoRecurso.id"
    )
    datos_tecnicos: Mapped[list["DatoTecnicoItem"]] = relationship(
        cascade="all, delete-orphan", order_by="DatoTecnicoItem.id"
    )


class EspecificacionItem(Base):
    """Especificación técnica asignada a un ítem (por número). El B-1 sigue mandando."""

    __tablename__ = "especificacion_item"
    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id", ondelete="CASCADE"), unique=True)
    titulo: Mapped[str] = mapped_column(Text)
    unidad_spec: Mapped[Optional[str]] = mapped_column(String(40))
    modulo_spec: Mapped[Optional[str]] = mapped_column(String(200))
    pagina: Mapped[int] = mapped_column(Integer, default=1)
    archivo: Mapped[Optional[str]] = mapped_column(String(255))
    sin_materiales: Mapped[bool] = mapped_column(Boolean, default=False)
    caracteristicas: Mapped[Optional[list]] = mapped_column(JSON)


class RequisitoRecurso(Base):
    """Recurso que la especificación pide para el ítem (sin cantidad: eso lo define el APU)."""

    __tablename__ = "requisito_recurso"
    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(20))  # material | mano_obra | equipo
    nombre: Mapped[str] = mapped_column(String(300))
    unidad: Mapped[Optional[str]] = mapped_column(String(20))
    unidad_normalizada: Mapped[Optional[str]] = mapped_column(String(20))
    detalle: Mapped[Optional[str]] = mapped_column(String(300))
    pagina: Mapped[int] = mapped_column(Integer)
    fragmento: Mapped[str] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(String(20), default="pendiente")  # pendiente | vinculado | confirmado | descartado
    recurso_id: Mapped[Optional[int]] = mapped_column(ForeignKey("recurso.id", ondelete="SET NULL"))


class DatoTecnicoItem(Base):
    __tablename__ = "dato_tecnico_item"
    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(30))  # dosificacion | espesor | cemento_minimo | rendimiento_declarado | espera
    valor: Mapped[str] = mapped_column(String(120))
    fragmento: Mapped[str] = mapped_column(Text)
    pagina: Mapped[int] = mapped_column(Integer)


class AlertaImportacion(Base):
    __tablename__ = "alerta_importacion"
    id: Mapped[int] = mapped_column(primary_key=True)
    proyecto_id: Mapped[int] = mapped_column(ForeignKey("proyecto.id", ondelete="CASCADE"), index=True)
    item_numero: Mapped[Optional[int]] = mapped_column(Integer)
    origen: Mapped[str] = mapped_column(String(20), default="b1")  # b1 | especificaciones
    nivel: Mapped[str] = mapped_column(String(20))  # error | advertencia | info
    codigo: Mapped[str] = mapped_column(String(60))
    mensaje: Mapped[str] = mapped_column(Text)

    proyecto: Mapped["Proyecto"] = relationship(back_populates="alertas")


# ---- Bibliotecas, recursos y APU (se usan en los próximos pasos) -------------


class Biblioteca(Base):
    __tablename__ = "biblioteca"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(200))
    descripcion: Mapped[Optional[str]] = mapped_column(Text)
    publica: Mapped[bool] = mapped_column(Boolean, default=False)
    region_id: Mapped[Optional[int]] = mapped_column(ForeignKey("region.id"))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)

    apus: Mapped[list["Apu"]] = relationship(
        cascade="all, delete-orphan", foreign_keys="Apu.biblioteca_id", order_by="Apu.id"
    )
    recursos: Mapped[list["Recurso"]] = relationship(cascade="all, delete-orphan", order_by="Recurso.id")
    grupos: Mapped[list["GrupoApu"]] = relationship(cascade="all, delete-orphan", order_by="GrupoApu.orden, GrupoApu.id")


class Recurso(Base):
    __tablename__ = "recurso"
    id: Mapped[int] = mapped_column(primary_key=True)
    biblioteca_id: Mapped[int] = mapped_column(ForeignKey("biblioteca.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(20))  # material | mano_obra | equipo
    nombre: Mapped[str] = mapped_column(String(200))
    nombre_normalizado: Mapped[str] = mapped_column(String(200), index=True)
    unidad: Mapped[str] = mapped_column(String(20))
    # precio con el que se propone el recurso al agregarlo a un ítem (las listas de precios por ciudad llegan después)
    precio_referencia: Mapped[Optional[float]] = mapped_column(Numeric(18, 4))


class Unidad(Base):
    """Unidades de medida que se ofrecen al elegir (predefinidas + las que agrega la persona), por tipo de recurso."""

    __tablename__ = "unidad"
    __table_args__ = (UniqueConstraint("tipo", "clave", name="uq_unidad_tipo_clave"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(20))  # material | mano_obra | equipo | item
    simbolo: Mapped[str] = mapped_column(String(20))
    clave: Mapped[str] = mapped_column(String(20))  # símbolo normalizado (kg == KG == Kg)
    nombre: Mapped[Optional[str]] = mapped_column(String(60))
    predefinida: Mapped[bool] = mapped_column(Boolean, default=False)
    orden: Mapped[int] = mapped_column(Integer, default=1000)


class GrupoApu(Base):
    """Grupo (capítulo) para ordenar los ítems de una biblioteca; opcional y anidable."""

    __tablename__ = "grupo_apu"
    id: Mapped[int] = mapped_column(primary_key=True)
    biblioteca_id: Mapped[int] = mapped_column(ForeignKey("biblioteca.id", ondelete="CASCADE"), index=True)
    padre_id: Mapped[Optional[int]] = mapped_column(ForeignKey("grupo_apu.id", ondelete="SET NULL"))
    nombre: Mapped[str] = mapped_column(String(200))
    orden: Mapped[int] = mapped_column(Integer, default=0)


class PrecioRecurso(Base):
    __tablename__ = "precio_recurso"
    id: Mapped[int] = mapped_column(primary_key=True)
    recurso_id: Mapped[int] = mapped_column(ForeignKey("recurso.id", ondelete="CASCADE"), index=True)
    region_id: Mapped[Optional[int]] = mapped_column(ForeignKey("region.id"))
    valor: Mapped[float] = mapped_column(Numeric(18, 4))
    moneda: Mapped[str] = mapped_column(String(3), default="BOB")
    condicion: Mapped[str] = mapped_column(String(20), default="puesto_en_obra")  # puesto_en_obra | en_deposito
    fecha: Mapped[date] = mapped_column(Date)
    fuente: Mapped[Optional[str]] = mapped_column(String(120))


class Apu(Base):
    """Análisis de precio unitario: de una biblioteca, o copia dentro de un proyecto."""

    __tablename__ = "apu"
    id: Mapped[int] = mapped_column(primary_key=True)
    biblioteca_id: Mapped[Optional[int]] = mapped_column(ForeignKey("biblioteca.id", ondelete="CASCADE"))
    proyecto_id: Mapped[Optional[int]] = mapped_column(ForeignKey("proyecto.id", ondelete="CASCADE"))
    origen_apu_id: Mapped[Optional[int]] = mapped_column(ForeignKey("apu.id", ondelete="SET NULL"))
    codigo: Mapped[Optional[str]] = mapped_column(String(40))
    nombre: Mapped[str] = mapped_column(String(300))
    nombre_normalizado: Mapped[str] = mapped_column(String(300), default="", index=True)
    unidad: Mapped[str] = mapped_column(String(20), default="")
    unidad_normalizada: Mapped[str] = mapped_column(String(20), default="")
    grupo_id: Mapped[Optional[int]] = mapped_column(ForeignKey("grupo_apu.id", ondelete="SET NULL"))

    proyecto: Mapped[Optional["Proyecto"]] = relationship(back_populates="apus", foreign_keys="Apu.proyecto_id")
    lineas: Mapped[list["ApuLinea"]] = relationship(
        back_populates="apu", cascade="all, delete-orphan", order_by="ApuLinea.id"
    )


class ApuLinea(Base):
    __tablename__ = "apu_linea"
    id: Mapped[int] = mapped_column(primary_key=True)
    apu_id: Mapped[int] = mapped_column(ForeignKey("apu.id", ondelete="CASCADE"), index=True)
    recurso_id: Mapped[Optional[int]] = mapped_column(ForeignKey("recurso.id", ondelete="SET NULL"))
    tipo: Mapped[str] = mapped_column(String(20))  # material | mano_obra | equipo
    descripcion: Mapped[str] = mapped_column(String(300))
    unidad: Mapped[str] = mapped_column(String(20))
    cantidad: Mapped[Optional[float]] = mapped_column(Numeric(18, 6))  # consumo o rendimiento
    precio_unitario: Mapped[Optional[float]] = mapped_column(Numeric(18, 4))
    origen_dato: Mapped[str] = mapped_column(String(20), default="manual")  # pliego | biblioteca | ambos | manual
    origen_rendimiento: Mapped[str] = mapped_column(String(20), default="pendiente")
    # biblioteca | medido | calculado | similar | comunitario | referencial | manual | pendiente
    requerido_por_pliego: Mapped[bool] = mapped_column(Boolean, default=False)
    estado: Mapped[str] = mapped_column(String(20), default="completo")  # completo | pendiente
    formula: Mapped[Optional[str]] = mapped_column(Text)
    fuente: Mapped[Optional[str]] = mapped_column(String(300))  # p. ej. página del pliego

    apu: Mapped["Apu"] = relationship(back_populates="lineas")
    recurso: Mapped[Optional["Recurso"]] = relationship()


class Equivalencia(Base):
    """Vínculo ítem -> APU que la persona confirmó: la próxima vez se propone con confianza alta."""

    __tablename__ = "equivalencia"
    id: Mapped[int] = mapped_column(primary_key=True)
    clave: Mapped[str] = mapped_column(String(400), unique=True, index=True)
    apu_id: Mapped[int] = mapped_column(ForeignKey("apu.id", ondelete="CASCADE"))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)


class PerfilCostos(Base):
    """Perfil de cálculo creado por la persona (copia de un modelo, con sus porcentajes y bases)."""

    __tablename__ = "perfil_costos"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), unique=True)
    descripcion: Mapped[Optional[str]] = mapped_column(Text)
    definicion: Mapped[dict] = mapped_column(JSON)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)
