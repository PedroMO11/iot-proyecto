// dashboard.js : panel del cuidador. Se suscribe a asistivo/# y calcula las métricas del
// README (paso 6) a partir de los mensajes: no solo los muestra, los procesa.
//  - pulso y SpO₂: promedio de 10 s, alerta fuera de rango
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
    eventos: [],                        // {t, origen, texto} (registro)
    nodo: { estado: null, desde: null, enLinea: 0, conocido: 0, caidas: 0 },
    modo: { actual: null, desde: null, reposoMs: 0 },
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

function registrar(origen, texto) {
  d.eventos.unshift({ t: Date.now(), origen, texto });
  if (d.eventos.length > 200) d.eventos.pop();
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
    registrar("nodo", retain ? `estado (retenido): ${m}` : `estado: ${m}`);
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
    registrar("EMG", `${m.tipo}${enReposo ? " (en reposo: accidental)" : ""}`);
  } else if (topic === T.imu) {
    registrar("IMU", `cabeza: ${m.dir}`);
  } else if (topic === T.cmd) {
    const f = m.accion === "frase" ? FRASES.find((x) => x.id === m.id) : null;
    registrar("comando", f ? `frase ${m.id}: «${f.texto}»` : texto);
  } else if (topic === T.actuadores) {
    if (typeof m.luz === "boolean") { $("p-luz").textContent = `Luz: ${m.luz ? "encendida" : "apagada"}`; $("p-luz").classList.remove("oculto"); }
  } else if (topic === T.modo) {
    acumularModo(ahora);
    d.modo.actual = m.modo;
    registrar("interfaz", `modo ${m.modo}`);
  } else if (topic === T.seleccion) {
    d.selecciones.push({ ...m, t: ahora });
    if (m.modo !== "reposo") {
      const extra = m.acierto === true ? " ✔ acierto" : m.acierto === false ? " ✘ error" : "";
      registrar("interfaz", `selección ${m.id} por ${m.via}` + (m.t_seleccion_ms !== null ? ` en ${(m.t_seleccion_ms / 1000).toFixed(1)} s` : "") + extra);
    }
  }
}

// ---- métricas ----
function kpi(id, valor, detalle, estado, textoMeta) {
  const k = $(id);
  k.querySelector(".valor").innerHTML = valor;
  if (detalle !== undefined) k.querySelector(".detalle").textContent = detalle;
  const meta = k.querySelector(".meta");
  meta.textContent = textoMeta;
  meta.className = "meta" + (estado === true ? " bien" : estado === false ? " mal" : "");
}

function actualizar() {
  const ahora = Date.now();
  acumularNodo(ahora);
  acumularModo(ahora);
  d.vitales = d.vitales.filter((v) => v.t > ahora - VENTANA_MS);
  d.latencias = d.latencias.filter((v) => v.t > ahora - VENTANA_MS);

  // pulso y SpO₂
  const rec = d.vitales.filter((v) => v.t > ahora - PROMEDIO_MS);
  const bpm = promedio(rec.map((v) => v.bpm).filter((x) => x !== null));
  const spo2 = promedio(rec.map((v) => v.spo2).filter((x) => x !== null));
  const alertas = [];
  if (bpm !== null && (bpm < ALERTAS.bpmMin || bpm > ALERTAS.bpmMax)) alertas.push(`pulso ${Math.round(bpm)} BPM`);
  if (spo2 !== null && spo2 < ALERTAS.spo2Min) alertas.push(`SpO₂ ${spo2.toFixed(0)} %`);
  const sinDedo = rec.length > 0 && bpm === null;
  kpi("k-bpm", bpm === null ? "—" : `${Math.round(bpm)} <small>BPM</small>`, sinDedo ? "sin dedo en el sensor" : "promedio de 10 s",
      bpm === null ? null : !alertas.some((a) => a.startsWith("pulso")), `rango ${ALERTAS.bpmMin}–${ALERTAS.bpmMax}`);
  kpi("k-spo2", spo2 === null ? "—" : `${spo2.toFixed(0)} <small>%</small>`, undefined,
      spo2 === null ? null : spo2 >= ALERTAS.spo2Min, `alerta < ${ALERTAS.spo2Min} %`);
  $("k-bpm").classList.toggle("alerta-kpi", alertas.some((a) => a.startsWith("pulso")));
  $("k-spo2").classList.toggle("alerta-kpi", alertas.some((a) => a.startsWith("SpO")));
  $("alerta").textContent = alertas.length ? `⚠ Revisar al paciente: ${alertas.join(" · ")}` : "";
  $("alerta").classList.toggle("oculto", alertas.length === 0);

  // latencia
  const ult = d.latencias.slice(-30).map((v) => v.ida);
  const sinPong = d.ultimoPing - d.ultimoPong > 5000 && d.nodo.estado === "online";
  const latMed = mediana(ult);
  kpi("k-latencia", latMed === null ? "—" : `${Math.round(latMed)} <small>ms</small>`,
      sinPong ? "el nodo no responde al ping" : latMed === null ? "esperando ping/pong" : `p90 ${Math.round(percentil(ult, 90))} ms · ${ult.length} muestras`,
      latMed === null ? null : latMed < METAS.latencia, `meta < ${METAS.latencia} ms`);

  // aciertos (solo modo prueba)
  const pruebas = d.selecciones.filter((s) => s.modo === "prueba" && s.acierto !== null && s.acierto !== undefined);
  const ok = pruebas.filter((s) => s.acierto).length;
  const tasa = pruebas.length ? (100 * ok) / pruebas.length : null;
  kpi("k-aciertos", tasa === null ? "—" : `${tasa.toFixed(0)} <small>%</small>`, `${ok} de ${pruebas.length} en modo prueba`,
      tasa === null ? null : tasa >= METAS.aciertos, `meta ≥ ${METAS.aciertos} %`);

  // tiempo de selección
  const tiempos = d.selecciones.filter((s) => s.modo !== "reposo" && typeof s.t_seleccion_ms === "number").map((s) => s.t_seleccion_ms);
  const tMed = mediana(tiempos);
  kpi("k-tsel", tMed === null ? "—" : `${(tMed / 1000).toFixed(1)} <small>s</small>`,
      tMed === null ? "mediana" : `mediana de ${tiempos.length} · máx. ${(Math.max(...tiempos) / 1000).toFixed(1)} s`,
      tMed === null ? null : tMed <= METAS.tSeleccion, `meta ≤ ${METAS.tSeleccion / 1000} s`);

  // activaciones accidentales
  const minReposo = d.modo.reposoMs / 60000;
  const tasaAcc = minReposo >= 1 ? (d.accidentales / minReposo) * 5 : null;
  kpi("k-accidentales", tasaAcc === null ? "—" : `${tasaAcc.toFixed(1)}`,
      minReposo < 1 ? `${d.accidentales} en ${minReposo.toFixed(1)} min de reposo (mínimo 1 min)` : `${d.accidentales} en ${minReposo.toFixed(1)} min de reposo`,
      tasaAcc === null ? null : tasaAcc <= METAS.accidentales, `meta ≤ ${METAS.accidentales} / 5 min`);

  // cabecera y disponibilidad
  const n = d.nodo;
  $("p-nodo").textContent = n.estado === "online" ? "Nodo: en línea" : n.estado === "offline" ? "Nodo: DESCONECTADO" : "Nodo: sin datos";
  $("p-nodo").className = "pastilla " + (n.estado === "online" ? "bien" : n.estado === "offline" ? "mal" : "");
  $("p-interfaz").textContent = d.modo.actual ? `Interfaz: modo ${d.modo.actual}` : "Interfaz: sin datos";
  $("d-disponibilidad").textContent = n.conocido > 0 ? `${((100 * n.enLinea) / n.conocido).toFixed(1)} % de ${(n.conocido / 60000).toFixed(1)} min` : "—";
  $("d-caidas").textContent = n.caidas;
  $("d-enviadas").textContent = d.selecciones.filter((s) => s.modo !== "reposo" && s.enviado).length;
  $("d-cancelaciones").textContent = d.cancelaciones;
  $("d-reposo").textContent = `${minReposo.toFixed(1)} min`;

  $("t-eventos").innerHTML = d.eventos.slice(0, 40)
    .map((e) => `<tr><td>${hora(e.t)}</td><td>${e.origen}</td><td>${e.texto.replace(/</g, "&lt;")}</td></tr>`).join("");

  // gráficos
  const css = getComputedStyle(document.documentElement);
  dibujarGrafico($("g-vitales"), [
    { datos: d.vitales.map((v) => [v.t, v.bpm]), color: css.getPropertyValue("--bpm"), rango: [40, 140], eje: "izq" },
    { datos: d.vitales.map((v) => [v.t, v.spo2]), color: css.getPropertyValue("--spo2"), rango: [80, 100], eje: "der" },
  ], { ventanaMs: VENTANA_MS, ahora });
  const maxLat = Math.max(400, ...d.latencias.map((v) => v.ida));
  dibujarGrafico($("g-latencia"), [
    { datos: d.latencias.map((v) => [v.t, v.ida]), color: css.getPropertyValue("--lat"), rango: [0, Math.ceil(maxLat / 100) * 100], tipo: "puntos" },
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
  const { estado } = d.nodo, actual = d.modo.actual;
  d = datosNuevos();
  d.nodo.estado = estado; d.nodo.desde = Date.now();
  d.modo.actual = actual; d.modo.desde = Date.now();
  registrar("panel", "métricas reiniciadas");
};
$("nombre-nodo").textContent = CONFIG.nodo;

// ---- MQTT ----
const cliente = new ClienteMQTT(CONFIG.broker, {
  clientId: "dashboard-" + ID,
  onConnect: () => { $("p-broker").textContent = "Broker: conectado"; $("p-broker").className = "pastilla bien"; registrar("panel", "conectado al broker"); },
  onClose: () => { $("p-broker").textContent = "Broker: desconectado"; $("p-broker").className = "pastilla mal"; registrar("panel", "sin conexión al broker"); },
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
