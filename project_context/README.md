# Guía de documentación y estado actual del Portal CRIS

**Actualizado: noviembre de 2026.** Este índice separa el contexto recibido, el
comportamiento implementado y las decisiones que siguen pendientes. Para saber cómo
funciona hoy el portal, empieza por la guía operativa; los documentos originales
conservan el contexto académico e institucional que compartió el equipo.

## Lectura recomendada

| Orden | Documento | Para qué sirve |
|---|---|---|
| 1 | [Guía de flujos operativos](guia-flujos-operativos-portal-cris.md) | Explica los roles, las pantallas, el recorrido de investigador/coordinador, las validaciones disponibles y qué integraciones siguen fuera de alcance. |
| 2 | [Diseño técnico del esquema y migración](diseno-tecnico-esquema-y-migracion-cris.md) | Describe las 42 tablas, relaciones, procedimientos, reglas de integridad y los límites entre el esquema implementado y el diseño futuro. |
| 3 | [Cambios del esquema y CSV Pure](registro-cambios-esquema-y-flujo-csv-pure.md) | Registra los cambios DDL, cómo se cura e importa el CSV y con qué criterios se consolidan automáticamente las publicaciones seguras. |
| 4 | [Contexto del módulo del coordinador](contexto-modulo-coordinador-cris.md) | Documento de contexto recibido. Contiene requisitos y propuestas originales; puede describir ideas que no forman parte del portal actual. |
| 5 | [Desarrollo de la base de datos](desarrollo_de_la_base_de_datos_repositorios_ucsm.md) | Documento académico original de modelado y PostgreSQL. Se conserva su nombre y contenido base; sus avisos iniciales apuntan a las actualizaciones técnicas. |

El [README principal](../README.md) contiene configuración, inicio local, credenciales
de demostración del coordinador y comandos de pruebas. El SQL ejecutable está en
`backend/database/base_datos_repositorio.sql`; ese archivo es la fuente de verdad del
esquema, no los ejemplos o diagramas de los documentos de contexto.

## Qué hace actualmente cada módulo

### Investigador

- Registra una cuenta y envía la postulación; puede consultar su estado y el historial
  de decisiones/verificaciones.
- Si el coordinador observa la solicitud, puede corregirla y reenviarla.
- Al aprobarse el perfil, aparecen dos pantallas separadas: **Mi solicitud** y
  **Mis patentes**. La segunda permite crear solicitudes de patente y consultar o
  corregir las observadas; solo está disponible para un perfil aprobado.

### Coordinador

- Revisa postulaciones, verifica evidencia y toma la decisión de aprobar, observar o
  rechazar dentro del portal.
- Consulta directorios de investigadores y patentes; aprueba solicitudes de patente
  antes de crear el registro definitivo.
- Registra manualmente el identificador de persona de Pure después de crear o vincular
  el perfil desde la instancia institucional.
- Consulta el Histórico de publicaciones, importa y depura CSV de Pure y usa el
  dashboard/reportes disponibles.

### Verificaciones externas

- **ORCID:** el backend puede consultar la existencia del identificador desde una
  solicitud pendiente cuando están configuradas `ORCID_CLIENT_ID` y
  `ORCID_CLIENT_SECRET`. Sin ellas, el resultado es `no_disponible`. La consulta no
  verifica afiliación UCSM ni aprueba al investigador.
- **Scopus:** no hay integración de API; el coordinador puede registrar una
  verificación manual.
- **Pure:** no hay integración de API. El perfil y su ID se gestionan manualmente.

### Importación y depuración de Pure

1. El coordinador previsualiza el CSV; esa acción no escribe en la base.
2. Al confirmar, las filas válidas se almacenan en `publicacion_candidata`, con el
   JSON de origen y datos de curación. El guardado de la candidatura no significa que
   ya esté en el Histórico oficial.
3. En el mismo flujo, el sistema consolida automáticamente las publicaciones que
   tengan al menos un autor vinculado mediante UUID exacto a un investigador aprobado,
   campos obligatorios compatibles y ningún DOI duplicado.
4. El sistema vuelve a buscar esos UUID al procesar el lote. Por eso también puede
   vincular perfiles cuyo ID Pure se registró después de importar el CSV. Al guardar
   la depuración de una candidatura pendiente se reintenta el lote.
5. Los casos con alertas siguen en **Histórico → Importar y depurar Pure →
   Candidaturas de Pure** para revisión. No se infiere autoría por nombre ni se
   fusionan automáticamente coincidencias DOI dudosas.

`Guardar depuración` persiste las correcciones en
`publicacion_candidata.metadatos_origen.curacion`. Si luego pasa las reglas de
consolidación, la publicación aparece en la pestaña **Publicaciones** del Histórico.

## Base de datos, instalación y validación

- El SQL de instalación define 42 tablas: conserva las 27 del esquema original y
  agrega las estructuras CRIS. La importación CSV Pure reutiliza candidaturas; solo
  amplía el `CHECK` de `publicacion_candidata.fuente`.
- `backend/database/instalar_bd.py` es para instalación desde cero y rechaza una base
  que ya tenga tablas en `public`. No es una migración ni debe ejecutarse sobre una
  base que se quiera conservar.
- Las pruebas unitarias/web cubren reglas y rutas con operaciones de base aisladas;
  no sustituyen probar el instalador y el flujo de importación con PostgreSQL en una
  base descartable.

## Fuera del alcance implementado

- Llamadas a Pure Web Services API o creación automática de perfiles Pure.
- Scopus API y búsqueda programada de publicaciones.
- Importación de actividad de Biblioteca. `historico` representa publicaciones,
  no accesos de estudiantes; la importación espera un archivo de muestra y reglas
  acordadas.
