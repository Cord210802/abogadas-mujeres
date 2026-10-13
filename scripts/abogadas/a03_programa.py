"""A03 - Dentro del programa: quien sale con carpeta y por que la conversion "subio".

La cifra que el gobierno puede mostrar sin evaluacion es la conversion: de cada
100 mujeres atendidas, cuantas salen con carpeta. En la base pasa de 24% (2019) a
mas de 50% (2022). Aqui se revisa que hay detras:

  1. LA CUENTA. Conversion = carpetas / atenciones. Si sube, puede ser porque suben
     las carpetas o porque bajan las atenciones. Se separan las dos cosas.
  2. EL MODELO. Que caracteristicas del caso se asocian con salir con carpeta, y si
     el modelo aprendido en 2019-2020 sigue sirviendo en 2021-2022.
  3. LA AGENCIA. Si la misma politica convierte distinto segun la agencia
     (grafica de embudo con limites binomiales).
  4. EL RIESGO. Cuantas mujeres con riesgo feminicida salen sin carpeta.

Regla de datos: la conversion y el modelo solo usan meses donde el "NO" se
capturo explicitamente (A01). En los 13 meses del hueco se reporta aparte, bajo el
supuesto declarado de que "sin dato" significa "no".

Cambios por la auditoria (2026-09-21):
  - Embudo con limites ajustados por sobredispersion (Spiegelhalter 2005): multiplicativo
    (phi winsorizado al 10%) y aditivo (tau^2 por momentos con I * phi winsorizado, no con la
    suma de z^2 crudos); se guardan las unidades fuera de cada version. Los limites binomiales
    quedan solo como diagnostico (auditoria/03_programa.md M1, M2).
  - Modelo del caso SIN tipo_sede como especificacion principal (tipo de sede es un atributo de
    la agencia); el modelo con tipo_sede se conserva en `modelo_con_tipo_sede` (03 m2, m3;
    06_consistencia C3).
  - Variables categoricas con categoria de referencia (la mas frecuente) para las razones de
    momios, estimadas sin penalizacion (03 m1).
  - AUC dentro de agencia; calibracion fuera de tiempo (media predicha contra observada,
    calibracion en el promedio, pendiente); correlacion de coeficientes entre periodos y parte
    del salto de conversion que ya predice el perfil del caso (03 M4).
  - Riesgo feminicida: intervalo agrupado por agencia (efecto de diseño, bootstrap por
    agencia, agencia-mes), diferencia dentro de agencia (Mantel-Haenszel) y heterogeneidad entre
    agencias en los casos con riesgo (03 M3, m5, m6).
  - Descomposicion de la conversion con otras bases: despliegue completo (jun-2019 a mar-2020),
    otras ventanas y por unidad territorial-mes; reparto de Shapley en niveles (03 M5).
  - Atenciones sin ningun tipo de violencia ni modalidad anotada, por año (03 m9).
  - Unidades y etiquetas normalizadas con registro por mes (03 m8).
  - El periodo "hueco del NO" se renombra: jul-2020 a ago-2021 son 14 meses e incluyen
    noviembre de 2020, que no es hueco (06_consistencia M6).
  - Usa `mes_valido_conversion` (antes `mes_no_capturado`, que se leia al reves) (01 m13).

Salidas: grafs/abogadas/03_programa/
"""
import sys
from pathlib import Path

import numpy as np
import polars as pl
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comun as C  # noqa: E402
from _viz import BLUE, BLUE_DARK, BLUE_LIGHT, BLUE_PALE, RED, guardar, miles, pct  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

CARPETA = "abogadas/03_programa"
NOTA = "Fuente: SEMUJERES CDMX, Atenciones de las Abogadas de las Mujeres, mar-2019 a mar-2022."
VIO = ["vio_psicoemocional", "vio_fisica", "vio_economica", "vio_patrimonial", "vio_sexual",
       "vio_simbolica", "vio_obstetrica", "vio_reproductivos", "vio_feminicida"]

PERIODOS = [
    ("Mar-dic 2019", "2019-03", "2019-12"),
    ("Ene-mar 2020", "2020-01", "2020-03"),
    ("Abr-jun 2020 (pandemia)", "2020-04", "2020-06"),
    ("Jul 2020-ago 2021 (incluye los 13 meses del hueco del NO)", "2020-07", "2021-08"),
    ("Sep 2021-mar 2022", "2021-09", "2022-03"),
]


def cuenta(a, res):
    m = a.with_columns(pl.col("mes").dt.strftime("%Y-%m").alias("m"))
    out = []
    for nombre, i, f in PERIODOS:
        x = m.filter(pl.col("m").is_between(pl.lit(i), pl.lit(f)))
        meses = x["m"].n_unique()
        out.append({"periodo": nombre, "meses": meses,
                    "atenciones_mes": x.height / meses, "carpetas_mes": float(x["carpeta"].sum()) / meses,
                    "conversion": float(x["carpeta"].mean()),
                    "agencias_mes": x.group_by("m").agg(pl.col("agencia_original").n_unique())["agencia_original"].mean(),
                    # la columna anterior cuenta etiquetas con variantes de mayusculas (auditoria 03 m8)
                    "etiquetas_normalizadas_mes": x.group_by("m").agg(pl.col("agencia_original").str.to_uppercase().n_unique())["agencia_original"].mean(),
                    "unidades_territoriales_mes": x.group_by("m").agg(pl.col("unidad").drop_nulls().n_unique())["unidad"].mean()})
    res["periodos"] = out
    base, fin = out[0], out[-1]
    # Descomposicion exacta del cambio de conversion (log): carpetas contra atenciones
    dlog_conv = np.log(fin["conversion"] / base["conversion"])
    dlog_carp = np.log(fin["carpetas_mes"] / base["carpetas_mes"])
    dlog_aten = np.log(fin["atenciones_mes"] / base["atenciones_mes"])
    res["descomposicion"] = {
        "conversion_inicio": base["conversion"], "conversion_fin": fin["conversion"],
        "cambio_carpetas_pct": (fin["carpetas_mes"] / base["carpetas_mes"] - 1) * 100,
        "cambio_atenciones_pct": (fin["atenciones_mes"] / base["atenciones_mes"] - 1) * 100,
        "parte_por_menos_atenciones_pct": float(-dlog_aten / dlog_conv * 100),
        "parte_por_mas_carpetas_pct": float(dlog_carp / dlog_conv * 100),
    }
    res["descomposicion_bases"] = bases(m, fin)
    serie = (m.group_by("m").agg(pl.len().alias("atenciones"), pl.col("carpeta").sum().alias("carpetas"),
                                 (pl.col("ci_registro") == "NO").sum().alias("no"),
                                 (pl.col("ci_registro") == "NA").sum().alias("na"),
                                 pl.col("mes_valido_conversion").first().alias("valido"))
             .sort("m"))
    res["serie"] = serie.to_dicts()
    return serie


def bases(m, fin):
    """La descomposicion con otras bases (auditoria 03 M5).

    La base mar-dic 2019 incluye el arranque (21, 36 y 48 unidades en marzo, abril y mayo),
    que baja las carpetas por mes de la base. Se repite con otras ventanas y por unidad
    territorial-mes. Tambien el reparto de Shapley en niveles (promedio de los dos ordenes).
    """
    def per(i, f, df):
        x = df.filter(pl.col("m").is_between(pl.lit(i), pl.lit(f)))
        k = x["m"].n_unique()
        return x.height / k, float(x["carpeta"].sum()) / k, float(x["carpeta"].mean())

    A1, C1, p1 = fin["atenciones_mes"], fin["carpetas_mes"], fin["conversion"]
    out = []
    for nombre, i, f in (("Mar-dic 2019 (base del estudio)", "2019-03", "2019-12"),
                         ("Mar-2019 a mar-2020", "2019-03", "2020-03"), ("Ene-mar 2020", "2020-01", "2020-03"),
                         ("Jun-2019 a mar-2020 (despliegue completo)", "2019-06", "2020-03"), ("Jun-dic 2019", "2019-06", "2019-12")):
        A0, C0, p0 = per(i, f, m)
        L = np.log(p1 / p0)
        c_only, a_only = C1 / A0, C0 / A1
        shap_c = 0.5 * ((c_only - p0) + (p1 - a_only)) / (p1 - p0)
        out.append({"base": nombre, "desde": i, "hasta": f, "conversion_base": p0,
                    "cambio_carpetas_pct": (C1 / C0 - 1) * 100, "cambio_atenciones_pct": (A1 / A0 - 1) * 100,
                    "parte_por_menos_atenciones_pct": float(-np.log(A1 / A0) / L * 100),
                    "parte_por_menos_atenciones_shapley_niveles_pct": float((1 - shap_c) * 100)})
    t = m.filter(pl.col("unidad").is_not_null())

    def por_unidad(i, f):
        x = t.filter(pl.col("m").is_between(pl.lit(i), pl.lit(f)))
        um = x.group_by("m").agg(pl.col("unidad").n_unique())["unidad"].sum()
        return x.height / um, float(x["carpeta"].sum()) / um, float(x["carpeta"].mean())
    A0, C0, p0 = por_unidad("2019-03", "2019-12")
    A1u, C1u, p1u = por_unidad("2021-09", "2022-03")
    out.append({"base": "Por unidad territorial-mes (mar-dic 2019 contra sep-2021 a mar-2022)", "desde": "2019-03", "hasta": "2019-12",
                "conversion_base": p0, "conversion_fin": p1u,
                "cambio_carpetas_pct": (C1u / C0 - 1) * 100, "cambio_atenciones_pct": (A1u / A0 - 1) * 100,
                "parte_por_menos_atenciones_pct": float(-np.log(A1u / A0) / np.log(p1u / p0) * 100),
                "atenciones_por_unidad_mes": [A0, A1u], "carpetas_por_unidad_mes": [C0, C1u]})
    return out


def registro_vacio(a, res):
    """Atenciones sin ningun tipo de violencia ni modalidad anotada, por año (auditoria 03 m9)."""
    vac = pl.sum_horizontal([pl.col(c).fill_null(False).cast(pl.Int8) for c in VIO]) == 0
    x = a.filter(pl.col("mes_valido_conversion")).with_columns(vac.alias("sin_violencia"),
                                                               pl.col("modalidad").is_null().alias("sin_modalidad"))
    por = (x.group_by(pl.col("mes").dt.year().alias("anio"))
           .agg(pl.len().alias("atenciones"), pl.col("sin_violencia").mean().alias("pct_sin_tipo_de_violencia"),
                pl.col("sin_modalidad").mean().alias("pct_sin_modalidad"),
                pl.col("carpeta").filter(pl.col("sin_violencia")).mean().alias("conversion_sin_tipo"),
                pl.col("carpeta").filter(~pl.col("sin_violencia")).mean().alias("conversion_con_tipo"))
           .sort("anio"))
    b = x.filter(pl.col("mes").is_between(pl.date(2019, 3, 1), pl.date(2019, 12, 1)))
    f = x.filter(pl.col("mes") >= pl.date(2021, 9, 1))
    mb, mf = b["mes"].n_unique(), f["mes"].n_unique()
    res["registro_vacio"] = {
        "por_anio": por.to_dicts(),
        "vacias_por_mes_base": float(b["sin_violencia"].sum()) / mb, "vacias_por_mes_fin": float(f["sin_violencia"].sum()) / mf,
        "atenciones_que_desaparecen_por_mes": b.height / mb - f.height / mf,
        "conversion_sin_vacias_base": float(b.filter(~pl.col("sin_violencia"))["carpeta"].mean()),
        "conversion_sin_vacias_fin": float(f.filter(~pl.col("sin_violencia"))["carpeta"].mean()),
    }


def matriz(df, cat_cols, num_cols, niveles=None):
    niveles = niveles or {c: sorted(df[c].drop_nulls().unique().to_list()) for c in cat_cols}
    cols, nombres = [], []
    for c in cat_cols:
        v = df[c].to_list()
        for lvl in niveles[c]:
            cols.append(np.array([x == lvl for x in v], float)); nombres.append(f"{c}={lvl}")
        cols.append(np.array([x is None for x in v], float)); nombres.append(f"{c}=sin dato")
    for c in num_cols:
        v = df[c].cast(pl.Float64).fill_null(-1).to_numpy()
        cols.append(v); nombres.append(c)
    return np.column_stack(cols), nombres, niveles


def matriz_ref(df, cat_cols, num_cols, niveles=None, referencia=None):
    """Como matriz(), pero sin la categoria de referencia (la mas frecuente en entrenamiento),
    para que las razones de momios sean contrastes contra ella (auditoria 03 m1)."""
    niveles = niveles or {c: sorted(df[c].drop_nulls().unique().to_list()) for c in cat_cols}
    referencia = referencia or {c: df[c].drop_nulls().mode().sort()[0] for c in cat_cols}
    cols, nombres = [], []
    for c in cat_cols:
        v = df[c].to_list()
        for lvl in niveles[c]:
            if lvl == referencia[c]:
                continue
            cols.append(np.array([x == lvl for x in v], float)); nombres.append(f"{c}={lvl}")
        cols.append(np.array([x is None for x in v], float)); nombres.append(f"{c}=sin dato")
    for c in num_cols:
        cols.append(df[c].cast(pl.Float64).fill_null(-1).to_numpy()); nombres.append(c)
    return np.column_stack(cols), nombres, niveles, referencia


def modelo(a, res):
    from scipy.special import logit
    a = a.with_columns(
        pl.when(pl.col("edad") < 18).then(pl.lit("menor de 18")).when(pl.col("edad") < 30).then(pl.lit("18-29"))
          .when(pl.col("edad") < 45).then(pl.lit("30-44")).when(pl.col("edad").is_not_null()).then(pl.lit("45 o más"))
          .otherwise(None).alias("edad_g"),
        *[pl.col(c).cast(pl.Int8).alias(c) for c in VIO])
    val = a.filter(pl.col("mes_valido_conversion"))
    ent = val.filter(pl.col("mes") < pl.date(2021, 1, 1))
    pru = val.filter(pl.col("mes") >= pl.date(2021, 9, 1))
    ye, yp = ent["carpeta"].to_numpy(), pru["carpeta"].to_numpy()
    grupos = ent["agencia_original"].to_numpy()
    meses_e = ent["mes"].dt.strftime("%Y-%m").to_numpy()

    def cv(X, y, g, clf):
        s = np.zeros(len(y))
        for tr, te in GroupKFold(n_splits=5).split(X, y, g):
            clf.fit(X[tr], y[tr]); s[te] = clf.predict_proba(X[te])[:, 1]
        return roc_auc_score(y, s), s

    Xa, _, _ = matriz(ent, ["agencia_original"], [])
    auc_solo_agencia = cv(Xa, ye, meses_e, LogisticRegression(max_iter=2000))[0]

    def ajustar(caso):
        Xe, nombres, niv = matriz(ent, caso, VIO)
        Xp, _, _ = matriz(pru, caso, VIO, niv)
        auc = {}
        lr = LogisticRegression(max_iter=2000, C=1.0)
        auc["logistica_caso_cv_por_agencia"], s_ag = cv(Xe, ye, grupos, lr)
        gb = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08, random_state=0)
        auc["boosting_caso_cv_por_agencia"] = cv(Xe, ye, grupos, gb)[0]
        lr.fit(Xe, ye)
        pp = lr.predict_proba(Xp)[:, 1]
        auc["logistica_caso_fuera_de_tiempo"] = roc_auc_score(yp, pp)
        gb.fit(Xe, ye)
        auc["boosting_caso_fuera_de_tiempo"] = roc_auc_score(yp, gb.predict_proba(Xp)[:, 1])
        auc["solo_agencia_cv_por_mes"] = auc_solo_agencia
        auc["caso_cv_por_mes"] = cv(Xe, ye, meses_e, LogisticRegression(max_iter=2000))[0]
        auc["agencia_y_caso_cv_por_mes"] = cv(np.column_stack([Xe, Xa]), ye, meses_e, LogisticRegression(max_iter=2000))[0]
        # AUC dentro de cada agencia, con las predicciones fuera de muestra por agencia (auditoria 03 m3)
        aucs, w = [], []
        for g in np.unique(grupos):
            i = grupos == g
            if i.sum() >= 100 and ye[i].min() != ye[i].max():
                aucs.append(roc_auc_score(ye[i], s_ag[i])); w.append(i.sum())
        terr = ent["tipo_sede"].to_numpy() == "territorial"
        dentro = {"ponderado": float(np.average(aucs, weights=w)), "mediana": float(np.median(aucs)), "agencias": len(aucs),
                  "solo_territoriales_cv_por_agencia": float(roc_auc_score(ye[terr], s_ag[terr]))}
        # calibracion fuera de tiempo (auditoria 03 M4)
        cal = LogisticRegression(C=1e8, max_iter=5000).fit(logit(pp).reshape(-1, 1), yp)
        lo, b = logit(pp), 0.0
        for _ in range(50):
            q = 1 / (1 + np.exp(-(lo + b))); b += (yp - q).sum() / (q * (1 - q)).sum()
        calib = {"predicho_medio": float(pp.mean()), "observado": float(yp.mean()), "entrenamiento": float(ye.mean()),
                 "calibracion_en_el_promedio_logit": float(b), "pendiente": float(cal.coef_[0][0]),
                 "parte_del_salto_que_predice_el_perfil": float((pp.mean() - ye.mean()) / (yp.mean() - ye.mean()))}
        # razones de momios con categoria de referencia, sin penalizar, y estabilidad entre periodos
        Xr, nr, nivr, ref = matriz_ref(ent, caso, VIO)
        Xrp, _, _, _ = matriz_ref(pru, caso, VIO, nivr, ref)
        b1 = LogisticRegression(C=1e6, max_iter=5000).fit(Xr, ye)
        b2 = LogisticRegression(C=1e6, max_iter=5000).fit(Xrp, yp)
        rms = sorted(zip(nr, b1.coef_[0], b2.coef_[0]), key=lambda t: -abs(t[1]))
        return {"auc": auc, "auc_dentro_de_agencia": dentro, "calibracion_fuera_de_tiempo": calib,
                "referencia": ref,
                "razones_de_momios": [{"variable": n, "rm": float(np.exp(c1)), "rm_2021_22": float(np.exp(c2))}
                                      for n, c1, c2 in rms if "sin dato" not in n][:16],
                "correlacion_coeficientes_entre_periodos": float(np.corrcoef(b1.coef_[0], b2.coef_[0])[0, 1]),
                "variables": caso}

    principal = ajustar(["modalidad", "relacion", "edad_g", "estado_civil"])
    con_sede = ajustar(["modalidad", "relacion", "edad_g", "estado_civil", "tipo_sede"])
    res["modelo"] = {**principal, "n_entrenamiento": len(ye), "n_prueba": len(yp),
                     "conversion_entrenamiento": float(ye.mean()), "conversion_prueba": float(yp.mean()),
                     "nota": "modelo del caso sin tipo de sede (atributo de la agencia); la version con sede esta en modelo_con_tipo_sede"}
    res["modelo_con_tipo_sede"] = con_sede
    # completitud del registro sola: descarta fuga de informacion por datos faltantes
    def comp(df):
        return np.column_stack([df[c].is_null().to_numpy() for c in ["modalidad", "relacion", "estado_civil", "edad"]] +
                               [(df.select(pl.sum_horizontal([pl.col(c) for c in VIO])) == 0).to_numpy().ravel()]).astype(float)
    res["modelo"]["auc_solo_completitud_cv_por_agencia"] = cv(comp(ent), ye, grupos, LogisticRegression(max_iter=2000))[0]
    for k, v in principal["auc"].items():
        print(f"  AUC {k}: {v:.3f}  (con tipo_sede {con_sede['auc'][k]:.3f})")
    print("  calibracion:", {k: round(v, 3) for k, v in principal["calibracion_fuera_de_tiempo"].items()},
          " AUC dentro de agencia", round(principal["auc_dentro_de_agencia"]["ponderado"], 3))


def embudo(a, res):
    """Conversion por unidad contra su tamaño, con limites que toman en cuenta la sobredispersion.

    Spiegelhalter (2005, Stat Med 24:1185): con phi >> 1 los limites binomiales marcan casi a
    todos. Se estiman phi con z winsorizados al 10% (percentiles 10 y 90) y dos ajustes:
      multiplicativo  p0 +- z * sqrt(phi_w) * se_i
      aditivo         p0 +- z * sqrt(se_i^2 + tau^2),  tau^2 = (I phi_w - (I-1)) / (sum w - sum w^2 / sum w)
    Los limites binomiales se guardan como diagnostico (fuera_95, fuera_998).
    """
    from scipy.stats import norm
    x = (a.filter(pl.col("mes_valido_conversion") & pl.col("unidad").is_not_null()
                  & pl.col("mes").is_between(pl.date(2019, 3, 1), pl.date(2020, 3, 1)))
         .group_by("unidad").agg(pl.len().alias("n"), pl.col("carpeta").mean().alias("conv")))
    n_todas = x.height
    x = x.filter(pl.col("n") >= 100).sort("conv")
    p0 = float((x["conv"] * x["n"]).sum() / x["n"].sum())
    n = x["n"].to_numpy().astype(float)
    se = np.sqrt(p0 * (1 - p0) / n)
    conv = x["conv"].to_numpy()
    z = (conv - p0) / se
    I = len(conv)
    z998 = float(norm.ppf(0.999))
    fuera95 = int((np.abs(z) > 1.96).sum())
    fuera998 = int((np.abs(z) > z998).sum())
    phi = float((z ** 2).sum() / (I - 1))
    lo, hi = np.percentile(z, [10, 90])
    phi_w = float((np.clip(z, lo, hi) ** 2).mean())
    w = 1 / se ** 2
    tau2 = max(0.0, (I * phi_w - (I - 1)) / (w.sum() - (w ** 2).sum() / w.sum()))
    tau2_crudo = max(0.0, ((z ** 2).sum() - (I - 1)) / (w.sum() - (w ** 2).sum() / w.sum()))
    sa = np.sqrt(se ** 2 + tau2)
    u = x["unidad"].to_list()
    lista = lambda m: [u[i] for i in np.where(m)[0]]  # noqa: E731
    mult95, mult998 = np.abs(z) > 1.96 * np.sqrt(phi_w), np.abs(z) > z998 * np.sqrt(phi_w)
    add95, add998 = np.abs(conv - p0) > 1.96 * sa, np.abs(conv - p0) > z998 * sa
    tabla = x.with_columns(pl.Series("z", z), pl.Series("fuera_998_binomial", np.abs(z) > z998),
                           pl.Series("fuera_95_aditivo", add95), pl.Series("fuera_998_aditivo", add998),
                           pl.Series("fuera_95_multiplicativo", mult95), pl.Series("fuera_998_multiplicativo", mult998))
    res["embudo"] = {"p0": p0, "unidades": I, "unidades_con_atenciones": n_todas,
                     "fuera_95": fuera95, "fuera_998": fuera998, "z_998": z998,
                     "limites_binomiales": "solo diagnostico: con esta sobredispersion no sirven para señalar agencias",
                     "sobredispersion": phi, "sobredispersion_winsorizada": phi_w,
                     "multiplicativo": {"phi": phi_w, "fuera_95": int(mult95.sum()), "fuera_998": int(mult998.sum()),
                                        "unidades_fuera_95": lista(mult95), "unidades_fuera_998": lista(mult998)},
                     "aditivo": {"tau": float(np.sqrt(tau2)), "tau2": tau2, "fuera_95": int(add95.sum()), "fuera_998": int(add998.sum()),
                                 "unidades_fuera_95": lista(add95), "unidades_fuera_998": lista(add998),
                                 "tau_con_z_crudos": float(np.sqrt(tau2_crudo)),
                                 "nota": "tau es una desviacion estandar entre unidades (en proporcion); tau_con_z_crudos es la "
                                         "formula anterior del reporte, que mezclaba z sin winsorizar"},
                     "p10": float(np.percentile(conv, 10)), "p90": float(np.percentile(conv, 90)),
                     "min": float(conv.min()), "max": float(conv.max()),
                     "tabla": tabla.to_dicts()}
    print(f"  embudo: p0={p0:.3f}, phi={phi:.1f}, phi_w={phi_w:.1f}; binomial fuera 99.8% {fuera998}/{I}; "
          f"multiplicativo {int(mult95.sum())}/{int(mult998.sum())}; aditivo tau={np.sqrt(tau2)*100:.2f} pp {int(add95.sum())}/{int(add998.sum())} "
          f"{lista(add998)}")
    return x, p0, phi_w, tau2


def riesgo(a, res):
    r = a.filter(pl.col("riesgo_feminicida").is_not_null())
    out = {}
    for nombre, filtro in (("meses con NO capturado", pl.col("mes_valido_conversion")),
                           ("todos, suponiendo sin dato = no", pl.lit(True))):
        x = r.filter(filtro)
        rf = x.filter(pl.col("riesgo_feminicida"))
        ar = x.filter(pl.col("alto_riesgo") == True)  # noqa: E712
        out[nombre] = {"con_dato_de_riesgo": x.height, "riesgo_feminicida": rf.height,
                       "pct_riesgo": rf.height / x.height * 100,
                       "riesgo_sin_carpeta_pct": float(1 - rf["carpeta"].mean()) * 100,
                       "sin_riesgo_sin_carpeta_pct": float(1 - x.filter(~pl.col("riesgo_feminicida"))["carpeta"].mean()) * 100,
                       "alto_riesgo": ar.height, "alto_riesgo_sin_carpeta_pct": float(1 - ar["carpeta"].mean()) * 100}
    por_anio = (r.filter(pl.col("mes_valido_conversion") & pl.col("riesgo_feminicida"))
                .group_by(pl.col("mes").dt.year().alias("anio")).agg(pl.len().alias("n"), (1 - pl.col("carpeta").mean()).alias("sin_carpeta"))
                .sort("anio"))
    out["por_anio_meses_validos"] = por_anio.to_dicts()

    # --- intervalo que respeta la agrupacion por agencia (auditoria 03 M3) ---
    x = r.filter(pl.col("mes_valido_conversion"))
    rf = x.filter(pl.col("riesgo_feminicida"))
    yv = 1 - rf["carpeta"].to_numpy().astype(float)
    p = yv.mean(); n = len(yv)
    g = rf["agencia_original"].to_numpy()
    G = np.unique(g)
    V = len(G) / (len(G) - 1) * np.sum([(yv[g == k] - p).sum() ** 2 for k in G]) / n ** 2
    gm = (rf["agencia_original"] + rf["mes"].cast(pl.String)).to_numpy()
    G2 = np.unique(gm)
    V2 = len(G2) / (len(G2) - 1) * np.sum([(yv[gm == k] - p).sum() ** 2 for k in G2]) / n ** 2
    rng = C.generador(20190304, "riesgo-bootstrap-agencia")
    idx = {k: np.where(g == k)[0] for k in G}
    bs = [yv[np.concatenate([idx[k] for k in rng.choice(G, len(G))])].mean() for _ in range(4000)]
    # diferencia dentro de agencia (Mantel-Haenszel), sin carpeta: con riesgo menos sin riesgo (m5)
    t = (x.group_by("agencia_original", "riesgo_feminicida").agg(pl.len().alias("n"), (1 - pl.col("carpeta").mean()).alias("sc"))
         .pivot(on="riesgo_feminicida", index="agencia_original", values=["n", "sc"]).drop_nulls())
    wmh = (t["n_true"] * t["n_false"] / (t["n_true"] + t["n_false"])).to_numpy()
    dmh = (t["sc_true"] - t["sc_false"]).to_numpy()
    # heterogeneidad entre agencias en los casos con riesgo (m6): sobredispersion binomial, agencias con >= 20 casos
    h = rf.group_by("agencia_original").agg(pl.len().alias("n"), (1 - pl.col("carpeta").mean()).alias("sc")).filter(pl.col("n") >= 20)
    zh = (h["sc"].to_numpy() - p) / np.sqrt(p * (1 - p) / h["n"].to_numpy())
    cols = ["mes", "agencia_original", "edad", "estado_civil", "relacion", "modalidad"] + VIO + ["riesgo_feminicida", "alto_riesgo"]
    out["intervalo_riesgo_sin_carpeta"] = {
        "unidad": "atenciones (la base no identifica personas)",
        "pct": p * 100, "n": n, "agencias": len(G),
        "semiamplitud_binomial_pp": 196 * np.sqrt(p * (1 - p) / n),
        "semiamplitud_agrupada_agencia_pp": 196 * np.sqrt(V), "efecto_de_diseno": float(V / (p * (1 - p) / n)),
        "semiamplitud_agrupada_agencia_mes_pp": 196 * np.sqrt(V2), "grupos_agencia_mes": len(G2),
        "ic95_bootstrap_por_agencia_pct": (np.percentile(bs, [2.5, 97.5]) * 100).tolist(),
        "filas_con_perfil_repetido_en_misma_agencia_mes": int(rf.select(cols).is_duplicated().sum()),
    }
    out["diferencia_dentro_de_agencia"] = {
        "sin_carpeta_con_riesgo_menos_sin_riesgo_pp": float(np.sum(wmh * dmh) / wmh.sum()) * 100,
        "cruda_pp": float(p - (1 - x.filter(~pl.col("riesgo_feminicida"))["carpeta"].mean())) * 100,
        "agencias": int(len(wmh)), "metodo": "Mantel-Haenszel de diferencia de riesgos por agencia"}
    out["heterogeneidad_entre_agencias_con_riesgo"] = {
        "agencias_con_20_o_mas": h.height, "phi": float((zh ** 2).sum() / (len(zh) - 1)),
        "min_sin_carpeta": float(h["sc"].min()), "max_sin_carpeta": float(h["sc"].max())}
    res["riesgo"] = out
    i = out["intervalo_riesgo_sin_carpeta"]
    print(f"  riesgo: {i['pct']:.1f}% sin carpeta, +-{i['semiamplitud_binomial_pp']:.2f} binomial, +-{i['semiamplitud_agrupada_agencia_pp']:.2f} agrupado, "
          f"bootstrap {np.round(i['ic95_bootstrap_por_agencia_pct'], 1)}; dentro de agencia {out['diferencia_dentro_de_agencia']['sin_carpeta_con_riesgo_menos_sin_riesgo_pp']:+.1f} pp")


def figuras(serie, res, emb, p0, phi_w, tau2):
    s = serie
    x = np.arange(s.height)
    conv = (s["carpetas"] / s["atenciones"]).to_numpy() * 100
    valido = s["valido"].to_numpy()
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7), sharex=True, gridspec_kw={"height_ratios": [1, 1.1]})
    ax1.plot(x, conv, color=BLUE, lw=2, marker="o", ms=3)
    ax1.plot(x[~valido], conv[~valido], "o", color=RED, ms=5, label="Meses sin 'NO' capturado (supone sin dato = no)")
    pct(ax1); ax1.set_ylabel("Conversión (%)"); ax1.set_ylim(0, 60)
    ax1.set_title("La mayor parte del salto en la conversión viene de registrar menos atenciones", fontweight="bold")
    ax1.legend(loc="upper left", framealpha=0.8)
    ax2.plot(x, s["atenciones"], color=BLUE_LIGHT, lw=2, label="Atenciones")
    ax2.plot(x, s["carpetas"], color=BLUE_DARK, lw=2, label="Carpetas iniciadas con abogada")
    miles(ax2); ax2.set_ylabel("Por mes"); ax2.legend(loc="upper right", framealpha=0.8)
    ax2.set_xticks(x[::3]); ax2.set_xticklabels(s["m"][::3], rotation=45, ha="right")
    guardar(fig, CARPETA, "01_conversion_y_su_cuenta", NOTA)

    n = emb["n"].to_numpy(); c = emb["conv"].to_numpy() * 100
    grid = np.linspace(n.min() * 0.9, n.max() * 1.05, 200)
    se = np.sqrt(p0 * (1 - p0) / grid + tau2) * 100
    se_b = np.sqrt(p0 * (1 - p0) / grid) * 100
    z998 = res["embudo"]["z_998"]
    fig, ax = plt.subplots(figsize=(9.5, 5))
    for z, ls in ((1.96, "--"), (z998, ":")):
        ax.plot(grid, p0 * 100 + z * se, color="#555", ls=ls, lw=1)
        ax.plot(grid, p0 * 100 - z * se, color="#555", ls=ls, lw=1)
    ax.plot(grid, p0 * 100 + z998 * se_b, color="#bbb", ls=":", lw=0.8)
    ax.plot(grid, p0 * 100 - z998 * se_b, color="#bbb", ls=":", lw=0.8, label="Límites binomiales al 99.8% (sin sobredispersión)")
    lim = np.sqrt(p0 * (1 - p0) / n + tau2) * 100 * z998
    fuera = np.abs(c - p0 * 100) > lim
    ax.scatter(n[~fuera], c[~fuera], color=BLUE, s=36, edgecolor="#000", linewidth=0.3)
    ax.scatter(n[fuera], c[fuera], color=RED, s=36, edgecolor="#000", linewidth=0.3, label="Fuera de los límites ajustados al 99.8%")
    ax.axhline(p0 * 100, color="#000", lw=0.8)
    ax.set_xlabel("Atenciones en la agencia (mar-2019 a mar-2020)"); ax.set_ylabel("Conversión (%)"); miles(ax, "x")
    ax.set_title(f"La misma política convierte entre {c.min():.0f}% y {c.max():.0f}% según la agencia", fontweight="bold")
    ax.legend(loc="upper right", framealpha=0.8); ax.set_ylim(0, max(c.max() * 1.1, 60))
    guardar(fig, CARPETA, "02_embudo_por_agencia", NOTA + f" Límites al 95% (--) y 99.8% (··) con variación entre agencias "
            f"tau = {np.sqrt(tau2)*100:.1f} pp (Spiegelhalter 2005, aditivo).")

    auc = res["modelo"]["auc"]
    etq = [("Caso sin sede (logística)", auc["logistica_caso_cv_por_agencia"]), ("Caso sin sede (boosting)", auc["boosting_caso_cv_por_agencia"]),
           ("Caso, probado en 2021-22", auc["logistica_caso_fuera_de_tiempo"]), ("Solo la agencia", auc["solo_agencia_cv_por_mes"]),
           ("Agencia + caso", auc["agencia_y_caso_cv_por_mes"])]
    fig, ax = plt.subplots(figsize=(8.5, 3.8))
    vals = [v for _, v in etq]
    bars = ax.barh([e for e, _ in etq], vals, color=BLUE, edgecolor="#000", linewidth=0.3)
    bars[int(np.argmax(vals))].set_color(RED)
    for b in bars:
        ax.text(b.get_width() + 0.005, b.get_y() + b.get_height() / 2, f"{b.get_width():.2f}", va="center", fontsize=9)
    ax.axvline(0.5, color="#000", ls="--", lw=0.8); ax.set_xlim(0.45, 1.0); ax.invert_yaxis()
    ax.set_xlabel("AUC (0.5 = azar)")
    ax.set_title("Saber en qué agencia se atendió predice la carpeta tanto como el caso mismo", fontweight="bold")
    guardar(fig, CARPETA, "03_que_predice_la_carpeta", NOTA)


def main():
    print("A03 dentro del programa")
    a = pl.read_parquet(C.INTERIM / "atenciones.parquet")
    res = {}
    serie = cuenta(a, res)
    d = res["descomposicion"]
    print(f"  conversion {d['conversion_inicio']:.3f} -> {d['conversion_fin']:.3f}; carpetas {d['cambio_carpetas_pct']:+.1f}%, "
          f"atenciones {d['cambio_atenciones_pct']:+.1f}%; parte por menos atenciones {d['parte_por_menos_atenciones_pct']:.0f}%")
    modelo(a, res)
    registro_vacio(a, res)
    emb, p0, phi_w, tau2 = embudo(a, res)
    riesgo(a, res)
    figuras(serie, res, emb, p0, phi_w, tau2)
    C.guardar_json(res, CARPETA)


if __name__ == "__main__":
    main()
