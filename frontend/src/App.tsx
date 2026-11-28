import { useCallback, useEffect, useRef, useState } from 'react';
import { api, mensajeDe } from './api';
import { Bibliotecas } from './components/Bibliotecas';
import { EditorBiblioteca } from './components/EditorBiblioteca';
import { Configuracion } from './components/Configuracion';
import { MenuLateral, type Vista } from './components/MenuLateral';
import { Modelos } from './components/Modelos';
import { ProyectoVista } from './components/ProyectoVista';
import type { BibliotecaOut, ModeloCostos, ProyectoOut, ProyectoResumen } from './types';

const formato = new Intl.NumberFormat('es-BO', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export default function App() {
  const [lista, setLista] = useState<ProyectoResumen[]>([]);
  const [bibliotecas, setBibliotecas] = useState<BibliotecaOut[]>([]);
  const [actual, setActual] = useState<ProyectoOut | null>(null);
  const [mensaje, setMensaje] = useState<{ texto: string; error: boolean }>({ texto: '', error: false });
  const entrada = useRef<HTMLInputElement>(null);
  const [bibAbierta, setBibAbierta] = useState<BibliotecaOut | null>(null);
  const [modelos, setModelos] = useState<ModeloCostos[]>([]);
  const [modeloNuevo, setModeloNuevo] = useState('predefinido:bolivia_b2');
  const [vista, setVista] = useState<Vista>('proyectos');
  const [menuAbierto, setMenuAbierto] = useState(false);

  const recargar = useCallback(async () => {
    const [proyectos, bibs] = await Promise.all([api.listar(), api.bibliotecas()]);
    setLista(proyectos);
    setBibliotecas(bibs);
  }, []);

  const recargarModelos = useCallback(async () => {
    setModelos(await api.modelosCosto());
  }, []);

  useEffect(() => {
    recargarModelos().catch((e) => setMensaje({ texto: mensajeDe(e), error: true }));
    recargar().catch((e) => setMensaje({ texto: mensajeDe(e), error: true }));
  }, [recargar]);

  function cambiarVista(v: Vista) {
    setVista(v);
    setMenuAbierto(false);
  }

  async function abrir(id: number) {
    try {
      setVista('proyectos');
      setMenuAbierto(false);
      setMensaje({ texto: '', error: false });
      setActual(await api.obtener(id));
    } catch (e) {
      setMensaje({ texto: mensajeDe(e), error: true });
    }
  }

  async function importar(archivo: File) {
    try {
      setMensaje({ texto: `Leyendo ${archivo.name}…`, error: false });
      const nuevo = await api.importarB1(archivo, modeloNuevo);
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
      <MenuLateral vista={vista} onCambiar={cambiarVista} abierto={menuAbierto} onAlternar={() => setMenuAbierto((a) => !a)}>
        {vista === 'proyectos' && (
          <>
            <label className="campo-linea">
              Cálculo del nuevo proyecto
              <select value={modeloNuevo} onChange={(e) => setModeloNuevo(e.target.value)}>
                {modelos.map((m) => (
                  <option key={m.clave} value={m.clave}>{m.propio ? `★ ${m.nombre}` : m.nombre}</option>
                ))}
              </select>
            </label>
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
            {lista.length === 0 && <p className="tenue">Aún no hay proyectos.</p>}
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
          </>
        )}
      </MenuLateral>

      <main className="principal">
        {mensaje.texto && (
          <p className={mensaje.error ? 'mensaje error' : 'mensaje'} role={mensaje.error ? 'alert' : 'status'}>
            {mensaje.texto}
          </p>
        )}
        {vista === 'bibliotecas' && !bibAbierta && (
          <Bibliotecas bibliotecas={bibliotecas} onImportar={(f) => void importarBiblioteca(f)} onBorrar={(b) => void borrarBiblioteca(b)}
            onAbrir={setBibAbierta}
            onCrear={(nombre) => { api.edCrearBiblioteca(nombre).then(async (b) => { await recargar(); setBibAbierta(b); }).catch((e) => setMensaje({ texto: mensajeDe(e), error: true })); }} />
        )}
        {vista === 'bibliotecas' && bibAbierta && (
          <EditorBiblioteca key={bibAbierta.id} biblioteca={bibAbierta} onVolver={() => setBibAbierta(null)} onCambio={() => void recargar()} />
        )}
        {vista === 'modelos' && <Modelos modelos={modelos} onCambio={() => void recargarModelos()} />}
        {vista === 'configuracion' && <Configuracion />}
        {vista === 'proyectos' &&
          (actual ? (
            <ProyectoVista
              key={actual.id}
              proyecto={actual}
              modelos={modelos}
              onModelosCambiaron={() => void recargarModelos()}
              bibliotecas={bibliotecas}
              onActualizar={proyectoActualizado}
              onBorrar={() => void borrar()}
            />
          ) : (
            <div className="vacio">
              <h2>Importa una convocatoria</h2>
              <p className="tenue">
                Sube el PDF del Formulario B-1 desde el menú. Los módulos, ítems, unidades y cantidades se leen tal como
                vienen. Después importa las especificaciones técnicas y vincula tus APU.
              </p>
            </div>
          ))}
      </main>
    </div>
  );
}
