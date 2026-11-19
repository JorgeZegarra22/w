# Operación local del pipeline diario

El pipeline diario usa la recolección HTTP responsable, materializa programas y
“Estudie su Polla”, y genera un reporte JSON con predicciones y combinaciones
teóricas para las carreras de la fecha solicitada. No persiste cuotas ni realiza
apuestas.

## Requisitos

1. Instalar el proyecto y sus dependencias en un entorno virtual.
2. Configurar `BENTER_SOURCE_URL`, `BENTER_USER_AGENT`,
   `BENTER_DATABASE_PATH` y `BENTER_BLOB_ROOT`.
3. Mantener el modelo y dataset locales en `var/ml/real-model/`, o definir
   `BENTER_REAL_MODEL_PATH` y `BENTER_REAL_DATASET_PATH`.
4. Verificar que el SHA-256 del modelo coincide con el artefacto fijado por el
   proyecto.

Ejecución manual:

```powershell
python scripts/daily_pipeline.py --date 2026-11-22
```

La salida estándar es JSON. Si la revista no se publica, el proceso termina con
`completed_with_warnings`. Si fue descubierta pero está corrupta, carece de capa
de texto o no se puede interpretar con confianza, el proceso termina con error.

## Programador de tareas de Windows

Cree una tarea con el usuario que posee la base de datos, blobs y artefactos del
modelo. Use como programa el `python.exe` del entorno virtual, como argumentos
`scripts/daily_pipeline.py` y como directorio inicial la raíz del repositorio.
Configure las variables de entorno en un script local protegido que active el
entorno y ejecute el comando. Programe viernes y sábados con una hora que respete
la publicación de la fuente.

## cron

En Linux, un ejemplo para viernes y sábados a las 08:00 es:

```cron
0 8 * * 5,6 cd /ruta/privada/hipico && . .venv/bin/activate && python scripts/daily_pipeline.py
```

No se incluye GitHub Actions: la base SQLite, los PDFs, los blobs, el dataset y
el modelo son artefactos locales ignorados por Git. Ejecutar el trabajo en CI sin
ellos produciría un resultado incompleto o engañoso.

## Interpretación segura

- `★ n`: selección confirmada del periodista en orden `n`.
- `⚠ texto`: selección preservada para revisión humana; no fue reasignada por
  similitud.
- `-`: la revista no seleccionó al caballo o no hay revista disponible.
- Las Exactas y Trifectas del reporte son probabilidades teóricas. Sin cuotas
  reales no existe recomendación financiera ni cálculo EV/Kelly.
