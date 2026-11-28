# RinoCost — app de presupuestos de construcción (Bolivia)

> **Este README es el ÚNICO documento del proyecto** (puesta en marcha, contexto, decisiones, estado y hoja de ruta).
> **Para quien retome el proyecto (persona o asistente de IA):** lee este archivo completo antes de tocar nada.
> Resume la visión, las decisiones ya tomadas con el usuario, lo que está hecho, lo que se verificó y lo que no,
> y lo que falta. Última actualización: 27 de noviembre de 2026 (lector de la revista PresNet, plan de bibliotecas y precios).
>
> **Regla de oro al retomar:** no afirmes que algo funciona si no lo probaste. La sección 9 separa lo que el usuario
> ya vio funcionando en su computador de lo que solo pasó pruebas automáticas.

## Inicio rápido (Windows, CMD, dos ventanas)

```bat
:: Ventana 1: backend  (API en http://127.0.0.1:8000/docs)
cd /d C:\proyectos\presupuestos-app\backend
python -m venv .venv && .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
uvicorn app.main:app --reload

:: Ventana 2: frontend  (pantalla en http://localhost:5173)
cd /d C:\proyectos\presupuestos-app\frontend
npm install && npm run dev
```
Pruebas: `cd backend` y `python -m unittest discover -s tests` (186 pruebas con los tres parches aplicados; con `B1_PDF` y `ESP_PDF` definidos no se salta
ninguna). Base de datos desde cero: `python -m app.db.init_db --reset` (**borra todo**). Más detalle en la sección 8.

---

## 1. Qué es el producto

Una aplicación web para elaborar **presupuestos de obra y su cronograma** en Bolivia, pensada para presupuestistas,
ingenieros y constructoras que hoy usan PRESCOM, Kabal, ZARCO o Excel.

**Promesa central:** *«Subes la convocatoria (o armas tu proyecto) y en minutos tienes presupuesto, cronograma y el
Excel para presentar, con la libertad de Excel y rendimientos que se pueden justificar.»*

**Diferenciales buscados**
1. **Rendimientos trazables** (cada consumo/rendimiento dice de dónde sale: biblioteca, medido en obra, calculado,
   similar, comunitario, referencial, manual o pendiente). Las apps actuales suelen calcularlos «a ojo» o fijos.
2. **Automatización de la convocatoria:** importar el B-1 y las especificaciones técnicas en PDF, vincular los APU de
   la biblioteca del usuario (aunque los nombres difieran) y programar la obra.
3. **Control total del usuario:** la automatización propone, nunca impone; todo es editable.
4. **Modelo de cálculo del precio configurable:** del costo directo del APU al precio unitario (B-2 de licitación pública,
   obra privada, perfiles propios del usuario), con porcentajes y bases editables y una copia congelada por proyecto.
5. *(Planeado)* Flexibilidad tipo Excel (columnas y fórmulas propias), biblioteca pública colaborativa por regiones,
   importación de modelos IFC con visor 3D.

**Modelo de negocio (acordado, aún sin construir):** gratis + suscripción mensual en bolivianos (pago por QR o
transferencia al inicio). Planes: gratuito (pocos proyectos, marca de agua), profesional, equipo.

**Usuario que dirige el proyecto:** trabaja en Windows 10 con CMD, lo ejecuta en `C:\proyectos\presupuestos-app`, tiene
internet lento (~50 KB/s), prefiere pasos exactos para copiar y pegar, y pide «continuar» para avanzar de módulo en
módulo. Idioma: español (la interfaz, los mensajes y el código están en español).

---

## 2. Decisiones y principios (no se cambian sin hablarlo con el usuario)

**Datos y fuentes**
- **El B-1 manda.** Nombre, unidad, cantidad, orden y módulo de cada ítem salen solo del Formulario B-1 y quedan
  bloqueados. Las especificaciones técnicas **solo complementan** (recursos y datos técnicos).
- Las especificaciones se asignan a los ítems **por número de ítem**, no por nombre ni por número de módulo (los
  documentos reales no coinciden: la especificación dice «MOD-8» y el B-1 «M04» para el mismo módulo).
- La especificación dice **qué** recursos pide un ítem, **no cuánto**: las cantidades quedan pendientes.
- **Nunca se corrige nada en silencio.** Lo dudoso se reporta como alerta (error, advertencia, información) con su
  origen. Todo dato extraído de un PDF guarda su **página y fragmento original**.
- **Nunca se inventa un rendimiento.** Lo que no tiene fuente queda `pendiente`. Un APU con líneas pendientes no da
  precio al ítem hasta completarse.
- Cálculos en el **servidor** con `Decimal` (totales a 2 decimales, redondeo half-up). El navegador solo muestra.

**Modelo de cálculo del precio (costos indirectos)**
- El precio unitario del ítem sale de aplicar un **modelo de cálculo** al **costo directo** del APU (materiales, mano de obra,
  equipo). El modelo es un **dato (JSON)**: lista ordenada de secciones y pasos (cargas sociales, IVA de mano de obra,
  herramientas, gastos generales, utilidad, IT…); cada paso es un porcentaje sobre una base que solo puede citar valores
  anteriores (sin referencias circulares). Nunca `eval`.
- Cada **proyecto guarda una copia congelada** del modelo (como el APU): editarla no cambia los modelos base ni los
  perfiles; borrar un perfil no cambia los proyectos que lo usaron.
- Se elige al **crear el proyecto** y se puede **cambiar en cualquier momento** (al guardar se recalculan los ítems con APU).
  Un proyecto anterior sin modelo guardado sigue con precio = costo directo (no cambia solo).
- **Los porcentajes NO son normativos para la app.** El D.S. 0181 no define el Formulario B-2 ni esos porcentajes (vienen del
  DBC de cada convocatoria). Los valores iniciales salen de la planilla de referencia del usuario (proyecto Alonso de Ibáñez
  D-11) y de la tabla de rangos que él indicó; la app **avisa, no bloquea**, si un porcentaje sale del rango de referencia, y
  la nota del modelo dice que se confirme con el DBC.
- Un APU **incompleto sigue sin precio**: el modelo no inventa nada.
- **Perfiles propios** (`perfil_costos`): copias guardadas con nombre único, **globales** por ahora (sin cuentas de usuario).

**Bibliotecas, precios y repositorio compartido** *(decidido el 26-27 nov; aún sin construir salvo el lector de la revista; ver sección 16)*
- Hay una **biblioteca básica** (la primera): los análisis de la «Revista Presupuesto y Construcción» (el usuario indica que
  tiene autorización), para que cualquiera pueda hacer su presupuesto desde el primer día. Sobre ella el usuario dueño del
  proyecto hará cambios a mano (empezando por la **unidad de medida** de cada ítem, que la revista no trae) y agregará **ítems
  nacionales, marcados solo como referencia**.
- El ítem guarda **solo el costo directo**: sus materiales, mano de obra y equipo con la cantidad por unidad. Cargas sociales,
  impuestos, gastos generales y utilidad **no se guardan**: los calcula el modelo de cálculo que elija cada usuario.
- Los **precios van aparte** del ítem, en **listas de precios por ciudad y fecha**, enlazadas a los materiales, la mano de obra y
  el equipo, y alimentadas por las **cotizaciones** que haga el dueño del proyecto (y, luego, los usuarios). Un mismo ítem se
  puede costear con la lista de La Paz, de Santa Cruz, etc.
- **Cada usuario puede tener sus propias bibliotecas de ítems y listas de precios**, y **publicarlas**; los demás **eligen** cuál
  les convence más. Un usuario puede **usar** una biblioteca publicada (solo lectura, aparece en su buscador) o **bajarla a su
  base** (copia propia, editable e independiente, que recuerda de cuál viene).
- **Publicar y descargar bibliotecas es gratis.**
- **Cada usuario crea lo suyo, sin obligarlo a importar:** bibliotecas vacías, **ítems**, y también sus propios **materiales, mano de
  obra y equipo** (cada recurso con su unidad). Dentro de un ítem puede **elegir un recurso de su biblioteca o escribirlo con
  libertad**; lo que escribe y no existe **se agrega solo** a su biblioteca de materiales / mano de obra / equipo con su unidad.
- **Unidades:** hay unidades predefinidas por tipo (material: Kg, Pza, Glb, Rollo, m…; mano de obra y equipo: Hr, Día…; ítem: m2,
  m3, Pza…), pero el usuario **puede elegir o escribir cualquiera**; la nueva se guarda en «sus unidades» de ese tipo. Kg, kg y KG son
  la misma unidad (se muestra la del catálogo). Al **importar** nunca se cambia el texto original: solo se registran las unidades nuevas.
- **Grupos:** el usuario puede agrupar sus ítems en grupos (capítulos) y subgrupos, si quiere; es opcional. Borrar un grupo no borra
  ítems.
- Lo privado es privado: sus proyectos, bibliotecas, listas, cotizaciones y perfiles de cálculo no los ve nadie si no los publica.
- Nunca se mezcla en silencio: si falta el precio en la ciudad elegida, se muestra de dónde sale el que se usa.

**Modos de recursos** (se elige por proyecto, se puede cambiar por ítem)
- `pliego`: solo los recursos que pide la especificación (si la biblioteca tiene el mismo recurso, se toma su
  cantidad y precio; el origen del recurso sigue siendo «pliego»).
- `biblioteca`: el APU del usuario tal cual; se **avisa** (sin cambiar nada) lo que el pliego pide y el APU no incluye.
- `hibrido` *(por defecto)*: el APU del usuario **más** lo que el pliego pide y falta, como pendiente.
- Si no hay APU en la biblioteca, se usa el pliego y se avisa.

**Vinculación con la biblioteca**
- El APU se **copia** al ítem (editarlo no altera la biblioteca).
- La **unidad del B-1 filtra**: un APU en otra unidad nunca pasa de confianza «baja».
- Una **especificación crítica distinta** (espesor, DN, diámetro, AWG, dosificación…) impide la confianza «alta».
- Solo la confianza **alta** se aplica sola; media y baja las confirma la persona.
- Lo que la persona confirma a mano se **recuerda** (tabla `equivalencia`); lo automático **no** se recuerda.

**Cronograma**
- La duración sale de la **mano de obra del APU**; solo se programan ítems con toda su mano de obra con cantidad.
- Hitos por módulo (fecha límite): se avisa el atraso en días hábiles.
- **Plazo máximo** de la obra en **días calendario o días hábiles** (a elección) y **objetivo**: usar las personas indicadas,
  cumplir el plazo con la menor gente, terminar lo más rápido posible, o menor costo total (necesita costo por día de obra).
  Solo se acelera la **ruta crítica**. Si con la secuencia elegida el plazo no alcanza (p. ej. 24 ítems «uno tras otro»), **abre frentes
  de trabajo en paralelo** (el menor número posible) y entrega la **cuadrilla de cada frente y el personal total**; también ofrece
  alternativas con más frentes (suelen pedir menos gente). Si es imposible, dice cuál es el mínimo real (esperas del pliego o tope).
- **PDF del cronograma con diseño tipo MS Project** (tabla + Gantt, ruta crítica en rojo, flechas de dependencia), en pestaña nueva.

**Tecnología:** FastAPI + SQLAlchemy 2 (SQLite por defecto; PostgreSQL opcional) + React 18 + TypeScript + Vite.
Sin Alembic todavía: `create_all` crea tablas nuevas y `init_db._agregar_columnas_faltantes()` agrega **columnas nuevas** a
tablas existentes (hoy solo `proyecto.modelo_costos`); Alembic cuando el esquema se estabilice.

---

## 3. Estado actual: resumen

Estado de cada módulo: **[HECHO]** implementado y con pruebas automáticas · **[POR PROBAR]** implementado, falta que el
usuario lo pruebe en su computador · **[PENDIENTE]** no existe.

| Módulo | Estado |
|---|---|
| Lector del Formulario B-1 (PDF) con doble lectura y alertas | [HECHO] y visto por el usuario en pantalla |
| Lector de especificaciones técnicas (recursos, datos técnicos, cruce con el B-1) | [HECHO] y visto por el usuario en pantalla |
| Base de datos (proyectos, módulos, ítems, alertas, especificaciones, bibliotecas, APU, equivalencias) | [HECHO]; el usuario corrió pruebas con SQLAlchemy 2.1 |
| Edición de precio directo por ítem + totales por módulo/proyecto | [HECHO] y visto por el usuario |
| Importación de bibliotecas de APU desde Excel (+ plantilla descargable) | [POR PROBAR] en pantalla |
| Motor de coincidencia + modos de recursos + vinculación automática y manual | [POR PROBAR] en pantalla (el modo «solo pliego» sí lo vio) |
| Edición de las líneas del APU (cantidad/rendimiento, precio, origen), agregar/quitar recursos, precios por recurso | [POR PROBAR] |
| Cronograma (duraciones, secuencia, ruta crítica, esperas del pliego, hitos por módulo, diagrama) | [POR PROBAR] |
| Cronograma: plazo máximo (calendario/hábiles), objetivos de tiempo óptimo, comparador de opciones y PDF tipo Project | [POR PROBAR] en pantalla; backend y PDF con pruebas automáticas (PDF revisado a ojo en imagen) |
| Exportación a Excel (B-1 con precios y literal, resumen, APU, recursos, cronograma) | [POR PROBAR] |
| Modelo de cálculo del precio (B-2 público, privado simple, solo costo directo): motor, validación, desglose por ítem, Excel con indirectos | [POR PROBAR] 150 pruebas + API probada con cliente de prueba; reproduce las 17 hojas B-2 de la planilla de referencia |
| Perfiles de cálculo propios (guardar, actualizar, eliminar) y elegir el cálculo al importar el proyecto | [POR PROBAR] |
| Menú lateral (Proyectos, Bibliotecas, Modelos de cálculo, Configuración) | [POR PROBAR] compila con los tipos reales de React; nunca visto en un navegador |
| Control de propuesta vs. precio referencial (regla del 85 %, garantías) | [HECHO] solo en el backend (`app/costos/control.py`); **sin pantalla ni endpoint** |
| Cuentas de usuario (registro, ingreso, datos privados por usuario) | [PENDIENTE] (sección 16, etapa A) |
| Lector de la «Revista Presupuesto y Construcción» (PDF → biblioteca en Excel con informe de validación) | [POR PROBAR] 16 pruebas con páginas sintéticas; **sugiere la unidad de cada ítem** (confianza alta/media/baja); sobre el PDF real: 420 APU, 2.614 líneas, 419 con precio idéntico al impreso; el usuario aún no lo ha corrido |
| **Editor de bibliotecas** (Bibliotecas → «Abrir y editar»): bibliotecas vacías, grupos, ítems, líneas, catálogos de materiales / mano de obra / equipo con unidades, recursos libres que se agregan solos, traer recursos de otras bibliotecas | [POR PROBAR] 16 pruebas de API + 2 pruebas de pantalla con navegador simulado contra el backend real (no incluidas en el repo); el usuario aún no lo ha visto |
| Catálogo de unidades por tipo (predefinidas + propias) | [POR PROBAR] |
| Listas de precios por ciudad y cotizaciones | [PENDIENTE] (sección 16, etapa C); mientras tanto cada recurso tiene un `precio_referencia` |
| Publicar, elegir, usar y bajar bibliotecas entre usuarios | [PENDIENTE] (sección 16, etapa E) |
| Planes y cobros | [PENDIENTE] |
| Todo lo demás de la sección 11 | [PENDIENTE] |

> **Entrega de los cambios del 26-nov:** se entregaron como el parche `menu-lateral-y-costos.patch` (aplicar con
> `git apply` desde la raíz del repo). Se hicieron sobre una copia del repositorio de GitHub `casoval/rinocost` (un solo
> commit al momento de revisarlo); **confirmar con el usuario que el parche se aplicó** antes de dar por hecho que está en
> su copia.

---

## 4. Arquitectura y estructura del repositorio

```
presupuestos-app/
├─ README.md                     este archivo (único documento del proyecto)
├─ docker-compose.yml            PostgreSQL opcional
├─ backend/
│  ├─ requirements.txt
│  ├─ app/
│  │  ├─ main.py                 FastAPI: arranque, GET /, GET /salud, POST /importar/b1 (vista previa sin guardar); incluye los routers
│  │  ├─ schemas.py              modelos Pydantic de entrada/salida de la API
│  │  ├─ static/index.html       pantalla simple de vista previa del B-1 (anterior al frontend React)
│  │  ├─ api/                    rutas: proyectos.py, bibliotecas.py (incluye el editor), modelos.py (modelos y perfiles), unidades.py, subida.py (lectura segura)
│  │  ├─ services/               proyectos.py (guardado, totales, salida), apu.py (vinculación, edición de líneas,
│  │  │                          precios por recurso), bibliotecas.py, editor_biblioteca.py (crear/editar bibliotecas, grupos, recursos, ítems y
│  │  │                          líneas), unidades.py (catálogo de unidades), cronograma.py,
│  │  │                          costos.py (modelo del proyecto, recálculo, perfiles, resolver clave)
│  │  ├─ db/                     base.py, session.py, models.py, init_db.py (crea tablas y siembra regiones de Bolivia)
│  │  ├─ importers/              b1_parser.py, spec_parser.py, biblioteca_excel.py, presnet_parser.py  (lectores de documentos)
│  │  ├─ matching/               texto.py (normalización y specs críticas), motor.py (sugerir/emparejar),
│  │  │                          apu_modos.py (pliego/biblioteca/híbrido y costo)
│  │  ├─ costos/                 modelo.py (motor: ModeloCostos/Seccion/Paso, validar_modelo, calcular), predefinidos.py
│  │  │                          (bolivia_b2, privado_simple, costo_directo), control.py (85 %, garantías)
│  │  ├─ cronograma/             motor.py (cálculo), puente.py (APU → actividades), optimizador.py (plazo y objetivos)
│  │  └─ exportadores/           excel.py, letras.py (importe en letras)
│  └─ tests/                     14 archivos, 186 pruebas (ver sección 8)
└─ frontend/
   ├─ package.json, vite.config.ts (proxy /api → http://127.0.0.1:8000), tsconfig.json
   └─ src/
      ├─ App.tsx                 estructura general: menú lateral + vista activa; selector de cálculo al importar el B-1
      ├─ api.ts, types.ts        cliente de la API y tipos (espejo de schemas.py)
      └─ components/             ProyectoVista (tabla, paneles), DetalleItem (APU, desglose del precio, candidatos, pliego),
                                 CeldaPrecio (celda numérica editable), Cronograma,
                                 MenuLateral, Bibliotecas, EditorBiblioteca (grupos, ítems, líneas y catálogos de recursos), Modelos (modelos base y perfiles), ModeloProyecto (editar el
                                 cálculo del proyecto, guardar como perfil), Configuracion (datos de la empresa)
```

**Flujo de datos:** PDF/Excel → lector (módulo `importers`) → servicio guarda en la base → `a_proyecto_out()` arma la
salida JSON (con totales calculados) → React la muestra. Las ediciones llaman a un endpoint, el servidor recalcula y
devuelve el proyecto completo.

**Módulos puros (sin base de datos) — se pueden probar en cualquier entorno:** `importers/*`, `matching/*`,
`cronograma/*`, `exportadores/*`. Los servicios y la API sí necesitan SQLAlchemy/FastAPI.

---

## 5. Modelo de datos (tablas)

`region` (jerárquica; se siembra Bolivia + 9 departamentos) · `proyecto` (nombre, archivo B-1, `modo_recursos`,
`region_id` sin uso aún) · `modulo` · `item` (campos del B-1 bloqueados, `modo_precio`: pendiente | directo | apu,
`precio_unitario`, `apu_id`, `vinculo_confianza`, `vinculo_confirmado`) · `especificacion_item` ·
`requisito_recurso` (lo que pide el pliego, con página y fragmento) · `dato_tecnico_item` · `alerta_importacion`
(`origen`: b1 | especificaciones | apu) · `biblioteca` · `recurso` (catálogo por biblioteca) · `precio_recurso`
(**sin uso todavía**; previsto para precios por región y fecha) · `apu` (de biblioteca **o** copia de un proyecto) ·
`apu_linea` (tipo, cantidad = consumo/rendimiento **por unidad del ítem**, precio, `origen_dato`:
pliego | biblioteca | ambos | manual, `origen_rendimiento`, `requerido_por_pliego`, `estado`: completo | pendiente) ·
`equivalencia` (clave del ítem → APU confirmado) · `perfil_costos` (nombre único, descripción, `definicion` JSON del modelo
de cálculo). `proyecto.modelo_costos` (JSON, nullable): copia congelada del modelo; `None` = solo costo directo. · `unidad` (tipo:
material | mano_obra | equipo | item, símbolo, clave normalizada, `predefinida`; única por tipo y clave) · `grupo_apu` (grupos y
subgrupos de una biblioteca) · `apu.grupo_id` · `recurso.precio_referencia` (precio con el que se propone el recurso al agregarlo
a un ítem; se reemplazará por las listas de precios).

Un ítem hoy pertenece a **un solo módulo** (no se modela «el mismo ítem en varios módulos»).

---

## 6. API (prefijo `/proyectos` y `/bibliotecas`)

Proyectos: `GET ""` · `POST /importar-b1` · `GET /{id}` · `DELETE /{id}` · `POST /{id}/especificaciones` ·
`PATCH /items/{id}/precio` · `GET /items/{id}/candidatos` · `POST /items/{id}/vincular` · `POST /{id}/vincular-auto` ·
`POST /items/{id}/lineas` · `PATCH /apu-lineas/{id}` · `DELETE /apu-lineas/{id}` · `POST /{id}/precio-recurso` ·
`POST /{id}/cronograma` · `POST /{id}/cronograma/pdf` (PDF tipo Project, inline) · `POST /{id}/exportar` (devuelve .xlsx).
Bibliotecas: `GET ""` · `GET /plantilla.xlsx` · `POST /importar-excel` · `GET /{id}/apus` · `DELETE /{id}`.
Proyectos (cálculo): `POST /importar-b1` acepta el campo de formulario opcional `modelo` (`predefinido:<codigo>` | `perfil:<id>`;
sin él, B-2 de Bolivia; 404 si no existe) · `PUT /{id}/modelo-costos` (cuerpo = modelo; valida, guarda y recalcula; 422 con los
problemas si es inválido).
Modelos (`/modelos-costos`): `GET ""` (predefinidos + perfiles, cada uno con `clave`, `propio`, `id`) · `GET /{codigo}` ·
`POST /perfiles` · `PUT /perfiles/{id}` · `DELETE /perfiles/{id}` (nombre único; 422 si el modelo es inválido).
Editor de bibliotecas (todo bajo `/bibliotecas`): `POST ""` (biblioteca vacía) · `PATCH /{id}` · grupos: `GET|POST /{id}/grupos`,
`PATCH|DELETE /grupos/{gid}` · recursos: `GET|POST /{id}/recursos?tipo=&q=`, `GET /{id}/recursos-de-otras?q=`, `POST /{id}/recursos/copiar`,
`PATCH|DELETE /recursos/{rid}?forzar=` · ítems: `POST /{id}/apus`, `GET|PATCH|DELETE /apus/{aid}`, `POST /apus/{aid}/duplicar` · líneas:
`POST /apus/{aid}/lineas` (un `recurso_id` de la biblioteca **o** `tipo`+`nombre`+`unidad` escritos), `PATCH|DELETE /lineas/{lid}`.
Unidades: `GET /unidades?tipo=`, `POST /unidades`, `DELETE /unidades/{id}` (solo las propias). Errores: 422 con el motivo, 404 si no existe.
Otras: `GET /salud`, `POST /importar/b1` (vista previa sin guardar), `GET /` (pantalla simple).
Documentación interactiva en `http://127.0.0.1:8000/docs`.

Las respuestas de edición devuelven siempre el **proyecto completo** actualizado (`ProyectoOut`).

---

## 7. Reglas de negocio ya implementadas (detalle)

**Lector del B-1** (`importers/b1_parser.py`): lectura principal por tablas (pdfplumber) y lectura de control por texto;
si difieren, alerta. Reconstruye descripciones partidas («Cu-» + «Unifilar» → «Cu-Unifilar»). Reconoce módulos
(`> M01 - NOMBRE`, con guion corto o largo). Normaliza unidades solo para comparar (`m²`/`m2`/`M2` → `m2`; se conserva
la original). Alertas: numeración salteada/repetida, cantidad ilegible o cero, unidad vacía/desconocida, módulo vacío.

**Lector de especificaciones** (`importers/spec_parser.py`): quita encabezado y número de página; reconoce encabezados de
ítem en muchas variantes (`ITEM N°1`, `ITEM 4.-`, `ITEM N5`, `ÍTEM 12.-`, `ITEM 18.- . -`…); secciones por palabras
clave (incluye `F0RMA DE PAGO` con cero); lista de recursos con una máquina de estados (viñetas, `[Kg]`, `(pie 2)`,
`Mano de obra peón.` en la misma línea, «materiales mínimos» en prosa, «No requiere»); une menciones repetidas;
**datos técnicos** por patrones fijos (dosificación, espesor, cemento mínimo, rendimiento declarado, esperas).
Alertas de cruce con el B-1: `unidad_distinta` (se usa la del B-1), `nombre_distinto` (informativa),
`item_sin_especificacion`, `especificacion_sin_item`, `unidad_sospechosa` (cemento en m³, arena en kg…).

**Motor de coincidencia** (`matching/`): normaliza (sin tildes, plurales, abreviaturas `H°A°`, `C/`, `PROV.`,
sinónimos como cielo falso = cielo raso, concreto = hormigón); separa **especificaciones críticas**; puntaje =
0,65 × Dice ponderado (palabras débiles como «suministro/instalación» pesan 0,35; tolera errores de tipeo) +
0,35 × similitud de secuencia; menos 0,30 por cada conflicto de especificación y 0,04 por cada una que falta.
Umbrales: alta ≥ 0,88 (sin conflictos y misma unidad), media ≥ 0,62, baja ≥ 0,40. Dos APU compatibles casi idénticos
(diferencia < 0,03) bajan a «media». Para recursos del pliego ↔ líneas de la biblioteca: umbral 0,70, mismo tipo, sin
conflictos; un material con más detalle sigue siendo el mismo si el nombre corto tiene ≥ 2 palabras.
*Estos umbrales se calibraron con pocos ejemplos: deben afinarse con una biblioteca real del usuario.*

**Edición del APU** (`services/apu.py`): `cantidad` = consumo o rendimiento **por unidad del ítem** (ej. kg de cemento
por m²; horas-hombre por m² para mano de obra). Si cambia la cantidad sin indicar origen, el origen pasa a `manual`.
El precio de un recurso se aplica por defecto a **todas las líneas del mismo recurso** del proyecto
(`clave_recurso` = tipo + nombre normalizado). El precio del ítem solo existe cuando **todas** las líneas están
completas. Panel «Precios de los recursos del proyecto» para cargar precios de una vez.

**Cronograma** (`cronograma/`): días hábiles = ceil(horas-hombre ÷ (personas × horas de jornada)), mínimo 1.
Horas-hombre del ítem = cantidad del ítem × suma de las cantidades de mano de obra del APU (unidad «día» × jornada;
cualquier otra unidad se toma como horas y se anota). Secuencias: `modulos_en_serie` (por defecto), `todo_en_serie`,
`todo_en_paralelo`. Semana lunes–viernes (opcional sábados); feriados los escribe el usuario (no hay lista
predefinida a propósito). Esperas del pliego: en **días** (p. ej. 21 de fraguado) retrasan a los sucesores
(conversión aproximada a días hábiles = ceil(días × días_hábiles_por_semana ÷ 7)); en **horas ≥ 24** alargan la
duración mínima. Ruta crítica y holgura por pasada hacia adelante/atrás. Hitos por módulo → atraso en días hábiles.
**No se guarda**: se calcula al pedirlo, con parámetros que envía el navegador.

**Plazo y tiempo óptimo** (`cronograma/optimizador.py`): las horas-hombre de un ítem no cambian al poner más gente, solo su
duración; por eso se suman personas **solo a actividades críticas** (acortar una con holgura no acorta la obra). Días
calendario = desde la fecha de inicio (día 1) hasta el último día de obra, fines de semana incluidos; días hábiles = los del
motor. `cumplir_plazo` suma de a una persona a la actividad crítica que más días ahorra por persona; `mas_rapido` acelera toda
la ruta crítica hasta el tope (`max_personas`, 30 por defecto); `menor_costo` minimiza `costo_indirecto_dia × días calendario +
costo_por_persona × personas sumadas` y exige el costo diario (no se inventa). **Frentes** (`secuencia = frentes_de_trabajo`, N frentes): `repartir_en_frentes` reparte los ítems equilibrando horas-hombre y
tiempo fijo (mínimo 1 día + esperas); cada frente hace los suyos en orden y los frentes corren a la vez. Con el plazo, se siembra
una cuadrilla uniforme por frente (h-h del frente ÷ días libres ÷ jornada), se repara con el cálculo real y se recorta el exceso;
personal necesario = suma de la cuadrilla (la mayor) de cada frente. El redondeo a días enteros por ítem hace que pocos frentes
pidan más gente que varios: por eso se listan alternativas. Las personas que el usuario fija a mano son el
piso. La respuesta incluye `escenarios` (manual, más rápido, plazo, menor costo) para compararlos. **Predecesoras** de cada
actividad = las que fijan su inicio. PDF (`exportadores/pdf_cronograma.py`): hoja horizontal; hasta ~8 semanas escala por días,
más largo por meses y semanas; duración en días hábiles, Comienzo/Fin en día calendario.

**Modelo de cálculo** (`costos/`, `services/costos.py`): secuencia B-2 predefinida (`bolivia_b2`): (1) materiales;
(2) mano de obra = subtotal + cargas sociales (55 %; rango de referencia 55–71,18 %) + IVA mano de obra (14,94 % = 13/87, sobre
subtotal + cargas); (3) equipo = equipo/maquinaria + herramientas (5 %, rango 5–6 %, sobre el TOTAL de mano de obra);
(4) gastos generales (10 %, rango 8–15 %) sobre 1+2+3; (5) utilidad (10 %, rango 5–10 %) sobre 1+2+3+4; (6) IT (3,09 % = 3/97)
sobre 1+2+3+4+5; precio = 1+…+6 redondeado a 2 decimales (configurable 0–6). También `privado_simple` (gastos generales y
utilidad, porcentajes de ejemplo) y `costo_directo` (sin indirectos). Referencias en `base`: `<seccion>` (total),
`<seccion>.directo`, `<paso>` (solo anteriores). `validar_modelo` rechaza códigos repetidos, base inexistente/posterior,
porcentaje negativo y dos secciones del mismo tipo de recurso. Cada paso puede llevar `minimo`/`maximo`/`ayuda` (informativos).
`calcular` usa `Decimal` y redondea solo el precio final. Los precios de materiales y equipo se ingresan **sin IVA** (87 % del
precio de factura); la app **no** hace esa conversión (idea pendiente). Verificación: calcula las 17 hojas «B-2 NN» de
`APU_Alonso_de_Ibanez_D11_corregido.xlsx` con el mismo precio adoptado (p. ej. ítem 6: Bs 59,14).
`services/apu.py` pone el precio del ítem con `costos_srv.precio_unitario(modelo del proyecto, líneas)`; `ApuProyectoOut` ahora
trae `costo` (directo), `precio` y `desglose`. `asignar_modelo` valida, guarda y recalcula los ítems con APU.

**Editor de bibliotecas** (`services/editor_biblioteca.py`, `services/unidades.py`): un ítem guarda solo líneas de materiales, mano de
obra y equipo (cantidad por unidad, precio, origen del rendimiento); no guarda indirectos. Al agregar una línea se elige un recurso de la
biblioteca o se escribe uno: se busca por tipo + nombre normalizado + unidad; si no existe se crea con su unidad (y la unidad se agrega a
las del usuario); si existe el nombre con **otra unidad** se crea aparte y se **avisa**. Sin precio escrito, la línea toma el
`precio_referencia` del recurso. Cambiar nombre, unidad o precio de un recurso se propaga a las líneas de los ítems **de esa
biblioteca** (los proyectos ya creados conservan su copia). Borrar un recurso en uso exige confirmar y las líneas conservan su texto.
Un grupo no puede quedar dentro de sí mismo o de un subgrupo; borrarlo deja sus ítems «sin grupo» y sube los subgrupos. Cantidades y
precios no pueden ser negativos; un ítem sin cantidad o precio **no tiene costo directo** (no se inventa). Los textos que escribe la
persona se unifican con el catálogo de unidades (kg → Kg); lo importado no se toca.

**Control de propuesta** (`costos/control.py`, solo backend): compara la propuesta con el precio referencial según el D.S. 0181
(NB-SABS) art. 21: garantía de seriedad 1 % del precio referencial; garantía de cumplimiento 7 % (3,5 % para micro y
pequeñas empresas en contrataciones de hasta Bs 1.000.000); garantía adicional si la propuesta queda bajo el 85 % del
precio referencial (diferencia con ese 85 %). Del mismo decreto se anotó: antigüedad máxima del precio referencial 4 meses
(art. 16) y anticipo máximo 20 % (art. 19) — esos dos aún no se usan en la app. Todos los porcentajes son parámetros.
No sustituye lo que diga el DBC de cada convocatoria.

**Exportación a Excel** (`exportadores/excel.py`): hojas «Formulario B-1» (precios, precio en letras, total por ítem
como fórmula, total general), «Resumen», «Análisis de precios», «Materiales y recursos» (consolidado por tipo +
nombre normalizado + unidad), y «Cronograma» con diagrama semanal. Las fórmulas se verificaron recalculando con
LibreOffice. El precio en letras es estático (se genera al exportar). Desde el 26-nov la hoja «Análisis de precios» agrega, bajo el costo
directo de cada ítem, las líneas del modelo (cargas, IVA, herramientas, gastos generales, utilidad, IT) y el **PRECIO UNITARIO**;
esas líneas van como **valores, no como fórmulas vivas**.

---

## 8. Cómo ejecutar y probar

**Requisitos:** Python 3.10+ (el usuario tiene 3.12) y Node 18+.

```bat
:: Backend (CMD de Windows)
cd /d C:\proyectos\presupuestos-app\backend
python -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
uvicorn app.main:app --reload

:: Frontend (otra ventana)
cd /d C:\proyectos\presupuestos-app\frontend
npm install
npm run dev
```
Pantalla: `http://localhost:5173` · API: `http://127.0.0.1:8000/docs`.
La base es `backend/presupuestos.db` (SQLite). Empezar de cero: `python -m app.db.init_db --reset` (**borra todo**).
El esquema crea tablas nuevas y solo agrega las columnas registradas en `_agregar_columnas_faltantes`; para cualquier otro cambio
en una tabla existente hay que reiniciar la base (aún no hay Alembic).

**Pruebas** (desde `backend`): `python -m unittest discover -s tests`. Total: **186** (con los parches de validación, del lector de la revista y del editor) (lector B-1 15, especificaciones
20, motor de coincidencia 17, modos de recursos 10, Excel de bibliotecas 8, cronograma 22, exportación 9, base de datos
30, modelo de costos 19, perfiles 4, revista PresNet 16, editor de bibliotecas 16). En un entorno sin los PDF reales se saltan 15. Las pruebas con los PDF reales leen las variables `B1_PDF` y `ESP_PDF`; sin ellas se **saltan** (no fallan).
En CMD: `set B1_PDF=C:\proyectos\pruebas\b1.pdf` y `set ESP_PDF=C:\proyectos\pruebas\especificaciones.pdf`.

**Aplicar el parche del 26-nov** (Git para Windows, desde la raíz del repo): `git apply menu-lateral-y-costos.patch`. Al
arrancar se agregan solas la columna `proyecto.modelo_costos` y la tabla `perfil_costos`: **no hace falta `--reset`**. El frontend
usa `npm run dev` como siempre.

**Cargar la revista (biblioteca básica)**, desde `backend` (usa `pdfplumber`, ya instalado; tarda unos minutos):
```bat
python -m app.importers presnet "C:\ruta\Revista.pdf" --excel biblioteca_revista.xlsx
```
Imprime el resumen y las advertencias y escribe el Excel con tres hojas: «Biblioteca» (el formato que ya importa la app), «Informe»
(lo que la lectura comprobó y lo dudoso) e «Instrucciones». Como la revista **no trae la unidad** (dice «M» en todos), el lector **sugiere una unidad por ítem** según su nombre y cómo se consume
su recurso principal (`--sin-sugerir-unidades` las deja vacías). Las sugerencias se ven con color en la columna «Unidad del APU»
(verde = confianza alta, amarillo = media, naranja = baja) y en la hoja **«Unidades sugeridas»**, con el motivo de cada una: **no son datos
de la revista**. Revisa primero las naranjas, corrige las que no sean correctas y guarda; luego, en la app: **Bibliotecas → Importar
biblioteca (Excel)**. Todo viene con origen «referencial». Hasta tener la edición en bloque, ese Excel es la forma de corregir unidades
en masa; una por una se cambian en **Bibliotecas → Abrir y editar**.

**Los PDF reales no están en el repositorio.** El usuario los tiene en `C:\proyectos\pruebas\` como `b1.pdf` y
`especificaciones.pdf` (originalmente con espacios en el nombre). Conviene decidir si se agregan copias de prueba al
repo (por ejemplo en `backend/tests/data/`).

**Repositorio:** si aún no existe, `git init` en `C:\proyectos\presupuestos-app`. El `.gitignore` debe ignorar
`.venv/`, `node_modules/`, `*.db`, `__pycache__/`, `.env`. No subir bases de datos ni PDF de terceros sin revisarlos.

---

## 9. Qué está verificado y qué no

**El usuario lo vio funcionando en su computador (Windows, CMD):**
- Instalación del backend y del frontend, 91 pruebas en verde con sus dos PDF reales (versión previa a la edición de
  líneas).
- Importar el B-1: 24 ítems en 7 módulos, sin alertas.
- Importar las especificaciones: 24 ítems con especificación y las alertas de los ítems 5, 17 y 3.
- Modo «Solo el pliego» + «Vincular automáticamente»: se armaron los APU con los recursos del pliego (con cantidad y
  precio «pendiente»). Con eso se detectó la necesidad de editar las líneas, que ya se implementó.

**Verificado por quien trabajó el 26-nov (en un entorno con FastAPI, SQLAlchemy y Node, sin los PDF reales):**
- `git clone` del repositorio y las 129 pruebas de entonces: 127 pasaban y **2 fallaban** por un error real en
  `services/apu.py::vincular_item` (asignaba `item.apu_id` pero no la relación `item.apu`, que quedaba en `None` en sesiones con
  la relación ya cargada). Corregido con `item.apu = nuevo`; con eso, 129 en verde (15 saltadas).
- 150 pruebas en verde tras agregar el modelo de cálculo, los perfiles y sus pruebas; las 17 hojas B-2 de la planilla de
  referencia coinciden con el motor.
- Con el cliente de prueba de FastAPI (SQLite): migración de una base antigua (agrega la columna), `GET/POST/PUT/DELETE` de
  perfiles, `PUT /proyectos/{id}/modelo-costos` (200 y 422 con modelo inválido), proyecto creado con un perfil y 404 si el perfil
  no existe.
- Frontend: `npm install`, `tsc --noEmit` y `vite build` sin errores **con los tipos reales de React**.

**Aún sin probar:** la interfaz en un navegador (menú lateral, selector de cálculo, panel «Modelo de cálculo», perfiles, desglose
del ítem), el Excel exportado con indirectos abierto en Excel, y `importar-b1` con un PDF real y un perfil.

**Solo pasó pruebas automáticas (el usuario aún no lo probó):** importar biblioteca desde Excel en pantalla, modos
híbrido y biblioteca, candidatos y «Cambiar APU», edición de líneas y precios por recurso, cronograma, exportación a
Excel y las 150 pruebas completas en su equipo. Las rutas de edición, cronograma y exportar y el frontend de esa etapa **nunca se ejecutaron end-to-end** con una persona
usando la pantalla; las rutas del modelo de cálculo sí se ejercitaron con el cliente de prueba (ver arriba).

**Valores de referencia para comprobar con los documentos de ejemplo** (obra «Mantenimiento Centro Productivo San
Pedro», contratación directa): B-1 = 24 ítems, 7 módulos con 5, 1, 1, 5, 5, 6 y 1 ítems; especificaciones = 24 ítems y
95 recursos (8 ítems solo con mano de obra); alertas: ítem 5 `unidad_distinta` (B-1 m³, especificación m²), ítem 17
`unidad_sospechosa` (cemento en m³, arena en kg), ítem 3 `nombre_distinto`. Con la plantilla de biblioteca (precios
ilustrativos): el ítem 1 queda en Bs 16,80 por unidad (total 543,31) y el ítem 12 en Bs 75,80 (total 45,48).

---

## 10. Particularidades de los documentos reales (Bolivia)

- **Formulario B-1:** tabla con columnas Ítem, Descripción, Unidad, Cantidad, Precio unitario (numeral y literal),
  Precio total. Módulos como filas `> M01 - NOMBRE`; numeración de ítems **continua** entre módulos; cantidades con
  coma decimal; descripciones que se parten en dos líneas (el texto plano las desordena, por eso se lee por tablas).
- **Especificaciones técnicas:** un ítem por sección con 5 apartados (descripción/definición; materiales, herramientas
  y equipo; procedimiento; medición; forma de pago). Encabezado «Especificaciones Técnicas» repetido y número de página
  al pie de cada hoja. Los encabezados de ítem y de módulo tienen muchas variantes. Los nombres de las secciones y de
  las etiquetas («Mano de Obra Mínima», «Equipo o maquinaria») varían. Hay errores en el propio pliego (unidades
  invertidas, módulo con otro número, unidad distinta a la del B-1).
- **«Revista Presupuesto y Construcción» (reporte de PresNet v1.92, sep-2026 a feb-2027):** PDF de 421 páginas **con texto**, un
  análisis de precios unitarios por página (420 APU; uno ocupa dos páginas). Todos usan la estructura B-2 con 55 %, 14,94 %, 5 %,
  10 %, 10 % y 3,09 %. No indica ciudad ni región, y la unidad del ítem dice «M» en los 420 (no es confiable). Hay descripciones
  de recurso partidas en varias líneas y nombres de ítem que empiezan en la línea de arriba de «Actividad :». Detalle en 16.5.
- Los PDF de las convocatorias son **con texto** (no escaneados). Los escaneados requerirían OCR (pendiente).

---

## 11. Lo que falta (hoja de ruta)

Prioridad sugerida: primero **verificar con el usuario** lo marcado [POR PROBAR], luego lo siguiente.

**Etapa 0 (prioridad, 26-27 nov): biblioteca básica, listas de precios y bibliotecas de usuarios** — plan en la sección 16. Orden:
lector de la revista (hecho, por probar) → editor de ítems y listas de precios por ciudad con cotizaciones → cuentas → publicar,
elegir, usar y bajar bibliotecas.

**Etapa 1: completar el flujo «convocatoria → presupuesto → entrega»**
- ~~Costos indirectos~~ **Hecho en lo básico (26-nov):** modelo de cálculo por proyecto, B-2 predefinido, perfiles propios,
  porcentajes editables con aviso de rango. **Falta:** armar un modelo propio desde cero por pantalla (cambiar bases, agregar o
  quitar conceptos; hoy solo se parte de uno existente y se editan porcentajes y qué se incluye); que el B-1 del Excel muestre
  los indirectos (hoy están en «Análisis de precios» como valores); fórmulas vivas en esas líneas; modelo distinto **por ítem**
  (hoy es uno por proyecto); precio directo manual no pasa por el modelo.
- **Control de propuesta en pantalla:** precio referencial del proyecto, regla del 85 %, garantías (el cálculo existe en el
  backend), y usar la antigüedad del precio referencial (art. 16) y el anticipo (art. 19).
- **Descuento automático del 13 % de IVA** en materiales y equipo (opción por recurso): hoy se ingresan ya sin IVA.
- **Calculadora de rendimientos por cuadrilla:** convertir «m² por día» (y tamaño de cuadrilla) en horas-hombre por
  unidad y registrar el origen del dato.
- **Crear un proyecto desde cero** (hoy solo nace del B-1 en PDF): agregar ítems propios o desde la biblioteca, para
  obra privada.
- **Importar convocatorias en Excel y Word**, y PDF escaneado con OCR.
- **Pantalla de revisión** con el PDF al lado de lo extraído; confirmación de módulos detectados.
- **Exportar a PDF** y **devolver el presupuesto en el formato exacto de la convocatoria** (hoy el Excel imita la
  estructura del B-1 pero no rellena el archivo original de la entidad).
- Importar **hitos por módulo** que vengan con la convocatoria.
- Persistir los parámetros del cronograma por proyecto; precios congelados por proyecto y «actualizar a fecha/región».
- Edición de la biblioteca desde la pantalla, «guardar este cambio también en mi biblioteca», exportar biblioteca a Excel.

**Etapa 2**
- **Columnas y filas personalizables con fórmulas tipo Excel** (motor propio con ~30–40 funciones en español,
  referencias por nombre de columna, servidor como fuente de verdad, vistas guardadas, pegar desde Excel).
- Rendimientos **calculados** desde los datos técnicos del pliego (dosificación + espesor → consumo de materiales),
  con supuestos editables; rangos mínimo/probable/máximo; jornada mínima y agrupar ítems pequeños.
- Plazo **inverso** por hito (el plazo total ya está hecho, ver `optimizador.py`); curva costo-plazo; el costo de acelerar hoy
  solo considera gastos por día y costo por persona (no horas extra ni rendimiento decreciente de cuadrillas grandes).
- Flujo de caja y curva S; avance real vs. línea base.
- **Biblioteca pública por regiones:** consulta primero; regiones jerárquicas (país → departamento → ciudad → zona);
  precios con región, fecha y condición (puesto en obra / en depósito); factor regional; catálogo maestro de recursos.
- Embeddings para la coincidencia, IA que sugiere APU (siempre «propone, no decide», marcado como sin verificar).
- Varios usuarios, roles, enlace de solo lectura para el cliente.

**Etapa 3**
- **IFC:** procesar en el navegador (web-ifc) para obtener cantidades; visor 3D (That Open Engine) con vinculación
  elemento → ítem, colores por estado y, luego, visor 4D con el cronograma.
- Publicación abierta de datos por los usuarios (incluye precios, por región) con moderación, detección de atípicos,
  estadísticas (mediana y rango por región) y términos de uso (consultar a un abogado sobre bases de terceros).
- Planillas de avance y certificados, control de obra, subcontratos, nivelación de recursos, modo sin conexión, vista móvil.

**Transversal pendiente:** cuentas de usuario y autenticación, planes y cobros, migraciones con Alembic, pasar a
PostgreSQL en producción, despliegue, respaldos.

### Estado por área (detalle)
| Área | Hecho | Falta |
|---|---|---|
| Bibliotecas | Varias bibliotecas, importar Excel, plantilla, catálogo de recursos por biblioteca | Activar varias con prioridad, fusionar/duplicados, historial de precios, importar de otros programas, editar en pantalla |
| Proyectos | Proyecto → módulos → ítems desde B-1 | Capítulos, mismo ítem en varios módulos, región de obra (campo sin UI), duplicar, plantillas, versiones |
| Precio del ítem | Directo y por APU | APU simplificado, precio global/cotización, cuadrillas y jornales, factores de ajuste |
| Rendimientos | Origen por línea (selector), pendiente explícito | Semáforo por ítem, cálculo desde datos técnicos, rangos, sensibilidad, retroalimentación desde obra |
| Cronograma | Cálculo, ruta crítica, esperas, hitos, diagrama, Excel | Dependencias editables, plazo inverso, nivelación, MS Project, persistencia, hitos importados |
| Exportación | Excel completo | PDF, formato exacto de la entidad, indirectos |

---

## 12. Decisiones abiertas

- Confirmar con el DBC de cada convocatoria los rangos y las bases del B-2 (los rangos de referencia los indicó el usuario; el
  D.S. 0181 no los contiene) y cuántos modelos predefinidos conviene ofrecer (hoy 3; privado de ejemplo).
- Perfiles de cálculo: hoy globales; deben pasar a ser por usuario/organización cuando haya cuentas.
- Precios de los planes, pasarela de pago y facturación.
- Autenticación y alojamiento (¿nube propia?, ¿PostgreSQL administrado?).
- Si se usará un modelo de lenguaje (¿cuál? ¿privacidad de las convocatorias?) para extraer datos que las reglas no
  alcanzan, por ejemplo materiales mencionados solo en la prosa (la grava del ítem 6 no está en su lista).
- **Licencia de la revista:** el usuario indica que **tiene autorización**. Conviene que conste por escrito y cubra (a) publicarla en
  un servicio de pago, (b) mostrarla a otros usuarios y (c) que puedan **bajarla completa a su base** (copia total). Guardar quién
  autorizó, cuándo y el alcance en la ficha de la biblioteca. Esto no es asesoría legal.
- Condiciones legales y de privacidad del repositorio público y de bases de terceros (PRESCOM, Kabal, ZARCO); términos de uso
  para contribuciones (licencia que otorga quien aporta).
- Ciudad/región de los precios de la revista (el PDF no la indica; el usuario hará sus propias cotizaciones por ciudad).
- Cómo se publica y se elige (publicar y descargar es **gratis**, decidido el 27-nov): ¿calificaciones y reportes?, ¿quién revisa lo publicado?, ¿se puede bajar siempre
  la biblioteca completa o el autor decide?, ¿qué pasa con los proyectos de quien bajó una biblioteca si el autor la retira?
- Registro abierto o por invitación al inicio; quiénes serán los curadores; si el repositorio se puede ver sin cuenta.
- Si se incluyen copias de los PDF de ejemplo en el repositorio.

---

## 13. Limitaciones y deuda técnica conocidas

- Los datos técnicos del pliego salen de **patrones fijos**; no detectan lo que no encaja (p. ej. el espesor «5 cm» del
  ítem 12 escrito sin la palabra «espesor»).
- Probado con **una sola** convocatoria. Otras entidades pueden traer encabezados distintos: habrá que ajustar.
- Los umbrales de coincidencia están calibrados con pocos ejemplos.
- El cronograma asume horas-hombre para unidades desconocidas, convierte las esperas a días hábiles de forma
  aproximada y no considera esperas finales del último ítem. No guarda parámetros.
- No hay autenticación: cualquier persona que alcance la API puede leer y borrar todo. **No exponer a internet así.**
- El precio en letras del Excel no se actualiza si se cambia un precio dentro del archivo.
- `precio_recurso` y `proyecto.region_id` existen pero no se usan; `static/index.html` es una pantalla antigua.
- Sin migraciones; sin pruebas del frontend ni de la API con servidor real (solo lógica y servicios).
- El frontend se compiló con los tipos reales de React y `vite build` (26-nov), pero no se ha probado en un navegador ni tiene pruebas.
- El modelo de cálculo es **uno por proyecto**; el precio directo manual de un ítem no pasa por él; el Excel muestra los indirectos como valores.
- El `precio_referencia` del recurso es provisional: la lista de precios por ciudad (etapa C) lo reemplaza. La lista de ítems del editor muestra hasta 300 a la vez (usa el buscador); no hay deshacer.
- Las dos pruebas de pantalla del editor (navegador simulado contra el backend real) no están en el repositorio porque exigen vitest/jsdom; si se quieren, agregarlas como `devDependencies`.
- Los datos de empresa de «Configuración» se guardan en el navegador (`localStorage`) y todavía no se usan en la exportación.
- La migración ligera solo conoce la columna `proyecto.modelo_costos`.

---

## 14. Convenciones y lecciones aprendidas

**Convenciones**
- Español en la interfaz, en los mensajes de error y en el código. Dinero en «Bs»; decimales con coma al escribir.
- Cada mensaje de error debe decir qué pasó y qué hacer. Alertas con nivel y origen; nada se corrige en silencio.
- Los campos del B-1 son de solo lectura. Los datos de PDF llevan página y fragmento.
- Toda lógica nueva va con pruebas; la lógica pura (sin base de datos) se prueba aparte para poder correrla en
  cualquier entorno. Las pruebas que dependen de archivos reales se saltan si no existen.
- Antes de afirmar que algo funciona: ejecutarlo. Si no se pudo, decirlo.

**Lecciones (errores que ya ocurrieron)**
- Un parche de texto sin revisar dejó `=` en vez de `=>` en un archivo TypeScript. Tras editar el frontend, comprobar la
  sintaxis con `tsc`.
- Se olvidó `openpyxl` en `requirements.txt` (el entorno de desarrollo ya lo tenía). Revisar siempre que los requisitos
  cubran lo que se importa.
- Un total esperado en una prueba (99 recursos) era una cifra supuesta; el valor correcto (95) se recontó a mano contra
  el PDF. No ajustar pruebas solo para que pasen: verificar el valor.
- En el computador del usuario `pip` falló con `charset-normalizer`; se resolvió con
  `python -m pip install --upgrade pip`. Con su conexión, `npm install` tarda ~7 minutos. Ignorar `npm audit` y no
  usar `npm audit fix --force`. Las versiones instaladas son más nuevas que las probadas al inicio (FastAPI 0.165,
  SQLAlchemy 2.1, Pydantic 2.14, Vite 5.4).
- Los nombres de archivo del usuario tenían espacios; usar comillas o renombrar.
- Asignar solo la clave foránea (`item.apu_id = …`) deja la relación en caché con el valor anterior dentro de la misma sesión:
  asignar la relación (`item.apu = …`). Lo destapó una prueba, no la aplicación real.
- El validador de modelos detectó un error propio (un paso y una sección con el mismo código): validar siempre los modelos predefinidos.
- No borrar un archivo SQLite mientras el motor lo tiene abierto en una prueba (da «readonly database»).
- No afirmar como norma lo que viene de la experiencia del usuario o de una planilla: el D.S. 0181 no define el B-2.

**Si quien retoma es un asistente de IA con un entorno sin internet:** probablemente no tenga FastAPI/SQLAlchemy
instalados (las pruebas de base de datos se saltan); el compilador `tsc` puede existir pero sin los tipos de React
(usar declaraciones mínimas para revisar); LibreOffice, si existe, sirve para recalcular los .xlsx y comprobar fórmulas;
el sistema de archivos puede reiniciarse entre turnos (restaurar desde el repositorio o el zip entregado).

---

## 15. Lista de verificación al retomar

1. Leer este archivo completo (`README.md`).
2. Pedir al usuario qué probó desde la última vez y qué vio (capturas y el texto de la ventana de `uvicorn` si algo falló).
3. Correr `python -m unittest discover -s tests` con `B1_PDF` y `ESP_PDF` definidos; deben pasar las 186 sin saltadas.
4. Si algo marcado [POR PROBAR] falla en su computador, **arreglarlo antes** de añadir módulos nuevos.
5. Confirmar que el parche `menu-lateral-y-costos.patch` está aplicado y que la interfaz nueva (menú, modelo de cálculo,
   perfiles) funciona en su navegador; pedir capturas.
6. Confirmar con el usuario la prioridad del siguiente módulo (sección 11, etapa 1). Candidatos inmediatos: control de propuesta
   en pantalla, descuento del 13 % de IVA, modelo propio desde cero, crear proyecto desde cero.
7. Al terminar cada módulo: pruebas nuevas y este README actualizado (secciones 3, 9 y 17), y entregar el cambio
   con instrucciones exactas para Windows/CMD.

---

## 16. Plan: bibliotecas, listas de precios, cotizaciones y publicación entre usuarios

*Estado: diseño acordado en conversación. Construido: solo el lector de la revista (16.4). El resto es plan.*

### 16.1 Qué se quiere
- Una **biblioteca básica** para que el usuario haga su presupuesto desde el primer día. Es la de la revista; luego se le suman
  ítems nacionales (solo como referencia) y las correcciones del dueño (unidades, nombres).
- Al abrir un ítem se ven **solo materiales, mano de obra y equipo**. Todo lo demás lo pone el modelo de cálculo del usuario (sección 7).
- Los **precios son de cada ciudad** y salen de **cotizaciones**; cada material, mano de obra y equipo está enlazado a su precio.
- Cada usuario arma **sus bibliotecas de ítems y sus listas de precios**, las **publica**, y otros **eligen** la que les convence;
  pueden **usarla** tal cual o **bajarla a su base** para modificarla.

### 16.2 Las tres capas (para no mezclar lo que cambia con lo que no)
| Capa | Qué guarda | Quién la cambia |
|---|---|---|
| **Biblioteca de ítems** | Ítems (APU): nombre, unidad, categoría y líneas (recurso + cantidad por unidad + origen del rendimiento). Sin precios ni indirectos. | Su autor |
| **Lista de precios** | Precio de cada recurso para una ciudad y una fecha, con su fuente (cotización, revista, usuario). | Su autor, a partir de cotizaciones |
| **Cotizaciones** | Proveedor, recurso, precio, condición (puesto en obra / en depósito), ciudad, fecha, vigencia, adjunto. | Quien cotiza |
Costear un ítem = Σ (cantidad × precio de la **lista elegida**) → **modelo de cálculo** del usuario → precio unitario. Cambiar de
ciudad es cambiar de lista; el ítem no se toca. Si la lista elegida no tiene el precio de un recurso, se **muestra** de qué otra lista
sale el que se usa (nunca en silencio) y el ítem queda marcado.
Cómo encaja con lo que ya existe: `Biblioteca` (ya tiene `publica` y `region_id`), `Recurso`, `Apu`/`ApuLinea` y `PrecioRecurso`
(valor, región, fecha, fuente). Falta: una **lista de precios** como entidad (hoy el precio cuelga del recurso), la **cotización**, la
ficha de publicación (autor, fuente, autorización, periodo, versión, estado) y el campo «solo referencia» / ámbito (nacional o ciudad)
del ítem.

### 16.3 Publicar, elegir, usar y bajar
- **Publicar:** el autor publica una biblioteca de ítems y/o una lista de precios con una **ficha**: nombre, descripción, ciudad,
  periodo, número de ítems, versión, fecha y autor (y, si aplica, fuente y autorización). Nada se publica solo.
- **Elegir:** catálogo de bibliotecas y listas publicadas, con búsqueda, filtro por ciudad/fuente/periodo y vista previa (ítems y
  precios) antes de decidir. Más adelante calificaciones y reportes.
- **Usar** = suscribirse en solo lectura: la biblioteca aparece en el buscador y en el motor de coincidencia, y se puede **copiar un
  ítem** al proyecto (el APU ya se copia al ítem hoy). Las versiones nuevas del autor se ofrecen, no se imponen.
- **Bajar a mi base** = copia **independiente y editable** (ítems, recursos y, si se quiere, la lista de precios) que recuerda de cuál
  viene (`origen`, versión). No se actualiza sola. Sirve para quien quiere partir de la base de otro y hacerla suya.
- Los datos privados de un usuario (proyectos, cotizaciones, perfiles de cálculo) nunca salen de su cuenta si no los publica.

### 16.4 Etapa A — La biblioteca básica de la revista (**hecho el lector; por probar**)
`python -m app.importers presnet revista.pdf --excel biblioteca.xlsx` (sección 8). Lo que se **verificó** sobre el PDF real:
- 421 páginas → **420 APU, 2.614 líneas**; 513 materiales, 42 de mano de obra y 36 de equipo distintos (según el nombre escrito);
  un solo precio por recurso en toda la revista. Las descripciones partidas en varias líneas, el análisis repartido en dos páginas
  (págs. 14–15) y los nombres que empiezan sobre «Actividad :» se reconstruyen.
- Se guarda **solo el costo directo**. Los indirectos de la revista se usan únicamente para **comprobar**: recalculando cada APU
  con el modelo B-2, **419 de 420 dan exactamente el precio impreso**.
- El que no coincide es un error de la propia revista (pág. 21, «Baranda metálica…»): las filas visibles suman Bs 590 en materiales
  y Bs 68,50 en mano de obra, pero los totales impresos son el doble (1.180 y 137) y el precio impreso (1.819,04) es el doble de lo que
  sale de las filas (909,52). No se sabe cuál es el correcto: se avisa y los datos quedan como están en el PDF.
- **La unidad del ítem no es confiable:** el PDF dice «M» en los 420. El lector **sugiere** una por ítem (`importers/unidades_sugeridas.py`:
  reglas sobre el nombre —EXCAVACION → m3, PISO → m2, TUBERIA → m, INODORO → Pza, PUNTO → Pto…— contrastadas con el consumo del recurso
  principal). Resultado sobre el PDF real: **331 con confianza alta, 83 media, 6 baja** (m2: 156, Pza: 100, m: 91, m3: 57, Pto: 10,
  Kg: 3, Glb: 3). Se marca como sugerida y con su motivo; el dueño las corregirá. Tampoco indica ciudad; trae el periodo
  (sep-2026 a feb-2027). Todo entra con origen de rendimiento «referencial».
- La hoja «Informe» del Excel lista las advertencias; hoy: el caso de la pág. 21 y la unidad.
Límites: las unidades sugeridas son reglas escritas a mano para esta revista (pueden fallar en ítems poco comunes); el lector está hecho para este formato; otro libro o edición puede traer variantes. No hay todavía pantalla en la app: se
importa por el Excel (que ya acepta la app).

### 16.5 Etapa B — Editar la biblioteca en pantalla (**hecho; por probar**)
Bibliotecas → **Abrir y editar** (o «Crear biblioteca vacía»). Pestañas **Ítems**, **Materiales**, **Mano de obra**, **Equipo**:
- **Ítems:** grupos y subgrupos a la izquierda; lista con buscador y filtro «solo sin unidad»; al abrir un ítem se editan nombre, unidad,
  código y grupo, y sus líneas por tipo (cantidad, precio, origen del rendimiento), con el **costo directo**. Para agregar una línea se
  escribe en un campo que sugiere los recursos de la biblioteca: si el nombre existe se completan unidad y precio; si es nuevo se
  agrega a la biblioteca de ese tipo. También: duplicar y borrar ítem.
- **Materiales / Mano de obra / Equipo:** tabla editable (nombre, unidad, precio de referencia, usos), alta de recursos sin pasar por un
  ítem, borrado con confirmación y **traer recursos de tus otras bibliotecas**.
- **Unidades:** se eligen de la lista del tipo (Kg, Pza, Glb, Rollo, m… / Hr, Día…) o se escribe cualquiera (se guarda sola).
- Falta: ítems nacionales marcados **«solo referencia»**, edición de unidades en bloque, ordenar ítems a mano, mover varios ítems
  de grupo a la vez, y copiar ítems de una biblioteca a otra. El flujo por Excel de la sección 8 sigue sirviendo para cambios masivos.

### 16.6 Etapa C — Listas de precios por ciudad y cotizaciones
- Entidad lista de precios (ciudad, fecha, fuente) y cotizaciones que la alimentan; enlazar cada material, mano de obra y equipo a su
  precio; el proyecto elige su lista de precios (por defecto, la de su ciudad) y el precio mostrado de cada ítem usa esa lista y el
  modelo de cálculo elegido.
- Importar cotizaciones desde Excel; historial de precios por recurso.

### 16.7 Etapa D — Cuentas
Registro e ingreso (correo y contraseña con hash, sesión con tokens, recuperación por correo), `usuario_id` en proyectos,
bibliotecas, listas, cotizaciones, perfiles de cálculo y equivalencias, con todas las consultas filtradas por dueño; roles
(`usuario`, `curador`, `admin`). Los datos actuales se asignan al primer usuario. Seguridad mínima: HTTPS, límite de intentos, CORS cerrado.
Va antes de publicar entre usuarios: sin identidad no hay autor.

### 16.8 Etapa E — Publicación entre usuarios
Ficha de publicación, catálogo para elegir, usar (suscripción de solo lectura), bajar a mi base (copia con procedencia), versiones del
autor, reportes. Revisión de lo publicado: **por decidir** (sección 12).

### 16.9 Licencia
El usuario indica que **tiene autorización** de la revista. Quedan dos cuidados: dejar constancia (quién autorizó, cuándo, alcance) en
la ficha de la biblioteca (`fuente`, `autorización`) y comprobar que el alcance cubre un servicio de pago, mostrarla a otros usuarios y
que puedan **bajarla completa**; el sistema debe poder retirar una biblioteca. No es asesoría legal.

### 16.10 Orden de construcción
| Etapa | Contenido | Se considera lista cuando |
|---|---|---|
| A | Lector de la revista → Excel → biblioteca en la app | el usuario la importó, puso las unidades y la ve en «Bibliotecas» |
| B | Editor de ítems en pantalla (**hecho, por probar**); falta «solo referencia» y edición en bloque | cambia una unidad y crea un ítem y un recurso desde la pantalla |
| C | Listas de precios por ciudad y cotizaciones | un mismo ítem da precios distintos al cambiar de ciudad |
| D | Cuentas y datos privados | dos usuarios no ven los datos del otro (pruebas de acceso) |
| E | Publicar, elegir, usar y bajar | un usuario publica y otro la usa y la baja a su base |

---

## 17. Registro de cambios

**28-nov-2026**
- Cronograma: plazo máximo en días calendario u hábiles, objetivos (manual, cumplir plazo, más rápido, menor costo), comparador de
  opciones y PDF tipo MS Project (`POST /{id}/cronograma/pdf`). Nuevo `cronograma/optimizador.py`, predecesoras y duración por
  módulo en el motor. Frentes de trabajo para cumplir el plazo (cuadrilla por frente y personal total) y alternativas. 56 pruebas nuevas (262 en total, 15 saltadas). `tsc --noEmit` y `vite build` sin errores. **Sin probar en navegador.**

**26-nov-2026**
- Revisión del repositorio `casoval/rinocost` (carpetas `backend`, `frontend`, `docker-compose.yml`, `README.md`). Corrección de `vincular_item` (relación `item.apu`).
- Lectura del D.S. 0181 (NB-SABS) y de la planilla `APU_Alonso_de_Ibanez_D11_corregido.xlsx` (17 hojas B-2).
  Conclusión: el decreto **no** define el B-2 ni sus porcentajes; sí fija garantías, regla del 85 %, antigüedad del precio
  referencial y anticipo.
- Nuevo paquete `app/costos/` (motor de modelos de cálculo, predefinidos, control de propuesta) y `services/costos.py`.
- El precio del ítem sale del modelo del proyecto; nuevos campos `precio` y `desglose` en el APU; Excel con indirectos.
- Perfiles propios (`perfil_costos`), elección del cálculo al importar el B-1, panel «Modelo de cálculo» en el proyecto con
  avisos de rango y «Guardar como perfil».
- Menú lateral con Proyectos, Bibliotecas, Modelos de cálculo y Configuración.
- Pruebas: de 129 a 150. Entrega como parche `menu-lateral-y-costos.patch`.
- **Plan de cuentas y repositorio compartido** (sección 16) y análisis de la revista PresNet (420 APU; 419 coinciden con el motor
  B-2; unidad ausente; sin región; posible problema de licencia). Se unificó la documentación en este único `README.md`.

**27-nov-2026**
- Se aclaró la visión: la revista es la **biblioteca básica**; el ítem guarda solo costo directo; los precios van en **listas por
  ciudad** alimentadas por **cotizaciones**; cada usuario puede **publicar** sus bibliotecas y listas, y otros **usar** o **bajar a su
  base** (sección 16, reescrita).
- Nuevo lector de la revista (`app/importers/presnet_parser.py`, `python -m app.importers presnet`) con informe de validación y salida
  en el formato de Excel que ya importa la app; 13 pruebas con páginas sintéticas (150 → 163; con el arreglo de validación, 167).
  Sobre el PDF real: 420 APU, 2.614 líneas, 419 con el precio idéntico al impreso; el caso de la pág. 21 queda avisado.
- Se corrigió en el lector un error propio: nombres que empiezan sobre «Actividad :» quedaban cortados («(SIN REVOQUE)»).
- `costos.b2_con_porcentajes`: constructor público del B-2 con porcentajes a medida (lo usa el lector para comprobar precios).
- **Editor de bibliotecas** (sección 16.5): bibliotecas vacías, grupos y subgrupos, ítems con líneas, catálogos de materiales / mano de
  obra / equipo con unidades, creación libre de recursos que se agregan solos, traer recursos de otras bibliotecas. Nuevo catálogo de
  unidades (predefinidas por tipo + propias). Nuevas tablas `unidad` y `grupo_apu`, columnas `apu.grupo_id` y
  `recurso.precio_referencia` (se agregan solas al arrancar). Se agregaron alias de unidad (`p2` = pie², `gal`/`galón`). 16 pruebas de
  API (150 → 183 con los tres parches; 186 con las unidades sugeridas). Decisión: publicar y descargar bibliotecas es **gratis**.
- Problema al probar: la migración ligera se verificó con una base creada por el código anterior (se agregan las columnas y se siembran
  las 40 unidades; repetible).

**28-nov-2026**
- El lector de la revista ahora **sugiere la unidad de cada ítem** (`unidades_sugeridas.py`) con su confianza y su motivo; el Excel
  generado trae las unidades con color, la hoja «Unidades sugeridas» y las instrucciones. Opción `--sin-sugerir-unidades`.
  Importado con el importador de la app: 420 ítems, 2.614 líneas, 0 errores. 3 pruebas nuevas (150 → 186 con los cuatro parches).
