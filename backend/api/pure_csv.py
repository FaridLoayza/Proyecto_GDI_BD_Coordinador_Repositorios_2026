"""Validación estructural de exportaciones CSV de publicaciones de Pure."""
import csv
import io
import json
import re
import uuid


MAX_BYTES = 50 * 1024 * 1024
REQUIRED_COLUMNS = {"uuid", "title", "publication_year", "data", "synced_at"}
_DOI = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)


def _term(value):
    if not isinstance(value, dict):
        return value.strip() if isinstance(value, str) else ""
    term = value.get("term")
    if isinstance(term, dict):
        return term.get("en_US") or term.get("es_PE") or next(iter(term.values()), "")
    return value.get("value", "")


def _doi(metadata):
    candidates = []
    versions = metadata.get("electronicVersions") or []
    for version in versions:
        if isinstance(version, dict):
            candidates.append(version.get("doi"))
    identifiers = metadata.get("identifiers") or []
    for identifier in identifiers:
        if isinstance(identifier, dict):
            source = str(identifier.get("idSource") or "").lower()
            if source == "doi":
                candidates.append(identifier.get("value"))
    for candidate in candidates:
        value = str(candidate or "").strip().lower()
        value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value)
        value = re.sub(r"^doi:\s*", "", value)
        value = value.rstrip(".,;)")
        if _DOI.fullmatch(value):
            return value
    return None


def _contributors(metadata):
    values = []
    person_uuids = []
    for contributor in metadata.get("contributors") or []:
        if not isinstance(contributor, dict):
            continue
        name = contributor.get("name") or {}
        first = str(name.get("firstName") or "").strip()
        last = str(name.get("lastName") or "").strip()
        if first or last:
            values.append(", ".join(part for part in (last, first) if part))
        person = contributor.get("person")
        if isinstance(person, dict) and person.get("uuid"):
            person_uuids.append(str(person["uuid"]).strip())
    return values, list(dict.fromkeys(person_uuids))


def parse_pure_csv(content):
    """Devuelve filas válidas y un resumen; nunca escribe en la base de datos."""
    if len(content) > MAX_BYTES:
        raise ValueError("El archivo excede el límite de 50 MB.")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("El CSV debe estar codificado en UTF-8.") from error

    reader = csv.DictReader(io.StringIO(text, newline=""))
    columns = set(reader.fieldnames or [])
    missing = REQUIRED_COLUMNS - columns
    if missing:
        raise ValueError("Faltan columnas requeridas: " + ", ".join(sorted(missing)) + ".")

    records = []
    errors = []
    seen = set()
    doi_counts = {}
    total = 0
    duplicates = 0
    for line, row in enumerate(reader, start=2):
        if not row or all(not (value or "").strip() for value in row.values() if value is not None):
            continue
        total += 1
        try:
            source_id = str(uuid.UUID((row.get("uuid") or "").strip()))
            if source_id in seen:
                duplicates += 1
                raise ValueError("UUID repetido dentro del archivo.")
            seen.add(source_id)

            metadata = json.loads(row.get("data") or "")
            if not isinstance(metadata, dict):
                raise ValueError("La columna data debe contener un objeto JSON.")
            embedded_uuid = metadata.get("uuid")
            if embedded_uuid and str(uuid.UUID(str(embedded_uuid))) != source_id:
                raise ValueError("El UUID de data no coincide con la columna uuid.")

            title = (row.get("title") or "").strip()
            if not title:
                title = str(_term(metadata.get("title")) or "").strip()
            if not title or len(title) > 500:
                raise ValueError("El título es obligatorio y no debe exceder 500 caracteres.")
            year = int((row.get("publication_year") or "").strip())
            if not 1900 <= year <= 2100:
                raise ValueError("El año de publicación debe estar entre 1900 y 2100.")

            contributors, person_uuids = _contributors(metadata)
            metadata_type = _term(metadata.get("type"))
            doi = _doi(metadata)
            if doi:
                doi_counts[doi] = doi_counts.get(doi, 0) + 1
            records.append({
                "id_fuente": source_id,
                "titulo": title,
                "anio_publicacion": year,
                "tipo": str(metadata_type or "")[:80] or None,
                "doi_normalizado": doi,
                "contribuyentes": contributors,
                "pure_person_uuids": person_uuids,
                "metadatos_origen": {
                    "csv": {
                        "uuid": source_id,
                        "title": title,
                        "publication_year": year,
                        "synced_at": (row.get("synced_at") or "").strip(),
                    },
                    "data": metadata,
                },
            })
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            errors.append({"linea": line, "mensaje": str(error)})

    return records, {
        "filas": total,
        "validas": len(records),
        "invalidas": len(errors),
        "uuid_repetidos": duplicates,
        "doi_repetidos": sum(count - 1 for count in doi_counts.values() if count > 1),
        "errores": errors[:10],
        "muestra": [
            {
                "uuid": record["id_fuente"],
                "titulo": record["titulo"],
                "anio": record["anio_publicacion"],
                "tipo": record["tipo"],
                "doi": record["doi_normalizado"],
            }
            for record in records[:10]
        ],
    }
