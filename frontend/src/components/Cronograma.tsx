import { useState, type ReactNode } from 'react';
import { api, descargar, mensajeDe, nombreArchivo } from '../api';
import type { CronogramaIn, CronogramaOut, ObjetivoCrono, ProyectoOut, Secuencia, TipoPlazo } from '../types';
import './cronograma.css';

const SECUENCIAS: { valor: Secuencia; titulo: string }[] = [
  { valor: 'modulos_en_serie', titulo: 'Un módulo tras otro (los ítems de cada módulo, en paralelo)' },
  { valor: 'todo_en_serie', titulo: 'Todos los ítems uno tras otro' },
  { valor: 'todo_en_paralelo', titulo: 'Todo en paralelo' },
  { valor: 'frentes_de_trabajo', titulo: 'Frentes de trabajo (cada frente hace sus ítems en orden)' },
];

const OBJETIVOS: { valor: ObjetivoCrono; titulo: string; ayuda: string }[] = [
  { valor: 'manual', titulo: 'Usar las personas indicadas', ayuda: 'No se cambia nada: la obra dura lo que salga con las personas de cada actividad.' },
  { valor: 'cumplir_plazo', titulo: 'Cumplir el plazo: calcular frentes, cuadrillas y personal',
    ayuda: 'Calcula la gente necesaria para entrar en el plazo. Si con la secuencia elegida no alcanza (p. ej. todo uno tras otro), abre frentes de trabajo en paralelo, el menor número posible, y da la cuadrilla de cada frente y el personal total.' },
  { valor: 'mas_rapido', titulo: 'Terminar lo más rápido posible',
    ayuda: 'Acelera la ruta crítica hasta el tope de personas por actividad. Es lo más corto posible, y lo que más gente pide.' },
  { valor: 'menor_costo', titulo: 'Menor costo total',
    ayuda: 'Suma personas mientras lo que se ahorra por terminar antes (gastos por día) supere lo que cuesta incorporarlas. Pide los dos costos de abajo.' },
];

const dmy = (s: string | null) => (s ? s.split('-').reverse().join('/') : '—');
const ms = (s: string) => Date.parse(`${s}T00:00:00Z`);
const dias = (a: string, b: string) => Math.round((ms(b) - ms(a)) / 86400000);
const hoy = () => new Date().toISOString().slice(0, 10);
const numero = (texto: string) => Number(texto.replace(',', '.'));

type Cambios = Partial<{
  personas: Record<number, number>; hitos: Record<number, string>; objetivo: ObjetivoCrono; secuencia: Secuencia; frentes: number;
}>;

const bs = (t: string) => Number(t).toLocaleString('es-BO', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export function Cronograma({ proyecto }: { proyecto: ProyectoOut }) {
  const [inicio, setInicio] = useState(hoy());
  const [horas, setHoras] = useState('8');
  const [personasDef, setPersonasDef] = useState('2');
  const [sabados, setSabados] = useState(false);
  const [secuencia, setSecuencia] = useState<Secuencia>('modulos_en_serie');
  const [feriados, setFeriados] = useState('');
  const [personas, setPersonas] = useState<Record<number, number>>({});
  const [hitos, setHitos] = useState<Record<number, string>>({});
  const [plazo, setPlazo] = useState('');
  const [tipoPlazo, setTipoPlazo] = useState<TipoPlazo>('calendario');
  const [objetivo, setObjetivo] = useState<ObjetivoCrono>('manual');
  const [maxPersonas, setMaxPersonas] = useState('30');
  const [abrirFrentes, setAbrirFrentes] = useState(true);
  const [maxFrentes, setMaxFrentes] = useState('');
  const [frentes, setFrentes] = useState('2');
  const [costoDia, setCostoDia] = useState('');
  const [costoPersona, setCostoPersona] = useState('');
  const [empresa, setEmpresa] = useState('');
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
    const obj = cambios?.objetivo ?? objetivo;
    const seq = cambios?.secuencia ?? secuencia;
    const nFrentes = cambios?.frentes ?? Math.floor(numero(frentes));
    if (seq === 'frentes_de_trabajo' && !(nFrentes >= 1)) throw new Error('El número de frentes debe ser al menos 1.');
    const topeFrentes = maxFrentes.trim() === '' ? null : Math.floor(numero(maxFrentes));
    if (topeFrentes !== null && !(topeFrentes >= 1)) throw new Error('El máximo de frentes debe ser 1 o más, o déjalo vacío.');
    const plazoNum = plazo.trim() === '' ? null : Number(plazo.replace(',', '.'));
    if (plazoNum !== null && !(Number.isInteger(plazoNum) && plazoNum >= 1)) throw new Error('El plazo máximo debe ser un número entero de días (1 o más), o déjalo vacío.');
    const tope = Math.floor(numero(maxPersonas));
    if (!(tope >= 1)) throw new Error('El tope de personas por actividad debe ser al menos 1.');
    const cDia = costoDia.trim() === '' ? 0 : numero(costoDia);
    const cPersona = costoPersona.trim() === '' ? 0 : numero(costoPersona);
    if (!(cDia >= 0) || !(cPersona >= 0)) throw new Error('Los costos deben ser números de 0 en adelante.');
    if (obj === 'cumplir_plazo' && plazoNum === null) throw new Error('Para «Cumplir el plazo» escribe el plazo máximo de la obra.');
    if (obj === 'menor_costo' && !(cDia > 0)) throw new Error('Para buscar el menor costo escribe el costo por día de obra (gastos generales diarios).');
    return {
      plazo_maximo: plazoNum,
      tipo_plazo: tipoPlazo,
      objetivo: obj,
      max_personas: tope,
      costo_indirecto_dia: cDia,
      costo_por_persona: cPersona,
      fecha_inicio: inicio,
      horas_jornada: h,
      personas_por_defecto: p,
      trabaja_sabados: sabados,
      feriados: feriados.split(/[\s,;]+/).filter((t) => /^\d{4}-\d{2}-\d{2}$/.test(t)),
      secuencia: seq,
      frentes: nFrentes >= 1 ? nFrentes : 1,
      abrir_frentes: abrirFrentes,
      max_frentes: topeFrentes,
      personas: cambios?.personas ?? personas,
      hitos: Object.fromEntries(Object.entries(hitosUsados).filter(([, f]) => f)) as Record<number, string>,
    };
  }

  async function calcular(cambios?: Cambios) {
    try {
      setError('');
      setOcupado(true);
      const nuevo = await api.cronograma(proyecto.id, cuerpo(cambios));
      if (cambios?.objetivo) setObjetivo(cambios.objetivo);
      if (cambios?.secuencia) setSecuencia(cambios.secuencia);
      if (cambios?.frentes) setFrentes(String(cambios.frentes));
      setResultado(nuevo);
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

  async function abrirPdf() {
    try {
      setError('');
      setOcupado(true);
      await api.abrirPdfCronograma(proyecto.id, { ...cuerpo(), empresa: empresa.trim() || null });
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

  const conCostos = numero(costoDia || '0') > 0 || numero(costoPersona || '0') > 0;
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
        {secuencia === 'frentes_de_trabajo' && (
          <label className="crono-campo">
            <span>Número de frentes</span>
            <input inputMode="numeric" value={frentes} onChange={(e) => setFrentes(e.target.value)} />
          </label>
        )}
        <label className="crono-campo crono-ancho">
          <span>Feriados <small>(AAAA-MM-DD, separados por coma o espacio)</small></span>
          <input value={feriados} placeholder="2026-12-25, 2027-01-01" onChange={(e) => setFeriados(e.target.value)} />
        </label>
      </fieldset>

      <fieldset className="crono-params" disabled={ocupado}>
        <legend>Plazo y tiempo óptimo</legend>
        <label className="crono-campo">
          <span>Plazo máximo de la obra <small>(días, opcional)</small></span>
          <input inputMode="numeric" value={plazo} placeholder="Ej.: 90" onChange={(e) => setPlazo(e.target.value)} />
        </label>
        <label className="crono-campo">
          <span>Los días del plazo son</span>
          <select value={tipoPlazo} onChange={(e) => setTipoPlazo(e.target.value as TipoPlazo)}>
            <option value="calendario">Días calendario (corridos)</option>
            <option value="habiles">Días hábiles (de trabajo)</option>
          </select>
        </label>
        <label className="crono-campo">
          <span>Máx. personas por actividad</span>
          <input inputMode="numeric" value={maxPersonas} onChange={(e) => setMaxPersonas(e.target.value)} />
        </label>
        <label className="crono-campo crono-ancho">
          <span>Objetivo</span>
          <select value={objetivo} onChange={(e) => setObjetivo(e.target.value as ObjetivoCrono)}>
            {OBJETIVOS.map((o) => <option key={o.valor} value={o.valor}>{o.titulo}</option>)}
          </select>
        </label>
        <label className="crono-campo crono-check">
          <input type="checkbox" checked={abrirFrentes} onChange={(e) => setAbrirFrentes(e.target.checked)} />
          <span>Abrir frentes en paralelo si hace falta</span>
        </label>
        <label className="crono-campo">
          <span>Máx. frentes <small>(opcional)</small></span>
          <input inputMode="numeric" value={maxFrentes} placeholder="Sin límite" onChange={(e) => setMaxFrentes(e.target.value)} />
        </label>
        <p className="crono-ayuda crono-ancho-total">{OBJETIVOS.find((o) => o.valor === objetivo)?.ayuda}</p>
        <label className="crono-campo">
          <span>Costo por día de obra <small>(Bs, gastos generales)</small></span>
          <input inputMode="decimal" value={costoDia} placeholder="Ej.: 1500" onChange={(e) => setCostoDia(e.target.value)} />
        </label>
        <label className="crono-campo">
          <span>Costo por persona adicional <small>(Bs, opcional)</small></span>
          <input inputMode="decimal" value={costoPersona} placeholder="Ej.: 300" onChange={(e) => setCostoPersona(e.target.value)} />
        </label>
        <label className="crono-campo crono-ancho">
          <span>Contratista <small>(se imprime en el PDF)</small></span>
          <input value={empresa} placeholder="Nombre de tu empresa" onChange={(e) => setEmpresa(e.target.value)} />
        </label>
      </fieldset>

      <div className="crono-acciones">
        <button type="button" className="boton primario" disabled={ocupado} onClick={() => void calcular()}>
          {ocupado ? 'Calculando…' : 'Calcular cronograma'}
        </button>
        <button type="button" className="boton" disabled={ocupado} onClick={() => void descargarExcel()}>
          Descargar Excel con cronograma
        </button>
        <button type="button" className="boton" disabled={ocupado} onClick={() => void abrirPdf()}>
          Abrir PDF (diseño Project)
        </button>
      </div>
      {error && <p className="mensaje error" role="alert">{error}</p>}

      {resultado && (
        <>
          {resultado.fecha_fin ? (
            <div className="crono-resumen">
              <div><span>Inicio</span><strong>{dmy(resultado.fecha_inicio)}</strong></div>
              <div><span>Fin</span><strong>{dmy(resultado.fecha_fin)}</strong></div>
              <div><span>Duración</span><strong>{resultado.dias_calendario} días calendario</strong><small>{resultado.dias_habiles} días hábiles</small></div>
              {resultado.frentes > 0 && (
                <div><span>Personal necesario</span><strong>{resultado.personal_total} personas</strong>
                  <small>{resultado.frentes} {resultado.frentes === 1 ? 'frente' : 'frentes'}</small></div>
              )}
              <div><span>Personas a la vez (máx.)</span><strong>{resultado.pico_personas}</strong></div>
              <div><span>Actividades</span><strong>{resultado.actividades.length}</strong></div>
              {resultado.plazo_maximo !== null && resultado.cumple_plazo !== null && (
                <div className={resultado.cumple_plazo ? 'crono-plazo bien' : 'crono-plazo mal'}>
                  <span>Plazo máximo</span>
                  <strong>{resultado.cumple_plazo ? 'Cumple' : 'No cumple'}</strong>
                  <small>{resultado.plazo_maximo} {resultado.tipo_plazo === 'habiles' ? 'días hábiles' : 'días calendario'}</small>
                </div>
              )}
            </div>
          ) : (
            <p className="crono-nota">Todavía no hay actividades que programar.</p>
          )}
          {resultado.frentes_detalle.length > 0 && (
            <div className="crono-opciones">
              <h3>Frentes y cuadrillas{resultado.frentes_abiertos ? ' (frentes abiertos para cumplir el plazo)' : ''}</h3>
              <div className="crono-caja-chica">
                <table className="crono-tabla-opc">
                  <thead>
                    <tr>
                      <th>Frente</th><th className="c-der">Cuadrilla (personas)</th><th className="c-der">Ítems</th><th>N° de ítems, en orden</th>
                      <th className="c-der">Horas-hombre</th><th className="c-der">Días hábiles</th><th>Inicio</th><th>Fin</th>
                    </tr>
                  </thead>
                  <tbody>
                    {resultado.frentes_detalle.map((f) => (
                      <tr key={f.frente}>
                        <td><strong>F{f.frente}</strong></td>
                        <td className="c-der">{f.personas}</td>
                        <td className="c-der">{f.actividades}</td>
                        <td className="crono-lista-num">{f.numeros.join(', ')}</td>
                        <td className="c-der">{Number(f.horas_hombre).toLocaleString('es-BO', { maximumFractionDigits: 0 })}</td>
                        <td className="c-der">{f.dias_habiles}</td>
                        <td>{dmy(f.inicio)}</td>
                        <td>{dmy(f.fin)}</td>
                      </tr>
                    ))}
                    <tr className="sel">
                      <td>Total</td><td className="c-der">{resultado.personal_total}</td>
                      <td className="c-der">{resultado.actividades.length}</td><td colSpan={5}>personas a contratar (una cuadrilla por frente)</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <p className="crono-ayuda">Cada frente hace sus ítems uno tras otro; los frentes trabajan a la vez. Revisa que no haya dependencias técnicas entre ítems de frentes distintos.</p>
            </div>
          )}
          {resultado.alternativas_frentes.length > 1 && (
            <div className="crono-opciones">
              <h3>Alternativas de frentes para el mismo plazo</h3>
              <div className="crono-caja-chica">
                <table className="crono-tabla-opc">
                  <thead>
                    <tr><th className="c-der">Frentes</th><th className="c-der">Personal necesario</th><th className="c-der">Días calendario</th><th>Fin</th><th /></tr>
                  </thead>
                  <tbody>
                    {resultado.alternativas_frentes.map((a) => (
                      <tr key={a.frentes} className={a.seleccionado || (!resultado.alternativas_frentes.some((x) => x.seleccionado) && a.frentes === resultado.frentes) ? 'sel' : undefined}>
                        <td className="c-der">{a.frentes}</td>
                        <td className="c-der">{a.personal_total}</td>
                        <td className="c-der">{a.dias_calendario}</td>
                        <td>{dmy(a.fecha_fin)}</td>
                        <td className="c-der">
                          {a.frentes === resultado.frentes
                            ? <span className="tenue">en uso</span>
                            : <button type="button" className="boton" disabled={ocupado}
                                      onClick={() => void calcular({ objetivo: 'cumplir_plazo', secuencia: 'frentes_de_trabajo', frentes: a.frentes })}>Usar</button>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="crono-ayuda">Más frentes suele pedir menos personal en total, pero hay que dirigir más frentes a la vez.</p>
            </div>
          )}
          {resultado.escenarios.length > 1 && (
            <div className="crono-opciones">
              <h3>Opciones de tiempo{conCostos ? ' y costo' : ''}</h3>
              <div className="crono-caja-chica">
                <table className="crono-tabla-opc">
                  <thead>
                    <tr>
                      <th>Opción</th><th className="c-der">Días calendario</th><th className="c-der">Días hábiles</th><th>Fin</th>
                      <th className="c-der">Personas a la vez</th><th className="c-der">Personal necesario</th>
                      {conCostos && <th className="c-der">Costo plazo + personas (Bs)</th>}
                      {resultado.plazo_maximo !== null && <th>Plazo</th>}
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {resultado.escenarios.map((e) => (
                      <tr key={e.clave} className={e.seleccionado ? 'sel' : undefined}>
                        <td>{e.titulo}</td>
                        <td className="c-der">{e.dias_calendario}</td>
                        <td className="c-der">{e.dias_habiles}</td>
                        <td>{dmy(e.fecha_fin)}</td>
                        <td className="c-der">{e.pico_personas}</td>
                        <td className="c-der">{e.personal_total}</td>
                        {conCostos && <td className="c-der">{bs(e.costo_total)}</td>}
                        {resultado.plazo_maximo !== null && (
                          <td>{e.cumple_plazo === null ? '—' : e.cumple_plazo ? <span className="crono-chip bien">cumple</span> : <span className="crono-chip mal">no cumple</span>}</td>
                        )}
                        <td className="c-der">
                          {e.seleccionado
                            ? <span className="tenue">en uso</span>
                            : <button type="button" className="boton" disabled={ocupado} onClick={() => void calcular({ objetivo: e.clave })}>Usar</button>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
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
                                {resultado.frentes > 1 && a.frente > 0 && <span className="crono-chip frente"> F{a.frente}</span>}
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
