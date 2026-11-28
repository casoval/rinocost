import { useEffect, useRef, useState } from 'react';
import { api, mensajeDe } from '../api';
import type { CandidatoOut, HojaB2Out, ItemOut, LineaApuOut, ModoRecursos, ProyectoOut } from '../types';
import { CeldaPrecio } from './CeldaPrecio';
import { HojaB2Modal } from './HojaB2Modal';
import './hojab2.css';

const formato = new Intl.NumberFormat('es-BO', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const bs = (v: string | null) => (v == null ? '—' : formato.format(Number(v)));
const TIPOS = { material: 'Materiales', mano_obra: 'Mano de obra', equipo: 'Equipo' } as const;
const ORIGEN: Record<string, string> = {
  pliego: 'Pliego', biblioteca: 'Mi biblioteca', ambos: 'Pliego + biblioteca', manual: 'Agregado por mí',
};
const ORIGENES_RENDIMIENTO: [string, string][] = [
  ['manual', 'Manual'], ['medido', 'Medido en obra'], ['calculado', 'Calculado'], ['similar', 'De un ítem similar'],
  ['referencial', 'Referencial'], ['biblioteca', 'Mi biblioteca'], ['pendiente', 'Pendiente'],
];
const ESTADO_APU = { completo: 'completo', incompleto: 'incompleto', vacio: 'vacío' } as const;
const DATOS: Record<string, string> = {
  dosificacion: 'Dosificación', espesor: 'Espesor', cemento_minimo: 'Cemento mínimo',
  rendimiento_declarado: 'Rendimiento declarado', espera: 'Espera obligatoria',
};

function CeldaTexto({ valor, etiqueta, onGuardar }: { valor: string; etiqueta: string; onGuardar: (v: string) => Promise<void> }) {
  const [texto, setTexto] = useState(valor);
  useEffect(() => setTexto(valor), [valor]);
  return (
    <input
      className="mini"
      value={texto}
      aria-label={etiqueta}
      onChange={(e) => setTexto(e.target.value)}
      onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur(); }}
      onBlur={() => { if (texto.trim() !== valor) onGuardar(texto.trim()).catch(() => setTexto(valor)); }}
    />
  );
}

interface Props {
  item: ItemOut;
  modo: ModoRecursos;
  bibliotecaIds: number[];
  onActualizar: (p: ProyectoOut) => void;
}

interface NuevaLinea { descripcion: string; unidad: string; cantidad: string; precio: string }
const VACIA: NuevaLinea = { descripcion: '', unidad: '', cantidad: '', precio: '' };
const ROTULO_AGREGAR = { material: 'material', mano_obra: 'mano de obra', equipo: 'equipo' } as const;

/** Alta rápida dentro de una categoría: el tipo ya está fijado, así que no hay selector que confundir. */
function AgregarRecurso({ tipo, ocupado, onAgregar }: { tipo: LineaApuOut['tipo']; ocupado: boolean; onAgregar: (d: NuevaLinea) => Promise<void> }) {
  const [abierto, setAbierto] = useState(false);
  const [d, setD] = useState<NuevaLinea>(VACIA);
  const nombre = useRef<HTMLInputElement>(null);

  if (!abierto) {
    return (
      <div className="cat-agregar">
        <button type="button" className="enlace" onClick={() => setAbierto(true)}>+ Agregar {ROTULO_AGREGAR[tipo]}</button>
      </div>
    );
  }
  const enviar = () => {
    if (!d.descripcion.trim()) return;
    onAgregar(d).then(() => { setD(VACIA); nombre.current?.focus(); }).catch(() => undefined);
  };
  const tecla = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') { e.preventDefault(); enviar(); }
    if (e.key === 'Escape') setAbierto(false);
  };
  return (
    <div className="cat-agregar abierto" onKeyDown={tecla}>
      <input ref={nombre} autoFocus className="mini ancho" placeholder={`Nombre del ${ROTULO_AGREGAR[tipo]}`} aria-label={`Nombre del ${ROTULO_AGREGAR[tipo]}`}
             value={d.descripcion} onChange={(e) => setD({ ...d, descripcion: e.target.value })} />
      <input className="mini corto" placeholder="Unidad" aria-label="Unidad" value={d.unidad} onChange={(e) => setD({ ...d, unidad: e.target.value })} />
      <input className="mini corto" placeholder="Cantidad" aria-label="Cantidad por unidad del ítem" inputMode="decimal" value={d.cantidad}
             onChange={(e) => setD({ ...d, cantidad: e.target.value })} />
      <input className="mini corto" placeholder="Precio" aria-label="Precio" inputMode="decimal" value={d.precio} onChange={(e) => setD({ ...d, precio: e.target.value })} />
      <button type="button" className="boton primario" disabled={ocupado || !d.descripcion.trim()} onClick={enviar}>Agregar</button>
      <button type="button" className="boton" onClick={() => { setAbierto(false); setD(VACIA); }}>Listo</button>
    </div>
  );
}

export function DetalleItem({ item, modo, bibliotecaIds, onActualizar }: Props) {
  const [candidatos, setCandidatos] = useState<CandidatoOut[] | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState('');
  const [aplicarPrecio, setAplicarPrecio] = useState(true);
  const [hoja, setHoja] = useState<HojaB2Out | null>(null);
  const [verHoja, setVerHoja] = useState(false);

  // Subtotales e importes vienen del servidor (mismo motor que el PDF y el Excel); se piden otra vez cuando cambia el APU.
  const firma = JSON.stringify(item.apu?.lineas.map((l) => [l.id, l.cantidad, l.precio_unitario]) ?? null);
  useEffect(() => {
    let vivo = true;
    if (!item.apu) { setHoja(null); return; }
    api.hojaB2(item.id).then((h) => vivo && setHoja(h)).catch(() => vivo && setHoja(null));
    return () => { vivo = false; };
  }, [item.id, firma]);

  async function ejecutar(accion: () => Promise<void>) {
    try {
      setError('');
      setOcupado(true);
      await accion();
    } catch (e) {
      setError(mensajeDe(e));
    } finally {
      setOcupado(false);
    }
  }

  // Para las celdas: si falla, avisa arriba y relanza para que la celda vuelva a su valor anterior.
  async function guardar(accion: () => Promise<ProyectoOut>) {
    try {
      setError('');
      onActualizar(await accion());
    } catch (e) {
      setError(mensajeDe(e));
      throw e;
    }
  }

  const buscar = () => ejecutar(async () => setCandidatos(await api.candidatos(item.id, bibliotecaIds)));
  const usar = (c: CandidatoOut) =>
    ejecutar(async () => {
      onActualizar(await api.vincular(item.id, { apu_id: c.apu_id, modo, recordar: true, confianza: c.confianza }));
      setCandidatos(null);
    });
  const soloPliego = () =>
    ejecutar(async () => onActualizar(await api.vincular(item.id, { apu_id: null, modo: 'pliego', recordar: false })));
  const quitar = (l: LineaApuOut) => {
    if (l.requerido_por_pliego && !window.confirm(`El pliego pide «${l.descripcion}». ¿Quitarlo de este APU de todos modos?`)) return;
    void ejecutar(async () => onActualizar(await api.eliminarLinea(l.id)));
  };
  const agregarDe = (tipo: LineaApuOut['tipo'], d: NuevaLinea) =>
    ejecutar(async () => {
      onActualizar(await api.agregarLinea(item.id, {
        tipo, descripcion: d.descripcion, unidad: d.unidad,
        cantidad: d.cantidad.trim() || null, precio_unitario: d.precio.trim() || null,
      }));
    });

  const pend = item.apu?.pendientes ?? 0;

  return (
    <div className="detalle-caja">
      {error && <p className="mensaje error columna-completa" role="alert">{error}</p>}

      <div className="columna-completa">
        <div className="apu-resumen">
          <h4>
            APU del ítem
            {item.apu && <span className={`chip ${item.apu.estado}`}> {ESTADO_APU[item.apu.estado]}</span>}
          </h4>
          {item.apu && (
            <span className="apu-precio">
              {item.apu.precio != null ? <>Precio unitario <strong>Bs {bs(item.apu.precio)}</strong> por {item.unidad}</> : <span className="tenue">Precio pendiente</span>}
              {' '}
              <button type="button" className="boton" onClick={() => setVerHoja(true)}>Ver hoja B-2</button>
            </span>
          )}
        </div>

        <div className="cats">
          {(['material', 'mano_obra', 'equipo'] as const).map((tipo) => {
            const lineas = (item.apu?.lineas ?? []).filter((l) => l.tipo === tipo);
            const costo = new Map((hoja?.secciones.find((x) => x.tipo_recurso === tipo)?.lineas ?? []).map((x) => [x.id, x.costo]));
            return (
              <section key={tipo} className={`cat ${tipo}`} aria-label={TIPOS[tipo]}>
                <div className="cat-cab">
                  <h5>{TIPOS[tipo]} <span className="tenue">({lineas.length})</span></h5>
                  <span className="cat-sub" title="Suma de cantidad × precio de esta categoría">
                    Subtotal Bs {bs(hoja?.subtotal_por_tipo[tipo] ?? null)}
                  </span>
                </div>
                {lineas.length === 0 ? (
                  <p className="tenue cat-vacia">Sin recursos de este tipo.</p>
                ) : (
                  <div className="tabla-caja">
                    <table className="tabla-apu">
                      <thead>
                        <tr>
                          <th>Recurso</th>
                          <th>Unidad</th>
                          <th className="num" title="Consumo o rendimiento por cada unidad del ítem. Ejemplos: kg de cemento por m²; horas-hombre por m².">Cantidad</th>
                          <th className="num">Precio (Bs)</th>
                          <th className="num">Importe (Bs)</th>
                          <th>Origen del rendimiento</th>
                          <th><span className="solo-lector">Quitar</span></th>
                        </tr>
                      </thead>
                      <tbody>
                        {lineas.map((l) => (
                        <tr key={l.id} className={l.estado === 'pendiente' ? 'pendiente' : ''} title={l.fuente ?? undefined}>
                          <td>
                            {l.descripcion}
                            {l.requerido_por_pliego && <span className="chip req"> pliego</span>}
                            <div className="tenue origen-dato">{ORIGEN[l.origen_dato] ?? l.origen_dato}</div>
                          </td>
                          <td>
                            <CeldaTexto valor={l.unidad} etiqueta={`Unidad de ${l.descripcion}`}
                                        onGuardar={(v) => guardar(() => api.editarLinea(l.id, { unidad: v })).then(() => undefined)} />
                          </td>
                          <td className="num">
                            <CeldaPrecio valor={l.cantidad} grupo={`cant-${item.id}`} ancho={96}
                                         etiqueta={`Cantidad de ${l.descripcion} por unidad del ítem`}
                                         onGuardar={(v) => guardar(() => api.editarLinea(l.id, { cantidad: v })).then(() => undefined)} />
                          </td>
                          <td className="num">
                            <CeldaPrecio valor={l.precio_unitario} grupo={`prec-${item.id}`} ancho={96}
                                         etiqueta={`Precio de ${l.descripcion}`}
                                         onGuardar={(v) => guardar(() => api.editarLinea(l.id, { precio_unitario: v, aplicar_precio_a_recurso: aplicarPrecio })).then(() => undefined)} />
                          </td>
                          <td className="num">{bs(costo.get(l.id) ?? null)}</td>
                          <td>
                            <select
                              className="mini"
                              value={l.origen_rendimiento}
                              aria-label={`Origen del rendimiento de ${l.descripcion}`}
                              onChange={(e) => void guardar(() => api.editarLinea(l.id, { origen_rendimiento: e.target.value })).catch(() => undefined)}
                            >
                              {ORIGENES_RENDIMIENTO.map(([valor, rotulo]) => <option key={valor} value={valor}>{rotulo}</option>)}
                              {!ORIGENES_RENDIMIENTO.some(([valor]) => valor === l.origen_rendimiento) && (
                                <option value={l.origen_rendimiento}>{l.origen_rendimiento}</option>
                              )}
                            </select>
                          </td>
                          <td>
                            <button type="button" className="quitar" aria-label={`Quitar ${l.descripcion} del APU`} disabled={ocupado} onClick={() => quitar(l)}>×</button>
                          </td>
                        </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <AgregarRecurso tipo={tipo} ocupado={ocupado} onAgregar={(d) => agregarDe(tipo, d)} />
              </section>
            );
          })}
        </div>
        {item.apu ? (
          <>
            <label className="casilla">
              <input type="checkbox" checked={aplicarPrecio} onChange={(e) => setAplicarPrecio(e.target.checked)} />
              Al cambiar un precio, aplicarlo a todas las líneas de ese mismo recurso en el proyecto
            </label>
            <p className="tenue pie-detalle">
              {pend > 0
                ? `${pend === 1 ? 'Falta 1 línea' : `Faltan ${pend} líneas`} por completar: el ítem no tiene precio hasta que el APU esté completo.`
                : item.apu.lineas.length > 0 ? 'El precio del ítem sale de este APU.' : 'El APU no tiene líneas.'}{' '}
              Si cambias una cantidad, su origen pasa a «Manual»; elige otro si corresponde.{' '}
              {item.vinculo_confianza && !item.vinculo_confirmado && `Vinculado automáticamente (confianza ${item.vinculo_confianza}): revísalo.`}
            </p>
          </>
        ) : (
          <p className="tenue">Este ítem todavía no tiene APU. Búscalo en tu biblioteca, usa los recursos del pliego o agrega tus propios recursos en cada categoría.</p>
        )}

        <div className="acciones">
          <button type="button" className="boton" disabled={ocupado || bibliotecaIds.length === 0} onClick={() => void buscar()}>
            {item.apu ? 'Cambiar APU' : 'Buscar APU en mi biblioteca'}
          </button>
          {item.requisitos.length > 0 && (
            <button type="button" className="boton" disabled={ocupado} onClick={() => void soloPliego()}>
              Usar solo los recursos del pliego
            </button>
          )}
        </div>
        {bibliotecaIds.length === 0 && <p className="tenue">Importa una biblioteca (Excel) para buscar APU.</p>}

        {candidatos && (
          <ul className="candidatos">
            {candidatos.length === 0 && <li className="tenue">No hay APU parecidos en la biblioteca.</li>}
            {candidatos.map((c) => (
              <li key={c.apu_id} className="candidato">
                <div>
                  <strong>{c.nombre}</strong>{' '}
                  <span className={`chip ${c.confianza}`}>{c.confianza}</span>
                  {c.motivo === 'equivalencia' && <span className="chip req"> ya confirmado antes</span>}
                  <span className="tenue"> · {c.unidad || 'sin unidad'} · {Math.round(c.puntaje * 100)}%</span>
                  {c.avisos.map((a, i) => <p key={i} className="aviso-candidato">{a}</p>)}
                </div>
                <button type="button" className="boton" disabled={ocupado} onClick={() => void usar(c)}>Usar este APU</button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {(item.requisitos.length > 0 || item.sin_materiales || item.datos_tecnicos.length > 0 || item.caracteristicas.length > 0) && (
        <details className="columna-completa pliego-caja">
          <summary>Lo que dice el pliego ({item.requisitos.length} {item.requisitos.length === 1 ? 'recurso' : 'recursos'})</summary>
          <div className="pliego-grupos">
      {(['material', 'mano_obra', 'equipo'] as const).map((tipo) => {
        const lista = item.requisitos.filter((r) => r.tipo === tipo);
        if (lista.length === 0) return null;
        return (
          <div key={tipo}>
            <h4>Pliego: {TIPOS[tipo].toLowerCase()}</h4>
            <ul>
              {lista.map((r) => (
                <li key={r.id} title={r.fragmento}>
                  {r.nombre}{r.unidad ? ` (${r.unidad})` : ''}{r.detalle ? ` — ${r.detalle}` : ''}{' '}
                  <span className="tenue">p. {r.pagina}</span>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
      {item.sin_materiales && <p className="tenue">La especificación indica que no requiere materiales.</p>}
      {item.datos_tecnicos.length > 0 && (
        <div>
          <h4>Datos técnicos</h4>
          <ul>
            {item.datos_tecnicos.map((d, i) => (
              <li key={i} title={d.fragmento}>
                {DATOS[d.tipo] ?? d.tipo}: <strong>{d.valor}</strong> <span className="tenue">p. {d.pagina}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {item.caracteristicas.length > 0 && (
        <div>
          <h4>Características mínimas</h4>
          <ul>{item.caracteristicas.map((c, i) => <li key={i}>{c}</li>)}</ul>
        </div>
      )}
          </div>
        </details>
      )}
      {verHoja && <HojaB2Modal itemId={item.id} onCerrar={() => setVerHoja(false)} />}
    </div>
  );
}
