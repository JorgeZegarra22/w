# Benter Perú v1.0.0

Benter Perú procesa documentos hípicos de Monterrico, conserva la evidencia de
los datos extraídos y calcula pronósticos por carrera para consultarlos en un
dashboard local.

## Entregables

| N.º | Entregable | Resultado |
| --- | --- | --- |
| 1 | Núcleo de ingesta | Descubrimiento responsable, almacenamiento por SHA-256, extracción e ingesta idempotente con trazabilidad. |
| 2 | Integración con datos reales | CLI de recolección y procesamiento local, con extracción de las tablas de participantes del programa. |
| 3 | Resolución de entidades | Normalización de caballos, jinetes, preparadores y studs, con vinculación a carreras y aislamiento de identidades sin confirmar. |
| 4 | Historial y características | Importación CSV atómica y variables históricas calculadas con resultados anteriores a la fecha de la carrera. |
| 5 | Motor predictivo de referencia | Baseline sintético Logit + Softmax y probabilidades de Placé mediante Plackett–Luce. |
| 6 | Dashboard | Streamlit con las vistas de resumen, carreras y predicciones sobre una conexión de solo lectura. |
| 7 | Recolección histórica | Scraper con Playwright y plantilla CSV implementados en `codex/entregable-7-historical-scraper`. Esta etiqueta incluye el importador CSV del Entregable 4. |
| 8 | Modelo histórico | LightGBM con inferencia dinámica por carrera, artefactos locales y validación de integridad del modelo. |
| 9 | Estrategia de apuestas | EV y Kelly fraccional con cuotas manuales, más combinaciones teóricas de Exacta y Trifecta. |
| 10 | Revista y automatización | Extracción y materialización de picks de «Estudie su Polla», visualización y reporte diario local. |

## Arquitectura

- **SQLite y Alembic** almacenan documentos, versiones, hechos con evidencia, entidades, carreras, historial y picks. Los PDFs quedan en el almacenamiento local de blobs.
- **LightGBM** calcula probabilidades para los participantes de cada carrera a partir de sus condiciones y del historial disponible antes de su fecha. El modelo y el dataset se mantienen en archivos locales.
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
`var/ml/real-model/` o configura `BENTER_REAL_MODEL_PATH` y
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
