# Programa oficial de Monterrico

La navegación parte de la vista de reunión y sigue los enlaces públicos
`programa?carrera=<ID>`. El recolector debe validar cada navegación y solicitud
con `PolicyGate` y respetar una pausa de 2,5 segundos como mínimo entre
navegaciones, ampliada si `robots.txt` indica una mayor.

## Contrato observable

La comprobación con Playwright de la carrera `863740` recibió HTTP 200. Con
las rutas excluidas por `robots.txt` y las solicitudes a dominios externos
bloqueadas, mostró «No se pudo cargar el programa de la carrera» y cero
tablas. No aparecieron Waytt, su historial ni sus aprontes. Se necesita una
captura renderizada con contenido o una exportación autorizada para validar
el contrato de extracción. El HTML vacío no prueba los selectores.

## Persistencia y dashboard

La migración `20261119_0005` crea `horse_stats_snapshots`. Cada fila se vincula
a `race_entries.id`, registra `source_url`, `fetched_at` en UTC y `content_hash`
(SHA-256 del contenido fuente), y guarda un objeto JSON `profile` con
estadísticas generales, estadísticas por pista, `recent_races` y `workouts`.
El dashboard interpreta las dos últimas como listas de registros tabulares.
La unicidad por entrada y hash evita importar dos veces una captura idéntica.
Carreras muestra el snapshot más reciente por participante. Las bases de la
versión anterior siguen abriendo y muestran que el perfil no está disponible.

Para vincular los datos oficiales, se debe corroborar la equivalencia entre
el código de reunión del sitio y el código local mediante fecha, número de
carrera y mandil, verificando también nombre y contexto. Las discrepancias
quedan pendientes de revisión. Los snapshots se consultan solo para mostrar
el perfil y no son entradas de inferencia de LightGBM.
