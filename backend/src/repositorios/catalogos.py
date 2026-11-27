"""Listas fijas que usan los formularios."""

ODS = [
    "ODS 1: Fin de la pobreza",
    "ODS 2: Hambre cero",
    "ODS 3: Salud y bienestar",
    "ODS 4: Educación de calidad",
    "ODS 5: Igualdad de género",
    "ODS 6: Agua limpia y saneamiento",
    "ODS 7: Energía asequible y no contaminante",
    "ODS 8: Trabajo decente y crecimiento económico",
    "ODS 9: Industria, innovación e infraestructura",
    "ODS 10: Reducción de las desigualdades",
    "ODS 11: Ciudades y comunidades sostenibles",
    "ODS 12: Producción y consumo responsables",
    "ODS 13: Acción por el clima",
    "ODS 14: Vida submarina",
    "ODS 15: Vida de ecosistemas terrestres",
    "ODS 16: Paz, justicia e instituciones sólidas",
    "ODS 17: Alianzas para lograr los objetivos",
]

GENEROS = ["Femenino", "Masculino"]

# Lista cerrada de escuelas profesionales de la universidad. Se usa para validar el
# formulario de postulación: evita que la misma escuela quede escrita de
# formas distintas por cada investigador.
ESCUELAS = [
    "Administración de Empresas",
    "Arquitectura",
    "Ciencia Política y Gobierno",
    "Comunicación Social",
    "Contabilidad",
    "Derecho",
    "Educación Inicial",
    "Enfermería",
    "Farmacia y Bioquímica",
    "Ingeniería Ambiental",
    "Ingeniería Biomédica",
    "Ingeniería Biotecnológica",
    "Ingeniería Civil",
    "Ingeniería Comercial",
    "Ingeniería de Minas",
    "Ingeniería de Sistemas",
    "Ingeniería en Inteligencia Artificial",
    "Ingeniería Industrial",
    "Ingeniería Mecánica",
    "Ingeniería Mecánica Eléctrica",
    "Ingeniería Mecatrónica",
    "Medicina Humana",
    "Medicina Veterinaria y Zootecnia",
    "Obstetricia y Puericultura",
    "Odontología",
    "Psicología",
    "Publicidad y Multimedia",
    "Tecnología Médica",
]

TIPOS_PUBLICACION = {          # tipo -> type_discriminator
    "Article": "ContributionToJournal",
    "Conference paper": "ContributionToConference",
    "Book": "Book",
    "Chapter": "ContributionToBookAnthology",
}
IDIOMAS = ["English", "Spanish", "Portuguese"]
CATEGORIAS = ["Research", "Review", "Thesis"]
