from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class RequisitoOut(BaseModel):
    id: int
    tipo: str
    nombre: str
    unidad: Optional[str]
    detalle: Optional[str]
    pagina: int
    fragmento: str
    estado: str


class DatoTecnicoOut(BaseModel):
    tipo: str
    valor: str
    fragmento: str
    pagina: int


class LineaApuOut(BaseModel):
    id: int
    tipo: str
    descripcion: str
    unidad: str
    cantidad: Optional[str]
    precio_unitario: Optional[str]
    origen_dato: str
    origen_rendimiento: str
    requerido_por_pliego: bool
    estado: str
    fuente: Optional[str]


class DesgloseOut(BaseModel):
    codigo: str
    etiqueta: str
    porcentaje: Optional[str] = None
    valor: str


class ApuProyectoOut(BaseModel):
    id: int
    origen_apu_id: Optional[int]
    estado: str  # completo | incompleto | vacio
    pendientes: int
    costo: Optional[str]  # costo directo (materiales + mano de obra + equipo)
    precio: Optional[str] = None  # precio unitario según el modelo de cálculo del proyecto
    desglose: Optional[list[DesgloseOut]] = None
    lineas: list[LineaApuOut]


class RecursoProyectoOut(BaseModel):
    clave: str
    tipo: str
    nombre: str
    unidad: str
    usos: int
    precio: Optional[str]
    estado: str  # completo | sin_precio | varios


class ItemOut(BaseModel):
    id: int
    numero: int
    descripcion: str
    unidad: str
    unidad_normalizada: str
    cantidad: Optional[str]
    cantidad_texto: str
    pagina: int
    bloqueado: bool
    modo_precio: str
    precio_unitario: Optional[str]
    total: Optional[str]
    tiene_especificacion: bool = False
    sin_materiales: bool = False
    requisitos: list[RequisitoOut] = []
    datos_tecnicos: list[DatoTecnicoOut] = []
    caracteristicas: list[str] = []
    apu: Optional[ApuProyectoOut] = None
    vinculo_confianza: Optional[str] = None
    vinculo_confirmado: bool = False


class ModuloOut(BaseModel):
    id: int
    codigo: str
    nombre: str
    orden: int
    items: list[ItemOut]
    total: str
    items_con_precio: int


class AlertaOut(BaseModel):
    id: int
    item_numero: Optional[int]
    origen: str = "b1"
    nivel: str
    codigo: str
    mensaje: str


class ProyectoOut(BaseModel):
    id: int
    nombre: str
    entidad: Optional[str]
    archivo_b1: Optional[str]
    creado_en: datetime
    modulos: list[ModuloOut]
    alertas: list[AlertaOut]
    total: str
    total_items: int
    items_con_precio: int
    items_con_especificacion: int = 0
    items_con_apu: int = 0
    modo_recursos: str = "hibrido"
    modelo_costos: Optional[dict] = None
    recursos: list[RecursoProyectoOut] = []


class ProyectoResumen(BaseModel):
    id: int
    nombre: str
    archivo_b1: Optional[str]
    creado_en: datetime
    total_modulos: int
    total_items: int
    total: str


class PrecioIn(BaseModel):
    precio_unitario: Optional[str] = None


class BibliotecaOut(BaseModel):
    id: int
    nombre: str
    total_apus: int
    total_lineas: int


class ApuResumenOut(BaseModel):
    id: int
    nombre: str
    unidad: str
    codigo: Optional[str]
    lineas: int
    costo: Optional[str]


class AlertaFilaOut(BaseModel):
    nivel: str
    codigo: str
    mensaje: str
    fila: Optional[int]


class ImportacionBibliotecaOut(BaseModel):
    biblioteca: BibliotecaOut
    alertas: list[AlertaFilaOut]


class CandidatoOut(BaseModel):
    apu_id: int
    nombre: str
    unidad: str
    puntaje: float
    confianza: str
    motivo: str
    compatible_unidad: bool
    avisos: list[str]


class VincularIn(BaseModel):
    apu_id: Optional[int] = None  # None = solo con los recursos del pliego
    modo: str = "hibrido"
    recordar: bool = True
    confianza: Optional[str] = None  # la del candidato elegido, si la interfaz la conoce


class VincularAutoIn(BaseModel):
    modo: str = "hibrido"
    biblioteca_ids: Optional[list[int]] = None
    minimo_confianza: str = "alta"


class VincularAutoOut(BaseModel):
    vinculados: int
    solo_pliego: int
    por_revisar: int
    sin_candidato: int
    proyecto: ProyectoOut


class LineaEditIn(BaseModel):
    """Solo se cambia lo que viene en el cuerpo (un campo en null = dejarlo vacío/pendiente)."""

    cantidad: Optional[str] = None
    precio_unitario: Optional[str] = None
    unidad: Optional[str] = None
    origen_rendimiento: Optional[str] = None
    aplicar_precio_a_recurso: bool = True


class LineaNuevaIn(BaseModel):
    tipo: str
    descripcion: str
    unidad: str = ""
    cantidad: Optional[str] = None
    precio_unitario: Optional[str] = None


class PrecioRecursoIn(BaseModel):
    clave: str
    precio_unitario: Optional[str] = None


class CronogramaIn(BaseModel):
    fecha_inicio: date
    horas_jornada: float = Field(8, gt=0, le=24)
    personas_por_defecto: int = Field(2, ge=1, le=500)
    trabaja_sabados: bool = False
    feriados: list[date] = []
    secuencia: str = "modulos_en_serie"  # modulos_en_serie | todo_en_serie | todo_en_paralelo
    personas: dict[int, int] = {}  # id del ítem -> personas (anula el valor por defecto)
    hitos: dict[int, date] = {}  # id del módulo -> fecha límite


class ActividadCronoOut(BaseModel):
    item_id: int
    numero: int
    nombre: str
    modulo_id: int
    modulo_codigo: str
    horas_hombre: str
    personas: int
    duracion_dias: int
    inicio: date
    fin: date
    holgura_dias: int
    critica: bool
    espera_dias: int
    nota: str


class ModuloCronoOut(BaseModel):
    id: int
    codigo: str
    nombre: str
    inicio: Optional[date]
    fin: Optional[date]
    hito: Optional[date]
    atraso_dias: int


class SinProgramarOut(BaseModel):
    item_id: int
    numero: int
    nombre: str
    motivo: str


class CronogramaOut(BaseModel):
    fecha_inicio: date
    fecha_fin: Optional[date]
    dias_habiles: int
    actividades: list[ActividadCronoOut]
    modulos: list[ModuloCronoOut]
    sin_programar: list[SinProgramarOut]
    avisos: list[str]


class ExportarIn(BaseModel):
    cronograma: Optional[CronogramaIn] = None  # si viene, se agrega la hoja de cronograma
