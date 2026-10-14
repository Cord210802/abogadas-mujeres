# Abogadas de las Mujeres en el Ministerio Público de la CDMX

Evaluación del programa Abogadas de las Mujeres, que desde marzo de 2019 asigna abogadas de la Secretaría de
las Mujeres a las agencias del Ministerio Público de la Ciudad de México. La pregunta es si el programa hizo
que se abrieran más carpetas de investigación por violencia familiar y si los datos alcanzan para saberlo.

Caso de titulación, ITAM. Juan Pablo Cordero Mayorga.

Repositorio: <https://github.com/Cord210802/abogadas-mujeres>

**Resultado.** En las agencias con abogadas se observaron 27.7% más carpetas de violencia familiar de las
esperadas (2,793 contra 2,187, de marzo a mayo de 2019). No se puede atribuir al programa de forma
concluyente. Todo el aumento viene de las agencias que entraron en marzo. Las agencias de comparación
también cambiaron en esos meses. Además, con este despliegue solo se detectan con confianza aumentos de 32%
o más.

## Qué hay en este repositorio

| Carpeta | Qué contiene |
|---|---|
| `reporte/` | El reporte escrito (`reporte.qmd` y su PDF). Cada cifra del texto se lee de `grafs/abogadas/*/resultados.json` |
| `dashboard/` | Aplicación web con el estudio narrado (`/abogadas`) y el método (`/metodologia`) |
| `presentation/` | La presentación de la defensa (Reveal.js) |
| `scripts/abogadas/` | El análisis completo, en cinco pasos (A01 a A05) |
| `scripts/` | Descarga y normalización de los datos públicos de los que parte el análisis |
| `grafs/abogadas/` | Los resultados del análisis (`resultados.json` por paso). De aquí leen el reporte y el dashboard |
| `data/` | Los tres archivos de entrada del análisis, ya listos para usarse |

Ninguna cifra del reporte ni del dashboard se escribe a mano. Todas salen de los `resultados.json`, que
produce el análisis con semillas fijas. La presentación tiene sus cifras escritas en el HTML, copiadas de
esos mismos archivos.

```
scripts/abogadas/run.py  ->  grafs/abogadas/*/resultados.json  ->  reporte/reporte.qmd
                                                               ->  dashboard/data_prep_abogadas.py  ->  dashboard
```

## Requisitos

Python 3.9 (probado con 3.9.6). Para el PDF del reporte hace falta [Quarto](https://quarto.org) con una
instalación de LaTeX.

```bash
pip3 install -r requirements.txt
```

## Cómo reproducirlo

Todos los comandos se corren desde la raíz del repositorio.

```bash
python3 scripts/abogadas/run.py            # análisis completo A01 a A05, unos 8 minutos
python3 dashboard/data_prep_abogadas.py    # arma el JSON del dashboard
cd reporte && quarto render reporte.qmd    # reporte en PDF
```

El primer comando vuelve a escribir los `resultados.json` y las gráficas de `grafs/abogadas/`. Con los datos
de `data/`, los resultados salen idénticos a los del reporte.

## Ver el dashboard y la presentación

```bash
python3 dashboard/app.py            # dashboard en http://127.0.0.1:5050
python3 presentation/serve.py       # presentación en http://127.0.0.1:5051
```

`presentation/serve.py` no necesita Flask. También se puede usar `python3 presentation/app.py`.
`netlify.toml` publica la presentación como sitio estático.

## Los datos

El análisis lee tres archivos. Todos vienen de fuentes públicas.

| Archivo | Fuente | Cómo se obtiene desde cero |
|---|---|---|
| `data/raw/abogadas/atenciones_abogadas_mujeres.csv` | Registro de atenciones de las Abogadas de las Mujeres, portal de datos abiertos de la CDMX | `python3 scripts/download.py --only abogadas_atenciones --only abogadas_diccionario` |
| `data/interim/fgj_carpetas.parquet` | Carpetas de investigación de la Fiscalía General de Justicia de la CDMX | `python3 scripts/download.py --only carpetasFGJ_acumulado` y después `python3 scripts/normalize.py fgj_carpetas`. El CSV original pesa unos 560 MB |
| `data/interim/cnpje/cnpje_carpetas_delitos.parquet` | Censo Nacional de Procuración de Justicia Estatal (INEGI), 2020 a 2024 | Los `.zip` se bajan del sitio del INEGI a `data/raw/cnpje/`. Después `python3 scripts/cnpje_normalize.py` |

`scripts/sources.py` registra la dirección exacta de cada descarga. Los archivos de `data/` son los que se
usaron para el reporte. Sus huellas SHA-256 empiezan así:

| Archivo | SHA-256 |
|---|---|
| `atenciones_abogadas_mujeres.csv` | `4b3bb4ffe0bab6ff…` |
| `fgj_carpetas.parquet` | `b2f2dca76a20ca66…` |
| `cnpje_carpetas_delitos.parquet` | `bbc241abaa456783…` |

`dashboard/static/data/alcaldias.geojson` es el contorno de las alcaldías para el mapa del dashboard. Es un
mapa base, no un resultado.

## El análisis, paso por paso

| Paso | Script | Qué hace |
|---|---|---|
| A01 | `a01_limpieza.py` | Limpia el registro del programa, reconstruye la fecha de llegada de cada agencia y arma el panel de 54 unidades por 38 meses |
| A02 | `a02_efecto.py` | Estima el efecto con el método de imputación de Borusyak, Jaravel y Spiess (2024), la prueba de permutación estratificada, los intervalos, las tendencias previas y los placebos |
| A03 | `a03_programa.py` | La conversión del programa, su descomposición, el embudo por agencia y el riesgo de feminicidio |
| A04 | `a04_evaluabilidad.py` | El techo lógico, la potencia por simulación, el efecto mínimo detectable y la simulación por estados |
| A05 | `a05_quiebres.py` | El detector de puntos de cambio (PELT) por unidad, con su prueba de permutación |

Las funciones compartidas (el ajuste Poisson, la permutación, el formato de las gráficas) están en
`scripts/abogadas/_comun.py` y `scripts/_viz.py`.
