// Metodología: cómo se construye el contrafactual.
// Los números llegan resueltos desde el servidor (bloque JSON en la plantilla). Aquí solo se
// dibuja la celda de ejemplo y se maneja el índice: no se calcula nada.

const AZUL = "#3E6BE6";
const AZUL_CLARO = "#8FB0FF";
const ROJO = "#F25555";
const TINTA = "#F4F4F4";

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

const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const fmtMes = (m) => `${MESES[+m.slice(5, 7) - 1]} ${m.slice(0, 4)}`;

// Línea vertical punteada con etiqueta, igual que en la página de la evaluación.
function lineaVertical(etiquetas, valor, texto, color = ROJO) {
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

function alVer(el, fn, umbral = 0.25) {
  if (!el) return;
  const obs = new IntersectionObserver((ents) => {
    ents.forEach((e) => { if (e.isIntersecting) { obs.disconnect(); fn(); } });
  }, { threshold: umbral });
  obs.observe(el);
}

function celdaDeEjemplo(ej) {
  const lienzo = document.getElementById("g-ejemplo");
  if (!lienzo) return;
  const etq = ej.serie.map((d) => d.mes);
  alVer(lienzo, () => new Chart(lienzo, {
    type: "line",
    data: {
      labels: etq,
      datasets: [
        { label: "Esperado sin programa (contrafactual)", data: ej.serie.map((d) => d.contrafactual),
          borderColor: AZUL_CLARO, borderDash: [4, 4], borderWidth: 1.8, pointRadius: 0 },
        { label: "Observado", data: ej.serie.map((d) => d.observado),
          borderColor: TINTA, borderWidth: 2.4, tension: 0.2,
          pointRadius: (ctx) => (ej.serie[ctx.dataIndex].programa ? 4 : 2.5),
          pointBackgroundColor: (ctx) => (ej.serie[ctx.dataIndex].programa ? ROJO : AZUL) },
      ],
    },
    plugins: [lineaVertical(etq, ej.entrada, "llegan las abogadas")],
    options: {
      interaction: { mode: "index", intersect: false },
      plugins: {
        tooltip: { callbacks: {
          title: (it) => fmtMes(it[0].label),
          label: (i) => `${i.dataset.label}: ${i.raw.toFixed(1).replace(".0", "")}`,
        } },
      },
      scales: {
        x: { ticks: { callback: (v, i) => fmtMes(etq[i]) } },
        y: { beginAtZero: true, title: { display: true, text: "Carpetas de violencia familiar / mes" } },
      },
    },
  }));
}

function indice() {
  const botones = document.querySelectorAll("#indice button");
  botones.forEach((b) => b.addEventListener("click", () =>
    document.getElementById(b.dataset.ir).scrollIntoView({ behavior: "smooth", block: "start" })));
  const obs = new IntersectionObserver((ents) => {
    ents.forEach((e) => {
      if (e.isIntersecting) botones.forEach((b) => b.classList.toggle("activo", b.dataset.ir === e.target.id));
    });
  }, { rootMargin: "0px 0px -70% 0px" });
  botones.forEach((b) => obs.observe(document.getElementById(b.dataset.ir)));

  const piezas = document.querySelectorAll(".tarjeta, .acto-veredicto, .puente");
  const rev = new IntersectionObserver((ents) => ents.forEach((e) => {
    if (e.isIntersecting) { e.target.classList.add("visible"); rev.unobserve(e.target); }
  }), { threshold: 0.08 });
  piezas.forEach((p) => { p.classList.add("revelar"); rev.observe(p); });
}

const EJEMPLO = JSON.parse(document.getElementById("datos-metodologia").textContent);
indice();
celdaDeEjemplo(EJEMPLO);
