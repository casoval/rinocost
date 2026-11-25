# App de presupuestos de construcción

Hito actual: **de la convocatoria al presupuesto, el cronograma y el Excel final: importar B-1 y especificaciones, vincular tus APU, cargar rendimientos y precios, programar la obra con hitos por módulo y exportar.**

## Estructura
```
backend/                     FastAPI + SQLAlchemy
  app/main.py                API (arranque, vista previa simple en GET /)
  app/importers/b1_parser.py lector del Formulario B-1 (PDF)
  app/importers/spec_parser.py lector de especificaciones técnicas (recursos, datos técnicos, cruce con el B-1)
  app/importers/biblioteca_excel.py importador de bibliotecas de APU desde Excel (+ plantilla)
  app/matching/              motor de coincidencia (nombres parecidos, unidad, specs críticas) y modos de recursos
  app/cronograma/            cronograma: duraciones desde la mano de obra, secuencia, ruta crítica, hitos
  app/exportadores/          Excel (B-1 con precios y literal, APU, recursos, cronograma) e importe en letras
  app/db/                    modelos, sesión y creación de tablas
  app/services/              proyectos, bibliotecas y vinculación de APU (cálculos en el servidor)
  app/api/                   rutas: /proyectos...
  tests/                     lectores, motor de coincidencia, cronograma, exportación y base de datos
frontend/                    React + TypeScript + Vite
  src/App.tsx                lista de proyectos e importación
  src/components/            tabla del proyecto y celda de precio editable
docker-compose.yml           PostgreSQL opcional (por defecto se usa SQLite)
```

## Puesta en marcha (dos terminales)
**1. Backend**
```bash
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload                           # http://127.0.0.1:8000/docs
```
**2. Frontend**
```bash
cd frontend
npm install
npm run dev                                             # http://localhost:5173
```
Abre http://localhost:5173, pulsa **Importar B-1 (PDF)** y sube el PDF. Escribe precios unitarios
(con coma decimal) y mira cómo cambian los totales por módulo y del proyecto.

## Probar los lectores sin servidor
```bash
cd backend
python -m app.importers b1  ruta/b1.pdf
python -m app.importers esp ruta/especificaciones.pdf --b1 ruta/b1.pdf    # cruza por número de ítem
```
En la app: importa el B-1 y, dentro del proyecto, pulsa **Importar especificaciones (PDF)**. Cada ítem
muestra «Ver especificación» con sus recursos (materiales, mano de obra, equipo), datos técnicos y
características mínimas, cada uno con su página de origen.

## Bibliotecas y vinculación de APU
1. En la barra lateral: **Descargar plantilla de Excel**, llénala con tus APU (una fila por recurso) y pulsa
   **Importar biblioteca (Excel)**. Sin cambiar el formato también sirve cualquier hoja con las columnas
   APU, Recurso y Cantidad (más Tipo, Unidad y Precio unitario).
2. En el proyecto elige el modo de recursos y pulsa **Vincular automáticamente**: solo se aplican las coincidencias
   de confianza alta con la misma unidad del B-1. El resto se elige ítem por ítem en «Ver detalle».
3. Modos: **pliego** (solo lo que pide la especificación), **biblioteca** (tu APU tal cual, avisando lo que falte
   del pliego) e **híbrido** (tu APU más lo que el pliego pide y falta, como pendiente).
- **Editar el APU del ítem:** en «Ver detalle» cada línea tiene su cantidad (consumo o rendimiento POR UNIDAD DEL ÍTEM,
  por ejemplo kg de cemento por m²), su precio y el origen del rendimiento. También puedes agregar o quitar recursos.
  El precio de un recurso se aplica a todos los APU del proyecto que lo usan (se puede desactivar), y en «Precios de los
  recursos del proyecto» se cargan todos de una vez.
- El APU se COPIA al ítem: editarlo no cambia tu biblioteca. Si le faltan cantidades o precios, el ítem no tiene
  precio hasta completarlo (nunca se inventa un rendimiento).
- Lo que confirmas a mano se recuerda: la próxima vez ese ítem se propone con confianza alta.
  Lo vinculado automáticamente NO se recuerda hasta que lo confirmes.

## Cronograma y exportación a Excel
- **Cronograma** (panel «Cronograma de ejecución» dentro del proyecto): duración de cada ítem = horas-hombre de la mano de
  obra de su APU ÷ (personas × horas de jornada), en días hábiles. Eliges fecha de inicio, jornada, personas por actividad
  (global o por ítem), si se trabaja los sábados, los feriados y la secuencia (un módulo tras otro, todo en serie o todo
  en paralelo). Las esperas del pliego en días (p. ej. 21 días de fraguado) retrasan a los sucesores.
- **Hitos por módulo:** pon una fecha límite en cada módulo; si el cronograma la incumple, se muestra el atraso en días
  hábiles y se avisa.
- Solo se programan los ítems cuyo APU tiene TODA la mano de obra con cantidad. Los demás quedan en «ítems sin programar»
  con su motivo: nunca se inventa una duración.
- **Descargar Excel:** hojas «Formulario B-1» (precios y precio en letras, totales como fórmulas vivas), «Resumen»,
  «Análisis de precios», «Materiales y recursos» y, si se pide, «Cronograma» con diagrama de barras semanal.
- Aún no incluye gastos generales, utilidad ni impuestos.

## Base de datos
- Por defecto: SQLite en `backend/presupuestos.db` (se crea sola al iniciar).
- Como el esquema va a cambiar mucho mientras se prueba, para empezar de cero:
  `python -m app.db.init_db --reset`  (**borra todo**).
- PostgreSQL: `docker compose up -d`, instalar `psycopg[binary]` y arrancar con
  `DATABASE_URL=postgresql+psycopg://presupuestos:presupuestos@localhost:5432/presupuestos`.
- Cuando el esquema se estabilice se pasa a migraciones con Alembic.

## Pruebas
```bash
cd backend
B1_PDF=ruta/al/b1.pdf python -m unittest discover -s tests -v
```
(En PowerShell: `$env:B1_PDF="ruta\al\b1.pdf"`.)

## Reglas ya implementadas
- El B-1 manda: nombre, unidad, cantidad, orden y módulo salen solo de él y quedan bloqueados.
- Dos lecturas del PDF (tablas y texto) se comparan; si difieren, hay alerta.
- Las especificaciones se asignan a cada ítem por su NÚMERO. El B-1 manda: nunca cambian nombre, unidad ni cantidad.
- Se avisa (sin corregir nada) de: unidad distinta entre B-1 y especificación, nombre distinto, ítems sin
  especificación o especificaciones sin ítem, y unidades sospechosas en los recursos (p. ej. cemento en m3).
- La especificación dice QUÉ recursos pide, no CUÁNTO: las cantidades quedan pendientes para el APU.
- Los totales se calculan en el servidor (Decimal, 2 decimales); el navegador solo los muestra.
- El esquema ya incluye regiones, bibliotecas, recursos con precio por región y APU con origen por línea.

## Siguiente
1. Costos indirectos (gastos generales, utilidad, impuestos) en el presupuesto y en el Excel.
2. Calculadora de rendimientos por cuadrilla (m² por día → horas-hombre por unidad).
3. Tabla con columnas y fórmulas personalizables.
