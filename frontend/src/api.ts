import type {
  BibliotecaOut, CandidatoOut, Confianza, CronogramaIn, CronogramaOut, ImportacionBibliotecaOut, ModoRecursos, ProyectoOut, ProyectoResumen,
  VincularAutoOut,
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

export const api = {
  listar: () => pedir<ProyectoResumen[]>('/proyectos'),
  obtener: (id: number) => pedir<ProyectoOut>(`/proyectos/${id}`),
  importarB1: (archivo: File) => {
    const form = new FormData();
    form.append('archivo', archivo);
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
  exportar: async (proyectoId: number, cronograma: CronogramaIn | null): Promise<Blob> => {
    let r: Response;
    try {
      r = await fetch(`${BASE}/proyectos/${proyectoId}/exportar`, {
        method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ cronograma }),
      });
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
  },
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
