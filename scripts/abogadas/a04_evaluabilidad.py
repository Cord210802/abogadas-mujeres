"""A04 - ¿Se podia evaluar? El techo del efecto posible y el piso de lo que se puede detectar.

Dos numeros que no dependen de si el programa funciono:

  EL TECHO. Las abogadas abrieron una parte de las carpetas de violencia familiar
  de cada agencia. Aunque TODAS esas carpetas fueran nuevas (sin el programa no
  existirian), el efecto no podria pasar de s / (1 - s), con s esa parte. Supone que el
  programa no genera carpetas que no pasen por la abogada, y acota el efecto verdadero,
  no el estimado (que puede pasarlo por ruido).

  EL PISO. El efecto minimo detectable (80% de potencia, prueba al 5% a dos colas)
  de cada forma de desplegar el programa. Se simula en un mundo SIN programa:
  los 26 meses de 2017-01 a 2019-02, con las mismas unidades de A02. Se reparte el
  programa segun el diseño, se le suma un efecto conocido a las celdas tratadas
  (Y + Poisson(r * Y)) y se estima con el mismo estimador de A02. La distribucion
  nula sale de repetir el reparto sin efecto. La prueba es la de A02: se rechaza si
  |efecto| supera el percentil 95 de |nula| (dos colas por valor absoluto).

Diseños comparados (todos reparten al azar dentro de terciles de tamaño):
  real       los tamaños de cohorte de 2019 de la muestra, un mes de diferencia, con la
             composicion por tercil de la lista alfabetica (la plantilla original)
  real, composicion observada   las fechas reales de cada unidad (grandes primero)
  12 meses   las mismas unidades repartidas en 12 cohortes mensuales
  trimestral 4 cohortes, una cada tres meses
  espera     mitad con programa, mitad en lista de espera 12 meses

Y para la expansion nacional, lo mismo con el panel estado-año del CNPJE (INEGI,
2020-2024). La variable es `totalca1`: DELITOS de violencia familiar registrados en las
carpetas de investigacion abiertas (no carpetas).

Cambios por la auditoria (2026-09-21):
  - Prueba con la regla de A02 (|efecto| >= percentil 95 de |nula|); la de colas iguales se
    guarda como `potencia_colas_iguales` (auditoria/04_potencia.md m1).
  - 5,000 nulas y 2,000 replicas por efecto; MDE interpolado con su intervalo Monte Carlo
    (remuestreo de nulas y replicas) (04 M2, m3; 06_consistencia C1, C4).
  - Rango del MDE sobre las ventanas de lanzamiento ficticio (sep-2017 a dic-2018) para cada
    calendario: minimo, mediana y maximo (04 M1).
  - Diseño real con la composicion de cohortes observada (orden por tamaño) (04 m2).
  - MDE estatal traducido a efecto por agencia cubierta con la cobertura territorial de la VF
    de la ciudad, y cobertura necesaria para ver el +28% (04 M3; 06 C2).
  - Sensibilidad sin Campeche, Chiapas, Tlaxcala y Yucatan (series con quiebres) (04 m7).
  - Techo tambien sobre las unidades de A02 y sobre las celdas del estimando, con y sin
    topar el programa en la Fiscalia celda por celda (04 m5; 01 m11; 03 m7).
  - Un generador aleatorio por procedimiento; titulo de la figura sin cifras escritas a mano.

Salidas: grafs/abogadas/04_evaluabilidad/
"""
import json
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comun as C  # noqa: E402
from a02_efecto import cargar  # noqa: E402
from _viz import BLUE, BLUE_DARK, BLUE_LIGHT, RED, guardar, pct  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

CARPETA = "abogadas/04_evaluabilidad"
NOTA = ("Simulacion sobre carpetas reales de violencia familiar, 2017-01 a 2019-02 (antes del programa). "
        "80% de potencia, prueba al 5% a dos colas (la de A02).")
SEMILLA = 7
N_NULL = 5000
N_POT = 2000
N_MC = 1000                              # remuestreos para el intervalo Monte Carlo del MDE
EFECTOS = np.array([0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.60, 0.70, 0.80, 1.00])
DISENOS = ("real", "12 meses", "trimestral", "espera", "real_composicion_observada")
VENTANAS = range(8, 24)                  # inicio ficticio: 2017-09 a 2018-12 (indice de mes desde 2017-01)
INICIO_PRINCIPAL = 14                    # 2018-03: 12 meses antes del fin del mundo simulado
ESTADOS_ROTOS = {"04": "Campeche", "07": "Chiapas", "29": "Tlaxcala", "31": "Yucatán"}


# ------------------------------------------------------------------ techo
def techo(res):
    def s_de(p):
        prog, vf = p["carpetas_programa_vf"].to_numpy().astype(float), p["vf"].to_numpy().astype(float)
        s = prog.sum() / vf.sum()
        st = np.minimum(prog, vf).sum() / vf.sum()
        return {"parte_de_carpetas_vf_con_abogada": s, "efecto_maximo": s / (1 - s),
                "parte_topada_en_fiscalia": st, "efecto_maximo_topado": st / (1 - st),
                "carpetas_programa_vf": int(prog.sum()), "carpetas_vf": int(vf.sum()), "celdas": int(len(vf)),
                "unidades": int(p["unidad"].n_unique()),
                "celdas_programa_mayor_que_fiscalia": int((prog > vf).sum())}

    panel = pl.read_parquet(C.INTERIM / "panel.parquet")
    p = panel.filter(pl.col("mes").is_between(C.LANZAMIENTO, C.PRE_COVID_FIN) & (pl.col("mes") >= pl.col("entrada")))
    s = float(p["carpetas_programa_vf"].sum() / p["vf"].sum())
    por_mes = (p.group_by("mes").agg(pl.col("carpetas_programa_vf").sum(), pl.col("vf").sum()).sort("mes")
               .with_columns((pl.col("carpetas_programa_vf") / pl.col("vf")).alias("s")))
    res["techo"] = {"parte_de_carpetas_vf_con_abogada": s, "efecto_maximo": s / (1 - s),
                    "carpetas_programa_vf": int(p["carpetas_programa_vf"].sum()), "carpetas_vf": int(p["vf"].sum()),
                    "poblacion": "todas las unidades del panel con programa, mar-2019 a feb-2020",
                    "unidades": int(p.filter(pl.col("vf") > 0)["unidad"].n_unique()), "celdas": p.height,
                    "por_mes": por_mes.with_columns(pl.col("mes").dt.strftime("%Y-%m")).to_dicts()}

    # las mismas cuentas sobre la muestra de A02 y sobre las celdas del estimando
    mat, unidades, meses, entrada, _, _, info = cargar(detalle=True)
    falt = {(d["unidad"], d["mes"]) for d in info["celdas_faltantes"]["celdas"]}
    pm = (p.filter(pl.col("unidad").is_in(unidades))
          .with_columns(pl.concat_str([pl.col("unidad"), pl.col("mes").dt.strftime("%Y-%m")], separator="|").alias("k"))
          .filter(~pl.col("k").is_in([f"{u}|{m}" for u, m in falt])))
    T = len(meses)
    ok, _ = C.meses_identificados(entrada, T)
    _, trat = C.imputar(mat["vf"], entrada, ok)
    celdas = {(unidades[i], meses[t].isoformat()[:7]) for i, t in zip(*np.where(trat))}
    pe = pm.filter(pl.col("k").is_in([f"{u}|{m}" for u, m in celdas]))
    res["techo_muestra_a02"] = {**s_de(pm), "poblacion": f"las {len(unidades)} unidades de A02, mar-2019 a feb-2020, sin celdas faltantes"}
    res["techo_celdas_del_estimando"] = {**s_de(pe), "poblacion": "las celdas tratadas identificadas del efecto de A02"}
    res["techo_supuestos"] = ("el programa no genera carpetas que no pasen por la abogada; el techo acota el efecto "
                              "verdadero, no el estimado, que puede superarlo por ruido")
    # la regla anterior de muestra (52 unidades), para comparar con lo publicado
    mat52, u52, m52, e52, _, _ = cargar("ventana_completa")
    ok52, _ = C.meses_identificados(e52, len(m52))
    _, trat52 = C.imputar(mat52["vf"], e52, ok52)
    c52 = {f"{u52[i]}|{m52[t].isoformat()[:7]}" for i, t in zip(*np.where(trat52))}
    p52 = p.filter(pl.col("unidad").is_in(u52)).with_columns(
        pl.concat_str([pl.col("unidad"), pl.col("mes").dt.strftime("%Y-%m")], separator="|").alias("k"))
    res["techo_regla_ventana_completa"] = {"muestra": s_de(p52), "celdas_del_estimando": s_de(p52.filter(pl.col("k").is_in(list(c52))))}
    print(f"  techo: {s*100:.1f}% -> {s/(1-s)*100:.0f}% (todas); muestra {res['techo_muestra_a02']['efecto_maximo']*100:.0f}%; "
          f"celdas del estimando {res['techo_celdas_del_estimando']['efecto_maximo']*100:.0f}% "
          f"(topado {res['techo_celdas_del_estimando']['efecto_maximo_topado']*100:.0f}%)")


# ----------------------------------------------------------- simulacion
def estratos(tamano, k=3):
    return np.digitize(tamano, np.quantile(tamano, np.linspace(0, 1, k + 1)[1:-1]))


def asignar(entradas_base, estrato, rng):
    """Reparte un vector de fechas de entrada al azar dentro de cada estrato."""
    ent = np.empty(len(entradas_base))
    for s in np.unique(estrato):
        idx = np.where(estrato == s)[0]
        ent[idx] = rng.permutation(entradas_base[idx])
    return ent


def plantilla(diseno, n, inicio, T, ent_real=None):
    if diseno == "real":
        # tamaños de cohorte reales de la muestra, asignados en orden alfabetico de unidad
        tam = np.unique(ent_real, return_counts=True)[1]
        return np.concatenate([np.full(k, inicio + i) for i, k in enumerate(tam)]).astype(float)[:n]
    if diseno == "real_composicion_observada":
        return inicio + (ent_real - ent_real.min())
    if diseno == "12 meses":
        return np.array([inicio + (i * 12) // n for i in range(n)], float)
    if diseno == "trimestral":
        return np.array([inicio + 3 * ((i * 4) // n) for i in range(n)], float)
    if diseno == "espera":
        return np.array([inicio if i < n // 2 else np.inf for i in range(n)], float)
    raise ValueError(diseno)


def cabe(diseno, inicio, T):
    """¿El calendario completo cabe en el mundo simulado?"""
    # el despliegue real solo identifica sus 3 primeros meses: basta con que quepan esos
    ultimo = {"real": inicio + 2, "real_composicion_observada": inicio + 2, "12 meses": inicio + 11,
              "trimestral": inicio + 9, "espera": inicio + 11}[diseno]
    return ultimo <= T - 1


def interpolar(efectos, potencias, meta=0.8):
    for x0, p0, x1, p1 in zip(efectos, potencias, efectos[1:], potencias[1:]):
        if p0 < meta <= p1:
            return float(x0 + (meta - p0) * (x1 - x0) / (p1 - p0))
    return None


def simular(Y, estrato, base, rng, minimo=C.MIN_SIN_PROGRAMA, n_null=N_NULL, n_pot=N_POT, efectos=EFECTOS):
    T = Y.shape[1]

    def est(Ysim, ent):
        mo, _ = C.meses_identificados(ent, T, minimo)
        Yhat, trat = C.imputar(Ysim, ent, mo)
        return C.razon(Ysim, Yhat, trat), int(trat.sum())

    nulas = np.array([est(Y, asignar(base, estrato, rng))[0] for _ in range(n_null)])
    nulas = nulas[np.isfinite(nulas)]
    lo, hi = np.percentile(nulas, [2.5, 97.5])
    c_abs = np.percentile(np.abs(nulas), 95)
    celdas = est(Y, asignar(base, estrato, rng))[1]
    alt = {}
    for r in efectos:
        v = np.empty(n_pot)
        for k in range(n_pot):
            ent = asignar(base, estrato, rng)
            t = np.arange(T)[None, :] >= ent[:, None]
            Ys = Y.copy()
            Ys[t] = Y[t] + rng.poisson(r * Y[t])
            v[k] = est(Ys, ent)[0]
        alt[float(r)] = v
    pot = {r: float(np.mean(np.abs(v) >= c_abs)) for r, v in alt.items()}
    pot_ct = {r: float(np.mean((v > hi) | (v < lo))) for r, v in alt.items()}
    grid = lambda pp: next((r for r in efectos if pp[float(r)] >= 0.8), None)  # noqa: E731
    mde_i = interpolar(list(efectos), [pot[float(r)] for r in efectos])
    # intervalo Monte Carlo del MDE interpolado: remuestreo de nulas y de replicas
    mc = []
    for _ in range(N_MC):
        nb = rng.choice(nulas, len(nulas))
        cb = np.percentile(np.abs(nb), 95)
        pb = [np.mean(np.abs(rng.choice(alt[float(r)], n_pot)) >= cb) for r in efectos]
        m = interpolar(list(efectos), pb)
        if m is not None:
            mc.append(m)
    return {"mde": float(grid(pot)) if grid(pot) is not None else None,
            "mde_interpolado": mde_i,
            "mde_interpolado_ic_mc": np.percentile(mc, [2.5, 97.5]).tolist() if mc else None,
            "mde_interpolado_ee_mc": float(np.std(mc)) if mc else None,
            "nula_ic95": [float(lo), float(hi)], "nula_abs_q95": float(c_abs), "nula_de": float(np.std(nulas)),
            "nula_media": float(np.mean(nulas)),
            "celdas_tratadas_identificadas": celdas, "potencia": pot,
            "potencia_colas_iguales": pot_ct,
            "mde_colas_iguales": float(grid(pot_ct)) if grid(pot_ct) is not None else None,
            "mde_colas_iguales_interpolado": interpolar(list(efectos), [pot_ct[float(r)] for r in efectos]),
            "nulas": n_null, "replicas_por_efecto": n_pot,
            "prueba": "|efecto| >= percentil 95 de |nula| (la de A02)"}


# ------------------------------------------------ datos del mundo simulado
def mundo():
    mat, unidades, meses, entrada, _, _ = cargar()
    pre = np.array([m < C.LANZAMIENTO for m in meses])
    Y = mat["vf"][:, pre]
    tam = mat["total"][:, np.array([m.year == 2018 for m in meses])].sum(1)
    return Y, estratos(tam), entrada, unidades, meses


def _tarea(args):
    diseno, inicio = args
    Y, estrato, entrada, unidades, _ = mundo()
    T = Y.shape[1]
    base = plantilla(diseno, len(unidades), inicio, T, entrada)
    rng = C.generador(SEMILLA, f"piso-{diseno}-{inicio}")
    return diseno, inicio, simular(Y, estrato, base, rng)


def pisos(res):
    Y, estrato, entrada, unidades, meses = mundo()
    T = Y.shape[1]
    cambio = Y[:, 12:24].sum(1) / Y[:, :12].sum(1) - 1
    res["deriva_sin_programa"] = {"cambio_2017_2018_percentiles": dict(zip(["p5", "p25", "p50", "p75", "p95"],
                                  np.percentile(cambio, [5, 25, 50, 75, 95]).round(3).tolist()))}
    res["deriva_sin_programa"]["por_unidad"] = [{"unidad": u, "cambio": round(float(c), 4)} for u, c in zip(unidades, cambio)]
    print("  deriva 2017->2018 por unidad:", res["deriva_sin_programa"]["cambio_2017_2018_percentiles"])

    tareas = [(d, i) for d in DISENOS for i in VENTANAS if cabe(d, i, T)]
    with Pool(8) as pool:
        salida = pool.map(_tarea, tareas)
    por = {(d, i): r for d, i, r in salida}
    out = {d: por[(d, INICIO_PRINCIPAL)] for d in ("real", "12 meses", "trimestral", "espera")}
    for d, v in out.items():
        print(f"  piso {d:10}: MDE rejilla {v['mde']}, interpolado {v['mde_interpolado']:.3f} "
              f"(MC {np.round(v['mde_interpolado_ic_mc'], 3)}), celdas {v['celdas_tratadas_identificadas']}, nula 95% {np.round(v['nula_ic95'], 3)}")
    res["pisos"] = out
    res["pisos_composicion_observada"] = por[("real_composicion_observada", INICIO_PRINCIPAL)]
    ventanas = {}
    for d in DISENOS:
        filas = [{"inicio": meses[i].isoformat()[:7], "mde_interpolado": por[(d, i)]["mde_interpolado"],
                  "mde": por[(d, i)]["mde"], "nula_de": por[(d, i)]["nula_de"],
                  "mde_colas_iguales_interpolado": por[(d, i)]["mde_colas_iguales_interpolado"]}
                 for i in VENTANAS if (d, i) in por]
        v = np.array([f["mde_interpolado"] if f["mde_interpolado"] is not None else np.nan for f in filas])
        ventanas[d] = {"ventanas": len(filas), "minimo": float(np.nanmin(v)), "mediana": float(np.nanmedian(v)),
                       "maximo": float(np.nanmax(v)), "sin_mde_en_rejilla": int(np.isnan(v).sum()), "por_ventana": filas}
        print(f"  ventanas {d:28}: {len(filas)} ventanas, MDE min {np.nanmin(v):.3f} mediana {np.nanmedian(v):.3f} max {np.nanmax(v):.3f}")
    res["pisos_por_ventana"] = ventanas
    res["mundo_simulado"] = {"meses": [meses[0].isoformat()[:7], meses[T - 1].isoformat()[:7]], "unidades": len(unidades),
                             "inicio_simulado": meses[INICIO_PRINCIPAL].isoformat()[:7],
                             "ventanas": [meses[VENTANAS[0]].isoformat()[:7], meses[VENTANAS[-1]].isoformat()[:7]],
                             "cohortes_por_tercil_alfabetico": {str(g): np.bincount(
                                 (plantilla("real", len(unidades), 0, T, entrada)[estrato == g]).astype(int), minlength=6).tolist() for g in range(3)},
                             "cohortes_por_tercil_observado": {str(g): np.bincount(
                                 (entrada[estrato == g] - entrada.min()).astype(int), minlength=6).tolist() for g in range(3)}}


def diagnostico_estimadores(res, n=300):
    """¿Otro estimador baja el ruido? Desviacion estandar del efecto nulo con tres variantes."""
    Y, estrato, entrada, unidades, _ = mundo()
    T = Y.shape[1]
    t = np.arange(T)
    rng = C.generador(SEMILLA, "diagnostico")

    def ipf(ent, ultimos=None):
        mo, _ = C.meses_identificados(ent, T)
        sin = t[None, :] < ent[:, None]
        W = sin.copy()
        if ultimos:
            W &= t[None, :] >= (T - 12 - ultimos)
        a, b = C.ajustar_poisson(Y, W)
        Yh = a[:, None] * b[None, :]
        return C.razon(Y, Yh, (~sin) & mo[None, :] & np.isfinite(Yh))

    def tendencia(ent):
        sin = t[None, :] < ent[:, None]
        L = np.log(Y + 1)
        mfe = np.array([L[sin[:, j], j].mean() if sin[:, j].sum() >= C.MIN_SIN_PROGRAMA else np.nan for j in range(T)])
        Yh = np.zeros_like(Y)
        for i in range(Y.shape[0]):
            p = sin[i] & np.isfinite(mfe)
            c = np.polyfit(t[p], L[i, p] - mfe[p], 1)
            Yh[i] = np.exp(np.polyval(c, t) + mfe) - 1
        tr = (~sin) & np.isfinite(mfe)[None, :]
        return float(Y[tr].sum() / Yh[tr].sum() - 1)

    out = {}
    for d in ("real", "espera"):
        base = plantilla(d, len(unidades), T - 12, T, entrada)
        out[d] = {}
        for nombre, f in (("imputacion", lambda e: ipf(e)), ("imputacion_ultimos_12", lambda e: ipf(e, 12)),
                          ("tendencia_por_agencia", tendencia)):
            v = np.array([f(asignar(base, estrato, rng)) for _ in range(n)])
            out[d][nombre] = float(np.nanstd(v))
    res["diagnostico_estimadores_de_nula"] = out
    print("  diagnostico DE nula:", {d: {k: round(x, 3) for k, x in v.items()} for d, v in out.items()})


def estados(res):
    """Expansion nacional: panel estado-año del CNPJE, delitos de violencia familiar registrados."""
    c = pl.read_parquet(C.ROOT / "data" / "interim" / "cnpje" / "cnpje_carpetas_delitos.parquet")
    x = (c.filter(pl.col("tipdelit_e_desc") == "Violencia familiar")
         .with_columns(pl.col("totalca1").cast(pl.Float64, strict=False).alias("n"))
         .filter(pl.col("cve_ent") != "09")
         .pivot(on="anio_dato", index="cve_ent", values="n", aggregate_function="sum").sort("cve_ent"))
    anios = sorted([k for k in x.columns if k != "cve_ent"])
    Y = x.select(anios).to_numpy()
    cve = x["cve_ent"].to_list()
    ok = np.isfinite(Y).all(1) & (Y > 0).all(1)
    Y = Y[ok]
    cve = [k for k, o in zip(cve, ok) if o]
    efectos = np.array([0.05, 0.10, 0.125, 0.15, 0.175, 0.20, 0.25, 0.30, 0.40, 0.50])

    def correr(Ys, nombre):
        n, T = Ys.shape
        base = np.array([T - 2 if i < n // 2 else np.inf for i in range(n)], float)
        return simular(Ys, estratos(Ys[:, 0]), base, C.generador(SEMILLA, nombre), minimo=1, efectos=efectos)

    out = {"estados": int(len(Y)), "anios": anios,
           "variable": "totalca1: delitos de violencia familiar registrados en las carpetas de investigacion abiertas (no carpetas)"}
    out["mitad_y_mitad"] = correr(Y, "estados")
    keep = np.array([k not in ESTADOS_ROTOS for k in cve])
    out["sin_series_rotas"] = {**correr(Y[keep], "estados-sin-rotos"), "estados": int(keep.sum()),
                               "excluidos": list(ESTADOS_ROTOS.values())}
    # dilucion: el efecto estatal es cobertura x efecto local (auditoria 04 M3)
    a1 = json.loads((C.GRAFS / "01_limpieza" / "resultados.json").read_text())
    cob = a1["vf_ciudad_en_territoriales"]["ene2017_feb2020"]
    ef = json.loads((C.GRAFS / "02_efecto" / "resultados.json").read_text())["resultados"]["vf"]["efecto"]
    m = out["mitad_y_mitad"]["mde_interpolado"]
    out["dilucion"] = {"cobertura_territorial_vf_cdmx": cob,
                       "mde_estatal_interpolado": m, "mde_estatal_rejilla": out["mitad_y_mitad"]["mde"],
                       "efecto_local_equivalente_interpolado": m / cob if m else None,
                       "efecto_local_equivalente_rejilla": out["mitad_y_mitad"]["mde"] / cob if out["mitad_y_mitad"]["mde"] else None,
                       "efecto_a02": ef, "cobertura_necesaria_para_ver_efecto_a02_como_mde": m / ef if m else None,
                       "nota": "el MDE estatal se inyecta en todas las carpetas del estado; si solo las agencias "
                               "territoriales tienen programa, el efecto estatal es cobertura x efecto local"}
    print(f"  estados (CNPJE, {len(Y)} estados, {anios[0]}-{anios[-1]}): MDE {out['mitad_y_mitad']['mde']} "
          f"interp {m:.3f}; sin 4 rotos {out['sin_series_rotas']['mde_interpolado']:.3f}; por agencia cubierta {m/cob:.3f}")
    out["todos_a_la_vez"] = "no identificado: sin estados sin programa no hay contra que comparar"
    res["expansion_estados"] = out


def figura(res, efecto_estimado):
    etq = {"real": "Como se hizo (5 meses)", "12 meses": "Escalonado en 12 meses",
           "trimestral": "Cuatro grupos, cada 3 meses", "espera": "Mitad y mitad, 12 meses de espera"}
    ds = ["real", "12 meses", "trimestral", "espera"]
    vals = [(res["pisos"][d]["mde_interpolado"] or 1.2) * 100 for d in ds]
    fig, ax = plt.subplots(figsize=(9.5, 4.4))
    bars = ax.barh([etq[d] for d in ds], vals, color=BLUE, edgecolor="#000", linewidth=0.3)
    bars[0].set_color(RED)
    for b, d in zip(bars, ds):
        v = res["pisos"][d]
        w = res["pisos_por_ventana"][d]
        ic = v["mde_interpolado_ic_mc"]
        ax.errorbar(b.get_width(), b.get_y() + b.get_height() / 2, xerr=[[b.get_width() - ic[0] * 100], [ic[1] * 100 - b.get_width()]],
                    color="#000", capsize=3, lw=1)
        ax.plot([w["minimo"] * 100, w["maximo"] * 100], [b.get_y() + b.get_height() * 0.95] * 2, color="#888", lw=3, alpha=0.6)
        ax.text(max(b.get_width(), w["maximo"] * 100) + 1.5, b.get_y() + b.get_height() / 2,
                f"{b.get_width():.0f}%  (ventanas: {w['minimo']*100:.0f}-{w['maximo']*100:.0f}%)", va="center", fontsize=8.5)
    t = res["techo_celdas_del_estimando"]["efecto_maximo"] * 100
    ax.axvline(t, color="#000", ls="--", lw=1)
    ax.text(t + 1, 3.45, f"techo: {t:.0f}%", fontsize=9)
    ax.axvline(efecto_estimado * 100, color="#666", ls=":", lw=1.2)
    ax.text(efecto_estimado * 100 + 1, -0.45, f"estimado: {efecto_estimado*100:.0f}%", fontsize=9, color="#444")
    ax.invert_yaxis(); ax.set_xlim(0, max(vals + [t]) * 1.35)
    ax.set_xlabel("Efecto mínimo detectable en carpetas de violencia familiar (%)")
    ax.set_title("Midiendo por agencia, ningún despliegue detecta con 80% de probabilidad efectos menores a "
                 f"{min(res['pisos_por_ventana'][d]['minimo'] for d in ds)*100:.0f}%", fontweight="bold")
    guardar(fig, CARPETA, "01_efecto_minimo_por_diseno", NOTA + " Barra: ventana mar-2018; negro: intervalo Monte Carlo; "
            "gris: rango sobre ventanas de lanzamiento ficticio.")


def main():
    print("A04 evaluabilidad")
    res = {}
    techo(res)
    pisos(res)
    diagnostico_estimadores(res)
    estados(res)
    ef = json.loads((C.ROOT / "grafs" / "abogadas" / "02_efecto" / "resultados.json").read_text())["resultados"]["vf"]["efecto"]
    res["efecto_estimado_a02"] = ef
    figura(res, ef)
    C.guardar_json(res, CARPETA)


if __name__ == "__main__":
    main()
