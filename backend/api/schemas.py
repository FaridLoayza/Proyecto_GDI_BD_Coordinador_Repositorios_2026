"""Esquemas HTTP y validaciones de los formularios del portal."""
import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..src.repositorios.catalogos import ESCUELAS_UCSM, ODS
from .orcid import checksum_valido


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginBody(StrictModel):
    role: Literal["coordinator", "investigator"]
    email: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=1, max_length=200)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("Ingrese un correo válido.")
        return value


class ApplicationBody(StrictModel):
    dni: str = Field(pattern=r"^[0-9]{8}$")
    codigo_ucsm: int = Field(ge=1000000000, le=9999999999)
    correo: str = Field(min_length=3, max_length=100)
    nombres: str = Field(min_length=1, max_length=60)
    apellido_paterno: str = Field(min_length=1, max_length=40)
    apellido_materno: str = Field(min_length=1, max_length=40)
    genero: Literal["Femenino", "Masculino"]
    fecha_nacimiento: date
    escuela: str = Field(min_length=1, max_length=60)
    celular: str = Field(pattern=r"^9[0-9]{8}$")
    orcid: str = Field(pattern=r"^[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9X]$")
    scopus_id: int = Field(gt=0)
    link_cti: str = Field(min_length=8, max_length=255)
    resumen: str = Field(min_length=1, max_length=2000)
    foto: str = Field(min_length=5, max_length=255)
    ods: list[str] = Field(min_length=1, max_length=17)
    intereses: list[str] = Field(min_length=1, max_length=30)

    @field_validator("correo")
    @classmethod
    def normalize_email(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("Ingrese un correo válido.")
        return value

    @field_validator("celular", mode="before")
    @classmethod
    def celular_como_texto(cls, value):
        # El celular llega como entero cuando se recarga desde la base de
        # datos (columna INTEGER); se normaliza a texto para que la
        # validación de formato funcione igual en el registro y en el reenvío.
        if isinstance(value, int):
            return str(value)
        return value

    @field_validator("escuela")
    @classmethod
    def escuela_debe_ser_de_la_lista_oficial(cls, value):
        value = value.strip()
        if value not in ESCUELAS_UCSM:
            raise ValueError(
                "Seleccione una escuela profesional de la lista de la UCSM."
            )
        return value

    @field_validator("fecha_nacimiento")
    @classmethod
    def birth_date_must_be_past(cls, value):
        if value >= date.today():
            raise ValueError("La fecha de nacimiento debe ser anterior a hoy.")
        return value

    @field_validator("link_cti")
    @classmethod
    def cti_must_be_https(cls, value):
        value = value.strip()
        if not value.startswith("https://"):
            raise ValueError("El enlace CTI Vitae debe comenzar con https://.")
        return value

    @field_validator("orcid")
    @classmethod
    def valid_orcid_checksum(cls, value):
        if not checksum_valido(value):
            raise ValueError("El ORCID debe tener un dígito de control válido.")
        return value

    @field_validator("foto")
    @classmethod
    def photo_reference_must_have_image_extension(cls, value):
        value = value.strip()
        if not re.search(r"\.(jpg|jpeg|png)$", value, re.IGNORECASE):
            raise ValueError("La referencia de foto debe terminar en .jpg, .jpeg o .png.")
        return value

    @field_validator("ods")
    @classmethod
    def ods_must_be_valid(cls, value):
        if len(set(value)) != len(value) or any(item not in ODS for item in value):
            raise ValueError("Seleccione ODS válidos sin repetir.")
        return value

    @field_validator("intereses")
    @classmethod
    def normalize_interests(cls, value):
        normalized = [item.strip() for item in value if item.strip()]
        if not normalized or any(len(item) > 100 for item in normalized):
            raise ValueError("Ingrese intereses de investigación válidos (máximo 100 caracteres).")
        if len(set(normalized)) != len(normalized):
            raise ValueError("No repita intereses de investigación.")
        return normalized

    @field_validator("nombres", "apellido_paterno", "apellido_materno", "escuela", "resumen")
    @classmethod
    def trim_required_text(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Este campo no puede quedar vacío.")
        return value

    def to_procedure_payload(self):
        return {
            "dni": self.dni,
            "codigo_ucsm": str(self.codigo_ucsm),
            "correo": self.correo,
            "nombres": self.nombres,
            "apellido_paterno": self.apellido_paterno,
            "apellido_materno": self.apellido_materno,
            "genero": self.genero,
            "fecha_nacimiento": self.fecha_nacimiento.isoformat(),
            "escuela": self.escuela,
            "celular": str(self.celular),
            "orcid": self.orcid,
            "scopus_id": str(self.scopus_id),
            "link_cti": self.link_cti,
            "resumen": self.resumen,
            "foto": self.foto,
            "ods": self.ods,
            "intereses": self.intereses,
        }


class RegisterBody(StrictModel):
    application: ApplicationBody
    password: str = Field(min_length=12, max_length=200)


class InvestigatorDecisionBody(StrictModel):
    resultado: Literal["aprobada", "rechazada"]
    motivo: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def require_rejection_reason(self):
        if self.resultado == "rechazada" and not (self.motivo or "").strip():
            raise ValueError("Indique el motivo del rechazo.")
        return self


class ObservationBody(StrictModel):
    motivo: str = Field(min_length=1, max_length=2000)

    @field_validator("motivo")
    @classmethod
    def trim_motive(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Indique qué debe corregir el investigador.")
        return value


class ManualVerificationBody(StrictModel):
    fuente: Literal["codigo_ucsm", "afiliacion", "orcid", "scopus", "cti_vitae", "renacyt"]
    resultado: Literal[
        "confirmado", "no_confirmado", "no_disponible", "error_consulta", "requiere_revision"
    ]
    referencia: str | None = Field(default=None, max_length=500)
    nota: str | None = Field(default=None, max_length=2000)


class PatentBody(StrictModel):
    n_patente: str = Field(pattern=r"^[A-Z]{2}-[0-9]{4,10}$", max_length=20)
    titulo: str = Field(min_length=1, max_length=200)
    editorial: str = Field(min_length=1, max_length=100)
    fecha_registro: date
    cip: str = Field(min_length=1, max_length=20)
    pais: str = Field(min_length=1, max_length=50)
    inventores: list[int] = Field(min_length=1, max_length=50)
    clasificacion_ocde: list[dict[str, str]] = Field(min_length=1, max_length=10)

    @field_validator("fecha_registro")
    @classmethod
    def registration_date_not_future(cls, value):
        if value > date.today():
            raise ValueError("La fecha de registro no puede ser futura.")
        return value

    @field_validator("titulo", "editorial", "cip", "pais")
    @classmethod
    def trim_patent_text(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Este campo no puede quedar vacío.")
        return value

    @field_validator("inventores")
    @classmethod
    def unique_inventors(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("No repita inventores.")
        return value

    @field_validator("clasificacion_ocde")
    @classmethod
    def valid_ocde_pairs(cls, value):
        pairs = []
        for item in value:
            campo = item.get("campo", "").strip()
            objetivo = item.get("objetivo", "").strip()
            if not campo or not objetivo:
                raise ValueError("Complete el campo y el objetivo OCDE.")
            if len(campo) > 100 or len(objetivo) > 100:
                raise ValueError("Los campos OCDE no pueden exceder 100 caracteres.")
            pairs.append((campo, objetivo))
        if len({campo for campo, _ in pairs}) != len(pairs):
            raise ValueError("No repita campos OCDE.")
        return [{"campo": campo, "objetivo": objetivo} for campo, objetivo in pairs]

    def to_procedure_payload(self):
        return {
            "n_patente": self.n_patente,
            "titulo": self.titulo,
            "editorial": self.editorial,
            "fecha_registro": self.fecha_registro,
            "cip": self.cip,
            "pais": self.pais,
            "inventores": self.inventores,
            "campos_ocde": [item["campo"] for item in self.clasificacion_ocde],
            "objetivos_ocde": [item["objetivo"] for item in self.clasificacion_ocde],
        }


class PatentDecisionBody(StrictModel):
    resultado: Literal["aprobada", "observada", "rechazada"]
    motivo: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def require_nonapproval_reason(self):
        if self.resultado != "aprobada" and not (self.motivo or "").strip():
            raise ValueError("Indique el motivo de la observación o rechazo.")
        return self


class PureRegistrationBody(StrictModel):
    pure_person_id: str = Field(min_length=1, max_length=120)

    @field_validator("pure_person_id")
    @classmethod
    def trim_pure_id(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Ingrese el identificador de persona de Pure.")
        return value


class CandidateOutputLink(StrictModel):
    pure_id: int = Field(gt=0, le=9223372036854775807)
    link_type: str = Field(min_length=1, max_length=50)
    url: str = Field(min_length=8, max_length=255)
    description: str | None = Field(default=None, max_length=100)

    @field_validator("link_type")
    @classmethod
    def trim_candidate_link_type(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("El tipo de enlace no puede quedar vacío.")
        return value

    @field_validator("url")
    @classmethod
    def valid_candidate_link_url(cls, value):
        value = value.strip()
        if not re.fullmatch(r"https?://\S+", value):
            raise ValueError("Ingrese una URL válida para el enlace.")
        return value


class CandidateCurationBody(StrictModel):
    title: str = Field(min_length=1, max_length=500)
    publication_year: int = Field(ge=1900, le=2100)
    type: str = Field(min_length=1, max_length=50)
    peer_review: bool = True
    language: str = Field(min_length=1, max_length=30)
    category: str = Field(min_length=1, max_length=50)
    portal_url: str = Field(min_length=8, max_length=255)
    contributors: list[str] = Field(min_length=1, max_length=200)
    identifiers: list[str] = Field(default_factory=list, max_length=100)
    keywords_groups: list[str] = Field(default_factory=list, max_length=100)
    abstract: str | None = Field(default=None, max_length=4000)
    volumen: int | None = Field(default=None, gt=0)
    number_of_pages: int | None = Field(default=None, gt=0)
    journal_number: str | None = Field(default=None, max_length=10)
    bibliographical_note: str | None = Field(default=None, max_length=500)
    publication_status: list[str] = Field(default_factory=list, max_length=100)
    links: list[CandidateOutputLink] = Field(default_factory=list, max_length=100)
    pages: str | None = Field(default=None, max_length=15)

    @field_validator("title", "type", "language", "category", "portal_url")
    @classmethod
    def trim_required_candidate_text(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Este campo no puede quedar vacío.")
        return value

    @field_validator("portal_url")
    @classmethod
    def valid_candidate_url(cls, value):
        if not re.fullmatch(r"https?://\S+", value):
            raise ValueError("Ingrese una URL válida del portal.")
        return value

    @field_validator("contributors", "identifiers", "keywords_groups")
    @classmethod
    def clean_candidate_lists(cls, values):
        normalized = [value.strip() for value in values if value.strip()]
        if len(normalized) != len(set(normalized)):
            raise ValueError("No repita valores en la lista.")
        return normalized

    @model_validator(mode="after")
    def validate_catalog_field_lengths(self):
        for value in self.contributors:
            if len(value) > 120:
                raise ValueError("Cada contribuyente puede tener hasta 120 caracteres.")
        for value in self.identifiers:
            if len(value) > 100:
                raise ValueError("Cada identificador puede tener hasta 100 caracteres.")
        for value in self.keywords_groups:
            if len(value) > 100:
                raise ValueError("Cada palabra clave puede tener hasta 100 caracteres.")
        for value in self.publication_status:
            if len(value) > 30:
                raise ValueError("Cada estado de publicación puede tener hasta 30 caracteres.")
        return self


class CandidateLinkBody(StrictModel):
    codigo_ucsm: int = Field(ge=1000000000, le=9999999999)


class CandidateDecisionBody(StrictModel):
    resultado: Literal["aceptada", "rechazada", "duplicada"]
    motivo: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def require_candidate_decision_reason(self):
        if self.resultado != "aceptada" and not (self.motivo or "").strip():
            raise ValueError("Indique el motivo del rechazo o de la duplicidad.")
        return self


class CandidateDiscardBody(StrictModel):
    motivo: str = Field(min_length=1, max_length=2000)

    @field_validator("motivo")
    @classmethod
    def trim_discard_reason(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Indique el motivo para descartar la candidatura.")
        return value


class PureBatchBody(StrictModel):
    lote_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ReportGenerateBody(StrictModel):
    fecha: date
