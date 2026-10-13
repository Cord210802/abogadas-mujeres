"""Corre el estudio de Abogadas de las Mujeres completo, en orden: A01 -> A05.

    python3 scripts/abogadas/run.py

Cada paso lee lo que dejo el anterior en data/interim/abogadas/ y grafs/abogadas/.
La explicacion de cada paso esta en docs/abogadas/.
"""
import runpy
import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

PASOS = ["a01_limpieza.py", "a02_efecto.py", "a03_programa.py", "a04_evaluabilidad.py", "a05_quiebres.py"]

if __name__ == "__main__":
    for paso in PASOS:
        t = time.time()
        runpy.run_path(str(AQUI / paso), run_name="__main__")
        print(f"  ({paso}: {time.time() - t:.1f} s)\n")
