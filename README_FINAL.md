# Benter Perú v2.0.0

Benter Perú procesa documentos hípicos de Monterrico, conserva la evidencia de
los datos extraídos y calcula pronósticos por carrera para consultarlos en un
dashboard local. La evolución de **Benter Perú v1.0.0** incorpora en v2.0.0 un
ensamble de **LightGBM, XGBoost y Random Forest** con pesos fijos 40/40/20. El
Analista Senior y el Generador de Boletos usan las probabilidades del ensamble.
El tag histórico `v1.0.0` conserva el punto de publicación original.

## Entregables

| N.º | Entregable | Resultado |
| --- | --- | --- |
| 1 | Núcleo de ingesta | Descubrimiento responsable, almacenamiento por SHA-256, extracción e ingesta idempotente con trazabilidad. |
| 2 | Integración con datos reales | CLI de recolección y procesamiento local, con extracción de las tablas de participantes del programa. |
| 3 | Resolución de entidades | Normalización de caballos, jinetes, preparadores y studs, con vinculación a carreras y aislamiento de identidades sin confirmar. |
| 4 | Historial y características | Importación CSV atómica y variables históricas calculadas con resultados anteriores a la fecha de la carrera. |
| 5 | Motor predictivo de referencia | Baseline sintético Logit + Softmax y probabilidades de Placé mediante Plackett–Luce. |
| 6 | Dashboard | Streamlit con las vistas de resumen, carreras y predicciones sobre una conexión de solo lectura. |
| 7 | Recolección histórica | Scraper con Playwright y plantilla CSV implementados en `codex/entregable-7-historical-scraper`. `master` incluye el importador CSV del Entregable 4. |
| 8 | Modelo histórico | LightGBM con inferencia dinámica por carrera, artefactos locales y validación de integridad del modelo. |
| 9 | Estrategia de apuestas | EV y Kelly fraccional con cuotas manuales, más combinaciones teóricas de Exacta y Trifecta. |
| 10 | Revista y automatización | Extracción y materialización de picks de «Estudie su Polla», visualización y reporte diario local. |
| 11 | Programa oficial de Monterrico | Recolección del programa con Playwright, almacenamiento de perfiles por inscripción y consulta de retrospectos y aprontes en el dashboard. |
| 12 | Analista Senior y Generador de Boletos | Pronósticos narrativos basados en LightGBM y perfiles oficiales. Boletos de llegada en orden o en Box y apuestas concatenadas, incluido Pick 6. |
| 13 | Ensamble predictivo | LightGBM, XGBoost y Random Forest con pesos fijos 40/40/20 y 18 características calculadas con historial anterior a cada jornada. |

## Arquitectura

- **SQLite y Alembic** almacenan documentos, versiones, hechos con evidencia, entidades, carreras, historial y picks. Los PDFs quedan en el almacenamiento local de blobs.
- **Ensamble (LightGBM + XGBoost + Random Forest)** calcula probabilidades normalizadas por carrera. El artefacto y el dataset se mantienen en archivos locales y se verifican por SHA-256.
- **Streamlit** consulta SQLite en modo de solo lectura y calcula predicciones y análisis de cuotas en memoria. La columna «Pick del Periodista» usa `★` para un pick confirmado, `⚠` para revisión y `-` cuando no hay un pick disponible para el participante.

## Puesta en marcha

Desde la raíz del repositorio, instala el proyecto en un entorno virtual de
Python 3.12 o 3.13.

```powershell
python -m pip install -e .
```

Usa `.env.example` como referencia y exporta las variables en el entorno de la
sesión. Configura `BENTER_DATABASE_PATH` para que el dashboard y el pipeline
usen la misma base. Para el pipeline, define también `BENTER_SOURCE_URL`,
`BENTER_USER_AGENT` y `BENTER_BLOB_ROOT`. Coloca el modelo y el dataset en
`var/ml/real-model/` o configura `BENTER_ENSEMBLE_MODEL_PATH` y
`BENTER_REAL_DATASET_PATH`. El pipeline aplica las migraciones al iniciar.

Abre el dashboard cuando la base esté migrada y tenga datos.

```powershell
streamlit run src/benter_peru/ui/app.py
```

Ejecuta la ingesta y el reporte para la fecha local del equipo.

```powershell
python scripts/daily_pipeline.py
```

Para seleccionar una fecha concreta, usa `--date`, por ejemplo
`python scripts/daily_pipeline.py --date 2026-11-22`. El script emite un
reporte JSON. Si la revista está ausente, el reporte incluye una advertencia y
el flujo continúa. Si la revista fue descubierta y es inválida, la ejecución
falla de forma explícita. La [guía del pipeline diario](docs/operations/daily-pipeline.md)
documenta la programación local.

## Scraper del Programa Oficial de Monterrico

Con el proyecto instalado, prepara Chromium y ejecuta el scraper desde la raíz
del repositorio. Configura `BENTER_USER_AGENT` con tu identificador y un enlace
de contacto real. Indica en `--blobs` una ruta fuera del repositorio.

La ingesta oficial de Monterrico cubre **34 carreras y 289 perfiles** del fin
de semana del 21 al 23 de noviembre de 2026.

| Fecha | Reunión | Carreras | ID de partida |
| --- | --- | ---: | ---: |
| Sábado 21/11/2026 | `2026-476` | 12 | `863740` |
| Domingo 22/11/2026 | `2026-477` | 12 | `863752` |
| Lunes 23/11/2026 | `2026-481` | 10 | `863729` |

```powershell
python -m playwright install chromium
$env:BENTER_USER_AGENT = 'BenterPeruBot/1.0 (+https://example.org/contacto)' # Sustituye la URL
$db = 'var/official-2026-11-21.sqlite3'
$blobs = 'C:/ruta/privada/blobs'
python -m scripts.official_program --date 2026-11-21 --seed-race 863740 --expected-races 12 --captures var --database $db --blobs $blobs
python -m scripts.official_program --date 2026-11-22 --seed-race 863752 --expected-races 12 --captures var/official-weekend --database $db --blobs $blobs
python -m scripts.official_program --date 2026-11-23 --seed-race 863729 --expected-races 10 --captures var/official-weekend --database $db --blobs $blobs
```

El scraper busca enlaces en la vista de reunión y usa `--seed-race` para
descubrirlos desde una ficha oficial si ese listado está vacío. `--expected-races`
verifica el total antes de importar. `--captures var` guarda el HTML renderizado
localmente y reutiliza las capturas disponibles en esa carpeta. Si ya tienes
Microsoft Edge instalado, puedes usar `--channel msedge` en lugar de instalar
Chromium. Consulta la [guía técnica del scraper](docs/superpowers/specs/2026-11-19-official-scraper-design.md).

Para ver los perfiles, abre el dashboard con la misma base que usaste en
`--database`.

```powershell
$env:BENTER_DATABASE_PATH = (Resolve-Path 'var/official-2026-11-21.sqlite3').Path
streamlit run src/benter_peru/ui/app.py
```

En **Carreras**, elige una de las tres reuniones y una carrera. Expande la fila
de un caballo para ver **Última forma** y **Aprontes recientes**. Para ver a Waytt,
elige **2026-476 → Carrera 1**. Para ver a Shotra, Mr Peggy y los demás inscritos
del Derby Nacional, elige **2026-477 → Carrera 10**. Los perfiles se guardan con
la URL oficial, la fecha de captura y el hash del HTML.

## Analista Senior y Generador de Boletos

En **Estrategia de Apuestas**, selecciona una reunión y una carrera. El
**Pronóstico del Analista Senior** muestra el favorito del modelo, la última
actuación y el apronte más reciente cuando están disponibles. Las cuotas reales
ingresadas a ganador se usan para identificar apuestas con EV positivo.

En **Generador de Boletos**, elige el tipo de apuesta. Para una llegada, elige
los mandiles en orden o activa **En Box**. Para una concatenada, selecciona la
carrera inicial entre las ventanas elegibles, Top 2 o Top 3 y el límite de
líneas. El boleto muestra los mandiles, el número de líneas y la cobertura
estimada. Para ver el EV, indica el costo por línea y los dividendos brutos de
todas las líneas cubiertas.

El panel muestra **SIMULACIÓN MATEMÁTICA** por defecto. **VENTA CONFIRMADA**
identifica una referencia de venta que ingresaste tras verificarla en el
programa o en taquilla.

## Entrenamiento del ensamble

El artefacto local que usa el dashboard es `var/ml/real-model/ensemble_model_v1.pkl`.
Para reproducir el entrenamiento, genera un candidato en una ruta nueva.

```powershell
python -m benter_peru.ml.entrenar_ensemble --dataset var/ml/real-model/dataset_oficial_resultados.csv --output var/ml/real-model/ensemble_candidate.pkl
```

El comando imprime el corte temporal, AUC-ROC y Log Loss por inscripción y
el SHA-256 del candidato. El corte reserva el 18 de abril de 2026 y las fechas
posteriores para validación. Las estadísticas usan resultados conocidos antes
de cada fecha. El dashboard valida el hash fijado del artefacto y
normaliza el ensamble después de combinar los tres puntajes.

La comparación usó 25.138 inscripciones de entrenamiento y 6.280 de
validación, con las mismas 18 características para todos los modelos. Las
métricas corresponden a los puntajes binarios por inscripción antes de la
normalización por carrera.

| Modelo | AUC-ROC ↑ | Log Loss ↓ |
| --- | ---: | ---: |
| LightGBM reentrenado | 0,669679 | 0,375186 |
| XGBoost | 0,681292 | 0,370790 |
| Random Forest | 0,677695 | 0,371599 |
| Ensamble 40/40/20 | 0,681756 | 0,370045 |

En este conjunto reservado, el ensamble mejoró el AUC-ROC en 0,01208 y redujo
el Log Loss en 0,00514 frente a LightGBM reentrenado con el mismo protocolo.
