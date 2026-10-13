"""A02 - ¿Aumentaron las carpetas de violencia familiar cuando llegaron las abogadas?

Diseño: adopcion escalonada. Las 57 unidades territoriales entraron entre marzo y
agosto de 2019 y ninguna se quedo sin programa, asi que la unica comparacion
valida es contra las que TODAVIA no lo tenian. Eso se hace con el estimador por
imputacion (Borusyak, Jaravel y Spiess 2024), version Poisson (la version no lineal
de Wooldridge 2023):

  1. Con las celdas agencia-mes SIN programa se ajusta E[Y] = a_agencia * b_mes.
  2. Para cada celda CON programa se imputa el contrafactual a_i * b_t.
  3. Efecto = sum(observado) / sum(contrafactual) - 1.

Un mes solo sirve si quedan al menos 5 unidades sin programa (C.MIN_SIN_PROGRAMA).

Muestra. Se excluyen las unidades cuyos codigos no son estables ANTES de su entrada:
algun mes sin ninguna carpeta, o un salto de mas de 2.5 veces en la media movil de 6
meses del total de carpetas. La regla solo mira meses previos a la entrada, para no
seleccionar la muestra con informacion posterior al tratamiento. Despues de la entrada,
un mes en que la Fiscalia no registra NINGUNA carpeta (de ningun delito) en la unidad
se marca como faltante y no como cero: el codigo dejo de usarse (IZP-7 desde sep-2019,
mientras el programa sigue reportando carpetas con esa etiqueta; auditoria/01_datos.md
M1). La evidencia viene del lado de la Fiscalia (total de carpetas = 0), no del resultado.

Inferencia:
  - aleatorizacion: las fechas de entrada reales se reparten entre unidades de tamaño
    parecido (terciles de carpetas de 2018), 5,000 veces;
  - intervalo por inversion de esa prueba (supone efecto multiplicativo constante);
  - bootstrap por unidad (2,000 remuestras) y jackknife por unidad.

Pruebas del diseño: adelantos, prueba conjunta de tendencias previas, placebos en el
tiempo (lanzamientos ficticios), placebos de resultado, contraste de los controles.

Cambios por la auditoria (2026-09-21):
  - Regla de exclusion con meses previos a la entrada como principal (54 unidades); la
    regla de toda la ventana (52 unidades) se guarda completa en `regla_exclusion_ventana_completa`
    (auditoria/01_datos.md M2, 02_efecto.md).
  - Celdas faltantes cuando la Fiscalia no registra ninguna carpeta despues de la entrada;
    se guardan cuantas y cuales (`celdas_faltantes`) y el efecto sin marcarlas (01 M1).
  - Adelantos con la misma regla de >= 5 unidades de comparacion por mes (02 M1); la version
    sin regla se guarda como `adelantos_sin_regla_minima`.
  - Prueba conjunta de tendencias previas de BJS en version Poisson, Wald agrupado por unidad
    y por permutacion (02 M2), y 18 placebos en el tiempo para VF, robos y resto de delitos (02 M2, M3).
  - p de permutacion como (b+1)/(N+1) con error Monte Carlo, 5,000 sorteos, y sensibilidad a
    1, 3, 4, 6 y 9 estratos (02 M4, m1, m9).
  - Intervalo por inversion de la permutacion y jackknife por unidad (02 M6).
  - Bootstrap: cuantas replicas pierden un mes identificado y el intervalo sin ellas (02 M5).
  - Contraste de las agencias aun sin programa en mar-may 2019 y efecto por mes calendario (02 M7).
  - Un generador aleatorio por procedimiento (02 m10).
  - Ciudad: intervalo del exceso con la incertidumbre de la tendencia (metodo delta) y
    variantes de especificacion (02 m6).
  - phi del modelo de imputacion por agencia (2.40 en VF con 52 unidades) y error del pulso
    mensual escalado por phi (02 m2, m3).
  - Efecto de la cohorte de marzo por mes calendario (02 m4) y ventanas de entrenamiento (02 M3).
  - Cuantas unidades de la muestra cambian de fecha con el umbral de 10 atenciones (01 m10).

Salidas: grafs/abogadas/02_efecto/
"""
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comun as C  # noqa: E402
from _viz import BLUE, BLUE_DARK, BLUE_LIGHT, BLUE_PALE, RED, guardar, miles, pct  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

CARPETA = "abogadas/02_efecto"
VENTANA_INI = C.PANEL_INI
VENTANA_FIN = C.PRE_COVID_FIN
SEMILLA = 20190304                      # fecha de lanzamiento del programa
N_PERM = 5000
N_BOOT = 2000
N_INVERSION = 2000
N_PERM_BJS = 1000
N_PERM_PLACEBO = 1000
LEADS = 6
ESTRATOS = (1, 3, 4, 6, 9)
REGLA_PRINCIPAL = "previos"             # "previos" (solo meses antes de la entrada) o "ventana_completa"
DELITOS = ("vf", "robos", "amenazas", "sexuales")


def meses_idx(fechas, mes0):
    return np.array([(f.year - mes0.year) * 12 + f.month - mes0.month for f in fechas], dtype=float)


def cargar(regla=REGLA_PRINCIPAL, detalle=False, marcar_faltantes=True):
    """Panel unidad x mes de la ventana del analisis, con la regla de muestra.

    regla="previos": la regla de estabilidad solo mira meses anteriores a la entrada.
    regla="ventana_completa": la regla original, que mira toda la ventana ene-2017 a feb-2020.
    marcar_faltantes: despues de la entrada, un mes sin ninguna carpeta de la Fiscalia es NaN.
    """
    p = pl.read_parquet(C.INTERIM / "panel.parquet").filter(pl.col("mes").is_between(VENTANA_INI, VENTANA_FIN))
    meses = sorted(p["mes"].unique().to_list())
    q = p.sort("unidad", "mes")
    if regla == "previos":
        q = q.filter(pl.col("mes") < pl.col("entrada"))
    elif regla != "ventana_completa":
        raise ValueError(regla)
    est = (q.with_columns(pl.col("total").cast(pl.Float64).rolling_mean(6).over("unidad").alias("m6"))
           .group_by("unidad").agg((pl.col("total") == 0).sum().alias("meses_cero"),
                                   (pl.col("m6").max() / pl.col("m6").min()).alias("salto"),
                                   pl.col("entrada").first()))
    fuera = est.filter((pl.col("meses_cero") > 0) | (pl.col("salto") > 2.5) | (pl.col("entrada") > VENTANA_FIN))
    dentro = est.join(fuera.select("unidad"), on="unidad", how="anti")
    p = p.join(dentro.select("unidad"), on="unidad").sort("unidad", "mes")
    conteos = ("vf", "robos", "amenazas", "sexuales", "total")
    faltan = p.filter(pl.col("fgj_sin_registro") & (pl.col("mes") >= pl.col("entrada")))
    if marcar_faltantes:
        p = p.with_columns([pl.when(pl.col("fgj_sin_registro") & (pl.col("mes") >= pl.col("entrada")))
                            .then(None).otherwise(pl.col(k)).cast(pl.Float64).alias(k) for k in conteos])
    unidades = sorted(p["unidad"].unique().to_list())
    info = p.group_by("unidad").agg(pl.col("entrada").first(), pl.col("entrada_10").first()).sort("unidad")
    mat = {k: p.pivot(on="mes", index="unidad", values=k).sort("unidad").drop("unidad").to_numpy().astype(float)
           for k in conteos + ("atenciones",)}
    salida = (mat, unidades, meses, meses_idx(info["entrada"].to_list(), meses[0]),
              meses_idx(info["entrada_10"].to_list(), meses[0]), fuera.sort("unidad").to_dicts())
    if not detalle:
        return salida
    d = {"regla": regla, "marcar_faltantes": marcar_faltantes,
         "celdas_faltantes": {"n": faltan.height if marcar_faltantes else 0,
                              "celdas": faltan.select("unidad", pl.col("mes").dt.strftime("%Y-%m")).to_dicts()
                              if marcar_faltantes else [],
                              "regla": "despues de la entrada, unidad-mes sin ninguna carpeta de la Fiscalia "
                                       "(de ningun delito): el codigo no esta en uso; se trata como faltante"}}
    return salida + (d,)


def estimar(Y, entrada, meses_ok):
    Yhat, trat = C.imputar(Y, entrada, meses_ok)
    return C.razon(Y, Yhat, trat), Yhat, trat


def por_evento(Y, Yhat, trat, entrada):
    T = Y.shape[1]
    e = np.arange(T)[None, :] - entrada[:, None]
    out = []
    for k in sorted(set(e[trat].astype(int))):
        c = trat & (e == k)
        out.append({"e": int(k), "efecto": C.razon(Y, Yhat, c), "celdas": int(c.sum()),
                    "observado": float(Y[c].sum()), "contrafactual": float(Yhat[c].sum())})
    return out


def adelantos(Y, entrada, minimo=C.MIN_SIN_PROGRAMA):
    """Se esconden los LEADS meses previos a la entrada y se imputan como si fueran tratados.

    Un mes oculto solo se usa si su pulso b_t lo sostienen al menos `minimo` unidades de
    entrenamiento, la misma regla del estimador principal (auditoria 02 M1). Sin la regla,
    los meses -2 y -3 salian de 1 o 2 agencias.
    """
    T = Y.shape[1]
    e = np.arange(T)[None, :] - entrada[:, None]
    obs = np.isfinite(Y)
    ocultas = (e >= -LEADS) & (e < 0) & obs
    W = (e < 0) & ~ocultas & obs
    n_train = W.sum(0)
    a, b = C.ajustar_poisson(np.where(obs, Y, 0.0), W)
    Yhat = a[:, None] * b[None, :]
    ok = (n_train >= minimo)[None, :]
    out = []
    for k in range(-LEADS, 0):
        c = ocultas & (e == k) & np.isfinite(Yhat) & ok
        out.append({"e": k, "efecto": C.razon(Y, Yhat, c) if c.any() else None, "celdas": int(c.sum())})
    c = ocultas & np.isfinite(Yhat) & ok
    return out, C.razon(Y, Yhat, c), int(c.sum())


def phi_imputacion(Y, entrada):
    """Sobredispersion de Pearson del modelo de imputacion en las celdas de entrenamiento.

    Es el phi relevante para el efecto (auditoria 02 m2): sum (y - mu)^2 / mu entre
    (celdas - parametros), con parametros = unidades + meses con entrenamiento - 1.
    """
    T = Y.shape[1]
    W = (np.arange(T)[None, :] < entrada[:, None]) & np.isfinite(Y)
    a, b = C.ajustar_poisson(np.where(W, Y, 0.0), W)
    mu = (a[:, None] * b[None, :])[W]
    y = Y[W]
    y, mu = y[mu > 0], mu[mu > 0]           # unidades sin ningun caso en entrenamiento (delitos sexuales)
    k = int(W.any(1).sum() + W.any(0).sum() - 1)
    return {"phi": float(((y - mu) ** 2 / mu).sum() / (W.sum() - k)), "celdas": int(W.sum()), "parametros": k,
            "definicion": "Pearson del Poisson a_i*b_t en las celdas sin programa, entre celdas menos parametros"}


def metodologia(Y, entrada, meses_ok, unidades, meses, phi, ejemplo="VC-3", ventana=6):
    """Las piezas del estimador, una por una, para la pagina que lo explica.

    No es un resultado nuevo: son los numeros intermedios del mismo ajuste
    (el nivel de una agencia, el pulso de cada mes, la convergencia del IPF y
    cuantas agencias sostienen cada mes). Viven aqui para que la pagina
    /metodologia no escriba ninguna cifra a mano. Solo el producto a*b esta
    identificado; a y b por separado dependen de la normalizacion (b arranca en 1).
    """
    T = Y.shape[1]
    obs = np.isfinite(Y)
    sin = (np.arange(T)[None, :] < entrada[:, None])
    Y0 = np.where(obs, Y, 0.0)
    a, b = C.ajustar_poisson(Y0, sin & obs)
    i = unidades.index(ejemplo)
    j = int(entrada[i])

    iteraciones = []
    for k in (1, 2, 3, 5, 10, 50):
        ak, bk = C.ajustar_poisson(Y0, sin & obs, iters=k)
        iteraciones.append({"iteracion": k, "a": float(ak[i]), "b": float(bk[j]),
                            "contrafactual": float(ak[i] * bk[j])})

    serie = [{"mes": meses[t].isoformat()[:7], "observado": int(Y[i, t]),
              "contrafactual": float(a[i] * b[t]), "b": float(b[t]),
              "programa": bool(t >= j)}
             for t in range(max(0, j - ventana), min(T, j + 3))]

    identificacion = []
    for t in range(T):
        if meses[t] < C.LANZAMIENTO:
            continue
        u = sin[:, t] & obs[:, t]
        n = int(u.sum())
        carpetas = float(Y[u, t].sum())
        identificacion.append({
            "mes": meses[t].isoformat()[:7], "unidades_sin_programa": n, "carpetas": carpetas,
            "ee_log_b": float(1 / np.sqrt(carpetas)) if carpetas > 0 else None,
            # con la sobredispersion del modelo de imputacion (auditoria 02 m3)
            "ee_log_b_cuasi": float(np.sqrt(phi / carpetas)) if carpetas > 0 else None,
            "identificado": bool(meses_ok[t] and n >= C.MIN_SIN_PROGRAMA),
        })

    return {"ejemplo": {"unidad": ejemplo, "a": float(a[i]),
                        "entrada": meses[j].isoformat()[:7], "serie": serie,
                        "iteraciones": iteraciones},
            "identificacion": identificacion,
            "minimo_sin_programa": C.MIN_SIN_PROGRAMA,
            "celdas_entrenamiento": int((sin & obs).sum()),
            "phi_imputacion": phi,
            "unidades": len(unidades), "meses": T}


# ---------------------------------------------------------------- permutacion
def estratos_de(tamano, n):
    if n <= 1:
        return np.zeros(len(tamano), int)
    return np.digitize(tamano, np.quantile(tamano, np.linspace(0, 1, n + 1)[1:-1]))


def sortear(entrada, estrato, rng):
    ent = entrada.copy()
    for s in np.unique(estrato):
        idx = np.where(estrato == s)[0]
        ent[idx] = rng.permutation(entrada[idx])
    return ent


def permutacion(Y, entrada, meses_ok, estrato, rng, n=N_PERM):
    """Nula: las fechas de entrada reales, repartidas al azar dentro de cada estrato.

    Conserva los tamaños de cohorte, asi que los meses identificados no cambian.
    """
    return np.array([estimar(Y, sortear(entrada, estrato, rng), meses_ok)[0] for _ in range(n)])


def bootstrap(Y, entrada, meses_ok, rng, n=N_BOOT):
    """Bootstrap por unidad. Una replica puede PERDER un mes identificado (si quedan menos de
    5 sin programa), nunca ganarlo. Se reporta cuantas lo pierden y el intervalo sin ellas."""
    N, T = Y.shape
    est = np.empty(n)
    cambia = np.zeros(n, bool)
    for i in range(n):
        s = rng.integers(0, N, N)
        mo, _ = C.meses_identificados(entrada[s], T)
        mo = mo & meses_ok
        cambia[i] = not np.array_equal(mo, meses_ok)
        est[i], _, _ = estimar(Y[s], entrada[s], mo)
    ok = np.isfinite(est)
    return {"ic95": np.percentile(est[ok], [2.5, 97.5]).tolist(), "replicas": n,
            "replicas_que_pierden_un_mes": int(cambia.sum()),
            "ic95_sin_replicas_que_pierden_un_mes": np.percentile(est[ok & ~cambia], [2.5, 97.5]).tolist(),
            "mediana_replicas_que_pierden_un_mes": float(np.median(est[ok & cambia])) if (ok & cambia).any() else None,
            "ic95_normal_log": np.expm1(np.log1p(estimar(Y, entrada, meses_ok)[0])
                                        + np.array([-1.96, 1.96]) * np.log1p(est[ok]).std()).tolist(),
            "nan": int((~ok).sum())}


def jackknife(Y, entrada):
    T = Y.shape[1]
    n = Y.shape[0]
    jk = np.empty(n)
    for i in range(n):
        e = np.delete(entrada, i)
        jk[i] = estimar(np.delete(Y, i, 0), e, C.meses_identificados(e, T)[0])[0]
    ef = estimar(Y, entrada, C.meses_identificados(entrada, T)[0])[0]
    se = float(np.sqrt((n - 1) / n * ((jk - jk.mean()) ** 2).sum()))
    se_log = float(np.sqrt((n - 1) / n * ((np.log1p(jk) - np.log1p(jk).mean()) ** 2).sum()))
    from scipy.stats import t as tdist
    q = float(tdist.ppf(0.975, n - 1))
    return {"ee": se, "ic95_t": [ef - q * se, ef + q * se],
            "ic95_log": np.expm1(np.log1p(ef) + np.array([-q, q]) * se_log).tolist(),
            "gl": n - 1, "min": float(jk.min()), "max": float(jk.max())}


def inversion(Y, entrada, meses_ok, estrato, rng, n=N_INVERSION):
    """Intervalo por inversion de la prueba de permutacion estratificada (auditoria 02 M6).

    Bajo H0(tau), Y(1) = (1 + tau) Y(0) en toda celda con programa ANTES de la ultima entrada
    (son las que una permutacion puede reasignar como entrenamiento). Se divide Y entre
    (1 + tau) en esas celdas, se recalcula el estadistico y se compara con las mismas n
    permutaciones. El IC es el conjunto de tau que no se rechazan al 5%. Supone un efecto
    multiplicativo constante en los meses con programa previos a agosto de 2019.
    """
    T = Y.shape[1]
    t = np.arange(T)[None, :]
    post = (t >= entrada[:, None]) & (t < entrada.max())
    P = [sortear(entrada, estrato, rng) for _ in range(n)]
    filas = []
    for tau in np.round(np.arange(-0.30, 1.21, 0.01), 2):
        Y0 = Y.copy()
        Y0[post] = Y[post] / (1 + tau)
        o = estimar(Y0, entrada, meses_ok)[0]
        nl = np.array([estimar(Y0, e, meses_ok)[0] for e in P])
        pp = C.p_permutacion(nl, o)
        filas.append((float(tau), pp["p"], pp["p_colas_iguales"]))
    f = np.array(filas)

    def ic(col, nivel):
        acc = f[f[:, col] > nivel, 0]
        if not len(acc):
            return None
        return [float(acc.min()), float(acc.max()), bool(np.allclose(np.diff(acc), 0.01))]

    return {"ic95_valor_absoluto": ic(1, 0.05), "ic90_valor_absoluto": ic(1, 0.10),
            "ic95_colas_iguales": ic(2, 0.05), "permutaciones": n,
            "rejilla": [f[0, 0], f[-1, 0], 0.01],
            "nota": "tercer elemento: region de aceptacion contigua; si el limite toca el borde de la rejilla, ampliarla",
            "supuesto": "efecto multiplicativo constante (1+tau) en toda celda con programa antes de ago-2019; "
                        "asignacion intercambiable dentro de terciles de tamaño"}


# ---------------------------------------------------- tendencias previas (BJS)
def _glm_adelantos(Y, W, extra):
    """Poisson con efectos fijos de unidad y mes + indicadores de adelanto, Newton-Raphson.

    Devuelve coeficientes de adelanto, errores agrupados por unidad (G/(G-1)) y Wald agrupado.
    """
    n, T = Y.shape
    ii, tt = np.where(W)
    rows = np.flatnonzero(W.any(1)); cols = np.flatnonzero(W.any(0))
    ri = {r: k for k, r in enumerate(rows)}; ci = {c: k for k, c in enumerate(cols)}
    nA, nB, K = len(rows), len(cols) - 1, extra.shape[2]
    X = np.zeros((len(ii), nA + nB + K))
    X[np.arange(len(ii)), [ri[i] for i in ii]] = 1
    for k, t in enumerate(tt):
        if ci[t] > 0:
            X[k, nA + ci[t] - 1] = 1
    X[:, nA + nB:] = extra[ii, tt]
    y = Y[ii, tt]
    th = np.zeros(X.shape[1]); th[:nA] = np.log(max(y.mean(), 1e-3))
    for _ in range(80):
        mu = np.exp(X @ th)
        st = np.linalg.solve((X.T * mu) @ X, X.T @ (y - mu))
        th += st
        if np.abs(st).max() < 1e-10:
            break
    mu = np.exp(X @ th)
    Hi = np.linalg.inv((X.T * mu) @ X)
    G = np.zeros((n, X.shape[1]))
    np.add.at(G, ii, X * (y - mu)[:, None])
    G = G[rows]
    g = len(rows)
    V = Hi @ (G.T @ G) @ Hi * g / (g - 1)
    idx = slice(nA + nB, None)
    d = th[idx]
    Wc = float(d @ np.linalg.solve(V[idx, idx], d))
    return d, np.sqrt(np.diag(V)[idx]), Wc, int(np.linalg.matrix_rank(X)), X.shape[1], g


def prueba_tendencias_previas(Y, entrada, estrato, rng, K_lista=(3, 6), n_perm=N_PERM_BJS):
    """Prueba conjunta de tendencias previas de Borusyak, Jaravel y Spiess (2024, sec. 4.4),
    version Poisson (auditoria 02 M2): en las celdas sin programa, efectos fijos de unidad y
    mes mas indicadores de e = -1..-K respecto a e <= -K-1. Wald agrupado por unidad (chi2 y
    F(K, G-1)) y su version por permutacion estratificada del calendario."""
    from scipy.stats import chi2, f as Fd
    T = Y.shape[1]
    obs = np.isfinite(Y)

    def lm(e, K):
        E = np.arange(T)[None] - e[:, None]
        return np.stack([(E == -k).astype(float) for k in range(1, K + 1)], 2)

    out = {}
    for K in K_lista:
        W = (np.arange(T)[None] < entrada[:, None]) & obs
        d, se, Wc, rk, p, g = _glm_adelantos(np.where(obs, Y, 0.0), W, lm(entrada, K))
        nl = []
        for _ in range(n_perm):
            e = sortear(entrada, estrato, rng)
            We = (np.arange(T)[None] < e[:, None]) & obs
            nl.append(_glm_adelantos(np.where(obs, Y, 0.0), We, lm(e, K))[2])
        nl = np.array(nl)
        out[f"K{K}"] = {"adelantos_pct": (np.expm1(d) * 100).tolist(), "ee_log": se.tolist(),
                        "wald_agrupado": Wc, "p_chi2": float(chi2.sf(Wc, K)), "p_F": float(Fd.sf(Wc / K, K, g - 1)),
                        "p_permutacion": float(((nl >= Wc).sum() + 1) / (len(nl) + 1)), "permutaciones": n_perm,
                        "rango_completo": rk == p, "grupos": g}
    return out


def placebos_en_el_tiempo(Y, entrada, estrato, rng, corrimientos=range(3, 21), n_perm=N_PERM_PLACEBO, meses=None):
    """El mismo estimador fingiendo que el programa llega s meses antes (auditoria 02 M2, M3).

    Solo se usan celdas realmente sin programa: se entrena antes de la fecha ficticia y se
    evalua entre la fecha ficticia y la real, con la regla de >= 5 unidades. Cada placebo
    tiene su propia permutacion estratificada.
    """
    T = Y.shape[1]
    t = np.arange(T)[None]
    obs = np.isfinite(Y)
    Y0 = np.where(obs, Y, 0.0)

    def plac(e_real, s):
        ef_ = e_real - s
        ok, _ = C.meses_identificados(ef_, T)
        W = (t < ef_[:, None]) & obs
        a, b = C.ajustar_poisson(Y0, W)
        Yh = a[:, None] * b[None]
        tr = (t >= ef_[:, None]) & (t < e_real[:, None]) & ok[None] & np.isfinite(Yh) & obs
        return C.razon(Y, Yh, tr), int(tr.sum())

    filas = []
    for s in corrimientos:
        v, n = plac(entrada, s)
        nl = np.array([plac(sortear(entrada, estrato, rng), s)[0] for _ in range(n_perm)])
        filas.append({"meses_antes": s, "lanzamiento_ficticio": meses[int(entrada.min()) - s].isoformat()[:7],
                      "efecto": v, "celdas": n, "p": C.p_permutacion(nl, v)["p"]})
    v = np.array([f["efecto"] for f in filas])
    return {"placebos": filas, "media": float(v.mean()), "de": float(v.std()),
            "max_abs": float(np.abs(v).max()), "positivos": int((v > 0).sum()), "n": len(v),
            "p_menor_005": int(sum(f["p"] < 0.05 for f in filas))}


# ------------------------------------------------------------ diagnosticos M7
def contraste_controles(Y, entrada, meses, alcaldias):
    """¿Cuanto del contraste viene de que los controles bajaron? (auditoria 02 M7)

    Variacion interanual de VF en celdas con programa y aun sin programa, en los meses
    identificados y un año antes, y el efecto por mes calendario.
    """
    T = Y.shape[1]
    ok, _ = C.meses_identificados(entrada, T)
    Yhat, trat = C.imputar(Y, entrada, ok)
    out = {"por_mes": []}
    for m in np.where(ok & (np.arange(T) >= entrada.min()))[0]:
        con = entrada <= m
        sin = ~con

        def g(sel, mm):
            a, b = Y[sel, mm], Y[sel, mm - 12]
            f = np.isfinite(a) & np.isfinite(b)
            return float(a[f].sum() / b[f].sum() - 1)
        c = trat & (np.arange(T)[None] == m)
        out["por_mes"].append({"mes": meses[m].isoformat()[:7], "unidades_con": int(con.sum()), "unidades_sin": int(sin.sum()),
                               "interanual_con_programa": g(con, m), "interanual_sin_programa": g(sin, m),
                               "interanual_todas": g(np.ones(len(entrada), bool), m),
                               "anio_antes_con": g(con, m - 12), "anio_antes_sin": g(sin, m - 12),
                               "efecto_mes_calendario": C.razon(Y, Yhat, c)})
    # marzo: controles con y sin una agencia tratada en su alcaldia (descriptivo)
    m = int(entrada.min())
    trt = entrada <= m
    ctl = ~trt
    alc_t = set(alcaldias[trt])
    vec = ctl & np.isin(alcaldias, list(alc_t))
    lej = ctl & ~vec
    sinm = np.arange(T)[None, :] < entrada[:, None]
    obs = np.isfinite(Y)
    W = sinm & obs
    W[vec, m] = False
    a, b = C.ajustar_poisson(np.where(obs, Y, 0.0), W)
    Yh = a[:, None] * b[None]
    c = trt[:, None] & (np.arange(T)[None] == m)
    out["marzo_por_vecindad"] = {
        "controles_con_vecina_tratada": int(vec.sum()), "controles_sin_vecina_tratada": int(lej.sum()),
        "interanual_vecinos": float(Y[vec, m].sum() / Y[vec, m - 12].sum() - 1) if vec.any() else None,
        "interanual_lejanos": float(Y[lej, m].sum() / Y[lej, m - 12].sum() - 1) if lej.any() else None,
        "efecto_marzo_solo_controles_lejanos": C.razon(Y, Yh, c),
        "efecto_marzo_todos": C.razon(Y, Yhat, c),
        "nota": "descriptivo: la caida de los vecinos empieza antes del lanzamiento (auditoria 02 M7)"}
    return out


def ventanas_entrenamiento(mat, entrada, meses, inicios=(0, 6, 12, 18, 20)):
    """Efecto con el entrenamiento recortado a partir de otro mes (auditoria 02 M3)."""
    T = len(meses)
    t = np.arange(T)[None]
    ok, _ = C.meses_identificados(entrada, T)
    out = []
    for ini in inicios:
        fila = {"desde": meses[ini].isoformat()[:7]}
        for k, Y in (("vf", mat["vf"]), ("robos", mat["robos"]), ("resto", mat["total"] - mat["vf"])):
            obs = np.isfinite(Y)
            W = (t < entrada[:, None]) & (t >= ini) & obs
            a, b = C.ajustar_poisson(np.where(obs, Y, 0.0), W)
            Yh = a[:, None] * b[None]
            tr = (t >= entrada[:, None]) & ok[None] & np.isfinite(Yh) & obs
            fila[k] = C.razon(Y, Yh, tr)
        out.append(fila)
    return out


def ciudad(res):
    """Descriptivo: violencia familiar en agencias territoriales contra su propia tendencia previa.

    Poisson con tendencia lineal y estacionalidad, ajustado antes del lanzamiento. La banda
    original (`banda`) solo tiene ruido; `banda_con_tendencia` y `ic95_exceso_pct` suman la
    incertidumbre de los parametros extrapolados (metodo delta, cuasi-Poisson; auditoria 02 m6).
    """
    t = pl.read_parquet(C.INTERIM / "fgj_tipo_agencia.parquet")

    def ajuste(tipos=("Agencias territoriales",), ini=dt.date(2016, 1, 1), tendencia=True):
        s = (t.filter(pl.col("tipo").is_in(list(tipos))).group_by("mes").agg(pl.col("n").sum())
             .filter(pl.col("mes").is_between(ini, dt.date(2020, 2, 1))).sort("mes"))
        y = s["n"].to_numpy().astype(float)
        m = s["mes"].to_list()
        pre = np.array([x < C.LANZAMIENTO for x in m])
        X = np.column_stack([np.ones(len(y))] + ([np.arange(len(y), dtype=float)] if tendencia else []) +
                            [np.array([x.month == k for x in m], float) for k in range(2, 13)])
        beta = np.zeros(X.shape[1]); beta[0] = np.log(y[pre].mean())
        for _ in range(50):
            mu = np.exp(X[pre] @ beta)
            z = X[pre] @ beta + (y[pre] - mu) / mu
            beta = np.linalg.solve((X[pre].T * mu) @ X[pre], (X[pre].T * mu) @ z)
        mu = np.exp(X @ beta)
        disp = float(((y[pre] - mu[pre]) ** 2 / mu[pre]).sum() / (pre.sum() - X.shape[1]))
        V = np.linalg.inv((X[pre].T * mu[pre]) @ X[pre]) * disp
        post = ~pre
        S = mu[post].sum()
        gr = (mu[post][:, None] * X[post]).sum(0)
        se = np.sqrt(gr @ V @ gr + disp * S)
        ex = float(y[post].sum() / S - 1)
        ic = [float(y[post].sum() / (S + 1.96 * se) - 1), float(y[post].sum() / (S - 1.96 * se) - 1)]
        var_mes = disp * mu + mu ** 2 * np.einsum("ij,jk,ik->i", X, V, X)
        return y, m, mu, disp, ex, ic, np.sqrt(var_mes)

    y, m, mu, disp, ex, ic, sd_mes = ajuste()
    res["ciudad"] = {
        "meses": [x.isoformat()[:7] for x in m], "observado": y.tolist(), "esperado": mu.round(1).tolist(),
        "banda": (1.96 * np.sqrt(mu * disp)).round(1).tolist(),
        "banda_con_tendencia": (1.96 * sd_mes).round(1).tolist(),
        "sobredispersion": disp,
        "sobredispersion_nota": "Pearson del modelo de tendencia de la ciudad (38 meses, 13 parametros); "
                                "no es la sobredispersion relevante para el efecto por agencia (ver phi_imputacion)",
        "exceso_post_pct": ex * 100,
        "ic95_exceso_pct": [v * 100 for v in ic],
        "variantes": {},
    }
    todas = t["tipo"].unique().to_list()
    for nombre, kw in (("desde_2017", {"ini": dt.date(2017, 1, 1)}), ("sin_tendencia", {"tendencia": False}),
                       ("todas_las_sedes", {"tipos": todas}),
                       ("territoriales_a75_cjm", {"tipos": ["Agencias territoriales", "Agencia 75 (violencia familiar)",
                                                             "Centros de Justicia para las Mujeres"]})):
        _, _, _, d_, e_, ic_, _ = ajuste(**kw)
        res["ciudad"]["variantes"][nombre] = {"exceso_pct": e_ * 100, "ic95_pct": [v * 100 for v in ic_], "phi": d_}


# ------------------------------------------------------------ nucleo por muestra
def analisis(mat, unidades, meses, entrada, fuera, etiqueta, completo=True):
    """Efecto, inferencia y placebos para una muestra. `completo=False` para la variante."""
    T = len(meses)
    meses_ok, sin_prog = C.meses_identificados(entrada, T)
    tamano = mat["total"][:, np.array([m.year == 2018 for m in meses])].sum(1)
    estrato = estratos_de(tamano, 3)
    res = {"unidades_en_muestra": len(unidades), "unidades_fuera": fuera,
           "ventana": [meses[0].isoformat()[:7], meses[-1].isoformat()[:7]],
           "meses_identificados": [meses[i].isoformat()[:7] for i in np.where(meses_ok & (np.arange(T) >= entrada.min()))[0]],
           "sin_programa_por_mes": {meses[i].isoformat()[:7]: int(sin_prog[i]) for i in range(T) if meses[i] >= C.LANZAMIENTO},
           "cohortes": {meses[int(e)].isoformat()[:7]: int((entrada == e).sum()) for e in sorted(set(entrada))}}
    resultados = {}
    for k in (DELITOS if completo else ("vf", "robos")):
        Y = mat[k]
        ef, Yhat, trat = estimar(Y, entrada, meses_ok)
        nulas = permutacion(Y, entrada, meses_ok, estratos_de(tamano, 1), C.generador(SEMILLA, f"{etiqueta}-perm1-{k}"))
        nulas_e = permutacion(Y, entrada, meses_ok, estrato, C.generador(SEMILLA, f"{etiqueta}-perm3-{k}"))
        p1, p3 = C.p_permutacion(nulas, ef), C.p_permutacion(nulas_e, ef)
        bs = bootstrap(Y, entrada, meses_ok, C.generador(SEMILLA, f"{etiqueta}-boot-{k}"))
        lead_ev, lead_tot, lead_c = adelantos(Y, entrada)
        r = {"efecto": ef, "ic95": bs["ic95"], "bootstrap": bs,
             "p_permutacion": p1["p"], "p_permutacion_por_tamano": p3["p"],
             "permutacion_sin_estratos": p1, "permutacion_por_tamano": p3,
             "celdas_tratadas": int(trat.sum()), "observado": float(Y[trat].sum()),
             "contrafactual": float(Yhat[trat].sum()),
             "por_evento": por_evento(Y, Yhat, trat, entrada),
             "adelantos": lead_ev, "adelantos_total": lead_tot, "adelantos_celdas": lead_c,
             "nulas_percentiles": np.percentile(nulas_e, [2.5, 50, 97.5]).tolist(),
             "nulas_sin_estratos_percentiles": np.percentile(nulas, [2.5, 50, 97.5]).tolist(),
             "nulas_abs_q95": float(np.percentile(np.abs(nulas_e), 95)),
             "nulas": np.round(nulas, 4).tolist() if (k == "vf" and completo) else None,
             "nulas_por_tamano": np.round(nulas_e, 4).tolist() if (k == "vf" and completo) else None}
        if completo:
            sr_ev, sr_tot, sr_c = adelantos(Y, entrada, minimo=0)
            r["adelantos_sin_regla_minima"] = {"por_mes": sr_ev, "total": sr_tot, "celdas": sr_c}
        r["phi_imputacion"] = phi_imputacion(Y, entrada)
        resultados[k] = r
        print(f"  [{etiqueta}] {k:9} efecto {ef*100:+.1f}%  IC95 [{bs['ic95'][0]*100:+.1f}, {bs['ic95'][1]*100:+.1f}]  "
              f"p={p1['p']:.4f} p_tam={p3['p']:.4f}  adelantos {lead_tot*100:+.1f}% ({lead_c} celdas)  celdas={trat.sum()}")
    res["resultados"] = resultados

    Y = mat["vf"]
    ef, Yhat, trat = estimar(Y, entrada, meses_ok)
    res["por_cohorte"] = []
    for e in sorted(set(entrada)):
        c = trat & (entrada == e)[:, None]
        if c.sum():
            res["por_cohorte"].append({"cohorte": meses[int(e)].isoformat()[:7], "unidades": int((entrada == e).sum()),
                                       "celdas": int(c.sum()), "efecto": C.razon(Y, Yhat, c),
                                       "contrafactual": float(Yhat[c].sum()), "observado": float(Y[c].sum()),
                                       "peso": float(Yhat[c].sum() / Yhat[trat].sum())})
    if not completo:
        return res, estrato, tamano

    # sensibilidad de la permutacion al numero de estratos (auditoria 02 M4)
    from scipy.stats import spearmanr
    sens = {}
    for n_e in ESTRATOS:
        s_ = estratos_de(tamano, n_e)
        if n_e == 1:
            nl = np.array(resultados["vf"]["nulas"])
        elif n_e == 3:
            nl = np.array(resultados["vf"]["nulas_por_tamano"])
        else:
            nl = permutacion(Y, entrada, meses_ok, s_, C.generador(SEMILLA, f"{etiqueta}-perm{n_e}-vf"))
        rhos = [spearmanr(entrada[s_ == g], tamano[s_ == g])[0] for g in np.unique(s_) if len(set(entrada[s_ == g])) > 1]
        sens[str(n_e)] = {**C.p_permutacion(nl, ef), "spearman_medio_dentro": float(np.mean(rhos))}
    res["permutacion_sensibilidad_estratos"] = sens
    res["spearman_dentro_de_terciles"] = [float(spearmanr(entrada[estrato == g], tamano[estrato == g])[0]) for g in range(3)]
    print("  p por numero de estratos:", {k: round(v["p"], 4) for k, v in sens.items()})
    return res, estrato, tamano


def main():
    print("A02 efecto")
    mat, unidades, meses, entrada, entrada10, fuera, info = cargar(detalle=True)
    T = len(meses)
    meses_ok, _ = C.meses_identificados(entrada, T)
    res, estrato, tamano = analisis(mat, unidades, meses, entrada, fuera, "principal")
    res["regla_exclusion"] = {
        "principal": REGLA_PRINCIPAL,
        "descripcion": "se excluye una unidad si ANTES de su entrada tiene algun mes sin carpetas o un salto > 2.5x "
                       "en la media movil de 6 meses del total, o si entra despues de feb-2020",
    }
    res["celdas_faltantes"] = info["celdas_faltantes"]

    # --- la otra regla de muestra, completa, como robustez ---
    mat52, u52, m52, e52, _, fuera52 = cargar("ventana_completa")
    alt, _, _ = analisis(mat52, u52, m52, e52, fuera52, "ventana_completa", completo=False)
    lead52 = adelantos(mat52["vf"], e52)
    alt["resultados"]["vf"]["adelantos_total"] = lead52[1]
    alt["resultados"]["vf"]["adelantos"] = lead52[0]
    alt["descripcion"] = "regla original: meses_cero y salto sobre toda la ventana ene-2017 a feb-2020 (usa meses con programa)"
    res["regla_exclusion_ventana_completa"] = alt
    # la principal sin marcar faltantes: el estimando no deberia moverse
    matz, _, _, ez, _, _ = cargar(marcar_faltantes=False)
    okz, _ = C.meses_identificados(ez, T)
    res["sin_marcar_faltantes"] = {"efecto_vf": estimar(matz["vf"], ez, okz)[0],
                                   "efecto_robos": estimar(matz["robos"], ez, okz)[0],
                                   "adelantos_total_vf": adelantos(matz["vf"], ez)[1]}

    # --- robustez ---
    rob = {}
    mo10, _ = C.meses_identificados(entrada10, T)
    rob["entrada_con_10_atenciones"] = estimar(mat["vf"], entrada10, mo10)[0]
    marzo = entrada == entrada.min()
    ent_sin = entrada[~marzo]
    mo_sin, _ = C.meses_identificados(ent_sin, T)
    rob["sin_cohorte_de_marzo"] = estimar(mat["vf"][~marzo], ent_sin, mo_sin)[0]
    mo3, _ = C.meses_identificados(entrada, T, minimo=3)
    rob["minimo_3_sin_programa"] = estimar(mat["vf"], entrada, mo3)[0]
    mo10u, _ = C.meses_identificados(entrada, T, minimo=10)
    rob["minimo_10_sin_programa"] = estimar(mat["vf"], entrada, mo10u)[0]
    Yv, Yt = mat["vf"], mat["total"] - mat["vf"]
    _, Yhv, trat = estimar(Yv, entrada, meses_ok)
    _, Yht, _ = estimar(Yt, entrada, meses_ok)
    rob["razon_vf_vs_resto_de_delitos"] = float((Yv[trat].sum() / Yhv[trat].sum()) / (Yt[trat].sum() / Yht[trat].sum()) - 1)
    rob["resto_de_delitos"] = C.razon(Yt, Yht, trat)
    rob["regla_exclusion_ventana_completa"] = alt["resultados"]["vf"]["efecto"]
    rob["unidades_con_otra_fecha_con_10_atenciones"] = int((entrada != entrada10).sum())
    res["robustez"] = rob
    for k, v in rob.items():
        print(f"  robustez {k}: {v*100:+.1f}%" if isinstance(v, float) else f"  robustez {k}: {v}")

    # --- inferencia adicional sobre el efecto principal ---
    Y = mat["vf"]
    ef = res["resultados"]["vf"]["efecto"]
    res["inversion_permutacion"] = inversion(Y, entrada, meses_ok, estrato, C.generador(SEMILLA, "inversion"))
    res["jackknife"] = jackknife(Y, entrada)
    print("  inversion:", res["inversion_permutacion"]["ic95_valor_absoluto"], " jackknife:", np.round(res["jackknife"]["ic95_t"], 3))

    # --- tendencias previas y placebos en el tiempo ---
    res["tendencias_previas_bjs"] = {k: prueba_tendencias_previas(mat[k], entrada, estrato, C.generador(SEMILLA, f"bjs-{k}"))
                                     for k in ("vf", "robos")}
    print("  BJS:", {k: {kk: round(vv["p_chi2"], 3) for kk, vv in v.items()} for k, v in res["tendencias_previas_bjs"].items()})
    res["placebos_en_el_tiempo"] = {
        k: placebos_en_el_tiempo(Y_, entrada, estrato, C.generador(SEMILLA, f"placebo-tiempo-{k}"), meses=meses)
        for k, Y_ in (("vf", mat["vf"]), ("robos", mat["robos"]), ("resto", mat["total"] - mat["vf"]))}
    for k, v in res["placebos_en_el_tiempo"].items():
        print(f"  placebos en el tiempo {k}: media {v['media']*100:+.1f}%, DE {v['de']*100:.1f}, max|.| {v['max_abs']*100:.1f}, "
              f"positivos {v['positivos']}/{v['n']}, p<0.05: {v['p_menor_005']}")
    res["placebos_en_el_tiempo"]["vf"]["alcanzan_el_efecto"] = int(sum(abs(f["efecto"]) >= abs(ef) for f in res["placebos_en_el_tiempo"]["vf"]["placebos"]))
    res["ventanas_entrenamiento"] = ventanas_entrenamiento(mat, entrada, meses)

    # --- contraste de los controles y efecto de marzo por mes calendario ---
    alc = pl.read_parquet(C.INTERIM / "panel.parquet").group_by("unidad").agg(pl.col("alcaldia").first()).sort("unidad")
    alc = np.array([dict(alc.iter_rows())[u] for u in unidades])
    res["contraste_controles"] = contraste_controles(Y, entrada, meses, alc)
    ef_, Yhat, trat = estimar(Y, entrada, meses_ok)
    T_ = np.arange(T)[None]
    res["cohorte_marzo_por_mes"] = [
        {"mes": meses[m].isoformat()[:7], "efecto": C.razon(Y, Yhat, trat & marzo[:, None] & (T_ == m))}
        for m in np.where(meses_ok & (np.arange(T) >= entrada.min()))[0]]

    # --- ¿el orden de entrada parece azar? balance de 2018 por cohorte ---
    a17 = np.array([m.year == 2017 for m in meses]); a18 = np.array([m.year == 2018 for m in meses])
    vf17, vf18, tot18 = mat["vf"][:, a17].sum(1), mat["vf"][:, a18].sum(1), mat["total"][:, a18].sum(1)
    res["balance"] = {
        "vf_2018_marzo": float(vf18[marzo].mean()), "vf_2018_resto": float(vf18[~marzo].mean()),
        "total_2018_marzo": float(tot18[marzo].mean()), "total_2018_resto": float(tot18[~marzo].mean()),
        "crec_vf_17_18_marzo": float(vf18[marzo].sum() / vf17[marzo].sum() - 1),
        "crec_vf_17_18_resto": float(vf18[~marzo].sum() / vf17[~marzo].sum() - 1),
    }
    from scipy.stats import spearmanr
    rho, pval = spearmanr(entrada, tot18)
    res["balance"]["spearman_entrada_vs_tamano"] = float(rho)
    res["balance"]["spearman_p"] = float(pval)
    res["balance"]["cohortes_por_tercil"] = {str(g): {meses[int(e)].isoformat()[:7]: int(((entrada == e) & (estrato == g)).sum())
                                                     for e in sorted(set(entrada))} for g in range(3)}
    print("  por cohorte:", [(d["cohorte"], round(d["efecto"] * 100, 1), d["celdas"]) for d in res["por_cohorte"]])

    res["metodologia"] = metodologia(mat["vf"], entrada, meses_ok, unidades, meses, res["resultados"]["vf"]["phi_imputacion"]["phi"])
    ciudad(res)
    print(f"  ciudad: exceso sobre tendencia previa {res['ciudad']['exceso_post_pct']:+.1f}% "
          f"IC95 {np.round(res['ciudad']['ic95_exceso_pct'], 1)}")

    def lista(M):
        return [[None if not np.isfinite(v) else int(v) for v in fila] for fila in M]
    res["panel"] = {"unidades": unidades, "meses": [m.isoformat()[:7] for m in meses],
                    "entrada": [meses[int(e)].isoformat()[:7] for e in entrada],
                    "vf": lista(mat["vf"]), "robos": lista(mat["robos"])}
    figuras(res, meses)
    C.guardar_json(res, CARPETA)


def figuras(res, meses):
    r = res["resultados"]
    nota = ("Fuente: FGJ CDMX (carpetas por fecha de inicio) y SEMUJERES (atenciones). "
            f"{res['unidades_en_muestra']} unidades territoriales con codigos estables; estimador por imputacion, Poisson.")
    # 1. estudio de evento: adelantos + efectos
    fig, ax = plt.subplots(figsize=(9.5, 4.6))
    previos = []
    for k, color, lab, dx in (("vf", RED, "Violencia familiar", -0.12), ("robos", BLUE, "Robos (placebo)", 0.12)):
        pts = [(d["e"], d["efecto"]) for d in r[k]["adelantos"] + r[k]["por_evento"] if d["efecto"] is not None]
        xs, ys = zip(*pts)
        ax.plot(np.array(xs) + dx, np.array(ys) * 100, "o-", color=color, lw=1.6, ms=5, label=lab)
        if k == "vf":
            previos = [d["efecto"] for d in r[k]["adelantos"] if d["efecto"] is not None]
    ax.axhline(0, color="#000", lw=0.8)
    ax.axvline(-0.5, color="#666", ls="--", lw=1)
    ax.text(-0.4, ax.get_ylim()[1] * 0.92, "llegan las abogadas", fontsize=9, color="#444")
    sin_comp = [d["e"] for d in r["vf"]["adelantos"] if d["efecto"] is None] + [-1]
    for e in sin_comp:
        ax.text(e, 0, "sin\ncomp.", ha="center", va="center", fontsize=7, color="#666")
    ax.set_xlabel("Meses desde la llegada del programa a la agencia")
    ax.set_ylabel("Diferencia contra el contrafactual (%)")
    ax.set_title(f"Los meses previos medibles van de {min(previos)*100:+.0f}% a {max(previos)*100:+.0f}%; "
                 f"después solo hay {len(res['meses_identificados'])} meses medibles", fontweight="bold")
    ax.legend(loc="upper left", framealpha=0.8)
    guardar(fig, CARPETA, "01_estudio_de_evento", nota + " Meses con menos de 5 agencias de comparacion: sin comparacion.")

    # 2. distribucion de permutacion
    nul = np.array(r["vf"]["nulas_por_tamano"]) * 100
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.hist(nul, bins=50, color=BLUE, edgecolor="#000", linewidth=0.3)
    ax.axvline(r["vf"]["efecto"] * 100, color=RED, lw=2,
               label=f"Efecto estimado: {r['vf']['efecto']*100:+.1f}% (p = {r['vf']['p_permutacion_por_tamano']:.3f})")
    ax.set_xlabel("Efecto con fechas de entrada repartidas al azar entre agencias de tamaño parecido (%)"); ax.set_ylabel("Repeticiones")
    ax.set_title("Contra fechas repartidas al azar, el efecto sí es poco común", fontweight="bold")
    ax.legend(loc="upper left", bbox_to_anchor=(0, -0.18), framealpha=0.8)
    guardar(fig, CARPETA, "02_permutacion", nota + f" {len(nul):,} sorteos dentro de terciles de tamaño.")

    # 3. todos los resultados con su intervalo
    etiquetas = {"vf": "Violencia familiar", "amenazas": "Amenazas", "sexuales": "Delitos sexuales", "robos": "Robos (placebo)"}
    fig, ax = plt.subplots(figsize=(8.5, 3.6))
    ks = ["vf", "amenazas", "sexuales", "robos"]
    for i, k in enumerate(ks):
        lo, hi = r[k]["ic95"]
        c = RED if k == "vf" else BLUE
        ax.plot([lo * 100, hi * 100], [i, i], color=c, lw=2.5)
        ax.plot(r[k]["efecto"] * 100, i, "o", color=c, ms=8)
    ax.axvline(0, color="#000", lw=0.8)
    ax.set_yticks(range(len(ks))); ax.set_yticklabels([etiquetas[k] for k in ks]); ax.invert_yaxis()
    ax.set_xlabel("Efecto estimado e intervalo bootstrap al 95% (%)")
    toca = r["vf"]["ic95"][0] <= 0
    ax.set_title("Violencia familiar sube, pero su intervalo toca el cero" if toca else
                 "Violencia familiar sube; su intervalo bootstrap no toca el cero", fontweight="bold")
    guardar(fig, CARPETA, "03_efecto_por_delito", nota)

    # 4. ciudad
    c = res["ciudad"]
    x = [dt.date.fromisoformat(m + "-01") for m in c["meses"]]
    obs, esp, b = np.array(c["observado"]), np.array(c["esperado"]), np.array(c["banda_con_tendencia"])
    fig, ax = plt.subplots(figsize=(11, 4.4))
    ax.fill_between(x, esp - b, esp + b, color=BLUE_PALE, label="Esperado con la tendencia 2016-2019 (95%, con incertidumbre de la tendencia)")
    ax.plot(x, esp, color=BLUE_LIGHT, lw=1.2)
    ax.plot(x, obs, color=BLUE_DARK, lw=1.8, label="Observado")
    ax.axvline(C.LANZAMIENTO, color=RED, ls="--", lw=1.2)
    ax.text(C.LANZAMIENTO, ax.get_ylim()[1] * 0.98, "  marzo 2019", color=RED, fontsize=9, va="top")
    ax.set_ylabel("Carpetas de violencia familiar por mes"); miles(ax)
    ax.set_title("En toda la ciudad la violencia familiar sube por encima de su tendencia desde 2019", fontweight="bold")
    ax.legend(loc="upper left", framealpha=0.8)
    guardar(fig, CARPETA, "04_ciudad_contra_tendencia", "Fuente: FGJ CDMX, agencias territoriales. "
            "Descriptivo: la ciudad entera no tiene grupo de comparacion.")

    # 5. placebos en el tiempo
    fig, ax = plt.subplots(figsize=(10, 4.2))
    for k, color, lab, dx in (("vf", RED, "Violencia familiar", -0.15), ("robos", BLUE, "Robos", 0.0),
                              ("resto", BLUE_LIGHT, "Resto de delitos", 0.15)):
        pl_ = res["placebos_en_el_tiempo"][k]["placebos"]
        ax.plot([f["meses_antes"] + dx for f in pl_], [f["efecto"] * 100 for f in pl_], "o", color=color, ms=5, label=lab)
    ax.axhline(r["vf"]["efecto"] * 100, color=RED, ls="--", lw=1)
    ax.text(3, r["vf"]["efecto"] * 100 + 1, f"efecto estimado {r['vf']['efecto']*100:+.1f}%", color=RED, fontsize=8)
    ax.axhline(0, color="#000", lw=0.8)
    ax.set_xlabel("Meses antes del lanzamiento real en que se finge la llegada")
    ax.set_ylabel("'Efecto' sin programa (%)")
    ax.set_title("Con lanzamientos ficticios en 2017-2018 el estimador no llega al efecto estimado", fontweight="bold")
    ax.legend(loc="upper left", bbox_to_anchor=(1, 1), framealpha=0.8)
    guardar(fig, CARPETA, "05_placebos_en_el_tiempo", nota + " Solo celdas sin programa.")


if __name__ == "__main__":
    main()
