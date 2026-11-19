# Programa oficial de Monterrico

La navegación parte de la vista de reunión y sigue los enlaces públicos
`programa?carrera=<ID>`. El recolector debe validar cada navegación y solicitud
con `PolicyGate` y respetar una pausa de 2,5 segundos como mínimo entre
navegaciones, ampliada si `robots.txt` indica una mayor.

## Contrato observable

La primera comprobación de la carrera `863740` mostró «No se pudo cargar el
programa de la carrera» al bloquear las solicitudes externas. La vista hace
peticiones al proveedor integrado elTurf. Al permitir sus solicitudes de datos
tras evaluar su política, la vista oficial mostró 21 tablas sin solicitar
`/api/` de Monterrico. El parser utiliza las tarjetas de escritorio, que
incluyen el retrospecto y los aprontes. Las tarjetas de móvil contienen un
subconjunto y no se cuentan como participantes adicionales.

La vista `/reunion` no publicó enlaces para el 21 de noviembre. La ficha
`863740` enlazó las doce carreras de la Reunión 476. El comando admite ese ID
como respaldo y verifica la fecha de cada ficha antes de materializarla.

## Persistencia y dashboard

La migración `20261119_0005` crea `horse_stats_snapshots`. Cada fila se vincula
a `race_entries.id`, registra `source_url`, `fetched_at` en UTC y `content_hash`
(SHA-256 del contenido fuente), y guarda un objeto JSON `profile` con
estadísticas generales, estadísticas por pista, `recent_races` y `workouts`.
El dashboard interpreta las dos últimas como listas de registros tabulares.
La unicidad por entrada y hash evita importar dos veces una captura idéntica.
Carreras muestra el snapshot más reciente por participante. Las bases de la
versión anterior siguen abriendo y muestran que el perfil no está disponible.

La reunión oficial se registra con un código que combina año y número oficial,
por ejemplo `2026-476`. Se reutiliza una entrada si coinciden el código,
número de carrera, mandil y nombre normalizado. Una discrepancia de contexto
o nombre aborta la transacción. Los snapshots se consultan solo para mostrar
el perfil y no son entradas de inferencia de LightGBM.

## Ejecución local

Instala el proyecto y Chromium con `python -m playwright install chromium`.
Define `BENTER_USER_AGENT` e indica una carpeta de blobs fuera del repositorio.
El comando también admite Edge instalado mediante `--channel msedge`.

```powershell
python -m scripts.official_program --date 2026-11-21 --seed-race 863740 --expected-races 12 --captures var --database var/official-2026-11-21.sqlite3 --blobs C:/ruta/privada/blobs
```

`--captures var` conserva localmente los HTML renderizados y permite reutilizar
las capturas al repetir la ejecución. `var/` está ignorado por Git. Para ver
los perfiles, configura `BENTER_DATABASE_PATH` con la base indicada y abre
Carreras en el dashboard.
