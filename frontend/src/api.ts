import type {
  BibliotecaOut, CandidatoOut, Confianza, CronogramaIn, CronogramaOut, ImportacionBibliotecaOut, ModoRecursos, ProyectoOut, ProyectoResumen,
  ModeloCostos, VincularAutoOut, UnidadOut, GrupoOut, ApuResumenOut, RecursoBibOut, ApuBibDetalleOut, LineaNueva, TipoRecurso,
} from './types';

const BASE = '/api';

async function pedir<T>(ruta: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(BASE + ruta, init);
  } catch {
    throw new Error('No se pudo conectar con la API. Verifica que uvicorn esté en ejecución.');
  }
  if (!r.ok) {
    let detalle = `La API respondió con el error ${r.status}.`;
    try {
      const j = await r.json();
      if (typeof j.detail === 'string') detalle = j.detail;
    } catch {
      /* respuesta sin JSON */
    }
    throw new Error(detalle);
  }
  if (r.status === 204) return undefined as T;
  return (await r.json()) as T;
}

export const URL_PLANTILLA = `${BASE}/bibliotecas/plantilla.xlsx`;

const JSON_HEADERS = { 'Content-Type': 'application/json' };

const J = (metodo: string, cuerpo?: unknown): RequestInit => ({ method: metodo, headers: JSON_HEADERS, body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo) });

export type Formulario = 'b1' | 'b2';

/** Pide un archivo a la API y devuelve su contenido; traduce los errores a mensajes claros. */
async function descargaBlob(ruta: string, opciones: RequestInit): Promise<Blob> {
  let r: Response;
  try {
    r = await fetch(`${BASE}${ruta}`, opciones);
  } catch {
    throw new Error('No se pudo conectar con la API. Verifica que uvicorn esté en ejecución.');
  }
  if (!r.ok) {
    let detalle = `La API respondió con el error ${r.status}.`;
    try {
      const j = await r.json();
      if (typeof j.detail === 'string') detalle = j.detail;
    } catch {
      /* respuesta sin JSON */
    }
    throw new Error(detalle);
  }
  return r.blob();
}

export const api = {
  // --- editor de bibliotecas
  edUnidades: () => pedir<UnidadOut[]>('/unidades'),
  edCrearBiblioteca: (nombre: string) => pedir<BibliotecaOut>('/bibliotecas', J('POST', { nombre })),
  edRenombrarBiblioteca: (id: number, nombre: string) => pedir<BibliotecaOut>(`/bibliotecas/${id}`, J('PATCH', { nombre })),
  edGrupos: (bid: number) => pedir<GrupoOut[]>(`/bibliotecas/${bid}/grupos`),
  edCrearGrupo: (bid: number, nombre: string, padre_id: number | null) => pedir<GrupoOut>(`/bibliotecas/${bid}/grupos`, J('POST', { nombre, padre_id })),
  edCambiarGrupo: (gid: number, cambios: { nombre?: string }) => pedir<GrupoOut>(`/bibliotecas/grupos/${gid}`, J('PATCH', cambios)),
  edBorrarGrupo: (gid: number) => pedir<void>(`/bibliotecas/grupos/${gid}`, { method: 'DELETE' }),
  edApusDe: (bid: number) => pedir<ApuResumenOut[]>(`/bibliotecas/${bid}/apus`),
  edRecursosDe: (bid: number, tipo?: TipoRecurso) => pedir<RecursoBibOut[]>(`/bibliotecas/${bid}/recursos${tipo ? `?tipo=${tipo}` : ''}`),
  edCrearRecurso: (bid: number, r: { tipo: TipoRecurso; nombre: string; unidad: string; precio_referencia: string | null }) =>
    pedir<RecursoBibOut>(`/bibliotecas/${bid}/recursos`, J('POST', r)),
  edCambiarRecurso: (rid: number, cambios: { nombre?: string; unidad?: string; precio_referencia?: string | null }) =>
    pedir<RecursoBibOut>(`/bibliotecas/recursos/${rid}`, J('PATCH', cambios)),
  edBorrarRecurso: (rid: number, forzar: boolean) => pedir<void>(`/bibliotecas/recursos/${rid}?forzar=${forzar}`, { method: 'DELETE' }),
  edRecursosDeOtras: (bid: number, q: string, tipo: TipoRecurso) => pedir<RecursoBibOut[]>(`/bibliotecas/${bid}/recursos-de-otras?q=${encodeURIComponent(q)}&tipo=${tipo}`),
  edCopiarRecurso: (bid: number, recurso_id: number) => pedir<RecursoBibOut>(`/bibliotecas/${bid}/recursos/copiar`, J('POST', { recurso_id })),
  edCrearItem: (bid: number, d: { nombre: string; unidad: string; grupo_id: number | null }) => pedir<ApuBibDetalleOut>(`/bibliotecas/${bid}/apus`, J('POST', d)),
  edDetalleItem: (id: number) => pedir<ApuBibDetalleOut>(`/bibliotecas/apus/${id}`),
  edCambiarItem: (id: number, c: { nombre?: string; unidad?: string; grupo_id?: number | null; codigo?: string }) => pedir<ApuBibDetalleOut>(`/bibliotecas/apus/${id}`, J('PATCH', c)),
  edBorrarItem: (id: number) => pedir<void>(`/bibliotecas/apus/${id}`, { method: 'DELETE' }),
  edDuplicarItem: (id: number) => pedir<ApuBibDetalleOut>(`/bibliotecas/apus/${id}/duplicar`, J('POST')),
  edAgregarLinea: (id: number, l: LineaNueva) => pedir<ApuBibDetalleOut>(`/bibliotecas/apus/${id}/lineas`, J('POST', l)),
  edCambiarLinea: (lid: number, c: { cantidad?: string | null; precio_unitario?: string | null; origen_rendimiento?: string }) => pedir<ApuBibDetalleOut>(`/bibliotecas/lineas/${lid}`, J('PATCH', c)),
  edBorrarLinea: (lid: number) => pedir<ApuBibDetalleOut>(`/bibliotecas/lineas/${lid}`, { method: 'DELETE' }),
  fijarModeloCostos: (proyectoId: number, modelo: ModeloCostos) =>
    pedir<ProyectoOut>(`/proyectos/${proyectoId}/modelo-costos`, { method: 'PUT', headers: JSON_HEADERS, body: JSON.stringify(modelo) }),
  crearPerfil: (nombre: string, modelo: ModeloCostos) =>
    pedir<ModeloCostos>('/modelos-costos/perfiles', { method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ nombre, modelo }) }),
  actualizarPerfil: (id: number, nombre: string, modelo: ModeloCostos) =>
    pedir<ModeloCostos>(`/modelos-costos/perfiles/${id}`, { method: 'PUT', headers: JSON_HEADERS, body: JSON.stringify({ nombre, modelo }) }),
  borrarPerfil: (id: number) => pedir<void>(`/modelos-costos/perfiles/${id}`, { method: 'DELETE' }),
  modelosCosto: () => pedir<ModeloCostos[]>('/modelos-costos'),
  listar: () => pedir<ProyectoResumen[]>('/proyectos'),
  obtener: (id: number) => pedir<ProyectoOut>(`/proyectos/${id}`),
  importarB1: (archivo: File, modelo?: string) => {
    const form = new FormData();
    form.append('archivo', archivo);
    if (modelo) form.append('modelo', modelo);
    return pedir<ProyectoOut>('/proyectos/importar-b1', { method: 'POST', body: form });
  },
  importarEspecificaciones: (proyectoId: number, archivo: File) => {
    const form = new FormData();
    form.append('archivo', archivo);
    return pedir<ProyectoOut>(`/proyectos/${proyectoId}/especificaciones`, { method: 'POST', body: form });
  },
  borrar: (id: number) => pedir<void>(`/proyectos/${id}`, { method: 'DELETE' }),
  editarLinea: (
    lineaId: number,
    cambios: {
      cantidad?: string | null;
      precio_unitario?: string | null;
      unidad?: string;
      origen_rendimiento?: string;
      aplicar_precio_a_recurso?: boolean;
    },
  ) =>
    pedir<ProyectoOut>(`/proyectos/apu-lineas/${lineaId}`, {
      method: 'PATCH', headers: JSON_HEADERS, body: JSON.stringify(cambios),
    }),
  eliminarLinea: (lineaId: number) => pedir<ProyectoOut>(`/proyectos/apu-lineas/${lineaId}`, { method: 'DELETE' }),
  agregarLinea: (
    itemId: number,
    cuerpo: { tipo: string; descripcion: string; unidad: string; cantidad: string | null; precio_unitario: string | null },
  ) =>
    pedir<ProyectoOut>(`/proyectos/items/${itemId}/lineas`, {
      method: 'POST', headers: JSON_HEADERS, body: JSON.stringify(cuerpo),
    }),
  fijarPrecioRecurso: (proyectoId: number, clave: string, precio: string | null) =>
    pedir<ProyectoOut>(`/proyectos/${proyectoId}/precio-recurso`, {
      method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ clave, precio_unitario: precio }),
    }),
  cronograma: (proyectoId: number, cuerpo: CronogramaIn) =>
    pedir<CronogramaOut>(`/proyectos/${proyectoId}/cronograma`, {
      method: 'POST', headers: JSON_HEADERS, body: JSON.stringify(cuerpo),
    }),
  exportar: (proyectoId: number, cronograma: CronogramaIn | null, solo: Formulario | null = null): Promise<Blob> =>
    descargaBlob(`/proyectos/${proyectoId}/exportar`, {
      method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ cronograma, solo }),
    }),
  /** PDF listo para imprimir del Formulario B-1 (presupuesto) o B-2 (análisis de precios), formato del DBC. */
  exportarPdf: (proyectoId: number, formulario: Formulario): Promise<Blob> =>
    descargaBlob(`/proyectos/${proyectoId}/pdf/${formulario}`, { method: 'GET' }),
  bibliotecas: () => pedir<BibliotecaOut[]>('/bibliotecas'),
  importarBiblioteca: (archivo: File) => {
    const form = new FormData();
    form.append('archivo', archivo);
    return pedir<ImportacionBibliotecaOut>('/bibliotecas/importar-excel', { method: 'POST', body: form });
  },
  borrarBiblioteca: (id: number) => pedir<void>(`/bibliotecas/${id}`, { method: 'DELETE' }),
  candidatos: (itemId: number, bibliotecaIds: number[]) => {
    const q = new URLSearchParams();
    bibliotecaIds.forEach((id) => q.append('biblioteca_ids', String(id)));
    const texto = q.toString();
    return pedir<CandidatoOut[]>(`/proyectos/items/${itemId}/candidatos${texto ? `?${texto}` : ''}`);
  },
  vincular: (
    itemId: number,
    cuerpo: { apu_id: number | null; modo: ModoRecursos; recordar?: boolean; confianza?: Confianza | null },
  ) =>
    pedir<ProyectoOut>(`/proyectos/items/${itemId}/vincular`, {
      method: 'POST', headers: JSON_HEADERS, body: JSON.stringify(cuerpo),
    }),
  vincularAuto: (proyectoId: number, cuerpo: { modo: ModoRecursos; biblioteca_ids: number[] | null }) =>
    pedir<VincularAutoOut>(`/proyectos/${proyectoId}/vincular-auto`, {
      method: 'POST', headers: JSON_HEADERS, body: JSON.stringify(cuerpo),
    }),
  fijarPrecio: (itemId: number, precio: string | null) =>
    pedir<ProyectoOut>(`/proyectos/items/${itemId}/precio`, {
      method: 'PATCH',
      headers: JSON_HEADERS,
      body: JSON.stringify({ precio_unitario: precio }),
    }),
};

export const mensajeDe = (e: unknown): string => (e instanceof Error ? e.message : 'Ocurrió un error inesperado.');

/** Descarga un archivo generado en el navegador (por ejemplo el Excel exportado). */
export function descargar(blob: Blob, nombre: string): void {
  const url = URL.createObjectURL(blob);
  const enlace = document.createElement('a');
  enlace.href = url;
  enlace.download = nombre;
  enlace.click();
  URL.revokeObjectURL(url);
}

export const nombreArchivo = (texto: string, extension: string): string =>
  `${texto.replace(/[^\w-]+/g, '_').replace(/^_+|_+$/g, '') || 'proyecto'}.${extension}`;
