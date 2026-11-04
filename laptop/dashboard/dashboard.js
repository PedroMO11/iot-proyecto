// dashboard.js : panel del cuidador. Se suscribe a asistivo/# y calcula las métricas del
// README (paso 6) a partir de los mensajes: no solo los muestra, los procesa.
//  - pulso y SpO₂: promedio de 10 s, alarma fuera de rango
//  - latencia MQTT: ping/pong con el ESP32 cada 2 s (RTT / 2)
//  - tasa de aciertos y tiempo de selección: de las selecciones de la interfaz
//  - activaciones accidentales: confirmaciones del EMG mientras la interfaz está en reposo
//  - disponibilidad: % del tiempo con el nodo en línea, y número de desconexiones
const T = {
  estado: `${CONFIG.nodo}/estado`,
  vitales: `${CONFIG.nodo}/vitales`,
  emg: `${CONFIG.nodo}/emg/evento`,
  imu: `${CONFIG.nodo}/imu/evento`,
  cmd: `${CONFIG.nodo}/cmd`,
  ping: `${CONFIG.nodo}/ping`,
  pong: `${CONFIG.nodo}/pong`,
  actuadores: `${CONFIG.nodo}/actuadores`,
  modo: `${CONFIG.interfaz}/estado`,
  seleccion: `${CONFIG.interfaz}/seleccion`,
  visionEstado: `${CONFIG.vision}/estado`,
  calibracion: `${CONFIG.vision}/calibracion`,
};
const VENTANA_MS = 5 * 60 * 1000;       // gráficos
const PROMEDIO_MS = 10 * 1000;          // pulso y SpO₂
const PING_MS = 2000;
const ID = Math.random().toString(16).slice(2, 8);   // para reconocer los pong propios

let d;                                  // todos los datos, para poder reiniciarlos
function datosNuevos() {
  return {
    inicio: Date.now(),
    vitales: [],                        // {t, bpm, spo2}
    latencias: [],                      // {t, ida}
    selecciones: [],                    // mensajes de interfaz/seleccion + t
    eventos: [],                        // {t, origen, texto, clase}
    nodo: { estado: null, desde: null, enLinea: 0, conocido: 0, caidas: 0 },
    modo: { actual: null, desde: null, reposoMs: 0 },
    vision: null, visionT: 0,
    luz: null,
    accidentales: 0,
    cancelaciones: 0,
    ultimoPing: 0, ultimoPong: 0,
  };
}
d = datosNuevos();

const $ = (id) => document.getElementById(id);
const hora = (t) => new Date(t).toLocaleTimeString("es-PE", { hour12: false });
const mediana = (v) => { const s = [...v].sort((a, b) => a - b); const n = s.length; return n ? (n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2) : null; };
const percentil = (v, p) => { const s = [...v].sort((a, b) => a - b); return s.length ? s[Math.min(s.length - 1, Math.floor((p / 100) * s.length))] : null; };
const promedio = (v) => (v.length ? v.reduce((a, b) => a + b, 0) / v.length : null);

function registrar(origen, texto, clase = "") {
  d.eventos.unshift({ t: Date.now(), origen, texto, clase });
  if (d.eventos.length > 300) d.eventos.pop();
}

// ---- estados que se acumulan en el tiempo ----
function acumularNodo(ahora) {
  const n = d.nodo;
  if (n.estado && n.desde) {
    const dt = ahora - n.desde;
    n.conocido += dt;
    if (n.estado === "online") n.enLinea += dt;
  }
  n.desde = ahora;
}
function acumularModo(ahora) {
  if (d.modo.actual === "reposo" && d.modo.desde) d.modo.reposoMs += ahora - d.modo.desde;
  d.modo.desde = ahora;
}

// ---- mensajes ----
function alMensaje(topic, texto, { retain }) {
  const ahora = Date.now();
  const m = leerJSON(texto);
  if (topic === T.estado) {
    acumularNodo(ahora);
    if (d.nodo.estado === "online" && m === "offline") d.nodo.caidas++;
    d.nodo.estado = m;
    registrar("nodo", retain ? `${m} (retenido)` : m, m === "offline" ? "mal" : "ok");
  } else if (topic === T.vitales) {
    const bpm = typeof m.bpm === "number" ? m.bpm : null, spo2 = typeof m.spo2 === "number" ? m.spo2 : null;
    d.vitales.push({ t: ahora, bpm, spo2 });
  } else if (topic === T.pong && typeof m === "string" && m.startsWith(`d${ID}:`)) {
    const enviado = Number(m.split(":")[1]);
    d.latencias.push({ t: ahora, ida: (ahora - enviado) / 2 });
    d.ultimoPong = ahora;
  } else if (topic === T.emg) {
    if (m.tipo === "cancelar") d.cancelaciones++;
    const enReposo = m.tipo === "confirmar" && d.modo.actual === "reposo";
    if (enReposo) d.accidentales++;
    registrar("emg", `${m.tipo}${enReposo ? "  ← accidental (reposo)" : ""}`, enReposo ? "mal" : "emg");
  } else if (topic === T.imu) {
    registrar("imu", `cabeza ${m.dir}`);
  } else if (topic === T.cmd) {
    const f = m.accion === "frase" ? FRASES.find((x) => x.id === m.id) : null;
    registrar("cmd", f ? `frase ${m.id} «${f.texto}»` : texto);
  } else if (topic === T.actuadores) {
    if (typeof m.luz === "boolean") d.luz = m.luz;
  } else if (topic === T.modo) {
    acumularModo(ahora);
    d.modo.actual = m.modo;
    registrar("interfaz", `modo ${m.modo}`);
  } else if (topic === T.seleccion) {
    d.selecciones.push({ ...m, t: ahora });
    if (m.modo !== "reposo") {
      const extra = m.acierto === true ? "  ✓ acierto" : m.acierto === false ? "  ✗ error" : "";
      const tSel = typeof m.t_seleccion_ms === "number" ? ` en ${(m.t_seleccion_ms / 1000).toFixed(1)} s` : "";
      registrar("interfaz", `selección ${m.id} por ${m.via}${tSel}${extra}`, m.acierto === false ? "mal" : m.acierto ? "ok" : "");
    }
  } else if (topic === T.visionEstado) {
    d.vision = m; d.visionT = ahora;
  } else if (topic === T.calibracion) {
    if (m.estado === "mirar" && m.paso === 1) registrar("visión", m.fase === "centro" ? "recentrado" : m.fase === "validacion" ? "comprobación de la calibración" : "calibración iniciada");
    else if (m.estado === "listo") registrar("visión", `calibrada · ${Math.round(m.acierto)} % de casillas · error x ${m.error_x} %, y ${m.error_y} %`, m.acierto >= 85 ? "ok" : "mal");
    else if (m.estado === "error") registrar("visión", `${m.fase} fallida (puntos ${(m.faltan || []).join(", ")})`, "mal");
  }
}

// ---- dibujo ----
function fila(id, valor, detalle, cumple) {
  const r = $(id);
  r.querySelector(".val").textContent = valor;
  r.querySelector(".det").textContent = detalle;
  const ok = r.querySelector(".ok");
  ok.textContent = cumple === true ? "cumple" : cumple === false ? "no cumple" : "";
  ok.className = "ok" + (cumple === true ? " si" : cumple === false ? " no" : "");
}

function parametro(id, valor, texto, alarma) {
  $(`v-${id}`).textContent = valor === null ? "--" : valor;
  $(`d-${id}`).textContent = texto;
  $(`p-${id}`).classList.toggle("alarma-param", alarma);
  $(`p-${id}`).classList.toggle("sin-dato", valor === null);
}

function estado(id, clase, html) {
  $(id).className = "estado " + clase;
  $(id).innerHTML = `<i></i>${html}`;
}

function actualizar() {
  const ahora = Date.now();
  acumularNodo(ahora);
  acumularModo(ahora);
  d.vitales = d.vitales.filter((v) => v.t > ahora - VENTANA_MS);
  d.latencias = d.latencias.filter((v) => v.t > ahora - VENTANA_MS);
  $("s-reloj").textContent = hora(ahora);

  // signos vitales
  const rec = d.vitales.filter((v) => v.t > ahora - PROMEDIO_MS);
  const bpm = promedio(rec.map((v) => v.bpm).filter((x) => x !== null));
  const spo2 = promedio(rec.map((v) => v.spo2).filter((x) => x !== null));
  const alarmaFC = bpm !== null && (bpm < ALERTAS.bpmMin || bpm > ALERTAS.bpmMax);
  const alarmaSp = spo2 !== null && spo2 < ALERTAS.spo2Min;
  const sinDedo = rec.length > 0 && bpm === null;
  const sinDatos = rec.length === 0;
  const pie = sinDatos ? "sin datos del nodo" : sinDedo ? "sin dedo en el sensor" : "promedio de 10 s";
  parametro("bpm", bpm === null ? null : Math.round(bpm), pie, alarmaFC);
  parametro("spo2", spo2 === null ? null : Math.round(spo2), pie, alarmaSp);
  const alertas = [];
  if (alarmaFC) alertas.push(`FC ${Math.round(bpm)} lpm`);
  if (alarmaSp) alertas.push(`SpO₂ ${Math.round(spo2)} %`);
  $("alerta").textContent = `ALARMA · revisar al paciente · ${alertas.join(" · ")}`;
  $("alerta").classList.toggle("oculto", alertas.length === 0);

  // estado de la cabecera
  const n = d.nodo;
  if (n.estado === "online") estado("s-nodo", "bien", "<b>Nodo</b> en línea");
  else if (n.estado === "offline") estado("s-nodo", "mal", "<b>Nodo</b> DESCONECTADO");
  else estado("s-nodo", "", "<b>Nodo</b> sin datos");

  // ficha del sistema
  const ult = d.latencias.slice(-30).map((v) => v.ida);
  const latMed = mediana(ult);
  const sinPong = d.ultimoPing - d.ultimoPong > 5000 && n.estado === "online";
  $("m-latencia").innerHTML = latMed === null ? (sinPong ? "el nodo no responde al ping" : "—")
    : `${Math.round(latMed)} ms <small>p90 ${Math.round(percentil(ult, 90))} · ${ult.length} ping</small>`;
  $("m-latencia").className = latMed !== null && latMed >= METAS.latencia ? "mal" : "";
  $("m-disp").innerHTML = n.conocido > 0 ? `${((100 * n.enLinea) / n.conocido).toFixed(1)} % <small>de ${(n.conocido / 60000).toFixed(1)} min</small>` : "—";
  $("m-caidas").textContent = n.caidas;
  $("m-modo").textContent = d.modo.actual ? `modo ${d.modo.actual}` : "sin datos";
  const v = d.vision;
  if (!v || ahora - d.visionT > 6000 || v.activo === false) $("m-vision").innerHTML = "inactiva";
  else {
    const cal = !v.calibrado ? "sin calibrar" : v.calidad ? `${Math.round(v.calidad.acierto)} % casillas · error ${v.calidad.error.toFixed(1)} %` : "calibrada";
    $("m-vision").innerHTML = `${v.cara ? "cara detectada" : `<span style='color:var(--ambar)'>sin cara${v.brillo < 60 ? " · poca luz" : ""}</span>`} <small>${v.fps} fps · ${cal}${v.region ? ` · casilla ${v.region}` : ""}</small>`;
  }
  $("m-luz").textContent = d.luz === null ? "—" : d.luz ? "encendida" : "apagada";

  // pruebas de uso
  const pruebas = d.selecciones.filter((s) => s.modo === "prueba" && typeof s.acierto === "boolean");
  const ok = pruebas.filter((s) => s.acierto).length;
  const tasa = pruebas.length ? (100 * ok) / pruebas.length : null;
  fila("r-aciertos", tasa === null ? "—" : `${tasa.toFixed(0)} %`, `${ok} de ${pruebas.length} en modo prueba`,
       tasa === null ? null : tasa >= METAS.aciertos);
  const tiempos = d.selecciones.filter((s) => s.modo !== "reposo" && typeof s.t_seleccion_ms === "number").map((s) => s.t_seleccion_ms);
  const tMed = mediana(tiempos);
  fila("r-tsel", tMed === null ? "—" : `${(tMed / 1000).toFixed(1)} s`,
       tMed === null ? "mediana" : `mediana de ${tiempos.length} · máx. ${(Math.max(...tiempos) / 1000).toFixed(1)} s`,
       tMed === null ? null : tMed <= METAS.tSeleccion);
  const minReposo = d.modo.reposoMs / 60000;
  const tasaAcc = minReposo >= 1 ? (d.accidentales / minReposo) * 5 : null;
  fila("r-accidentales", tasaAcc === null ? "—" : `${tasaAcc.toFixed(1)}`,
       `${d.accidentales} en ${minReposo.toFixed(1)} min de reposo${minReposo < 1 ? " (mín. 1 min)" : ""}`,
       tasaAcc === null ? null : tasaAcc <= METAS.accidentales);
  $("r-enviadas").querySelector(".val").textContent =
    `${d.selecciones.filter((s) => s.modo !== "reposo" && s.enviado).length} · ${d.cancelaciones}`;

  // registro
  const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;");
  $("t-eventos").innerHTML = d.eventos.slice(0, 60)
    .map((e) => `<span class="o">${hora(e.t)}  ${e.origen.padEnd(9)}</span><span class="${e.clase}">${esc(e.texto)}</span>`).join("\n");

  // gráficos
  const css = getComputedStyle(document.documentElement);
  dibujarGrafico($("g-vitales"), [
    { datos: d.vitales.map((x) => [x.t, x.bpm]), color: css.getPropertyValue("--fc"), rango: [40, 140], eje: "izq" },
    { datos: d.vitales.map((x) => [x.t, x.spo2]), color: css.getPropertyValue("--spo2"), rango: [80, 100], eje: "der" },
  ], { ventanaMs: VENTANA_MS, ahora });
  const maxLat = Math.max(400, ...d.latencias.map((x) => x.ida));
  dibujarGrafico($("g-latencia"), [
    { datos: d.latencias.map((x) => [x.t, x.ida]), color: css.getPropertyValue("--lat"), rango: [0, Math.ceil(maxLat / 100) * 100], tipo: "puntos" },
  ], { ventanaMs: VENTANA_MS, ahora, lineas: [{ valor: METAS.latencia, color: css.getPropertyValue("--mal") }] });
}

// ---- exportar (datos para las figuras del informe) ----
function exportarCSV() {
  const iso = (t) => new Date(t).toISOString();
  const filas = [["tipo", "hora", "a", "b", "c", "d", "e"]];
  for (const v of d.vitales) filas.push(["vitales", iso(v.t), v.bpm ?? "", v.spo2 ?? ""]);
  for (const v of d.latencias) filas.push(["latencia_ida_ms", iso(v.t), v.ida.toFixed(1)]);
  for (const s of d.selecciones) filas.push(["seleccion", iso(s.t), s.modo, s.id, s.via, s.t_seleccion_ms ?? "", s.acierto ?? ""]);
  for (const e of [...d.eventos].reverse()) filas.push(["evento", iso(e.t), e.origen, `"${e.texto.replace(/"/g, '""')}"`]);
  const blob = new Blob([filas.map((f) => f.join(",")).join("\n")], { type: "text/csv" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `metricas_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.csv`;
  a.click();
}

$("b-csv").onclick = exportarCSV;
$("b-reiniciar").onclick = () => {
  const { estado: e } = d.nodo, actual = d.modo.actual, vision = d.vision, visionT = d.visionT, luz = d.luz;
  d = datosNuevos();
  d.nodo.estado = e; d.nodo.desde = Date.now();
  d.modo.actual = actual; d.modo.desde = Date.now();
  d.vision = vision; d.visionT = visionT; d.luz = luz;
  registrar("panel", "métricas reiniciadas");
};
$("nombre-nodo").textContent = CONFIG.nodo.split("/").pop();
$("l-bpm").innerHTML = `${ALERTAS.bpmMax}<br>${ALERTAS.bpmMin}`;
$("l-spo2").innerHTML = `<br>${ALERTAS.spo2Min}`;

// ---- MQTT ----
const cliente = new ClienteMQTT(CONFIG.broker, {
  clientId: "dashboard-" + ID,
  onConnect: () => { estado("s-broker", "bien", "<b>Broker</b> conectado"); registrar("panel", "conectado al broker", "ok"); },
  onClose: () => { estado("s-broker", "mal", "<b>Broker</b> desconectado"); registrar("panel", "sin conexión al broker", "mal"); },
  onMessage: alMensaje,
});
cliente.suscribir("asistivo/#", 1);
cliente.conectar();

setInterval(() => {
  if (cliente.publicar(T.ping, `d${ID}:${Date.now()}`)) d.ultimoPing = Date.now();
}, PING_MS);
setInterval(actualizar, 1000);
window.addEventListener("resize", actualizar);
actualizar();
window.d = () => d;                     // para inspeccionar desde la consola
