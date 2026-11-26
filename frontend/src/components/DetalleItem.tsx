import { useEffect, useState } from 'react';
import { api, mensajeDe } from '../api';
import type { CandidatoOut, ItemOut, LineaApuOut, ModoRecursos, ProyectoOut } from '../types';
import { CeldaPrecio } from './CeldaPrecio';

const formato = new Intl.NumberFormat('es-BO', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const bs = (v: string | null) => (v == null ? '—' : formato.format(Number(v)));
const TIPOS = { material: 'Materiales', mano_obra: 'Mano de obra', equipo: 'Equipo' } as const;
const TIPO_UNO = { material: 'Material', mano_obra: 'Mano de obra', equipo: 'Equipo' } as const;
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

const lineaVacia = { tipo: 'material' as LineaApuOut['tipo'], descripcion: '', unidad: '', cantidad: '', precio: '' };

export function DetalleItem({ item, modo, bibliotecaIds, onActualizar }: Props) {
  const [candidatos, setCandidatos] = useState<CandidatoOut[] | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState('');
  const [aplicarPrecio, setAplicarPrecio] = useState(true);
  const [nueva, setNueva] = useState(lineaVacia);

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
  const agregar = () =>
    ejecutar(async () => {
      onActualizar(await api.agregarLinea(item.id, {
        tipo: nueva.tipo, descripcion: nueva.descripcion, unidad: nueva.unidad,
        cantidad: nueva.cantidad.trim() || null, precio_unitario: nueva.precio.trim() || null,
      }));
      setNueva(lineaVacia);
    });

  const pend = item.apu?.pendientes ?? 0;

  return (
    <div className="detalle-caja">
      {error && <p className="mensaje error columna-completa" role="alert">{error}</p>}

      <div className="columna-completa">
        <h4>
          APU del ítem
          {item.apu && (
            <span className={`chip ${item.apu.estado}`}> {ESTADO_APU[item.apu.estado]}
              {item.apu.precio != null ? ` · Bs ${bs(item.apu.precio)} por unidad` : ''}
            </span>
          )}
        </h4>

        {item.apu ? (
          <>
            <div className="tabla-caja">
              <table className="tabla-apu">
                <thead>
                  <tr>
                    <th>Tipo</th>
                    <th>Recurso</th>
                    <th>Unidad</th>
                    <th className="num" title="Consumo o rendimiento por cada unidad del ítem. Ejemplos: kg de cemento por m²; horas-hombre por m².">
                      Cantidad por unidad del ítem
                    </th>
                    <th className="num">Precio (Bs)</th>
                    <th>Origen del rendimiento</th>
                    <th><span className="solo-lector">Quitar</span></th>
                  </tr>
                </thead>
                <tbody>
                  {item.apu.lineas.map((l) => (
                    <tr key={l.id} className={l.estado === 'pendiente' ? 'pendiente' : ''} title={l.fuente ?? undefined}>
                      <td>{TIPO_UNO[l.tipo]}</td>
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
          <p className="tenue">Este ítem todavía no tiene APU. Búscalo en tu biblioteca, usa los recursos del pliego o agrega tus propios recursos aquí abajo.</p>
        )}

        <fieldset className="nueva-linea" disabled={ocupado}>
          <legend>Agregar un recurso a este APU</legend>
          <select className="mini" aria-label="Tipo de recurso" value={nueva.tipo}
                  onChange={(e) => setNueva({ ...nueva, tipo: e.target.value as LineaApuOut['tipo'] })}>
            {(Object.keys(TIPO_UNO) as LineaApuOut['tipo'][]).map((t) => <option key={t} value={t}>{TIPO_UNO[t]}</option>)}
          </select>
          <input className="mini ancho" placeholder="Nombre (ej. Cemento portland)" aria-label="Nombre del recurso"
                 value={nueva.descripcion} onChange={(e) => setNueva({ ...nueva, descripcion: e.target.value })} />
          <input className="mini corto" placeholder="Unidad" aria-label="Unidad" value={nueva.unidad}
                 onChange={(e) => setNueva({ ...nueva, unidad: e.target.value })} />
          <input className="mini corto" placeholder="Cantidad" aria-label="Cantidad por unidad del ítem" inputMode="decimal"
                 value={nueva.cantidad} onChange={(e) => setNueva({ ...nueva, cantidad: e.target.value })} />
          <input className="mini corto" placeholder="Precio" aria-label="Precio" inputMode="decimal" value={nueva.precio}
                 onChange={(e) => setNueva({ ...nueva, precio: e.target.value })} />
          <button type="button" className="boton" disabled={!nueva.descripcion.trim()} onClick={() => void agregar()}>Agregar</button>
        </fieldset>

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
  );
}
