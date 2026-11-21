# Contexto Técnico de Desarrollo: Módulo del Coordinador de Repositorios (CRIS - UCSM)

> **Aviso de vigencia:** este archivo conserva un borrador anterior y contiene
> propuestas que no forman parte del flujo aprobado para la primera versión (por
> ejemplo, automatización de cargas CSV y validaciones). Para implementar y actualizar
> los diagramas, tablas y flujos, usar como documento vigente
> [guia-flujos-operativos-portal-cris.md](guia-flujos-operativos-portal-cris.md).
> En particular, el perfil Pure se crea manualmente en la primera versión: el Swagger
> compartido documenta la API, pero no concede acceso a la instancia UCSM ni sustituye
> sus credenciales y permisos.

Este documento define las especificaciones técnicas, flujos de trabajo, modelo de datos y reglas de negocio enfocadas **exclusivamente en la funcionalidad del Coordinador de Repositorios** del Vicerrectorado de Investigación (VRINV) de la Universidad Católica de Santa María (UCSM).

---

## 1. Rol y Alcance del Coordinador de Repositorios

* **Actor Principal:** Coordinador de Repositorios (ej. Ing. Javier Fernando Angulo Osorio).
* **Unidad Organizativa:** Dirección de Investigación / Vicerrectorado de Investigación (VRINV) - UCSM.
* **Objetivo del Módulo:** Automatizar y centralizar las tareas operativas que actualmente se realizan de forma segmentada (correos, formularios manuales, descarga y depuración manual de archivos CSV/JSON).

### Responsabilidades Core en el Software
1. **Autenticación y Gestión de Sesión:** Acceso seguro mediante correo institucional (`@ucsm.edu.pe`) y contraseña hasheada.
2. **Validación de Solicitudes de Registro de Investigadores:** Revisión de formatos enviados, verificación de afiliación UCSM, RENACYT/CTI Vitae, ORCID y Scopus ID, y creación/publicación del perfil en CRIS tras aprobación del Director de Investigación.
3. **Sincronización y Depuración de Publicaciones (CRIS-Pure):** Carga e ingesta del archivo `Pure_research_outputs.csv` (con metadatos JSON en la columna `data`), verificación de autoría y eliminación de duplicados.
4. **Validación de Registro de Patentes:** Verificación de patentes registradas por investigadores previamente aprobados.
5. **Procesamiento de Históricos y Generación de Reportes (Dashboard):** Consolidación de métricas de uso de repositorios institucionales por estudiantes (escuela/facultad) y producción científica (rankings ODS, top escuelas, top investigadores).

---

## 2. Flujos de Trabajo Detallados (Casos de Uso del Coordinador)

### Flujo A: Validación y Alta de Investigadores en CRIS
1. **Recepción:** El coordinador visualiza la bandeja de solicitudes pendientes (`Formato_Investigador`).
2. **Verificación de Requisitos:**
   * Confirmar afiliación activa con la UCSM (`Cod_UCSM`, `Escuela_Profesional`).
   * Validar existencia en el Registro Nacional de Investigadores (`Link_CTI_Vitae`).
   * Validar formato y existencia de identificadores académicos: `Cod_ORCID` (ej. `0000-0002-1825-0097`) y `SCOPUS_ID`.
   * Verificar que posea investigaciones indexadas.
3. **Resolución:**
   * Se registra la validación vinculando el `Cod_UCSM` del coordinador (`relación Valida`).
   * Una vez aprobada la solicitud por el Director de Investigación, el sistema habilita la carga/publicación del perfil del investigador en el portal CRIS.

### Flujo B: Sincronización y Curaduría de Publicaciones (ORCID / Scopus / Pure CSV)
1. **Ingesta de Datos (`Procesa`):**
   * El coordinador sube o sincroniza el archivo `Pure_research_outputs.csv` hacia la entidad `Historico`.
   * El sistema parsea los 5 campos base (`uuid`, `title`, `publication_year`, `data`, `synced_at`) y descompone el objeto JSON de `data` (metadatos bibliográficos, autores, enlaces, palabras clave, estado).
2. **Curaduría Manual/Asistida:**
   * El coordinador revisa los artículos sincronizados uno a uno para verificar que correspondan al investigador, estén debidamente indexados y no presenten duplicidades.
   * Los artículos validados quedan listos para mostrarse en el perfil público del investigador en CRIS.

### Flujo C: Validación de Patentes
1. **Recepción:** El coordinador revisa las solicitudes de `Formato_Patente`.
2. **Regla Crítica de Negocio:** Todos los inventores listados en la patente (`Inventores`) **deben estar previamente registrados y validados** como investigadores en el sistema.
3. **Validación:** El coordinador verifica los datos oficiales (`N°Patente`, `CIP`, `Editorial` como INDECOPI, `Fecha_Registro`, `Pais`, `Campo_OCDE`, `Obj_OCDE`) y aprueba el registro (`relación Valida`).

### Flujo D: Seguimiento de Repositorios y Generación de Dashboard (`Genera` / `Origina`)
1. **Análisis de Accesos:** El coordinador consulta los registros históricos de uso de repositorios institucionales (hora de ingreso, correo del estudiante, repositorio consultado, escuela y facultad).
2. **Generación de Corte de Reporte:**
   * El coordinador genera un reporte periódico identificado por fecha (`Dia`, `Mes`, `Año`).
   * El sistema calcula y consolida automáticamente los KPIs a partir de `Historico` (`relación Origina`) y vincula la auditoría al coordinador que lo generó (`relación Genera`).

---

## 3. Modelo de Datos Relacional (Enfoque en el Coordinador)

El modelo está normalizado hasta **Tercera Forma Normal (3FN)** para PostgreSQL 16. A continuación se detallan las tablas principales y las claves foráneas que gobiernan la actividad del coordinador.

### 3.1 Entidad Principal: `COORDINADOR_REPOSITORIOS`
Almacena la identidad, adscripción y credenciales del coordinador.

| Columna | Tipo Sugerido (PG 16) | Clave / Restricción | Descripción | Ejemplo |
| :--- | :--- | :--- | :--- | :--- |
| `cod_ucsm` | `VARCHAR(15)` / `BIGINT` | **PK**, `NOT NULL` | Código institucional del coordinador | `1000123498` |
| `dni` | `CHAR(8)` | `UNIQUE`, `NOT NULL` | Documento Nacional de Identidad (8 dígitos) | `87654321` |
| `nombre` | `VARCHAR(150)` | `NOT NULL` | Nombre completo del coordinador | `Javier Fernando Angulo Osorio` |
| `correo_e_coordinador` | `VARCHAR(120)` | `UNIQUE`, `NOT NULL` | Correo institucional (`@ucsm.edu.pe`) | `jangulo@ucsm.edu.pe` |
| `contrasena` | `VARCHAR(255)` | `NOT NULL` | Hash seguro (SHA-256 / bcrypt) de la clave | `8c6976e5b5410415...` |
| `funcion` | `VARCHAR(100)` | `NOT NULL` | Cargo desempeñado | `Coordinador de repositorios` |
| `direccion_adscrita` | `VARCHAR(120)` | `NOT NULL` | Oficina o dirección orgánica | `Dirección de investigación` |
| `fecha_ingreso` | `DATE` | `NOT NULL` | Fecha en que asumió el cargo | `2023-03-01` |
| `fecha_retiro` | `DATE` | `NULL` | Fecha de cese (NULL mientras esté activo) | `NULL` |

> **Regla de Seguridad:** Si `fecha_retiro IS NOT NULL` y `fecha_retiro <= CURRENT_DATE`, el coordinador pierde permisos de escritura/validación en el sistema.

---

### 3.2 Tablas Operativas Gestionadas por el Coordinador (Relaciones 1:N)

El `cod_ucsm` del coordinador se propaga como **Clave Foránea (`cod_ucsm_coordinador`)** en las cuatro entidades operativas principales:

#### A. Validación de Investigadores (`FORMATO_INVESTIGADOR` + Tablas Normalizadas 3FN)
* **Relación MER:** `Coordinador_Repositorios` (1) --- *Valida* ---> (N) `Formato_Investigador` (Participación total).
* **Descomposición 3FN:**
  * `PERSONA` (`dni` PK, `nombres`, `apellido_p`, `apellido_m`, `genero`, `fecha_nacimiento`).
  * `INVESTIGADOR` (`cod_ucsm` PK, `dni` FK, `escuela_profesional`, `cod_orcid` UNIQUE, `scopus_id`, `link_cti_vitae`, `correo_electronico`, `n_celular`).
  * `FORMATO_INVESTIGADOR` (`n_formato_inv` PK, `cod_ucsm` FK, `resumen_acad`, `foto_perfil`, `cod_ucsm_coordinador` FK).
  * **Tablas Multivaluadas:**
    * `FORMATO_INVES_ODS` (`n_formato_inv` PK/FK, `ods` PK).
    * `FORMATO_INVES_INTERESES` (`n_formato_inv` PK/FK, `intereses_invest` PK).

#### B. Validación de Patentes (`FORMATO_PATENTE` + Tablas Normalizadas 3FN)
* **Relación MER:** `Coordinador_Repositorios` (1) --- *Valida* ---> (N) `Formato_Patente` (Participación total).
* **Descomposición 3FN:**
  * `PATENTE` (`n_patente` PK, `titulo_patente`, `cip`, `editorial`, `fecha_registro`, `pais`).
  * `FORMATO_PATENTE` (`n_formato_paten` PK, `n_patente` FK, `cod_ucsm_coordinador` FK).
  * **Tablas Asociativas / Multivaluadas:**
    * `FORMATO_PATENTE_INVESTIGADOR` (`n_formato_paten` PK/FK, `n_formato_inv` PK/FK) -> *Relación N:M `Requiere`*.
    * `FORMATO_PATEN_OCDE` (`n_formato_paten` PK/FK, `campo_ocde` PK, `objetivos_ocde` PK).

#### C. Procesamiento de Históricos (`HISTORICO` + Tablas Multivaluadas)
* **Relación MER:** `Coordinador_Repositorios` (1) --- *Procesa* ---> (N) `Historico`.
* **Estructura Base:**
  * `HISTORICO` (`uuid` PK, `title`, `publication_year`, `synced_at`, `type`, `sub_title`, `volume`, `journal_number`, `number_of_pages`, `pages`, `language`, `category`, `type_discriminator`, `peer_review`, `visibility`, `submission_year`, `portal_url`, `system_name`, `version`, `abstract`, `bibliographical_note`, `create_by`, `create_date`, `modified_by`, `modified_date`, `cod_ucsm_coordinador` FK, `dia_reporte` FK, `mes_reporte` FK, `anio_reporte` FK).
  * **Tablas Multivaluadas del JSON `data`:**
    * `HISTORICO_LINKS` (`uuid` PK/FK, `pure_id` PK, `url`, `description`, `link_type`).
    * `HISTORICO_CONTRIBUTORS` (`uuid` PK/FK, `contributors` PK).
    * `HISTORICO_IDENTIFIERS` (`uuid` PK/FK, `identifiers` PK).
    * `HISTORICO_ELECTRONIC_VERSIONS` (`uuid` PK/FK, `electronic_versions` PK).
    * `HISTORICO_KEYWORD_GROUPS` (`uuid` PK/FK, `keyword_groups` PK).
    * `HISTORICO_PUBLICATION_STATUSES` (`uuid` PK/FK, `publication_statuses` PK).

#### D. Generación de Reportes / Dashboard (`REPORTE`)
* **Relaciones MER:**
  * `Coordinador_Repositorios` (1) --- *Genera* ---> (N) `Reporte`.
  * `Reporte` (1) --- *Origina* ---> (N) `Historico`.
* **Estructura Base:**
  * `REPORTE` (`dia` PK, `mes` PK, `anio` PK, `cod_ucsm_coordinador` FK).
  * **Atributos Derivados / Multivaluados del Dashboard:**
    * `cant_escuela_profesional`: Total de escuelas registradas.
    * `total_publicaciones`: Total de publicaciones indexadas.
    * `total_investigadores`: Total de investigadores activos en CRIS.
    * `cant_ods_vinculados`: Cantidad de ODS asociados a investigaciones/patentes.
    * `ranking_ods`: Frecuencia ordenada de ODS (ej. `ODS 9, ODS 4, ODS 3`).
    * `distribucion_por_ods`: Porcentaje de producción por ODS (ej. `ODS 9: 20%, ODS 3: 15%`).
    * `top_escuelas`: Escuelas profesionales con mayor producción/investigadores.
    * `top_escuela_por_investigador`: Investigador líder en publicaciones por cada escuela.

---

## 4. Reglas de Validación e Integridad de Datos (Backend / DB)

El backend y la base de datos (PostgreSQL 16) deben rechazar cualquier operación del coordinador que viole estas restricciones:

1. **DNI:** Cadena numérica exacta de **8 dígitos** (`CHECK (dni ~ '^[0-9]{8}$')`).
2. **Código ORCID:** Formato estándar ISO `0000-0000-0000-000X` (`CHECK (cod_orcid ~ '^[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9X]$')`).
3. **Correo Institucional:** Formato de correo válido y único para coordinadores (`UNIQUE`).
4. **Catálogo ODS:** Solo se permiten los **17 Objetivos de Desarrollo Sostenible** oficiales de la ONU (rechazar valores como `ODS 18` o inexistentes).
5. **Pre-registro de Inventores:** No se puede aprobar un `Formato_Patente` si alguno de los inventores no existe previamente en `INVESTIGADOR` / `FORMATO_INVESTIGADOR`.
6. **Integridad de Archivo CSV (`Pure_research_outputs.csv`):**
   * El campo `uuid` debe ser único (evitar duplicidad al re-subir archivos).
   * El campo `data` debe ser un JSON válido antes de extraer sus nodos multivaluados.

---

## 5. Especificación Sugerida de Endpoints (API REST para el Módulo Coordinador)

Para implementar el backend en VS Code, organiza los controladores bajo el prefijo `/api/v1/coordinador`:

### Autenticación y Perfil
* `POST /api/v1/coordinador/auth/login` — Autentica con `correo_e_coordinador` y `contrasena`, valida que `fecha_retiro` sea nula/futura y retorna JWT.
* `GET /api/v1/coordinador/perfil` — Devuelve datos del coordinador autenticado (`cod_ucsm`, `nombre`, `funcion`, `direccion_adscrita`).

### Gestión y Validación de Investigadores
* `GET /api/v1/coordinador/investigadores/solicitudes` — Lista solicitudes de `Formato_Investigador` (filtrable por estado: pendiente, validado, rechazado).
* `GET /api/v1/coordinador/investigadores/solicitudes/{n_formato_inv}` — Obtiene el detalle completo (datos personales, ORCID, Scopus ID, CTI Vitae, ODS, intereses, foto).
* `PATCH /api/v1/coordinador/investigadores/solicitudes/{n_formato_inv}/validar` — Asigna `cod_ucsm_coordinador`, registra la validación y habilita el perfil CRIS.

### Gestión y Validación de Patentes
* `GET /api/v1/coordinador/patentes/solicitudes` — Lista formatos de patente enviados.
* `PATCH /api/v1/coordinador/patentes/solicitudes/{n_formato_paten}/validar` — Verifica que todos los inventores estén registrados como investigadores y aprueba la patente.

### Sincronización y Curaduría de Publicaciones (`Historico`)
* `POST /api/v1/coordinador/historico/importar-csv` — Recibe el archivo `Pure_research_outputs.csv`, ejecuta el parser JSON del campo `data`, evita duplicados por `uuid` y asocia el lote al `cod_ucsm_coordinador`.
* `GET /api/v1/coordinador/historico/publicaciones` — Lista publicaciones sincronizadas para revisión uno a uno.
* `PATCH /api/v1/coordinador/historico/publicaciones/{uuid}/aprobar` — Marca la publicación como verificada y sin duplicidades para su visualización en CRIS.

### Dashboard y Reportes (`Reporte`)
* `POST /api/v1/coordinador/reportes/generar` — Genera un corte de reporte para la fecha actual (`dia`, `mes`, `anio`) consolidando métricas de `Historico` e `Investigador`.
* `GET /api/v1/coordinador/reportes/{anio}/{mes}/{dia}` — Retorna los 9 indicadores del Dashboard (totales, ranking ODS, distribución porcentual ODS, top escuelas, top investigador por escuela).
* `GET /api/v1/coordinador/repositorios/accesos` — Consulta métricas de uso de repositorios por estudiantes (escuela, facultad, frecuencia de acceso).

---

## 6. Estructura de Vistas Frontend (UI del Coordinador)

1. **Login Institucional:** Formulario de acceso exclusivo para coordinadores registrados.
2. **Dashboard Principal (Vista Reporte):**
   * Tarjetas KPI: Total Investigadores, Total Publicaciones, Escuelas Profesionales activas, Cantidad de ODS vinculados.
   * Gráfico circular/dona: Distribución porcentual por ODS.
   * Gráfico de barras horizontales: Top Escuelas por investigadores/publicaciones.
   * Tablas de ranking: Ranking de ODS y Top Investigador por Escuela.
   * Botón de acción: *"Generar nuevo corte de reporte"* + Selector histórico por fecha.
3. **Bandeja de Validación de Investigadores:**
   * Tabla con buscador por DNI, Código UCSM o Apellidos.
   * Modal/Vista de revisión con enlaces directos externos para verificar `ORCID`, `Scopus ID` y `CTI Vitae/Renacyt` antes de hacer clic en *Validar*.
4. **Bandeja de Validación de Patentes:**
   * Vista de detalles de patente (CIP, INDECOPI, Clasificación OCDE) + Checklist automático que indica si los inventores ya tienen perfil validado.
5. **Módulo de Sincronización CSV y Curaduría:**
   * Zona *Drag & Drop* para subir `Pure_research_outputs.csv` con log de registros insertados, actualizados y omitidos.
   * Tabla de revisión de artículos para aprobar publicación en el portal CRIS.
