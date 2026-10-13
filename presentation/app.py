"""Presentación del caso con Flask.

    python3 app.py          -> http://localhost:5051

Sin Flask, serve.py sirve los mismos archivos con la biblioteca estándar.
Netlify publica la versión estática (ver netlify.toml).
"""

from flask import Flask, render_template

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5051, debug=False)
