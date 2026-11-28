import { useEffect, useState } from 'react';
import { abrirPdf, api, mensajeDe } from '../api';
import type { HojaB2Out } from '../types';
import './hojab2.css';

const num = (v: string | null | undefined, dec = 2) =>
  v == null ? '—' : new Intl.NumberFormat('es-BO', { minimumFractionDigits: dec, maximumFractionDigits: dec }).format(Number(v));

const TIPOS = { material: 'Materiales', mano_obra: 'Mano de obra', equipo: 'Equipo' } as const;

/** Ventana con la hoja unitaria del ítem, como el Formulario B-2. Los números vienen calculados del servidor. */
export function HojaB2Modal({ itemId, onCerrar }: { itemId: number; onCerrar: () => void }) {
  const [hoja, setHoja] = useState<HojaB2Out | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let vivo = true;
    api.hojaB2(itemId).then((h) => vivo && setHoja(h)).catch((e) => vivo && setError(mensajeDe(e)));
    return () => { vivo = false; };
  }, [itemId]);

  useEffect(() => {
    const tecla = (e: KeyboardEvent) => { if (e.key === 'Escape') onCerrar(); };
    document.addEventListener('keydown', tecla);
    const antes = document.body.style.overflow;
    document.body.style.overflow = 'hidden';  // el fondo no se desplaza mientras la hoja está abierta
    return () => { document.removeEventListener('keydown', tecla); document.body.style.overflow = antes; };
  }, [onCerrar]);

  const dec = hoja?.modelo.decimales ?? 2;

  return (
    <div className="b2-fondo" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) onCerrar(); }}>
      <div className="b2-ventana" role="dialog" aria-modal="true" aria-label="Hoja B-2 del ítem">
        <header className="b2-barra">
          <div className="b2-titulo">
            <span className="b2-etiqueta">Formulario B-2 · Análisis de precio unitario</span>
            <strong title={hoja?.item.descripcion}>{hoja ? `${hoja.item.numero}. ${hoja.item.descripcion}` : 'Cargando…'}</strong>
          </div>
          <div className="b2-acciones">
            <button type="button" className="boton primario" onClick={() => abrirPdf(api.rutaPdfItem(itemId))}>Abrir PDF</button>
            <button type="button" className="boton" onClick={onCerrar}>Cerrar ✕</button>
          </div>
        </header>

        <div className="b2-cuerpo">
          {error && <p className="mensaje error" role="alert">{error}</p>}
          {!hoja && !error && <p className="tenue b2-cargando">Calculando la hoja…</p>}

          {hoja && (
            <>
              <div className="b2-resumen">
                {(['material', 'mano_obra', 'equipo'] as const).map((t) => (
                  <div key={t} className={`b2-dato ${t}`}>
                    <span>{TIPOS[t]}</span>
                    <strong>Bs {num(hoja.subtotal_por_tipo[t])}</strong>
                  </div>
                ))}
                <div className="b2-dato precio">
                  <span>Precio unitario por {hoja.item.unidad}</span>
                  <strong>{hoja.precio_adoptado != null ? `Bs ${num(hoja.precio_adoptado, dec)}` : 'Pendiente'}</strong>
                </div>
              </div>

              <div className="b2-hoja">
                <div className="b2-encabezado">
                  <span>FORMULARIO B-2</span>
                  <span>ANÁLISIS DE PRECIOS UNITARIOS</span>
                </div>

                <table className="b2-generales">
                  <tbody>
                    <tr><th>Proyecto</th><td>{hoja.proyecto}</td></tr>
                    <tr><th>Actividad</th><td>{hoja.item.numero}. {hoja.item.descripcion}</td></tr>
                    <tr><th>Cantidad</th><td>{hoja.item.cantidad_texto || num(hoja.item.cantidad)}</td></tr>
                    <tr><th>Unidad</th><td>{hoja.item.unidad}</td></tr>
                    <tr><th>Moneda</th><td>Bolivianos</td></tr>
                    <tr><th>Cálculo</th><td>{hoja.modelo.nombre} <span className="tenue">· precio con {hoja.modelo.decimales} decimales</span></td></tr>
                  </tbody>
                </table>

                {hoja.tiene_apu && !hoja.completo && (
                  <p className="mensaje aviso">
                    {hoja.pendientes === 1 ? 'Falta 1 línea' : `Faltan ${hoja.pendientes} líneas`} sin cantidad o precio (—). Los cargos y el precio se calculan cuando el análisis esté completo.
                  </p>
                )}

                {hoja.secciones.map((s) => (
                  <table key={s.codigo} className={`b2-seccion tipo-${s.tipo_recurso ?? 'otro'}`}>
                    <colgroup><col className="c-n" /><col /><col className="c-u" /><col className="c-c" /><col className="c-p" /><col className="c-t" /></colgroup>
                    <thead>
                      <tr className="b2-banda"><th colSpan={6}>{s.numero}. {s.titulo}</th></tr>
                      {s.tipo_recurso && (
                        <tr className="b2-cab">
                          <th>N°</th><th>Descripción</th><th>Unidad</th><th className="num">Cantidad</th>
                          <th className="num">Precio productivo</th><th className="num">Costo total</th>
                        </tr>
                      )}
                    </thead>
                    <tbody>
                      {s.tipo_recurso && s.lineas.length === 0 && (
                        <tr><td colSpan={6} className="tenue">(sin recursos de este tipo)</td></tr>
                      )}
                      {s.lineas.map((l) => (
                        <tr key={l.n} className={l.costo == null ? 'pendiente' : ''}>
                          <td>{l.n}</td><td>{l.descripcion}</td><td>{l.unidad}</td>
                          <td className="num">{num(l.cantidad, 4)}</td>
                          <td className="num">{num(l.precio_unitario)}</td>
                          <td className="num">{num(l.costo)}</td>
                        </tr>
                      ))}
                      {s.tipo_recurso === 'mano_obra' && s.pasos.length > 0 && (
                        <tr className="b2-sub"><td colSpan={5}>SUBTOTAL {s.titulo}</td><td className="num">{num(s.subtotal_directo)}</td></tr>
                      )}
                      {s.pasos.map((q) => (
                        <tr key={q.codigo} className="b2-paso">
                          <td>*</td>
                          <td colSpan={4}>
                            {q.etiqueta}
                            {q.base_valor != null && <span className="tenue"> — {num(q.porcentaje)} % de Bs {num(q.base_valor)}</span>}
                          </td>
                          <td className="num">{num(q.importe)}</td>
                        </tr>
                      ))}
                      <tr className="b2-total"><td colSpan={5}>{s.etiqueta_total}</td><td className="num">{num(s.total)}</td></tr>
                    </tbody>
                  </table>
                ))}

                <table className="b2-cierre">
                  <tbody>
                    <tr><th>TOTAL PRECIO UNITARIO ({hoja.secciones.map((s) => s.numero).join(' + ')})</th><td className="num">{num(hoja.total_sin_redondeo, dec + 2)}</td></tr>
                    <tr className="b2-adoptado"><th>TOTAL PRECIO UNITARIO ADOPTADO ({dec} decimales)</th><td className="num">{num(hoja.precio_adoptado, dec)}</td></tr>
                  </tbody>
                </table>
              </div>
              <p className="tenue b2-pie">Los impuestos y cargas salen del modelo de cálculo del proyecto (pestaña Cálculo). Si lo cambias, la hoja se actualiza al volver a abrirla.</p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
