"""
Esquemas explicitos para la normalizacion a parquet.

El encargo exige: "fija dtypes explicitos y parsea fechas con formato declarado,
no con inferencia". Aqui viven esas declaraciones. Si el CSV real trae una
columna que no esta en el esquema, normalize.py aborta (fallo ruidoso).

Encabezados observados el 2026-08-27 (peticion Range a los CSV 'acumulado'):

  carpetas (21 col):
    anio_inicio, mes_inicio, fecha_inicio, hora_inicio, anio_hecho, mes_hecho,
    fecha_hecho, hora_hecho, delito, categoria_delito, competencia, fiscalia,
    agencia, unidad_investigacion, colonia_hecho, colonia_catalogo,
    alcaldia_hecho, alcaldia_catalogo, municipio_hecho, latitud, longitud

  victimas (22 col): igual que carpetas pero SIN fiscalia/agencia/
    unidad_investigacion y CON sexo, edad, tipo_persona, calidad_juridica.
"""
from __future__ import annotations

import polars as pl

# Formato de fecha DECLARADO (no se infiere).
#
# HALLAZGO 2026-08-27: las columnas fecha_inicio / fecha_hecho NO tienen un
# formato unico en el archivo acumulado. Hasta ~mediados de 2024 traen solo la
# fecha ("YYYY-MM-DD", 10 chars) y la hora va aparte en hora_*. Desde ~mediados
# de 2024 (y todo 2025) traen un timestamp completo ("YYYY-MM-DD HH:MM:SS",
# 19 chars). Ver memory.md.
#
# Regla de normalizacion (explicita, no inferida):
#   - fecha_*  = primeros 10 caracteres, parseados con "%Y-%m-%d".
#   - dt_*     = timestamp completo con "%Y-%m-%d %H:%M:%S" si la cadena lo trae;
#                si no, fecha (10 chars) + hora_* ("%H:%M:%S"); si no hay hora,
#                medianoche.
DATE_FMT = "%Y-%m-%d"
DATETIME_FMT = "%Y-%m-%d %H:%M:%S"
TIME_FMT = "%H:%M:%S"

# Sentinelas de nulo que aparecen en estos CSV.
NULL_TOKENS = ["", "NA", "N/A", "ND", "N/D", "NULL", "null", "(null)", "SIN DATO", "NO ESPECIFICADO"]

# --- CARPETAS ---------------------------------------------------------------
# Todo entra como Utf8 en la lectura (control total); luego se castea explicito.
CARPETAS_READ_SCHEMA: dict[str, pl.DataType] = {
    "anio_inicio": pl.Utf8,
    "mes_inicio": pl.Utf8,
    "fecha_inicio": pl.Utf8,
    "hora_inicio": pl.Utf8,
    "anio_hecho": pl.Utf8,
    "mes_hecho": pl.Utf8,
    "fecha_hecho": pl.Utf8,
    "hora_hecho": pl.Utf8,
    "delito": pl.Utf8,
    "categoria_delito": pl.Utf8,
    "competencia": pl.Utf8,
    "fiscalia": pl.Utf8,
    "agencia": pl.Utf8,
    "unidad_investigacion": pl.Utf8,
    "colonia_hecho": pl.Utf8,
    "colonia_catalogo": pl.Utf8,
    "alcaldia_hecho": pl.Utf8,
    "alcaldia_catalogo": pl.Utf8,
    "municipio_hecho": pl.Utf8,
    "latitud": pl.Utf8,
    "longitud": pl.Utf8,
}

# dtype final por columna tras el casteo explicito.
CARPETAS_FINAL: dict[str, str] = {
    "anio_inicio": "Int32",
    "mes_inicio": "Utf8",
    "fecha_inicio": "Date",
    "hora_inicio": "Time",
    "dt_inicio": "Datetime",          # derivada: fecha_inicio + hora_inicio
    "anio_hecho": "Int32",
    "mes_hecho": "Utf8",
    "fecha_hecho": "Date",
    "hora_hecho": "Time",
    "dt_hecho": "Datetime",           # derivada
    "delito": "Utf8",
    "categoria_delito": "Utf8",
    "competencia": "Utf8",
    "fiscalia": "Utf8",
    "agencia": "Utf8",
    "unidad_investigacion": "Utf8",
    "colonia_hecho": "Utf8",
    "colonia_catalogo": "Utf8",
    "alcaldia_hecho": "Utf8",
    "alcaldia_catalogo": "Utf8",
    "municipio_hecho": "Utf8",
    "latitud": "Float64",
    "longitud": "Float64",
    # banderas de calidad derivadas
    "fecha_inicio_parse_ok": "Boolean",
    "fecha_hecho_parse_ok": "Boolean",
    "rezago_denuncia_dias": "Int32",  # dt_inicio - dt_hecho, en dias
}

# --- VICTIMAS -------------------------------------------------------------
VICTIMAS_READ_SCHEMA: dict[str, pl.DataType] = {
    "anio_inicio": pl.Utf8,
    "mes_inicio": pl.Utf8,
    "fecha_inicio": pl.Utf8,
    "hora_inicio": pl.Utf8,
    "anio_hecho": pl.Utf8,
    "mes_hecho": pl.Utf8,
    "fecha_hecho": pl.Utf8,
    "hora_hecho": pl.Utf8,
    "delito": pl.Utf8,
    "categoria_delito": pl.Utf8,
    "sexo": pl.Utf8,
    "edad": pl.Utf8,
    "tipo_persona": pl.Utf8,
    "calidad_juridica": pl.Utf8,
    "competencia": pl.Utf8,
    "colonia_hecho": pl.Utf8,
    "colonia_catalogo": pl.Utf8,
    "alcaldia_hecho": pl.Utf8,
    "alcaldia_catalogo": pl.Utf8,
    "municipio_hecho": pl.Utf8,
    "latitud": pl.Utf8,
    "longitud": pl.Utf8,
}

VICTIMAS_FINAL: dict[str, str] = {
    "anio_inicio": "Int32",
    "mes_inicio": "Utf8",
    "fecha_inicio": "Date",
    "hora_inicio": "Time",
    "dt_inicio": "Datetime",
    "anio_hecho": "Int32",
    "mes_hecho": "Utf8",
    "fecha_hecho": "Date",
    "hora_hecho": "Time",
    "dt_hecho": "Datetime",
    "delito": "Utf8",
    "categoria_delito": "Utf8",
    "sexo": "Utf8",
    "edad": "Int32",
    "tipo_persona": "Utf8",
    "calidad_juridica": "Utf8",
    "competencia": "Utf8",
    "colonia_hecho": "Utf8",
    "colonia_catalogo": "Utf8",
    "alcaldia_hecho": "Utf8",
    "alcaldia_catalogo": "Utf8",
    "municipio_hecho": "Utf8",
    "latitud": "Float64",
    "longitud": "Float64",
    "fecha_inicio_parse_ok": "Boolean",
    "fecha_hecho_parse_ok": "Boolean",
    "rezago_denuncia_dias": "Int32",
}

# --- Bounding box CDMX (trabajo; se reajusta contra el shp de AGEB) --------
# Ver assumptions.md [ASSUMP-09].
CDMX_BBOX = {"lon_min": -99.365, "lon_max": -98.940, "lat_min": 19.048, "lat_max": 19.593}

# Rango valido de fechas del hecho para el reporte de calidad.
FECHA_HECHO_MIN = "2016-01-01"   # inicio de la serie FGJ
