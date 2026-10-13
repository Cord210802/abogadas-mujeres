"""Piezas compartidas del estudio de Abogadas de las Mujeres.

Todo lo que dos scripts necesitan igual vive aqui, para que no haya dos versiones
de la misma decision:

  - rutas y constantes (ventanas, listas de delitos)
  - la unidad de analisis: como se empata una agencia del programa con los
    codigos de agencia de la Fiscalia
  - el estimador por imputacion (Borusyak, Jaravel y Spiess 2024) en su version
    Poisson, que usan el analisis de efecto y las simulaciones de potencia

Ver docs/abogadas/ para la justificacion de cada decision.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

RAW = ROOT / "data" / "raw" / "abogadas" / "atenciones_abogadas_mujeres.csv"
FGJ = ROOT / "data" / "interim" / "fgj_carpetas.parquet"
INTERIM = ROOT / "data" / "interim" / "abogadas"
GRAFS = ROOT / "grafs" / "abogadas"

# ---------------------------------------------------------------- ventanas
# El panel de agencias va de enero de 2017 a enero de 2021. En febrero de 2021 la
# Fiscalia empieza a abrir Unidades de Atencion Temprana (UAT) y en septiembre de
# 2021 la violencia familiar se muda casi entera a ellas: despues de eso los codigos
# de agencia ya no son comparables en el tiempo (docs/abogadas/01_datos_y_limpieza.md).
PANEL_INI = dt.date(2017, 1, 1)
PANEL_FIN = dt.date(2021, 1, 1)
# Antes de la pandemia. El analisis principal no cruza marzo de 2020.
PRE_COVID_FIN = dt.date(2020, 2, 1)
LANZAMIENTO = dt.date(2019, 3, 1)
# Minimo de agencias todavia sin programa para que un mes sirva de comparacion.
MIN_SIN_PROGRAMA = 5

# --------------------------------------------------------------- delitos
# Violencia familiar es el resultado principal: es el delito que mas atienden las
# abogadas (24,108 atenciones con carpeta SI de violencia familiar; 24,779 filas traen
# ese delito anotado) y el 59% de la violencia familiar DE LA CIUDAD se abre en agencias
# territoriales (ene-2017 a feb-2020; A01 guarda la cifra en resultados.json).
# Los delitos sexuales van casi todos a la fiscalia especializada.
# (Corregido por auditoria/01_datos.md m3-m4: decia "24,779 carpetas" y "60% de sus carpetas".)
DELITOS_SEXUALES = (
    "ABUSO SEXUAL", "ACOSO SEXUAL", "ACOSO SEXUAL AGRAVADO EN CONTRA DE MENORES",
    "VIOLACION", "VIOLACION EQUIPARADA", "VIOLACION EQUIPARADA POR CONOCIDO",
    "VIOLACION TUMULTUARIA", "VIOLACION TUMULTUARIA EQUIPARADA", "TENTATIVA DE VIOLACION",
    "CONTRA LA INTIMIDAD SEXUAL", "ESTUPRO",
)
# Placebo: todos los robos juntos. Sumados, no les afectan las reclasificaciones
# entre subtipos de robo (2018, 2020) y el programa no tiene por que moverlos.
PREFIJO_PLACEBO = "ROBO"

# ------------------------------------------------------- unidad de analisis
# Prefijos del programa -> prefijos de la Fiscalia.
PREFIJO_FGJ = {"AZC": "AZ", "CUJ": "CJ"}
TERRITORIALES = {"AO", "AZ", "BJ", "COY", "CUH", "CJ", "GAM", "IZC", "IZP",
                 "MC", "MH", "MIL", "TLH", "TLP", "VC", "XO"}
ALCALDIA = {
    "AO": "Álvaro Obregón", "AZ": "Azcapotzalco", "BJ": "Benito Juárez", "COY": "Coyoacán",
    "CUH": "Cuauhtémoc", "CJ": "Cuajimalpa", "GAM": "Gustavo A. Madero", "IZC": "Iztacalco",
    "IZP": "Iztapalapa", "MC": "Magdalena Contreras", "MH": "Miguel Hidalgo",
    "MIL": "Milpa Alta", "TLH": "Tláhuac", "TLP": "Tlalpan", "VC": "Venustiano Carranza",
    "XO": "Xochimilco",
}


def codigos_programa(etiqueta: str) -> list[str]:
    """'CUJ 1 Y 2' -> ['CJ-1', 'CJ-2']; 'AZC-2 y 4' -> ['AZ-2', 'AZ-4'].

    Devuelve [] si la etiqueta no es una agencia territorial (fiscalias
    especializadas, oficinas centrales, jornadas, NA).
    """
    e = re.sub(r"\s+", " ", (etiqueta or "").upper().strip())
    m = re.match(r"^([A-Z]+)[- ](\d+)((?: Y \d+)*)$", e)
    if not m:
        return []
    pre = PREFIJO_FGJ.get(m.group(1), m.group(1))
    if pre not in TERRITORIALES:
        return []
    nums = [m.group(2)] + re.findall(r"\d+", m.group(3))
    return [f"{pre}-{n}" for n in nums]


def codigo_fgj(agencia: str | None) -> str | None:
    """Normaliza el codigo de agencia de la Fiscalia.

    'UAT-IZP-5' -> 'IZP-5': la Unidad de Atencion Temprana atiende el mismo
    territorio que la agencia. 'URI-' y 'ADD-' son unidades de otra naturaleza
    (recepcion, denuncia digital) y se quedan fuera.
    """
    if agencia is None:
        return None
    a = agencia.upper().strip()
    if a.startswith("UAT-"):
        a = a[4:]
    m = re.match(r"^([A-Z]+)-(\d+)$", a)
    if not m:
        return None
    # 'UAT-CUJ-1' usa el prefijo del programa: se traduce igual que las etiquetas del
    # programa (auditoria/01_datos.md m7). Solo cambia el panel posterior a 2021.
    pre = PREFIJO_FGJ.get(m.group(1), m.group(1))
    if pre not in TERRITORIALES:
        return None
    return f"{pre}-{m.group(2)}"


class Unir:
    """Union-find minimo: dos etiquetas que comparten un codigo son la misma unidad."""

    def __init__(self):
        self.p = {}

    def raiz(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def unir(self, a, b):
        self.p[self.raiz(a)] = self.raiz(b)


# ------------------------------------------------------------ estimador
def ajustar_poisson(Y: np.ndarray, W: np.ndarray, iters: int = 200, tol: float = 1e-10):
    """Poisson con efectos fijos de agencia y de mes, solo con las celdas W=True.

    E[Y_it] = a_i * b_t. El estimador de maxima verosimilitud de este modelo es
    el ajuste proporcional iterativo: se alternan a_i = sum_t y / sum_t b_t y
    b_t = sum_i y / sum_i a_i sobre las celdas de entrenamiento. Un mes sin
    ninguna celda de entrenamiento queda con b_t = NaN (no identificado).
    """
    Yw = np.where(W, Y, 0.0)
    a = np.ones(Y.shape[0])
    b = np.ones(Y.shape[1])
    col_ok = W.any(axis=0)
    fil_ok = W.any(axis=1)
    for _ in range(iters):
        a_new = Yw.sum(1) / np.maximum((W * b[None, :]).sum(1), 1e-12)
        b_new = Yw.sum(0) / np.maximum((W * a_new[:, None]).sum(0), 1e-12)
        if np.allclose(a_new, a, rtol=0, atol=tol) and np.allclose(b_new, b, rtol=0, atol=tol):
            a, b = a_new, b_new
            break
        a, b = a_new, b_new
    a = np.where(fil_ok, a, np.nan)
    b = np.where(col_ok, b, np.nan)
    return a, b


def imputar(Y: np.ndarray, entrada: np.ndarray, meses_validos: np.ndarray,
            excluir: np.ndarray | None = None):
    """Estimador por imputacion con agencias todavia sin programa como comparacion.

    Y          agencias x meses, conteos
    entrada    indice de mes en que entra cada agencia (np.inf = nunca)
    meses_validos  booleano por mes: meses donde se permite imputar (hay suficientes
               agencias sin programa)
    excluir    celdas que no entran al ajuste aunque no tengan programa (para la
               prueba de adelantos)

    Devuelve (Yhat, tratadas) con Yhat el contrafactual en todas las celdas y
    tratadas el booleano de celdas con programa donde se puede imputar.
    Una celda con Y = NaN (faltante: el codigo de la Fiscalia no esta en uso ese mes,
    ver A02) no entra ni al ajuste ni a las celdas tratadas.
    """
    T = Y.shape[1]
    t = np.arange(T)[None, :]
    sin = t < entrada[:, None]
    obs = np.isfinite(Y)
    W = sin & obs
    if excluir is not None:
        W &= ~excluir
    a, b = ajustar_poisson(np.where(obs, Y, 0.0), W)
    Yhat = a[:, None] * b[None, :]
    tratadas = (~sin) & meses_validos[None, :] & np.isfinite(Yhat) & obs
    return Yhat, tratadas


def razon(Y, Yhat, celdas):
    """Efecto como razon: observado sobre contrafactual, menos uno."""
    den = Yhat[celdas].sum()
    return float(Y[celdas].sum() / den - 1) if den > 0 else np.nan


def meses_identificados(entrada: np.ndarray, T: int, minimo: int = MIN_SIN_PROGRAMA):
    t = np.arange(T)
    sin_programa = (t[None, :] < entrada[:, None]).sum(0)
    return sin_programa >= minimo, sin_programa


def generador(semilla: int, nombre: str) -> np.random.Generator:
    """Un generador por procedimiento (auditoria/02_efecto.md m10).

    Con un solo generador global, cambiar el numero de permutaciones movia el
    intervalo bootstrap. Aqui cada procedimiento tiene su propia secuencia, fija,
    derivada de la semilla del script y del nombre del procedimiento.
    """
    import zlib
    return np.random.default_rng([semilla, zlib.crc32(nombre.encode())])


def p_permutacion(nulas, observado, tol: float = 1e-12) -> dict:
    """p de una prueba de permutacion con N sorteos: (b + 1) / (N + 1) (Phipson y Smyth 2010).

    b = sorteos con |nula| >= |observado| (dos colas por valor absoluto, la regla del
    estudio). Tambien la version de colas iguales y el error Monte Carlo del p.
    """
    nulas = np.asarray(nulas, float)
    nulas = nulas[np.isfinite(nulas)]
    N = len(nulas)
    b = int((np.abs(nulas) >= abs(observado) - tol).sum())
    p = (b + 1) / (N + 1)
    alta = ((nulas >= observado - tol).sum() + 1) / (N + 1)
    baja = ((nulas <= observado + tol).sum() + 1) / (N + 1)
    return {"p": p, "b": b, "n": N, "ee_mc": float(np.sqrt(p * (1 - p) / N)),
            "p_colas_iguales": float(min(1.0, 2 * min(alta, baja)))}


# ----------------------------------------------------------------- salida
def sin_nan(o):
    """JSON no admite NaN: un efecto no identificado se escribe como null."""
    if isinstance(o, dict):
        return {k: sin_nan(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [sin_nan(v) for v in o]
    if isinstance(o, (float, np.floating)):
        return None if not np.isfinite(o) else float(o)
    return o


def guardar_json(obj, carpeta: str, nombre: str = "resultados.json"):
    destino = ROOT / "grafs" / carpeta
    destino.mkdir(parents=True, exist_ok=True)
    ruta = destino / nombre

    def conv(o):
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, np.bool_):
            return bool(o)
        if isinstance(o, (np.floating,)):
            return None if np.isnan(o) else round(float(o), 6)
        if isinstance(o, (dt.date, dt.datetime)):
            return o.isoformat()
        if isinstance(o, np.ndarray):
            return o.tolist()
        raise TypeError(type(o))

    ruta.write_text(json.dumps(sin_nan(obj), ensure_ascii=False, indent=1, default=conv, allow_nan=False))
    print(f"  [json] {ruta.relative_to(ROOT)}")
    return ruta
