import { useState, type ReactNode } from 'react';
import { api, descargar, mensajeDe, nombreArchivo } from '../api';
import type { CronogramaIn, CronogramaOut, ProyectoOut, Secuencia } from '../types';
import './cronograma.css';

const SECUENCIAS: { valor: Secuencia; titulo: string }[] = [
  { valor: 'modulos_en_serie', titulo: 'Un módulo tras otro (los ítems de cada módulo, en paralelo)' },
  { valor: 'todo_en_serie', titulo: 'Todos los ítems uno tras otro' },
  { valor: 'todo_en_paralelo', titulo: 'Todo en paralelo' },
];

const dmy = (s: string | null) => (s ? s.split('-').reverse().join('/') : '—');
const ms = (s: string) => Date.parse(`${s}T00:00:00Z`);
const dias = (a: string, b: string) => Math.round((ms(b) - ms(a)) / 86400000);
const hoy = () => new Date().toISOString().slice(0, 10);
const numero = (texto: string) => Number(texto.replace(',', '.'));

type Cambios = Partial<{ personas: Record<number, number>; hitos: Record<number, string> }>;

export function Cronograma({ proyecto }: { proyecto: ProyectoOut }) {
  const [inicio, setInicio] = useState(hoy());
  const [horas, setHoras] = useState('8');
  const [personasDef, setPersonasDef] = useState('2');
  const [sabados, setSabados] = useState(false);
  const [secuencia, setSecuencia] = useState<Secuencia>('modulos_en_serie');
  const [feriados, setFeriados] = useState('');
  const [personas, setPersonas] = useState<Record<number, number>>({});
  const [hitos, setHitos] = useState<Record<number, string>>({});
  const [resultado, setResultado] = useState<CronogramaOut | null>(null);
  const [error, setError] = useState('');
  const [ocupado, setOcupado] = useState(false);

  function cuerpo(cambios?: Cambios): CronogramaIn {
    const h = numero(horas);
    const p = Math.floor(numero(personasDef));
    if (!inicio) throw new Error('Elige la fecha de inicio.');
    if (!(h > 0 && h <= 24)) throw new Error('Las horas de jornada deben estar entre 1 y 24.');
    if (!(p >= 1)) throw new Error('Las personas por actividad deben ser al menos 1.');
    const hitosUsados = cambios?.hitos ?? hitos;
    return {
      fecha_inicio: inicio,
      horas_jornada: h,
      personas_por_defecto: p,
      trabaja_sabados: sabados,
      feriados: feriados.split(/[\s,;]+/).filter((t) => /^\d{4}-\d{2}-\d{2}$/.test(t)),
      secuencia,
      personas: cambios?.personas ?? personas,
      hitos: Object.fromEntries(Object.entries(hitosUsados).filter(([, f]) => f)) as Record<number, string>,
    };
  }

  async function calcular(cambios?: Cambios) {
    try {
      setError('');
      setOcupado(true);
      setResultado(await api.cronograma(proyecto.id, cuerpo(cambios)));
    } catch (e) {
      setError(mensajeDe(e));
    } finally {
      setOcupado(false);
    }
  }

  async function descargarExcel() {
    try {
      setError('');
      setOcupado(true);
      const blob = await api.exportar(proyecto.id, cuerpo());
      descargar(blob, nombreArchivo(`cronograma-${proyecto.nombre}`, 'xlsx'));
    } catch (e) {
      setError(mensajeDe(e));
    } finally {
      setOcupado(false);
    }
  }

  function cambiarPersonas(itemId: number, texto: string) {
    const n = Math.floor(numero(texto));
    if (!(n >= 1) || personas[itemId] === n) return;
    const nuevo = { ...personas, [itemId]: n };
    setPersonas(nuevo);
    void calcular({ personas: nuevo });
  }

  function cambiarHito(moduloId: number, valor: string) {
    if ((hitos[moduloId] ?? '') === valor) return;
    const nuevo = { ...hitos, [moduloId]: valor };
    setHitos(nuevo);
    void calcular({ hitos: nuevo });
  }

  const total = resultado?.fecha_fin ? dias(resultado.fecha_inicio, resultado.fecha_fin) + 1 : 1;
  const escala = resultado?.fecha_fin ? marcasDeMes(resultado.fecha_inicio, resultado.fecha_fin, total) : [];
  const pct = (n: number) => `${Math.min(Math.max(n, 0), 100)}%`;

  return (
    <div className="crono">
      <p className="crono-nota">
        La duración de cada ítem sale de la mano de obra de su APU: horas-hombre ÷ (personas × horas de jornada), en días
        hábiles. Solo se programan los ítems cuyo APU tiene <strong>toda</strong> su mano de obra con cantidad.
      </p>

      <fieldset className="crono-params" disabled={ocupado}>
        <legend>Parámetros</legend>
        <label className="crono-campo">
          <span>Inicio de obra</span>
          <input type="date" value={inicio} onChange={(e) => setInicio(e.target.value)} />
        </label>
        <label className="crono-campo">
          <span>Horas de jornada</span>
          <input inputMode="decimal" value={horas} onChange={(e) => setHoras(e.target.value)} />
        </label>
        <label className="crono-campo">
          <span>Personas por actividad</span>
          <input inputMode="numeric" value={personasDef} onChange={(e) => setPersonasDef(e.target.value)} />
        </label>
        <label className="crono-campo crono-casilla">
          <input type="checkbox" checked={sabados} onChange={(e) => setSabados(e.target.checked)} />
          <span>Se trabaja los sábados</span>
        </label>
        <label className="crono-campo crono-ancho">
          <span>Secuencia</span>
          <select value={secuencia} onChange={(e) => setSecuencia(e.target.value as Secuencia)}>
            {SECUENCIAS.map((s) => <option key={s.valor} value={s.valor}>{s.titulo}</option>)}
          </select>
        </label>
        <label className="crono-campo crono-ancho">
          <span>Feriados <small>(AAAA-MM-DD, separados por coma o espacio)</small></span>
          <input value={feriados} placeholder="2026-12-25, 2027-01-01" onChange={(e) => setFeriados(e.target.value)} />
        </label>
      </fieldset>

      <div className="crono-acciones">
        <button type="button" className="boton primario" disabled={ocupado} onClick={() => void calcular()}>
          {ocupado ? 'Calculando…' : 'Calcular cronograma'}
        </button>
        <button type="button" className="boton" disabled={ocupado} onClick={() => void descargarExcel()}>
          Descargar Excel con cronograma
        </button>
      </div>
      {error && <p className="mensaje error" role="alert">{error}</p>}

      {resultado && (
        <>
          {resultado.fecha_fin ? (
            <div className="crono-resumen">
              <div><span>Inicio</span><strong>{dmy(resultado.fecha_inicio)}</strong></div>
              <div><span>Fin</span><strong>{dmy(resultado.fecha_fin)}</strong></div>
              <div><span>Duración</span><strong>{resultado.dias_habiles} días hábiles</strong></div>
              <div><span>Actividades</span><strong>{resultado.actividades.length}</strong></div>
            </div>
          ) : (
            <p className="crono-nota">Todavía no hay actividades que programar.</p>
          )}
          {resultado.avisos.length > 0 && (
            <ul className="crono-avisos">
              {resultado.avisos.map((a, i) => <li key={i}>{a}</li>)}
            </ul>
          )}

          {resultado.actividades.length > 0 && (
            <>
              <p className="crono-leyenda" aria-hidden="true">
                <span><i className="crono-muestra critica" /> Ruta crítica (sin holgura)</span>
                <span><i className="crono-muestra" /> Con holgura</span>
              </p>
              <div className="crono-caja">
                <table className="crono-tabla">
                  <colgroup>
                    <col style={{ width: 40 }} /><col style={{ width: 220 }} /><col style={{ width: 88 }} />
                    <col style={{ width: 92 }} /><col style={{ width: 62 }} /><col style={{ width: 90 }} />
                    <col style={{ width: 90 }} /><col style={{ width: 78 }} /><col />
                  </colgroup>
                  <thead>
                    <tr>
                      <th className="c-num">N°</th>
                      <th className="c-act">Actividad</th>
                      <th className="c-der">Personas</th>
                      <th className="c-der">Horas-hombre</th>
                      <th className="c-der">Días háb.</th>
                      <th>Inicio</th>
                      <th>Fin</th>
                      <th className="c-der">Holgura</th>
                      <th className="c-gantt">
                        <div className="crono-escala" aria-hidden="true">
                          {escala.map((m) => <span key={m.clave} style={{ left: pct(m.izq) }}>{m.texto}</span>)}
                        </div>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {resultado.modulos.map((m) => {
                      const acts = resultado.actividades.filter((a) => a.modulo_id === m.id);
                      if (acts.length === 0) return null;
                      return (
                        <FilasModulo key={m.id}>
                          <tr className="crono-modulo">
                            <td colSpan={9}>
                              <div className="crono-modulo-info">
                                <strong>{m.codigo}</strong> <span>{m.nombre}</span>
                                <span className="tenue"> · {dmy(m.inicio)} – {dmy(m.fin)}</span>
                                <label className="crono-hito">
                                  Hito (fecha límite)
                                  <input type="date" defaultValue={m.hito ?? ''} onBlur={(e) => cambiarHito(m.id, e.target.value)} />
                                </label>
                                {m.atraso_dias > 0 && <span className="crono-chip mal">atraso: {m.atraso_dias} días hábiles</span>}
                                {m.hito && m.atraso_dias === 0 && <span className="crono-chip bien">cumple el hito</span>}
                              </div>
                            </td>
                          </tr>
                          {acts.map((a) => (
                            <tr key={a.item_id} title={a.nota || undefined}>
                              <td className="c-num">{a.numero}</td>
                              <td className="c-act">
                                {a.nombre}
                                {a.espera_dias > 0 && <span className="crono-chip espera"> espera {a.espera_dias} d</span>}
                              </td>
                              <td className="c-der">
                                <input className="crono-mini" inputMode="numeric" defaultValue={a.personas}
                                       aria-label={`Personas en ${a.nombre}`} key={`${a.item_id}-${a.personas}`}
                                       onBlur={(e) => cambiarPersonas(a.item_id, e.target.value)}
                                       onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur(); }} />
                              </td>
                              <td className="c-der">{a.horas_hombre}</td>
                              <td className="c-der">{a.duracion_dias}</td>
                              <td>{dmy(a.inicio)}</td>
                              <td>{dmy(a.fin)}</td>
                              <td className="c-der">
                                {a.critica ? <span className="crono-chip mal">crítica</span> : `${a.holgura_dias} d`}
                              </td>
                              <td className="c-gantt">
                                {/* La barra se posiciona dentro de esta pista (position: relative), nunca respecto de la página. */}
                                <div className="crono-pista">
                                  <div
                                    className={a.critica ? 'crono-barra critica' : 'crono-barra'}
                                    style={{
                                      left: pct((dias(resultado.fecha_inicio, a.inicio) / total) * 100),
                                      width: pct(Math.min(Math.max(((dias(a.inicio, a.fin) + 1) / total) * 100, 0.8),
                                                          100 - (dias(resultado.fecha_inicio, a.inicio) / total) * 100)),
                                    }}
                                    role="img"
                                    aria-label={`${a.nombre}: del ${dmy(a.inicio)} al ${dmy(a.fin)}`}
                                    title={`${dmy(a.inicio)} – ${dmy(a.fin)}`}
                                  />
                                </div>
                              </td>
                            </tr>
                          ))}
                        </FilasModulo>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {resultado.sin_programar.length > 0 && (
            <details className="crono-sin">
              <summary>{resultado.sin_programar.length} ítems sin programar</summary>
              <ul>
                {resultado.sin_programar.map((s) => (
                  <li key={s.item_id}><strong>Ítem {s.numero}</strong> {s.nombre} — <span className="tenue">{s.motivo}</span></li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}
    </div>
  );
}

/** Marcas de mes para la escala del diagrama: una por cada día 1 dentro del rango (más la fecha de inicio). */
function marcasDeMes(inicio: string, fin: string, total: number): { clave: string; texto: string; izq: number }[] {
  const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
  const marcas: { clave: string; texto: string; izq: number }[] = [];
  const [a, m] = inicio.split('-').map(Number);
  const ultimo = ms(fin);
  let anio = a;
  let mes = m - 1;
  let primera = true;
  for (let guardia = 0; guardia < 240; guardia++) {
    const iso = primera ? inicio : `${anio}-${String(mes + 1).padStart(2, '0')}-01`;
    if (ms(iso) > ultimo) break;
    const texto = `${MESES[mes]}${primera ? ` ${String(anio).slice(2)}` : ''}`;  // el año solo en la primera marca
    marcas.push({ clave: iso, texto, izq: (dias(inicio, iso) / total) * 100 });
    primera = false;
    mes += 1;
    if (mes > 11) { mes = 0; anio += 1; }
  }
  // si la marca del inicio y la del primer mes quedan casi encimadas, se deja la del mes
  if (marcas.length > 1 && marcas[1].izq - marcas[0].izq < 6) {
    marcas.shift();
    marcas[0].texto = `${marcas[0].texto} ${String(marcas[0].clave.slice(2, 4))}`;
  }
  return marcas;
}

/** Agrupa las filas de un módulo sin agregar elementos al DOM. */
function FilasModulo({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
