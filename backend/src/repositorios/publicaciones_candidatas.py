"""Importación y curación de publicaciones candidatas provenientes de Pure."""
import hashlib
import re
from datetime import date, datetime, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import Json

from ..db.conexion import ErrorOperacion, _mensaje_operacion, conectar
from . import historico


_DOI_PREFIX = re.compile(r"^https?://(?:dx\.)?doi\.org/", re.IGNORECASE)


def _doi(value):
    normalized = _DOI_PREFIX.sub("", str(value or "").strip().lower())
    return re.sub(r"^doi:\s*", "", normalized).rstrip(".,;)")


def _term(value):
    if not isinstance(value, dict):
        return str(value or "").strip()
    term = value.get("term")
    if isinstance(term, dict):
        return str(term.get("en_US") or term.get("es_PE") or "").strip()
    return str(
        value.get("value")
        or value.get("en_US")
        or value.get("es_PE")
        or value.get("en_GB")
        or ""
    ).strip()


def _contributors(data):
    names = []
    for contributor in data.get("contributors") or []:
        if not isinstance(contributor, dict):
            continue
        name = contributor.get("name") or {}
        first = str(name.get("firstName") or "").strip()
        last = str(name.get("lastName") or "").strip()
        if first or last:
            names.append(", ".join(part for part in (last, first) if part))
    return names


def _curation_default(record):
    metadata = record["metadatos_origen"]
    data = metadata["data"]
    visibility = data.get("visibility") or {}
    if isinstance(visibility, dict):
        visibility = visibility.get("key", "FREE")
    versions = data.get("electronicVersions") or []
    identifiers = data.get("identifiers") or []
    keywords = []
    for group in data.get("keywordGroups") or []:
        if not isinstance(group, dict):
            continue
        group_name = _term(group.get("name"))
        for classification in group.get("classifications") or []:
            term = _term(classification)
            if term:
                keywords.append(f"{group_name}: {term}" if group_name else term)
    return {
        "title": record["titulo"],
        "publication_year": record["anio_publicacion"],
        "type": _term(data.get("type")) or record["tipo"] or "",
        "language": _term(data.get("language")),
        "category": _term(data.get("category")),
        "portal_url": str(data.get("portalUrl") or "").strip(),
        "contributors": _contributors(data),
        "identifiers": [
            f"{item.get('value')} ({item.get('idSource')})"
            if item.get("idSource") else str(item.get("value") or "")
            for item in identifiers if isinstance(item, dict) and item.get("value")
        ],
        "keywords_groups": keywords,
        "abstract": _term(data.get("abstract")),
        "volumen": data.get("volume"),
        "number_of_pages": data.get("numberOfPages"),
        "pages": data.get("pages"),
        "electronic_versions": [
            _doi(item.get("doi"))
            for item in versions if isinstance(item, dict) and item.get("doi")
        ],
        "create_date": str(data.get("createdDate") or "")[:10] or None,
        "create_by": data.get("createdBy"),
        "journal_number": data.get("journalNumber"),
        "peer_review": data.get("peerReview", True),
        "type_discriminator": _term(data.get("typeDiscriminator")),
        "bibliographical_note": _term(data.get("bibliographicalNote")),
        "visibility": visibility,
        "modified_date": str(data.get("modifiedDate") or "")[:10] or None,
        "submission_year": data.get("submissionYear"),
        "system_name": _term(data.get("systemName")) or "ResearchOutput",
        "sub_title": _term(data.get("subTitle")),
        "publication_status": [
            _term(item.get("publicationStatus"))
            for item in data.get("publicationStatuses") or []
            if isinstance(item, dict) and _term(item.get("publicationStatus"))
        ] or ["Published"],
        "links": [
            {
                "pure_id": item.get("pureId"),
                "link_type": _term(item.get("linkType")) or "Enlace externo",
                "url": item.get("url"),
                "description": _term(item.get("description")),
            }
            for item in data.get("links") or []
            if isinstance(item, dict) and item.get("pureId") and item.get("url")
        ],
    }


def _curacion_automatica(record):
    """Adapta campos opcionales sin truncarlos; conserva el origen en metadata."""
    values = _curation_default(record)
    values.update(record["metadatos_origen"].get("curacion") or {})
    omitted = []
    blockers = []

    def omit(field, reason):
        omitted.append({"campo": field, "motivo": reason})

    def bounded_optional(field, maximum):
        value = values[field]
        if value and len(str(value)) > maximum:
            values[field] = None if field in {
                "abstract", "bibliographical_note", "sub_title", "pages"
            } else ""
            omit(field, f"supera {maximum} caracteres")

    for field, maximum in (
        ("abstract", 4000), ("journal_number", 10),
        ("bibliographical_note", 500), ("pages", 15),
        ("sub_title", 500), ("create_by", 50),
    ):
        bounded_optional(field, maximum)

    for field, maximum in (
        ("identifiers", 100), ("keywords_groups", 100),
        ("publication_status", 30), ("electronic_versions", 255),
    ):
        items = values[field]
        if len(items) > 100:
            values[field] = []
            omit(field, "se omitió la lista por exceder 100 elementos")
            continue
        valid = [item for item in items if len(str(item)) <= maximum]
        if len(valid) != len(items):
            omit(field, f"{len(items) - len(valid)} elemento(s) exceden {maximum} caracteres")
        unique = list(dict.fromkeys(valid))
        if len(unique) != len(valid):
            omit(field, "se quitaron valores repetidos")
        values[field] = unique

    contributors = values["contributors"]
    if not contributors:
        blockers.append("No hay contribuyentes para registrar.")
    if len(contributors) > 200:
        blockers.append("Hay más de 200 contribuyentes.")
    if any(len(name) > 120 for name in contributors):
        blockers.append("Un contribuyente excede los 120 caracteres.")
    if len(contributors) != len(set(contributors)):
        blockers.append("Hay nombres de contribuyentes repetidos.")

    links = values["links"]
    if len(links) > 100:
        blockers.append("Hay más de 100 enlaces.")
    else:
        valid_links = []
        seen_link_ids = set()
        for link in links:
            raw_pure_id = link.get("pure_id")
            url = str(link.get("url") or "").strip()
            link_type = str(link.get("link_type") or "").strip()
            description = str(link.get("description") or "").strip()
            if isinstance(raw_pure_id, int) and not isinstance(raw_pure_id, bool):
                pure_id = raw_pure_id
            elif isinstance(raw_pure_id, str) and re.fullmatch(
                r"\d+", raw_pure_id.strip()
            ):
                pure_id = int(raw_pure_id.strip())
            else:
                pure_id = 0
            valid = (
                pure_id > 0
                and pure_id <= 9223372036854775807
                and len(link_type) <= 50
                and bool(re.fullmatch(r"https?://\S+", url, re.IGNORECASE))
                and len(url) <= 255
                and len(description) <= 100
            )
            if not valid:
                omit("links", "se excluyó un enlace inválido o fuera de límite")
                continue
            if pure_id in seen_link_ids:
                blockers.append("Hay enlaces con identificador Pure repetido.")
                continue
            seen_link_ids.add(pure_id)
            valid_links.append({
                **link, "pure_id": pure_id, "link_type": link_type,
                "url": url, "description": description or None,
            })
        values["links"] = valid_links

    for field, maximum in (("type", 50), ("language", 30), ("category", 50)):
        value = str(values[field] or "").strip()
        values[field] = value
        if not value:
            blockers.append(f"Falta el campo obligatorio {field}.")
        elif len(value) > maximum:
            blockers.append(f"{field} excede {maximum} caracteres.")

    portal_url = str(values["portal_url"] or "").strip()
    values["portal_url"] = portal_url
    if (
        len(portal_url) > 255
        or not re.fullmatch(r"https?://\S+", portal_url, re.IGNORECASE)
    ):
        blockers.append("La URL del portal falta, es inválida o excede 255 caracteres.")

    values["type_discriminator"] = (
        values["type_discriminator"]
        or historico.TIPOS_PUBLICACION.get(values["type"], "ContributionToJournal")
    )
    if len(str(values["type_discriminator"])) > 50:
        values["type_discriminator"] = historico.TIPOS_PUBLICACION.get(
            values["type"], "ContributionToJournal")
        omit("type_discriminator", "se usó la clasificación compatible con el tipo")
    if len(str(values["system_name"] or "")) > 50:
        values["system_name"] = "ResearchOutput"
        omit("system_name", "se usó el nombre estándar del sistema")
    if len(str(values["visibility"] or "")) > 50:
        values["visibility"] = "UNKNOWN"
        omit("visibility", "se marcó como desconocida para no asumir acceso abierto")
    for field, maximum in (
        ("type_discriminator", 50), ("visibility", 50), ("system_name", 50),
    ):
        value = str(values[field] or "").strip()
        if not value or len(value) > maximum:
            blockers.append(f"{field} falta o excede {maximum} caracteres.")
        values[field] = value

    peer_review = values["peer_review"]
    if isinstance(peer_review, str) and peer_review.strip().lower() in {"true", "false"}:
        peer_review = peer_review.strip().lower() == "true"
        values["peer_review"] = peer_review
    if not isinstance(peer_review, bool):
        blockers.append("El valor de revisión por pares no es booleano.")

    for field in ("volumen", "number_of_pages"):
        raw = values[field]
        if raw in (None, ""):
            values[field] = None
            continue
        if isinstance(raw, int) and not isinstance(raw, bool):
            number = raw
        elif isinstance(raw, str) and re.fullmatch(r"\d+", raw.strip()):
            number = int(raw.strip())
        else:
            values[field] = None
            omit(field, "el valor no es un entero; se dejó vacío")
            continue
        if number <= 0 or number > 2147483647:
            values[field] = None
            omit(field, "el valor queda fuera del rango entero positivo; se dejó vacío")
        else:
            values[field] = number

    for field in ("create_date", "modified_date"):
        raw = values[field]
        if raw:
            try:
                date.fromisoformat(str(raw))
            except ValueError:
                values[field] = None
                omit(field, "fecha inválida; se usará la fecha predeterminada del catálogo")

    submission_year = values["submission_year"]
    try:
        submission_year = int(submission_year)
    except (TypeError, ValueError):
        submission_year = 0
    if not 1900 <= submission_year <= 2100:
        values["submission_year"] = values["publication_year"]
        omit("submission_year", "se usó el año de publicación como valor de reemplazo")
    else:
        values["submission_year"] = submission_year

    return values, omitted, blockers


def _autor_uuid_pure(metadata):
    return {
        str(contributor.get("person", {}).get("uuid", "")).strip()
        for contributor in metadata.get("data", {}).get("contributors") or []
        if isinstance(contributor, dict)
        and isinstance(contributor.get("person"), dict)
        and contributor.get("person", {}).get("uuid")
    }


def _investigadores_pure_exactos(person_uuids, pure_people):
    matched = set()
    for person_uuid in set(person_uuids):
        researcher_codes = pure_people.get(person_uuid, [])
        if len(researcher_codes) == 1:
            matched.add(researcher_codes[0])
    return sorted(matched)


def _clasificar_candidatura_lote(candidate, links, doi_duplicado=False, uuid_existente=False):
    metadata = candidate["metadatos_origen"]
    _curation, _omitted, reasons = _curacion_automatica(candidate)
    exact_links = [
        link["codigo_ucsm"]
        for link in links
        if link["estado_revision"] == "pendiente"
        and link["pure_person_id"]
        and link["pure_person_id"] in _autor_uuid_pure(metadata)
    ]
    if not exact_links:
        reasons.append("No hay autor vinculado por UUID exacto a un perfil aprobado.")
    if doi_duplicado:
        reasons.append("El DOI coincide con otra candidatura o publicación del Histórico.")
    if uuid_existente:
        reasons.append("El UUID ya existe en el Histórico.")
    record = {
        "titulo": candidate["titulo"],
        "anio_publicacion": candidate["anio_publicacion"],
        "tipo": candidate["tipo"],
        "metadatos_origen": metadata,
    }
    try:
        _publicacion_datos(metadata, record)
    except ErrorOperacion as error:
        reasons.append(str(error))
    return {
        "id": candidate["id"],
        "titulo": candidate["titulo"],
        "vinculos_exactos": sorted(set(exact_links)),
        "motivos": list(dict.fromkeys(reasons)),
    }


def _publicacion_datos(metadata, record):
    defaults = _curation_default(record)
    curated = metadata.get("curacion") or {}
    values = {**defaults, **curated}
    if not values["type"] or not values["language"] or not values["category"]:
        raise ErrorOperacion(
            "Complete el tipo, idioma y categoría de la publicación antes de aprobarla.")
    if not values["portal_url"]:
        raise ErrorOperacion("La publicación necesita una URL de portal antes de aprobarla.")
    if not values["contributors"]:
        raise ErrorOperacion("La publicación necesita al menos un contribuyente.")
    return values


def _coordinador_activo(cursor, codigo_ucsm):
    cursor.execute(
        "SELECT 1 FROM coordinador_repositorios "
        "WHERE codigo_ucsm = %s AND fecha_retiro IS NULL",
        (codigo_ucsm,),
    )
    if cursor.fetchone() is None:
        raise ErrorOperacion("El coordinador no existe o ya fue retirado.")


def importar_pure(records, nombre_archivo, codigo_coordinador, contenido):
    """Guarda filas válidas como candidatas; nunca publica en historico."""
    if not records:
        raise ErrorOperacion("El archivo no contiene publicaciones válidas para importar.")

    digest = hashlib.sha256(contenido).hexdigest()
    resultado = {
        "filas_validas": len(records),
        "candidatas_creadas": 0,
        "candidatas_en_lote": 0,
        "ya_en_historico": 0,
        "ya_importadas": 0,
        "posibles_duplicados_doi": 0,
        "vinculos_pure_exactos": 0,
        "campos_opcionales_omitidos": 0,
        "lote_sha256": digest,
    }
    conn = conectar()
    try:
        with conn.cursor() as cursor:
            _coordinador_activo(cursor, codigo_coordinador)
            source_ids = [record["id_fuente"] for record in records]
            cursor.execute(
                "SELECT uuid::text FROM historico WHERE uuid::text = ANY(%s)",
                (source_ids,),
            )
            official_ids = {row[0] for row in cursor.fetchall()}
            cursor.execute(
                "SELECT id_fuente FROM publicacion_candidata "
                "WHERE fuente = 'pure' AND id_fuente = ANY(%s)",
                (source_ids,),
            )
            candidate_ids = {row[0] for row in cursor.fetchall()}
            dois = list({
                record["doi_normalizado"] for record in records
                if record["doi_normalizado"]
            })
            existing_dois = set()
            if dois:
                cursor.execute(
                    "SELECT lower(regexp_replace(regexp_replace("
                    "btrim(e.electronic_versions), "
                    "'^https?://(dx[.])?doi[.]org/', '', 'i'), "
                    "'^doi:[[:space:]]*', '', 'i')) "
                    "FROM historico_electronic_versions e "
                    "WHERE lower(regexp_replace(regexp_replace("
                    "btrim(e.electronic_versions), "
                    "'^https?://(dx[.])?doi[.]org/', '', 'i'), "
                    "'^doi:[[:space:]]*', '', 'i')) = ANY(%s) "
                    "UNION SELECT lower(regexp_replace(regexp_replace("
                    "btrim(c.doi_normalizado), "
                    "'^https?://(dx[.])?doi[.]org/', '', 'i'), "
                    "'^doi:[[:space:]]*', '', 'i')) "
                    "FROM publicacion_candidata c "
                    "WHERE lower(regexp_replace(regexp_replace("
                    "btrim(c.doi_normalizado), "
                    "'^https?://(dx[.])?doi[.]org/', '', 'i'), "
                    "'^doi:[[:space:]]*', '', 'i')) = ANY(%s)",
                    (dois, dois),
                )
                existing_dois = {row[0] for row in cursor.fetchall()}

            cursor.execute(
                "SELECT codigo_ucsm, btrim(pure_person_id) "
                "FROM investigador WHERE pure_person_id IS NOT NULL"
            )
            pure_people = {}
            for code, person_id in cursor.fetchall():
                if person_id:
                    pure_people.setdefault(person_id.strip(), []).append(code)

            for record in records:
                source_id = record["id_fuente"]
                if source_id in official_ids:
                    resultado["ya_en_historico"] += 1
                    continue
                if source_id in candidate_ids:
                    resultado["ya_importadas"] += 1
                    continue

                metadata = dict(record["metadatos_origen"])
                metadata["importacion"] = {
                    "archivo": Path(nombre_archivo or "pure.csv").name,
                    "sha256": digest,
                    "coordinador": codigo_coordinador,
                    "fecha": datetime.now(timezone.utc).isoformat(),
                }
                curation, omitted, blockers = _curacion_automatica({
                    **record, "metadatos_origen": metadata,
                })
                metadata["curacion"] = curation
                metadata["curacion_automatica"] = {
                    "version": 1,
                    "campos_omitidos": omitted,
                    "bloqueos": blockers,
                }
                cursor.execute(
                    "INSERT INTO publicacion_candidata "
                    "(fuente, id_fuente, doi_normalizado, titulo, anio_publicacion, "
                    "tipo, metadatos_origen) "
                    "VALUES ('pure', %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (fuente, id_fuente) DO NOTHING "
                    "RETURNING id",
                    (
                        source_id, record["doi_normalizado"], record["titulo"],
                        record["anio_publicacion"], record["tipo"], Json(metadata),
                    ),
                )
                inserted = cursor.fetchone()
                if inserted is None:
                    resultado["ya_importadas"] += 1
                    continue
                candidate_id = inserted[0]
                resultado["candidatas_creadas"] += 1
                resultado["campos_opcionales_omitidos"] += len(omitted)
                if record["doi_normalizado"] in existing_dois:
                    resultado["posibles_duplicados_doi"] += 1
                for researcher_code in _investigadores_pure_exactos(
                    record["pure_person_uuids"], pure_people
                ):
                    cursor.execute(
                        "INSERT INTO publicacion_candidata_investigador "
                        "(publicacion_candidata_id, codigo_ucsm) "
                        "VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        (candidate_id, researcher_code),
                    )
                    resultado["vinculos_pure_exactos"] += cursor.rowcount
            cursor.execute(
                "SELECT COUNT(*) FROM publicacion_candidata "
                "WHERE fuente = 'pure' "
                "AND metadatos_origen #>> '{importacion,sha256}' = %s",
                (digest,),
            )
            resultado["candidatas_en_lote"] = cursor.fetchone()[0]
        conn.commit()
        return resultado
    except psycopg2.Error as error:
        conn.rollback()
        raise ErrorOperacion(_mensaje_operacion(error)) from error
    finally:
        conn.close()


def _clasificar_lote_cursor(cursor, lote_sha256, bloquear=False):
    lock_clause = " FOR UPDATE" if bloquear else ""
    cursor.execute(
        "SELECT id, id_fuente, titulo, anio_publicacion, tipo, doi_normalizado, "
        "estado, metadatos_origen FROM publicacion_candidata "
        "WHERE fuente = 'pure' "
        "AND metadatos_origen #>> '{importacion,sha256}' = %s "
        "ORDER BY id" + lock_clause,
        (lote_sha256,),
    )
    columns = [column[0] for column in cursor.description]
    candidates = [dict(zip(columns, row)) for row in cursor.fetchall()]
    if not candidates:
        raise ErrorOperacion("No se encontraron candidaturas para esta importación.")

    candidate_ids = [candidate["id"] for candidate in candidates]
    source_ids = [candidate["id_fuente"] for candidate in candidates]
    dois = list({
        candidate["doi_normalizado"].strip().lower()
        for candidate in candidates if candidate["doi_normalizado"]
    })
    cursor.execute(
        "SELECT publicacion_candidata_id, codigo_ucsm, estado_revision, "
        "btrim(i.pure_person_id) AS pure_person_id "
        "FROM publicacion_candidata_investigador r "
        "JOIN investigador i ON i.codigo_ucsm = r.codigo_ucsm "
        "WHERE publicacion_candidata_id = ANY(%s) "
        "ORDER BY publicacion_candidata_id, codigo_ucsm"
        + (" FOR UPDATE OF r, i" if bloquear else ""),
        (candidate_ids,),
    )
    links_by_candidate = {}
    for candidate_id, researcher_code, link_state, pure_person_id in cursor.fetchall():
        links_by_candidate.setdefault(candidate_id, []).append({
            "codigo_ucsm": researcher_code,
            "estado_revision": link_state,
            "pure_person_id": (pure_person_id or "").strip(),
        })

    official_ids = set()
    if source_ids:
        cursor.execute(
            "SELECT uuid::text FROM historico WHERE uuid::text = ANY(%s)",
            (source_ids,),
        )
        official_ids = {row[0] for row in cursor.fetchall()}

    duplicate_dois = set()
    if dois:
        cursor.execute(
            "SELECT doi FROM (SELECT lower(regexp_replace(regexp_replace("
            "btrim(doi_normalizado), "
            "'^https?://(dx[.])?doi[.]org/', '', 'i'), "
            "'^doi:[[:space:]]*', '', 'i')) AS doi "
            "FROM publicacion_candidata "
            "WHERE lower(regexp_replace(regexp_replace("
            "btrim(doi_normalizado), "
            "'^https?://(dx[.])?doi[.]org/', '', 'i'), "
            "'^doi:[[:space:]]*', '', 'i')) = ANY(%s)) candidates "
            "GROUP BY doi HAVING COUNT(*) > 1 "
            "UNION SELECT lower(regexp_replace(regexp_replace("
            "btrim(e.electronic_versions), "
            "'^https?://(dx[.])?doi[.]org/', '', 'i'), "
            "'^doi:[[:space:]]*', '', 'i')) "
            "FROM historico_electronic_versions e "
            "WHERE lower(regexp_replace(regexp_replace("
            "btrim(e.electronic_versions), "
            "'^https?://(dx[.])?doi[.]org/', '', 'i'), "
            "'^doi:[[:space:]]*', '', 'i')) = ANY(%s)",
            (dois, dois),
        )
        duplicate_dois = {row[0] for row in cursor.fetchall()}

    eligible = []
    manual = []
    finalized = {"consolidada": 0, "descartada": 0}
    reason_counts = {}
    omitted_fields = 0
    for candidate in candidates:
        if candidate["estado"] != "pendiente":
            finalized[candidate["estado"]] = finalized.get(candidate["estado"], 0) + 1
            continue

        metadata = candidate["metadatos_origen"]
        automatic = metadata.get("curacion_automatica")
        if automatic is None:
            _curation, omitted, _blockers = _curacion_automatica(candidate)
            automatic = {
                "campos_omitidos": omitted,
            }
        omitted_fields += len(automatic.get("campos_omitidos") or [])
        doi = (candidate["doi_normalizado"] or "").strip().lower()
        entry = _clasificar_candidatura_lote(
            candidate,
            links_by_candidate.get(candidate["id"], []),
            doi_duplicado=bool(doi and doi in duplicate_dois),
            uuid_existente=candidate["id_fuente"] in official_ids,
        )
        reasons = entry["motivos"]
        if entry["motivos"]:
            manual.append(entry)
            for reason in entry["motivos"]:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
        else:
            eligible.append(entry)

    return {
        "lote_sha256": lote_sha256,
        "total": len(candidates),
        "aptas": len(eligible),
        "revision_manual": len(manual),
        "consolidadas": finalized.get("consolidada", 0),
        "descartadas": finalized.get("descartada", 0),
        "campos_opcionales_omitidos": omitted_fields,
        "motivos_revision": [
            {"motivo": reason, "cantidad": amount}
            for reason, amount in sorted(
                reason_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "muestra_aptas": eligible[:10],
        "muestra_revision": manual[:10],
        "_aptas": eligible,
    }


def resumen_lote_pure(lote_sha256):
    conn = conectar()
    try:
        with conn.cursor() as cursor:
            result = _clasificar_lote_cursor(cursor, lote_sha256)
            result.pop("_aptas", None)
            return result
    except psycopg2.Error as error:
        raise ErrorOperacion(_mensaje_operacion(error)) from error
    finally:
        conn.close()


def listar(filtro="", limite=50, desplazamiento=0):
    filtro = (filtro or "").strip()
    patron = f"%{filtro}%"
    condicion = (
        "fuente = 'pure' AND estado <> 'descartada' "
        "AND (%s = '' OR titulo ILIKE %s OR id_fuente ILIKE %s "
        "OR COALESCE(doi_normalizado, '') ILIKE %s)"
    )
    filas = _consultar(
        f"""
        SELECT id, id_fuente, titulo, anio_publicacion, tipo, doi_normalizado,
               estado, creada_en,
               (SELECT COUNT(*) FROM publicacion_candidata_investigador x
                 WHERE x.publicacion_candidata_id = c.id
                   AND x.estado_revision = 'pendiente') AS pendientes,
               (SELECT COUNT(*) FROM publicacion_candidata_investigador x
                 WHERE x.publicacion_candidata_id = c.id
                   AND x.estado_revision = 'aceptada') AS aceptadas
          FROM publicacion_candidata c
         WHERE {condicion}
         ORDER BY CASE estado WHEN 'pendiente' THEN 0 ELSE 1 END, creada_en DESC, id
         LIMIT %s OFFSET %s
        """,
        (filtro, patron, patron, patron, limite, desplazamiento),
    )
    total = _consultar(
        f"SELECT COUNT(*) AS total FROM publicacion_candidata WHERE {condicion}",
        (filtro, patron, patron, patron),
    )[0]["total"]
    return {"items": filas, "total": total, "limite": limite, "desplazamiento": desplazamiento}


def obtener(candidata_id):
    filas = _consultar(
        "SELECT id, id_fuente, titulo, anio_publicacion, tipo, doi_normalizado, "
        "estado, creada_en, metadatos_origen "
        "FROM publicacion_candidata WHERE id = %s AND fuente = 'pure'",
        (candidata_id,),
    )
    if not filas:
        return None
    record = filas[0]
    record["curacion"] = {
        **_curation_default(record),
        **(record["metadatos_origen"].get("curacion") or {}),
    }
    record["investigadores"] = _consultar(
        """
        SELECT r.codigo_ucsm,
               p.apellido_paterno || ' ' || p.apellido_materno || ', ' || p.nombres AS nombre,
               r.estado_revision, r.motivo, i.pure_person_id
          FROM publicacion_candidata_investigador r
          JOIN investigador i ON i.codigo_ucsm = r.codigo_ucsm
          JOIN persona p ON p.dni = i.dni
         WHERE r.publicacion_candidata_id = %s
         ORDER BY nombre
        """,
        (candidata_id,),
    )
    pure_person_uuids = {
        str(contributor.get("person", {}).get("uuid", "")).strip()
        for contributor in record["metadatos_origen"]["data"].get("contributors") or []
        if isinstance(contributor, dict)
        and isinstance(contributor.get("person"), dict)
    }
    for researcher in record["investigadores"]:
        pure_person_id = (researcher["pure_person_id"] or "").strip()
        researcher["coincidencia_pure_exacta"] = bool(
            pure_person_id and pure_person_id in pure_person_uuids)
    doi = record["doi_normalizado"]
    record["posible_duplicado_doi"] = bool(doi and _consultar(
        """
        SELECT EXISTS (
          SELECT 1 FROM historico_electronic_versions
           WHERE lower(regexp_replace(regexp_replace(
             btrim(electronic_versions),
             '^https?://(dx[.])?doi[.]org/', '', 'i'),
             '^doi:[[:space:]]*', '', 'i')) = %s
          UNION ALL
          SELECT 1 FROM publicacion_candidata
           WHERE id <> %s AND lower(regexp_replace(regexp_replace(
             btrim(doi_normalizado),
             '^https?://(dx[.])?doi[.]org/', '', 'i'),
             '^doi:[[:space:]]*', '', 'i')) = %s
        ) AS existe
        """,
        (doi, candidata_id, doi),
    )[0]["existe"])
    return record


def guardar_curacion(candidata_id, datos, codigo_coordinador):
    conn = conectar()
    try:
        with conn.cursor() as cursor:
            _coordinador_activo(cursor, codigo_coordinador)
            cursor.execute(
                "SELECT estado, metadatos_origen FROM publicacion_candidata "
                "WHERE id = %s AND fuente = 'pure' FOR UPDATE",
                (candidata_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise ErrorOperacion("No se encontró la candidatura de Pure.")
            if row[0] != "pendiente":
                raise ErrorOperacion("Solo se pueden depurar candidaturas pendientes.")
            metadata = row[1]
            metadata["curacion"] = datos
            lote_sha256 = (metadata.get("importacion") or {}).get("sha256")
            cursor.execute(
                "UPDATE publicacion_candidata "
                "SET titulo = %s, anio_publicacion = %s, tipo = %s, "
                "metadatos_origen = %s, actualizada_en = CURRENT_TIMESTAMP "
                "WHERE id = %s",
                (
                    datos["title"], datos["publication_year"], datos["type"],
                    Json(metadata), candidata_id,
                ),
            )
        conn.commit()
        return lote_sha256
    except psycopg2.Error as error:
        conn.rollback()
        raise ErrorOperacion(_mensaje_operacion(error)) from error
    finally:
        conn.close()


def descartar(candidata_id, codigo_coordinador, motivo):
    conn = conectar()
    try:
        with conn.cursor() as cursor:
            _coordinador_activo(cursor, codigo_coordinador)
            cursor.execute(
                "SELECT estado, metadatos_origen FROM publicacion_candidata "
                "WHERE id = %s AND fuente = 'pure' FOR UPDATE",
                (candidata_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise ErrorOperacion("No se encontró la candidatura de Pure.")
            if row[0] != "pendiente":
                raise ErrorOperacion(
                    "Solo se pueden descartar candidaturas pendientes.")
            metadata = row[1]
            metadata["descarte"] = {
                "motivo": motivo.strip(),
                "coordinador": codigo_coordinador,
                "fecha": datetime.now(timezone.utc).isoformat(),
            }
            cursor.execute(
                "UPDATE publicacion_candidata "
                "SET estado = 'descartada', metadatos_origen = %s, "
                "actualizada_en = CURRENT_TIMESTAMP WHERE id = %s",
                (Json(metadata), candidata_id),
            )
        conn.commit()
    except psycopg2.Error as error:
        conn.rollback()
        raise ErrorOperacion(_mensaje_operacion(error)) from error
    finally:
        conn.close()


def vincular_investigador(candidata_id, codigo_ucsm, codigo_coordinador):
    conn = conectar()
    try:
        with conn.cursor() as cursor:
            _coordinador_activo(cursor, codigo_coordinador)
            cursor.execute(
                "SELECT estado FROM publicacion_candidata "
                "WHERE id = %s AND fuente = 'pure' FOR UPDATE",
                (candidata_id,),
            )
            candidate = cursor.fetchone()
            if candidate is None:
                raise ErrorOperacion("No se encontró la candidatura de Pure.")
            if candidate[0] == "descartada":
                raise ErrorOperacion("La candidatura fue descartada.")
            cursor.execute(
                "INSERT INTO publicacion_candidata_investigador "
                "(publicacion_candidata_id, codigo_ucsm) "
                "VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (candidata_id, codigo_ucsm),
            )
            if cursor.rowcount == 0:
                raise ErrorOperacion("El investigador ya está vinculado a esta candidatura.")
        conn.commit()
    except psycopg2.Error as error:
        conn.rollback()
        raise ErrorOperacion(_mensaje_operacion(error)) from error
    finally:
        conn.close()


def _resolver_vinculo_cursor(
    cursor, candidata_id, codigo_ucsm, codigo_coordinador, resultado, motivo=None
):
    cursor.execute(
        "SELECT id_fuente, titulo, anio_publicacion, tipo, estado, metadatos_origen "
        "FROM publicacion_candidata "
        "WHERE id = %s AND fuente = 'pure' FOR UPDATE",
        (candidata_id,),
    )
    row = cursor.fetchone()
    if row is None:
        raise ErrorOperacion("No se encontró la candidatura de Pure.")
    source_id, title, year, publication_type, candidate_state, metadata = row
    if candidate_state == "descartada":
        raise ErrorOperacion("La candidatura fue descartada.")
    cursor.execute(
        "SELECT estado_revision FROM publicacion_candidata_investigador "
        "WHERE publicacion_candidata_id = %s AND codigo_ucsm = %s FOR UPDATE",
        (candidata_id, codigo_ucsm),
    )
    association = cursor.fetchone()
    if association is None:
        raise ErrorOperacion("Vincule primero al investigador con la candidatura.")
    if association[0] != "pendiente":
        raise ErrorOperacion("Este vínculo ya fue revisado.")

    if resultado == "aceptada":
        record = {
            "titulo": title,
            "anio_publicacion": year,
            "tipo": publication_type,
            "metadatos_origen": metadata,
        }
        data = _publicacion_datos(metadata, record)
        cursor.execute(
            "SELECT 1 FROM historico WHERE uuid = %s::uuid",
            (source_id,),
        )
        if cursor.fetchone() is None:
            params, types = historico.parametros_importacion(
                data, codigo_coordinador, source_id)
            marks = ", ".join(
                "%s" + ("::" + sql_type if sql_type else "")
                for sql_type in types
            )
            cursor.execute(
                f"CALL sp_cargar_historico({marks})",
                params,
            )
        cursor.execute(
            "UPDATE publicacion_candidata_investigador "
            "SET estado_revision = 'aceptada', revisado_por = %s, "
            "revisado_en = CURRENT_TIMESTAMP, motivo = NULL "
            "WHERE publicacion_candidata_id = %s AND codigo_ucsm = %s",
            (codigo_coordinador, candidata_id, codigo_ucsm),
        )
        cursor.execute(
            "INSERT INTO investigador_historico "
            "(codigo_ucsm, uuid, publicacion_candidata_id, codigo_ucsm_coordinador) "
            "VALUES (%s, %s::uuid, %s, %s) "
            "ON CONFLICT (codigo_ucsm, uuid) DO NOTHING",
            (codigo_ucsm, source_id, candidata_id, codigo_coordinador),
        )
        cursor.execute(
            "UPDATE publicacion_candidata SET estado = 'consolidada', "
            "actualizada_en = CURRENT_TIMESTAMP WHERE id = %s",
            (candidata_id,),
        )
    else:
        cursor.execute(
            "UPDATE publicacion_candidata_investigador "
            "SET estado_revision = %s, revisado_por = %s, "
            "revisado_en = CURRENT_TIMESTAMP, motivo = %s "
            "WHERE publicacion_candidata_id = %s AND codigo_ucsm = %s",
            (resultado, codigo_coordinador, motivo, candidata_id, codigo_ucsm),
        )


def resolver_vinculo(candidata_id, codigo_ucsm, codigo_coordinador, resultado, motivo=None):
    conn = conectar()
    try:
        with conn.cursor() as cursor:
            _coordinador_activo(cursor, codigo_coordinador)
            _resolver_vinculo_cursor(
                cursor, candidata_id, codigo_ucsm, codigo_coordinador,
                resultado, motivo)
        conn.commit()
    except psycopg2.Error as error:
        conn.rollback()
        raise ErrorOperacion(_mensaje_operacion(error)) from error
    finally:
        conn.close()


def aprobar_lote_pure(lote_sha256, codigo_coordinador):
    if not re.fullmatch(r"[a-f0-9]{64}", lote_sha256 or ""):
        raise ErrorOperacion("El identificador del lote no es válido.")
    conn = conectar()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            _coordinador_activo(cursor, codigo_coordinador)
            cursor.execute(
                "SELECT id, metadatos_origen FROM publicacion_candidata "
                "WHERE fuente = 'pure' AND estado = 'pendiente' "
                "AND metadatos_origen #>> '{importacion,sha256}' = %s "
                "ORDER BY id FOR UPDATE",
                (lote_sha256,),
            )
            candidates = cursor.fetchall()
            person_uuids = set()
            for _candidate_id, metadata in candidates:
                person_uuids.update(_autor_uuid_pure(metadata))
            pure_people = {}
            if person_uuids:
                cursor.execute(
                    "SELECT btrim(pure_person_id), codigo_ucsm "
                    "FROM investigador WHERE pure_person_id IS NOT NULL "
                    "AND btrim(pure_person_id) <> '' "
                    "AND btrim(pure_person_id) = ANY(%s)",
                    (list(person_uuids),),
                )
                for person_uuid, researcher_code in cursor.fetchall():
                    pure_people.setdefault(person_uuid, []).append(researcher_code)
                for candidate_id, metadata in candidates:
                    for researcher_code in _investigadores_pure_exactos(
                        _autor_uuid_pure(metadata), pure_people
                    ):
                        cursor.execute(
                            "INSERT INTO publicacion_candidata_investigador "
                            "(publicacion_candidata_id, codigo_ucsm) "
                            "VALUES (%s, %s) ON CONFLICT DO NOTHING",
                            (candidate_id, researcher_code),
                        )
            batch = _clasificar_lote_cursor(cursor, lote_sha256, bloquear=True)
            for candidate in batch["_aptas"]:
                for researcher_code in candidate["vinculos_exactos"]:
                    _resolver_vinculo_cursor(
                        cursor, candidate["id"], researcher_code,
                        codigo_coordinador, "aceptada")
        conn.commit()
        return {
            "lote_sha256": lote_sha256,
            "publicaciones_consolidadas": batch["aptas"],
            "vinculos_aprobados": sum(
                len(candidate["vinculos_exactos"])
                for candidate in batch["_aptas"]
            ),
            "revision_manual": batch["revision_manual"],
        }
    except psycopg2.Error as error:
        conn.rollback()
        raise ErrorOperacion(_mensaje_operacion(error)) from error
    except ErrorOperacion:
        conn.rollback()
        raise
    finally:
        conn.close()


def _consultar(sql, parametros):
    conn = conectar()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, parametros)
            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    except psycopg2.Error as error:
        raise ErrorOperacion(_mensaje_operacion(error)) from error
    finally:
        conn.close()
