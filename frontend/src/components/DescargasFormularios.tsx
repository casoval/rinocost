import { useEffect, useRef, useState } from 'react';
import { abrirPdf, api, descargar, mensajeDe, nombreArchivo, type Formulario } from '../api';
import type { ProyectoOut } from '../types';
import './descargas.css';

type Formato = 'pdf' | 'xlsx';

const FORMULARIOS: { id: Formulario; titulo: string; detalle: string }[] = [
  { id: 'b1', titulo: 'Formulario B-1', detalle: 'Presupuesto por ítems y general de la obra' },
  { id: 'b2', titulo: 'Formulario B-2', detalle: 'Análisis de precios unitarios (una hoja por ítem)' },
];

/** Menú «Descargar»: cada formulario en PDF (listo para imprimir, formato del DBC) o en Excel, y el libro completo. */
export function DescargasFormularios({ proyecto }: { proyecto: Pick<ProyectoOut, 'id' | 'nombre'> }) {
  const [abierto, setAbierto] = useState(false);
  const [ocupado, setOcupado] = useState<string | null>(null);
  const [error, setError] = useState('');
  const raiz = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!abierto) return;
    const fuera = (e: MouseEvent) => { if (!raiz.current?.contains(e.target as Node)) setAbierto(false); };
    const tecla = (e: KeyboardEvent) => { if (e.key === 'Escape') setAbierto(false); };
    document.addEventListener('mousedown', fuera);
    document.addEventListener('keydown', tecla);
    return () => { document.removeEventListener('mousedown', fuera); document.removeEventListener('keydown', tecla); };
  }, [abierto]);

  async function bajar(clave: string, formulario: Formulario | null, formato: Formato) {
    if (formato === 'pdf' && formulario) {  // el PDF se abre en una pestaña nueva; desde ahí se imprime o se guarda
      setError('');
      abrirPdf(api.rutaPdf(proyecto.id, formulario));
      setAbierto(false);
      return;
    }
    try {
      setError('');
      setOcupado(clave);
      const base = formulario ? `formulario-${formulario.toUpperCase()}-${proyecto.nombre}` : `presupuesto-${proyecto.nombre}`;
      const blob = await api.exportar(proyecto.id, null, formulario);
      descargar(blob, nombreArchivo(base, formato));
    } catch (e) {
      setError(mensajeDe(e));
    } finally {
      setOcupado(null);
    }
  }

  const boton = (clave: string, etiqueta: string, formulario: Formulario | null, formato: Formato) => (
    <button type="button" className="descarga-opcion" disabled={ocupado !== null} onClick={() => void bajar(clave, formulario, formato)}>
      {ocupado === clave ? 'Preparando…' : etiqueta}
    </button>
  );

  return (
    <div className="descargas" ref={raiz}>
      <button type="button" className="boton primario" aria-haspopup="true" aria-expanded={abierto} onClick={() => setAbierto(!abierto)}>
        Descargar ▾
      </button>
      {abierto && (
        <div className="descargas-menu" role="menu">
          {FORMULARIOS.map((f) => (
            <div className="descarga-grupo" key={f.id}>
              <strong>{f.titulo}</strong>
              <span className="tenue">{f.detalle}</span>
              <div className="descarga-fila">
                {boton(`${f.id}-pdf`, 'Abrir PDF', f.id, 'pdf')}
                {boton(`${f.id}-xlsx`, 'Excel', f.id, 'xlsx')}
              </div>
            </div>
          ))}
          <div className="descarga-grupo">
            <strong>Libro completo</strong>
            <span className="tenue">B-1, resumen, análisis de precios y lista de recursos</span>
            <div className="descarga-fila">{boton('todo-xlsx', 'Excel completo', null, 'xlsx')}</div>
          </div>
          {error && <p className="mensaje error" role="alert">{error}</p>}
        </div>
      )}
    </div>
  );
}
