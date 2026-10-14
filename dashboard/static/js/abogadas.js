// Abogadas de las Mujeres: la historia en cinco actos.
// Todo número sale de /static/data/abogadas.json. Aquí solo se dibuja: nada se estima.
// Paleta con significado, la misma de la presentación:
// verde = observado o programa, pizarra = esperado, azar o comparación, ámbar = cautela.
// Blanco solo para texto, la marca de llegada y la línea del cero.
const VERDE = "#5CC46E";
const VERDE_FONDO = "rgba(92, 196, 110, 0.18)";
const PIZARRA = "#7D93B2";
const PIZARRA_CLARO = "#B7C6DB";
const PIZARRA_FONDO = "rgba(125, 147, 178, 0.20)";
const AMBAR = "#F5A524";
const AMBAR_FONDO = "rgba(245, 165, 36, 0.16)";
const TINTA = "#F4F4F4";
const LLEGADA = "rgba(244, 244, 244, 0.85)";

// Nombres legibles: la alcaldía, nunca el código de la Fiscalía.
// Si una alcaldía tiene varias unidades, se numeran dentro de ella: "Cuauhtémoc (3 de 8)".
const NOMBRE = {}, ALCALDIA = {};
function prepararNombres(D) {
  const por = {};
  D.despliegue.unidades.forEach((u) => (por[u.alcaldia] ||= []).push(u));
  Object.values(por).forEach((us) => us.sort((a, b) => a.unidad.localeCompare(b.unidad)).forEach((u, i) => {
    const nom = us.length === 1 ? u.alcaldia : `${u.alcaldia} (${i + 1} de ${us.length})`;
    [u.unidad, ...u.codigos].forEach((k) => { NOMBRE[k] = nom; ALCALDIA[k] = u.alcaldia; });
  }));
}
const nombre = (k) => NOMBRE[k] ?? k;

Chart.defaults.font.family = "'DM Sans', system-ui, sans-serif";
Chart.defaults.font.size = 13;
Chart.defaults.color = "#C6C6C6";
Chart.defaults.maintainAspectRatio = false;
Chart.defaults.scale.grid.color = "#262626";
Chart.defaults.scale.border.display = false;
Chart.defaults.plugins.legend.labels.boxWidth = 12;
Chart.defaults.plugins.legend.labels.boxHeight = 12;
Chart.defaults.datasets.line.backgroundColor = (ctx) => ctx.dataset.borderColor;
Chart.defaults.scales.category.ticks.maxRotation = 0;
Chart.defaults.scales.category.ticks.autoSkipPadding = 10;

const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const fmtMes = (m) => `${MESES[+m.slice(5, 7) - 1]} ${m.slice(0, 4)}`;
const pct = (x, d = 0) => `${(x * 100).toFixed(d).replace("-", "−")}%`;
const signo = (x, d = 0) => `${x >= 0 ? "+" : "−"}${Math.abs(x * 100).toFixed(d)}%`;
const miles = (x) => Math.round(x).toLocaleString("es-MX");
// Las llaves de potencia vienen de Python: "0.05", "0.1", ..., "1.0".
// Coincidencia exacta por valor: redondear la llave con toFixed(1) hacía que 0.35 leyera la
// potencia de 0.3 en la rejilla por estados, que no simuló 35%. Sin llave, no hay dato.
const potDe = (pot, r) => {
  const k = Object.keys(pot).find((x) => Math.abs(Number(x) - r) < 1e-9);
  return k === undefined ? undefined : pot[k];
};

// Crea cada gráfica cuando entra a la pantalla, para que su animación se vea al leer.
function alVer(el, fn, umbral = 0.25) {
  if (!el) return;
  const obs = new IntersectionObserver((ents) => {
    ents.forEach((e) => { if (e.isIntersecting) { obs.disconnect(); fn(); } });
  }, { threshold: umbral });
  obs.observe(el);
}

// Línea vertical punteada con etiqueta en un eje de categorías.
function lineaVertical(etiquetas, valor, texto, color = LLEGADA) {
  return {
    id: `v-${Math.random().toString(36).slice(2)}`,
    afterDatasetsDraw(chart) {
      const i = etiquetas.indexOf(valor);
      if (i === -1) return;
      const { ctx, chartArea, scales } = chart;
      const x = scales.x.getPixelForValue(i);
      ctx.save();
      ctx.setLineDash([5, 4]); ctx.lineWidth = 1.6; ctx.strokeStyle = color;
      ctx.beginPath(); ctx.moveTo(x, chartArea.top); ctx.lineTo(x, chartArea.bottom); ctx.stroke();
      if (texto) {
        ctx.setLineDash([]); ctx.fillStyle = color; ctx.font = "600 12px 'DM Sans', sans-serif";
        ctx.fillText(texto, x + 6, chartArea.top + 14);
      }
      ctx.restore();
    },
  };
}

// Valor escrito al final de cada barra: el lector no tiene que ir al eje.
function valoresEnBarras(fmt, color = TINTA) {
  return {
    id: `vb-${Math.random().toString(36).slice(2)}`,
    afterDatasetsDraw(chart) {
      const { ctx } = chart; const horiz = chart.options.indexAxis === "y";
      chart.data.datasets.forEach((ds, k) => {
        if (!chart.isDatasetVisible(k)) return;
        chart.getDatasetMeta(k).data.forEach((bar, i) => {
          const v = ds.data[i]; if (v == null || Array.isArray(v)) return;
          ctx.save(); ctx.fillStyle = color; ctx.font = "700 12px 'DM Sans', sans-serif";
          if (horiz) { ctx.textBaseline = "middle"; ctx.textAlign = "left"; ctx.fillText(fmt(v), v >= 0 ? bar.x + 6 : bar.base + 6, bar.y); } // negativos: junto al cero, lejos de las etiquetas del eje
          else { ctx.textAlign = "center"; ctx.fillText(fmt(v), bar.x, v >= 0 ? bar.y - 6 : bar.y + 14); }
          ctx.restore();
        });
      });
    },
  };
}
const fmtPct = (v) => `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(0)}%`;

// Etiqueta al final de cada línea en lugar de leyenda.
function etiquetasAlFinal(pares) {
  return {
    id: `ef-${Math.random().toString(36).slice(2)}`,
    afterDatasetsDraw(chart) {
      const { ctx, chartArea } = chart;
      pares.forEach(([k, texto, dy = -8]) => {
        const pts = chart.getDatasetMeta(k).data; const p = pts[pts.length - 1]; if (!p) return;
        ctx.save(); ctx.fillStyle = chart.data.datasets[k].borderColor; ctx.font = "700 12px 'DM Sans', sans-serif";
        ctx.textAlign = "right"; ctx.fillText(texto, chartArea.right - 4, p.y + dy); ctx.restore();
      });
    },
  };
}

// ============================================================== ACTO 1: mapa
function actoDespliegue(D) {
  const unidades = D.despliegue.unidades;
  const meses = ["2019-02", "2019-03", "2019-04", "2019-05", "2019-06", "2019-07", "2019-08", "2019-09"];
  const sinProg = D.despliegue.sin_programa_por_mes;
  const n = D.resumen.unidades_analisis;
  const textos = {
    "2019-02": `Antes del programa. Ninguna de las ${D.resumen.unidades} unidades territoriales tiene abogadas.`,
    "2019-03": "4 de marzo: arranca el programa. Llega sobre todo a las agencias más grandes.",
    "2019-04": "Un mes después ya está en más de la mitad de las agencias.",
    "2019-05": `Quedan ${sinProg["2019-05"]} unidades sin abogadas. Es el último mes con suficientes para comparar.`,
    "2019-06": `Solo ${sinProg["2019-06"]} unidades siguen sin programa, menos de las ${D.metodologia.minimo_sin_programa} que exige el método: ya no alcanza para comparar.`,
    "2019-07": `Queda ${sinProg["2019-07"]}.`,
    "2019-08": "Agosto: todas tienen abogadas. Desde aquí no hay contra qué comparar.",
    "2019-09": "El programa sigue, pero su efecto ya no se puede medir con estos datos.",
  };

  const mapa = L.map("mapa-despliegue", { scrollWheelZoom: false, zoomSnap: 0.25 });
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© OpenStreetMap", maxZoom: 16,
  }).addTo(mapa);
  mapa.fitBounds([[19.13, -99.33], [19.59, -98.95]]);

  fetch("/static/data/alcaldias.geojson").then((r) => r.json()).then((g) => {
    L.geoJSON(g, { style: { color: "#3A3A3A", weight: 1, fillOpacity: 0 }, interactive: false }).addTo(mapa);
  });

  const maxAt = Math.max(...unidades.map((u) => u.atenciones));
  const circulos = unidades.map((u) => {
    const c = L.circleMarker([u.lat, u.lon], { radius: 5 + 13 * Math.sqrt(u.atenciones / maxAt), weight: 1.5 }).addTo(mapa);
    const conv = u.conversion === null ? "sin dato" : pct(u.conversion);
    c.bindTooltip(`<b>${nombre(u.unidad)}</b><br>Llegan las abogadas: ${fmtMes(u.entrada)}<br>` +
      `${miles(u.atenciones)} atenciones · conversión ${conv}`);
    return { u, c };
  });

  const slider = document.getElementById("slider-mes");
  const btn = document.getElementById("btn-play");
  let timer = null;

  function pintar(i) {
    const mes = meses[i];
    let con = 0;
    circulos.forEach(({ u, c }) => {
      if (u.entrada > mes) {
        c.setStyle({ color: PIZARRA, fillColor: PIZARRA, fillOpacity: 0.12, opacity: 0.9 });
      } else if (u.entrada === mes) {
        c.setStyle({ color: TINTA, fillColor: VERDE, fillOpacity: 0.95, opacity: 1, weight: 2.5 }); con++;
        c.bringToFront();
      } else {
        c.setStyle({ color: VERDE, fillColor: VERDE, fillOpacity: 0.4, opacity: 1, weight: 1.5 }); con++;
      }
    });
    document.getElementById("mes-actual").textContent = fmtMes(mes);
    document.getElementById("cont-con").textContent = con;
    const sin = mes < "2019-03" ? n : (sinProg[mes] ?? 0);
    document.getElementById("cont-sin").textContent = sin;
    document.getElementById("cont-sin").classList.toggle("cautela", mes >= "2019-03" && sin < D.metodologia.minimo_sin_programa);
    document.getElementById("caption-mes").textContent = textos[mes];
    slider.value = i;
  }

  function parar() { clearInterval(timer); timer = null; btn.textContent = "▶ Reproducir"; }
  btn.addEventListener("click", () => {
    if (timer) return parar();
    let i = +slider.value >= meses.length - 1 ? 0 : +slider.value;
    pintar(i);
    btn.textContent = "❚❚ Pausa";
    timer = setInterval(() => {
      i += 1;
      if (i >= meses.length) return parar();
      pintar(i);
    }, 1300);
  });
  slider.addEventListener("input", () => { parar(); pintar(+slider.value); });
  pintar(0);
  // La primera vez que el mapa entra a la pantalla, se reproduce solo.
  alVer(document.getElementById("mapa-despliegue"), () => { if (!timer) btn.click(); }, 0.5);
}

// ============================================================ ACTO 2: efecto
function actoEfecto(D) {
  const c = D.ciudad;
  const etq = c.meses;
  alVer(document.getElementById("ch-ciudad"), () => new Chart(document.getElementById("ch-ciudad"), {
    type: "line",
    data: {
      labels: etq,
      datasets: [
        { label: "Banda de lo esperado", data: c.esperado.map((v, i) => v + c.banda[i]), borderColor: "transparent", pointRadius: 0, fill: false },
        { label: "Esperado con la tendencia previa", data: c.esperado.map((v, i) => v - c.banda[i]), borderColor: "transparent", backgroundColor: PIZARRA_FONDO, pointRadius: 0, fill: "-1" },
        { label: "Esperado", data: c.esperado, borderColor: PIZARRA_CLARO, borderDash: [4, 4], borderWidth: 1.4, pointRadius: 0 },
        { label: "Observado", data: c.observado, borderColor: VERDE, borderWidth: 2.6, pointRadius: 0, tension: 0.2 },
      ],
    },
    plugins: [lineaVertical(etq, "2019-03", "llegan las abogadas"), etiquetasAlFinal([[3, "observado", -10], [2, "esperado por la tendencia", 18]])],
    options: {
      layout: { padding: { top: 20, right: 8 } },
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: { filter: (i) => i.datasetIndex >= 2, callbacks: { label: (i) => `${i.dataset.label}: ${miles(i.raw)}` } },
      },
      scales: { x: { ticks: { callback: (v, i) => (etq[i].endsWith("-01") ? etq[i].slice(0, 4) : "") } },
                y: { title: { display: true, text: "Carpetas de violencia familiar / mes" } } },
    },
  }));

  // --- estudio de evento con selector de delito
  const nombres = { vf: "Violencia familiar", robos: "Robos", amenazas: "Amenazas", sexuales: "Delitos sexuales" };
  const previos = (r) => r.evento.filter((d) => d.e < 0 && d.efecto !== null).map((d) => d.e);
  const sinComp = (r) => r.evento.filter((d) => d.e < 0 && d.efecto === null).map((d) => d.e);
  const rango = (xs) => (xs.length ? `${xs[0]} a ${xs[xs.length - 1]}`.replace(/-/g, "−") : "");
  const TP = D.diseno.tendencias_previas;
  const PT = D.diseno.placebos_en_el_tiempo;
  const pies = {
    vf: (r) => `En los ${D.resumen.meses_medibles} meses después de la llegada: ${miles(r.observado)} carpetas contra ${miles(r.contrafactual)} esperadas, ${signo(r.efecto, 1)}. Antes de la llegada el cálculo principal solo puede medir los meses ${rango(previos(r))}, con ${signo(r.adelantos_total, 1)} en conjunto. Los meses ${rango(sinComp(r))} no tienen suficientes unidades sin programa para ese cálculo. Ahí los círculos ámbar son una prueba aparte de tendencias previas, con su rango al 95%. Vienen de otro modelo y no forman una sola trayectoria con las barras. Esa prueba no distingue esos meses del azar (p = ${TP.vf.K3.p_chi2.toFixed(2)} con tres meses, ${TP.vf.K6.p_chi2.toFixed(2)} con seis), pero tampoco permite descartar que ya vinieran subiendo.`,
    robos: (r) => `Prueba de control: el programa no debería afectar los robos. Suben ${signo(r.efecto)}, sin diferencia estadística clara (p = ${r.p.toFixed(2)}). Ya subían antes de la llegada (${signo(r.adelantos_total)} en los meses previos). Al fingir la llegada en ${PT.robos.n} fechas de años sin programa, los robos suben en ${PT.robos.positivos}. Es una tendencia propia de estas unidades, no un efecto de la llegada.`,
    amenazas: (r) => `Sin efecto claro (${signo(r.efecto)}, p = ${r.p.toFixed(2)}) y sin tendencia previa (${signo(r.adelantos_total)} en los meses previos).`,
    sexuales: (r) => `${signo(r.efecto)}, con muy pocos casos: estos delitos se denuncian casi siempre en la fiscalía especializada, no en estas agencias, así que no permiten evaluar.`,
  };
  let chEvento = null;
  function evento(k) {
    const r = D.efecto[k];
    const pts = r.evento.filter((d) => d.efecto !== null);
    const labels = [];
    for (let e = -6; e <= 2; e++) labels.push(e === 0 ? "llegada" : (e > 0 ? `+${e}` : `${e}`));
    const val = labels.map((_, i) => { const d = pts.find((p) => p.e === i - 6); return d ? d.efecto * 100 : null; });
    const colores = labels.map((_, i) => (i - 6 >= 0 ? VERDE : PIZARRA_CLARO));
    // Meses −3 a −1: solo los estima la prueba de tendencias previas (otro modelo), como en fig-evento del reporte.
    const K3 = D.diseno.tendencias_previas.vf.K3; // adelantos_pct y ee_log ordenados mes −1, −2, −3
    const enK3 = (e) => k === "vf" && e >= -3 && e <= -1;
    const previa = labels.map((_, i) => (enK3(i - 6) ? K3.adelantos_pct[-(i - 6) - 1] : null));
    const rangoK3 = labels.map((_, i) => {
      const e = i - 6; if (!enK3(e)) return null;
      const c = Math.log1p(K3.adelantos_pct[-e - 1] / 100), s = 1.96 * K3.ee_log[-e - 1];
      return [Math.expm1(c - s) * 100, Math.expm1(c + s) * 100];
    });
    document.getElementById("pie-evento").textContent = pies[k](r);
    const datos = {
      labels,
      datasets: [
        { label: nombres[k], data: val, backgroundColor: colores, borderRadius: 4, maxBarThickness: 38 },
        { label: "Rango al 95% de la prueba aparte", data: rangoK3, backgroundColor: AMBAR, barThickness: 2, grouped: false },
        { type: "line", label: "Prueba de tendencias previas", data: previa, showLine: false, pointRadius: 6, pointHoverRadius: 7,
          pointBackgroundColor: "rgba(0, 0, 0, 0)", pointBorderColor: AMBAR, pointBorderWidth: 2 },
      ],
    };
    if (chEvento) { chEvento.data = datos; chEvento.update(); return; }
    chEvento = new Chart(document.getElementById("ch-evento"), {
      type: "bar", data: datos,
      options: {
        plugins: { legend: { display: false },
          tooltip: { callbacks: { title: (i) => (i[0].label === "llegada" ? "Mes de llegada" : `Mes ${i[0].label}`),
                                  label: (i) => (i.datasetIndex === 1
                                    ? `rango al 95%: ${signo(i.raw[0] / 100)} a ${signo(i.raw[1] / 100)}`
                                    : i.raw === null ? "sin comparación"
                                    : `${i.raw >= 0 ? "+" : ""}${i.raw.toFixed(1)}% contra lo esperado${i.datasetIndex === 2 ? " (prueba aparte)" : ""}`) } } },
        scales: { y: { suggestedMin: -40, suggestedMax: 50, title: { display: true, text: "% contra lo esperado" }, ticks: { callback: (v) => `${v}%` } },
                  x: { title: { display: true, text: "Meses antes y después de la llegada" } } },
      },
    });
  }
  const selDel = document.getElementById("sel-delito");
  selDel.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
    selDel.querySelectorAll("button").forEach((x) => x.classList.toggle("activo", x === b));
    evento(b.dataset.k);
  }));
  alVer(document.getElementById("ch-evento"), () => evento("vf"));

  // --- permutación
  const P = D.permutacion;
  alVer(document.getElementById("ch-permutacion"), () => {
    const labels = P.conteo.map((_, i) => P.bordes[i]);
    const obs = P.observado;
    const total = P.conteo.reduce((a, b) => a + b, 0);
    new Chart(document.getElementById("ch-permutacion"), {
      type: "bar",
      data: { labels, datasets: [{ data: P.conteo, backgroundColor: labels.map((b) => (b + 2 > obs || b < -obs ? PIZARRA_CLARO : PIZARRA)), barPercentage: 1, categoryPercentage: 1 }] },
      plugins: [{
        id: "obs-perm",
        afterDatasetsDraw(chart) {
          const { ctx, chartArea, scales } = chart;
          const i = labels.findIndex((b) => obs >= b && obs < b + 2); if (i < 0) return;
          const ancho = scales.x.getPixelForValue(1) - scales.x.getPixelForValue(0);
          const x = scales.x.getPixelForValue(i) - ancho / 2 + (ancho * (obs - labels[i])) / 2;
          ctx.save(); ctx.strokeStyle = VERDE; ctx.lineWidth = 2; ctx.setLineDash([5, 4]);
          ctx.beginPath(); ctx.moveTo(x, chartArea.top); ctx.lineTo(x, chartArea.bottom); ctx.stroke();
          ctx.setLineDash([]); ctx.fillStyle = VERDE; ctx.font = "700 13px 'DM Sans', sans-serif";
          ctx.fillText(`observado ${signo(obs / 100, 1)}`, x + 6, chartArea.top + 14);
          ctx.restore();
        },
      }],
      options: {
        plugins: { legend: { display: false },
          tooltip: { callbacks: { title: (i) => `${i[0].label}% a ${+i[0].label + 2}%`, label: (i) => `${i.raw} de ${miles(total)} repeticiones` } } },
        scales: { x: { grid: { display: false }, title: { display: true, text: "Efecto que da cada sorteo de fechas" }, ticks: { autoSkip: false, callback: (v, i) => (labels[i] % 10 === 0 ? `${labels[i]}%` : "") } },
                  y: { display: false } },
      },
    });
  });

  sorteoEnVivo(D);

  // --- cohortes
  alVer(document.getElementById("ch-cohortes"), () => {
    const co = D.por_cohorte;
    new Chart(document.getElementById("ch-cohortes"), {
      type: "bar",
      data: { labels: co.map((d) => `Llegaron en ${fmtMes(d.cohorte)} · ${d.unidades} unidades`),
              datasets: [{ data: co.map((d) => d.efecto * 100), backgroundColor: VERDE, borderRadius: 4, maxBarThickness: 56 }] },
      plugins: [valoresEnBarras((v) => `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(1)}%`)],
      options: { indexAxis: "y",
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (i) => `${i.raw >= 0 ? "+" : ""}${i.raw.toFixed(1)}% contra lo esperado` } } },
        scales: { x: { ticks: { callback: (v) => `${v}%` }, title: { display: true, text: "% contra lo esperado" } } } },
    });
  });

  // --- tres intervalos de confianza
  const I = D.inferencia;
  alVer(document.getElementById("ch-intervalos"), () => {
    const filas = [
      ["Inversión de la permutación", I.inversion.ic95_valor_absoluto],
      ["Bootstrap por unidad", I.bootstrap.ic95],
      ["Jackknife por unidad", I.jackknife.ic95_t],
    ];
    const est = D.efecto.vf.efecto * 100;
    const ref = {
      id: "ref-intervalos",
      afterDatasetsDraw(chart) {
        const { ctx, chartArea, scales } = chart;
        [[0, TINTA, [4, 4], ""], [est, VERDE, [], `estimado ${signo(D.efecto.vf.efecto, 1)}`]].forEach(([v, col, dash, t]) => {
          const x = scales.x.getPixelForValue(v);
          ctx.save(); ctx.setLineDash(dash); ctx.strokeStyle = col; ctx.lineWidth = 1.6;
          ctx.beginPath(); ctx.moveTo(x, chartArea.top); ctx.lineTo(x, chartArea.bottom); ctx.stroke();
          if (t) { ctx.fillStyle = col; ctx.font = "600 12px 'DM Sans', sans-serif"; ctx.fillText(t, x + 6, chartArea.top + 12); }
          ctx.restore();
        });
      },
    };
    new Chart(document.getElementById("ch-intervalos"), {
      type: "bar",
      data: { labels: filas.map((f) => f[0]),
              datasets: [{ data: filas.map((f) => [f[1][0] * 100, f[1][1] * 100]),
                           backgroundColor: filas.map((f) => (f[1][0] <= 0 ? AMBAR_FONDO : PIZARRA_FONDO)), borderColor: filas.map((f) => (f[1][0] <= 0 ? AMBAR : PIZARRA)), borderWidth: 1.5, borderRadius: 4, barPercentage: 0.5 }] },
      plugins: [ref],
      options: { indexAxis: "y", layout: { padding: { top: 16 } },
        plugins: { legend: { display: false },
          tooltip: { callbacks: { label: (i) => `${signo(i.raw[0] / 100, 1)} a ${signo(i.raw[1] / 100, 1)}` } } },
        scales: { x: { min: -20, max: 100, ticks: { callback: (v) => `${v}%` }, title: { display: true, text: "Efecto sobre las carpetas (%)" } },
                  y: { ticks: { autoSkip: false } } } },
    });
  });

  // --- lanzamientos ficticios
  alVer(document.getElementById("ch-placebos"), () => {
    const pl = [...PT.vf.placebos].sort((a, b) => a.lanzamiento_ficticio.localeCompare(b.lanzamiento_ficticio));
    const obs = D.efecto.vf.efecto * 100;
    const limites = {
      id: "lim-placebos",
      afterDatasetsDraw(chart) {
        const { ctx, chartArea, scales } = chart;
        [obs, -obs].forEach((v) => {
          const y = scales.y.getPixelForValue(v);
          ctx.save(); ctx.setLineDash([5, 4]); ctx.strokeStyle = VERDE; ctx.lineWidth = 1.6;
          ctx.beginPath(); ctx.moveTo(chartArea.left, y); ctx.lineTo(chartArea.right, y); ctx.stroke();
          ctx.setLineDash([]); ctx.fillStyle = VERDE; ctx.font = "600 12px 'DM Sans', sans-serif";
          ctx.fillText(`${signo(v / 100)} observado`, chartArea.left + 6, y - 6);
          ctx.restore();
        });
      },
    };
    new Chart(document.getElementById("ch-placebos"), {
      type: "bar",
      data: { labels: pl.map((d) => fmtMes(d.lanzamiento_ficticio)),
              datasets: [{ data: pl.map((d) => d.efecto * 100), backgroundColor: PIZARRA, borderRadius: 3, maxBarThickness: 30 }] },
      plugins: [limites],
      options: { plugins: { legend: { display: false },
          tooltip: { callbacks: { title: (i) => `Lanzamiento ficticio en ${i[0].label}`, label: (i) => `${i.raw >= 0 ? "+" : ""}${i.raw.toFixed(1)}% contra lo esperado` } } },
        scales: { y: { suggestedMin: -35, suggestedMax: 35, ticks: { callback: (v) => `${v}%` }, title: { display: true, text: "% contra lo esperado" } },
                  x: { ticks: { autoSkip: false, maxRotation: 0, callback: (v, i) => (/^(ene|jul)/.test(fmtMes(pl[i].lanzamiento_ficticio)) ? fmtMes(pl[i].lanzamiento_ficticio) : "") } } } },
    });
  });

  // --- las unidades de comparación también se movieron
  alVer(document.getElementById("ch-controles"), () => {
    const cm = D.diseno.contraste_controles.por_mes;
    new Chart(document.getElementById("ch-controles"), {
      type: "bar",
      data: { labels: cm.map((d) => fmtMes(d.mes)),
              datasets: [
                { label: "Con abogadas", data: cm.map((d) => d.interanual_con_programa * 100), backgroundColor: VERDE, borderRadius: 4, maxBarThickness: 48 },
                { label: "Sin programa todavía (comparación)", data: cm.map((d) => d.interanual_sin_programa * 100), backgroundColor: PIZARRA, borderRadius: 4, maxBarThickness: 48 },
              ] },
      plugins: [valoresEnBarras(fmtPct)],
      options: { layout: { padding: { top: 18 } }, plugins: { legend: { position: "bottom" },
          tooltip: { callbacks: { label: (i) => { const d = cm[i.dataIndex]; const n = i.datasetIndex === 0 ? d.unidades_con : d.unidades_sin; return `${i.dataset.label} (${n} unidades): ${i.raw >= 0 ? "+" : ""}${i.raw.toFixed(1)}% contra el mismo mes de 2018`; } } } },
        scales: { y: { ticks: { callback: (v) => `${v}%` }, title: { display: true, text: "Cambio contra 2018 (%)" } } } },
    });
  });

  // --- explorador por agencia
  const PN = D.panel;
  const sel = document.getElementById("sel-agencia");
  const orden = PN.unidades.map((u, i) => ({ u, i, tot: PN.vf[i].reduce((a, b) => a + b, 0) })).sort((a, b) => nombre(a.u).localeCompare(nombre(b.u), "es"));
  orden.forEach(({ u, i }) => { const o = document.createElement("option"); o.value = i; o.textContent = `${nombre(u)} · llegan en ${fmtMes(PN.entrada[i])}`; sel.appendChild(o); });
  const inicial = orden.reduce((a, b) => (b.tot > a.tot ? b : a));
  sel.value = inicial.i;
  let chAg = null;
  function agencia(i) {
    const datos = { labels: PN.meses, datasets: [{ label: "Violencia familiar", data: PN.vf[i], borderColor: VERDE, borderWidth: 2, pointRadius: 0, tension: 0.2 }] };
    if (chAg) chAg.destroy();
    chAg = new Chart(document.getElementById("ch-agencia"), {
      type: "line", data: datos, plugins: [lineaVertical(PN.meses, PN.entrada[i], "llegan")],
      options: { plugins: { legend: { display: false } },
        scales: { x: { ticks: { callback: (v, k) => (PN.meses[k].endsWith("-01") ? PN.meses[k].slice(0, 4) : "") } },
                  y: { beginAtZero: true, title: { display: true, text: "Carpetas / mes" } } } },
    });
  }
  sel.addEventListener("change", () => agencia(+sel.value));
  alVer(document.getElementById("ch-agencia"), () => agencia(+sel.value));
}

// ================================================== ACTO 2: puntos de cambio
// Resultados de puntos de cambio (scripts/abogadas/a05_quiebres.py). Solo se dibujan.

// Línea vertical punteada en un eje lineal (el helper lineaVertical trabaja con categorías).
function lineaEnValor(valor, texto, color = TINTA) {
  return {
    id: `vv-${Math.random().toString(36).slice(2)}`,
    afterDatasetsDraw(chart) {
      const { ctx, chartArea, scales } = chart;
      const x = scales.x.getPixelForValue(valor);
      ctx.save();
      ctx.setLineDash([5, 4]); ctx.lineWidth = 1.4; ctx.strokeStyle = color;
      ctx.beginPath(); ctx.moveTo(x, chartArea.top); ctx.lineTo(x, chartArea.bottom); ctx.stroke();
      ctx.setLineDash([]); ctx.fillStyle = color; ctx.font = "600 12px 'DM Sans', sans-serif";
      ctx.fillText(texto, x + 6, chartArea.top + 12);
      ctx.restore();
    },
  };
}

function actoQuiebres(D) {
  const Q = D.quiebres;
  if (!Q) return;
  const A = Q.agencias;

  // --- A1: el detector trabajando sobre una agencia real. Los tramos son el promedio de cada segmento
  // entre los escalones que encontró el detector (el detector trabaja con la serie desestacionalizada).
  const PN = D.panel;
  const det = Object.fromEntries(A.vf.detalle.map((x) => [x.unidad, x]));
  const enVentana = (q) => q.cambio > 0 && A.ventana_e.includes(q.e);
  const EJEMPLOS = [
    ["VC-3", "Sube al llegar"],
    ["AO-3 Y 4", "Sube, pero en otro mes"],
    ["MIL-1", "No sube"],
  ].filter(([u]) => det[u] && PN.unidades.includes(u));

  function tramos(serie, quiebres) {
    const cortes = [0, ...quiebres.map((q) => PN.meses.indexOf(q.mes)).filter((i) => i > 0).sort((x, y) => x - y), serie.length];
    const nivel = new Array(serie.length);
    for (let j = 0; j < cortes.length - 1; j++) {
      const tramo = serie.slice(cortes[j], cortes[j + 1]);
      const m = tramo.reduce((x, y) => x + y, 0) / tramo.length;
      for (let t = cortes[j]; t < cortes[j + 1]; t++) nivel[t] = m;
    }
    return nivel;
  }
  const franjaLlegada = {
    id: "franja-llegada",
    beforeDatasetsDraw(chart) {
      const { ctx, chartArea, scales } = chart;
      const i = PN.meses.indexOf(chart.$entrada);
      if (i < 0) return;
      const ancho = scales.x.getPixelForValue(1) - scales.x.getPixelForValue(0);
      const x0 = scales.x.getPixelForValue(i) - ancho / 2;
      ctx.save();
      ctx.fillStyle = "rgba(244, 244, 244, 0.08)";
      ctx.fillRect(x0, chartArea.top, ancho * A.ventana_e.length, chartArea.height);
      ctx.fillStyle = TINTA; ctx.font = "600 12px 'DM Sans', sans-serif";
      ctx.textAlign = "right"; ctx.fillText("Llegan las abogadas", x0 - 6, chartArea.bottom - 10);
      ctx.restore();
    },
  };
  let chEj = null;
  function ejemplo(u) {
    const i = PN.unidades.indexOf(u), d = det[u];
    const serie = PN.vf[i], nivel = tramos(serie, d.quiebres);
    const datos = { labels: PN.meses.map(fmtMes), datasets: [
      { label: "Carpetas al mes", data: serie, borderColor: VERDE, borderWidth: 1.6, pointRadius: 2, pointBackgroundColor: VERDE, tension: 0.2 },
      { label: "Nivel que encontró el detector", data: nivel, borderColor: TINTA, borderWidth: 3, pointRadius: 0, stepped: "before" },
    ] };
    const q = d.quiebres.find(enVentana);
    const otro = d.quiebres.find((x) => x.cambio > 0 && !enVentana(x));
    document.getElementById("pelt-ejemplo-texto").textContent = q
      ? `La agencia de ${ALCALDIA[u]} recibió abogadas en ${fmtMes(d.entrada)} y el detector ubicó un escalón hacia arriba ${q.mes === d.entrada ? "ese mismo mes" : `en ${fmtMes(q.mes)}`}, sin saber la fecha. Cuenta como una agencia que sube al llegar.`
      : otro
        ? `La agencia de ${ALCALDIA[u]} recibió abogadas en ${fmtMes(d.entrada)}, pero su escalón hacia arriba cae en ${fmtMes(otro.mes)}, fuera de la franja. No cuenta.`
        : `La agencia de ${ALCALDIA[u]} recibió abogadas en ${fmtMes(d.entrada)} y el detector no encontró ningún escalón: la variación de un mes a otro no alcanza para declarar un cambio. No cuenta, aunque no descarta un efecto pequeño.`;
    if (chEj) { chEj.$entrada = d.entrada; chEj.data = datos; chEj.update(); return; }
    chEj = new Chart(document.getElementById("ch-pelt-ejemplo"), {
      type: "line", data: datos, plugins: [franjaLlegada],
      options: {
        interaction: { mode: "index", intersect: false },
        layout: { padding: { right: 16 } },
        plugins: { legend: { position: "bottom", labels: { usePointStyle: true, padding: 16 } },
          tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${miles(c.raw)}` } } },
        scales: { y: { beginAtZero: true, title: { display: true, text: "Carpetas de violencia familiar" } },
                  x: { ticks: { autoSkip: false, callback: (v, j) => (j % 6 === 0 ? fmtMes(PN.meses[j]) : "") } } },
      },
    });
    chEj.$entrada = d.entrada; chEj.update();
  }
  const selEj = document.getElementById("sel-pelt-ejemplo");
  EJEMPLOS.forEach(([u, texto], j) => {
    const b = document.createElement("button");
    b.textContent = `${texto} · ${ALCALDIA[u]}`; b.dataset.u = u;
    b.className = j === 0 ? "activo" : ""; b.setAttribute("aria-pressed", j === 0 ? "true" : "false");
    b.addEventListener("click", () => {
      selEj.querySelectorAll("button").forEach((x) => { x.classList.toggle("activo", x === b); x.setAttribute("aria-pressed", x === b ? "true" : "false"); });
      ejemplo(u);
    });
    selEj.appendChild(b);
  });
  if (EJEMPLOS.length) alVer(document.getElementById("ch-pelt-ejemplo"), () => ejemplo(EJEMPLOS[0][0]));

  // --- A2: mosaico de las 52 agencias, agrupadas por mes de llegada.
  function mosaico(k) {
    const cont = document.getElementById("pelt-mosaico");
    const grupos = {};
    A[k].detalle.forEach((x) => (grupos[x.entrada] ||= []).push(x));
    const n = { llegada: 0, otro: 0, sin: 0 };
    cont.innerHTML = "";
    Object.keys(grupos).sort().forEach((m) => {
      const fila = document.createElement("div"); fila.className = "mosaico-fila";
      const et = document.createElement("span"); et.className = "mosaico-mes"; et.textContent = fmtMes(m);
      const cuadros = document.createElement("div"); cuadros.className = "mosaico-cuadros";
      grupos[m].sort((x, y) => x.unidad.localeCompare(y.unidad)).forEach((x) => {
        const q = x.quiebres.find(enVentana), otro = x.quiebres.find((z) => z.cambio > 0);
        const clase = q ? "llegada" : otro ? "otro" : "sin";
        n[clase]++;
        const c = document.createElement("i");
        c.className = `cuadro ${clase === "llegada" ? "alza-llegada" : clase === "otro" ? "alza-otro" : "sin"}`;
        c.title = `${nombre(x.unidad)} · abogadas desde ${fmtMes(x.entrada)} · ${q ? `sube en ${fmtMes(q.mes)}` : otro ? `sube en ${fmtMes(otro.mes)}, fuera de la franja` : "sin escalón hacia arriba"}`;
        cuadros.appendChild(c);
      });
      fila.append(et, cuadros); cont.appendChild(fila);
    });
    ["llegada", "otro", "sin"].forEach((k2) => {
      document.getElementById(`pelt-n-${k2}`).textContent = n[k2];
      document.getElementById(`pelt-t-${k2}`).textContent = n[k2] === 1 ? "sube" : "suben";
    });
  }

  // --- A3: regla con el rango que da el azar (9 de cada 10 repartos) y lo observado.
  const MAX = 15;
  const ejes = document.getElementById("pelt-ejes");
  for (let v = 0; v <= MAX; v += 1) {
    const t = document.createElement("span"); t.style.left = `${(v / MAX) * 100}%`; t.textContent = v % 5 === 0 ? v : "";
    t.className = v % 5 === 0 ? "mayor" : ""; ejes.appendChild(t);
  }
  function regla(k) {
    const r = A[k], c = r.nula_conteo, tot = c.reduce((x, y) => x + y, 0);
    let acum = 0, lo = null, hi = null;
    c.forEach((x, v) => { acum += x; if (lo === null && acum / tot >= 0.05) lo = v; if (hi === null && acum / tot >= 0.95) hi = v; });
    const hab = Math.round(r.nula_media * A.n), obs = r.unidades_con_quiebre_en_llegada;
    const pos = (v) => `${(v / MAX) * 100}%`;
    const banda = document.getElementById("pelt-banda");
    banda.style.left = pos(lo - 0.5 < 0 ? 0 : lo - 0.5); banda.style.width = `${((hi - Math.max(lo - 0.5, 0) + 0.5) / MAX) * 100}%`;
    const h = document.getElementById("pelt-habitual"), o = document.getElementById("pelt-observado");
    h.style.left = pos(hab); h.querySelector("span").textContent = `Habitual: ${hab}`;
    o.style.left = pos(obs); o.querySelector("span").textContent = `Observado: ${obs}`;
    const fuera = obs > hi;
    o.classList.toggle("dentro", !fuera);
    const wy = r.westfall_young;
    const ajuste = wy ? ` Tomando en cuenta las ${wy.especificaciones} variantes de definición que se probaron, la proporción sube a ${Math.round(wy.p_principal_ajustado * 100)} de cada 100: es un resultado exploratorio.` : "";
    document.getElementById("pelt-regla-texto").innerHTML = fuera
      ? `En 9 de cada 10 repartos al azar salen entre ${lo} y ${hi} unidades. Lo observado, <b>${obs}</b>, queda fuera: ${obs} o más aparece en <b>1 de cada ${Math.round(1 / r.p)}</b> repartos.${ajuste}`
      : `En 9 de cada 10 repartos al azar salen entre ${lo} y ${hi} ${hi === 1 ? "unidad" : "unidades"}. Lo observado, <b>${obs}</b>, cae dentro de lo que produce el sorteo de fechas.`;
  }

  const sel = document.getElementById("sel-quiebres");
  const pintar = (k) => { mosaico(k); regla(k); };
  sel.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
    sel.querySelectorAll("button").forEach((x) => {
      x.classList.toggle("activo", x === b); x.setAttribute("aria-pressed", x === b ? "true" : "false");
    });
    pintar(b.dataset.k);
  }));
  pintar("vf");

  // --- B: qué tan frágil es: cuántos de cada 100 repartos igualan lo observado con cada definición
  const V = A.vf;
  const filas = [
    [["Definición principal:", "mes de llegada o el siguiente"], V.p, true],
    ["Solo el mes de llegada", V.sensibilidad_ventana.e0.p],
    ["Hasta dos meses después de la llegada", V.sensibilidad_ventana.e0a2.p],
    ["Del mes anterior al siguiente a la llegada", V.sensibilidad_ventana["e-1a1"].p],
    ["Criterio mucho más laxo para aceptar un cambio", V.sensibilidad_k["1.0"].p],
    ["Criterio algo más laxo", V.sensibilidad_k["2.0"].p],
    ["Criterio más estricto", V.sensibilidad_k["4.0"].p],
    ["Criterio mucho más estricto", V.sensibilidad_k["5.0"].p],
    ["Placebo: fechas corridas un mes antes", V.placebo_temporal["-1"].p],
  ];
  alVer(document.getElementById("ch-quiebres-fragilidad"), () => new Chart(document.getElementById("ch-quiebres-fragilidad"), {
    type: "bar",
    data: { labels: filas.map((f) => f[0]),
            datasets: [{ data: filas.map((f) => f[1] * 100), backgroundColor: filas.map((f) => (f[2] ? VERDE : String(f[0]).startsWith("Placebo") ? AMBAR : PIZARRA)),
                         borderRadius: 4, maxBarThickness: 30 }] },
    plugins: [lineaEnValor(5, "5 de cada 100", TINTA)],
    options: { indexAxis: "y",
      plugins: { legend: { display: false },
        tooltip: { callbacks: { label: (i) => `${i.raw < 1 ? i.raw.toFixed(1) : Math.round(i.raw)} de cada 100 repartos igualan o superan lo observado` } } },
      scales: { x: { min: 0, max: 100, title: { display: true, text: "Repartos al azar, de cada 100, que igualan el resultado" } },
                y: { ticks: { autoSkip: false } } } },
  }));
}

// ======================================================= ACTO 3: por dentro
function actoPrograma(D) {
  const S = D.programa.serie;
  const etq = S.map((s) => s.m);
  const RV = D.programa.registro_vacio.por_anio;
  const rv = (a) => RV.find((x) => x.anio === a);
  let chConv = null;
  const pies = {
    conteos: (() => {
      const a = S.find((s) => s.m.startsWith("2019-08")), b = S.find((s) => s.m.startsWith("2022-03"));
      return `Atenciones y carpetas con abogada por mes. La conversión es la línea verde dividida entre la de atenciones. En agosto de 2019, ${miles(a.carpetas)} carpetas de ${miles(a.atenciones)} atenciones (${pct(a.carpetas / a.atenciones)}). En marzo de 2022, ${miles(b.carpetas)} de ${miles(b.atenciones)} (${pct(b.carpetas / b.atenciones)}). El promedio de 2019 es más bajo porque incluye los meses de arranque. En meses de operación plena las carpetas son casi las mismas y las atenciones, menos de la mitad.`;
    })(),
    registro: `Qué dice la base en cada atención. En ámbar, "sin dato": durante ${D.resumen.hueco_meses} meses sustituye casi por completo al "no se abrió carpeta". El registro también se fue llenando. En ${RV[0].anio}, ${pct(RV[0].pct_sin_tipo_de_violencia)} de las atenciones no tenían tipo de violencia anotado. En ${RV[2].anio}, ${pct(RV[2].pct_sin_tipo_de_violencia, 1)}.`,
  };
  function conv(v) {
    document.getElementById("pie-conversion").textContent = pies[v];
    let cfg;
    if (v === "conteos") {
      cfg = { type: "line",
        data: { labels: etq, datasets: [
          { label: "Atenciones", data: S.map((s) => s.atenciones), borderColor: PIZARRA_CLARO, borderWidth: 2, pointRadius: 0, tension: 0.2 },
          { label: "Carpetas con abogada", data: S.map((s) => s.carpetas), borderColor: VERDE, borderWidth: 2.4, pointRadius: 0, tension: 0.2 }] },
        options: { interaction: { mode: "index", intersect: false },
          plugins: { tooltip: { callbacks: { label: (i) => `${i.dataset.label}: ${miles(i.raw)}`,
            footer: (it) => { const s = S[it[0].dataIndex]; return s.valido ? `Conversión: ${pct(s.carpetas / s.atenciones)}` : "Mes sin 'no' capturado"; } } } },
          scales: { y: { beginAtZero: true, ticks: { callback: (x) => miles(x) } } } } };
    } else {
      const P = D.por_mes_programa;
      cfg = { type: "bar",
        data: { labels: P.map((m) => m.mes), datasets: [
          { label: "Se abrió carpeta", data: P.map((m) => m.si), backgroundColor: VERDE },
          { label: "No se abrió", data: P.map((m) => m.no), backgroundColor: PIZARRA },
          { label: "Sin dato", data: P.map((m) => m.na), backgroundColor: AMBAR }] },
        options: { plugins: { tooltip: { mode: "index", callbacks: { label: (i) => `${i.dataset.label}: ${miles(i.raw)}` } } },
          scales: { x: { stacked: true }, y: { stacked: true, ticks: { callback: (x) => miles(x) } } } } };
    }
    cfg.options.scales.x = Object.assign(cfg.options.scales.x || {}, { ticks: { callback: (_, k) => { const m = cfg.data.labels[k]; return m.endsWith("-01") ? m.slice(0, 4) : ""; } } });
    if (chConv) chConv.destroy();
    chConv = new Chart(document.getElementById("ch-conversion"), cfg);
  }
  const selC = document.getElementById("sel-conv");
  selC.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
    selC.querySelectorAll("button").forEach((x) => x.classList.toggle("activo", x === b));
    conv(b.dataset.v);
  }));
  alVer(document.getElementById("ch-conversion"), () => conv("conteos"));

  // --- embudo
  const E = D.programa.embudo;
  alVer(document.getElementById("ch-embudo"), () => {
    const p0 = E.p0;
    const ns = E.tabla.map((t) => t.n);
    const xs = [];
    for (let x = Math.min(...ns) * 0.9; x <= Math.max(...ns) * 1.05; x += (Math.max(...ns) - Math.min(...ns)) / 80) xs.push(x);
    // Límites ajustados por sobredispersión (Spiegelhalter, aditivo): p0 ± z·√(p0(1−p0)/n + τ²).
    // Qué unidad queda fuera lo dice el JSON.
    const tau2 = E.aditivo.tau2, z998 = E.z_998;
    const lim = (z, s, t2) => xs.map((x) => ({ x, y: 100 * (p0 + s * z * Math.sqrt(p0 * (1 - p0) / x + t2)) }));
    const linea = (d, dash, color, w = 1.3) => ({ type: "line", data: d, borderColor: color, borderDash: dash, borderWidth: w, pointRadius: 0, fill: false });
    const estado = (t) => (t.fuera_998_aditivo ? "fuera del 99.8%" : t.fuera_95_aditivo ? "fuera del 95%" : "dentro de los límites");
    new Chart(document.getElementById("ch-embudo"), {
      type: "scatter",
      data: { datasets: [
        { label: "Agencias", data: E.tabla.map((t) => ({ x: t.n, y: t.conv * 100, u: t.unidad, est: estado(t) })),
          backgroundColor: VERDE,
          borderColor: E.tabla.map((t) => (t.fuera_95_aditivo ? TINTA : VERDE)), borderWidth: E.tabla.map((t) => (t.fuera_95_aditivo ? 2 : 1)),
          pointRadius: 5.5, pointHoverRadius: 8 },
        linea(lim(z998, 1, tau2), [2, 3], PIZARRA), linea(lim(z998, -1, tau2), [2, 3], PIZARRA), linea(lim(1.96, 1, tau2), [6, 4], PIZARRA_CLARO), linea(lim(1.96, -1, tau2), [6, 4], PIZARRA_CLARO),
      ] },
      options: {
        plugins: { legend: { display: false },
          tooltip: { filter: (i) => i.datasetIndex === 0, callbacks: { label: (i) => `${nombre(i.raw.u)}: ${i.raw.y.toFixed(1)}% de ${miles(i.raw.x)} atenciones · ${i.raw.est}` } } },
        scales: { x: { type: "linear", title: { display: true, text: "Atenciones en la agencia" }, ticks: { callback: (v) => miles(v) } },
                  y: { min: 0, max: 50, title: { display: true, text: "Conversión (%)" }, ticks: { callback: (v) => `${v}%` } } },
      },
    });
  });
}

// ============================================ ACTO 2: el sorteo en vivo
// Cada punto es uno de los repartos de fechas ya calculados (permutacion.conteo).
// Solo se baraja el orden en que caen: al final cada barra tiene exactamente su conteo.
// La prueba es de dos colas en valor absoluto (scripts/abogadas/_comun.py, p_permutacion):
// se iluminan los repartos con |efecto| >= |observado|, de los dos lados.
const MOVIMIENTO_REDUCIDO = matchMedia("(prefers-reduced-motion: reduce)").matches;
const PARAM_ANIM = new URLSearchParams(location.search).get("anim");

function sorteoEnVivo(D) {
  const cv = document.getElementById("cv-sorteo");
  if (!cv) return;
  const P = D.permutacion, T = D.inferencia.permutacion_por_tamano;
  const B = P.bordes, C = P.conteo, obs = P.observado, nb = C.length;
  const N = C.reduce((a, b) => a + b, 0);
  const btn = document.getElementById("btn-sorteo");
  const contador = document.getElementById("sorteo-contador");
  const resultado = document.getElementById("sorteo-resultado");

  // Qué repartos llegan tan lejos como el observado. Las barras de 2 puntos que quedan del todo
  // afuera cuentan completas. En las dos que cruzan una línea, cola_alta y cola_baja dicen cuántos
  // la pasan (los cuenta data_prep_abogadas.py con los repartos sin agrupar).
  const llenaAlta = (i) => B[i] >= obs, llenaBaja = (i) => B[i + 1] <= -obs;
  const suma = (f) => C.reduce((a, c, i) => a + (f(i) ? c : 0), 0);
  const iAlta = C.findIndex((_, i) => B[i] < obs && obs < B[i + 1]);
  const iBaja = C.findIndex((_, i) => B[i] < -obs && -obs < B[i + 1]);
  let colaAlta = P.cola_alta, colaBaja = P.cola_baja;
  if (colaAlta == null || colaBaja == null) {
    console.warn("abogadas.json sin permutacion.cola_alta/cola_baja: vuelve a correr data_prep_abogadas.py");
    colaAlta = suma(llenaAlta); colaBaja = suma(llenaBaja);
  }
  const extra = new Array(nb).fill(0);
  if (iAlta >= 0) extra[iAlta] = colaAlta - suma(llenaAlta);
  if (iBaja >= 0) extra[iBaja] = colaBaja - suma(llenaBaja);
  if (N !== T.n || colaAlta + colaBaja !== T.b || extra.some((x, i) => x < 0 || x > C[i]))
    console.warn("El sorteo no cuadra con inferencia.permutacion_por_tamano", { N, n: T.n, colaAlta, colaBaja, b: T.b });

  let L = null;
  function medir() {
    const dpr = devicePixelRatio || 1;
    const w = cv.clientWidth, h = cv.clientHeight;
    cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
    const ctx = cv.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const izq = 8, der = 8, arriba = 40, abajo = 44;
    const W = w - izq - der, H = h - arriba - abajo;
    const binW = W / nb, hueco = Math.max(1, binW * 0.1);
    const maxC = Math.max(...C);
    let paso = 7, cols = 1;
    for (; paso > 1; paso -= 0.25) {
      cols = Math.max(1, Math.floor((binW - hueco) / paso));
      if (Math.ceil(maxC / cols) * paso <= H) break;
    }
    const margen = (binW - cols * paso) / 2;
    // Qué lugares de las barras que cruzan la línea se iluminan: los del lado de afuera.
    const ilumina = C.map((c, i) => {
      if (!extra[i]) return null;
      const borde = i === iAlta ? cols - 1 : 0;
      const k = [...Array(c).keys()].sort((a, b) =>
        Math.abs(a % cols - borde) - Math.abs(b % cols - borde) || a - b);
      return new Set(k.slice(0, extra[i]));
    });
    L = { ctx, w, h, izq, arriba, W, H, base: arriba + H, binW, paso, cols, margen, punto: Math.max(1, paso * 0.78), ilumina,
          x: (v) => izq + ((v - B[0]) / (B[nb] - B[0])) * W };
  }
  const lugar = (i, k) => ({
    x: L.x(B[i]) + L.margen + (k % L.cols) * L.paso,
    y: L.base - (Math.floor(k / L.cols) + 1) * L.paso,
  });
  const esCola = (i, k) => llenaAlta(i) || llenaBaja(i) || (L.ilumina[i] && L.ilumina[i].has(k));

  function eje() {
    const { ctx, w, h, base } = L;
    ctx.clearRect(0, 0, w, h);
    ctx.strokeStyle = "#353535"; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(L.izq, base + 0.5); ctx.lineTo(L.izq + L.W, base + 0.5); ctx.stroke();
    ctx.fillStyle = "#C6C6C6"; ctx.font = "13px 'DM Sans', sans-serif"; ctx.textAlign = "center";
    for (let v = Math.ceil(B[0] / 10) * 10; v <= B[nb]; v += 10) {
      const x = L.x(v);
      ctx.fillRect(x, base, 1, 5);
      ctx.fillText(`${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v)}%`, x, base + 20);
    }
    ctx.fillStyle = "#8E8E8E"; ctx.font = "12px 'DM Sans', sans-serif";
    ctx.fillText("Efecto que da cada reparto de fechas", L.izq + L.W / 2, base + 38);
  }
  function lineas(alfa, soloObs = false) {
    if (alfa <= 0) return;
    const { ctx, arriba, base } = L;
    ctx.save(); ctx.globalAlpha = alfa;
    [[obs, VERDE, `observado ${signo(obs / 100, 1)}`],
     [-obs, PIZARRA_CLARO, L.w < 700 ? signo(-obs / 100, 1) : `${signo(-obs / 100, 1)}, igual de lejos hacia abajo`]].slice(0, soloObs ? 1 : 2).forEach(([v, col, txt]) => {
      const x = L.x(v);
      ctx.font = "700 13px 'DM Sans', sans-serif";
      const lado = x + 6 + ctx.measureText(txt).width > L.w ? "right" : "left";
      ctx.strokeStyle = col; ctx.lineWidth = 2; ctx.setLineDash([5, 4]);
      ctx.beginPath(); ctx.moveTo(x, arriba - 8); ctx.lineTo(x, base); ctx.stroke();
      ctx.setLineDash([]); ctx.fillStyle = col; ctx.font = "700 13px 'DM Sans', sans-serif";
      ctx.textAlign = lado; ctx.fillText(txt, x + (lado === "left" ? 6 : -6), arriba - 14);
    });
    ctx.restore();
  }
  function punto(i, k, y) {
    const p = lugar(i, k);
    L.ctx.fillStyle = esCola(i, k) ? PIZARRA_CLARO : "rgba(125, 147, 178, 0.38)";
    L.ctx.fillRect(p.x, y ?? p.y, L.punto, L.punto);
  }

  const textoContador = (k, t) => `${miles(k)} de ${miles(N)} repartos · <b>${t}</b> llegan tan lejos como lo observado`;
  function textoFinal() {
    contador.innerHTML = textoContador(N, colaAlta + colaBaja);
    resultado.innerHTML = `Solo <b>${colaAlta + colaBaja} de ${miles(N)}</b> repartos llegan hasta aquí:
      ${colaAlta} suben ${signo(obs / 100, 1)} o más y ${colaBaja} bajan ${pct(obs / 100, 1)} o más.
      Si las abogadas no hubieran hecho nada, un resultado así saldría en 1 de cada ${Math.round(1 / T.p)} repartos.
      Por eso es difícil achacarlo a cómo cayeron las fechas. El sorteo no resuelve lo de arriba: todo viene de las
      agencias de marzo, las de comparación también cambiaron y no se puede descartar que ya vinieran subiendo.`;
    resultado.classList.add("visible");
  }

  let estado = "vacio", anim = null;
  function dibujarVacio() {
    eje();
    L.ctx.fillStyle = "#8E8E8E"; L.ctx.font = "15px 'DM Sans', sans-serif"; L.ctx.textAlign = "center";
    L.ctx.fillText("Aquí van a caer los repartos", L.izq + L.W / 2, L.arriba + L.H / 2);
    lineas(1, true);
  }
  function dibujarFinal() {
    eje();
    C.forEach((c, i) => { for (let k = 0; k < c; k++) punto(i, k); });
    lineas(1);
  }
  function final() {
    if (anim) cancelAnimationFrame(anim);
    anim = null; estado = "final";
    dibujarFinal(); textoFinal();
    btn.textContent = "Repetir";
  }

  // Orden de caída al azar. El k-ésimo punto que llega a una barra ocupa su lugar k, así que
  // al final cada barra tiene C[i] puntos y ninguno más.
  const CAIDA = 4200, VUELO = 450, LINEA = 500;
  function jugar() {
    if (anim) cancelAnimationFrame(anim);
    const orden = [];
    C.forEach((c, i) => { for (let k = 0; k < c; k++) orden.push(i); });
    for (let j = orden.length - 1; j > 0; j--) { const r = Math.floor(Math.random() * (j + 1)); [orden[j], orden[r]] = [orden[r], orden[j]]; }
    const lleno = new Array(nb).fill(0);
    // Empieza lento para que se vean los primeros puntos y luego se acelera.
    const gotas = orden.map((i, j) => ({ i, k: lleno[i]++, t0: CAIDA * Math.sqrt(j / N) }));
    // Autocomprobación: cada barra recibe su conteo exacto y se iluminan b repartos.
    const iluminados = gotas.filter((g) => esCola(g.i, g.k)).length;
    const cuadra = lleno.every((x, i) => x === C[i]) && iluminados === T.b;
    cv.dataset.verificado = cuadra ? `ok ${gotas.length} ${iluminados}` : "no cuadra";
    if (!cuadra) console.warn("Los puntos del sorteo no cuadran con el histograma", { lleno, iluminados });
    estado = "jugando"; resultado.classList.remove("visible"); resultado.innerHTML = "";
    btn.textContent = "Repetir";
    const t0 = performance.now();
    const cuadro = (ahora) => {
      const t = ahora - t0;
      eje();
      let caidos = 0, cola = 0;
      for (const g of gotas) {
        if (g.t0 > t) break;
        const f = Math.min(1, (t - g.t0) / VUELO);
        if (f >= 1) { caidos++; if (esCola(g.i, g.k)) cola++; punto(g.i, g.k); }
        else { const destino = lugar(g.i, g.k).y; punto(g.i, g.k, L.arriba - 10 + (destino - L.arriba + 10) * f * f); }
      }
      contador.innerHTML = textoContador(caidos, cola);
      lineas((t - CAIDA - VUELO) / LINEA);
      if (t < CAIDA + VUELO + LINEA) anim = requestAnimationFrame(cuadro);
      else final();
    };
    anim = requestAnimationFrame(cuadro);
  }

  btn.addEventListener("click", () => {
    if (!L) medir();
    if (MOVIMIENTO_REDUCIDO || PARAM_ANIM === "final") final(); else jugar();
  });
  addEventListener("resize", () => {
    if (!L) return;
    medir();
    if (estado === "final") dibujarFinal(); else if (estado === "vacio") dibujarVacio();
  });
  alVer(cv, () => {
    medir();
    if (MOVIMIENTO_REDUCIDO || PARAM_ANIM === "final") final();
    else if (PARAM_ANIM === "jugar") jugar();
    else dibujarVacio();
  }, 0.1);
}

// =================================================== ACTO 4: evaluabilidad
function actoEvaluabilidad(D) {
  const E = D.evaluabilidad;
  alVer(document.getElementById("regla"), () => document.getElementById("regla").classList.add("visible"), 0.5);

  const disenos = [
    ["real", "Como se hizo: 5 meses", E.composicion_observada.potencia],
    ["estados", "Por estados, mitad y mitad", E.estados.potencia],
  ];
  const efectos = Object.keys(E.composicion_observada.potencia).map(Number).sort((a, b) => a - b);
  // 100 evaluaciones imaginarias: se encienden tantas como la potencia (de 100) del calendario
  // elegido. Es la misma cifra que la curva de la derecha: potDe(pot, r), redondeada igual.
  const enFrase = {
    real: "el calendario real de 5 meses",
    estados: "el calendario por estados, mitad y mitad",
  };
  let sel = "real";
  const selCal = document.getElementById("sel-calendario");
  selCal.innerHTML = disenos.map(([k, et]) => `<button data-k="${k}" class="${k === sel ? "activo" : ""}" aria-pressed="${k === sel}">${et}</button>`).join("");
  const rejilla = document.getElementById("evals-rejilla");
  rejilla.innerHTML = Array.from({ length: 100 }, (_, i) => `<i class="eval-c" style="--i:${i}"></i>`).join("");
  const puntos = [...rejilla.children];

  const slider = document.getElementById("slider-efecto");
  slider.max = efectos.length - 1;
  let chPot = null;
  function pintar() {
    const r = efectos[+slider.value];
    const R = Math.round(r * 100);
    document.getElementById("efecto-val").textContent = `+${R}%`;
    const pot = disenos.find(([k]) => k === sel)[2];
    const v = potDe(pot, r);
    const frase = document.getElementById("evals-frase"), vara = document.getElementById("evals-vara");
    if (v == null) {
      // La simulación por estados usó otra rejilla de aumentos: no se inventa el punto que falta.
      puntos.forEach((p) => { p.classList.remove("on"); p.classList.add("sin-dato"); });
      rejilla.setAttribute("aria-label", "Sin simulación para este aumento");
      frase.innerHTML = `La simulación por estados no probó un aumento de +${R}%. Mueve el control a otro valor.`;
      vara.textContent = ""; vara.className = "evals-vara";
    } else {
      const si = Math.round(v * 100), no = 100 - si;
      puntos.forEach((p, i) => { p.classList.remove("sin-dato"); p.classList.toggle("on", i < si); });
      rejilla.setAttribute("aria-label", `${si} de 100 evaluaciones lo habrían visto`);
      frase.innerHTML = `Con un aumento real de +${R}% y ${enFrase[sel]}, esta evaluación lo habría visto en
        <b class="si">${si} de cada 100</b> intentos. ` +
        (no === 0 ? "No lo habría pasado por alto en ninguno." : `En <b class="no">${no}</b> lo habría pasado por alto.`) +
        (sel === "estados" ? " Aquí el aumento se aplica a todo el estado. No se compara directo con el calendario real (acto&nbsp;5)." : "");
      vara.textContent = si >= 80
        ? "Pasa la vara de 80 de cada 100 que se pide para confiar en una evaluación."
        : `Le faltan ${80 - si} para la vara de 80 de cada 100 que se pide para confiar en una evaluación.`;
      vara.className = `evals-vara ${si >= 80 ? "pasa" : "falta"}`;
    }
    const ok = potDe(disenos[0][2], r) >= 0.8;
    document.getElementById("titulo-potencia").textContent = ok
      ? `Con un aumento de ${Math.round(r * 100)}%, el calendario real sí lo detecta 8 de cada 10 veces`
      : `Con un aumento de ${Math.round(r * 100)}%, el calendario real no lo detecta 8 de cada 10 veces`;
    if (chPot) {
      chPot.options.plugins.marca = r;
      chPot.data.datasets.forEach((d, i) => { d.borderWidth = disenos[i][0] === sel ? 3.5 : 1.4; });
      chPot.update("none");
    }
  }
  slider.addEventListener("input", pintar);
  selCal.addEventListener("click", (ev) => {
    const b = ev.target.closest("button"); if (!b) return;
    sel = b.dataset.k;
    selCal.querySelectorAll("button").forEach((x) => { x.classList.toggle("activo", x === b); x.setAttribute("aria-pressed", x === b ? "true" : "false"); });
    pintar();
  });
  pintar();

  alVer(document.getElementById("ch-potencia"), () => {
    const marca = {
      id: "marca-efecto",
      afterDatasetsDraw(chart) {
        const r = chart.options.plugins.marca;
        const { ctx, chartArea, scales } = chart;
        const x = scales.x.getPixelForValue(r * 100);
        const y = scales.y.getPixelForValue(80);
        ctx.save();
        ctx.setLineDash([5, 4]); ctx.strokeStyle = TINTA; ctx.lineWidth = 1.2;
        ctx.beginPath(); ctx.moveTo(chartArea.left, y); ctx.lineTo(chartArea.right, y); ctx.stroke();
        ctx.setLineDash([]); ctx.strokeStyle = TINTA; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.moveTo(x, chartArea.top); ctx.lineTo(x, chartArea.bottom); ctx.stroke();
        ctx.restore();
      },
    };
    const tonos = [VERDE, PIZARRA, PIZARRA, PIZARRA, PIZARRA_CLARO];
    chPot = new Chart(document.getElementById("ch-potencia"), {
      type: "line",
      data: { datasets: disenos.map(([k, et, pot], i) => ({
        label: et, data: efectos.filter((r) => potDe(pot, r) != null).map((r) => ({ x: r * 100, y: potDe(pot, r) * 100 })),
        borderColor: tonos[i], borderWidth: k === sel ? 3.5 : 1.4, borderDash: k === "estados" ? [6, 4] : [], pointRadius: 0, tension: 0.25 })) },
      plugins: [marca],
      options: {
        plugins: { marca: efectos[+slider.value], legend: { position: "bottom" },
          tooltip: { mode: "index", intersect: false, callbacks: { title: (i) => `Efecto real +${i[0].raw.x}%`, label: (i) => `${i.dataset.label}: ${Math.round(i.raw.y)} de 100` } } },
        scales: { x: { type: "linear", min: 0, max: 100, title: { display: true, text: "Efecto real del programa (%)" }, ticks: { callback: (v) => `${v}%` } },
                  y: { min: 0, max: 100, title: { display: true, text: "Detectan (de 100)" } } },
      },
    });
  });

  alVer(document.getElementById("ch-deriva"), () => {
    const pu = [...E.deriva.por_unidad].sort((a, b) => a.cambio - b.cambio);
    const mde = E.composicion_observada.mde_interpolado;
    new Chart(document.getElementById("ch-deriva"), {
      type: "bar",
      data: { labels: pu.map((d) => nombre(d.unidad)), datasets: [{ data: pu.map((d) => d.cambio * 100), backgroundColor: pu.map((d) => (Math.abs(d.cambio) > mde ? AMBAR : PIZARRA)), borderRadius: 2 }] },
      plugins: [{
        id: "mde-deriva",
        afterDatasetsDraw(chart) {
          const { ctx, chartArea, scales } = chart;
          [mde * 100, -mde * 100].forEach((v) => {
            const y = scales.y.getPixelForValue(v);
            ctx.save(); ctx.setLineDash([5, 4]); ctx.strokeStyle = AMBAR; ctx.lineWidth = 1.4;
            ctx.beginPath(); ctx.moveTo(chartArea.left, y); ctx.lineTo(chartArea.right, y); ctx.stroke();
            ctx.setLineDash([]); ctx.fillStyle = AMBAR; ctx.font = "600 12px 'DM Sans', sans-serif";
            ctx.textAlign = v > 0 ? "left" : "right";
            ctx.fillText(`${v > 0 ? "+" : "−"}${pct(mde)} mínimo detectable`, v > 0 ? chartArea.left + 6 : chartArea.right - 6, v > 0 ? y - 6 : y + 14);
            ctx.restore();
          });
        },
      }],
      options: { plugins: { legend: { display: false }, tooltip: { callbacks: { label: (i) => `${i.raw >= 0 ? "+" : ""}${i.raw.toFixed(0)}% de 2017 a 2018` } } },
        scales: { x: { ticks: { display: false }, grid: { display: false } },
                  y: { title: { display: true, text: "Cambio 2017 → 2018 (%)" }, ticks: { callback: (v) => `${v}%` } } } },
    });
  });
}

// ================================================================ índice
function indice() {
  const barra = document.getElementById("progreso-barra");
  const inicio = document.getElementById("acto1");
  const avance = () => {
    const a = inicio.getBoundingClientRect().top + scrollY - 160;
    const b = document.documentElement.scrollHeight - innerHeight;
    if (barra) barra.style.width = `${Math.max(0, Math.min(1, (scrollY - a) / (b - a))) * 100}%`;
  };
  addEventListener("scroll", avance, { passive: true }); avance();
  const botones = document.querySelectorAll("#indice button");
  botones.forEach((b) => b.addEventListener("click", () =>
    document.getElementById(b.dataset.ir).scrollIntoView({ behavior: "smooth", block: "start" })));
  const obs = new IntersectionObserver((ents) => {
    ents.forEach((e) => {
      if (e.isIntersecting) botones.forEach((b) => b.classList.toggle("activo", b.dataset.ir === e.target.id));
    });
  }, { rootMargin: "0px 0px -70% 0px" });
  botones.forEach((b) => obs.observe(document.getElementById(b.dataset.ir)));

  const piezas = document.querySelectorAll(".tarjeta, .acto-veredicto, .puente, .aviso-dato");
  const rev = new IntersectionObserver((ents) => ents.forEach((e) => {
    if (e.isIntersecting) { e.target.classList.add("visible"); rev.unobserve(e.target); }
  }), { threshold: 0.08 });
  piezas.forEach((p) => { p.classList.add("revelar"); rev.observe(p); });
}

fetch("/static/data/abogadas.json").then((r) => r.json()).then((D) => {
  prepararNombres(D);
  indice();
  actoDespliegue(D);
  actoEfecto(D);
  actoQuiebres(D);
  actoPrograma(D);
  actoEvaluabilidad(D);
});
