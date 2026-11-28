export type ModoRecursos = 'pliego' | 'biblioteca' | 'hibrido';
export type Confianza = 'alta' | 'media' | 'baja';

export interface LineaApuOut {
  id: number;
  tipo: 'material' | 'mano_obra' | 'equipo';
  descripcion: string;
  unidad: string;
  cantidad: string | null;
  precio_unitario: string | null;
  origen_dato: 'pliego' | 'biblioteca' | 'ambos' | 'manual';
  origen_rendimiento: string;
  requerido_por_pliego: boolean;
  estado: 'completo' | 'pendiente';
  fuente: string | null;
}

export interface ApuProyectoOut {
  id: number;
  origen_apu_id: number | null;
  estado: 'completo' | 'incompleto' | 'vacio';
  pendientes: number;
  costo: string | null; // costo directo
  precio: string | null; // precio unitario según el modelo de cálculo
  desglose: { codigo: string; etiqueta: string; porcentaje: string | null; valor: string }[] | null;
  lineas: LineaApuOut[];
}

export interface RecursoProyectoOut {
  clave: string;
  tipo: 'material' | 'mano_obra' | 'equipo';
  nombre: string;
  unidad: string;
  usos: number;
  precio: string | null;
  estado: 'completo' | 'sin_precio' | 'varios';
}

export interface RequisitoOut {
  id: number;
  tipo: 'material' | 'mano_obra' | 'equipo';
  nombre: string;
  unidad: string | null;
  detalle: string | null;
  pagina: number;
  fragmento: string;
  estado: string;
}

export interface DatoTecnicoOut {
  tipo: string;
  valor: string;
  fragmento: string;
  pagina: number;
}

export interface ItemOut {
  id: number;
  numero: number;
  descripcion: string;
  unidad: string;
  unidad_normalizada: string;
  cantidad: string | null;
  cantidad_texto: string;
  pagina: number;
  bloqueado: boolean;
  modo_precio: 'pendiente' | 'directo' | 'apu' | 'global';
  precio_unitario: string | null;
  total: string | null;
  tiene_especificacion: boolean;
  sin_materiales: boolean;
  requisitos: RequisitoOut[];
  datos_tecnicos: DatoTecnicoOut[];
  caracteristicas: string[];
  apu: ApuProyectoOut | null;
  vinculo_confianza: Confianza | null;
  vinculo_confirmado: boolean;
}

export interface ModuloOut {
  id: number;
  codigo: string;
  nombre: string;
  orden: number;
  items: ItemOut[];
  total: string;
  items_con_precio: number;
}

export interface AlertaOut {
  id: number;
  item_numero: number | null;
  origen: 'b1' | 'especificaciones' | 'apu';
  nivel: 'error' | 'advertencia' | 'info';
  codigo: string;
  mensaje: string;
}

export interface ProyectoOut {
  id: number;
  nombre: string;
  entidad: string | null;
  archivo_b1: string | null;
  creado_en: string;
  modulos: ModuloOut[];
  alertas: AlertaOut[];
  total: string;
  total_items: number;
  items_con_precio: number;
  items_con_especificacion: number;
  items_con_apu: number;
  modo_recursos: ModoRecursos;
  modelo_costos: ModeloCostos | null;
  recursos: RecursoProyectoOut[];
}

export interface ProyectoResumen {
  id: number;
  nombre: string;
  archivo_b1: string | null;
  creado_en: string;
  total_modulos: number;
  total_items: number;
  total: string;
}

export interface BibliotecaOut {
  id: number;
  nombre: string;
  total_apus: number;
  total_lineas: number;
}

export interface AlertaFilaOut {
  nivel: 'error' | 'advertencia' | 'info';
  codigo: string;
  mensaje: string;
  fila: number | null;
}

export interface ImportacionBibliotecaOut {
  biblioteca: BibliotecaOut;
  alertas: AlertaFilaOut[];
}

export interface CandidatoOut {
  apu_id: number;
  nombre: string;
  unidad: string;
  puntaje: number;
  confianza: Confianza;
  motivo: 'equivalencia' | 'texto';
  compatible_unidad: boolean;
  avisos: string[];
}

export interface VincularAutoOut {
  vinculados: number;
  solo_pliego: number;
  por_revisar: number;
  sin_candidato: number;
  proyecto: ProyectoOut;
}

export type Secuencia = 'modulos_en_serie' | 'todo_en_serie' | 'todo_en_paralelo';

export interface CronogramaIn {
  fecha_inicio: string;
  horas_jornada: number;
  personas_por_defecto: number;
  trabaja_sabados: boolean;
  feriados: string[];
  secuencia: Secuencia;
  personas: Record<number, number>;
  hitos: Record<number, string>;
}

export interface ActividadCronoOut {
  item_id: number;
  numero: number;
  nombre: string;
  modulo_id: number;
  modulo_codigo: string;
  horas_hombre: string;
  personas: number;
  duracion_dias: number;
  inicio: string;
  fin: string;
  holgura_dias: number;
  critica: boolean;
  espera_dias: number;
  nota: string;
}

export interface ModuloCronoOut {
  id: number;
  codigo: string;
  nombre: string;
  inicio: string | null;
  fin: string | null;
  hito: string | null;
  atraso_dias: number;
}

export interface SinProgramarOut {
  item_id: number;
  numero: number;
  nombre: string;
  motivo: string;
}

export interface CronogramaOut {
  fecha_inicio: string;
  fecha_fin: string | null;
  dias_habiles: number;
  actividades: ActividadCronoOut[];
  modulos: ModuloCronoOut[];
  sin_programar: SinProgramarOut[];
  avisos: string[];
}

export interface PasoModelo { codigo: string; etiqueta: string; porcentaje: string; base: string[]; activo: boolean; minimo?: string; maximo?: string; ayuda?: string }
export interface SeccionModelo { codigo: string; titulo: string; tipo_recurso: string | null; activo: boolean; pasos: PasoModelo[] }
export interface ModeloCostos { clave?: string; propio?: boolean; id?: number | null; codigo: string; nombre: string; descripcion: string; nota: string; decimales: number; secciones: SeccionModelo[] }

export type TipoRecurso = 'material' | 'mano_obra' | 'equipo';
export interface UnidadOut { id: number; tipo: string; simbolo: string; nombre: string | null; predefinida: boolean }
export interface GrupoOut { id: number; nombre: string; padre_id: number | null; orden: number; items: number }
export interface ApuResumenOut { id: number; nombre: string; unidad: string; codigo: string | null; lineas: number; costo: string | null; grupo_id: number | null }
export interface RecursoBibOut { id: number; tipo: TipoRecurso; nombre: string; unidad: string; precio_referencia: string | null; usos: number; biblioteca_nombre: string | null }
export interface LineaBibOut { id: number; recurso_id: number | null; tipo: TipoRecurso; descripcion: string; unidad: string; cantidad: string | null; precio_unitario: string | null; importe: string | null; origen_rendimiento: string }
export interface ApuBibDetalleOut { id: number; biblioteca_id: number; codigo: string | null; nombre: string; unidad: string; grupo_id: number | null; costo_directo: string | null; lineas: LineaBibOut[]; avisos: string[] }
export interface LineaNueva { recurso_id?: number; tipo?: TipoRecurso; nombre?: string; unidad?: string; cantidad?: string | null; precio_unitario?: string | null; origen_rendimiento?: string }

export interface HojaB2Linea { n: number; id: number | null; descripcion: string; unidad: string; cantidad: string | null; precio_unitario: string | null; costo: string | null }
export interface HojaB2Paso { codigo: string; etiqueta: string; porcentaje: string; bases: string[]; base_valor: string | null; importe: string | null }
export interface HojaB2Seccion {
  numero: number; codigo: string; titulo: string; tipo_recurso: TipoRecurso | null; etiqueta_total: string;
  lineas: HojaB2Linea[]; subtotal_directo: string | null; pasos: HojaB2Paso[]; total: string | null;
}
export interface HojaB2Out {
  proyecto: string;
  item: { id: number; numero: number; descripcion: string; unidad: string; cantidad: string | null; cantidad_texto: string };
  modelo: { codigo: string; nombre: string; decimales: number };
  tiene_apu: boolean; completo: boolean; pendientes: number;
  secciones: HojaB2Seccion[];
  subtotal_por_tipo: Record<TipoRecurso, string>;
  total_sin_redondeo: string | null; precio_adoptado: string | null;
  directos: Record<TipoRecurso, string> | null;
}
