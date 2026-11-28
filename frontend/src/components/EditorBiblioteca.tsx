import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { api, mensajeDe } from '../api';
import type { ApuBibDetalleOut, ApuResumenOut, BibliotecaOut, GrupoOut, LineaBibOut, RecursoBibOut, TipoRecurso, UnidadOut } from '../types';

const TIPOS: { id: TipoRecurso; plural: string; singular: string }[] = [
  { id: 'material', plural: 'Materiales', singular: 'material' },
  { id: 'mano_obra', plural: 'Mano de obra', singular: 'mano de obra' },
  { id: 'equipo', plural: 'Equipo', singular: 'equipo' },
];
const ORIGENES = ['manual', 'medido', 'calculado', 'similar', 'comunitario', 'referencial', 'biblioteca'];
const bs = (t: string | null) => (t == null ? '—' : Number(t).toLocaleString('es-BO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }));

/** Campo de texto/número que guarda al salir (blur) solo si cambió. */
function Campo({ valor, onGuardar, etiqueta, num, ancho, lista, placeholder }: {
  valor: string; onGuardar: (v: string) => void; etiqueta: string; num?: boolean; ancho?: string; lista?: string; placeholder?: string;
}) {
  const [v, setV] = useState(valor);
  useEffect(() => setV(valor), [valor]);
  return (
    <input aria-label={etiqueta} value={v} list={lista} placeholder={placeholder} inputMode={num ? 'decimal' : undefined}
      className={num ? 'campo-num' : 'campo'} style={ancho ? { width: ancho } : undefined}
      onChange={(e) => setV(num ? e.target.value.replace(',', '.') : e.target.value)}
      onBlur={() => { if (v.trim() !== valor.trim()) onGuardar(v.trim()); }}
      onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }} />
  );
}

/** Ventana por encima de la lista (elemento <dialog> nativo: Esc la cierra y el foco queda dentro). */
function Ventana({ titulo, posicion, onCerrar, onAnterior, onSiguiente, children }: {
  titulo: string; posicion: string; onCerrar: () => void; onAnterior?: () => void; onSiguiente?: () => void; children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
    return () => { if (d?.open) d.close(); };
  }, []);
  return (
    <dialog ref={ref} className="ventana" aria-label={titulo} onClose={onCerrar}
      onClick={(e) => { if (e.target === ref.current) onCerrar(); }}>
      <header className="ventana-cab">
        <div className="ventana-titulo"><strong>{titulo}</strong><span className="tenue">{posicion}</span></div>
        <div className="acciones">
          <button type="button" className="boton chico" disabled={!onAnterior} onClick={onAnterior}>← Anterior</button>
          <button type="button" className="boton chico" disabled={!onSiguiente} onClick={onSiguiente}>Siguiente →</button>
          <button type="button" className="boton chico" onClick={onCerrar}>Cerrar ✕</button>
        </div>
      </header>
      <div className="ventana-cuerpo">{children}</div>
    </dialog>
  );
}

interface Props { biblioteca: BibliotecaOut; onVolver: () => void; onCambio: () => void }

export function EditorBiblioteca({ biblioteca, onVolver, onCambio }: Props) {
  const bid = biblioteca.id;
  const [pestana, setPestana] = useState<'items' | TipoRecurso>('items');
  const [grupos, setGrupos] = useState<GrupoOut[]>([]);
  const [apus, setApus] = useState<ApuResumenOut[]>([]);
  const [recursos, setRecursos] = useState<RecursoBibOut[]>([]);
  const [unidades, setUnidades] = useState<UnidadOut[]>([]);
  const [grupoSel, setGrupoSel] = useState<number | 'todos' | 'sin'>('todos');
  const [abiertos, setAbiertos] = useState<number[]>([]);          // ítems desplegados en la lista (puede haber varios)
  const [ventanaId, setVentanaId] = useState<number | null>(null);  // ítem abierto en la ventana
  const [detalles, setDetalles] = useState<Record<number, ApuBibDetalleOut>>({});  // una sola copia por ítem: fila y ventana siempre coinciden
  const [buscar, setBuscar] = useState('');
  const [soloSinUnidad, setSoloSinUnidad] = useState(false);
  const [msg, setMsg] = useState<{ texto: string; error: boolean }>({ texto: '', error: false });

  const avisar = (texto: string, error = false) => setMsg({ texto, error });
  const fallo = (e: unknown) => avisar(mensajeDe(e), true);

  const recargar = useCallback(async () => {
    const [g, a, r, u] = await Promise.all([api.edGrupos(bid), api.edApusDe(bid), api.edRecursosDe(bid), api.edUnidades()]);
    setGrupos(g); setApus(a); setRecursos(r); setUnidades(u);
  }, [bid]);
  useEffect(() => { recargar().catch(fallo); }, [recargar]);
  useEffect(() => {
    if (pestana !== 'items') { setDetalles({}); return; }  // al volver de editar recursos se vuelven a leer
    const ids = ventanaId != null ? [...abiertos, ventanaId] : abiertos;
    for (const id of ids) {
      if (!detalles[id]) api.edDetalleItem(id).then((d) => setDetalles((p) => ({ ...p, [d.id]: d }))).catch(fallo);
    }
  }, [abiertos, ventanaId, pestana]);

  const unidadesDe = useMemo(() => {
    const m: Record<string, string[]> = { material: [], mano_obra: [], equipo: [], item: [] };
    unidades.forEach((u) => (m[u.tipo] ??= []).push(u.simbolo));
    return m;
  }, [unidades]);

  async function tras<T>(accion: Promise<T>, ok?: string) {
    try { const r = await accion; await recargar(); onCambio(); if (ok) avisar(ok); return r; } catch (e) { fallo(e); return undefined; }
  }
  const aplicarItem = (d: ApuBibDetalleOut | undefined, avisos = true) => {
    if (!d) return;
    setDetalles((p) => ({ ...p, [d.id]: d }));
    if (avisos && d.avisos.length) avisar(d.avisos.join(' ')); else if (avisos) setMsg({ texto: '', error: false });
  };

  const hijos = (padre: number | null) => grupos.filter((g) => g.padre_id === padre);
  const filas: { g: GrupoOut; nivel: number }[] = [];
  const recorrer = (padre: number | null, nivel: number) => hijos(padre).forEach((g) => { filas.push({ g, nivel }); recorrer(g.id, nivel + 1); });
  recorrer(null, 0);

  const q = buscar.trim().toLowerCase();
  const visibles = apus.filter((a) =>
    (grupoSel === 'todos' || (grupoSel === 'sin' ? a.grupo_id == null : a.grupo_id === grupoSel)) &&
    (!soloSinUnidad || !a.unidad) && (!q || a.nombre.toLowerCase().includes(q) || (a.codigo ?? '').toLowerCase().includes(q)));

  const alternar = (id: number) => setAbiertos((a) => (a.includes(id) ? a.filter((x) => x !== id) : [...a, id]));
  const cerrarItem = (id: number) => { setAbiertos((a) => a.filter((x) => x !== id)); setVentanaId((v) => (v === id ? null : v)); };
  const posVentana = ventanaId == null ? -1 : visibles.findIndex((a) => a.id === ventanaId);
  const irVentana = (delta: number) => { const n = visibles[posVentana + delta]; if (n) setVentanaId(n.id); };
  const editorDe = (id: number) => {
    const d = detalles[id];
    if (!d) return <p className="tenue">Cargando…</p>;
    return (
      <EditorItem key={d.id} item={d} grupos={grupos} filas={filas} recursos={recursos} unidadesDe={unidadesDe}
        onItem={aplicarItem} onRecargar={() => void recargar().then(onCambio)} onError={fallo}
        onBorrado={() => { cerrarItem(d.id); void recargar().then(onCambio); }}
        onDuplicado={(n) => { setAbiertos((a) => [...a, n.id]); void recargar().then(onCambio); }} />
    );
  };

  async function nuevoGrupo(padre: number | null) {
    const nombre = window.prompt(padre == null ? 'Nombre del grupo (p. ej. «Obra gruesa»):' : 'Nombre del subgrupo:', '')?.trim();
    if (nombre) await tras(api.edCrearGrupo(bid, nombre, padre));
  }
  async function nuevoItem() {
    const nombre = window.prompt('Nombre del ítem:', '')?.trim();
    if (!nombre) return;
    const d = await tras(api.edCrearItem(bid, { nombre, unidad: '', grupo_id: typeof grupoSel === 'number' ? grupoSel : null }));
    if (d) { setAbiertos((a) => [...a, d.id]); setPestana('items'); avisar('Ítem creado. Elige su unidad y agrega materiales, mano de obra y equipo.'); }
  }
  async function renombrarBiblioteca() {
    const nombre = window.prompt('Nuevo nombre de la biblioteca:', biblioteca.nombre)?.trim();
    if (nombre && nombre !== biblioteca.nombre) { try { await api.edRenombrarBiblioteca(bid, nombre); biblioteca.nombre = nombre; onCambio(); setMsg({ texto: '', error: false }); } catch (e) { fallo(e); } }
  }

  return (
    <section aria-labelledby="t-ed">
      <p><button type="button" className="boton" onClick={onVolver}>← Mis bibliotecas</button></p>
      <h2 id="t-ed">{biblioteca.nombre} <button type="button" className="boton chico" onClick={() => void renombrarBiblioteca()}>Renombrar</button></h2>
      <p className="tenue">
        Cada ítem tiene solo materiales, mano de obra y equipo. Cargas sociales, impuestos, gastos generales y utilidad los pone el
        modelo de cálculo que elijas en cada proyecto.
      </p>
      {msg.texto && <p className={msg.error ? 'mensaje error' : 'mensaje'} role={msg.error ? 'alert' : 'status'}>{msg.texto}</p>}

      <div className="pestanas" role="tablist">
        {[{ id: 'items' as const, t: `Ítems (${apus.length})` }, ...TIPOS.map((t) => ({ id: t.id, t: `${t.plural} (${recursos.filter((r) => r.tipo === t.id).length})` }))].map((p) => (
          <button key={p.id} type="button" role="tab" aria-selected={pestana === p.id} className={pestana === p.id ? 'pestana activa' : 'pestana'} onClick={() => setPestana(p.id)}>{p.t}</button>
        ))}
      </div>

      {pestana === 'items' ? (
        <div className="editor-rejilla">
          <aside className="panel-grupos" aria-label="Grupos">
            <h3>Grupos</h3>
            <ul className="lista-simple">
              <li><button type="button" className={grupoSel === 'todos' ? 'opcion activa' : 'opcion'} onClick={() => setGrupoSel('todos')}>Todos ({apus.length})</button></li>
              <li><button type="button" className={grupoSel === 'sin' ? 'opcion activa' : 'opcion'} onClick={() => setGrupoSel('sin')}>Sin grupo ({apus.filter((a) => a.grupo_id == null).length})</button></li>
              {filas.map(({ g, nivel }) => (
                <li key={g.id} style={{ paddingLeft: nivel * 14 }}>
                  <button type="button" className={grupoSel === g.id ? 'opcion activa' : 'opcion'} onClick={() => setGrupoSel(g.id)}>{g.nombre} ({g.items})</button>
                </li>
              ))}
            </ul>
            <p className="acciones">
              <button type="button" className="boton chico" onClick={() => void nuevoGrupo(null)}>+ Grupo</button>
              {typeof grupoSel === 'number' && (<>
                <button type="button" className="boton chico" onClick={() => void nuevoGrupo(grupoSel)}>+ Subgrupo</button>
                <button type="button" className="boton chico" onClick={() => { const g = grupos.find((x) => x.id === grupoSel); const n = window.prompt('Nuevo nombre del grupo:', g?.nombre)?.trim(); if (n) void tras(api.edCambiarGrupo(grupoSel, { nombre: n })); }}>Renombrar</button>
                <button type="button" className="boton chico peligro" onClick={() => { if (window.confirm('¿Borrar este grupo? Sus ítems no se borran: quedan «sin grupo».')) { void tras(api.edBorrarGrupo(grupoSel)); setGrupoSel('todos'); } }}>Borrar</button>
              </>)}
            </p>
          </aside>

          <div>
            <p className="acciones">
              <input className="campo" aria-label="Buscar ítems" placeholder="Buscar ítem…" value={buscar} onChange={(e) => setBuscar(e.target.value)} />
              <label><input type="checkbox" checked={soloSinUnidad} onChange={(e) => setSoloSinUnidad(e.target.checked)} /> Solo sin unidad ({apus.filter((a) => !a.unidad).length})</label>
              <button type="button" className="boton primario" onClick={() => void nuevoItem()}>+ Nuevo ítem</button>
            </p>
            <ul className="lista-items">
              {visibles.length === 0 && <li className="tenue">No hay ítems aquí. Crea uno con «Nuevo ítem».</li>}
              {visibles.slice(0, 300).map((a) => {
                const abierto = abiertos.includes(a.id);
                return (
                  <li key={a.id} className={abierto ? 'item-fila abierto' : 'item-fila'}>
                    <div className="item-cab">
                      <button type="button" className="item-nombre" aria-expanded={abierto} onClick={() => alternar(a.id)}>
                        <span className="flecha" aria-hidden="true">{abierto ? '▾' : '▸'}</span>
                        <span>
                          <strong>{a.nombre}</strong>
                          <span className="tenue">{a.unidad ? a.unidad : <span className="sin-unidad">sin unidad</span>} · {a.lineas} líneas · Bs {bs(a.costo)}</span>
                        </span>
                      </button>
                      <button type="button" className="boton chico" aria-label={`Abrir ${a.nombre} en una ventana`} onClick={() => setVentanaId(a.id)}>Ventana ⤢</button>
                    </div>
                    {abierto && <div className="item-cuerpo">{editorDe(a.id)}</div>}
                  </li>
                );
              })}
              {visibles.length > 300 && <li className="tenue">Se muestran 300 de {visibles.length}; usa el buscador para acotar.</li>}
            </ul>
            {abiertos.length > 1 && <p><button type="button" className="boton chico" onClick={() => setAbiertos([])}>Cerrar los {abiertos.length} desplegados</button></p>}
          </div>
        </div>
      ) : (
        <PestanaRecursos key={pestana} bid={bid} tipo={pestana} recursos={recursos.filter((r) => r.tipo === pestana)} unidades={unidadesDe[pestana] ?? []}
          onCambio={() => { void recargar().then(onCambio); }} onMensaje={avisar} onError={fallo} />
      )}
      {ventanaId != null && (
        <Ventana titulo={detalles[ventanaId]?.nombre ?? 'Cargando…'} posicion={posVentana >= 0 ? `Ítem ${posVentana + 1} de ${visibles.length}` : ''}
          onCerrar={() => setVentanaId(null)}
          onAnterior={posVentana > 0 ? () => irVentana(-1) : undefined}
          onSiguiente={posVentana >= 0 && posVentana < visibles.length - 1 ? () => irVentana(1) : undefined}>
          {editorDe(ventanaId)}
        </Ventana>
      )}
      {TIPOS.concat([{ id: 'item' as TipoRecurso, plural: '', singular: '' }]).map((t) => (
        <datalist key={t.id} id={`u-${t.id}`}>{(unidadesDe[t.id] ?? []).map((u) => <option key={u} value={u} />)}</datalist>
      ))}
    </section>
  );
}

function EditorItem({ item, grupos, filas, recursos, unidadesDe, onItem, onRecargar, onError, onBorrado, onDuplicado }: {
  item: ApuBibDetalleOut; grupos: GrupoOut[]; filas: { g: GrupoOut; nivel: number }[]; recursos: RecursoBibOut[]; unidadesDe: Record<string, string[]>;
  onItem: (d: ApuBibDetalleOut | undefined, avisos?: boolean) => void; onRecargar: () => void; onError: (e: unknown) => void;
  onBorrado: () => void; onDuplicado: (d: ApuBibDetalleOut) => void;
}) {
  const guardar = async (c: { nombre?: string; unidad?: string; grupo_id?: number | null; codigo?: string }) => {
    try { onItem(await api.edCambiarItem(item.id, c), false); onRecargar(); } catch (e) { onError(e); }
  };
  const linea = async (f: () => Promise<ApuBibDetalleOut>, avisos = false) => { try { onItem(await f(), avisos); onRecargar(); } catch (e) { onError(e); } };
  void grupos;
  return (
    <article className="tarjeta editor-item" aria-label={`Ítem ${item.nombre}`}>
      <div className="fila-campos">
        <label>Nombre<Campo valor={item.nombre} etiqueta="Nombre del ítem" ancho="100%" onGuardar={(v) => v && void guardar({ nombre: v })} /></label>
        <label>Unidad del ítem<Campo valor={item.unidad} etiqueta="Unidad del ítem" lista="u-item" ancho="9em" placeholder="m2, m3, Pza…" onGuardar={(v) => void guardar({ unidad: v })} /></label>
        <label>Código<Campo valor={item.codigo ?? ''} etiqueta="Código" ancho="8em" onGuardar={(v) => void guardar({ codigo: v })} /></label>
        <label>Grupo
          <select aria-label="Grupo del ítem" value={item.grupo_id ?? ''} onChange={(e) => void guardar({ grupo_id: e.target.value === '' ? null : Number(e.target.value) })}>
            <option value="">— sin grupo —</option>
            {filas.map(({ g, nivel }) => <option key={g.id} value={g.id}>{'\u00A0'.repeat(nivel * 3)}{g.nombre}</option>)}
          </select>
        </label>
      </div>
      {!item.unidad && <p className="aviso-rango" role="status">Este ítem no tiene unidad: elígela o escríbela (puede ser cualquiera).</p>}

      {TIPOS.map((t) => {
        const ls = item.lineas.filter((l) => l.tipo === t.id);
        return (
          <div key={t.id} className="bloque-tipo">
            <h4>{t.plural}</h4>
            {ls.length > 0 && (
              <div className="tabla-caja"><table className="tabla-apu">
                <thead><tr><th>Descripción</th><th>Unidad</th><th className="num">Cantidad</th><th className="num">Precio</th><th className="num">Importe</th><th>Origen</th><th /></tr></thead>
                <tbody>
                  {ls.map((l: LineaBibOut) => (
                    <tr key={l.id}>
                      <td>{l.descripcion}</td><td>{l.unidad}</td>
                      <td className="num"><Campo num valor={l.cantidad ?? ''} etiqueta={`Cantidad de ${l.descripcion}`} ancho="6.5em" onGuardar={(v) => void linea(() => api.edCambiarLinea(l.id, { cantidad: v === '' ? null : v }))} /></td>
                      <td className="num"><Campo num valor={l.precio_unitario ?? ''} etiqueta={`Precio de ${l.descripcion}`} ancho="6.5em" onGuardar={(v) => void linea(() => api.edCambiarLinea(l.id, { precio_unitario: v === '' ? null : v }))} /></td>
                      <td className="num">{bs(l.importe)}</td>
                      <td><select aria-label={`Origen del rendimiento de ${l.descripcion}`} value={l.origen_rendimiento} onChange={(e) => void linea(() => api.edCambiarLinea(l.id, { origen_rendimiento: e.target.value }))}>
                        {[...new Set([l.origen_rendimiento, ...ORIGENES])].map((o) => <option key={o} value={o}>{o}</option>)}</select></td>
                      <td><button type="button" className="quitar" aria-label={`Quitar ${l.descripcion}`} onClick={() => void linea(() => api.edBorrarLinea(l.id))}>×</button></td>
                    </tr>
                  ))}
                </tbody>
              </table></div>
            )}
            <NuevaLinea tipo={t.id} etiqueta={t.singular} recursos={recursos.filter((r) => r.tipo === t.id)} unidades={unidadesDe[t.id] ?? []}
              onAgregar={(l) => void linea(() => api.edAgregarLinea(item.id, l), true)} />
          </div>
        );
      })}
      <p className="total-item"><strong>Costo directo: Bs {bs(item.costo_directo)}</strong> {item.costo_directo == null && <span className="tenue"> (faltan cantidades o precios: no se inventa)</span>}</p>
      <p className="acciones">
        <button type="button" className="boton" onClick={() => { void api.edDuplicarItem(item.id).then(onDuplicado).catch(onError); }}>Duplicar ítem</button>
        <button type="button" className="boton peligro" onClick={() => { if (window.confirm(`¿Borrar «${item.nombre}»?`)) void api.edBorrarItem(item.id).then(onBorrado).catch(onError); }}>Borrar ítem</button>
      </p>
    </article>
  );
}

function NuevaLinea({ tipo, etiqueta, recursos, unidades, onAgregar }: {
  tipo: TipoRecurso; etiqueta: string; recursos: RecursoBibOut[]; unidades: string[]; onAgregar: (l: { recurso_id?: number; tipo?: TipoRecurso; nombre?: string; unidad?: string; cantidad?: string | null; precio_unitario?: string | null }) => void;
}) {
  const [nombre, setNombre] = useState('');
  const [unidad, setUnidad] = useState('');
  const [cantidad, setCantidad] = useState('');
  const [precio, setPrecio] = useState('');
  const existente = recursos.find((r) => r.nombre.toLowerCase() === nombre.trim().toLowerCase() && (!unidad || r.unidad.toLowerCase() === unidad.trim().toLowerCase()))
    ?? recursos.find((r) => r.nombre.toLowerCase() === nombre.trim().toLowerCase());
  const elegirNombre = (v: string) => {
    setNombre(v);
    const r = recursos.find((x) => x.nombre.toLowerCase() === v.trim().toLowerCase());
    if (r) { setUnidad(r.unidad); setPrecio(r.precio_referencia ?? ''); }
  };
  const lista = `rec-${tipo}`;
  const puede = nombre.trim() !== '' && (existente != null || unidad.trim() !== '');
  function agregar() {
    onAgregar(existente && (!unidad || existente.unidad.toLowerCase() === unidad.trim().toLowerCase())
      ? { recurso_id: existente.id, cantidad: cantidad || null, precio_unitario: precio || null }
      : { tipo, nombre: nombre.trim(), unidad: unidad.trim(), cantidad: cantidad || null, precio_unitario: precio || null });
    setNombre(''); setUnidad(''); setCantidad(''); setPrecio('');
  }
  return (
    <div className="nueva-linea">
      <datalist id={lista}>{recursos.map((r) => <option key={r.id} value={r.nombre}>{r.unidad}</option>)}</datalist>
      <input className="campo" list={lista} aria-label={`Agregar ${etiqueta}: nombre`} placeholder={`Agregar ${etiqueta}: elige de tu biblioteca o escribe uno nuevo`} value={nombre} onChange={(e) => elegirNombre(e.target.value)} />
      <input className="campo" list={`u-${tipo}`} aria-label="Unidad" placeholder="Unidad" style={{ width: '7em' }} value={unidad} onChange={(e) => setUnidad(e.target.value)} />
      <input className="campo-num" inputMode="decimal" aria-label="Cantidad por unidad del ítem" placeholder="Cantidad" style={{ width: '6.5em' }} value={cantidad} onChange={(e) => setCantidad(e.target.value.replace(',', '.'))} />
      <input className="campo-num" inputMode="decimal" aria-label="Precio unitario" placeholder="Precio" style={{ width: '6.5em' }} value={precio} onChange={(e) => setPrecio(e.target.value.replace(',', '.'))} />
      <button type="button" className="boton" disabled={!puede} onClick={agregar}>Agregar</button>
      {nombre.trim() !== '' && !existente && <span className="tenue"> Nuevo: se guardará en tu biblioteca de {etiqueta}.</span>}
      {unidades.length === 0 && null}
    </div>
  );
}

function PestanaRecursos({ bid, tipo, recursos, unidades, onCambio, onMensaje, onError }: {
  bid: number; tipo: TipoRecurso; recursos: RecursoBibOut[]; unidades: string[]; onCambio: () => void; onMensaje: (t: string) => void; onError: (e: unknown) => void;
}) {
  const t = TIPOS.find((x) => x.id === tipo)!;
  const [nombre, setNombre] = useState('');
  const [unidad, setUnidad] = useState('');
  const [precio, setPrecio] = useState('');
  const [q, setQ] = useState('');
  const [otras, setOtras] = useState<RecursoBibOut[]>([]);
  const [filtro, setFiltro] = useState('');
  void unidades;
  const ok = async (f: Promise<unknown>, texto?: string) => { try { await f; onCambio(); if (texto) onMensaje(texto); } catch (e) { onError(e); } };
  async function buscarOtras(v: string) {
    setQ(v);
    if (v.trim().length < 2) { setOtras([]); return; }
    try { setOtras(await api.edRecursosDeOtras(bid, v, tipo)); } catch (e) { onError(e); }
  }
  const lista = recursos.filter((r) => !filtro.trim() || r.nombre.toLowerCase().includes(filtro.trim().toLowerCase()));
  return (
    <div>
      <p className="tenue">
        Tu biblioteca de {t.plural.toLowerCase()}. Se alimenta sola cuando escribes uno nuevo dentro de un ítem, y también puedes crearlos aquí.
        Cambiar el nombre, la unidad o el precio actualiza los ítems de esta biblioteca que lo usan (los proyectos ya creados conservan su copia).
      </p>
      <form className="nueva-linea" onSubmit={(e) => { e.preventDefault(); if (nombre.trim() && unidad.trim()) { void ok(api.edCrearRecurso(bid, { tipo, nombre: nombre.trim(), unidad: unidad.trim(), precio_referencia: precio || null }), `«${nombre.trim()}» agregado.`); setNombre(''); setUnidad(''); setPrecio(''); } }}>
        <input className="campo" aria-label={`Nombre del ${t.singular}`} placeholder={`Nuevo ${t.singular}`} value={nombre} onChange={(e) => setNombre(e.target.value)} />
        <input className="campo" list={`u-${tipo}`} aria-label="Unidad" placeholder="Unidad (elige o escribe)" style={{ width: '10em' }} value={unidad} onChange={(e) => setUnidad(e.target.value)} />
        <input className="campo-num" inputMode="decimal" aria-label="Precio de referencia" placeholder="Precio (opcional)" style={{ width: '8em' }} value={precio} onChange={(e) => setPrecio(e.target.value.replace(',', '.'))} />
        <button type="submit" className="boton primario" disabled={!nombre.trim() || !unidad.trim()}>Agregar</button>
      </form>
      <p><input className="campo" aria-label="Filtrar" placeholder="Filtrar…" value={filtro} onChange={(e) => setFiltro(e.target.value)} /></p>
      <div className="tabla-caja"><table className="tabla-apu">
        <thead><tr><th>Nombre</th><th>Unidad</th><th className="num">Precio ref.</th><th className="num">Usos</th><th /></tr></thead>
        <tbody>
          {lista.length === 0 && <tr><td colSpan={5} className="tenue">Aún no hay {t.plural.toLowerCase()} aquí.</td></tr>}
          {lista.slice(0, 400).map((r) => (
            <tr key={r.id}>
              <td><Campo valor={r.nombre} etiqueta={`Nombre de ${r.nombre}`} ancho="100%" onGuardar={(v) => v && void ok(api.edCambiarRecurso(r.id, { nombre: v }))} /></td>
              <td><Campo valor={r.unidad} etiqueta={`Unidad de ${r.nombre}`} lista={`u-${tipo}`} ancho="8em" onGuardar={(v) => v && void ok(api.edCambiarRecurso(r.id, { unidad: v }))} /></td>
              <td className="num"><Campo num valor={r.precio_referencia ?? ''} etiqueta={`Precio de ${r.nombre}`} ancho="7em" onGuardar={(v) => void ok(api.edCambiarRecurso(r.id, { precio_referencia: v === '' ? null : v }))} /></td>
              <td className="num">{r.usos}</td>
              <td><button type="button" className="quitar" aria-label={`Borrar ${r.nombre}`} onClick={() => {
                if (r.usos === 0 || window.confirm(`«${r.nombre}» se usa en ${r.usos} línea(s). Si lo borras, esas líneas conservan su texto pero dejan de estar ligadas al recurso. ¿Borrar?`)) void ok(api.edBorrarRecurso(r.id, r.usos > 0));
              }}>×</button></td>
            </tr>
          ))}
        </tbody>
      </table></div>
      {lista.length > 400 && <p className="tenue">Se muestran 400 de {lista.length}; usa el filtro.</p>}
      <h3>Traer de tus otras bibliotecas</h3>
      <p><input className="campo" aria-label="Buscar en otras bibliotecas" placeholder={`Buscar ${t.singular} en otras bibliotecas…`} value={q} onChange={(e) => void buscarOtras(e.target.value)} /></p>
      {otras.length > 0 && (
        <ul className="lista-simple">
          {otras.map((o) => (
            <li key={o.id} className="fila-biblioteca"><span><strong>{o.nombre}</strong> <span className="tenue">{o.unidad}{o.precio_referencia ? ` · Bs ${bs(o.precio_referencia)}` : ''} · de «{o.biblioteca_nombre}»</span></span>
              <button type="button" className="boton chico" onClick={() => void ok(api.edCopiarRecurso(bid, o.id), `«${o.nombre}» traído a esta biblioteca.`)}>Traer</button></li>
          ))}
        </ul>
      )}
    </div>
  );
}
