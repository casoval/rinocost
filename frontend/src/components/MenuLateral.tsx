export type Vista = 'proyectos' | 'bibliotecas' | 'modelos' | 'configuracion';

const OPCIONES: { id: Vista; titulo: string; ayuda: string }[] = [
  { id: 'proyectos', titulo: 'Proyectos', ayuda: 'Tus presupuestos de obra' },
  { id: 'bibliotecas', titulo: 'Bibliotecas', ayuda: 'Ítems, materiales y unidades' },
  { id: 'modelos', titulo: 'Modelos de cálculo', ayuda: 'Cómo se arma el precio' },
  { id: 'configuracion', titulo: 'Configuración', ayuda: 'Datos de tu empresa' },
];

interface Props {
  vista: Vista;
  onCambiar: (v: Vista) => void;
  abierto: boolean;
  onAlternar: () => void;
  children?: React.ReactNode; // contenido extra bajo la opción activa (p. ej. la lista de proyectos)
}

export function MenuLateral({ vista, onCambiar, abierto, onAlternar, children }: Props) {
  return (
    <>
      <button type="button" className="boton hamburguesa" aria-expanded={abierto} aria-controls="menu-lateral" onClick={onAlternar}>
        {abierto ? 'Cerrar menú' : 'Menú'}
      </button>
      <aside id="menu-lateral" className={abierto ? 'lateral abierto' : 'lateral'}>
        <div className="marca">
          <h1>Rino<span>Cost</span></h1>
          <p>Presupuestos de obra</p>
        </div>
        <nav aria-label="Secciones de la aplicación">
          <ul className="menu">
            {OPCIONES.map((o) => (
              <li key={o.id}>
                <button
                  type="button"
                  className={vista === o.id ? 'opcion activa' : 'opcion'}
                  aria-current={vista === o.id ? 'page' : undefined}
                  onClick={() => onCambiar(o.id)}
                >
                  <strong>{o.titulo}</strong>
                  <span className="tenue">{o.ayuda}</span>
                </button>
                {vista === o.id && children && <div className="submenu">{children}</div>}
              </li>
            ))}
          </ul>
        </nav>
      </aside>
    </>
  );
}
