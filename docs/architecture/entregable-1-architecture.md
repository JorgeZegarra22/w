# BENTER PERÚ — Arquitectura del Entregable 1

**Estado:** Propuesta para revisión final

**Fecha:** 18 de noviembre de 2026

**Alcance:** Recolección, persistencia, deduplicación y extracción documental trazable de El Informativo Hípico

**Fuera de alcance:** Motor estadístico, historial deportivo, interfaz web y visión artificial

## 1. Propósito

El Entregable 1 construye la primera vertical operativa de BENTER PERÚ. Una corrida debe descubrir publicaciones de El Informativo Hípico, identificar un programa y una edición real de «Estudie su polla», descargar los documentos de forma responsable, calcular su SHA-256, conservar versiones, extraer hechos con evidencia y producir un reporte auditable.

La arquitectura prioriza, en este orden:

1. Calidad y procedencia de los datos.
2. Idempotencia de cada operación.
3. Evidencia suficiente para justificar cada hecho.
4. Recuperación segura después de fallos.
5. Portabilidad de SQLite a PostgreSQL.

Ningún componente debe completar datos faltantes mediante inferencia no declarada. Un valor desconocido permanece desconocido.

## 2. Restricciones normativas

- El PDF real se almacena únicamente en un directorio local configurable fuera del repositorio.
- El repositorio conserva código, migraciones, fixtures sintéticos o de dominio público y documentación; nunca el PDF real.
- La base de datos conserva hash, metadatos, procedencia, hechos derivados y una clave de almacenamiento local, no una copia del documento.
- Los fragmentos de evidencia se limitan al mínimo necesario para justificar el hecho; no se almacena el texto integral de una página.
- Los documentos se tratan como entrada hostil: no se ejecutan scripts, macros, enlaces ni instrucciones contenidas en ellos.
- No se instala PostgreSQL ni Tesseract durante este entregable.
- OCR permanece como puerto desactivado. Si el documento real carece de capa de texto utilizable, se registra `needs_ocr` y se solicita aprobación para el plan B.
- No se incluyen secretos, credenciales ni rutas personales en el repositorio o en los logs.
- Los accesos de red respetan `robots.txt`, condiciones observables de la fuente, límites por host y respuestas `Retry-After`.
- `robots.txt` es una señal técnica de acceso, no una declaración completa de derechos de autor o autorización legal.

## 3. Decisión arquitectónica

### 3.1 Enfoque elegido: monolito modular con puertos y adaptadores

El sistema se despliega como una sola aplicación y una sola unidad transaccional. Internamente separa orquestación, políticas, red, descubrimiento, almacenamiento, extracción, validación y observabilidad mediante contratos estables.

Este enfoque ofrece transacciones simples y pruebas rápidas en SQLite sin acoplar la lógica de dominio a HTTP, al sistema de archivos o al motor SQL. Cada adaptador puede reemplazarse posteriormente: SQLite por PostgreSQL, almacenamiento local por un objeto remoto, o extracción textual por OCR aprobado.

### 3.2 Alternativas consideradas

| Alternativa | Ventaja | Riesgo | Decisión |
|---|---|---|---|
| Script ETL lineal | Inicio rápido | Mezcla red, persistencia y parsing; difícil de reanudar y auditar | Rechazada |
| Monolito modular | Transacciones simples, límites claros, bajo costo operativo | Requiere disciplina en interfaces | Elegida |
| Microservicios y cola externa | Escalamiento independiente | Complejidad, costo y fallos distribuidos prematuros | Rechazada para este entregable |

## 4. Diagramas autoritativos

Los archivos siguientes son parte de esta especificación:

- [Diagrama de componentes](diagrams/entregable-1-components.mmd) — Mermaid.
- [Flujo del pipeline](diagrams/entregable-1-pipeline.mmd) — Mermaid.
- [ERD completo](diagrams/entregable-1-erd.puml) — PlantUML con notación crow's foot.
- [ERD secundario](diagrams/entregable-1-erd.mmd) — representación Mermaid para compatibilidad futura.
- [Secuencia de corrida exitosa](diagrams/entregable-1-sequence-success.mmd) — Mermaid.
- [Secuencia de reintento y fallo](diagrams/entregable-1-sequence-retry-failure.mmd) — Mermaid.

PlantUML es la fuente autoritativa del ERD porque Mermaid no renderizó de forma fiable el grafo físico completo en la pestaña visual. Mermaid continúa siendo apropiado para componentes, flujo y secuencias.

## 5. Componentes

### 5.1 `RunOrchestrator`

Coordina una corrida, crea o recupera su identidad, aplica políticas, solicita descubrimiento, registra versiones, agenda extracciones y finaliza el `run_report`. No conoce detalles de HTTP, HTML, PDF o SQL.

### 5.2 `PolicyGate`

Evalúa `robots.txt`, el host permitido, el esquema de URL y la política registrada para la fuente. Conserva una instantánea con hash y fecha. Una denegación produce un resultado auditable y evita la descarga.

### 5.3 `ResponsibleHttpClient`

Aplica User-Agent identificable, límite por host, concurrencia uno por defecto, caché condicional, tiempos máximos, validación de redirecciones, reintentos y backoff. Registra cada intento sin guardar cuerpos sensibles en logs.

Valores iniciales configurables:

- Intervalo mínimo por host: 2 segundos.
- Máximo de intentos HTTP: 4.
- Backoff: exponencial desde 2 segundos, máximo 60 segundos, con jitter.
- Concurrencia por host: 1.
- Tamaño máximo de documento: 100 MiB.
- Tiempo máximo de conexión: 10 segundos.
- Tiempo máximo de lectura: 60 segundos.

### 5.4 `ElInformativoConnector`

Convierte páginas y enlaces de la fuente en candidatos canónicos. Inspecciona HTML, atributos, enlaces salientes y scripts embebidos. El orden de preferencia es:

1. HTML estático y enlaces públicos.
2. Peticiones estructuradas públicas descubiertas mediante inspección de red.
3. Renderizado dinámico con un adaptador de navegador únicamente si las dos opciones anteriores no permiten cumplir la aceptación.

La detección de «Estudie su polla» se basa en contexto de enlace, procedencia, tipo de contenido y validación del documento. El nombre del archivo es una señal auxiliar, nunca la identidad primaria.

### 5.5 `LocalBlobStore`

Escribe primero a un archivo temporal dentro de `BENTER_DATA_DIR`, calcula SHA-256 durante el streaming y promueve el archivo mediante renombrado atómico a una clave derivada del hash. `put_if_absent` reutiliza el objeto si el hash ya existe. Ninguna ruta absoluta entra en logs o fixtures.

### 5.6 Repositorios y `UnitOfWork`

Encapsulan las operaciones SQL y delimitan transacciones. Las restricciones únicas son la última barrera contra duplicados; la lógica de aplicación no sustituye a las constraints.

### 5.7 `ExtractionRouter`

Inspecciona el PDF y selecciona un extractor. En el Entregable 1 solo puede activar extracción de capa textual. Si no existe texto con coordenadas suficiente, devuelve `needs_ocr` y no intenta OCR silenciosamente.

### 5.8 `TextPdfExtractor`

Usa `pdfplumber` como extractor principal por su soporte de palabras y bounding boxes. `pypdf` actúa como verificación y fallback de texto, no como fuente de bounding boxes. Produce candidatos con página, valor crudo, fragmento mínimo, región y método.

### 5.9 `FactValidator`

Normaliza valores, valida campos conocidos, calcula confianza y genera el fingerprint. La confianza es específica de la regla de extracción; no se interpreta como probabilidad estadística de carrera.

El umbral inicial de revisión es configurable y vale `0.80`. Un valor inferior crea `requires_review=true`. El hecho y su evidencia se conservan.

### 5.10 `RunReporter`

Agrega contadores y guarda un `run_report` exactamente una vez por corrida. También emite un resumen JSON local sin contenido documental.

## 6. Flujo de datos

1. El disparador entrega `source_code` y `correlation_id`.
2. El orquestador crea o recupera la corrida.
3. La puerta de políticas evalúa la fuente y registra su evidencia.
4. El conector descubre publicaciones y documentos canónicos.
5. La descarga se transmite a almacenamiento temporal mientras se calcula SHA-256.
6. El blob se promueve solo si su hash es nuevo.
7. Se registran el documento lógico y la versión `(document_id, blob_sha256)`.
8. El fingerprint de extracción decide si reutilizar un resultado previo.
9. El extractor produce candidatos con página, bounding box y snippet.
10. El validador normaliza y marca hechos de baja confianza.
11. Hechos, evidencia y elementos de revisión se guardan en una transacción.
12. El reporte de corrida y el checkpoint se finalizan después del commit.

El flujo completo se representa en [entregable-1-pipeline.mmd](diagrams/entregable-1-pipeline.mmd). La secuencia nominal está en [entregable-1-sequence-success.mmd](diagrams/entregable-1-sequence-success.mmd): separa la promoción del blob de la transacción de metadatos para que una interrupción sea recuperable, y coloca el checkpoint después del `run_report` para no declarar trabajo incompleto como confirmado.

## 7. Modelo de datos

### 7.1 Identidad y procedencia

- `source_registry`: configuración estable de una fuente.
- `source_policy_snapshots`: evidencia de políticas y robots observados.
- `source_checkpoints`: último punto confirmado de procesamiento.
- `crawl_runs`: identidad y estado de cada ejecución.
- `fetch_attempts`: historial de intentos HTTP.
- `http_cache_entries`: validadores y cuerpos cacheados por fingerprint.

### 7.2 Publicaciones y documentos

- `publications`: recurso editorial lógico identificado por fuente y URL canónica.
- `publication_versions`: contenido observado de una publicación.
- `documents`: recurso documental lógico.
- `publication_document_links`: evidencia de que una versión editorial enlazó un documento.
- `blob_objects`: objeto físico direccionado por SHA-256.
- `document_versions`: asociación de una versión lógica con el objeto descargado.

### 7.3 Extracción y revisión

- `extraction_runs`: ejecución reproducible de un extractor y configuración.
- `extracted_facts`: hecho normalizado y versionado por fingerprint.
- `fact_evidence`: página, región, snippet y método de extracción.
- `review_items`: motivo y estado de revisión.
- `review_decisions`: historial inmutable de decisiones humanas.
- `processing_tasks`: trabajo recuperable con clave de idempotencia.

### 7.4 Observabilidad

- `run_reports`: resumen único por corrida.
- `run_metrics`: contadores nombrados extensibles.

### 7.5 Constraints e índices obligatorios

| Tabla | Restricción única |
|---|---|
| `source_registry` | `code` |
| `source_checkpoints` | `(source_id, checkpoint_key)` |
| `crawl_runs` | `correlation_id` |
| `fetch_attempts` | `(crawl_run_id, url, attempt_no)` |
| `http_cache_entries` | `request_fingerprint` |
| `publications` | `(source_id, canonical_url)` |
| `publication_versions` | `(publication_id, content_sha256)` |
| `documents` | `(source_id, canonical_url)` |
| `publication_document_links` | `(publication_version_id, document_id, discovered_url)` |
| `blob_objects` | `sha256` |
| `document_versions` | `(document_id, blob_sha256)` |
| `extraction_runs` | `input_fingerprint` |
| `extracted_facts` | `fact_fingerprint` |
| `review_items` | `fact_id` |
| `processing_tasks` | `idempotency_key` |
| `run_reports` | `crawl_run_id` |
| `run_metrics` | `(run_report_id, metric_name)` |

Índices no únicos cubren estados y reanudación: `processing_tasks(status, available_at)`, `document_versions(processing_status)`, `review_items(status, created_at)`, `crawl_runs(source_id, started_at)` y fechas de primera/última detección.

## 8. Contratos de interfaces

Los nombres expresan contratos lógicos. La implementación posterior definirá tipos Python equivalentes sin alterar su semántica.

### 8.1 Descubrimiento

`SourceConnector.discover(context) -> iterable[DiscoveryCandidate]`

`DiscoveryCandidate` contiene:

- `candidate_type`: `publication` o `document`.
- `source_code`.
- `canonical_url`.
- `discovered_url`.
- `parent_publication_url`, si existe.
- `title` y `published_at`, si la fuente los declara.
- `link_context` mínimo.
- `discovery_method`: `html`, `script`, `endpoint` o `rendered`.
- `observed_at`.

### 8.2 Políticas

`PolicyGate.evaluate(url, user_agent) -> PolicyDecision`

`PolicyDecision` contiene `allowed`, `reason_code`, `crawl_delay`, `snapshot_hash` y `observed_at`. Una decisión denegada no puede ser ignorada por el conector.

### 8.3 Red

`FetchClient.fetch(request) -> FetchResult`

`FetchRequest` contiene URL, propósito, cabeceras condicionales, tamaño máximo y correlation ID. `FetchResult` contiene estado, URL final validada, cabeceras permitidas, stream o referencia cacheada, timings y número de intento.

### 8.4 Almacenamiento

`BlobStore.put_if_absent(stream, expected_media_type) -> StoredBlob`

`StoredBlob` contiene SHA-256, tamaño, tipo detectado, `storage_key` relativo y `created`. No devuelve una ruta absoluta persistible.

### 8.5 Registro documental

`DocumentRepository.register_version(candidate, stored_blob, crawl_run_id) -> DocumentVersionResult`

El resultado contiene `document_id`, `document_version_id`, `created` y estado. Una colisión de constraint se resuelve leyendo la fila existente, no repitiendo la descarga.

### 8.6 Extracción

`DocumentExtractor.extract(document_handle) -> ExtractionBundle`

`ExtractionBundle` contiene:

- Identidad y versión del extractor.
- Hash de configuración.
- Estado `extracted`, `needs_ocr` o `failed`.
- Candidatos de hechos.
- Diagnósticos sin contenido completo del documento.

Cada `FactCandidate` contiene tipo, sujeto provisional, valor crudo, valor propuesto, página uno-basada, bounding box opcional, snippet mínimo, método y señales de confianza.

### 8.7 Validación

`FactValidator.validate(candidate, extraction_context) -> ValidatedFact`

`ValidatedFact` contiene valores crudo y normalizado, confianza entre 0 y 1, `requires_review`, `reason_codes`, fingerprint y una o más evidencias.

### 8.8 Tareas y reintentos

`TaskRepository.claim_or_create(idempotency_key, task_type, target) -> ProcessingTask`

Solo una tarea activa puede existir por clave. Los estados son `pending`, `running`, `deferred`, `completed` y `failed`.

### 8.9 Reporte

`RunReporter.finalize(crawl_run_id, counters, status) -> RunReport`

Estados de corrida: `completed`, `completed_with_reviews`, `partial_failure`, `deferred` y `failed`.

## 9. Estrategia de idempotencia

La idempotencia se aplica en cinco niveles:

1. **Corrida:** `correlation_id` evita duplicar la identidad de una ejecución reanudada.
2. **Recurso lógico:** fuente más URL canónica identifica publicación o documento.
3. **Contenido:** SHA-256 identifica el objeto físico y la versión.
4. **Extracción:** `input_fingerprint = SHA256(blob_sha256 + extractor_name + extractor_version + config_hash)`.
5. **Hecho:** `fact_fingerprint = SHA256(input_fingerprint + fact_type + subject_key + normalized_value + evidence_fingerprint)`.

Los upserts se implementan mediante inserción y manejo portable de violación única. No se depende de `INSERT OR REPLACE`, `ON CONFLICT` específico ni bloqueo exclusivo de SQLite.

El checkpoint se actualiza únicamente después de que los datos dependientes y el `run_report` se confirman. Un proceso interrumpido antes del commit repite la operación con las mismas claves.

## 10. Canonicalización

La canonicalización:

- Normaliza esquema y host a minúsculas.
- Elimina fragmentos URL.
- Resuelve rutas relativas.
- Elimina puertos predeterminados.
- Ordena parámetros permitidos.
- Descarta parámetros conocidos de seguimiento.
- Conserva parámetros que cambian la identidad del documento.
- Valida cada redirección contra esquemas `https` o `http` y hosts permitidos.
- Aplica reglas explícitas a enlaces compartidos de Google Drive sin adivinar IDs.

La URL original y cada salto relevante permanecen en procedencia; canonicalizar no significa perder evidencia.

## 11. Descarga y seguridad documental

- Solo se aceptan `http` y `https`.
- El host inicial y cada redirección se validan para prevenir SSRF.
- Se rechazan direcciones privadas o locales cuando provienen de una fuente externa.
- Se verifica TLS.
- Se limita tamaño antes y durante el streaming.
- Se valida `%PDF-` y tipo detectado; `Content-Type` por sí solo no es suficiente.
- El nombre remoto nunca se utiliza como ruta local.
- La clave física deriva del SHA-256.
- Los temporales se limpian tras fallo; no se elimina automáticamente un blob confirmado.
- Los parsers operan sin ejecutar contenido incrustado.
- Los errores exponen códigos y contexto técnico, no bytes ni texto completo.

## 12. Extracción del PDF real

### 12.1 Puerta de decisión

Después de descubrir y registrar el PDF real se evalúa, por página:

- Cantidad de palabras recuperables.
- Disponibilidad de coordenadas.
- Proporción de páginas con texto coherente.
- Diferencia entre texto de `pdfplumber` y verificación de `pypdf`.

Si la mayoría de páginas de contenido ofrece palabras y coordenadas útiles, se usa extracción textual. Si predominan páginas sin texto o con texto ilegible, la versión queda `needs_ocr`, el reporte explica la evidencia y no se instala Tesseract.

### 12.2 Evidencia

Cada hecho incluye:

- Documento y versión de origen.
- Página uno-basada.
- Bounding box cuando `pdfplumber` la ofrece.
- Snippet máximo de 500 caracteres, reducido cuando baste menos.
- Método `text` o, en una etapa posterior aprobada, `ocr`.
- Identidad y versión del extractor.
- Confianza y motivos.

### 12.3 Revisión humana

Un hecho se marca para revisión cuando:

- Confianza menor a `BENTER_REVIEW_CONFIDENCE_THRESHOLD`.
- Falta un campo obligatorio de su tipo.
- Dos reglas producen valores incompatibles.
- El texto fue recuperado sin bounding box.
- La entidad no puede resolverse con evidencia suficiente.

La revisión no elimina el hecho. Una decisión posterior se registra como aceptar, corregir o rechazar, preservando el valor original.

## 13. Política de reintentos y fallos

### 13.1 HTTP

Son transitorios: errores de conexión, timeout, 408, 425, 429, 500, 502, 503 y 504. `Retry-After` tiene prioridad. Los demás 4xx son permanentes salvo regla documentada de la fuente.

Después del máximo de intentos, la tarea pasa a `deferred` con `available_at`. Una corrida posterior reclama la misma clave. Cada intento queda en `fetch_attempts`.

### 13.2 Extracción

Errores temporales de I/O permiten hasta dos intentos. Un PDF corrupto, cifrado sin acceso o incompatible produce fallo permanente con diagnóstico. La versión documental se conserva.

### 13.3 Confianza baja

No es un fallo técnico. El hecho y su evidencia se confirman, se crea o reutiliza un `review_item` y la corrida puede terminar `completed_with_reviews`.

La secuencia completa está en [entregable-1-sequence-retry-failure.mmd](diagrams/entregable-1-sequence-retry-failure.mmd).

## 14. Observabilidad

### 14.1 Logs estructurados

Cada evento JSON contiene, cuando aplique:

- `timestamp` UTC.
- `level`.
- `event`.
- `correlation_id` y `crawl_run_id`.
- `source_id`, `task_id`, `document_version_id`.
- `attempt_no`, duración y estado.
- `error_code` estable.

No se registran cuerpos HTTP, snippets documentales, secretos, cookies, tokens ni rutas absolutas.

### 14.2 Contadores mínimos

- Publicaciones descubiertas, nuevas y reutilizadas.
- Documentos descubiertos, descargados y deduplicados.
- Bytes descargados.
- Cachés 304 y aciertos locales.
- Extracciones exitosas, `needs_ocr` y fallidas.
- Hechos generados y hechos para revisión.
- Reintentos y fallos por categoría.
- Duración total y por etapa.

### 14.3 `run_report`

El reporte incluye identidad de corrida, fuente, timestamps, estado, checkpoint anterior y nuevo, contadores, lista de códigos de error y referencias a tareas pendientes. Se guarda una vez en base de datos y se imprime como resumen JSON.

## 15. Configuración

Variables previstas:

| Variable | Propósito | Valor local inicial |
|---|---|---|
| `DATABASE_URL` | Conexión portable | `sqlite+pysqlite:///./var/benter.db` |
| `BENTER_DATA_DIR` | Blobs y temporales fuera del repo | Obligatoria para corrida real |
| `BENTER_USER_AGENT` | Identificación del recolector | Obligatoria para corrida real |
| `BENTER_MIN_REQUEST_INTERVAL_MS` | Límite por host | `2000` |
| `BENTER_HTTP_MAX_ATTEMPTS` | Intentos HTTP | `4` |
| `BENTER_HTTP_MAX_BYTES` | Tamaño máximo | `104857600` |
| `BENTER_REVIEW_CONFIDENCE_THRESHOLD` | Umbral de revisión | `0.80` |
| `BENTER_LOG_LEVEL` | Nivel de logs | `INFO` |
| `BENTER_LIVE_TESTS` | Habilita pruebas contra fuente real | `0` |

`.env.example` contendrá nombres y valores no sensibles. `.env`, `var/`, archivos PDF, temporales y `.superpowers/` quedarán ignorados por Git.

## 16. Tecnologías previstas

- Python 3.12.
- SQLAlchemy 2.x y Alembic para persistencia y migraciones.
- SQLite para desarrollo local; PostgreSQL como destino compatible.
- HTTPX para red síncrona o asíncrona, decidido en implementación sin cambiar el contrato.
- BeautifulSoup para HTML.
- `pdfplumber` y `pypdf` para PDFs con capa de texto.
- Pydantic 2.x para configuración y contratos en los límites.
- `structlog` o logging estándar con formateador JSON; se elegirá uno, no ambos.
- Pytest, pytest-cov y un adaptador de HTTP simulado.

No se añade Playwright, OCR, LightGBM, CatBoost ni infraestructura de colas salvo que una prueba del requisito lo justifique y exista aprobación.

## 17. Plan de pruebas

### 17.1 Unitarias

- Canonicalización de URLs y redirecciones.
- Interpretación de robots y política.
- Rate limit y cálculo de backoff con reloj inyectable.
- Clasificación de errores reintentables y permanentes.
- Parsing de publicaciones, programas y enlaces documentales con fixtures HTML.
- SHA-256 streaming y promoción atómica.
- Deduplicación de blobs y versiones.
- Fingerprints de extracción y hechos.
- Reglas deterministas de extracción sobre PDF sintético o de dominio público.
- Página, bounding box, snippet y método.
- Umbral de confianza y creación de revisión.
- Contadores y estado de `run_report`.

### 17.2 Integración local

- Migración desde base vacía en SQLite con foreign keys activas.
- Corrida completa contra un servidor HTTP simulado.
- Respuesta 200 seguida de 304.
- Dos URLs que entregan el mismo hash.
- Documento que cambia de hash y crea nueva versión.
- Interrupción después de guardar blob y recuperación sin duplicados.
- Fallo de extracción que conserva la versión.
- Repetición completa de corrida con conteos estables.

### 17.3 Contratos

Cada adaptador debe pasar el mismo conjunto de pruebas de contrato para `FetchClient`, `BlobStore`, repositorios y extractores. Los tests no dependen de detalles internos.

### 17.4 Prueba real de aceptación

Marcada `live` y deshabilitada por defecto. Requiere User-Agent y directorio de datos explícitos. Ejecuta una sola corrida limitada, respeta políticas, registra al menos una edición real de «Estudie su polla» y un programa, y repite para demostrar ausencia de duplicados.

La prueba real no se ejecuta en cada CI porque depende de una fuente externa cambiante. Sus resultados se guardan como `run_report` local; el PDF no se publica.

### 17.5 Cobertura

Objetivo mínimo del 85 % para canonicalización, parser, deduplicación, reintentos, extracción y reporte. La cobertura global no sustituye los escenarios de idempotencia y recuperación.

Comando de verificación previsto: `pytest -m "not live" --cov`.

## 18. Portabilidad y migración a PostgreSQL

### 18.1 Reglas desde el inicio

- IDs ULID `char(26)` generados por la aplicación.
- Timestamps conscientes de zona, almacenados en UTC.
- Tipos SQLAlchemy portables: texto, booleano, entero, bigint, numeric y datetime.
- Estados como strings con `CHECK`, no enums nativos.
- Sin `AUTOINCREMENT` dependiente de SQLite.
- Sin JSON obligatorio, índices parciales, FTS o triggers específicos.
- Foreign keys activas en SQLite.
- Constraints e índices creados por Alembic.
- Resolución de colisiones mediante constraints y relectura portable.

### 18.2 Migración futura

1. Crear PostgreSQL vacío.
2. Ejecutar todas las migraciones Alembic sin ramas alternativas.
3. Exportar filas por lotes preservando ULIDs y hashes.
4. Importar en orden de dependencias.
5. Comparar conteos, hashes y constraints.
6. Ejecutar pruebas de contrato contra PostgreSQL.
7. Cambiar `DATABASE_URL` sin alterar dominio ni conectores.

No se migra el contenido físico del PDF dentro de PostgreSQL. `storage_key` continúa apuntando al adaptador de blobs configurado.

## 19. Riesgos

| Riesgo | Probabilidad | Impacto | Mitigación | Señal de activación |
|---|---|---|---|---|
| Cambia el HTML o enlace superior | Alta | Alta | Parser por señales múltiples, fixtures y contrato del conector | Cero candidatos o cambio de estructura |
| `robots.txt` o política restringe acceso | Media | Alta | Snapshot, parada segura y reporte | Decisión `denied` |
| Enlace de Google Drive requiere interacción | Media | Alta | Buscar endpoint público estable; navegador solo como fallback aprobado | Descarga no reproducible |
| PDF real es escaneado | Media | Alta | Estado `needs_ocr`; plan B separado | Páginas sin palabras o coordenadas |
| PDF malicioso o corrupto | Media | Alta | Límites, validación de firma, parser aislado y sin ejecución | Error permanente de extracción |
| Dos URLs representan el mismo documento | Alta | Media | SHA-256 global y enlace de procedencia separado | Hash idéntico |
| Parámetros alteran identidad | Media | Media | Allowlist de parámetros y fixtures de canonicalización | Colisiones o versiones mezcladas |
| SQLite oculta incompatibilidad | Media | Alta | Tipos portables, migraciones y compilación PostgreSQL | SQL específico o migration failure |
| Fuente caída durante aceptación | Media | Media | Reintento, tarea diferida y prueba live separada | Timeout/5xx agotados |
| Confianza sin calibrar | Alta | Media | Revisión conservadora y motivos visibles | Exceso de revisiones o errores |
| Crecimiento del almacenamiento | Media | Media | Métricas de bytes y política futura de retención | Umbral de disco configurable |
| Redistribución accidental | Baja | Alta | `.gitignore`, almacenamiento externo y test de repositorio | PDF detectado en Git |

## 20. Cronograma por hitos verificables

Estimación para una persona, sin contar bloqueos externos:

| Hito | Resultado verificable | Duración estimada |
|---|---|---|
| H0 | Arquitectura aprobada y plan de implementación | 0.5 día |
| H1 | Configuración, modelo, migración SQLite y logs | 1 día |
| H2 | HTTP responsable y conector con fixtures | 1.5 días |
| H3 | Blob store, SHA-256, dedup y versionado | 1 día |
| H4 | Extracción determinista y revisión sobre fixtures | 1.5 días |
| H5 | Corrida real limitada y decisión texto/OCR | 1 día |
| H6 | Recuperación, repetición idempotente, cobertura y README | 1 día |

Cada hito termina con pruebas y revisión antes de avanzar. H5 puede detenerse en `needs_ocr` sin invalidar H1–H4.

## 21. Criterios de aceptación trazados

| Criterio | Mecanismo arquitectónico | Verificación |
|---|---|---|
| Descubrir documento real y programa | Conector y candidatos canónicos | Prueba `live` limitada |
| Respetar robots y límites | `PolicyGate` + cliente responsable | Unitarias y registro de política |
| Descargar sin redistribuir | `LocalBlobStore` fuera del repo | Inspección Git y run report |
| Hash y deduplicación | Blob por SHA-256 + constraints | Corrida repetida |
| Versionar cambios | Documento lógico + `document_versions` | Fixture con segundo hash |
| Hechos con evidencia | `extracted_facts` + `fact_evidence` | Tests de extractor |
| Marcar confianza baja | Umbral configurable + `review_items` | Fixture ambiguo |
| Reintentar sin duplicar | `processing_tasks` + idempotency key | Fallo inyectado y reanudación |
| Observabilidad | Logs JSON, métricas y `run_report` | Assertions de integración |
| SQLite portable | Tipos, constraints y Alembic | Migración desde vacío y revisión SQL |
| README completo | H6 | Checklist documental |

## 22. Supuestos explícitos

- El contenido objetivo es público y no requiere eludir autenticación, paywall, CAPTCHA o controles técnicos.
- La primera implementación procesa una fuente a la vez y una descarga concurrente por host.
- Las fechas publicadas sin zona se interpretan en `America/Lima` y se almacenan en UTC conservando el texto original.
- La edición real utilizada será la más reciente que la fuente permita descubrir durante la prueba; su identidad se fija por URL, fecha observada y hash.
- El fixture de CI no será una copia del PDF real.
- El primer parser extrae un conjunto mínimo verificable de campos; ampliar campos no cambia los contratos de evidencia.
- No se automatizan decisiones humanas de corrección en este entregable.

## 23. Preguntas abiertas y decisión predeterminada

Estas preguntas no bloquean la arquitectura, pero sí condicionan la corrida real:

1. **Identidad de contacto del User-Agent.** La corrida real se negará a iniciar si `BENTER_USER_AGENT` no contiene una identificación y medio de contacto definidos por el propietario del proyecto.
2. **Retención de archivos locales.** El Entregable 1 no elimina blobs confirmados automáticamente. Una política de retención se diseñará después de medir volumen y revisar obligaciones.
3. **PDF sin capa textual.** La decisión predeterminada es detener esa tarea en `needs_ocr`, conservar metadatos y solicitar aprobación antes de instalar Tesseract.
4. **Fuente dinámica sin endpoint público estable.** La decisión predeterminada es presentar evidencia y pedir aprobación antes de añadir Playwright como dependencia operativa.
5. **Interfaz de revisión.** Este entregable persiste la cola y permite inspección técnica; una UI de revisión pertenece a una fase posterior.

## 24. Definición de terminado

El Entregable 1 está terminado únicamente cuando:

- Migraciones y pruebas no live pasan desde un entorno limpio.
- La corrida real respeta políticas y produce un `run_report`.
- Se registra al menos un programa y una edición real de «Estudie su polla». Una restricción externa verificable se reporta como bloqueo y no satisface este criterio de aceptación.
- Repetir la corrida no aumenta filas ni blobs para contenido sin cambios.
- La extracción real produce hechos con evidencia si existe capa textual; de lo contrario, produce `needs_ocr` sin instalar OCR.
- Un caso ambiguo genera `requires_review=true` y un único `review_item`.
- README, `.env.example` y límites éticos coinciden con esta arquitectura.
- No hay PDFs, secretos ni datos sensibles rastreados por Git.

La aprobación de este documento autoriza la creación de un plan de implementación detallado. No autoriza todavía cambios de código.
