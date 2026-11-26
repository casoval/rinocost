# Contexto del proyecto: app de presupuestos de construcción (Bolivia)

> **Para quien retome este proyecto (persona o asistente de IA):** lee este archivo completo antes de tocar nada.
> Resume la visión, las decisiones ya tomadas con el usuario, lo que está hecho, lo que se verificó y lo que no,
> y lo que falta. Última actualización: 26 de noviembre de 2026 (modelos de cálculo del precio, perfiles, menú lateral).
>
> **Regla de oro al retomar:** no afirmes que algo funciona si no lo probaste. La sección 9 separa lo que el usuario
> ya vio funcionando en su computador de lo que solo pasó pruebas automáticas.

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
| Exportación a Excel (B-1 con precios y literal, resumen, APU, recursos, cronograma) | [POR PROBAR] |
| Modelo de cálculo del precio (B-2 público, privado simple, solo costo directo): motor, validación, desglose por ítem, Excel con indirectos | [POR PROBAR] 150 pruebas + API probada con cliente de prueba; reproduce las 17 hojas B-2 de la planilla de referencia |
| Perfiles de cálculo propios (guardar, actualizar, eliminar) y elegir el cálculo al importar el proyecto | [POR PROBAR] |
| Menú lateral (Proyectos, Bibliotecas, Modelos de cálculo, Configuración) | [POR PROBAR] compila con los tipos reales de React; nunca visto en un navegador |
| Control de propuesta vs. precio referencial (regla del 85 %, garantías) | [HECHO] solo en el backend (`app/costos/control.py`); **sin pantalla ni endpoint** |
| Cuentas, planes y cobros | [PENDIENTE] |
| Todo lo demás de la sección 11 | [PENDIENTE] |

> **Entrega de los cambios del 26-nov:** se entregaron como el parche `menu-lateral-y-costos.patch` (aplicar con
> `git apply` desde la raíz del repo). Se hicieron sobre una copia del repositorio de GitHub `casoval/rinocost` (un solo
> commit al momento de revisarlo); **confirmar con el usuario que el parche se aplicó** antes de dar por hecho que está en
> su copia.

---

## 4. Arquitectura y estructura del repositorio

```
presupuestos-app/
├─ CONTEXTO_DEL_PROYECTO.md      este archivo
├─ README.md                     puesta en marcha corta
├─ docker-compose.yml            PostgreSQL opcional
├─ backend/
│  ├─ requirements.txt
│  ├─ app/
│  │  ├─ main.py                 FastAPI: arranque, GET /, GET /salud, POST /importar/b1 (vista previa sin guardar); incluye los routers
│  │  ├─ schemas.py              modelos Pydantic de entrada/salida de la API
│  │  ├─ static/index.html       pantalla simple de vista previa del B-1 (anterior al frontend React)
│  │  ├─ api/                    rutas: proyectos.py, bibliotecas.py, modelos.py (modelos y perfiles), subida.py (lectura segura)
│  │  ├─ services/               proyectos.py (guardado, totales, salida), apu.py (vinculación, edición de líneas,
│  │  │                          precios por recurso), bibliotecas.py, cronograma.py,
│  │  │                          costos.py (modelo del proyecto, recálculo, perfiles, resolver clave)
│  │  ├─ db/                     base.py, session.py, models.py, init_db.py (crea tablas y siembra regiones de Bolivia)
│  │  ├─ importers/              b1_parser.py, spec_parser.py, biblioteca_excel.py  (lectores de documentos)
│  │  ├─ matching/               texto.py (normalización y specs críticas), motor.py (sugerir/emparejar),
│  │  │                          apu_modos.py (pliego/biblioteca/híbrido y costo)
│  │  ├─ costos/                 modelo.py (motor: ModeloCostos/Seccion/Paso, validar_modelo, calcular), predefinidos.py
│  │  │                          (bolivia_b2, privado_simple, costo_directo), control.py (85 %, garantías)
│  │  ├─ cronograma/             motor.py (cálculo), puente.py (APU → actividades)
│  │  └─ exportadores/           excel.py, letras.py (importe en letras)
│  └─ tests/                     11 archivos, 150 pruebas (ver sección 8)
└─ frontend/
   ├─ package.json, vite.config.ts (proxy /api → http://127.0.0.1:8000), tsconfig.json
   └─ src/
      ├─ App.tsx                 estructura general: menú lateral + vista activa; selector de cálculo al importar el B-1
      ├─ api.ts, types.ts        cliente de la API y tipos (espejo de schemas.py)
      └─ components/             ProyectoVista (tabla, paneles), DetalleItem (APU, desglose del precio, candidatos, pliego),
                                 CeldaPrecio (celda numérica editable), Cronograma,
                                 MenuLateral, Bibliotecas, Modelos (modelos base y perfiles), ModeloProyecto (editar el
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
de cálculo). `proyecto.modelo_costos` (JSON, nullable): copia congelada del modelo; `None` = solo costo directo.

Un ítem hoy pertenece a **un solo módulo** (no se modela «el mismo ítem en varios módulos»).

---

## 6. API (prefijo `/proyectos` y `/bibliotecas`)

Proyectos: `GET ""` · `POST /importar-b1` · `GET /{id}` · `DELETE /{id}` · `POST /{id}/especificaciones` ·
`PATCH /items/{id}/precio` · `GET /items/{id}/candidatos` · `POST /items/{id}/vincular` · `POST /{id}/vincular-auto` ·
`POST /items/{id}/lineas` · `PATCH /apu-lineas/{id}` · `DELETE /apu-lineas/{id}` · `POST /{id}/precio-recurso` ·
`POST /{id}/cronograma` · `POST /{id}/exportar` (devuelve .xlsx).
Bibliotecas: `GET ""` · `GET /plantilla.xlsx` · `POST /importar-excel` · `GET /{id}/apus` · `DELETE /{id}`.
Proyectos (cálculo): `POST /importar-b1` acepta el campo de formulario opcional `modelo` (`predefinido:<codigo>` | `perfil:<id>`;
sin él, B-2 de Bolivia; 404 si no existe) · `PUT /{id}/modelo-costos` (cuerpo = modelo; valida, guarda y recalcula; 422 con los
problemas si es inválido).
Modelos (`/modelos-costos`): `GET ""` (predefinidos + perfiles, cada uno con `clave`, `propio`, `id`) · `GET /{codigo}` ·
`POST /perfiles` · `PUT /perfiles/{id}` · `DELETE /perfiles/{id}` (nombre único; 422 si el modelo es inválido).
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

**Pruebas** (desde `backend`): `python -m unittest discover -s tests`. Total: **150** (lector B-1 15, especificaciones
20, motor de coincidencia 17, modos de recursos 10, Excel de bibliotecas 8, cronograma 22, exportación 9, base de datos
30, modelo de costos 15, perfiles 4). En un entorno sin los PDF reales se saltan 15. Las pruebas con los PDF reales leen las variables `B1_PDF` y `ESP_PDF`; sin ellas se **saltan** (no fallan).
En CMD: `set B1_PDF=C:\proyectos\pruebas\b1.pdf` y `set ESP_PDF=C:\proyectos\pruebas\especificaciones.pdf`.

**Aplicar el parche del 26-nov** (Git para Windows, desde la raíz del repo): `git apply menu-lateral-y-costos.patch`. Al
arrancar se agregan solas la columna `proyecto.modelo_costos` y la tabla `perfil_costos`: **no hace falta `--reset`**. El frontend
usa `npm run dev` como siempre.

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
- Los PDF de las convocatorias son **con texto** (no escaneados). Los escaneados requerirían OCR (pendiente).

---

## 11. Lo que falta (hoja de ruta)

Prioridad sugerida: primero **verificar con el usuario** lo marcado [POR PROBAR], luego lo siguiente.

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
- Plazo **inverso**: dado un plazo total o un hito, calcular cuadrillas necesarias (existe el helper
  `personas_necesarias` en `cronograma/motor.py`, sin interfaz); plazo óptimo con curva costo-plazo.
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
- Condiciones legales y de privacidad de la biblioteca pública y de bases de terceros (PRESCOM, Kabal, ZARCO).
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

1. Leer este archivo y `README.md`.
2. Pedir al usuario qué probó desde la última vez y qué vio (capturas y el texto de la ventana de `uvicorn` si algo falló).
3. Correr `python -m unittest discover -s tests` con `B1_PDF` y `ESP_PDF` definidos; deben pasar las 150 sin saltadas.
4. Si algo marcado [POR PROBAR] falla en su computador, **arreglarlo antes** de añadir módulos nuevos.
5. Confirmar que el parche `menu-lateral-y-costos.patch` está aplicado y que la interfaz nueva (menú, modelo de cálculo,
   perfiles) funciona en su navegador; pedir capturas.
6. Confirmar con el usuario la prioridad del siguiente módulo (sección 11, etapa 1). Candidatos inmediatos: control de propuesta
   en pantalla, descuento del 13 % de IVA, modelo propio desde cero, crear proyecto desde cero.
7. Al terminar cada módulo: pruebas nuevas, README y este archivo actualizados (sección 3 y 9), y entregar el cambio
   con instrucciones exactas para Windows/CMD.

---

## 16. Registro de cambios

**26-nov-2026**
- Revisión del repositorio `casoval/rinocost` (carpetas `backend`, `frontend`, `docker-compose.yml`, `README.md`; este archivo no
  estaba en el repo: conviene agregarlo en la raíz). Corrección de `vincular_item` (relación `item.apu`).
- Lectura del D.S. 0181 (NB-SABS) y de la planilla `APU_Alonso_de_Ibanez_D11_corregido.xlsx` (17 hojas B-2).
  Conclusión: el decreto **no** define el B-2 ni sus porcentajes; sí fija garantías, regla del 85 %, antigüedad del precio
  referencial y anticipo.
- Nuevo paquete `app/costos/` (motor de modelos de cálculo, predefinidos, control de propuesta) y `services/costos.py`.
- El precio del ítem sale del modelo del proyecto; nuevos campos `precio` y `desglose` en el APU; Excel con indirectos.
- Perfiles propios (`perfil_costos`), elección del cálculo al importar el B-1, panel «Modelo de cálculo» en el proyecto con
  avisos de rango y «Guardar como perfil».
- Menú lateral con Proyectos, Bibliotecas, Modelos de cálculo y Configuración.
- Pruebas: de 129 a 150. Entrega como parche `menu-lateral-y-costos.patch`.
