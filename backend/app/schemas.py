from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional

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
    grupo_id: Optional[int] = None


class UnidadOut(BaseModel):
    id: int
    tipo: str
    simbolo: str
    nombre: Optional[str] = None
    predefinida: bool


class UnidadIn(BaseModel):
    tipo: str
    simbolo: str
    nombre: Optional[str] = None


class BibliotecaIn(BaseModel):
    nombre: str
    descripcion: Optional[str] = None


class BibliotecaCambios(BaseModel):
    nombre: Optional[str] = None
    descripcion: Optional[str] = None


class GrupoOut(BaseModel):
    id: int
    nombre: str
    padre_id: Optional[int] = None
    orden: int
    items: int = 0


class GrupoIn(BaseModel):
    nombre: str
    padre_id: Optional[int] = None


class RecursoBibOut(BaseModel):
    id: int
    tipo: str
    nombre: str
    unidad: str
    precio_referencia: Optional[str] = None
    usos: int = 0
    biblioteca_nombre: Optional[str] = None


class RecursoBibIn(BaseModel):
    tipo: str
    nombre: str
    unidad: str
    precio_referencia: Optional[Decimal] = None


class LineaBibOut(BaseModel):
    id: int
    recurso_id: Optional[int]
    tipo: str
    descripcion: str
    unidad: str
    cantidad: Optional[str]
    precio_unitario: Optional[str]
    importe: Optional[str]
    origen_rendimiento: str


class ApuBibDetalleOut(BaseModel):
    id: int
    biblioteca_id: int
    codigo: Optional[str]
    nombre: str
    unidad: str
    grupo_id: Optional[int]
    costo_directo: Optional[str]
    lineas: list[LineaBibOut]
    avisos: list[str] = []


class ApuBibIn(BaseModel):
    nombre: str
    unidad: str = ""
    grupo_id: Optional[int] = None
    codigo: Optional[str] = None


class LineaBibIn(BaseModel):
    recurso_id: Optional[int] = None
    tipo: Optional[str] = None
    nombre: Optional[str] = None
    unidad: Optional[str] = None
    cantidad: Optional[Decimal] = None
    precio_unitario: Optional[Decimal] = None
    origen_rendimiento: str = "manual"


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
    secuencia: str = "modulos_en_serie"  # modulos_en_serie | todo_en_serie | todo_en_paralelo | frentes_de_trabajo | logica_constructiva
    predecesoras: dict[int, list[int]] = {}  # «logica_constructiva»: id del ítem -> ids de sus predecesoras (reemplazan a las propuestas)
    personas: dict[int, int] = {}  # id del ítem -> personas (anula el valor por defecto)
    hitos: dict[int, date] = {}  # id del módulo -> fecha límite
    # Plazo máximo de la obra y objetivo de la optimización
    plazo_maximo: Optional[int] = Field(None, ge=1, le=5000)  # días máximos de ejecución; None = sin plazo
    tipo_plazo: Literal["calendario", "habiles"] = "calendario"  # en qué días se cuenta el plazo máximo
    objetivo: Literal["manual", "cumplir_plazo", "mas_rapido", "menor_costo"] = "manual"
    max_personas: int = Field(30, ge=1, le=500)  # tope de personas por actividad al acelerar (en «cumplir_plazo» se calcula solo)
    frentes: int = Field(1, ge=1, le=500)  # con secuencia «frentes_de_trabajo»: cuántos frentes en paralelo
    costo_indirecto_dia: float = Field(0, ge=0)  # Bs por día calendario de obra (para «menor costo»)
    costo_por_persona: float = Field(0, ge=0)  # Bs por persona adicional incorporada (para «menor costo»)


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
    predecesoras: list[int] = []  # ids de los ítems que fijan su inicio (los que «empujan»)
    predecesoras_definidas: list[int] = []  # «logica_constructiva»: ids de las predecesoras asignadas (propuestas o editadas)
    predecesora_manual: bool = False  # True si el usuario cambió las predecesoras de este ítem
    fase: str = ""  # etapa constructiva (solo «logica_constructiva»)
    frente: int = 0  # N° de frente de trabajo (0 = la secuencia no define frentes)


class ModuloCronoOut(BaseModel):
    id: int
    codigo: str
    nombre: str
    inicio: Optional[date]
    fin: Optional[date]
    hito: Optional[date]
    atraso_dias: int
    dias_habiles: int = 0


class SinProgramarOut(BaseModel):
    item_id: int
    numero: int
    nombre: str
    motivo: str


class FrenteCronoOut(BaseModel):
    frente: int
    personas: int  # cuadrilla del frente (la mayor que necesita alguna de sus actividades)
    actividades: int
    numeros: list[int]  # N° de los ítems que hace, en orden
    horas_hombre: str
    dias_habiles: int  # días que el frente está ocupado (suma de sus actividades)
    inicio: Optional[date]
    fin: Optional[date]


class EscenarioCronoOut(BaseModel):
    clave: str  # manual | cumplir_plazo | mas_rapido | menor_costo
    titulo: str
    frentes: int = 0
    personal_total: int = 0
    dias_calendario: int
    dias_habiles: int
    fecha_fin: Optional[date]
    pico_personas: int
    personas_agregadas: int
    costo_plazo: str
    costo_movilizacion: str
    costo_total: str
    cumple_plazo: Optional[bool]
    seleccionado: bool


class CronogramaOut(BaseModel):
    fecha_inicio: date
    fecha_fin: Optional[date]
    dias_habiles: int
    dias_calendario: int = 0
    plazo_maximo: Optional[int] = None
    tipo_plazo: str = "calendario"
    cumple_plazo: Optional[bool] = None
    objetivo: str = "manual"
    pico_personas: int = 0
    secuencia_usada: str = ""
    frentes: int = 0  # frentes de trabajo del plan elegido (0 = la secuencia no los define)
    automatico: bool = False  # True si el programa calculó solo las personas por actividad (objetivo «cumplir el plazo»)
    max_personas_usado: int = 0  # tope de personas por actividad con el que se calculó (el automático, o el indicado)
    personal_total: int = 0  # personal a contratar (suma de las cuadrillas de los frentes)
    frentes_detalle: list[FrenteCronoOut] = []
    escenarios: list[EscenarioCronoOut] = []
    actividades: list[ActividadCronoOut]
    modulos: list[ModuloCronoOut]
    sin_programar: list[SinProgramarOut]
    avisos: list[str]


class CronogramaPdfIn(CronogramaIn):
    empresa: Optional[str] = Field(None, max_length=200)  # contratista que se imprime en el encabezado


class ExportarIn(BaseModel):
    cronograma: Optional[CronogramaIn] = None  # si viene, se agrega la hoja de cronograma
    solo: Optional[Literal["b1", "b2"]] = None  # None = libro completo; 'b1' o 'b2' = solo ese formulario
