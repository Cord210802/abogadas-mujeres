"""
Registro de fuentes verificadas para el pipeline de inseguridad urbana CDMX.

REGLA DURA: cada URL de este archivo fue obtenida de un catalogo o pagina
consultada en sesion (API CKAN de datos.cdmx.gob.mx, o pagina del INEGI) y
verificada con una peticion HTTP HEAD. NO se construyen URLs por patron.

Si el portal publica una actualizacion, hay que volver a consultar la API
(`GET /api/3/action/package_show?id=<slug>`) y sustituir la URL A MANO aqui.
Ver assumptions.md [ASSUMP-10].

`expected_bytes` es el Content-Length observado en el HEAD del 2026-08-27; sirve
solo como sanity check aproximado (los CSV "acumulado" crecen con cada refresh).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Source:
    key: str                 # identificador unico (nombre de archivo destino sin extension)
    group: str               # subcarpeta bajo data/raw/
    url: str                 # URL exacta verificada
    filename: str            # nombre del archivo tal cual se guarda en data/raw/<group>/
    period: str              # periodo que cubre el recurso (texto libre)
    kind: str                # csv | pdf | xlsx | shp_zip | csv_zip
    source_page: str         # pagina/catalogo de donde salio la URL
    expected_bytes: Optional[int] = None
    notes: str = ""
    checksum_check: bool = True   # si False, no se exige que el sha256 sea estable entre corridas


# ---------------------------------------------------------------------------
# NUCLEO — se descarga por defecto
# ---------------------------------------------------------------------------
CORE: list[Source] = [
    # --- Fuente 1: Carpetas de investigacion FGJ (vigente) ------------------
    Source(
        key="carpetasFGJ_acumulado",
        group="fgj_carpetas",
        url="https://archivo.datos.cdmx.gob.mx/FGJ/carpetas/carpetasFGJ_acumulado_2025_01.csv",
        filename="carpetasFGJ_acumulado_2025_01.csv",
        period="2016-01-01 .. >=2025-01 (nombre dice 2025_01; archivo re-subido 2025-09-05, rango real por confirmar al normalizar)",
        kind="csv",
        source_page="https://datos.cdmx.gob.mx/dataset/carpetas-de-investigacion-fgj-de-la-ciudad-de-mexico "
                    "(CKAN id 250f29c0-31c7-44dc-9d31-f7e6cc78b79e)",
        expected_bytes=559_894_090,
        notes="Recurso 'acumulado'. Unico recurso mantenido al dia. Serie continua; "
              "la reclasificacion de delitos de jul-2020 ocurre DENTRO del archivo.",
        checksum_check=False,  # crece con cada refresh del portal
    ),
    Source(
        key="nota_reclasificacion_carpetas",
        group="fgj_carpetas",
        url="https://datos.cdmx.gob.mx/dataset/250f29c0-31c7-44dc-9d31-f7e6cc78b79e/resource/"
            "360e2aa0-77e0-463c-b20d-345ef1c1d95b/download/nota-reclasificacion.pdf",
        filename="nota-reclasificacion.pdf",
        period="doc: reclasificacion de delitos jul-2020",
        kind="pdf",
        source_page="dataset carpetas-de-investigacion-fgj (CKAN)",
        expected_bytes=281_957,
    ),
    Source(
        key="nota_actualizacion_290720_carpetas",
        group="fgj_carpetas",
        url="https://datos.cdmx.gob.mx/dataset/250f29c0-31c7-44dc-9d31-f7e6cc78b79e/resource/"
            "1128fb92-59af-452f-ae38-36b4d835d23e/download/nota-actualizacion-290720-.pdf",
        filename="nota-actualizacion-290720.pdf",
        period="doc: nota de actualizacion 29-07-2020",
        kind="pdf",
        source_page="dataset carpetas-de-investigacion-fgj (CKAN)",
        expected_bytes=58_784,
    ),
    Source(
        key="nota_diferencia_secretariado_portal",
        group="fgj_carpetas",
        url="https://datos.cdmx.gob.mx/dataset/250f29c0-31c7-44dc-9d31-f7e6cc78b79e/resource/"
            "bcb29264-91fa-4cc6-8c7e-561d8eb771e9/download/nota-diferencia-entre-datos-del-secretariado-y-portal-cdmx.pdf",
        filename="nota-diferencia-secretariado-portal.pdf",
        period="doc: diferencia datos secretariado vs portal CDMX",
        kind="pdf",
        source_page="dataset carpetas-de-investigacion-fgj (CKAN)",
        expected_bytes=81_593,
    ),

    # --- Fuente 2: Victimas en carpetas de investigacion FGJ ---------------
    Source(
        key="victimasFGJ_acumulado",
        group="fgj_victimas",
        url="https://archivo.datos.cdmx.gob.mx/FGJ/victimas/victimasFGJ_acumulado_2024_09.csv",
        filename="victimasFGJ_acumulado_2024_09.csv",
        period="2019-01-01 .. 2024-09-30",
        kind="csv",
        source_page="https://datos.cdmx.gob.mx/dataset/victimas-en-carpetas-de-investigacion-fgj "
                    "(CKAN id 7593b324-6010-44f7-8132-cb8b2276c842)",
        expected_bytes=372_959_491,
        notes="Recurso 'acumulado'. La serie de victimas empieza en 2019 (no 2016) y "
              "NO hay datos posteriores a sep-2024 en el portal.",
        checksum_check=False,
    ),
    Source(
        key="diccionario_victimas",
        group="fgj_victimas",
        url="https://datos.cdmx.gob.mx/dataset/7593b324-6010-44f7-8132-cb8b2276c842/resource/"
            "10235569-f4a9-4876-9465-9780887df8e2/download/diccionario-de-victimas-actualizado.xlsx",
        filename="diccionario-de-victimas-actualizado.xlsx",
        period="doc: diccionario de datos de victimas",
        kind="xlsx",
        source_page="dataset victimas-en-carpetas-de-investigacion-fgj (CKAN)",
        expected_bytes=14_376,
    ),

    # --- Fuente 4: Geoestadistica ----------------------------------------
    Source(
        key="colonias_iecm_2022",
        group="geo",
        url="https://datos.cdmx.gob.mx/dataset/d8f83ce7-163d-4c2a-96e0-ae38d304c4a0/resource/"
            "e3bbadb4-f3de-4c52-b3f4-a4ffea4466a3/download/colonias_iecm_2022.zip",
        filename="colonias_iecm_2022.zip",
        period="delimitacion colonial IECM 2022",
        kind="shp_zip",
        source_page="https://datos.cdmx.gob.mx/dataset/colonias-del-iecm-2022 (CKAN)",
        expected_bytes=1_424_886,
    ),
    Source(
        key="diccionario_colonias_iecm_2022",
        group="geo",
        url="https://datos.cdmx.gob.mx/dataset/d8f83ce7-163d-4c2a-96e0-ae38d304c4a0/resource/"
            "cee6dbd2-7225-4d5d-ac70-6a843e501325/download/diccionario_coloniasiecm_2022.xlsx",
        filename="diccionario_colonias_iecm_2022.xlsx",
        period="doc: diccionario colonias IECM 2022",
        kind="xlsx",
        source_page="dataset colonias-del-iecm-2022 (CKAN)",
        expected_bytes=8_174,
    ),
    Source(
        key="ageb_urbanas_cdmx_mg2020",
        group="geo",
        url="https://datos.cdmx.gob.mx/dataset/d2ccf6ae-fdf4-407c-a15f-e7dfac2d509d/resource/"
            "b2e17ed0-f2d9-4540-94a1-e57e988b6668/download/poligono_ageb_urbanas_cdmx.zip",
        filename="poligono_ageb_urbanas_cdmx.zip",
        period="Marco Geoestadistico 2020 (INEGI) - AGEB urbanas, recorte CDMX",
        kind="shp_zip",
        source_page="https://datos.cdmx.gob.mx/dataset/ageb-urbanas-areas-geoestadisticas-basicas-urbanas (CKAN)",
        expected_bytes=1_659_316,
        notes="Rehospedado en portal CDMX; notes del dataset: 'Marco Geoestadistico 2020 "
              "generado por el INEGI'. Ver assumptions.md [ASSUMP-03].",
    ),
    Source(
        key="manzanas_cdmx_mg2020",
        group="geo",
        url="https://datos.cdmx.gob.mx/dataset/93a59c20-5bfd-43ec-b631-057e9f9f6891/resource/"
            "6987f6cd-2844-4baf-817b-ee0589a438d0/download/poligono_manzanas_cdmx.zip",
        filename="poligono_manzanas_cdmx.zip",
        period="Marco Geoestadistico 2020 (INEGI) - manzanas, recorte CDMX",
        kind="shp_zip",
        source_page="https://datos.cdmx.gob.mx/dataset/poligonos-de-manzanas-de-la-ciudad-de-mexico (CKAN)",
        expected_bytes=18_126_932,
        notes="Rehospedado en portal CDMX; vintage MG 2020. Ver assumptions.md [ASSUMP-03].",
    ),

    # --- Fuente 5: Censo 2020 por AGEB urbana, CDMX ----------------------
    Source(
        key="resageburb_09csv20",
        group="censo2020",
        url="https://www.inegi.org.mx/contenidos/programas/ccpv/iter/zip/resageburb20/resageburb_09csv20.zip",
        filename="resageburb_09csv20.zip",
        period="Censo 2020 - Principales resultados por AGEB y manzana urbana, entidad 09 (CDMX)",
        kind="csv_zip",
        source_page="https://www.inegi.org.mx/app/scitel/Default?ev=10 "
                    "(URL verificada con HEAD: 200, application/x-zip-compressed, 12472358 B, Last-Modified 2021-07-26)",
        expected_bytes=12_472_358,
        notes="Tabla RESAGEBURB completa. Incluye filas de resumen por entidad/municipio/"
              "localidad/AGEB/manzana; se etiquetan con columna 'nivel' al normalizar.",
    ),

    # --- Fuente 8: Atenciones de las Abogadas de las Mujeres (SEMUJERES) ---
    # La API CKAN devuelve las ligas con el host interno http://10.80.148.134;
    # se sustituye por https://datos.cdmx.gob.mx (mismo dataset/resource id) y
    # se verifico con HEAD el 2026-09-16: 200, text/csv.
    Source(
        key="abogadas_atenciones",
        group="abogadas",
        url="https://datos.cdmx.gob.mx/dataset/c9e96ab4-c127-4ee1-a222-bfa2b5d759de/resource/"
            "b1926485-e512-4c4f-a03a-5d489bce8740/download/b1926485-e512-4c4f-a03a-5d489bce8740.csv",
        filename="atenciones_abogadas_mujeres.csv",
        period="mar-2019 .. mar-2022 (una fila por atencion; fecha a nivel mes)",
        kind="csv",
        source_page="https://datos.cdmx.gob.mx/dataset/atenciones-abogadas-mujeres "
                    "(CKAN id c9e96ab4-c127-4ee1-a222-bfa2b5d759de; Last-Modified 2026-08-28)",
        expected_bytes=17_619_683,
        notes="Programa 'Abogadas de las Mujeres en el Ministerio Publico'. La agencia puede "
              "venir compartida ('TLP-2 Y 3'). Ver docs/abogadas/01_datos_y_limpieza.md.",
    ),
    Source(
        key="abogadas_diccionario",
        group="abogadas",
        url="https://datos.cdmx.gob.mx/dataset/c9e96ab4-c127-4ee1-a222-bfa2b5d759de/resource/"
            "f7902a6e-afd8-47e0-af46-34e4237e8fea/download/f7902a6e-afd8-47e0-af46-34e4237e8fea.csv",
        filename="diccionario_abogadas_mujeres.csv",
        period="doc: diccionario de datos",
        kind="csv",
        source_page="dataset atenciones-abogadas-mujeres (CKAN)",
        expected_bytes=3_442,
    ),
]


# ---------------------------------------------------------------------------
# OPCIONAL — no se descarga salvo que se pida explicitamente
# ---------------------------------------------------------------------------
OPTIONAL: list[Source] = [
    Source(
        key="pgj_carpetas_archivo",
        group="pgj_archivo",
        url="https://datos.cdmx.gob.mx/dataset/12d22477-bcf1-49ee-92aa-16a0d0a5817c/resource/"
            "3f308147-b1fc-49a9-92b7-e74f3f79aa9c/download/da_carpetas-de-investigacion-pgj-cdmx.csv",
        filename="da_carpetas-de-investigacion-pgj-cdmx.csv",
        period="2016-01-01 .. 2019-06-30 (esquema de delitos ANTERIOR a la reclasificacion)",
        kind="csv",
        source_page="https://datos.cdmx.gob.mx/dataset/carpetas-de-investigacion-pgj-cdmx (CKAN)",
        expected_bytes=204_571_101,
        notes="TRAMPA: dataset archivado, NO vigente. Solo para comparar esquema viejo vs nuevo.",
    ),
]


# ---------------------------------------------------------------------------
# APORTADO POR EL USUARIO — no lo descarga el pipeline
# ---------------------------------------------------------------------------
# ENVIPE (Encuesta Nacional de Victimizacion y Percepcion sobre Seguridad
# Publica), microdatos INEGI, 12 ediciones 2014-2025. El usuario entrego los
# .zip el 2026-08-28. sha256 + tamano en logs/manifest.csv (keys envipe_2014..
# envipe_2025). Descompresion -> data/raw/envipe/<anio>/ ; normalizacion a CDMX
# -> data/interim/envipe/ con scripts/envipe_normalize.py (ver envipe_schema.py).
#
# Cubre PARCIALMENTE el hueco de ENSU: la ENVIPE mide percepcion de inseguridad,
# desempeno de autoridades, cambio de habitos y victimizacion + cifra negra, con
# representatividad ESTATAL y periodicidad ANUAL (la ENSU es trimestral y por
# ciudad). No la reemplaza, pero permite la serie de percepcion 2014-2025 CDMX.
USER_PROVIDED = {
    "envipe_microdatos": {
        "descripcion": "ENVIPE microdatos 2014-2025 (6 tablas/edicion: TVivienda, THogar, TSDem, TMod_Vic, TPer_Vic1, TPer_Vic2).",
        "origen": "https://www.inegi.org.mx/programas/envipe/ (microdatos por edicion)",
        "formato": "DBF (2014-2020, ISO-8859-1) + CSV (2021-2025; 2021-2022 ISO-8859-1, 2023-2025 UTF-8)",
        "entrega": "12 .zip aportados por el usuario el 2026-08-28; provenance en logs/manifest.csv",
        "alcance_raw": "las 32 entidades, tal cual",
        "alcance_interim": "solo CDMX (cve_ent == '09'); ver assumptions.md [ASSUMP-ENVIPE-01]",
        "scripts": "scripts/envipe_schema.py, scripts/envipe_normalize.py",
    }
}


# ---------------------------------------------------------------------------
# BLOQUEADO — sin URL verificable (ver assumptions.md [BLOCK-ENSU])
# ---------------------------------------------------------------------------
BLOCKED = {
    "ensu_microdatos": {
        "descripcion": "ENSU microdatos trimestrales INEGI, 2016 a la fecha (tablas ENSU_VIV / ENSU_CS / ENSU_CB por trimestre).",
        "motivo": "SPA en JS no renderizable; la RNM solo expone metadatos, no los .zip de microdatos.",
        "mitigacion_parcial": "El usuario aporto microdatos ENVIPE 2014-2025 (ver USER_PROVIDED). Percepcion + victimizacion anual con representatividad estatal; no sustituye la granularidad trimestral/por-ciudad de la ENSU.",
        "catalogos_rnm": {
            "2022": "https://www.inegi.org.mx/rnm/index.php/catalog/976",
            "2023": "https://www.inegi.org.mx/rnm/index.php/catalog/859",
            "2024": "https://www.inegi.org.mx/rnm/index.php/catalog/969",
            "2025": "https://www.inegi.org.mx/rnm/index.php/catalog/1100",
        },
        "doc_abierta": "https://www.inegi.org.mx/contenidos/programas/ensu/doc/",
        "accion": "Requiere que el usuario aporte los enlaces o elija opcion (b)/(c). Ver assumptions.md.",
    }
}


def core_sources() -> list[Source]:
    return list(CORE)


def all_known() -> list[Source]:
    return list(CORE) + list(OPTIONAL)
