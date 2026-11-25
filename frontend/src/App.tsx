import { useCallback, useEffect, useRef, useState } from 'react';
import { URL_PLANTILLA, api, mensajeDe } from './api';
import { ProyectoVista } from './components/ProyectoVista';
import type { BibliotecaOut, ProyectoOut, ProyectoResumen } from './types';

const formato = new Intl.NumberFormat('es-BO', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export default function App() {
  const [lista, setLista] = useState<ProyectoResumen[]>([]);
  const [bibliotecas, setBibliotecas] = useState<BibliotecaOut[]>([]);
  const [actual, setActual] = useState<ProyectoOut | null>(null);
  const [mensaje, setMensaje] = useState<{ texto: string; error: boolean }>({ texto: '', error: false });
  const entrada = useRef<HTMLInputElement>(null);
  const entradaBib = useRef<HTMLInputElement>(null);

  const recargar = useCallback(async () => {
    const [proyectos, bibs] = await Promise.all([api.listar(), api.bibliotecas()]);
    setLista(proyectos);
    setBibliotecas(bibs);
  }, []);

  useEffect(() => {
    recargar().catch((e) => setMensaje({ texto: mensajeDe(e), error: true }));
  }, [recargar]);

  async function abrir(id: number) {
    try {
      setMensaje({ texto: '', error: false });
      setActual(await api.obtener(id));
    } catch (e) {
      setMensaje({ texto: mensajeDe(e), error: true });
    }
  }

  async function importar(archivo: File) {
    try {
      setMensaje({ texto: `Leyendo ${archivo.name}…`, error: false });
      const nuevo = await api.importarB1(archivo);
      setActual(nuevo);
      setMensaje({ texto: '', error: false });
      await recargar();
    } catch (e) {
      setMensaje({ texto: mensajeDe(e), error: true });
    }
  }

  async function importarBiblioteca(archivo: File) {
    try {
      setMensaje({ texto: `Leyendo ${archivo.name}…`, error: false });
      const r = await api.importarBiblioteca(archivo);
      await recargar();
      const problemas = r.alertas.filter((a) => a.nivel !== 'info');
      const detalle = problemas.slice(0, 3).map((a) => (a.fila ? `fila ${a.fila}: ${a.mensaje}` : a.mensaje)).join(' · ');
      setMensaje({
        texto:
          `Biblioteca «${r.biblioteca.nombre}»: ${r.biblioteca.total_apus} APU y ${r.biblioteca.total_lineas} líneas.` +
          (problemas.length ? ` ${problemas.length} avisos: ${detalle}${problemas.length > 3 ? '…' : ''}` : ''),
        error: false,
      });
    } catch (e) {
      setMensaje({ texto: mensajeDe(e), error: true });
    }
  }

  async function borrarBiblioteca(b: BibliotecaOut) {
    if (!window.confirm(`¿Eliminar la biblioteca “${b.nombre}” y sus ${b.total_apus} APU? Los APU ya copiados a proyectos se conservan.`)) return;
    try {
      await api.borrarBiblioteca(b.id);
      await recargar();
    } catch (e) {
      setMensaje({ texto: mensajeDe(e), error: true });
    }
  }

  async function borrar() {
    if (!actual || !window.confirm(`¿Eliminar el proyecto “${actual.nombre}”? Esta acción no se puede deshacer.`)) return;
    try {
      await api.borrar(actual.id);
      setActual(null);
      await recargar();
    } catch (e) {
      setMensaje({ texto: mensajeDe(e), error: true });
    }
  }

  function proyectoActualizado(p: ProyectoOut) {
    setActual(p);
    recargar().catch(() => undefined);
  }

  return (
    <div className="app">
      <aside className="lateral">
        <h1>Presupuestos</h1>
        <button type="button" className="boton primario" onClick={() => entrada.current?.click()}>
          Importar B-1 (PDF)
        </button>
        <input
          ref={entrada}
          type="file"
          accept="application/pdf,.pdf"
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void importar(f);
            e.target.value = '';
          }}
        />
        <nav aria-label="Proyectos">
          {lista.length === 0 && <p className="tenue">Aún no hay proyectos. Importa el B-1 de una convocatoria.</p>}
          <ul>
            {lista.map((p) => (
              <li key={p.id}>
                <button
                  type="button"
                  className={actual?.id === p.id ? 'proyecto activo' : 'proyecto'}
                  onClick={() => void abrir(p.id)}
                >
                  <strong>{p.nombre}</strong>
                  <span className="tenue">{p.total_items} ítems · Bs {formato.format(Number(p.total))}</span>
                </button>
              </li>
            ))}
          </ul>
        </nav>

        <section className="bloque-bibliotecas" aria-label="Bibliotecas">
          <h3>Mis bibliotecas</h3>
          <button type="button" className="boton" onClick={() => entradaBib.current?.click()}>
            Importar biblioteca (Excel)
          </button>
          <input
            ref={entradaBib}
            type="file"
            accept=".xlsx,.xlsm"
            hidden
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void importarBiblioteca(f);
              e.target.value = '';
            }}
          />
          <a className="enlace-simple" href={URL_PLANTILLA}>Descargar plantilla de Excel</a>
          {bibliotecas.length === 0 ? (
            <p className="tenue">Carga una biblioteca para vincular tus APU a los ítems.</p>
          ) : (
            <ul>
              {bibliotecas.map((b) => (
                <li key={b.id} className="fila-biblioteca">
                  <span>
                    <strong>{b.nombre}</strong>
                    <span className="tenue"> {b.total_apus} APU</span>
                  </span>
                  <button type="button" className="quitar" aria-label={`Eliminar la biblioteca ${b.nombre}`} onClick={() => void borrarBiblioteca(b)}>
                    ×
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </aside>

      <main className="principal">
        {mensaje.texto && (
          <p className={mensaje.error ? 'mensaje error' : 'mensaje'} role={mensaje.error ? 'alert' : 'status'}>
            {mensaje.texto}
          </p>
        )}
        {actual ? (
          <ProyectoVista
            key={actual.id}
            proyecto={actual}
            bibliotecas={bibliotecas}
            onActualizar={proyectoActualizado}
            onBorrar={() => void borrar()}
          />
        ) : (
          <div className="vacio">
            <h2>Importa una convocatoria</h2>
            <p className="tenue">
              Sube el PDF del Formulario B-1. Los módulos, ítems, unidades y cantidades se leen tal como vienen y
              quedan guardados en la base de datos. Después importa las especificaciones técnicas y vincula tus APU.
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
