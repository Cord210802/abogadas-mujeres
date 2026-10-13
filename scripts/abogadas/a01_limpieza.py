"""A01 - Limpieza: atenciones del programa, unidades de analisis y panel agencia-mes.

Entradas
  data/raw/abogadas/atenciones_abogadas_mujeres.csv   (portal CDMX, fuente 8)
  data/interim/fgj_carpetas.parquet                    (Fiscalia, fuente 1)

Salidas
  data/interim/abogadas/atenciones.parquet     una fila por atencion, tipada
  data/interim/abogadas/unidades.parquet       unidad de analisis <-> codigos FGJ, fecha de entrada
  data/interim/abogadas/panel.parquet          unidad x mes: carpetas por delito y atenciones
  data/interim/abogadas/fgj_tipo_agencia.parquet  violencia familiar por tipo de agencia (ciudad)
  grafs/abogadas/01_limpieza/                  figuras + resultados.json

Cada decision esta explicada en docs/abogadas/01_datos_y_limpieza.md.

Cambios por la auditoria (2026-09-21):
  - Regex de fiscalia territorial: excluye "EN AGENCIAS DE ATENCION ESPECIALIZADAS" y
    "DELITOS AMBIENTALES", que cabian en "^INVESTIGACION EN " (auditoria/01_datos.md m5).
    El panel no cambia (esos codigos no son territoriales); cambian el total de carpetas
    territoriales y la serie "Agencias territoriales" de fgj_tipo_agencia.parquet.
  - Columnas de conteo del panel en Int64 con signo: con UInt32 una resta da 4,294,967,282 (m8).
  - Validacion del empate: de las 34 celdas donde el programa registra mas carpetas de VF que
    la Fiscalia, cuantas se compensan con la holgura del mes vecino (16) y el desglose de las
    que no (IZP-7 y MC-1: codigos que la Fiscalia dejo de usar) (M1, m9).
  - hueco_no: la llave `no_fuera_del_hueco` sumaba NA; se agrega `na_fuera_del_hueco` (mismo
    valor) y `no_en_hueco` (7 NO en oct-2020), y los dos tramos del hueco (m1, m2).
  - Columna `mes_valido_conversion` en atenciones.parquet (= `mes_no_capturado`, que se
    conserva por compatibilidad; el nombre viejo se lee al reves) (m13).
  - Columna `fgj_sin_registro` en el panel: la Fiscalia no registra ninguna carpeta (de
    ningun delito) en esa unidad-mes. A02 la usa para marcar celdas faltantes (IZP-7).
  - Se guardan: atenciones con delito VF y SI (24,108) contra filas con delito VF (24,779)
    (m3); parte de la VF de la ciudad en territoriales ene-2017 a feb-2020 (59.3%) (m4,
    06_consistencia m2); codigos con carpetas (m6); copias en exceso de duplicados (m14).
  - 'UAT-CUJ-1' se traduce a CJ-1 en _comun.codigo_fgj (m7); solo toca el panel de 2021 en adelante.
"""
import datetime as dt
import hashlib
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comun as C  # noqa: E402
from _viz import BLUE, BLUE_DARK, BLUE_LIGHT, BLUE_PALE, RED, guardar, miles  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

CARPETA = "abogadas/01_limpieza"
NOTA_AB = "Fuente: SEMUJERES CDMX, Atenciones de las Abogadas de las Mujeres (datos.cdmx.gob.mx)."
NOTA_FGJ = "Fuente: FGJ CDMX, carpetas de investigacion (datos.cdmx.gob.mx), por fecha de inicio."

SI = {"SÍ", "SI", "Sí", "Si"}
NO = {"NO", "No"}
BOOL_COLS = ["representacion", "solicitud_medidas", "alto_riesgo", "riesgo_feminicida",
             "vio_psicoemocional", "vio_fisica", "vio_economica", "vio_patrimonial",
             "vio_sexual", "vio_simbolica", "vio_obstetrica", "vio_reproductivos",
             "vio_feminicida"]

PAREJA = {"CÓNYUGE", "NOVIO(A)", "EXPAREJA", "CONCUBINO(A)", "PAREJA", "ESPOSO(A)", "EX CONYUGE"}
FAMILIA = {"HERMANO(A)", "HIJO(A)", "PADRE", "TÍO(A)", "CUÑADO(A)", "SOBRINO(A)", "MADRE",
           "PRIMO(A)", "PADRASTRO", "YERNO", "ABUELO(A)", "SUEGRO(A)", "NIETO(A)", "NUERA",
           "CONCUÑO(A)", "MADRASTRA", "HERMANASTRO(A)", "PADRINO", "COMPADRE",
           "CONSUEGRO(A)", "AHIJADO(A)"}
CONOCIDO = {"AMIGA(O)", "VECINA(O)", "COMPAÑERO(A) DE TRABAJO", "JEFE(A)", "PROFESOR(A)",
            "COMPAÑERO(A) DE LA ESCUELA"}


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def a_bool(col):
    return (pl.when(pl.col(col).is_in(list(SI))).then(True)
            .when(pl.col(col).is_in(list(NO))).then(False)
            .otherwise(None).alias(col))


def tipo_sede(etq: str) -> str:
    if C.codigos_programa(etq):
        return "territorial"
    e = etq.upper()
    if e.startswith("FDS") or e in {"AGENCIA 75", "FIVF", "FEAM"}:
        return "especializada"
    if e == "NA":
        return "sin dato"
    return "otra"


# Fiscalias territoriales. "^INVESTIGACIÓN EN " tambien atrapaba "...EN AGENCIAS DE ATENCIÓN
# ESPECIALIZADAS" y "...EN DELITOS AMBIENTALES...", que no son territoriales (auditoria 01 m5).
ES_TERRITORIAL = (pl.col("fiscalia").str.contains("TERRITORIAL|^INVESTIGACIÓN EN ")
                  & ~pl.col("fiscalia").str.contains("ESPECIALIZADAS|AMBIENTALES"))


def tramos(meses):
    """Meses (date) -> lista de tramos contiguos [(desde, hasta)] en 'AAAA-MM'."""
    out = []
    for m in sorted(meses):
        i = m.year * 12 + m.month
        if out and i == out[-1][2] + 1:
            out[-1][1], out[-1][2] = m.isoformat()[:7], i
        else:
            out.append([m.isoformat()[:7], m.isoformat()[:7], i])
    return [{"desde": a, "hasta": b} for a, b, _ in out]


# ------------------------------------------------------------------ atenciones
def limpiar_atenciones(res):
    raw = pl.read_csv(C.RAW, infer_schema_length=0)
    res["crudo"] = {"filas": raw.height, "columnas": raw.width, "sha256": sha(C.RAW)}
    res["crudo"]["filas_identicas_repetidas"] = int(raw.is_duplicated().sum())
    # filas que pertenecen a un grupo repetido (3,245) contra copias en exceso (auditoria 01 m14)
    res["crudo"]["copias_en_exceso"] = int(raw.height - raw.unique().height)

    etiquetas = raw["agencia"].unique().to_list()
    res["etiquetas_programa"] = {"n": len(etiquetas),
                                 "territoriales": sum(bool(C.codigos_programa(e)) for e in etiquetas)}
    uf = C.Unir()
    for e in etiquetas:
        cods = C.codigos_programa(e)
        for c in cods:
            uf.unir(("cod", c), ("cod", cods[0]))
    # nombre de la unidad: la etiqueta mas frecuente del programa dentro del componente
    freq = Counter(raw["agencia"].to_list())
    comp_etq = defaultdict(list)
    for e in etiquetas:
        cods = C.codigos_programa(e)
        if cods:
            comp_etq[uf.raiz(("cod", cods[0]))].append(e)
    nombre_comp = {}
    for r, es in comp_etq.items():
        top = max(es, key=lambda x: freq[x])
        nombre_comp[r] = C.re.sub(r"\s+", " ", top.upper()).replace("CUJ 1", "CUJ-1").replace(" y ", " Y ")
    unidad_de = {}
    for e in etiquetas:
        cods = C.codigos_programa(e)
        unidad_de[e] = nombre_comp[uf.raiz(("cod", cods[0]))] if cods else None
    codigos_de_unidad = defaultdict(set)
    for e in etiquetas:
        for c in C.codigos_programa(e):
            codigos_de_unidad[unidad_de[e]].add(c)

    edad = pl.col("usuaria_edad").cast(pl.Int32, strict=False)
    a = raw.with_columns(
        pl.col("fecha").str.to_date("%Y-%m-%d").alias("mes"),
        pl.col("agencia").alias("agencia_original"),
        pl.col("agencia").map_elements(tipo_sede, return_dtype=pl.String).alias("tipo_sede"),
        pl.col("agencia").replace_strict(unidad_de, default=None, return_dtype=pl.String).alias("unidad"),
        pl.when(edad.is_between(0, 99)).then(edad).otherwise(None).alias("edad"),
        pl.when(pl.col("ci_iniciada") == "SÍ").then(pl.lit("SI"))
          .when(pl.col("ci_iniciada") == "NO").then(pl.lit("NO"))
          .otherwise(pl.lit("NA")).alias("ci_registro"),
        pl.when(pl.col("relacion_con_agresora").is_in(list(PAREJA))).then(pl.lit("pareja o expareja"))
          .when(pl.col("relacion_con_agresora").is_in(list(FAMILIA))).then(pl.lit("familiar"))
          .when(pl.col("relacion_con_agresora").is_in(list(CONOCIDO))).then(pl.lit("conocido"))
          .when(pl.col("relacion_con_agresora") == "OTRO").then(pl.lit("otro"))
          .otherwise(None).alias("relacion"),
        pl.when(pl.col("usuaria_estado_civil").is_in(["NA", "NO CONTESTA"])).then(None)
          .otherwise(pl.col("usuaria_estado_civil").str.replace("SOCIEDAD EN CONVIVENCIA", "SOCIEDAD DE CONVIVENCIA"))
          .alias("estado_civil"),
        pl.when(pl.col("violencia_modalidad") == "NA").then(None)
          .otherwise(pl.col("violencia_modalidad")).alias("modalidad"),
        pl.when(pl.col("delito") == "NA").then(None).otherwise(pl.col("delito")).alias("delito_carpeta"),
        *[a_bool(c) for c in BOOL_COLS],
    )
    res["edad_fuera_de_rango"] = int(a.filter(edad.is_not_null() & edad.is_between(0, 99).not_()).height)
    res["edad_sin_dato"] = int(a["edad"].null_count())

    # --- el hueco de codificacion de ci_iniciada: meses sin ningun "NO" ---
    por_mes = (a.group_by("mes").agg(pl.len().alias("atenciones"),
                                     (pl.col("ci_registro") == "SI").sum().alias("si"),
                                     (pl.col("ci_registro") == "NO").sum().alias("no"),
                                     (pl.col("ci_registro") == "NA").sum().alias("na"),
                                     pl.col("riesgo_feminicida").is_not_null().mean().alias("riesgo_capturado"),
                                     (pl.col("usuaria_ent_fed_nacimiento") == "COLIMA").mean().alias("colima"),
                                     pl.col("unidad").drop_nulls().n_unique().alias("unidades"))
               .sort("mes"))
    # Un mes "valido" para la conversion es uno donde el NO se capturo explicitamente.
    meses_validos = por_mes.filter(pl.col("no") > pl.col("na"))["mes"].to_list()
    a = a.with_columns(
        (pl.col("ci_registro") == "SI").cast(pl.Int8).alias("carpeta"),
        pl.col("mes").is_in(meses_validos).alias("mes_no_capturado"),
        pl.col("mes").is_in(meses_validos).alias("mes_valido_conversion"),
    )
    hueco = por_mes.filter(pl.col("no") <= pl.col("na"))
    res["hueco_no"] = {
        "meses": [m.isoformat()[:7] for m in hueco["mes"].to_list()],
        "n_meses": hueco.height,
        "atenciones_en_hueco": int(hueco["atenciones"].sum()),
        "na_en_hueco": int(hueco["na"].sum()),
        # llave vieja: en realidad suma NA fuera del hueco (se conserva por compatibilidad)
        "no_fuera_del_hueco": int(por_mes.filter(pl.col("no") > pl.col("na"))["na"].sum()),
        "na_fuera_del_hueco": int(por_mes.filter(pl.col("no") > pl.col("na"))["na"].sum()),
        "no_en_hueco": int(hueco["no"].sum()),
        "no_en_hueco_por_mes": {m.isoformat()[:7]: int(n) for m, n in zip(hueco["mes"], hueco["no"]) if n > 0},
        "tramos": tramos([m for m in hueco["mes"].to_list()]),
        "descripcion": "13 meses en dos tramos (jul-oct 2020 y dic 2020-ago 2021) donde el NO casi desaparece "
                       "y el no se registra como sin dato; noviembre de 2020 no es hueco y octubre de 2020 tiene 7 NO",
    }
    res["riesgo_primer_mes_capturado"] = por_mes.filter(pl.col("riesgo_capturado") > 0.5)["mes"].min().isoformat()[:7]
    res["colima"] = {
        "desde": por_mes.filter(pl.col("colima") > 0.5)["mes"].min().isoformat()[:7],
        "pct_desde": round(float(a.filter(pl.col("mes") >= dt.date(2021, 9, 1))
                                 .select((pl.col("usuaria_ent_fed_nacimiento") == "COLIMA").mean()).item()) * 100, 1),
        "pct_antes": round(float(a.filter(pl.col("mes") < dt.date(2021, 9, 1))
                                 .select((pl.col("usuaria_ent_fed_nacimiento") == "COLIMA").mean()).item()) * 100, 2),
    }
    h = a.select(pl.col("usuaria_hijas").cast(pl.Int32, strict=False).alias("hijas"),
                 pl.col("usuaria_hijos").cast(pl.Int32, strict=False).alias("hijos"),
                 pl.col("usuaria_hijes").cast(pl.Int32, strict=False).alias("hijes")).drop_nulls()
    res["hijos_inconsistentes"] = {
        "filas_con_los_tres": h.height,
        "pct_total_menor_que_hijas": round(float((h["hijos"] < h["hijas"]).mean()) * 100, 1),
        "pct_hijes_igual_hijas_mas_hijos": round(float((h["hijes"] == h["hijas"] + h["hijos"]).mean()) * 100, 1),
    }
    res["por_mes"] = por_mes.with_columns(pl.col("mes").dt.strftime("%Y-%m")).to_dicts()
    res["tipo_sede"] = dict(a["tipo_sede"].value_counts().rows())
    # atenciones con delito de violencia familiar: con carpeta SI contra cualquier registro (auditoria 01 m3)
    vf = pl.col("delito_carpeta") == "VIOLENCIA FAMILIAR"
    res["atenciones_por_delito"] = {
        "vf_con_carpeta_si": int(a.filter(vf & (pl.col("ci_registro") == "SI")).height),
        "vf_filas_con_delito": int(a.filter(vf).height),
        "sexuales_con_carpeta_si": int(a.filter((pl.col("delito_carpeta") == "DELITOS SEXUALES") & (pl.col("ci_registro") == "SI")).height),
        "sexuales_filas_con_delito": int(a.filter(pl.col("delito_carpeta") == "DELITOS SEXUALES").height),
        "filas_con_delito_sin_si": int(a.filter(pl.col("delito_carpeta").is_not_null() & (pl.col("ci_registro") != "SI")).height),
    }

    cols = ["mes", "agencia_original", "tipo_sede", "unidad", "edad", "estado_civil", "relacion",
            "modalidad", "ci_registro", "carpeta", "mes_no_capturado", "mes_valido_conversion",
            "delito_carpeta"] + BOOL_COLS
    at = a.select(cols)
    C.INTERIM.mkdir(parents=True, exist_ok=True)
    at.write_parquet(C.INTERIM / "atenciones.parquet")
    print(f"  atenciones.parquet: {at.height:,} filas")
    return at, codigos_de_unidad, por_mes


# ------------------------------------------------------------------ unidades
def construir_unidades(at, codigos_de_unidad, res):
    ent = (at.filter(pl.col("unidad").is_not_null())
           .group_by("unidad", "mes").agg(pl.len().alias("n"))
           .group_by("unidad").agg(
               pl.col("mes").min().alias("entrada"),
               pl.col("mes").filter(pl.col("n") >= 10).min().alias("entrada_10"),
               pl.col("n").sum().alias("atenciones"),
               pl.col("mes").n_unique().alias("meses_con_registro")))
    u = ent.with_columns(
        pl.col("unidad").replace_strict({k: sorted(v) for k, v in codigos_de_unidad.items()},
                                        return_dtype=pl.List(pl.String)).alias("codigos_fgj"),
        pl.col("unidad").map_elements(lambda s: C.ALCALDIA[C.codigos_programa(s)[0].split("-")[0]],
                                      return_dtype=pl.String).alias("alcaldia"),
    ).sort("entrada", "unidad")
    return u


# --------------------------------------------------------------------- panel
def construir_panel(u, at, res):
    cod2uni = {c: r["unidad"] for r in u.iter_rows(named=True) for c in r["codigos_fgj"]}
    f = (pl.scan_parquet(C.FGJ)
         .filter(pl.col("fecha_inicio").is_between(dt.date(2016, 1, 1), dt.date(2024, 12, 31)))
         .select("fecha_inicio", "delito", "fiscalia", "agencia", "latitud", "longitud")
         .with_columns(pl.col("fecha_inicio").dt.truncate("1mo").alias("mes"))
         .collect())

    # violencia familiar por tipo de agencia, toda la ciudad: por que el panel se corta en 2021
    tipo = (pl.when(pl.col("agencia").str.starts_with("UAT-")).then(pl.lit("Unidades de Atención Temprana"))
            .when(pl.col("agencia").str.starts_with("CJM")).then(pl.lit("Centros de Justicia para las Mujeres"))
            .when(pl.col("agencia").str.contains("^75")).then(pl.lit("Agencia 75 (violencia familiar)"))
            .when(ES_TERRITORIAL).then(pl.lit("Agencias territoriales"))
            .otherwise(pl.lit("Otras fiscalías")))
    vf_tipo = (f.filter(pl.col("delito") == "VIOLENCIA FAMILIAR").with_columns(tipo.alias("tipo"))
               .group_by("mes", "tipo").agg(pl.len().alias("n")).sort("mes", "tipo"))
    vf_tipo.write_parquet(C.INTERIM / "fgj_tipo_agencia.parquet")

    terr = f.filter(ES_TERRITORIAL)
    terr = terr.with_columns(pl.col("agencia").map_elements(C.codigo_fgj, return_dtype=pl.String).alias("codigo"))
    terr = terr.with_columns(pl.col("codigo").replace_strict(cod2uni, default=None, return_dtype=pl.String).alias("unidad"))

    ventana = terr.filter(pl.col("mes").is_between(C.PANEL_INI, C.PANEL_FIN))
    res["fgj_territorial_ventana"] = {
        "carpetas": ventana.height,
        "con_codigo_territorial": int(ventana["codigo"].is_not_null().sum()),
        "en_unidades_del_programa": int(ventana["unidad"].is_not_null().sum()),
        "vf": int((ventana["delito"] == "VIOLENCIA FAMILIAR").sum()),
        "vf_en_unidades": int(ventana.filter(pl.col("unidad").is_not_null())["delito"].eq("VIOLENCIA FAMILIAR").sum()),
        # de los 72 codigos nominales, cuantos tienen carpetas (auditoria 01 m6: GAM-7 nunca; AZ-3 una en 2016)
        "codigos_con_carpetas_en_ventana": int(ventana.filter(pl.col("unidad").is_not_null())["codigo"].n_unique()),
        "codigos_con_carpetas_2016_2024": int(terr.filter(pl.col("unidad").is_not_null())["codigo"].n_unique()),
        "codigos_sin_carpetas_nunca": sorted(set(cod2uni) - set(terr["codigo"].drop_nulls().unique().to_list())),
        # con el regex anterior (incluia dos fiscalias no territoriales): para comparar
        "carpetas_regex_anterior": int(f.filter(pl.col("fiscalia").str.contains("TERRITORIAL|^INVESTIGACIÓN EN ")
                                                & pl.col("mes").is_between(C.PANEL_INI, C.PANEL_FIN)).height),
    }
    # parte de la VF de la ciudad que se abre en agencias territoriales, ventana del analisis causal
    vt = vf_tipo.filter(pl.col("mes").is_between(C.PANEL_INI, C.PRE_COVID_FIN))
    vt_panel = vf_tipo.filter(pl.col("mes").is_between(C.PANEL_INI, C.PANEL_FIN))
    ter = pl.col("tipo") == "Agencias territoriales"
    res["vf_ciudad_en_territoriales"] = {
        "ene2017_feb2020": float(vt.filter(ter)["n"].sum() / vt["n"].sum()),
        "ene2017_ene2021": float(vt_panel.filter(ter)["n"].sum() / vt_panel["n"].sum()),
        "carpetas_territoriales_ene2017_feb2020": int(vt.filter(ter)["n"].sum()),
        "carpetas_ciudad_ene2017_feb2020": int(vt["n"].sum()),
    }
    sin_uni = (ventana.filter(pl.col("unidad").is_null())
               .group_by("agencia").agg(pl.len().alias("carpetas"),
                                        (pl.col("delito") == "VIOLENCIA FAMILIAR").sum().alias("vf"))
               .sort("carpetas", descending=True))
    res["agencias_fuera_de_unidades"] = sin_uni.head(25).to_dicts()

    es = pl.col("delito")
    panel_fgj = (terr.filter(pl.col("unidad").is_not_null())
                 .group_by("unidad", "mes").agg(
                     (es == "VIOLENCIA FAMILIAR").sum().alias("vf"),
                     es.is_in(list(C.DELITOS_SEXUALES)).sum().alias("sexuales"),
                     (es == "AMENAZAS").sum().alias("amenazas"),
                     es.str.starts_with(C.PREFIJO_PLACEBO).sum().alias("robos"),
                     pl.len().alias("total")))
    ubic = (terr.filter(pl.col("unidad").is_not_null() & pl.col("mes").is_between(dt.date(2017, 1, 1), dt.date(2019, 12, 1))
                        & pl.col("latitud").is_between(19.0, 19.65) & pl.col("longitud").is_between(-99.4, -98.9))
            .group_by("unidad").agg(pl.col("latitud").median().alias("lat"), pl.col("longitud").median().alias("lon")))

    prog = (at.filter(pl.col("unidad").is_not_null())
            .group_by("unidad", "mes").agg(
                pl.len().alias("atenciones"),
                pl.col("carpeta").sum().alias("carpetas_programa"),
                ((pl.col("carpeta") == 1) & (pl.col("delito_carpeta") == "VIOLENCIA FAMILIAR")).sum().alias("carpetas_programa_vf")))

    meses = pl.date_range(dt.date(2016, 1, 1), dt.date(2024, 12, 1), "1mo", eager=True)
    base = u.select("unidad").join(pl.DataFrame({"mes": meses}), how="cross")
    panel = (base.join(panel_fgj, on=["unidad", "mes"], how="left")
             .join(prog, on=["unidad", "mes"], how="left")
             .with_columns(pl.col(["vf", "sexuales", "amenazas", "robos", "total", "atenciones",
                                   "carpetas_programa", "carpetas_programa_vf"]).fill_null(0).cast(pl.Int64))
             # la Fiscalia no registra ninguna carpeta de ningun delito en la unidad ese mes:
             # el codigo no esta en uso (A02 lo marca como faltante despues de la entrada)
             .with_columns((pl.col("total") == 0).alias("fgj_sin_registro"))
             .join(u.select("unidad", "entrada", "entrada_10", "alcaldia"), on="unidad")
             .sort("unidad", "mes"))
    panel.write_parquet(C.INTERIM / "panel.parquet")
    u = u.join(ubic, on="unidad", how="left")
    u.write_parquet(C.INTERIM / "unidades.parquet")
    print(f"  panel.parquet: {panel.height:,} filas, {u.height} unidades")

    # --- validacion: el programa no puede abrir mas carpetas de VF que la agencia entera ---
    val = panel.filter(pl.col("mes").is_between(C.LANZAMIENTO, C.PANEL_FIN) & (pl.col("carpetas_programa_vf") > 0))
    res["validacion_vf"] = {
        "celdas_con_carpetas_del_programa": val.height,
        "celdas_programa_mayor_que_fiscalia": int((val["carpetas_programa_vf"] > val["vf"]).sum()),
        "carpetas_programa_vf": int(val["carpetas_programa_vf"].sum()),
        "vf_fiscalia_mismas_celdas": int(val["vf"].sum()),
    }
    res["validacion_vf"].update(compensacion_mes_vecino(panel))
    # --- estabilidad: unidades con meses sin ninguna carpeta dentro del panel ---
    est = (panel.filter(pl.col("mes").is_between(C.PANEL_INI, C.PANEL_FIN))
           .group_by("unidad").agg((pl.col("total") == 0).sum().alias("meses_cero"),
                                   pl.col("vf").sum().alias("vf"), pl.col("total").sum().alias("total")))
    res["unidades_con_meses_vacios"] = est.filter(pl.col("meses_cero") > 0).sort("meses_cero", descending=True).to_dicts()
    return panel, u, vf_tipo


def compensacion_mes_vecino(panel):
    """¿Las celdas donde el programa registra mas VF que la Fiscalia son desfases de fecha?

    Holgura h = vf - carpetas_programa_vf (en Int64: con UInt32 la resta se desborda).
    Una celda con exceso "se compensa" si la holgura del mes anterior o del siguiente de la
    misma unidad cubre el exceso (auditoria/01_datos.md M1). Las que no se compensan son
    codigos que la Fiscalia deja de usar mientras el programa sigue reportando la etiqueta.
    """
    p = (panel.filter(pl.col("mes").is_between(C.LANZAMIENTO, C.PANEL_FIN)).sort("unidad", "mes")
         .with_columns((pl.col("vf").cast(pl.Int64) - pl.col("carpetas_programa_vf").cast(pl.Int64)).alias("h"))
         .with_columns(pl.col("h").shift(1).over("unidad").fill_null(0).alias("h_ant"),
                       pl.col("h").shift(-1).over("unidad").fill_null(0).alias("h_sig")))
    val = p.filter(pl.col("carpetas_programa_vf") > 0)
    exc = val.filter(pl.col("h") < 0).with_columns(
        ((pl.col("h_ant") >= -pl.col("h")) | (pl.col("h_sig") >= -pl.col("h"))).alias("compensada"))
    cumplen = val.filter(pl.col("h") >= 0)
    no_comp = exc.filter(~pl.col("compensada"))
    desglose = (no_comp.group_by("unidad").agg(pl.len().alias("celdas"), pl.col("mes").min().dt.strftime("%Y-%m").alias("desde"),
                                               pl.col("mes").max().dt.strftime("%Y-%m").alias("hasta"),
                                               pl.col("vf").sum().alias("vf_fiscalia"),
                                               pl.col("carpetas_programa_vf").sum().alias("vf_programa"))
                .sort("celdas", descending=True))
    return {
        "compensadas_mes_vecino": int(exc["compensada"].sum()),
        "no_compensadas": int((~exc["compensada"]).sum()),
        "no_compensadas_por_unidad": desglose.to_dicts(),
        "no_compensadas_celdas": no_comp.select(pl.col("unidad"), pl.col("mes").dt.strftime("%Y-%m"), "vf",
                                                "carpetas_programa_vf").to_dicts(),
        "lectura_no_compensadas": "falla del empate en agencias que la Fiscalia deja de usar (IZP-7 desde sep-2019, "
                                  "MC-1 en jul-nov 2020): el programa sigue reportando la etiqueta vieja",
        "celdas_que_cumplen": cumplen.height,
        "cumplen_carpetas_programa_vf": int(cumplen["carpetas_programa_vf"].sum()),
        "cumplen_vf_fiscalia": int(cumplen["vf"].sum()),
    }


# ------------------------------------------------------------------ figuras
def figuras(por_mes, u, vf_tipo, res):
    pm = por_mes.with_columns(pl.col("mes").dt.strftime("%Y-%m").alias("m"))
    x = np.arange(pm.height)
    fig, ax = plt.subplots(figsize=(11, 4.6))
    ax.bar(x, pm["si"], color=BLUE_DARK, label="Se abrió carpeta (SÍ)")
    ax.bar(x, pm["no"], bottom=pm["si"], color=BLUE_LIGHT, label="No se abrió (NO)")
    ax.bar(x, pm["na"], bottom=pm["si"] + pm["no"], color=RED, label="Sin dato (NA)")
    ax.set_xticks(x[::3]); ax.set_xticklabels(pm["m"][::3], rotation=45, ha="right")
    ax.set_ylabel("Atenciones por mes"); miles(ax)
    ax.set_title("Durante 13 meses el 'NO' desaparece de la base y se registra como 'sin dato'", fontweight="bold")
    ax.legend(loc="upper left", bbox_to_anchor=(1, 1), framealpha=0.8)
    ax.set_ylim(0, pm["atenciones"].max() * 1.1)
    guardar(fig, CARPETA, "01_hueco_codificacion", NOTA_AB)

    fig, ax = plt.subplots(figsize=(11, 4.2))
    ax.plot(x, pm["unidades"], color=BLUE, lw=2, marker="o", ms=3.5)
    i = pm["m"].to_list().index("2020-04")
    ax.axvspan(i - 0.5, pm["m"].to_list().index("2020-12") + 0.5, color=RED, alpha=.12)
    ax.text(i + 0.3, pm["unidades"].max() * 0.95, "Pandemia: el programa\nregistra atenciones en\nmenos de la mitad de las agencias",
            color=RED, fontsize=9, va="top")
    ax.set_xticks(x[::3]); ax.set_xticklabels(pm["m"][::3], rotation=45, ha="right")
    ax.set_ylabel("Agencias territoriales con atenciones"); ax.set_ylim(0, pm["unidades"].max() * 1.15)
    ax.set_title("El despliegue tardó cinco meses; en abril de 2020 el programa se replegó", fontweight="bold")
    guardar(fig, CARPETA, "02_agencias_con_registro", NOTA_AB)

    p = vf_tipo.filter(pl.col("mes") < dt.date(2024, 1, 1)).pivot(on="tipo", index="mes", values="n").sort("mes").fill_null(0)
    fig, ax = plt.subplots(figsize=(11, 4.6))
    colores = {"Agencias territoriales": BLUE, "Unidades de Atención Temprana": RED,
               "Agencia 75 (violencia familiar)": BLUE_LIGHT, "Centros de Justicia para las Mujeres": BLUE_PALE,
               "Otras fiscalías": "#999999"}
    for k, c in colores.items():
        if k in p.columns:
            ax.plot(p["mes"], p[k], color=c, lw=2 if k in ("Agencias territoriales", "Unidades de Atención Temprana") else 1.3, label=k)
    ax.axvline(C.PANEL_FIN, color="#000", ls="--", lw=1)
    ax.text(C.PANEL_FIN, ax.get_ylim()[1] * 0.97, "  fin del panel", fontsize=9, va="top")
    ax.set_ylabel("Carpetas de violencia familiar por mes"); miles(ax)
    ax.set_title("En 2021 la violencia familiar se muda a otras unidades: el panel se corta antes", fontweight="bold")
    ax.legend(loc="upper left", bbox_to_anchor=(1, 1), framealpha=0.8)
    guardar(fig, CARPETA, "03_violencia_familiar_por_tipo_de_agencia", NOTA_FGJ)


def main():
    res = {}
    print("A01 limpieza")
    at, cods, por_mes = limpiar_atenciones(res)
    u = construir_unidades(at, cods, res)
    panel, u, vf_tipo = construir_panel(u, at, res)
    cohortes = u.group_by("entrada").agg(pl.len().alias("unidades")).sort("entrada")
    res["unidades"] = {
        "n": u.height,
        "codigos_fgj": int(u["codigos_fgj"].list.len().sum()),
        "cohortes": [{"mes": r["entrada"].isoformat()[:7], "unidades": r["unidades"]} for r in cohortes.iter_rows(named=True)],
        "entrada_distinta_con_umbral_10": int((u["entrada"] != u["entrada_10"]).sum()),
        "tabla": u.with_columns(pl.col("entrada").dt.strftime("%Y-%m"), pl.col("entrada_10").dt.strftime("%Y-%m")).to_dicts(),
    }
    figuras(por_mes, u, vf_tipo, res)
    C.guardar_json(res, CARPETA)


if __name__ == "__main__":
    main()
