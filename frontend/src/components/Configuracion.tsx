import { useState } from 'react';

const CLAVE = 'presupuestos.empresa';
const CAMPOS: [keyof Empresa, string][] = [
  ['nombre', 'Nombre de la empresa'], ['direccion', 'Dirección'], ['telefono', 'Teléfono'], ['ciudad', 'Ciudad y país'],
];
export interface Empresa { nombre: string; direccion: string; telefono: string; ciudad: string }

export function leerEmpresa(): Empresa {
  try {
    return { nombre: '', direccion: '', telefono: '', ciudad: '', ...JSON.parse(localStorage.getItem(CLAVE) ?? '{}') };
  } catch {
    return { nombre: '', direccion: '', telefono: '', ciudad: '' };
  }
}

export function Configuracion() {
  const [e, setE] = useState<Empresa>(leerEmpresa);
  const [guardado, setGuardado] = useState(false);
  function guardar(ev: React.FormEvent) {
    ev.preventDefault();
    try { localStorage.setItem(CLAVE, JSON.stringify(e)); setGuardado(true); } catch { setGuardado(false); }
  }
  return (
    <section aria-labelledby="t-cfg">
      <h2 id="t-cfg">Configuración</h2>
      <p className="tenue">Encabezado de la empresa para los formularios (B-2 y demás). Por ahora se guarda en este navegador; todavía no se usa en la exportación.</p>
      <form className="formulario" onSubmit={guardar}>
        {CAMPOS.map(([k, titulo]) => (
          <label key={k}>{titulo}
            <input value={e[k]} onChange={(ev) => { setE({ ...e, [k]: ev.target.value }); setGuardado(false); }} />
          </label>
        ))}
        <p><button type="submit" className="boton primario">Guardar</button> {guardado && <span className="ok" role="status">Guardado</span>}</p>
      </form>
    </section>
  );
}
