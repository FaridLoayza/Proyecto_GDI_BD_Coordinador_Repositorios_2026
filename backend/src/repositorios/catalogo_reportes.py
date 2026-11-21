"""Las 15 consultas (reportes) del aplicativo.

Cada reporte es un procedimiento almacenado (sp_reporte_01 ... sp_reporte_15,
Bloque F de base_datos_repositorio.sql) que abre un cursor con el resultado.
8 de ellos usan JOIN (requisito: al menos 6 de 10). Son de solo lectura y
consideran solo registros activos (borrado logico).
"""

CONSULTAS = [
    {"id": 1, "titulo": "Total de investigadores", "usa_join": False},
    {"id": 2, "titulo": "Escuelas profesionales con más investigadores", "usa_join": False},
    {"id": 3, "titulo": "Directorio de investigadores con datos personales", "usa_join": True},
    {"id": 4, "titulo": "Investigadores sin patentes asociadas", "usa_join": True},
    {"id": 5, "titulo": "Evolución de publicaciones por año", "usa_join": False},
    {"id": 6, "titulo": "Producción por tipo de documento", "usa_join": False},
    {"id": 7, "titulo": "Publicaciones recientes por fecha de creación", "usa_join": False},
    {"id": 8, "titulo": "Publicaciones por idioma", "usa_join": False},
    {"id": 9, "titulo": "Reportes generados por coordinador", "usa_join": True},
    {"id": 10, "titulo": "Enlaces de cada publicación", "usa_join": True},
    {"id": 11, "titulo": "Investigadores asociados a cada ODS", "usa_join": True},
    {"id": 12, "titulo": "Patentes por país de registro y entidad", "usa_join": False},
    {"id": 13, "titulo": "Investigadores con sus ODS vinculados", "usa_join": True},
    {"id": 14, "titulo": "Patentes con sus inventores registrados", "usa_join": True},
    {"id": 15, "titulo": "Formatos de investigador y coordinador que los valida", "usa_join": True},
]

for _consulta in CONSULTAS:
    _consulta["procedimiento"] = f"sp_reporte_{_consulta['id']:02d}"
