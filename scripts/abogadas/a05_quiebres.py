"""A05 - ¿Donde cambia de nivel la violencia familiar? Puntos de cambio con PELT.

Pregunta. Si las abogadas aumentaron las carpetas, cada agencia deberia cambiar de
nivel en SU mes de llegada. Si lo que paso fue un choque de toda la ciudad, las
agencias cambian en un mismo mes CALENDARIO sin importar cuando llegaron. Un detector
de puntos de cambio, corrido agencia por agencia sin decirle nada del programa,
permite ver cual de los dos patrones aparece.

Metodo: PELT (Pruned Exact Linear Time; Killick, Fearnhead y Eckley 2012, JASA
107(500): 1590-1598, DOI 10.1080/01621459.2012.737745), implementado aqui en numpy.

  F(t) = min_s [ F(s) + C(y_{s+1:t}) + beta ],   F(0) = -beta

y la poda: un candidato s se descarta para siempre cuando F(s) + C(y_{s+1:t}) >= F(t).
Con longitud minima de segmento m la poda solo es exacta para finales T >= t + m
(el segmento (t, T] tiene que ser legal), asi que el candidato se retira m meses despues
de que se cumple la condicion. La validacion compara contra la programacion dinamica
sin poda (Jackson et al. 2005) y contra la enumeracion de todas las segmentaciones.

Costo (docs/abogadas/06_quiebres.md explica cada decision):
  - Estacionalidad como desplazamiento conocido: y_t ~ Poisson(lambda_segmento * s_mes),
    con s_mes estimado ANTES del programa (Poisson con efecto de año y de mes).
    Sin esto PELT marca los picos de primavera de cada año.
  - Sobredispersion: el costo es la devianza Poisson dividida entre phi (cuasi-verosimilitud).
    phi se mide con diferencias de un mes a otro (robustas a los propios quiebres).
  - Penalizacion beta = k * log(n). k se elige ANTES de mirar los quiebres reales: el
    menor k de la rejilla cuyo tasa de quiebres espurios en series simuladas sin quiebre
    (misma estacionalidad, nivel y sobredispersion) queda en 5% o menos.

Analisis:
  A. La ciudad: serie de violencia familiar en agencias territoriales, 2016-01 a 2020-02.
  B. Por agencia: las unidades de A02 (54), 2017-01 a 2020-02. Estadistico = proporcion de
     agencias con un quiebre al alza en su mes de llegada o el siguiente (e = 0 o +1).
     p-valor: permutando las fechas de llegada dentro de terciles de tamaño (como A02).
     Robos como placebo.

Validacion: exactitud de la poda, quiebres espurios, potencia por tamaño de salto y
potencia/tamaño de la prueba por agencia (incluido un choque comun que NO deberia
rechazar).

Cambios por la auditoria (2026-09-21):
  - `k_rango_por_quiebre` guardaba min(k_min) y max(k_max) sobre tramos no contiguos: decia que
    mayo de 2019 aparece con cualquier k, y desaparece en k de 2.3 a 3.6. Ahora guarda la lista
    de intervalos disjuntos de cada mes (auditoria/05_quiebres.md M1).
  - Una sola matriz de 10,000 permutaciones estratificadas para la especificacion principal,
    las ventanas, los k, el placebo temporal y el ajuste por especificaciones: el p de la misma
    especificacion ya no sale distinto en tres corridas (05 m6; 06_consistencia m12).
  - Placebo temporal: todas las fechas de llegada corridas -3, -2, -1, +1, +2 meses; ventana
    -3..+3; p por mes relativo, con e = -1 solo separado de la ventana -1..+1 (05 M2, m1).
  - Ajuste min-p de Westfall-Young sobre las 36 especificaciones (4 ventanas x 9 k) (05 M3).
  - Magnitud de los escalones: mediana, y conteo solo con escalones <= +100% y <= +60% (05 M4).
  - `unidades_con_algun_quiebre` cuenta quiebres en CUALQUIER punto de 2017-2020, no en la
    ventana; se agrega `unidades_con_algun_quiebre_descripcion` (05 M5).
  - Calibracion de falsos positivos tambien con nivel latente AR(1), tendencia suave y
    estacionalidad propia por agencia (05 m2).
  - Placebo de robos (y VF) a la baja (05 m4) y mas nulos de choque comun, incluido un programa
    que empieza un mes antes de la fecha registrada (05 m5, M2).
  - phi del modelo de tendencia de A02 leido de su resultados.json, no escrito a mano (02 m2).
  - Series con celdas faltantes (IZP-7 desde sep-2019, ver A02): PELT corre sobre el tramo
    observado. Un generador aleatorio por procedimiento.

Salidas: grafs/abogadas/05_quiebres/
"""
import datetime as dt
import itertools
import sys
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comun as C  # noqa: E402
from a02_efecto import cargar  # noqa: E402
from _viz import BLUE, BLUE_DARK, BLUE_LIGHT, RED, guardar, miles, pct  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

CARPETA = "abogadas/05_quiebres"
NOTA = ("Fuente: FGJ CDMX (carpetas por fecha de inicio) y SEMUJERES (fechas de llegada). "
        "PELT con costo Poisson estacional escalado por sobredispersion.")
SEMILLA = 20190304                       # la misma de A02
MIN_SEG = 3                              # meses minimos por segmento
K_REJILLA = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0]   # beta = k * log(n)
FP_OBJETIVO = 0.05                       # tasa de series sin quiebre que marcan alguno
VENTANA_E = (0, 1)                       # "en su llegada": e = 0 o e = +1
N_PERM = 10000
N_NULA_PANEL = 100                       # paneles simulados sin quiebre (x unidades de A02)
N_NULA_CIUDAD = 1000
N_POT = 500                              # series por (nivel, salto)
N_PANEL_POT = 200                        # paneles por escenario de la prueba por agencia
N_PERM_SIM = 500
SALTOS = [0.10, 0.20, 0.30, 0.45]
rng = np.random.default_rng(SEMILLA)
ESPECIFICACIONES_V = (("e0", (0, 0)), ("e0a1", (0, 1)), ("e-1a1", (-1, 1)), ("e0a2", (0, 2)))


def usar(nombre):
    """Cambia el generador global a uno propio del procedimiento (auditoria 02 m10)."""
    global rng
    rng = C.generador(SEMILLA, nombre)


def phi_a02():
    """Sobredispersion del modelo de tendencia de la ciudad en A02 (antes se escribia 3.9 a mano)."""
    import json
    return float(json.loads((C.GRAFS / "02_efecto" / "resultados.json").read_text())["ciudad"]["sobredispersion"])


# ======================================================================= PELT
def costo_poisson(y, s, phi=1.0):
    """Costo de un segmento con media lambda * s_t: -2 log-verosimilitud / phi.

    Con lambda de maxima verosimilitud (sum y / sum s) y quitando los terminos que
    suman lo mismo en cualquier segmentacion, el costo del segmento (a, b] es
    -2/phi * Sy * log(Sy / Ss). Se evalua en O(1) con sumas acumuladas.
    """
    cy = np.concatenate([[0.0], np.cumsum(y)])
    cs = np.concatenate([[0.0], np.cumsum(s)])

    def c(a, b):
        sy = cy[b] - cy[a]
        ss = cs[b] - cs[a]
        with np.errstate(divide="ignore", invalid="ignore"):
            v = np.where(sy > 0, sy * np.log(sy / ss), 0.0)
        return -2.0 * v / phi
    return c


def costo_normal(v, sigma2):
    """Cambio de media normal con varianza conocida: sum (v - media)^2 / sigma2."""
    c1 = np.concatenate([[0.0], np.cumsum(v)])
    c2 = np.concatenate([[0.0], np.cumsum(v * v)])

    def c(a, b):
        n = b - a
        s1 = c1[b] - c1[a]
        return ((c2[b] - c2[a]) - s1 * s1 / n) / sigma2
    return c


def _rastrear(ultimo, n):
    cps, t = [], n
    while t > 0:
        t = int(ultimo[t])
        if t > 0:
            cps.append(t)
    return sorted(cps)


def pelt(n, costo, beta, m=MIN_SEG, podar=True):
    """PELT (Killick, Fearnhead y Eckley 2012). Devuelve (quiebres, F(n), evaluaciones).

    Un quiebre en t significa que el nuevo segmento empieza en la observacion t
    (indice base 0). podar=False es la programacion dinamica exacta sin poda
    (optimal partitioning), que sirve para verificar la poda.
    """
    F = np.full(n + 1, np.inf)
    F[0] = -beta
    ultimo = np.zeros(n + 1, dtype=int)
    muerto = np.full(n + 1, np.iinfo(np.int64).max // 2)   # t en que se cumplio la regla de poda
    R = np.array([0])
    evaluaciones = 0
    for t in range(m, n + 1):
        cand = R[(t - R) >= m]
        if cand.size == 0:
            continue
        v = F[cand] + costo(cand, np.full(cand.size, t))
        evaluaciones += cand.size
        k = int(np.argmin(v))
        F[t] = v[k] + beta
        ultimo[t] = cand[k]
        if podar:
            nuevos = cand[(v >= F[t]) & (muerto[cand] > t)]
            muerto[nuevos] = t
            R = R[t < muerto[R] + m]           # solo se retira cuando (t, T] ya es legal
        R = np.append(R, t)
    return _rastrear(ultimo, n), float(F[n]), evaluaciones


def exhaustiva(n, costo, beta, m=MIN_SEG):
    """Todas las segmentaciones legales, una por una (solo para series cortas)."""
    mejor, arg = np.inf, []
    pos = range(m, n - m + 1)
    for k in range(0, n // m):
        for cps in itertools.combinations(pos, k):
            b = (0,) + cps + (n,)
            if any(b[i + 1] - b[i] < m for i in range(len(b) - 1)):
                continue
            v = sum(float(costo(np.array([b[i]]), np.array([b[i + 1]]))[0]) for i in range(len(b) - 1)) + beta * k
            if v < mejor - 1e-12:
                mejor, arg = v, list(cps)
    return arg, mejor


# ========================================================= piezas del modelo
def estacionalidad(y, meses, entrenamiento):
    """Factores de mes (media 1) con Poisson año x mes ajustado solo en los meses de entrenamiento.

    Reutiliza el ajuste proporcional iterativo de _comun: filas = años, columnas =
    meses del año. El efecto de año absorbe el nivel, asi que un cambio de nivel dentro
    del periodo previo no contamina los factores de mes.
    """
    anios = sorted({x.year for x in meses})
    Y = np.zeros((len(anios), 12))
    W = np.zeros_like(Y, dtype=bool)
    for v, x, e in zip(y, meses, entrenamiento):
        Y[anios.index(x.year), x.month - 1] = v
        W[anios.index(x.year), x.month - 1] = e
    _, b = C.ajustar_poisson(Y, W)
    return b / b.mean()


def dispersion(y, s):
    """Sobredispersion phi con diferencias de un mes a otro (robusta a los quiebres).

    z = y / s tiene varianza phi * lambda / s. La diferencia z_t - z_{t-1}, dividida
    entre sqrt(lambda_local * (1/s_t + 1/s_{t-1})), tiene varianza phi si no hay quiebre
    entre t-1 y t. Con la mediana de desviaciones absolutas, unos cuantos quiebres no
    la mueven. Se acota abajo en 1: un conteo no puede ser menos disperso que Poisson
    salvo por ruido de estimacion.
    """
    z = y / s
    d = np.diff(z)
    lam = np.maximum((z[1:] + z[:-1]) / 2, 1e-9)
    u = d / np.sqrt(lam * (1 / s[1:] + 1 / s[:-1]))
    mad = np.median(np.abs(u - np.median(u))) / 0.6745
    return float(max(1.0, mad ** 2))


def segmentar(y, s, k, phi=None, m=MIN_SEG):
    """PELT con costo Poisson estacional; devuelve quiebres, niveles y cambios."""
    n = len(y)
    phi = dispersion(y, s) if phi is None else phi
    cps, _, _ = pelt(n, costo_poisson(y, s, phi), k * np.log(n), m)
    b = [0] + cps + [n]
    niveles = [float(y[b[i]:b[i + 1]].sum() / s[b[i]:b[i + 1]].sum()) for i in range(len(b) - 1)]
    cambios = [niveles[i + 1] / niveles[i] - 1 if niveles[i] > 0 else np.inf for i in range(len(niveles) - 1)]
    return {"quiebres": cps, "niveles": niveles, "cambios": cambios, "phi": phi, "limites": b}


def simular(mu, phi):
    """Poisson-gamma (binomial negativa) con varianza phi * mu."""
    mu = np.asarray(mu, float)
    if phi <= 1.0001:
        return rng.poisson(mu).astype(float)
    forma = mu / (phi - 1)                   # gamma con media mu y varianza mu * (phi - 1)
    return rng.poisson(rng.gamma(forma, mu / forma)).astype(float)


# =============================================================== A. la ciudad
def serie_ciudad():
    t = pl.read_parquet(C.INTERIM / "fgj_tipo_agencia.parquet")
    s = (t.filter(pl.col("tipo") == "Agencias territoriales")
         .filter(pl.col("mes").is_between(dt.date(2016, 1, 1), dt.date(2020, 2, 1))).sort("mes"))
    return s["n"].to_numpy().astype(float), s["mes"].to_list()


def barrido(y, s, phi, betas, m=MIN_SEG):
    """Segmentacion para una rejilla fina de beta (camino tipo CROPS; Haynes et al. 2017).

    Devuelve los tramos de beta donde la segmentacion no cambia.
    """
    c = costo_poisson(y, s, phi)
    n = len(y)
    tramos = []
    for b in betas:
        cps, F, _ = pelt(n, c, b, m)
        if tramos and tramos[-1]["quiebres"] == cps:
            tramos[-1]["beta_max"] = float(b)
        else:
            if tramos:
                tramos[-1]["beta_max"] = float(b)     # tramos contiguos: el siguiente empieza donde acaba este
            tramos.append({"beta_min": float(b), "beta_max": float(b), "quiebres": cps})
    return tramos


def ciudad(k_ciudad, res):
    y, meses = serie_ciudad()
    n = len(y)
    pre = np.array([x < C.LANZAMIENTO for x in meses])
    f = estacionalidad(y, meses, pre)
    s = f[[x.month - 1 for x in meses]]
    seg = segmentar(y, s, k_ciudad)
    mes = lambda i: meses[i].isoformat()[:7]  # noqa: E731

    # sensibilidad: rejilla de k, camino fino de beta, sin desestacionalizar, costo normal
    por_k = {str(k): [mes(c) for c in segmentar(y, s, k, seg["phi"])["quiebres"]] for k in K_REJILLA}
    betas = np.exp(np.linspace(np.log(0.5 * np.log(n)), np.log(40 * np.log(n)), 400))
    tramos = barrido(y, s, seg["phi"], betas)
    for t_ in tramos:
        t_["k_min"], t_["k_max"] = t_["beta_min"] / np.log(n), t_["beta_max"] / np.log(n)
        t_["quiebres"] = [mes(c) for c in t_["quiebres"]]
    # intervalos de k en que aparece cada mes; se unen solo tramos contiguos (auditoria 05 M1)
    rango_k = {}
    for t_ in tramos:
        for q in t_["quiebres"]:
            iv = rango_k.setdefault(q, [])
            if iv and abs(iv[-1][1] - t_["k_min"]) < 1e-9:
                iv[-1][1] = t_["k_max"]
            else:
                iv.append([t_["k_min"], t_["k_max"]])
    crudo = segmentar(y, np.ones(n), k_ciudad)
    v = 2 * np.sqrt(y / s + 3 / 8)                       # Anscombe sobre la serie desestacionalizada
    sig2 = (np.median(np.abs(np.diff(v) - np.median(np.diff(v)))) / 0.6745) ** 2 / 2
    cps_n, _, _ = pelt(n, costo_normal(v, sig2), k_ciudad * np.log(n))

    # dispersion de Pearson dentro de los segmentos: ¿la phi de diferencias era razonable?
    mu = np.concatenate([[lv] * (seg["limites"][i + 1] - seg["limites"][i]) for i, lv in enumerate(seg["niveles"])]) * s
    phi_pearson = float(((y - mu) ** 2 / mu).sum() / (n - 2 * len(seg["niveles"]) + 1))
    r = (y - mu) / np.sqrt(mu)
    ac1 = float(np.corrcoef(r[1:], r[:-1])[0, 1])
    con_pearson = segmentar(y, s, k_ciudad, phi_pearson)["quiebres"]

    segmentos = []
    for i, lv in enumerate(seg["niveles"]):
        a, b = seg["limites"][i], seg["limites"][i + 1]
        segmentos.append({"desde": mes(a), "hasta": mes(b - 1), "meses": b - a, "nivel_desestacionalizado": lv,
                          "observado_promedio": float(y[a:b].mean()),
                          "cambio_vs_anterior": seg["cambios"][i - 1] if i else None})
    res["ciudad"] = {
        "meses": [mes(i) for i in range(n)], "observado": y.tolist(),
        "desestacionalizado": (y / s).round(1).tolist(), "ajustado": mu.round(1).tolist(),
        "factores_mes": f.round(4).tolist(), "phi_diferencias": seg["phi"],
        "phi_pearson_en_segmentos": phi_pearson, "autocorrelacion_residuos": ac1,
        "phi_modelo_tendencia_a02": phi_a02(),
        "k": k_ciudad, "beta": k_ciudad * np.log(n),
        "quiebres": [mes(c) for c in seg["quiebres"]], "segmentos": segmentos,
        "sensibilidad": {"por_k": por_k, "camino_beta": tramos,
                         "k_rango_por_quiebre": [{"mes": q, "intervalos": [{"k_min": a, "k_max": b} for a, b in iv],
                                                  "continuo": len(iv) == 1,
                                                  "en_todo_el_barrido": len(iv) == 1 and iv[0][0] <= tramos[0]["k_min"] + 1e-9
                                                  and iv[0][1] >= tramos[-1]["k_max"] - 1e-9}
                                                 for q, iv in sorted(rango_k.items())],
                         "k_barrido": [tramos[0]["k_min"], tramos[-1]["k_max"]],
                         "con_phi_pearson": [mes(c) for c in con_pearson],
                         "sin_desestacionalizar": [mes(c) for c in crudo["quiebres"]],
                         "costo_normal_anscombe": [mes(c) for c in cps_n]},
    }
    print(f"  ciudad: phi={seg['phi']:.2f} (Pearson en segmentos {phi_pearson:.2f}, autocorr {ac1:.2f}), k={k_ciudad} "
          f"quiebres {res['ciudad']['quiebres']}")
    for sg in segmentos:
        print(f"     {sg['desde']}..{sg['hasta']}  nivel {sg['nivel_desestacionalizado']:.0f}")
    print("  ciudad por k:", por_k)
    print("  ciudad sin desestacionalizar:", res["ciudad"]["sensibilidad"]["sin_desestacionalizar"],
          " normal:", res["ciudad"]["sensibilidad"]["costo_normal_anscombe"])
    return y, s, seg


# ======================================================== B. por agencia
def terciles(tamano, k=3):
    cortes = np.quantile(tamano, np.linspace(0, 1, k + 1)[1:-1])
    return np.digitize(tamano, cortes)


def observado(y):
    """Largo del tramo observado: las celdas faltantes (NaN) solo pueden estar al final."""
    ok = np.isfinite(y)
    n = int(ok.sum())
    assert ok[:n].all(), "celdas faltantes en medio de la serie"
    return n


def quiebres_panel(Y, s, k, phis=None):
    """PELT en cada fila (sobre su tramo observado). Devuelve lista de (unidad, t, cambio)."""
    out = []
    for i in range(Y.shape[0]):
        n = observado(Y[i])
        sg = segmentar(Y[i, :n], s[:n], k, None if phis is None else phis[i])
        for t, c in zip(sg["quiebres"], sg["cambios"]):
            out.append((i, t, c))
    return out


def estadistico_matriz(alza, entradas, ventana=VENTANA_E):
    """Proporcion de unidades con al menos un quiebre al alza con e = t - entrada en la ventana.

    alza es unidades x meses (bool); entradas es repeticiones x unidades.
    """
    T = alza.shape[1]
    t = np.arange(T)
    e = t[None, None, :] - entradas[:, :, None]
    en = (e >= ventana[0]) & (e <= ventana[1])
    return (en & alza[None]).any(2).mean(1)


def permutaciones(entrada, estrato, n_perm):
    perms = np.empty((n_perm, len(entrada)))
    for p in range(n_perm):
        ent = entrada.copy()
        for g in np.unique(estrato):
            idx = np.where(estrato == g)[0]
            ent[idx] = rng.permutation(entrada[idx])
        perms[p] = ent
    return perms


def matriz_quiebres(qs, n_u, T, signo=1, tope=np.inf):
    """Unidades x meses: quiebre con cambio del signo pedido (y |cambio| <= tope)."""
    A = np.zeros((n_u, T), bool)
    for i, t, c in qs:
        if c * signo > 0 and abs(c) <= tope:
            A[i, t] = True
    return A


def prueba(qs, entrada, estrato, n_u, T, n_perm, ventana=VENTANA_E, perms=None, signo=1, tope=np.inf, corrimiento=0):
    """Estadistico en la ventana y su p por permutacion. p = proporcion de nulas >= observado
    (como antes; con 10,000 permutaciones la diferencia con (b+1)/(N+1) es < 0.0001)."""
    alza = matriz_quiebres(qs, n_u, T, signo, tope)
    obs = estadistico_matriz(alza, entrada[None] + corrimiento, ventana)[0]
    if perms is None:
        perms = permutaciones(entrada, estrato, n_perm)
    nulas = estadistico_matriz(alza, perms + corrimiento, ventana)
    return float(obs), nulas, float((nulas >= obs - 1e-12).mean())


def diagnosticos_agencia(qs, qs_k, entrada, estrato, n_u, T, P, obs, k_ag, meses):
    """Placebo temporal, p por mes relativo, magnitudes, quiebres a la baja y Westfall-Young."""
    out = {}
    # placebo temporal: todas las fechas corridas delta meses, mismas permutaciones (05 M2)
    pt = {}
    for d in (-3, -2, -1, 0, 1, 2):
        o, nl, pv = prueba(qs, entrada, estrato, n_u, T, N_PERM, perms=P, corrimiento=d)
        pt[str(d)] = {"unidades": int(round(o * n_u)), "nula_media": float(nl.mean() * n_u), "p": pv}
    out["placebo_temporal"] = pt
    # por mes relativo, cada e por separado (05 M2, m1: e = -1 solo no es la ventana -1..+1)
    pe = {}
    for e in (-3, -2, -1, 0, 1, 2, 3):
        o, nl, pv = prueba(qs, entrada, estrato, n_u, T, N_PERM, (e, e), perms=P)
        pe[str(e)] = {"unidades": int(round(o * n_u)), "esperado": float(nl.mean() * n_u), "p": pv}
    out["por_e_separado"] = pe
    # magnitud de los escalones en la ventana y conteos acotados (05 M4)
    en_v = [(i, t, c) for i, t, c in qs if c > 0 and VENTANA_E[0] <= t - entrada[i] <= VENTANA_E[1]]
    mags = np.array([c for _, _, c in en_v])
    acot = {}
    for tope in (1.0, 0.6):
        o, nl, pv = prueba(qs, entrada, estrato, n_u, T, N_PERM, perms=P, tope=tope)
        acot[f"hasta_{int(tope*100)}pct"] = {"unidades": int(round(o * n_u)), "esperado": float(nl.mean() * n_u), "p": pv}
    out["magnitudes_en_ventana"] = {"n": int(len(mags)), "mediana": float(np.median(mags)) if len(mags) else None,
                                    "mayores_a_100pct": int((mags > 1.0).sum()),
                                    "valores": sorted([float(x) for x in mags], reverse=True), "acotado": acot}
    # quiebres a la baja en la ventana (05 m4)
    o, nl, pv = prueba(qs, entrada, estrato, n_u, T, N_PERM, perms=P, signo=-1)
    out["a_la_baja"] = {"unidades": int(round(o * n_u)), "esperado": float(nl.mean() * n_u), "p": pv}
    # Westfall-Young min-p sobre 4 ventanas x 9 k con las mismas permutaciones (05 M3)
    S_obs, S_null, nombres = [], [], []
    for k in K_REJILLA:
        A = matriz_quiebres(qs_k[k], n_u, T)
        for nombre, w in ESPECIFICACIONES_V:
            S_obs.append(estadistico_matriz(A, entrada[None], w)[0]); S_null.append(estadistico_matriz(A, P, w))
            nombres.append(f"k{k}_{nombre}")
    S_obs, S_null = np.array(S_obs), np.array(S_null)
    pobs = (S_null >= S_obs[:, None] - 1e-12).mean(1)
    # p de cada permutacion en cada especificacion (por rango)
    orden = np.sort(S_null, axis=1)
    rank_p = np.empty_like(S_null)
    for j in range(len(S_obs)):
        rank_p[j] = 1 - np.searchsorted(orden[j], S_null[j] - 1e-12, side="left") / S_null.shape[1]
    minp = rank_p.min(0)
    j0 = nombres.index(f"k{k_ag}_e0a1")
    out["westfall_young"] = {"especificaciones": len(nombres), "p_principal": float(pobs[j0]),
                             "p_principal_ajustado": float((minp <= pobs[j0] + 1e-12).mean()),
                             "mejor": nombres[int(np.argmin(pobs))], "p_mejor": float(pobs.min()),
                             "p_mejor_ajustado": float((minp <= pobs.min() + 1e-12).mean()),
                             "p_por_especificacion": dict(zip(nombres, pobs.round(5).tolist()))}
    print(f"         placebo temporal: { {k: (v['unidades'], round(v['p'], 3)) for k, v in pt.items()} }")
    print(f"         WY: principal {pobs[j0]:.4f} -> ajustado {out['westfall_young']['p_principal_ajustado']:.3f}; "
          f"<=100%: {acot['hasta_100pct']}; baja: {out['a_la_baja']}")
    return out


def por_agencia(k_ag, res):
    mat, unidades, meses, entrada, _, _ = cargar()
    T = len(meses)
    pre = np.array([x < C.LANZAMIENTO for x in meses])
    tamano = mat["total"][:, np.array([x.year == 2018 for x in meses])].sum(1)
    estrato = terciles(tamano)
    mes = lambda i: meses[i].isoformat()[:7]  # noqa: E731
    out = {"unidades": unidades, "meses": [mes(i) for i in range(T)],
           "entrada": [mes(int(e)) for e in entrada], "k": k_ag, "beta": k_ag * np.log(T),
           "ventana_e": list(VENTANA_E)}
    extra = {}
    for delito in ("vf", "robos"):
        Y = mat[delito]
        f = estacionalidad(np.nansum(Y, 0), meses, pre)
        s = f[[x.month - 1 for x in meses]]
        phis = np.array([dispersion(Y[i, :observado(Y[i])], s[:observado(Y[i])]) for i in range(len(unidades))])
        qs = quiebres_panel(Y, s, k_ag, phis)
        usar(f"permutaciones-{delito}")
        P = permutaciones(entrada, estrato, N_PERM)
        n_u = len(unidades)
        obs, nulas, p = prueba(qs, entrada, estrato, n_u, T, N_PERM, perms=P)
        # sensibilidad: otras ventanas y otras penalizaciones, con las MISMAS permutaciones
        sens_v = {}
        for nombre, v in ESPECIFICACIONES_V:
            o, nl, pv = prueba(qs, entrada, estrato, n_u, T, N_PERM, v, perms=P)
            sens_v[nombre] = {"observado": o, "nula_media": float(nl.mean()), "p": pv}
        o, nl, pv = prueba(qs, entrada, estrato, n_u, T, N_PERM, (-3, 3), perms=P)
        sens_v["e-3a3"] = {"observado": o, "nula_media": float(nl.mean()), "p": pv}
        sens_k, qs_k = {}, {}
        for k in K_REJILLA:
            q2 = quiebres_panel(Y, s, k, phis)
            qs_k[k] = q2
            o, nl, pv = prueba(q2, entrada, estrato, n_u, T, N_PERM, perms=P)
            sens_k[str(k)] = {"observado": o, "nula_media": float(nl.mean()), "p": pv,
                              "quiebres": len(q2), "al_alza": sum(c > 0 for _, _, c in q2)}
        extra_d = diagnosticos_agencia(qs, qs_k, entrada, estrato, n_u, T, P, obs, k_ag, meses)
        # distribuciones
        rel = {}
        cal = {mes(t): {"alza": 0, "baja": 0} for t in range(T)}
        for i, t, c in qs:
            e = int(t - entrada[i])
            rel.setdefault(e, {"alza": 0, "baja": 0})
            rel[e]["alza" if c > 0 else "baja"] += 1
            cal[mes(t)]["alza" if c > 0 else "baja"] += 1
        # lo que se esperaria por e si las llegadas fueran otras (media de la permutacion)
        alza = np.zeros((len(unidades), T), bool)
        for i, t, c in qs:
            if c > 0:
                alza[i, t] = True
        esperado_e = {}
        ii, tt = np.where(alza)
        for ent in P[:1000]:
            for e in (tt - ent[ii]).astype(int):
                esperado_e[int(e)] = esperado_e.get(int(e), 0) + 1 / 1000
        detalle = []
        for i, u in enumerate(unidades):
            mis = [(t, c) for j, t, c in qs if j == i]
            detalle.append({"unidad": u, "entrada": mes(int(entrada[i])), "phi": float(phis[i]),
                            "quiebres": [{"mes": mes(t), "e": int(t - entrada[i]), "cambio": float(c)} for t, c in mis]})
        cohortes = {}
        for e0 in sorted(set(entrada)):
            idx = np.where(entrada == e0)[0]
            con = sum(any(c > 0 and VENTANA_E[0] <= t - e0 <= VENTANA_E[1] for j, t, c in qs if j == i) for i in idx)
            cohortes[mes(int(e0))] = {"unidades": int(len(idx)), "con_quiebre_al_alza_en_llegada": int(con)}
        out[delito] = {
            "estadistico": obs, "unidades_con_quiebre_en_llegada": int(round(obs * len(unidades))),
            "nula_media": float(nulas.mean()), "nula_p95": float(np.percentile(nulas, 95)), "p": p,
            "nula_valores": np.round(nulas, 4).tolist(),
            "quiebres_totales": len(qs), "al_alza": sum(c > 0 for _, _, c in qs),
            "unidades_con_algun_quiebre": len({i for i, _, _ in qs}),
            "unidades_con_algun_quiebre_descripcion": "unidades con al menos un quiebre en CUALQUIER punto de la serie "
                                                      "2017-01 a 2020-02, no en la ventana de llegada",
            "n_perm": N_PERM, "p_ee_mc": float(np.sqrt(p * (1 - p) / N_PERM)), **extra_d,
            "phi_percentiles": dict(zip(["p10", "p50", "p90"], np.percentile(phis, [10, 50, 90]).tolist())),
            "factores_mes": f.round(4).tolist(),
            "por_e": [{"e": e, **rel[e], "esperado_alza": esperado_e.get(e, 0.0)} for e in sorted(rel)],
            "esperado_alza_por_e": {str(e): v for e, v in sorted(esperado_e.items())},
            "por_mes": [{"mes": m_, **v} for m_, v in cal.items()],
            "por_cohorte": cohortes, "sensibilidad_ventana": sens_v, "sensibilidad_k": sens_k,
            "detalle": detalle,
        }
        extra[delito] = {"phis": phis, "s": s, "Y": Y}
        top = sorted(cal.items(), key=lambda kv: -kv[1]["alza"])[:4]
        print(f"  {delito:6} quiebres {len(qs)} (al alza {out[delito]['al_alza']}) en {out[delito]['unidades_con_algun_quiebre']} unidades; "
              f"en llegada {obs:.3f} vs nula {nulas.mean():.3f}  p={p:.3f}; meses con mas alzas {[(a, b['alza']) for a, b in top]}")
        print(f"         por k: { {k: (round(v['observado'], 3), round(v['p'], 3)) for k, v in sens_k.items()} }")
        print(f"         por ventana: { {k: (round(v['observado'], 3), round(v['p'], 3)) for k, v in sens_v.items()} }")
    res["agencias"] = out
    return mat, meses, entrada, estrato, extra


# ============================================================ validacion
def val_exactitud():
    """PELT = DP sin poda = enumeracion completa."""
    out = {"pelt_vs_dp": {"series": 0, "mismo_optimo": 0, "mismos_quiebres": 0, "max_dif_costo": 0.0,
                          "evaluaciones_pelt": 0, "evaluaciones_dp": 0},
           "vs_enumeracion": {"series": 0, "mismo_optimo": 0, "mismos_quiebres": 0}}
    for r in range(400):
        n = int(rng.integers(20, 61))
        mu = np.full(n, rng.uniform(5, 60))
        for c in sorted(rng.choice(np.arange(4, n - 3), size=int(rng.integers(0, 4)), replace=False)):
            mu[c:] *= rng.uniform(0.6, 1.6)
        s = np.ones(n) if r % 2 else 1 + 0.15 * np.sin(np.arange(n) * 2 * np.pi / 12)
        y = simular(mu * s, rng.uniform(1, 3))
        m = int(rng.integers(1, 5))
        beta = rng.uniform(0.5, 4) * np.log(n)
        c = costo_poisson(y, s, rng.uniform(1, 3)) if r % 3 else costo_normal(np.sqrt(y), 0.25)
        a, Fa, ea = pelt(n, c, beta, m)
        b, Fb, eb = pelt(n, c, beta, m, podar=False)
        d = out["pelt_vs_dp"]
        d["series"] += 1
        d["mismo_optimo"] += abs(Fa - Fb) < 1e-8 * max(1, abs(Fb))
        d["mismos_quiebres"] += a == b
        d["max_dif_costo"] = max(d["max_dif_costo"], abs(Fa - Fb))
        d["evaluaciones_pelt"] += ea
        d["evaluaciones_dp"] += eb
    for r in range(200):
        n = int(rng.integers(6, 15))
        y = simular(np.where(np.arange(n) < n // 2, 10, rng.uniform(8, 25)), 1.5)
        m = int(rng.integers(1, 4))
        c = costo_poisson(y, np.ones(n), 1.5)
        beta = rng.uniform(0.5, 3) * np.log(n)
        a, Fa, _ = pelt(n, c, beta, m)
        b, Fb = exhaustiva(n, c, beta, m)
        d = out["vs_enumeracion"]
        d["series"] += 1
        d["mismo_optimo"] += abs(Fa - Fb) < 1e-8 * max(1, abs(Fb))
        d["mismos_quiebres"] += a == b
    d = out["pelt_vs_dp"]
    d["ahorro_evaluaciones"] = 1 - d["evaluaciones_pelt"] / d["evaluaciones_dp"]
    print(f"  exactitud: PELT=DP {d['mismo_optimo']}/{d['series']} (quiebres {d['mismos_quiebres']}), "
          f"ahorro {d['ahorro_evaluaciones']*100:.0f}%; enumeracion {out['vs_enumeracion']['mismo_optimo']}/{out['vs_enumeracion']['series']}")
    return out


def val_recuperacion(f_ciudad, nivel, phi, k):
    """Serie tipo ciudad con dos quiebres conocidos: ¿los encuentra en el mes correcto?"""
    n = 50
    s = f_ciudad[np.arange(n) % 12]
    exacto = cerca = n_ok = 0
    for _ in range(300):
        mu = np.full(n, nivel)
        mu[20:] *= 1.15
        mu[35:] *= 0.90
        y = simular(mu * s, phi)
        q = segmentar(y, s, k)["quiebres"]
        exacto += (20 in q) + (35 in q)
        cerca += any(abs(x - 20) <= 1 for x in q) + any(abs(x - 35) <= 1 for x in q)
        n_ok += len(q) == 2
    out = {"series": 300, "quiebres_verdaderos": ["t=20: +15%", "t=35: -10%"],
           "detectados_mes_exacto": exacto / 600, "detectados_mas_menos_1": cerca / 600,
           "numero_correcto_de_quiebres": n_ok / 300}
    print(f"  recuperacion (ciudad, +15% y -10%): exacto {out['detectados_mes_exacto']:.2f}, "
          f"+-1 {out['detectados_mas_menos_1']:.2f}, numero correcto {out['numero_correcto_de_quiebres']:.2f}")
    return out


def val_falsos_ciudad(f_ciudad, nivel, phi):
    n = 50
    s = f_ciudad[np.arange(n) % 12]
    tasas = {str(k): 0 for k in K_REJILLA}
    tasa_poisson_pura = tasa_cruda = 0
    for _ in range(N_NULA_CIUDAD):
        y = simular(nivel * s, phi)
        ph = dispersion(y, s)
        c = costo_poisson(y, s, ph)
        for k in K_REJILLA:
            tasas[str(k)] += len(pelt(n, c, k * np.log(n))[0]) > 0
        tasa_poisson_pura += len(pelt(n, costo_poisson(y, s, 1.0), 2 * np.log(n))[0]) > 0
        tasa_cruda += len(pelt(n, costo_poisson(y, np.ones(n), dispersion(y, np.ones(n))), 2 * np.log(n))[0]) > 0
    out = {"series": N_NULA_CIUDAD, "nivel": nivel, "phi_simulada": phi,
           "tasa_con_algun_quiebre_por_k": {k: v / N_NULA_CIUDAD for k, v in tasas.items()},
           "tasa_k2_sin_escalar_por_phi": tasa_poisson_pura / N_NULA_CIUDAD,
           "tasa_k2_sin_desestacionalizar": tasa_cruda / N_NULA_CIUDAD}
    print(f"  falsos (ciudad): {out['tasa_con_algun_quiebre_por_k']}; sin phi {out['tasa_k2_sin_escalar_por_phi']:.2f}; "
          f"sin estacionalidad {out['tasa_k2_sin_desestacionalizar']:.2f}")
    return out


def niveles_previos(Y, s, pre):
    return (Y[:, pre] / s[None, pre]).mean(1)


def val_falsos_agencias(Y, s, pre, phis):
    """Paneles de agencias sin quiebre (las de A02), cada una con su nivel y su phi."""
    mu = niveles_previos(Y, s, pre)
    T = Y.shape[1]
    tasas = {str(k): 0 for k in K_REJILLA}
    quiebres_por_serie = {str(k): 0 for k in K_REJILLA}
    total = 0
    for _ in range(N_NULA_PANEL):
        for i in range(Y.shape[0]):
            y = simular(mu[i] * s, phis[i])
            ph = dispersion(y, s)
            c = costo_poisson(y, s, ph)
            total += 1
            for k in K_REJILLA:
                q = pelt(T, c, k * np.log(T))[0]
                tasas[str(k)] += len(q) > 0
                quiebres_por_serie[str(k)] += len(q)
    out = {"series": total, "tasa_con_algun_quiebre_por_k": {k: v / total for k, v in tasas.items()},
           "quiebres_por_serie_por_k": {k: v / total for k, v in quiebres_por_serie.items()}}
    print(f"  falsos (agencias): {out['tasa_con_algun_quiebre_por_k']}")
    return out


def val_falsos_escenarios(Y, s, pre, phis, meses, paneles=40, ks=(2.5, 3.0)):
    """Falsos positivos cuando el nulo no es i.i.d. (auditoria 05 m2): nivel latente AR(1)
    (rho 0.6, DE 10%), tendencia suave de +-8% al año y estacionalidad propia por agencia (DE 8%)."""
    mu = niveles_previos(Y, s, pre)
    T = Y.shape[1]
    out = {}
    for nombre in ("iid", "ar1_latente", "tendencia_8pct_anual", "estacionalidad_propia"):
        cuenta = {str(k): 0 for k in ks}
        n = 0
        for _ in range(paneles):
            for i in range(Y.shape[0]):
                m = mu[i] * s.copy()
                if nombre == "ar1_latente":
                    e = np.zeros(T); sd = 0.10
                    for t in range(T):
                        e[t] = (0.6 * e[t - 1] if t else 0) + rng.normal(0, sd * np.sqrt(1 - 0.36))
                    m = m * np.exp(e - sd ** 2 / 2)
                elif nombre == "tendencia_8pct_anual":
                    m = m * np.exp(rng.choice([-1, 1]) * 0.08 * np.arange(T) / 12)
                elif nombre == "estacionalidad_propia":
                    pert = np.exp(rng.normal(0, 0.08, 12)); pert /= pert.mean()
                    m = m * pert[[x.month - 1 for x in meses]]
                y = simular(m, phis[i])
                c = costo_poisson(y, s, dispersion(y, s))
                n += 1
                for k in ks:
                    cuenta[str(k)] += len(pelt(T, c, k * np.log(T))[0]) > 0
        out[nombre] = {"series": n, "tasa_por_k": {k: v / n for k, v in cuenta.items()}}
    print("  falsos por escenario:", {k: v["tasa_por_k"] for k, v in out.items()})
    return out


def elegir_k(tasas):
    for k in K_REJILLA:
        if tasas[str(k)] <= FP_OBJETIVO:
            return k
    return K_REJILLA[-1]


def val_potencia_agencia(Y, s, pre, phis, k):
    """Series del tamaño de una agencia, con un salto en marzo de 2019 (t = 26)."""
    mu_all = niveles_previos(Y, s, pre)
    T = Y.shape[1]
    t0 = 26
    phi = float(np.median(phis))
    out = {"t_salto": t0, "phi": phi, "k": k, "niveles": {}}
    for nombre, mu in (("chica_p25", np.percentile(mu_all, 25)), ("tipica_mediana", np.median(mu_all)),
                       ("grande_p75", np.percentile(mu_all, 75))):
        fila = {"nivel": float(mu), "saltos": {}}
        for r in SALTOS:
            det = cerca = alguno = 0
            errores = []
            for _ in range(N_POT):
                m_ = np.full(T, mu)
                m_[t0:] *= 1 + r
                y = simular(m_ * s, phi)
                sg = segmentar(y, s, k)
                alguno += len(sg["quiebres"]) > 0
                arriba = [t for t, c in zip(sg["quiebres"], sg["cambios"]) if c > 0]
                if arriba:
                    t_ = min(arriba, key=lambda x: abs(x - t0))
                    det += 1
                    errores.append(abs(t_ - t0))
                    cerca += abs(t_ - t0) <= 1
            fila["saltos"][str(r)] = {"detecta_al_alza": det / N_POT, "detecta_en_mas_menos_1": cerca / N_POT,
                                      "algun_quiebre": alguno / N_POT,
                                      "error_mediano_meses": float(np.median(errores)) if errores else None,
                                      "exacto_entre_detectados": float(np.mean(np.array(errores) == 0)) if errores else None}
        out["niveles"][nombre] = fila
        print(f"  potencia {nombre} (nivel {mu:.1f}/mes): " +
              ", ".join(f"{int(r*100)}%: {v['detecta_en_mas_menos_1']:.2f}" for r, v in zip(SALTOS, fila["saltos"].values())))
    return out


def val_prueba_panel(Y, s, pre, phis, entrada, estrato, k):
    """Potencia y tamaño de la prueba por agencia, con el calendario real.

    Escenarios: sin efecto; efecto del programa de +28% y +45% en el mes de llegada
    de cada agencia; y un choque COMUN de +28% en marzo de 2019 para todas, que es lo
    que la prueba NO deberia confundir con el programa.
    """
    mu = niveles_previos(Y, s, pre)
    n_u, T = Y.shape
    t = np.arange(T)
    esc = {"sin_efecto": lambda: np.ones((n_u, T)),
           "programa_28": lambda: np.where(t[None] >= entrada[:, None], 1.28, 1.0),
           "programa_45": lambda: np.where(t[None] >= entrada[:, None], 1.45, 1.0),
           "choque_comun_28_marzo_2019": lambda: np.where(t[None] >= 26, 1.28, 1.0) * np.ones((n_u, 1)),
           # nulos adicionales (auditoria 05 m5) y un programa real que empieza un mes antes de la fecha registrada (M2)
           "choque_comun_28_mayo_2019": lambda: np.where(t[None] >= 28, 1.28, 1.0) * np.ones((n_u, 1)),
           "choque_comun_rampa_mar_jun_2019": lambda: np.clip(1 + 0.28 * (t - 25) / 4, 1, 1.28)[None] * np.ones((n_u, 1)),
           "choque_comun_28_marzo_2019_solo_tercil_grande": lambda: np.where((t[None] >= 26) & (estrato[:, None] == 2), 1.28, 1.0),
           "programa_28_un_mes_antes_de_la_fecha": lambda: np.where(t[None] >= entrada[:, None] - 1, 1.28, 1.0)}
    out = {}
    for nombre, g in esc.items():
        ps, stats = [], []
        for _ in range(N_PANEL_POT):
            M = g() * mu[:, None] * s[None]
            Ysim = np.vstack([simular(M[i], phis[i]) for i in range(n_u)])
            qs = quiebres_panel(Ysim, s, k)
            o, _, p = prueba(qs, entrada, estrato, n_u, T, N_PERM_SIM)
            ps.append(p)
            stats.append(o)
        ps = np.array(ps)
        out[nombre] = {"rechaza_al_5": float((ps <= 0.05).mean()), "rechaza_al_10": float((ps <= 0.10).mean()),
                       "estadistico_medio": float(np.mean(stats)), "paneles": N_PANEL_POT}
        print(f"  prueba por agencia [{nombre}]: rechaza al 5% {out[nombre]['rechaza_al_5']:.2f}, "
              f"estadistico medio {out[nombre]['estadistico_medio']:.3f}")
    return out


# ================================================================ figuras
def figuras(res):
    cz = res["ciudad"]
    x = [dt.date.fromisoformat(m + "-01") for m in cz["meses"]]
    fig, ax = plt.subplots(figsize=(11, 4.4))
    ax.plot(x, cz["observado"], color=BLUE_LIGHT, lw=1.2, label="Observado")
    ax.plot(x, cz["desestacionalizado"], color=BLUE, lw=1.6, marker="o", ms=3, label="Sin estacionalidad")
    for sg in cz["segmentos"]:
        a = dt.date.fromisoformat(sg["desde"] + "-01")
        b = dt.date.fromisoformat(sg["hasta"] + "-01")
        b = dt.date(b.year + (b.month == 12), b.month % 12 + 1, 1)
        ax.plot([a, b], [sg["nivel_desestacionalizado"]] * 2, color=BLUE_DARK, lw=3, solid_capstyle="butt")
    for q in cz["quiebres"]:
        ax.axvline(dt.date.fromisoformat(q + "-01"), color="#666", ls=":", lw=1)
    ax.axvline(C.LANZAMIENTO, color=RED, ls="--", lw=1.2)
    ax.text(C.LANZAMIENTO, ax.get_ylim()[1] * 0.99, "  llegan las abogadas (mar-2019)", color=RED, fontsize=9, va="top")
    ax.plot([], [], color=BLUE_DARK, lw=3, label="Nivel de cada segmento (PELT)")
    miles(ax)
    ax.set_ylabel("Carpetas de violencia familiar por mes")
    ax.set_title("En la ciudad, el nivel sube por escalones a lo largo de 2019, no de un solo golpe", fontweight="bold")
    ax.legend(loc="upper left", framealpha=0.8)
    guardar(fig, CARPETA, "01_ciudad_segmentos", "Fuente: FGJ CDMX, agencias territoriales. "
            f"PELT, costo Poisson con factores de mes previos al programa, phi = {cz['phi_diferencias']:.2f}, "
            f"beta = {cz['k']:g} log(n).")

    # 2. camino de la penalizacion para la ciudad
    tr = cz["sensibilidad"]["camino_beta"]
    fig, ax = plt.subplots(figsize=(10, 4.2))
    for t_ in tr:
        for q in t_["quiebres"]:
            yq = dt.date.fromisoformat(q + "-01")
            ax.plot([t_["k_min"], t_["k_max"]], [yq, yq], color=BLUE, lw=4, solid_capstyle="butt")
    ax.axvline(cz["k"], color=RED, lw=1.2, ls="--")
    ax.text(cz["k"], ax.get_ylim()[1], f"  k elegido = {cz['k']:g}", color=RED, fontsize=9, va="top")
    ax.axhline(C.LANZAMIENTO, color="#888", lw=0.8, ls=":")
    ax.set_xscale("log")
    ax.set_xlabel("Penalización por quiebre, en múltiplos de log(n)  (β = k · log n)")
    ax.set_ylabel("Mes del quiebre")
    ax.set_title("Qué quiebres sobreviven al subir la penalización", fontweight="bold")
    guardar(fig, CARPETA, "02_ciudad_penalizacion", "Cada barra: rango de penalización en que PELT marca ese mes. "
            "Línea punteada: marzo de 2019.")

    # 3. quiebres por agencia en tiempo relativo y en calendario
    ag = res["agencias"]
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.3))
    for ax, delito, titulo in ((axs[0], "vf", "Violencia familiar"), (axs[1], "robos", "Robos (placebo)")):
        d = ag[delito]
        es = list(range(-26, 12))
        obs = [next((r["alza"] for r in d["por_e"] if r["e"] == e), 0) for e in es]
        esp = [d["esperado_alza_por_e"].get(str(e), 0) for e in es]
        cols = [RED if VENTANA_E[0] <= e <= VENTANA_E[1] else BLUE for e in es]
        ax.bar(es, obs, color=cols, edgecolor="#000", linewidth=0.3, label="Quiebres al alza observados")
        ax.step(es, esp, where="mid", color="#000", lw=1, label="Esperado si las llegadas fueran otras")
        ax.axvline(-0.5, color="#666", ls="--", lw=1)
        ax.set_xlabel("Meses desde la llegada del programa a la agencia (e)")
        ax.set_title(f"{titulo}: p = {d['p']:.3f}", fontweight="bold")
    axs[0].set_ylabel("Agencias con quiebre al alza")
    axs[0].legend(loc="upper left", framealpha=0.8, fontsize=8)
    guardar(fig, CARPETA, "03_quiebres_tiempo_relativo", NOTA + " En rojo: e = 0 y e = +1.")

    fig, ax = plt.subplots(figsize=(11, 4.0))
    xm = [dt.date.fromisoformat(r["mes"] + "-01") for r in ag["vf"]["por_mes"]]
    al = [r["alza"] for r in ag["vf"]["por_mes"]]
    ba = [-r["baja"] for r in ag["vf"]["por_mes"]]
    ax.bar(xm, al, width=25, color=BLUE, label="Al alza")
    ax.bar(xm, ba, width=25, color=BLUE_LIGHT, label="A la baja")
    ax.axhline(0, color="#000", lw=0.8)
    ax.axvline(C.LANZAMIENTO, color=RED, ls="--", lw=1.2)
    ax.set_ylabel("Agencias con quiebre ese mes")
    ax.set_title("Violencia familiar: en qué mes calendario cambian de nivel las agencias", fontweight="bold")
    ax.legend(loc="upper left", framealpha=0.8)
    guardar(fig, CARPETA, "04_quiebres_por_mes", NOTA)

    # 5. permutacion
    fig, axs = plt.subplots(1, 2, figsize=(12, 3.8), sharey=True)
    for ax, delito, titulo in ((axs[0], "vf", "Violencia familiar"), (axs[1], "robos", "Robos (placebo)")):
        d = ag[delito]
        nul = np.array(d["nula_valores"]) * 100
        n_u = len(ag["unidades"])
        bordes = (np.arange(-0.5, 20.5) / n_u) * 100          # una barra por numero de agencias
        ax.hist(nul, bins=bordes, color=BLUE, edgecolor="#000", linewidth=0.3)
        ax.axvline(d["estadistico"] * 100, color=RED, lw=2,
                   label=f"Observado: {d['unidades_con_quiebre_en_llegada']} de {n_u} (p = {d['p']:.3f})")
        ax.set_xlim(-2, 36)
        ax.set_xlabel("% de agencias con quiebre al alza en e = 0 o +1")
        ax.set_title(titulo, fontweight="bold")
        ax.legend(loc="upper right", framealpha=0.8, fontsize=8)
    axs[0].set_ylabel("Repeticiones")
    guardar(fig, CARPETA, "05_permutacion", f"Fechas de llegada permutadas dentro de terciles de tamaño ({N_PERM:,} veces).")

    # 6. validacion: falsos positivos y potencia
    v = res["validacion"]
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.0))
    ax = axs[0]
    ks = K_REJILLA
    ax.plot(ks, [v["falsos_agencias"]["tasa_con_algun_quiebre_por_k"][str(k)] * 100 for k in ks], "o-", color=BLUE, label="Serie de agencia (38 meses)")
    ax.plot(ks, [v["falsos_ciudad"]["tasa_con_algun_quiebre_por_k"][str(k)] * 100 for k in ks], "s-", color=BLUE_DARK, label="Serie de la ciudad (50 meses)")
    ax.axhline(FP_OBJETIVO * 100, color=RED, ls="--", lw=1)
    ax.set_xlabel("k  (β = k · log n)"); ax.set_ylabel("Series sin quiebre que marcan alguno"); pct(ax)
    ax.set_title("Quiebres espurios según la penalización", fontweight="bold")
    ax.legend(framealpha=0.8, fontsize=8)
    ax = axs[1]
    for nombre, c in (("chica_p25", BLUE_LIGHT), ("tipica_mediana", BLUE), ("grande_p75", BLUE_DARK)):
        fila = v["potencia_agencia"]["niveles"][nombre]
        ax.plot([r * 100 for r in SALTOS], [fila["saltos"][str(r)]["detecta_en_mas_menos_1"] * 100 for r in SALTOS],
                "o-", color=c, label=f"{fila['nivel']:.0f} carpetas/mes")
    ax.axhline(80, color="#888", ls=":", lw=1)
    ax.axvline(28, color=RED, ls="--", lw=1)
    ax.text(28, 90, " +28% (A02)", color=RED, fontsize=8)
    ax.set_xlabel("Salto verdadero en marzo de 2019"); ax.set_ylabel("Lo detecta en el mes correcto (±1 mes)"); pct(ax)
    ax.set_ylim(0, 100)
    ax.set_title("Por agencia, PELT casi no ve saltos del tamaño estimado", fontweight="bold")
    ax.legend(framealpha=0.8, fontsize=8, title="Agencia de", title_fontsize=8)
    guardar(fig, CARPETA, "06_validacion", "Simulación Poisson-gamma con la estacionalidad, nivel y sobredispersión reales.")


# ================================================================== main
def main():
    print("A05 quiebres (PELT)")
    res = {"metodo": {
        "algoritmo": "PELT (Killick, Fearnhead y Eckley 2012, JASA 107(500):1590-1598)",
        "costo": "devianza Poisson con factores de mes previos al programa como desplazamiento, dividida entre phi",
        "penalizacion": "beta = k log(n); k = menor valor de la rejilla con <= 5% de series nulas con algun quiebre",
        "min_segmento": MIN_SEG, "rejilla_k": K_REJILLA, "fp_objetivo": FP_OBJETIVO, "semilla": SEMILLA}}
    usar("exactitud")
    val = {"exactitud": val_exactitud()}

    # calibracion ANTES de mirar los quiebres reales
    y, meses_c = serie_ciudad()
    pre_c = np.array([x < C.LANZAMIENTO for x in meses_c])
    f_c = estacionalidad(y, meses_c, pre_c)
    s_c = f_c[[x.month - 1 for x in meses_c]]
    phi_c = dispersion(y, s_c)
    nivel_c = float((y[pre_c] / s_c[pre_c]).mean())
    usar("falsos-ciudad")
    val["falsos_ciudad"] = val_falsos_ciudad(f_c, nivel_c, phi_c)
    usar("falsos-ciudad-phi-a02")
    val["falsos_ciudad_phi_3_9"] = val_falsos_ciudad(f_c, nivel_c, phi_a02())   # llave vieja: es el phi de A02
    k_ciudad = elegir_k(val["falsos_ciudad"]["tasa_con_algun_quiebre_por_k"])

    mat, _, meses, entrada, _, _ = cargar()
    pre = np.array([x < C.LANZAMIENTO for x in meses])
    tamano = mat["total"][:, np.array([x.year == 2018 for x in meses])].sum(1)
    estrato = terciles(tamano)
    Yv = mat["vf"]
    s_v = estacionalidad(np.nansum(Yv, 0), meses, pre)[[x.month - 1 for x in meses]]
    phis_v = np.array([dispersion(Yv[i, :observado(Yv[i])], s_v[:observado(Yv[i])]) for i in range(Yv.shape[0])])
    usar("falsos-agencias")
    val["falsos_agencias"] = val_falsos_agencias(Yv, s_v, pre, phis_v)
    k_ag = elegir_k(val["falsos_agencias"]["tasa_con_algun_quiebre_por_k"])
    res["metodo"]["k_ciudad"], res["metodo"]["k_agencias"] = k_ciudad, k_ag
    print(f"  k elegido: ciudad {k_ciudad}, agencias {k_ag}")

    usar("falsos-escenarios")
    val["falsos_agencias_escenarios"] = val_falsos_escenarios(Yv, s_v, pre, phis_v, meses)
    usar("recuperacion")
    val["recuperacion_ciudad"] = val_recuperacion(f_c, nivel_c, phi_c, k_ciudad)
    usar("potencia-agencia")
    val["potencia_agencia"] = val_potencia_agencia(Yv, s_v, pre, phis_v, k_ag)
    usar("prueba-panel")
    val["prueba_por_agencia"] = val_prueba_panel(Yv, s_v, pre, phis_v, entrada, estrato, k_ag)
    res["validacion"] = val

    usar("ciudad")
    ciudad(k_ciudad, res)
    por_agencia(k_ag, res)
    figuras(res)
    C.guardar_json(res, CARPETA)


if __name__ == "__main__":
    main()
