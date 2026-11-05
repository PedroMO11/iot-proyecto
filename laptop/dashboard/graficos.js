// graficos.js : gráfico de líneas/puntos en <canvas>, sin dependencias.
// series: [{ datos: [[t_ms, valor], ...], color, rango: [min, max], eje: "izq" | "der", tipo: "linea" | "puntos" }]
// opciones: { ventanaMs, ahora, lineas: [{ valor, color, serie }] }
function dibujarGrafico(canvas, series, opciones) {
  const css = getComputedStyle(document.documentElement);
  const tenue = css.getPropertyValue("--tenue").trim();
  const linea = css.getPropertyValue("--linea").trim();
  const dpr = window.devicePixelRatio || 1;
  const ancho = canvas.clientWidth, alto = canvas.clientHeight;
  if (canvas.width !== ancho * dpr || canvas.height !== alto * dpr) { canvas.width = ancho * dpr; canvas.height = alto * dpr; }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, ancho, alto);

  const m = { izq: 40, der: series.some((s) => s.eje === "der") ? 40 : 12, arr: 8, abj: 22 };
  const w = ancho - m.izq - m.der, h = alto - m.arr - m.abj;
  const t1 = opciones.ahora, t0 = t1 - opciones.ventanaMs;
  const x = (t) => m.izq + ((t - t0) / (t1 - t0)) * w;
  const y = (v, r) => m.arr + h - ((v - r[0]) / (r[1] - r[0])) * h;

  ctx.font = "11px 'JetBrainsMono NFM', 'DejaVu Sans Mono', monospace";
  ctx.strokeStyle = linea; ctx.fillStyle = tenue; ctx.lineWidth = 1;

  // rejilla y ejes (4 divisiones) con las escalas de la primera serie de cada lado
  const izq = series.find((s) => s.eje !== "der"), der = series.find((s) => s.eje === "der");
  for (let i = 0; i <= 4; i++) {
    const yy = m.arr + (h * i) / 4;
    ctx.beginPath(); ctx.moveTo(m.izq, yy); ctx.lineTo(m.izq + w, yy); ctx.stroke();
    if (izq) { ctx.textAlign = "right"; ctx.fillText(Math.round(izq.rango[1] - ((izq.rango[1] - izq.rango[0]) * i) / 4), m.izq - 6, yy + 4); }
    if (der) { ctx.textAlign = "left"; ctx.fillText(Math.round(der.rango[1] - ((der.rango[1] - der.rango[0]) * i) / 4), m.izq + w + 6, yy + 4); }
  }
  ctx.textAlign = "center";
  for (let i = 0; i <= 5; i++) {
    const t = t0 + ((t1 - t0) * i) / 5;
    const seg = Math.round((t - t1) / 1000);
    ctx.fillText(seg === 0 ? "ahora" : `${seg} s`, x(t), alto - 6);
  }

  // líneas de referencia (metas)
  for (const l of opciones.lineas || []) {
    const r = series[l.serie || 0].rango;
    ctx.save(); ctx.setLineDash([6, 4]); ctx.strokeStyle = l.color;
    ctx.beginPath(); ctx.moveTo(m.izq, y(l.valor, r)); ctx.lineTo(m.izq + w, y(l.valor, r)); ctx.stroke(); ctx.restore();
  }

  // series (se corta la línea si hay un hueco de más de 5 s entre puntos)
  ctx.save(); ctx.beginPath(); ctx.rect(m.izq, m.arr, w, h); ctx.clip();
  for (const s of series) {
    const d = s.datos.filter((p) => p[0] >= t0 && p[1] !== null && p[1] !== undefined);
    ctx.strokeStyle = ctx.fillStyle = s.color; ctx.lineWidth = 2;
    if (s.tipo === "puntos") {
      for (const p of d) { ctx.beginPath(); ctx.arc(x(p[0]), y(p[1], s.rango), 3, 0, 2 * Math.PI); ctx.fill(); }
    } else {
      ctx.beginPath();
      d.forEach((p, i) => {
        const cortar = i === 0 || p[0] - d[i - 1][0] > 5000;
        cortar ? ctx.moveTo(x(p[0]), y(p[1], s.rango)) : ctx.lineTo(x(p[0]), y(p[1], s.rango));
      });
      ctx.stroke();
    }
  }
  ctx.restore();
  if (!series.some((s) => s.datos.some((p) => p[0] >= t0 && p[1] !== null))) {
    ctx.fillStyle = tenue; ctx.textAlign = "center"; ctx.font = "12px 'JetBrainsMono NFM', 'DejaVu Sans Mono', monospace";
    ctx.fillText("sin datos todavía", m.izq + w / 2, m.arr + h / 2);
  }
}
