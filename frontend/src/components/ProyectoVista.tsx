import { Fragment, useMemo, useRef, useState } from 'react';
import { api, descargar, mensajeDe, nombreArchivo } from '../api';
import type { BibliotecaOut, ModoRecursos, ProyectoOut, ModeloCostos } from '../types';
import { CeldaPrecio } from './CeldaPrecio';
import { ModeloProyecto } from './ModeloProyecto';
import { Cronograma } from './Cronograma';
import { DetalleItem } from './DetalleItem';
import { HojaB2Modal } from './HojaB2Modal';
import './hojab2.css';
import { DescargasFormularios } from './DescargasFormularios';

const TIPO_RECURSO = { material: 'Material', mano_obra: 'Mano de obra', equipo: 'Equipo' } as const;

const formato = new Intl.NumberFormat('es-BO', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const bs = (v: string | null) => (v == null ? '—' : formato.format(Number(v)));
type Pestana = 'presupuesto' | 'apu' | 'precios' | 'calculo' | 'cronograma' | 'avisos';
const ROTULO = { error: 'Error', advertencia: 'Advertencia', info: 'Información' } as const;
const ORIGEN_ALERTA = { b1: '', especificaciones: ' (especificaciones)', apu: ' (APU)' } as const;
const MODOS: { valor: ModoRecursos; titulo: string; ayuda: string }[] = [
  { valor: 'hibrido', titulo: 'Híbrido', ayuda: 'Los recursos de tu APU más lo que el pliego pide y falta.' },
  { valor: 'biblioteca', titulo: 'Solo mi biblioteca', ayuda: 'Tu APU tal cual; te aviso si falta algo del pliego.' },
  { valor: 'pliego', titulo: 'Solo el pliego', ayuda: 'Únicamente los recursos que pide la especificación.' },
];

interface Props {
  proyecto: ProyectoOut;
  bibliotecas: BibliotecaOut[];
  modelos: ModeloCostos[];
  onModelosCambiaron: () => void;
  onActualizar: (p: ProyectoOut) => void;
  onBorrar: () => void;
}

export function ProyectoVista({ proyecto, bibliotecas, modelos, onModelosCambiaron, onActualizar, onBorrar }: Props) {
  const [pestana, setPestana] = useState<Pestana>('presupuesto');
  const [busqueda, setBusqueda] = useState('');
  const [cerrados, setCerrados] = useState<Set<number>>(new Set());
  const [abiertos, setAbiertos] = useState<Set<number>>(new Set());
  const [hojaItem, setHojaItem] = useState<number | null>(null);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [ocupado, setOcupado] = useState(false);
  const [modo, setModo] = useState<ModoRecursos>(proyecto.modo_recursos);
  const [bibliotecaSel, setBibliotecaSel] = useState<number | 'todas'>('todas');
  const entradaEsp = useRef<HTMLInputElement>(null);

  const bibliotecaIds = bibliotecaSel === 'todas' ? bibliotecas.map((b) => b.id) : [bibliotecaSel];

  // Las alertas de nivel "información" no marcan la fila; las demás sí.
  const avisosPorItem = useMemo(() => {
    const m = new Map<number, { texto: string; error: boolean }[]>();
    for (const a of proyecto.alertas) {
      if (a.item_numero == null || a.nivel === 'info') continue;
      m.set(a.item_numero, [...(m.get(a.item_numero) ?? []), { texto: a.mensaje, error: a.nivel === 'error' }]);
    }
    return m;
  }, [proyecto.alertas]);

  async function ejecutar(accion: () => Promise<void>) {
    try {
      setError('');
      setInfo('');
      setOcupado(true);
      await accion();
    } catch (e) {
      setError(mensajeDe(e));
    } finally {
      setOcupado(false);
    }
  }

  async function fijarPrecio(itemId: number, valor: string | null) {
    try {
      setError('');
      onActualizar(await api.fijarPrecio(itemId, valor));
    } catch (e) {
      setError(mensajeDe(e));
      throw e;
    }
  }

  async function fijarPrecioRecurso(clave: string, valor: string | null) {
    try {
      setError('');
      onActualizar(await api.fijarPrecioRecurso(proyecto.id, clave, valor));
    } catch (e) {
      setError(mensajeDe(e));
      throw e;
    }
  }

  const descargarExcel = () =>
    ejecutar(async () => {
      descargar(await api.exportar(proyecto.id, null), nombreArchivo(`presupuesto-${proyecto.nombre}`, 'xlsx'));
    });

  const subirEspecificaciones = (archivo: File) =>
    ejecutar(async () => onActualizar(await api.importarEspecificaciones(proyecto.id, archivo)));

  const vincularAuto = () =>
    ejecutar(async () => {
      const r = await api.vincularAuto(proyecto.id, { modo, biblioteca_ids: bibliotecaIds.length ? bibliotecaIds : null });
      onActualizar(r.proyecto);
      setInfo(
        `Vinculados con confianza alta: ${r.vinculados}` +
          (r.solo_pliego ? ` · solo con el pliego: ${r.solo_pliego}` : '') +
          ` · por revisar: ${r.por_revisar} · sin candidato: ${r.sin_candidato}.`,
      );
    });

  function alternar(conjunto: Set<number>, poner: (s: Set<number>) => void, id: number) {
    const nuevo = new Set(conjunto);
    if (!nuevo.delete(id)) nuevo.add(id);
    poner(nuevo);
  }

  const q = busqueda.trim().toLowerCase();
  const total = proyecto.total_items;
  const sinPrecioRec = proyecto.recursos.filter((r) => r.estado !== 'completo').length;
  const avisos = proyecto.alertas.filter((a) => a.nivel !== 'info');
  const hayError = avisos.some((a) => a.nivel === 'error');

  const pasos: { titulo: string; detalle: string; hecho: boolean; ir: () => void }[] = [
    { titulo: 'Importar el B-1', detalle: `${total} ítems`, hecho: true, ir: () => setPestana('presupuesto') },
    { titulo: 'Especificaciones', detalle: `${proyecto.items_con_especificacion} de ${total}`, hecho: proyecto.items_con_especificacion > 0, ir: () => setPestana('apu') },
    { titulo: 'Vincular APU', detalle: `${proyecto.items_con_apu} de ${total}`, hecho: total > 0 && proyecto.items_con_apu === total, ir: () => setPestana('apu') },
    { titulo: 'Completar precios', detalle: `${proyecto.items_con_precio} de ${total}`, hecho: total > 0 && proyecto.items_con_precio === total, ir: () => setPestana('precios') },
    { titulo: 'Descargar Excel', detalle: 'Presupuesto final', hecho: false, ir: () => void descargarExcel() },
  ];
  const actual = pasos.findIndex((p) => !p.hecho);

  const PESTANAS: { id: Pestana; titulo: string; insignia?: number }[] = [
    { id: 'presupuesto', titulo: 'Presupuesto' },
    { id: 'apu', titulo: 'Armar APU' },
    { id: 'precios', titulo: 'Precios', insignia: sinPrecioRec || undefined },
    { id: 'calculo', titulo: 'Cálculo' },
    { id: 'cronograma', titulo: 'Cronograma' },
    { id: 'avisos', titulo: 'Avisos', insignia: avisos.length || undefined },
  ];

  return (
    <section>
      <header className="cabecera">
        <div>
          <h2>{proyecto.nombre}</h2>
          <p className="tenue">
            {total} ítems en {proyecto.modulos.length} módulos{proyecto.archivo_b1 ? ` · ${proyecto.archivo_b1}` : ''}
          </p>
        </div>
        <div className="cabecera-der">
          <div className="acciones">
            <DescargasFormularios proyecto={proyecto} />
            <button type="button" className="boton peligro" onClick={onBorrar}>Eliminar</button>
          </div>
          <div className="total-proyecto">
            <span className="tenue">Total del proyecto</span>
            <strong>Bs {bs(proyecto.total)}</strong>
          </div>
        </div>
      </header>

      <ol className="pasos" aria-label="Avance del presupuesto">
        {pasos.map((p, i) => (
          <li key={p.titulo}>
            <button type="button" className={`paso${p.hecho ? ' hecho' : ''}${i === actual ? ' actual' : ''}`}
                    aria-current={i === actual ? 'step' : undefined} onClick={p.ir}>
              <span className="n" aria-hidden="true">{p.hecho ? '✓' : i + 1}</span>
              <strong>{p.titulo}</strong>
              <span className="tenue">{p.detalle}</span>
            </button>
          </li>
        ))}
      </ol>

      {error && <p className="mensaje error" role="alert">{error}</p>}
      {info && <p className="mensaje" role="status">{info}</p>}

      <div className="pestanas" role="tablist" aria-label="Secciones del proyecto">
        {PESTANAS.map((t) => (
          <button key={t.id} type="button" role="tab" aria-selected={pestana === t.id}
                  className={pestana === t.id ? 'pestana activa' : 'pestana'} onClick={() => setPestana(t.id)}>
            {t.titulo}
            {t.insignia !== undefined && <span className={t.id === 'avisos' && hayError ? 'insignia error' : 'insignia'}>{t.insignia}</span>}
          </button>
        ))}
      </div>

      {pestana === 'presupuesto' && (
        <>
          {avisos.length > 0 && (
            <p className="resumen-avisos" role="status">
              Hay {avisos.length} {avisos.length === 1 ? 'aviso' : 'avisos'} de la lectura de los PDF; los ítems afectados están marcados con una barra de color.{' '}
              <button type="button" onClick={() => setPestana('avisos')}>Ver avisos</button>
            </p>
          )}
          <div className="barra">
            <input type="search" value={busqueda} onChange={(e) => setBusqueda(e.target.value)}
                   placeholder="Buscar por número o descripción" aria-label="Buscar ítems" />
            <span className="tenue">Escribe el precio unitario directo en la columna «Precio unitario»; con APU se calcula solo.</span>
          </div>
          <div className="tabla-caja">
            <table>
              <thead>
                <tr>
                  <th className="num">N°</th><th>Descripción</th><th>Unidad</th>
                  <th className="num">Cantidad</th><th className="num">Precio unitario</th><th className="num">Total (Bs)</th>
                </tr>
              </thead>
              <tbody>
                {proyecto.modulos.map((m) => {
                  const items = m.items.filter((it) => !q || String(it.numero) === q || it.descripcion.toLowerCase().includes(q));
                  if (q && items.length === 0) return null;
                  const cerrado = !q && cerrados.has(m.id);
                  return (
                    <Fragment key={m.id}>
                      <tr className="modulo">
                        <td colSpan={6}>
                          <button type="button" aria-expanded={!cerrado} onClick={() => alternar(cerrados, setCerrados, m.id)}>
                            <span>{cerrado ? '▸' : '▾'} {m.codigo || '—'}</span>
                            <span>{m.nombre}</span>
                            <span className="resumen-modulo">{m.items_con_precio}/{m.items.length} con precio · Bs {bs(m.total)}</span>
                          </button>
                        </td>
                      </tr>
                      {!cerrado && items.map((it) => {
                        const av = avisosPorItem.get(it.numero);
                        const clase = av ? (av.some((a) => a.error) ? 'marcado error' : 'marcado') : '';
                        const abierto = abiertos.has(it.id);
                        return (
                          <Fragment key={it.id}>
                            <tr className={clase} title={av?.map((a) => a.texto).join('\n')}>
                              <td className="num tenue">{it.numero}</td>
                              <td>
                                {it.descripcion}
                                {it.apu && (
                                  <span className={`chip ${it.apu.estado}`}>APU {it.apu.estado}
                                    {it.vinculo_confianza && !it.vinculo_confirmado ? ` · auto (${it.vinculo_confianza})` : ''}
                                  </span>
                                )}
                                {' '}
                                <button type="button" className="enlace" aria-expanded={abierto} onClick={() => alternar(abiertos, setAbiertos, it.id)}>
                                  {abierto ? 'Ocultar' : 'Ver'} detalle
                                  {it.tiene_especificacion ? ` (${it.requisitos.length} ${it.requisitos.length === 1 ? 'recurso' : 'recursos'} del pliego)` : ''}
                                </button>
                                {it.apu && it.apu.lineas.length > 0 && (
                                  <button type="button" className="boton-hoja" title="Ver el análisis de precio unitario de este ítem (Formulario B-2)"
                                          onClick={() => setHojaItem(it.id)}>Hoja B-2</button>
                                )}
                                {hojaItem === it.id && <HojaB2Modal itemId={it.id} onCerrar={() => setHojaItem(null)} />}
                              </td>
                              <td title={it.unidad !== it.unidad_normalizada ? `Se compara como: ${it.unidad_normalizada}` : undefined}>{it.unidad}</td>
                              <td className="num">{it.cantidad_texto}</td>
                              <td className="num">
                                {it.modo_precio === 'apu' ? (
                                  <span title={it.precio_unitario == null ? 'El APU tiene líneas pendientes' : 'Calculado con el APU'}>{bs(it.precio_unitario)}</span>
                                ) : (
                                  <CeldaPrecio valor={it.precio_unitario} onGuardar={(v) => fijarPrecio(it.id, v)} />
                                )}
                              </td>
                              <td className="num">{bs(it.total)}</td>
                            </tr>
                            {abierto && (
                              <tr className="detalle">
                                <td colSpan={6}>
                                  <DetalleItem item={it} modo={modo} bibliotecaIds={bibliotecaIds} onActualizar={onActualizar} />
                                </td>
                              </tr>
                            )}
                          </Fragment>
                        );
                      })}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      {pestana === 'apu' && (
        <div className="dos-columnas">
          <section className="panel">
            <h3>1. Especificaciones del pliego</h3>
            <p className="tenue nota">
              Se asignan a cada ítem por su número. Dicen qué recursos pide el pliego, no cuánto; las cantidades quedan pendientes.
              {proyecto.items_con_especificacion > 0 && ` Ya hay ${proyecto.items_con_especificacion} de ${total} ítems con especificación.`}
            </p>
            <button type="button" className="boton" disabled={ocupado} onClick={() => entradaEsp.current?.click()}>
              {proyecto.items_con_especificacion ? 'Reemplazar especificaciones (PDF)' : 'Importar especificaciones (PDF)'}
            </button>
            <input ref={entradaEsp} type="file" accept="application/pdf,.pdf" hidden
                   onChange={(e) => { const f = e.target.files?.[0]; if (f) void subirEspecificaciones(f); e.target.value = ''; }} />
          </section>
          <fieldset className="panel-vinculo" disabled={ocupado}>
            <legend>2. Vincular con tu biblioteca</legend>
            <div className="modos" role="radiogroup" aria-label="Recursos del APU">
              {MODOS.map((m) => (
                <label key={m.valor} className={modo === m.valor ? 'modo activo' : 'modo'}>
                  <input type="radio" name="modo" value={m.valor} checked={modo === m.valor} onChange={() => setModo(m.valor)} />
                  <span><strong>{m.titulo}</strong><span className="tenue">{m.ayuda}</span></span>
                </label>
              ))}
            </div>
            <div className="acciones">
              <label className="campo">Biblioteca
                <select value={bibliotecaSel} onChange={(e) => setBibliotecaSel(e.target.value === 'todas' ? 'todas' : Number(e.target.value))}>
                  <option value="todas">Todas</option>
                  {bibliotecas.map((b) => <option key={b.id} value={b.id}>{b.nombre}</option>)}
                </select>
              </label>
              <button type="button" className="boton primario" onClick={() => void vincularAuto()} disabled={modo !== 'pliego' && bibliotecas.length === 0}>
                Vincular automáticamente
              </button>
            </div>
            <p className="tenue nota">
              Solo se aplican las coincidencias de confianza alta con la misma unidad del B-1. El resto lo eliges ítem por ítem en
              «Ver detalle» de la pestaña Presupuesto. Un APU con líneas pendientes no da precio hasta completarse.
              {bibliotecas.length === 0 && modo !== 'pliego' && ' Aún no tienes bibliotecas: créalas o impórtalas en el menú Bibliotecas.'}
            </p>
          </fieldset>
        </div>
      )}

      {pestana === 'precios' && (
        proyecto.recursos.length === 0 ? (
          <p className="tenue">Aún no hay recursos. Vincula los APU primero (pestaña «Armar APU») y aquí podrás ponerles precio.</p>
        ) : (
          <section className="panel">
            <h3>Precios de los recursos ({proyecto.recursos.length}{sinPrecioRec ? ` · ${sinPrecioRec} sin precio completo` : ''})</h3>
            <p className="tenue nota">
              Cada recurso se usa en varios ítems. Escribe su precio una sola vez (sin IVA) y se aplica en todos los APU del proyecto donde aparezca.
            </p>
            <div className="tabla-caja">
              <table className="tabla-apu">
                <thead>
                  <tr><th>Tipo</th><th>Recurso</th><th>Unidad</th><th className="num">Usado en</th><th className="num">Precio (Bs)</th></tr>
                </thead>
                <tbody>
                  {proyecto.recursos.map((r) => (
                    <tr key={r.clave} className={r.estado === 'completo' ? '' : 'pendiente'}>
                      <td>{TIPO_RECURSO[r.tipo]}</td>
                      <td>{r.nombre}</td>
                      <td>{r.unidad || '—'}</td>
                      <td className="num">{r.usos} {r.usos === 1 ? 'ítem' : 'ítems'}</td>
                      <td className="num">
                        <CeldaPrecio valor={r.precio} grupo="recurso" ancho={104} etiqueta={`Precio de ${r.nombre}`}
                                     onGuardar={(v) => fijarPrecioRecurso(r.clave, v)} />
                        {r.estado === 'varios' && <div className="tenue">precios distintos o incompletos</div>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )
      )}

      {pestana === 'calculo' && (
        <>
          <p className="tenue nota">
            Define cómo se pasa del costo directo al precio unitario. Es una copia para este proyecto: cambiarla no altera los
            modelos base ni tus perfiles. Los precios se recalculan al guardar.
          </p>
          <ModeloProyecto proyecto={proyecto} modelos={modelos} onActualizar={onActualizar} onModelosCambiaron={onModelosCambiaron} />
        </>
      )}

      {pestana === 'cronograma' && <Cronograma proyecto={proyecto} />}

      {pestana === 'avisos' && (
        <ul className="alertas">
          {proyecto.alertas.length === 0 ? (
            <li><b className="ok">Sin avisos.</b> Las dos lecturas del PDF coinciden.</li>
          ) : (
            proyecto.alertas.map((a) => (
              <li key={a.id} className={a.nivel}>
                <b>{ROTULO[a.nivel]}{ORIGEN_ALERTA[a.origen]}:</b> {a.mensaje}
              </li>
            ))
          )}
        </ul>
      )}
    </section>
  );
}
