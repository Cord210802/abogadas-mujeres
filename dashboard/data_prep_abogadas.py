"""Arma static/data/abogadas.json con los resultados del estudio de Abogadas de las Mujeres.

No calcula ningun resultado: copia lo que escribieron scripts/abogadas/a0*.py en
grafs/abogadas/*/resultados.json y lo acomoda para las graficas. Lo unico que hace
es agrupar en barras la distribucion de permutacion para dibujarla.

    python3 scripts/abogadas/run.py        # primero
    python3 dashboard/data_prep_abogadas.py
"""
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
G = ROOT / "grafs" / "abogadas"
SALIDA = ROOT / "dashboard" / "static" / "data" / "abogadas.json"


def leer(carpeta):
    return json.loads((G / carpeta / "resultados.json").read_text())


def quiebres(a5):
    """Puntos de cambio (A05, PELT): la ciudad por segmentos y los quiebres por agencia.

    Solo reacomoda: la distribucion de permutacion se cuenta por numero de agencias.
    """
    if a5 is None:
        return None
    ag = a5["agencias"]
    n_u = len(ag["unidades"])

    def delito(d):
        nul = np.rint(np.array(d["nula_valores"]) * n_u).astype(int)
        return {
            "unidades_con_quiebre_en_llegada": d["unidades_con_quiebre_en_llegada"],
            "proporcion": d["estadistico"], "p": d["p"],
            "nula_media": d["nula_media"], "nula_p95": d["nula_p95"],
            "nula_conteo": np.bincount(nul, minlength=n_u + 1)[: max(int(nul.max()), d["unidades_con_quiebre_en_llegada"]) + 2].tolist(),
            "quiebres_totales": d["quiebres_totales"], "al_alza": d["al_alza"],
            "por_e": d["por_e"], "por_mes": d["por_mes"], "por_cohorte": d["por_cohorte"],
            "sensibilidad_k": {k: {"proporcion": v["observado"], "p": v["p"]} for k, v in d["sensibilidad_k"].items()},
            "sensibilidad_ventana": {k: {"proporcion": v["observado"], "p": v["p"]} for k, v in d["sensibilidad_ventana"].items()},
            "placebo_temporal": d.get("placebo_temporal"), "por_e_separado": d.get("por_e_separado"),
            "magnitudes_en_ventana": d.get("magnitudes_en_ventana"), "a_la_baja": d.get("a_la_baja"),
            "westfall_young": {k: v for k, v in d.get("westfall_young", {}).items() if k != "p_por_especificacion"},
            "unidades_con_algun_quiebre": d.get("unidades_con_algun_quiebre"), "n_perm": d.get("n_perm"),
            "detalle": [{"unidad": u["unidad"], "entrada": u["entrada"], "quiebres": u["quiebres"]} for u in d["detalle"]],
        }

    c = a5["ciudad"]
    v = a5["validacion"]
    return {
        "metodo": {k: a5["metodo"][k] for k in ("k_ciudad", "k_agencias", "min_segmento", "fp_objetivo")},
        "ciudad": {
            "meses": c["meses"], "observado": c["observado"], "desestacionalizado": c["desestacionalizado"],
            "ajustado": c["ajustado"], "quiebres": c["quiebres"], "segmentos": c["segmentos"],
            "phi": c["phi_diferencias"], "k": c["k"],
            "sensibilidad": {k: c["sensibilidad"][k] for k in ("por_k", "k_rango_por_quiebre", "con_phi_pearson",
                                                               "sin_desestacionalizar", "costo_normal_anscombe")},
        },
        "agencias": {"n": n_u, "ventana_e": ag["ventana_e"], "vf": delito(ag["vf"]), "robos": delito(ag["robos"])},
        "validacion": {
            "exactitud": {"series": v["exactitud"]["pelt_vs_dp"]["series"],
                          "iguales_a_dp": v["exactitud"]["pelt_vs_dp"]["mismo_optimo"],
                          "series_enumeracion": v["exactitud"]["vs_enumeracion"]["series"],
                          "iguales_a_enumeracion": v["exactitud"]["vs_enumeracion"]["mismo_optimo"],
                          "ahorro_evaluaciones": v["exactitud"]["pelt_vs_dp"]["ahorro_evaluaciones"]},
            "falsos": {"agencias": v["falsos_agencias"]["tasa_con_algun_quiebre_por_k"],
                       "ciudad": v["falsos_ciudad"]["tasa_con_algun_quiebre_por_k"],
                       "ciudad_sin_escalar_por_phi": v["falsos_ciudad"]["tasa_k2_sin_escalar_por_phi"],
                       "ciudad_sin_desestacionalizar": v["falsos_ciudad"]["tasa_k2_sin_desestacionalizar"]},
            "recuperacion_ciudad": v["recuperacion_ciudad"],
            "potencia": {n: {"nivel": f["nivel"],
                             "saltos": {r: s["detecta_en_mas_menos_1"] for r, s in f["saltos"].items()}}
                         for n, f in v["potencia_agencia"]["niveles"].items()},
            "prueba": {n: {"rechaza_al_5": e["rechaza_al_5"], "proporcion_media": e["estadistico_medio"]}
                       for n, e in v["prueba_por_agencia"].items()},
            "falsos_escenarios": {k: e["tasa_por_k"] for k, e in v.get("falsos_agencias_escenarios", {}).items()},
        },
    }


def main():
    a1, a2, a3, a4 = leer("01_limpieza"), leer("02_efecto"), leer("03_programa"), leer("04_evaluabilidad")
    a5 = leer("05_quiebres") if (G / "05_quiebres" / "resultados.json").exists() else None
    por_mes = a1["por_mes"]
    conv = {r["unidad"]: r for r in a3["embudo"]["tabla"]}

    unidades = []
    for u in a1["unidades"]["tabla"]:
        if u.get("lat") is None:
            continue
        c = conv.get(u["unidad"])
        unidades.append({"unidad": u["unidad"], "alcaldia": u["alcaldia"], "entrada": u["entrada"],
                         "lat": u["lat"], "lon": u["lon"], "atenciones": u["atenciones"],
                         "codigos": u["codigos_fgj"], "conversion": c["conv"] if c else None,
                         "en_analisis": u["unidad"] in a2["panel"]["unidades"]})

    r = a2["resultados"]
    nul = np.array(r["vf"]["nulas_por_tamano"]) * 100
    bordes = np.arange(np.floor(nul.min() / 2) * 2, np.ceil(nul.max() / 2) * 2 + 2, 2)
    conteo, _ = np.histogram(nul, bordes)

    out = {
        "resumen": {
            "atenciones": a1["crudo"]["filas"],
            "carpetas_programa": int(sum(m["si"] for m in por_mes)),
            "unidades": a1["unidades"]["n"],
            "unidades_analisis": a2["unidades_en_muestra"],
            "etiquetas_programa": a1.get("etiquetas_programa", {}).get("n", 79),
            "codigos_fgj": a1["unidades"]["codigos_fgj"],
            "meses_medibles": len(a2["meses_identificados"]),
            "hueco_meses": a1["hueco_no"]["n_meses"],
            "hueco_atenciones": a1["hueco_no"]["atenciones_en_hueco"],
            "colima_pct": a1["colima"]["pct_desde"],
            "riesgo_desde": a1["riesgo_primer_mes_capturado"],
            "validacion": a1["validacion_vf"],
            "hueco": {k: a1["hueco_no"][k] for k in ("tramos", "no_en_hueco", "na_fuera_del_hueco", "descripcion")},
            "celdas_faltantes": a2.get("celdas_faltantes"),
            "vf_ciudad_en_territoriales": a1.get("vf_ciudad_en_territoriales"),
        },
        "despliegue": {
            "unidades": unidades,
            "sin_programa_por_mes": a2["sin_programa_por_mes"],
            "cohortes": a2["cohortes"],
            "balance": a2["balance"],
        },
        "por_mes_programa": [{"mes": m["mes"], "si": m["si"], "no": m["no"], "na": m["na"],
                              "atenciones": m["atenciones"], "unidades": m["unidades"]} for m in por_mes],
        "ciudad": a2["ciudad"],
        "efecto": {
            k: {"efecto": v["efecto"], "ic95": v["ic95"], "p": v["p_permutacion_por_tamano"],
                "adelantos_total": v["adelantos_total"],
                "evento": [{"e": d["e"], "efecto": d["efecto"]} for d in v["adelantos"] + v["por_evento"]],
                "observado": v["observado"], "contrafactual": v["contrafactual"]}
            for k, v in r.items()
        },
        "permutacion": {"bordes": bordes.tolist(), "conteo": conteo.tolist(),
                        "observado": r["vf"]["efecto"] * 100, "p": r["vf"]["p_permutacion_por_tamano"],
                        # Repartos que llegan tan lejos como el observado, por lado (misma
                        # tolerancia que C.p_permutacion). Suman inferencia.permutacion_por_tamano.b.
                        # Las barras de 2 puntos no lo dicen solas: dos cruzan la linea.
                        "cola_alta": int((nul / 100 >= r["vf"]["efecto"] - 1e-12).sum()),
                        "cola_baja": int((nul / 100 <= -r["vf"]["efecto"] + 1e-12).sum())},
        "por_cohorte": a2["por_cohorte"],
        "metodologia": a2["metodologia"],
        "robustez": a2["robustez"],
        # inferencia y pruebas agregadas tras la auditoria (auditoria/07_cambios_aplicados.md)
        "inferencia": {
            "p_sin_estratos": r["vf"]["p_permutacion"],
            "permutacion_por_tamano": r["vf"]["permutacion_por_tamano"],
            "sensibilidad_estratos": {k: {"p": v["p"], "ee_mc": v["ee_mc"],
                                                          "p_colas_iguales": v["p_colas_iguales"]}
                                      for k, v in a2["permutacion_sensibilidad_estratos"].items()},
            "bootstrap": r["vf"]["bootstrap"], "inversion": a2["inversion_permutacion"], "jackknife": a2["jackknife"],
            "nula_abs_q95": r["vf"]["nulas_abs_q95"], "phi_imputacion": r["vf"]["phi_imputacion"],
        },
        "diseno": {
            "tendencias_previas": a2["tendencias_previas_bjs"],
            "placebos_en_el_tiempo": {k: {kk: vv for kk, vv in v.items()} for k, v in a2["placebos_en_el_tiempo"].items()},
            "contraste_controles": a2["contraste_controles"],
            "ventanas_entrenamiento": a2["ventanas_entrenamiento"],
            "regla_exclusion": a2["regla_exclusion"],
            "regla_exclusion_ventana_completa": {
                "unidades": a2["regla_exclusion_ventana_completa"]["unidades_en_muestra"],
                "efecto": a2["regla_exclusion_ventana_completa"]["resultados"]["vf"]["efecto"],
                "celdas": a2["regla_exclusion_ventana_completa"]["resultados"]["vf"]["celdas_tratadas"],
                "p": a2["regla_exclusion_ventana_completa"]["resultados"]["vf"]["p_permutacion_por_tamano"],
                "ic95": a2["regla_exclusion_ventana_completa"]["resultados"]["vf"]["ic95"],
                "robos": a2["regla_exclusion_ventana_completa"]["resultados"]["robos"]["efecto"]},
        },
        "panel": a2["panel"],
        "programa": {
            "serie": a3["serie"], "periodos": a3["periodos"], "descomposicion": a3["descomposicion"],
            "auc": a3["modelo"]["auc"], "modelo_n": [a3["modelo"]["n_entrenamiento"], a3["modelo"]["n_prueba"]],
            "embudo": a3["embudo"], "riesgo": a3["riesgo"],
            "auc_con_tipo_sede": a3["modelo_con_tipo_sede"]["auc"],
            "auc_dentro_de_agencia": a3["modelo"]["auc_dentro_de_agencia"],
            "calibracion_fuera_de_tiempo": a3["modelo"]["calibracion_fuera_de_tiempo"],
            "descomposicion_bases": a3["descomposicion_bases"], "registro_vacio": a3["registro_vacio"],
        },
        "evaluabilidad": {
            "techo": {k: v for k, v in a4["techo"].items() if k != "por_mes"},
            "pisos": {d: {"mde": v["mde"], "potencia": v["potencia"], "nula_ic95": v["nula_ic95"],
                          "celdas": v["celdas_tratadas_identificadas"],
                          "mde_interpolado": v["mde_interpolado"], "mde_interpolado_ic_mc": v["mde_interpolado_ic_mc"],
                          "nula_abs_q95": v["nula_abs_q95"],
                          "ventanas": {k: a4["pisos_por_ventana"][d][k] for k in ("ventanas", "minimo", "mediana", "maximo")}}
                      for d, v in a4["pisos"].items()},
            # El despliegue tal como ocurrio: conserva la fecha real de cada agencia, asi que la
            # composicion por tercil de tamano es la observada. pisos["real"] solo conserva los
            # tamanos de las tandas y reparte las agencias en orden alfabetico (otro despliegue
            # posible, no el que paso). Es la cifra que usan el reporte y las dos paginas.
            "composicion_observada": {
                "mde": a4["pisos_composicion_observada"]["mde"],
                "potencia": a4["pisos_composicion_observada"]["potencia"],
                "nula_ic95": a4["pisos_composicion_observada"]["nula_ic95"],
                "celdas": a4["pisos_composicion_observada"]["celdas_tratadas_identificadas"],
                "mde_interpolado": a4["pisos_composicion_observada"]["mde_interpolado"],
                "mde_interpolado_ic_mc": a4["pisos_composicion_observada"]["mde_interpolado_ic_mc"],
                "nula_abs_q95": a4["pisos_composicion_observada"]["nula_abs_q95"],
                "replicas_por_efecto": a4["pisos_composicion_observada"]["replicas_por_efecto"],
                "ventanas": {k: a4["pisos_por_ventana"]["real_composicion_observada"][k]
                             for k in ("ventanas", "minimo", "mediana", "maximo")}},
            # Periodo sin programa y fecha ficticia de llegada de la simulacion de potencia (/metodologia).
            "mundo_simulado": {k: a4["mundo_simulado"][k] for k in ("meses", "inicio_simulado", "ventanas")},
            "techo_celdas_del_estimando": {k: v for k, v in a4["techo_celdas_del_estimando"].items()},
            "techo_muestra": {k: v for k, v in a4["techo_muestra_a02"].items()},
            "estados": {"mde": a4["expansion_estados"]["mitad_y_mitad"]["mde"],
                        "potencia": a4["expansion_estados"]["mitad_y_mitad"]["potencia"],
                        "n": a4["expansion_estados"]["estados"], "anios": a4["expansion_estados"]["anios"],
                        "mde_interpolado": a4["expansion_estados"]["mitad_y_mitad"]["mde_interpolado"],
                        "dilucion": a4["expansion_estados"]["dilucion"],
                        "sin_series_rotas": a4["expansion_estados"]["sin_series_rotas"]["mde_interpolado"]},
            "deriva": a4["deriva_sin_programa"],
            "efecto_estimado": a4["efecto_estimado_a02"],
            "diagnostico": a4["diagnostico_estimadores_de_nula"],
        },
        "quiebres": quiebres(a5),
    }
    SALIDA.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
    print(f"  {SALIDA.relative_to(ROOT)}  ({SALIDA.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
