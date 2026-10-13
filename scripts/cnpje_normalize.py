#!/usr/bin/env python3
"""
Normaliza los datos abiertos del CNPJE (INEGI) de data/raw/cnpje/ a parquet en
data/interim/cnpje/  ->  las 32 entidades (la comparacion entre estados es el
punto de esta fuente; el filtro a CDMX se hace aguas abajo).

Contexto
  El Censo Nacional de Procuracion de Justicia Estatal se levanta cada anio y
  reporta el anio ANTERIOR: la edicion 2025 trae datos de 2024. Cada edicion
  cambia los identificadores de tabla (m1p8 en 2020 -> m1s2p2 en 2025) y los
  nombres de catalogo, igual que la ENVIPE. Por eso las tablas NO se toman por
  su nombre de archivo sino por la descripcion del indice (0_indice_*.csv), que
  es lo unico estable entre ediciones.

Que hace
  - recorre data/raw/cnpje/<edicion>/<familia>/;
  - lee el indice de cada familia y empata cada tabla contra TARGETS (regex
    sobre la descripcion, sin acentos); la edicion 2019 no trae indice y se
    resuelve con ALIAS_2019;
  - lee los csv como texto (sin inferencia), ISO-8859-1/UTF-8 -> UTF-8;
  - normaliza la entidad a cve_ent de dos digitos ('09' = CDMX) venga como
    cve_ent, cvegeo o entidad_a, y agrega nom_ent;
  - pega la descripcion de cada catalogo de la edicion como <columna>_desc
    (asi el codigo 3 de mediorec_a se lee 'En linea (via internet)' sin que
    nadie tenga que recordarlo);
  - agrega anio_edicion y anio_dato (= edicion - 1) al frente;
  - escribe:
      data/interim/cnpje/by_year/<edicion>_<target>.parquet  (fiel a la edicion)
      data/interim/cnpje/cnpje_<target>.parquet              (ediciones apiladas)
  - deja bitacora en logs/cnpje_normalize.log con el sha256 de cada salida.

data/raw/ no se modifica.

Uso:
  python scripts/cnpje_normalize.py                      # todo
  python scripts/cnpje_normalize.py denuncias_medio      # targets sueltos
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
import sys
import unicodedata
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "cnpje"
OUT = ROOT / "data" / "interim" / "cnpje"
LOGS = ROOT / "logs"
NLOG = LOGS / "cnpje_normalize.log"

# Descripcion (normalizada: minusculas, sin acentos) -> nombre canonico.
# Los patrones son estrictos a proposito: las descripciones del INEGI se
# parecen mucho entre si ("segun tipo" vs "segun tipo y grado de consumacion"
# vs "segun rango de edad, cargo y/o funcion y sexo") y un patron laxo mete dos
# tablas distintas bajo el mismo nombre. Si un target empata mas de una tabla
# en la misma edicion, el script avisa y se queda con la primera.
TARGETS: dict[str, str] = {
    "denuncias_medio": r"^denuncias, querellas.*, segun medio de recepcion, durante",
    "denuncias_total": r"^denuncias, querellas[^,]*(?: del fuero comun)?, durante el ano \d{4}\.$",
    "carpetas_abiertas": r"^carpetas de investigacion abiertas por el ministerio publico(?: del fuero comun)?, durante el ano \d{4}\.$",
    # La edicion 2021 (datos 2020) no publica el total de carpetas abiertas:
    # solo el desglose por agencia, que hay que sumar para reconstruirlo.
    "carpetas_abiertas_agencia": r"^carpetas de investigacion abiertas.*, segun (?:agencia y/o fiscalia|unidad administrativa)",
    "carpetas_delitos": r"^delitos registrados en las carpetas de investigacion abiertas.*, segun tipo, durante",
    "determinaciones": r"^determinaciones y/o conclusiones.*, segun tipo, durante",
    "determinaciones_delitos": r"^delitos registrados en las determinaciones.*, segun tipo, durante",
    "determinaciones_delito_x_tipo": r"^delitos registrados en las determinaciones.*, segun tipo de delito y tipo de determinacion",
    "personal_funcion": r"^personal (?:adscrito )?(?:a la|de la).*, segun (?:cargo y/o funcion|funcion principal) y sexo",
    "personal_total": r"^personal (?:adscrito )?(?:a la|de la).*, segun sexo, al cierre",
    "vehiculos_robados": r"^vehiculos (?:robados|reportados).*recuperados.*, segun tipo, durante",
    "bienes_robados": r"^(?:bienes|objetos) reportados.*recuperados.*, segun tipo de (?:bien|objeto)",
}

# La edicion 2019 no trae 0_indice: se mapea por nombre de archivo.
ALIAS_2019: dict[str, str] = {
    "per_func": "personal_funcion",
    "vehiroba": "vehiculos_robados",
}

ENT_COLS = ("cve_ent", "cvegeo", "entidad_a", "entidad")


def utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str) -> None:
    line = f"{utcnow()}  {msg}"
    print(line, flush=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    with NLOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )


def norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", strip_accents(s).lower()).strip()


def read_csv_text(path: Path) -> pl.DataFrame:
    """Todo como texto. Los csv del INEGI vienen en latin-1 o utf-8 con BOM."""
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    df = pl.read_csv(
        text.encode("utf-8"),
        infer_schema_length=0,
        truncate_ragged_lines=True,
        ignore_errors=True,
    )
    return df.rename({c: c.strip().lower().lstrip("﻿") for c in df.columns})


def read_index(fam_dir: Path) -> dict[str, str]:
    """{clave de archivo -> descripcion} a partir de 0_indice_*.csv."""
    hits = list(fam_dir.glob("conjunto_de_datos/0_indice*.csv"))
    if not hits:
        return {}
    idx = read_csv_text(hits[0])
    cols = {c.lower(): c for c in idx.columns}
    a, c = cols.get("archivo"), cols.get("contenido")
    if not a or not c:
        return {}
    return {
        str(r[a]).strip().lower(): str(r[c]).strip()
        for r in idx.iter_rows(named=True)
        if r[a]
    }


def match_target(descripcion: str) -> str | None:
    d = norm_text(descripcion)
    for name, pattern in TARGETS.items():
        if re.search(pattern, d):
            return name
    return None


def entity_catalog(fam_dir: Path) -> pl.DataFrame | None:
    """Catalogo de entidades de la edicion -> cve_ent (2 digitos) + nom_ent."""
    for pat in ("catalogos/cve_ent_*.csv", "catalogos/entidad_*.csv"):
        for path in fam_dir.glob(pat):
            cat = read_csv_text(path)
            key = next((c for c in cat.columns if c in ENT_COLS), cat.columns[0])
            name_col = next(
                (c for c in cat.columns if c in ("nom_ent", "descrip", "descripcion")),
                None,
            )
            if name_col is None:
                continue
            return (
                cat.select(
                    pl.col(key).cast(pl.String).str.zfill(2).alias("cve_ent"),
                    pl.col(name_col).cast(pl.String).alias("nom_ent"),
                )
                .unique(subset=["cve_ent"])
                .sort("cve_ent")
            )
    return None


def attach_catalogs(df: pl.DataFrame, fam_dir: Path, edicion: int) -> pl.DataFrame:
    """Pega <columna>_desc por cada catalogo de la edicion que empate columna."""
    for path in sorted(fam_dir.glob("catalogos/*.csv")):
        col = path.stem.replace(f"_cnpje{edicion}", "").lower()
        if col not in df.columns or col in ENT_COLS:
            continue
        cat = read_csv_text(path)
        if col not in cat.columns:
            continue
        desc_col = next(
            (c for c in cat.columns if c in ("descrip", "descripcion", "desc")), None
        )
        if desc_col is None:
            continue
        cat = (
            cat.select(
                pl.col(col).cast(pl.String).str.strip_chars(),
                pl.col(desc_col).cast(pl.String).alias(f"{col}_desc"),
            )
            .unique(subset=[col])
        )
        df = df.join(cat, on=col, how="left")
    return df


def normalize_entity(df: pl.DataFrame, ent_cat: pl.DataFrame | None) -> pl.DataFrame:
    src = next((c for c in ENT_COLS if c in df.columns), None)
    if src is None:
        return df.with_columns(
            pl.lit(None, dtype=pl.String).alias("cve_ent"),
            pl.lit(None, dtype=pl.String).alias("nom_ent"),
        )
    df = df.with_columns(
        pl.col(src).cast(pl.String).str.strip_chars().str.zfill(2).alias("cve_ent")
    )
    if "cvegeo" in df.columns and src != "cvegeo":
        df = df.drop("cvegeo")
    if ent_cat is not None:
        df = df.join(ent_cat, on="cve_ent", how="left")
    else:
        df = df.with_columns(pl.lit(None, dtype=pl.String).alias("nom_ent"))
    return df


# Columnas canonicas: el INEGI renombra la misma variable en cada edicion
# (fun_prin -> funcprin_a -> funcion_p -> carfunde_d -> carfunde_g) y renombra
# tambien los conteos. Se coalescen en un nombre estable para poder apilar.
# OJO: que el nombre sea estable no quiere decir que la variable lo sea; el
# desglose de personal cambia de significado en 2022 (de area de adscripcion a
# cargo). Ver docs/calidad_cnpje.md antes de comparar entre anios.
CANON: dict[str, tuple[str, ...]] = {
    "clasif_desc": (
        "fun_prin_desc",
        "funcprin_a_desc",
        "funcion_p_desc",
        "carfunde_d_desc",
        "carfunde_g_desc",
        "mediorec_a_desc",
    ),
    "n_total": ("sexostt", "denquett"),
}


def add_canonical(df: pl.DataFrame) -> pl.DataFrame:
    for nombre, fuentes in CANON.items():
        presentes = [c for c in fuentes if c in df.columns]
        if not presentes:
            continue
        expr = pl.coalesce([pl.col(c).cast(pl.String) for c in presentes])
        if nombre.startswith("n_"):
            expr = expr.str.strip_chars().cast(pl.Float64, strict=False)
        df = df.with_columns(expr.alias(nombre))
    return df


def tidy(df: pl.DataFrame, edicion: int, target: str, archivo: str) -> pl.DataFrame:
    front = ["anio_edicion", "anio_dato", "cve_ent", "nom_ent"]
    df = df.with_columns(
        pl.lit(edicion, dtype=pl.Int16).alias("anio_edicion"),
        pl.lit(edicion - 1, dtype=pl.Int16).alias("anio_dato"),
        pl.lit(target).alias("tabla"),
        pl.lit(archivo).alias("archivo_origen"),
    )
    rest = [c for c in df.columns if c not in front]
    return df.select(front + rest)


def build_dictionary() -> pl.DataFrame:
    """Un solo parquet con el significado de cada columna de cada edicion.

    Las tablas anchas del CNPJE (determinaciones trae 135 columnas) usan claves
    como 'decoef14' que cambian de prefijo entre ediciones; sin el diccionario
    no hay forma de saber que mide cada una. Es la misma leccion que dejo la
    auditoria de la ENVIPE: el catalogo se lee, no se recuerda.
    """
    filas = []
    for path in sorted(RAW.glob("*/*/diccionario_de_datos/*.csv")):
        edicion = int(path.parents[2].name)
        familia = path.parents[1].name
        dic = read_csv_text(path)
        cols = {c.lower(): c for c in dic.columns}
        col_c, col_d = cols.get("columna"), cols.get("descripcion")
        if not col_c or not col_d:
            continue
        filas.append(
            dic.select(
                pl.lit(edicion, dtype=pl.Int16).alias("anio_edicion"),
                pl.lit(edicion - 1, dtype=pl.Int16).alias("anio_dato"),
                pl.lit(familia).alias("familia"),
                pl.lit(path.stem.replace("diccionario_de_datos_", "")).alias("archivo"),
                pl.col(col_c).cast(pl.String).str.strip_chars().str.to_lowercase().alias("columna"),
                pl.col(col_d).cast(pl.String).alias("descripcion"),
            )
        )
    if not filas:
        return pl.DataFrame()
    return pl.concat(filas, how="diagonal_relaxed").sort(
        ["anio_edicion", "familia", "archivo", "columna"]
    )


def process(only: list[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "by_year").mkdir(parents=True, exist_ok=True)
    log("=== cnpje_normalize: inicio")

    piezas: dict[str, list[pl.DataFrame]] = {}
    faltantes: list[str] = []

    for ed_dir in sorted(p for p in RAW.iterdir() if p.is_dir() and p.name.isdigit()):
        edicion = int(ed_dir.name)
        for fam_dir in sorted(p for p in ed_dir.iterdir() if p.is_dir()):
            indice = read_index(fam_dir)
            ent_cat = entity_catalog(fam_dir)
            encontrados: set[str] = set()

            for csv_path in sorted(fam_dir.glob("conjunto_de_datos/*.csv")):
                clave = csv_path.stem.replace(f"_cnpje{edicion}", "").lower()
                if clave.startswith("0_indice"):
                    continue
                descripcion = indice.get(clave, "")
                target = match_target(descripcion) if descripcion else ALIAS_2019.get(clave)
                if target is None or (only and target not in only):
                    continue
                if target in encontrados:
                    log(
                        f"AVISO {edicion}/{fam_dir.name}: '{target}' ya se habia "
                        f"resuelto; se ignora {csv_path.name} ({descripcion[:90]})"
                    )
                    continue

                df = read_csv_text(csv_path)
                df = normalize_entity(df, ent_cat)
                df = attach_catalogs(df, fam_dir, edicion)
                df = add_canonical(df)
                df = tidy(df, edicion, target, csv_path.name)

                dest = OUT / "by_year" / f"{edicion}_{target}.parquet"
                df.write_parquet(dest)
                piezas.setdefault(target, []).append(df)
                encontrados.add(target)
                log(
                    f"{edicion}/{fam_dir.name}: {csv_path.name} -> {target} "
                    f"({df.height} filas, {df.width} cols)"
                )

            esperados = {
                "rec_humanos": {"personal_funcion"},
                "inicio": {"denuncias_medio", "denuncias_total"},
                "cierre": {"determinaciones"},
                "bienes": {"vehiculos_robados"},
            }.get(fam_dir.name, set())
            if only:
                esperados &= set(only)
            for falta in sorted(esperados - encontrados):
                faltantes.append(f"{edicion}/{fam_dir.name}: sin '{falta}'")

    for target, dfs in sorted(piezas.items()):
        apilado = pl.concat(dfs, how="diagonal_relaxed").sort(
            ["anio_dato", "cve_ent"], nulls_last=True
        )
        dest = OUT / f"cnpje_{target}.parquet"
        apilado.write_parquet(dest)
        anios = sorted(set(apilado["anio_dato"].to_list()))
        log(
            f"apilado {target}: {apilado.height} filas, {apilado.width} cols, "
            f"anios {anios[0]}-{anios[-1]}  sha256={sha256_file(dest)}"
        )

    dic = build_dictionary()
    if not dic.is_empty():
        dest = OUT / "cnpje_diccionario.parquet"
        dic.write_parquet(dest)
        log(f"diccionario: {dic.height} columnas documentadas  sha256={sha256_file(dest)}")

    for f in faltantes:
        log(f"AVISO {f}")
    log("=== cnpje_normalize: fin")


if __name__ == "__main__":
    pedidos = [a for a in sys.argv[1:] if not a.startswith("-")]
    desconocidos = [p for p in pedidos if p not in TARGETS]
    if desconocidos:
        raise SystemExit(
            f"target desconocido: {desconocidos}. Opciones: {sorted(TARGETS)}"
        )
    process(pedidos)
