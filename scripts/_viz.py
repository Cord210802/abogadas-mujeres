"""Configuracion compartida de graficas.

Implementa la guia de estilo del proyecto (.claude/skills/graficas):
todo en azul salvo lo que se quiere resaltar, que va en rojo.
Cada analisis en scripts/h*/ importa de aqui para que todas las
figuras del proyecto se vean iguales.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

BLUE       = "#4a6fa5"   # principal
BLUE_LIGHT = "#a8bfcf"   # secundario / comparacion suave
BLUE_DARK  = "#2c4a6e"   # enfasis dentro del mismo grupo
BLUE_MID   = "#6a8caf"   # series adicionales
BLUE_PALE  = "#c5d4e8"   # areas rellenas
RED        = "#8b0000"   # UNICO uso: KPI, maximo, anomalia, referencia

ROOT  = Path(__file__).resolve().parents[1]
GRAFS = ROOT / "grafs"

plt.rcParams.update({
    "font.size": 10,
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif"],
    "axes.edgecolor": "#000",
    "axes.labelcolor": "#000",
    "xtick.color": "#000",
    "ytick.color": "#000",
    "text.color": "#000",
    "figure.facecolor": "white",
    "axes.facecolor": "white",
})


def miles(ax, eje="y"):
    """Separador de miles en el eje indicado."""
    fmt = mticker.FuncFormatter(lambda x, _: f"{int(x):,}")
    (ax.yaxis if eje == "y" else ax.xaxis).set_major_formatter(fmt)


def pct(ax, eje="y", dec=0):
    fmt = mticker.FuncFormatter(lambda x, _: f"{x:.{dec}f}%")
    (ax.yaxis if eje == "y" else ax.xaxis).set_major_formatter(fmt)


def guardar(fig, carpeta, nombre, nota=None):
    """Guarda en grafs/<carpeta>/<nombre>.png con la nota de fuente al pie."""
    if nota:
        fig.text(0.0, -0.02, nota, ha="left", va="top", fontsize=7.5, color="#444")
    fig.tight_layout()
    destino = GRAFS / carpeta
    destino.mkdir(parents=True, exist_ok=True)
    ruta = destino / f"{nombre}.png"
    fig.savefig(ruta, dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(f"  [graf] {ruta.relative_to(ROOT)}")
    return ruta
