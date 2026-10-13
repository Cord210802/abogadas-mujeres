#!/usr/bin/env python3
"""
Normaliza los archivos crudos de data/raw/ a parquet en data/interim/.

Principios:
  - data/raw/ NO se toca.
  - dtypes explicitos (ver schema.py). Nada de inferencia de tipos.
  - fechas parseadas con formato DECLARADO ("%Y-%m-%d"); lo que no parsea queda
    como null y se marca con una bandera *_parse_ok (NO se corrige, se cuantifica
    despues en el reporte de calidad).
  - si el CSV trae columnas que no estan en el esquema -> aborta (fallo ruidoso).
  - cada salida registra en logs/normalize.log: filas, columnas, nulos, rango de
    fechas, y sha256 del parquet.

Uso:
  python scripts/normalize.py                # todo lo que haya en raw
  python scripts/normalize.py fgj_carpetas fgj_victimas
  python scripts/normalize.py censo geo
"""
from __future__ import annotations

import datetime as dt
import hashlib
import sys
import zipfile
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))
import schema as S  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
LOGS = ROOT / "logs"
NLOG = LOGS / "normalize.log"


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


def _clean_null(expr: pl.Expr) -> pl.Expr:
    """Convierte los sentinelas de nulo (schema.NULL_TOKENS) en null real."""
    return (
        pl.when(expr.str.strip_chars().is_in(S.NULL_TOKENS))
        .then(None)
        .otherwise(expr.str.strip_chars())
    )


# --------------------------------------------------------------------------- #
# FGJ (carpetas / victimas): misma logica, distinto esquema
# --------------------------------------------------------------------------- #
def normalize_fgj(csv_path: Path, read_schema: dict, out_name: str, has_edad: bool) -> None:
    log(f"--- normalize_fgj: {csv_path.name}")

    # encoding: se intenta utf-8; si el archivo trae bytes invalidos, polars
    # avisa. Ver assumptions.md [ASSUMP-06].
    lf = pl.scan_csv(
        csv_path,
        schema_overrides=read_schema,
        infer_schema_length=0,          # 0 = no inferir, usar el esquema tal cual
        has_header=True,
        encoding="utf8",
        low_memory=True,
        rechunk=False,
    )

    got = lf.collect_schema().names()
    expected = list(read_schema)
    if got != expected:
        raise SystemExit(
            f"ABORTO: columnas inesperadas en {csv_path.name}.\n"
            f"  esperado: {expected}\n  obtenido: {got}"
        )

    # limpieza de sentinelas de nulo en todas las columnas de texto
    lf = lf.with_columns([_clean_null(pl.col(c)).alias(c) for c in expected])

    # --- casteos explicitos ---
    # fecha_*: primeros 10 chars, formato DECLARADO "%Y-%m-%d" (ver schema.py:
    #   el portal mezcla "YYYY-MM-DD" y "YYYY-MM-DD HH:MM:SS" en el mismo archivo).
    def date10(col: str) -> pl.Expr:
        return pl.col(col).str.slice(0, 10).str.strptime(pl.Date, format=S.DATE_FMT, strict=False)

    def parse_ok(col: str) -> pl.Expr:
        # null  -> venia vacia (dato ausente)
        # False -> venia con valor pero NO parsea con el formato declarado
        # True  -> parsea
        return (pl.when(pl.col(col).is_null())
                  .then(None)
                  .otherwise(date10(col).is_not_null()))

    def dt_full(fcol: str, hcol: str) -> pl.Expr:
        # timestamp completo si la cadena lo trae; si no, fecha (10) + hora_*
        full = pl.col(fcol).str.strptime(pl.Datetime("us"), format=S.DATETIME_FMT, strict=False)
        hora = pl.col(hcol).str.strptime(pl.Time, format=S.TIME_FMT, strict=False)
        hdur = pl.duration(hours=hora.dt.hour(), minutes=hora.dt.minute(),
                           seconds=hora.dt.second()).fill_null(pl.duration(seconds=0))
        base = date10(fcol).cast(pl.Datetime("us")) + hdur
        return pl.coalesce(full, base)

    exprs = [
        # anios: vienen a veces como "2015.0" -> quitar sufijo decimal antes de Int
        pl.col("anio_inicio").str.replace(r"\.0$", "").cast(pl.Int32, strict=False).alias("anio_inicio"),
        pl.col("anio_hecho").str.replace(r"\.0$", "").cast(pl.Int32, strict=False).alias("anio_hecho"),
        pl.col("mes_inicio").alias("mes_inicio"),
        pl.col("mes_hecho").alias("mes_hecho"),

        date10("fecha_inicio").alias("fecha_inicio"),
        date10("fecha_hecho").alias("fecha_hecho"),
        parse_ok("fecha_inicio").alias("fecha_inicio_parse_ok"),
        parse_ok("fecha_hecho").alias("fecha_hecho_parse_ok"),
        dt_full("fecha_inicio", "hora_inicio").alias("dt_inicio"),
        dt_full("fecha_hecho", "hora_hecho").alias("dt_hecho"),

        pl.col("hora_inicio").str.strptime(pl.Time, format=S.TIME_FMT, strict=False).alias("hora_inicio"),
        pl.col("hora_hecho").str.strptime(pl.Time, format=S.TIME_FMT, strict=False).alias("hora_hecho"),

        pl.col("latitud").cast(pl.Float64, strict=False).alias("latitud"),
        pl.col("longitud").cast(pl.Float64, strict=False).alias("longitud"),
    ]
    passthrough = ["delito", "categoria_delito", "competencia", "colonia_hecho",
                   "colonia_catalogo", "alcaldia_hecho", "alcaldia_catalogo", "municipio_hecho"]
    if has_edad:
        passthrough += ["sexo", "tipo_persona", "calidad_juridica"]
        exprs.append(
            pl.col("edad").str.replace(r"\.0$", "").cast(pl.Int32, strict=False).alias("edad")
        )
    else:
        passthrough += ["fiscalia", "agencia", "unidad_investigacion"]
    exprs += [pl.col(c) for c in passthrough]

    lf = lf.with_columns(exprs)

    # rezago de denuncia a nivel FECHA (dias enteros): fecha_inicio - fecha_hecho.
    # Se mide con las columnas Date, no con los timestamps: ~la mitad de los
    # registros trae fecha_hecho imputada = fecha_inicio, y comparar la hora en
    # esos casos genera falsos "hecho posterior al inicio". El detalle sub-diario
    # queda en dt_inicio / dt_hecho para quien lo necesite.
    lf = lf.with_columns(
        (pl.col("fecha_inicio") - pl.col("fecha_hecho")).dt.total_days().cast(pl.Int32).alias("rezago_denuncia_dias")
    )

    final_cols = list((S.VICTIMAS_FINAL if has_edad else S.CARPETAS_FINAL).keys())
    lf = lf.select(final_cols)

    out = INTERIM / f"{out_name}.parquet"
    INTERIM.mkdir(parents=True, exist_ok=True)
    log(f"    escribiendo {out} (sink_parquet, streaming)")
    lf.sink_parquet(out, compression="zstd", statistics=True)

    _report_parquet(out, date_cols=["fecha_inicio", "fecha_hecho"])


def _report_parquet(out: Path, date_cols: list[str]) -> None:
    df = pl.read_parquet(out)
    n = df.height
    log(f"    OK {out.name}: {n:,} filas x {df.width} columnas  sha256={sha256_file(out)}")
    # rango de fechas
    for c in date_cols:
        if c in df.columns:
            mn, mx = df[c].min(), df[c].max()
            log(f"      {c}: min={mn} max={mx}")
    # top nulos
    nulls = (df.null_count().transpose(include_header=True, column_names=["n_null"])
             .with_columns((pl.col("n_null") / n * 100).round(2).alias("pct"))
             .sort("n_null", descending=True).head(8))
    log(f"      nulos (top 8):\n{nulls}")


# --------------------------------------------------------------------------- #
# Censo 2020 RESAGEBURB (entidad 09)
# --------------------------------------------------------------------------- #
def normalize_censo() -> None:
    zpath = RAW / "censo2020" / "resageburb_09csv20.zip"
    if not zpath.exists():
        log(f"SKIP censo: no existe {zpath}")
        return
    log(f"--- normalize_censo: {zpath.name}")
    with zipfile.ZipFile(zpath) as z:
        members = z.namelist()
        log(f"    contenido del zip: {members}")
        csv_members = [m for m in members if m.lower().endswith(".csv")]
        if len(csv_members) != 1:
            raise SystemExit(f"ABORTO: esperaba 1 CSV en el zip del censo, hay {csv_members}")
        target = csv_members[0]
        extract_dir = RAW / "censo2020" / "_unzipped"
        extract_dir.mkdir(exist_ok=True)
        z.extract(target, extract_dir)
        csv_path = extract_dir / target

    # claves geoestadisticas como texto (con ceros a la izquierda); indicadores
    # como Utf8 en lectura porque traen '*' (confidencial) y 'N/D'.
    cols = pl.read_csv(csv_path, n_rows=0, infer_schema_length=0).columns
    key_cols = [c for c in cols if c.upper() in
                {"ENTIDAD", "NOM_ENT", "MUN", "NOM_MUN", "LOC", "NOM_LOC", "AGEB", "MZA"}]
    ind_cols = [c for c in cols if c not in key_cols]
    log(f"    {len(cols)} columnas; {len(key_cols)} de clave, {len(ind_cols)} indicadores")

    lf = pl.scan_csv(csv_path, schema_overrides={c: pl.Utf8 for c in cols},
                     infer_schema_length=0, encoding="utf8")

    # indicadores: '*' y 'N/D' -> null; el resto -> Int64
    ind_exprs = [
        pl.when(pl.col(c).str.strip_chars().is_in(["*", "N/D", "ND", ""]))
          .then(None).otherwise(pl.col(c).str.strip_chars())
          .cast(pl.Int64, strict=False).alias(c)
        for c in ind_cols
    ]
    lf = lf.with_columns(ind_exprs)

    # nivel de agregacion segun claves '0000'/'000'
    lf = lf.with_columns(
        pl.when((pl.col("MZA") != "000") & (pl.col("MZA").is_not_null()) & (pl.col("MZA") != "0"))
          .then(pl.lit("manzana"))
          .when((pl.col("AGEB") != "0000") & (pl.col("AGEB").is_not_null()))
          .then(pl.lit("ageb"))
          .when((pl.col("LOC") != "0000") & (pl.col("LOC").is_not_null()))
          .then(pl.lit("localidad"))
          .when((pl.col("MUN") != "000") & (pl.col("MUN").is_not_null()))
          .then(pl.lit("municipio"))
          .otherwise(pl.lit("entidad"))
          .alias("nivel")
    )
    # CVEGEO util para join con el shapefile
    lf = lf.with_columns(
        (pl.col("ENTIDAD") + pl.col("MUN") + pl.col("LOC") + pl.col("AGEB") + pl.col("MZA")).alias("cvegeo_full")
    )

    out = INTERIM / "censo2020_resageburb_09.parquet"
    lf.sink_parquet(out, compression="zstd", statistics=True)
    df = pl.read_parquet(out)
    log(f"    OK {out.name}: {df.height:,} filas x {df.width} col  sha256={sha256_file(out)}")
    log(f"      filas por nivel:\n{df['nivel'].value_counts().sort('nivel')}")


# --------------------------------------------------------------------------- #
# Geo: shapefiles -> (geo)parquet
# --------------------------------------------------------------------------- #
def normalize_geo() -> None:
    try:
        import geopandas as gpd
    except ImportError:
        log("SKIP geo: geopandas no disponible")
        return

    jobs = [
        ("geo/colonias_iecm_2022.zip", "geo_colonias_iecm_2022.parquet"),
        ("geo/poligono_ageb_urbanas_cdmx.zip", "geo_ageb_urbanas_cdmx.parquet"),
        ("geo/poligono_manzanas_cdmx.zip", "geo_manzanas_cdmx.parquet"),
    ]
    for rel, out_name in jobs:
        zpath = RAW / rel
        if not zpath.exists():
            log(f"SKIP geo: no existe {zpath}")
            continue
        log(f"--- normalize_geo: {zpath.name}")
        # extraer a data/raw/geo/_unzipped/<stem>/ y leer el .shp directamente
        # (mas robusto que zip:// cuando hay subcarpeta o archivos .qmd extra)
        exdir = zpath.parent / "_unzipped" / zpath.stem
        exdir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zpath) as z:
            z.extractall(exdir)
        shps = sorted(exdir.rglob("*.shp"))
        if len(shps) != 1:
            raise SystemExit(f"ABORTO: esperaba 1 .shp en {zpath.name}, encontrados: {shps}")
        gdf = gpd.read_file(shps[0])
        log(f"    {len(gdf):,} geometrias; CRS={gdf.crs}; columnas={list(gdf.columns)}")
        crs_orig = str(gdf.crs)
        gdf_wgs = gdf.to_crs(4326) if gdf.crs and gdf.crs.to_epsg() != 4326 else gdf
        out = INTERIM / out_name
        gdf_wgs.to_parquet(out)  # geoparquet
        log(f"    OK {out.name}: {len(gdf_wgs):,} filas  crs_original={crs_orig}  "
            f"sha256={sha256_file(out)}  bounds={list(gdf_wgs.total_bounds)}")


# --------------------------------------------------------------------------- #
def main() -> int:
    targets = sys.argv[1:] or ["fgj_carpetas", "fgj_victimas", "censo", "geo"]
    log(f"=== normalize: targets={targets}")

    if "fgj_carpetas" in targets:
        p = RAW / "fgj_carpetas" / "carpetasFGJ_acumulado_2025_01.csv"
        if p.exists():
            normalize_fgj(p, S.CARPETAS_READ_SCHEMA, "fgj_carpetas", has_edad=False)
        else:
            log(f"SKIP fgj_carpetas: no existe {p}")

    if "fgj_victimas" in targets:
        p = RAW / "fgj_victimas" / "victimasFGJ_acumulado_2024_09.csv"
        if p.exists():
            normalize_fgj(p, S.VICTIMAS_READ_SCHEMA, "fgj_victimas", has_edad=True)
        else:
            log(f"SKIP fgj_victimas: no existe {p}")

    if "censo" in targets:
        normalize_censo()

    if "geo" in targets:
        normalize_geo()

    log("=== normalize: fin")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
