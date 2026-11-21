# Registro de cambios del esquema y flujo CSV de Pure

> **Leyenda:** 🟩 cambio implementado en la fuente SQL; 🟨 requiere instalar y
> verificar en la base de desarrollo. No uses solo el color: cada estado también se
> describe con texto.

> **Estado actual (noviembre de 2026):** el portal importa el CSV a candidaturas y
> consolida automáticamente en una transacción serializable los casos con autoría
> vinculada por UUID exacto, datos obligatorios válidos y sin DOI duplicado. «Guardar
> depuración» vuelve a procesar el lote; los casos restantes conservan sus motivos en
> la lista de candidaturas. No se requiere aprobar uno por uno.

## 🟩 Actualización 2026-11: importación CSV de Pure

> [!IMPORTANT]
> **No se agregan tablas ni columnas para este flujo.** Se reutilizan las tablas de
> candidaturas que ya forman parte del esquema de 42 tablas. El único cambio DDL
> específico de la importación es incluir `pure` entre los valores aceptados por
> `ck_publicacion_candidata_fuente` en el SQL de instalación desde cero.

| Objeto | Antes | Ahora | Impacto |
|---|---|---|---|
| `ck_publicacion_candidata_fuente` | `fuente IN ('scopus', 'orcid', 'manual')` | `fuente IN ('scopus', 'orcid', 'manual', 'pure')` | Acepta candidaturas que vienen de un CSV exportado desde Pure. |
| Tablas / columnas | — | Sin cambios | No requiere tablas, columnas, índices ni procedimientos nuevos. |

- `publicacion_candidata.metadatos_origen` ya conserva el JSON original de Pure,
  además de la curación y la huella SHA-256 del CSV.
- `publicacion_candidata_investigador` ya registra asociaciones, estados de revisión,
  coordinador, fecha y motivo.
- `investigador_historico` ya conserva la asociación consolidada entre investigador,
  publicación y coordinador.
- La importación no inserta en `historico`. La aprobación reutiliza
  `sp_cargar_historico` dentro de la transacción del repositorio.
- No se creó lote de importación, tabla de auditoría ni campo nuevo: el nombre del
  archivo, huella y datos de descarte se guardan en el JSONB existente.
- El importador etiqueta cada candidatura con la huella SHA-256 del archivo para
  agrupar la clasificación y el procesamiento automático en lote, sin una tabla adicional.
- El CSV de ejemplo tiene 2.519 filas estructuralmente válidas. Hay 41 publicaciones
  con al menos un campo fuera de los límites del Histórico. Los campos opcionales
  incompatibles se omiten del catálogo durante la preparación automática; su valor
  completo permanece en el JSON de origen y se informa en el portal.
- Los datos del CSV no se insertan durante la instalación ni se agregan como fixtures:
  el coordinador los carga después desde el portal.

### 🟩 Curación automática y consolidación segura por lote

La previsualización no escribe en la base. Cuenta UUID y DOI repetidos dentro del
archivo, valida las columnas requeridas, UUID, JSON, título y año, y muestra las filas
inválidas. Al confirmar la carga, las válidas se guardan como candidaturas y el sistema
procesa automáticamente las que ya cumplen los criterios seguros.

La curación de entrada adapta campos **opcionales** a los límites físicos sin truncar
ni alterar el JSON original:

- Omite resumen, número de revista, nota bibliográfica, páginas y subtítulo que
  excedan el tamaño de su columna.
- Excluye identificadores, palabras clave, estados y enlaces inválidos o fuera de
  límite; elimina repetidos donde la clave de la tabla no permite duplicados.
- Omite volumen o cantidad de páginas que no sean enteros positivos representables.
- Si no hay año de envío válido, usa el año de publicación y deja constancia.
- Si la visibilidad exportada excede el límite, registra `UNKNOWN` en vez de asumir
  acceso abierto. Clasificaciones auxiliares demasiado largas usan la clasificación
  estándar del tipo; fechas de origen inválidas se omiten y se aplica la fecha
  predeterminada del catálogo. Cada reemplazo queda informado.
- No elimina ni recorta título, tipo, idioma, categoría, URL de portal ni nombres de
  contribuyentes para forzar una aprobación. Si un campo obligatorio falla o la
  autoría no es conservable, la candidatura queda fuera del lote automático. Una
  revisión por pares cuyo valor no se pueda interpretar como booleano también requiere
  que el coordinador la corrija en la candidatura.
- Cada omisión se registra en `metadatos_origen.curacion_automatica` y se explica en
  el detalle de la candidatura. El JSON `metadatos_origen.data` conserva los valores
  íntegros exportados por Pure.

Después de importar, el portal consolida automáticamente en una transacción serializable
las candidaturas que cumplen todos los criterios siguientes. Al guardar la depuración de
una candidatura pendiente, vuelve a procesar automáticamente el lote al que pertenece:

1. Está pendiente y tiene al menos un vínculo de autor cuyo UUID de persona en el CSV
   coincide exactamente con el ID Pure de un perfil local aprobado.
2. Los vínculos que se aprueban son únicamente esos vínculos exactos; nunca se infiere
   autoría por nombre ni se aprueban vínculos agregados manualmente.
3. Sus campos obligatorios y restricciones del Histórico son válidos después de la
   curación automática.
4. Su UUID aún no está en `historico` y su DOI, si tiene, no colisiona con otra
   candidatura ni con un DOI del Histórico (incluye duplicados del mismo CSV).

Ante un error, se revierte la consolidación del lote. Las candidaturas sin coincidencia
exacta, con DOI repetido, con campos obligatorios faltantes o con autoría ambigua quedan
pendientes con los motivos agrupados en pantalla para revisión manual. «Guardar
depuración» conserva los cambios en `publicacion_candidata.metadatos_origen.curacion`;
no inserta por sí solo esa publicación en el Histórico. Después de guardar, el lote se
reprocesa automáticamente y la interfaz informa cuántas publicaciones pasaron al
Histórico. La carga no cambia el sentido de la sección “Altas manuales en Pure”: esa
bandeja sigue siendo para perfiles de investigadores, no para publicaciones. Para que
la autoría coincida automáticamente, el perfil aprobado debe tener registrado el UUID
exacto de persona de Pure; no se usa el nombre para inferir identidad. Al reprocesar,
el sistema vuelve a buscar esos UUID en los perfiles y crea los vínculos exactos que
faltaban, por lo que registrar el ID Pure después de importar también permite que el
siguiente guardado de depuración procese los casos ahora aptos.

### 🟩 Cambios del instalador y la prueba de esquema

- `instalar_bd.py` muestra la base destino y se niega a ejecutar el SQL si detecta
  tablas en `public`; esto evita que el comando borre silenciosamente un esquema ya
  instalado. Después valida 42 tablas y la definición de `pure`.
- `prueba_conexion.py` comprueba además que
  `ck_publicacion_candidata_fuente` permita `pure`.
- Se añadió `prueba_instalador_bd.py` para comprobar los bloqueos y la verificación
  del resultado sin conectarse a PostgreSQL.
- Validación sin PostgreSQL: las pruebas del instalador y del portal cubren el
  preflight, validación CSV, DOI repetido, curación opcional, exclusión de URL
  obligatoria inválida, el reprocesamiento automático y la coincidencia UUID exacta.
  La instalación conectada y la importación real en PostgreSQL deben verificarse en
  la base de desarrollo del equipo.

🟨 **Validación pendiente en la base que recreará el equipo:** la restricción `pure`
está en el SQL, pero no se ejecutó el instalador sobre la base configurada. Después de
crear una base vacía, `instalar_bd.py` comprueba las 42 tablas y la fuente `pure`;
`prueba_conexion.py` comprueba ambos puntos sin modificar datos.

## Alcance

Se integró el modelo objetivo del portal CRIS en
`backend/database/base_datos_repositorio.sql` para una instalación desde cero. No se
preparó una migración ni se copiaron datos de otra base. El script elimina y vuelve a
crear las tablas del aplicativo, por lo que solo debe ejecutarse contra una base
descartable vacía.

El esquema conserva las 27 tablas originales y agrega 15, para un total de 42 tablas.
El portal web ya usa el flujo implementado sobre estas tablas. Las integraciones
automáticas con las API de Pure y Scopus siguen fuera de alcance. La importación de
Pure parte de un CSV exportado; la curación de campos y la consolidación de casos con
autoría exacta se pueden ejecutar en lote desde el portal.

## Cambios realizados

### 🟩 Tablas nuevas

**Cuenta, postulación y verificaciones**

- `cuenta_investigador`: credenciales protegidas, DNI, código UCSM y correo.
- `solicitud_investigador`: datos estructurados del formulario y estado de revisión.
- `solicitud_investigador_ods` y `solicitud_investigador_interes`: listas normalizadas.
- `solicitud_investigador_version`: snapshots de cada versión enviada.
- `revision_solicitud`: decisiones de aprobación, observación o rechazo del coordinador.
- `verificacion_solicitud`: resultados manuales o de ORCID/Scopus ligados a una versión.

**ORCID/Scopus y publicaciones**

- `integracion_ejecucion`: estado, tiempos, contadores y errores resumidos; no guarda
  tokens ni cuerpos completos de solicitudes/respuestas.
- `publicacion_candidata`: metadatos de publicaciones sugeridas para revisión humana.
- `publicacion_candidata_investigador`: decisión de curación por investigador.
- `investigador_historico`: relación normalizada entre investigadores y publicaciones
  confirmadas.

**Solicitudes de patente**

- `solicitud_patente`: datos y estado de la solicitud.
- `solicitud_patente_investigador`: inventores propuestos.
- `solicitud_patente_ocde`: clasificación propuesta.
- `revision_solicitud_patente`: versiones evaluadas y decisiones del coordinador.

### 🟩 Cambios a tablas existentes

- `investigador` agrega `cuenta_investigador_id` y campos para registrar el ID de Pure,
  su estado manual, quién lo registró y cuándo. Los perfiles de ejemplo quedan sin
  clasificación Pure porque no se conoce su situación en esa plataforma.
- `formato_patente` agrega `solicitud_patente_id`, nullable y único cuando tiene valor,
  para enlazar una patente definitiva con su solicitud aprobada.

### 🟩 Procedimientos e índices

Se agregaron procedimientos para crear y corregir postulaciones, observarlas,
resolverlas, registrar verificaciones, guardar el alta manual de Pure, y crear,
corregir y resolver solicitudes de patente. La aprobación de una solicitud de
investigador reutiliza `sp_registrar_investigador`; la aprobación de patente reutiliza
`sp_registrar_patente`. En ambos casos las operaciones se ejecutan dentro de la
transacción del procedimiento llamador.

Procedimientos agregados:

- `sp_crear_solicitud_investigador`
- `sp_actualizar_solicitud_investigador`
- `sp_observar_solicitud_investigador`
- `sp_resolver_solicitud_investigador`
- `sp_aprobar_solicitud_investigador` (nombre anterior; delega en el resolvedor)
- `sp_registrar_verificacion_solicitud`
- `sp_registrar_pure_manual`
- `sp_crear_solicitud_patente`
- `sp_actualizar_solicitud_patente`
- `sp_resolver_solicitud_patente`

Índices añadidos:

`uq_cuenta_investigador_correo`, `uq_solicitud_investigador_abierta`,
`uq_solicitud_orcid_activa`, `uq_solicitud_scopus_activa`,
`uq_solicitud_cti_activa`, `ix_solicitud_investigador_estado_enviada`,
`ix_revision_solicitud_solicitud_fecha`, `ix_verificacion_solicitud_fecha`,
`uq_investigador_cuenta`, `uq_investigador_pure_person`,
`ix_integracion_ejecucion_sistema_fecha`, `ix_integracion_ejecucion_solicitud`,
`ix_publicacion_candidata_doi`, `ix_publicacion_candidata_titulo_anio`,
`ix_candidata_investigador_pendiente`, `ix_investigador_historico_uuid`,
`ix_solicitud_patente_solicitante`, `uq_solicitud_patente_activa`,
`ix_solicitud_patente_investigador_codigo`,
`ix_revision_solicitud_patente_fecha` y `uq_formato_patente_solicitud`.

El script conserva los 21 índices con prefijo `idx_*` del esquema original.
También se conserva el índice único original `ux_coordinador_correo`.

## Inserciones de ejemplo

Se conservaron los INSERT originales del esquema base y se agregaron relaciones de
ejemplo en `investigador_historico` para los autores que ya aparecen en los datos
demostrativos de `historico_contributors`.

No se agregan cuentas, postulaciones, decisiones, resultados API, candidatos ni
identificadores Pure ficticios. Las solicitudes de patente de ejemplo tampoco se
inventan; las patentes preexistentes son registros del esquema original y conservan
`solicitud_patente_id = NULL`.

## Reglas y límites reflejados

- Solo Investigador y Coordinador son usuarios del portal; el coordinador decide.
- ORCID puede verificarse por API cuando se configuran sus credenciales; Scopus API no
  está integrada y el coordinador puede registrar su revisión manual. Los resultados
  son evidencia y no aprueban una solicitud automáticamente.
- El código UCSM se valida por formato y duplicados locales; no existe una API UCSM
  incorporada para confirmar identidad o afiliación.
- Pure se gestiona manualmente; no se incorporan API keys, tokens ni credenciales.
- Una solicitud de patente requiere un perfil local de investigador; solo una
  aprobación del coordinador crea la patente definitiva.
- Las tablas de Biblioteca quedan fuera del script hasta recibir una muestra
  anonimizada y acordar la retención de sus datos.

## 🟨 Instalación desde cero

`backend/database/instalar_bd.py` ejecuta el SQL principal completo,
`backend/database/base_datos_repositorio.sql`, sobre la base configurada. No hay un
proceso de migración adicional: crea una base vacía y ejecuta el instalador. El
preflight ahora se niega a ejecutar si encuentra tablas en `public`; el SQL fuente
elimina y recrea tablas y no debe ejecutarse manualmente sobre una base cuyos datos se
quieran conservar.

La versión inicial de 42 tablas se validó en un clúster PostgreSQL 17 temporal y
descartable:

- Instalación del SQL principal: correcta.
- Tablas en `public`: 42.
- Índices con prefijo `idx_*`: 21.
- Procedimientos almacenados: 19.
- Prueba funcional: crear postulación, guardar verificaciones, observar y corregir,
  aprobar y crear perfil local, registrar Pure manualmente, crear solicitud de patente,
  aprobarla y comprobar el vínculo desde `formato_patente`.

La base activa del proyecto no se ha reinstalado. La verificación de la restricción de
fuente `pure` y la importación con PostgreSQL real quedan pendientes de la próxima
instalación; las pruebas web actuales simulan el acceso a la base.
