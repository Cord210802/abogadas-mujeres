"""Dashboard del caso de titulación — Abogadas de las Mujeres en la CDMX.

Dos vistas sobre la evaluación del programa: la historia (/abogadas) y cómo se construye
el número (/metodologia). La app no recalcula nada: solo presenta lo que escribió
`data_prep_abogadas.py` en static/data/abogadas.json.

    python3 scripts/abogadas/run.py
    python3 dashboard/data_prep_abogadas.py
    python3 dashboard/app.py
"""
import json
import os
from pathlib import Path

from flask import Flask, redirect, render_template, url_for

BASE = Path(__file__).resolve().parent
app = Flask(__name__, static_folder=str(BASE / "static"), template_folder=str(BASE / "templates"))


def _cifras():
    # Ninguna plantilla escribe numeros: todos vienen de este JSON.
    return json.loads((BASE / "static" / "data" / "abogadas.json").read_text())


@app.route("/")
def inicio():
    return redirect(url_for("abogadas"))


@app.route("/abogadas")
def abogadas():
    return render_template("abogadas.html", activo="abogadas", c=_cifras())


@app.route("/metodologia")
def metodologia():
    # Explica como se construye el contrafactual; lee el mismo JSON que /abogadas.
    return render_template("metodologia.html", activo="metodologia", c=_cifras())


# Rutas de la pregunta anterior (Denuncia Digital), retiradas del producto. Si quedó un
# enlace abierto en algún lado, lleva a la pregunta vigente.
@app.route("/asesor")
@app.route("/investigacion")
@app.route("/mapa")
@app.route("/graficas")
def _retiradas():
    return redirect(url_for("abogadas"))


if __name__ == "__main__":
    # Apagado por defecto: con el depurador encendido, un error cualquiera muestra
    # el codigo fuente y una consola en la pantalla proyectada. DEBUG=1 para editar.
    app.run(debug=os.environ.get("DEBUG") == "1", port=5050)
