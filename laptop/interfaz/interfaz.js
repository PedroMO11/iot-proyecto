// interfaz.js : menú 2 × 3 del paciente (README, paso 6).
// Entradas: imu/evento mueve el cursor una casilla, vision/mirada lo pone en una región,
// emg/evento confirma o cancela. El teclado hace lo mismo (pruebas y cuidador).
// Salidas: cmd al ESP32, y estado/selecciones de la interfaz para el dashboard.
const T = {
  estadoNodo: `${CONFIG.nodo}/estado`,
  emg: `${CONFIG.nodo}/emg/evento`,
  imu: `${CONFIG.nodo}/imu/evento`,
  cmd: `${CONFIG.nodo}/cmd`,
  mirada: `${CONFIG.vision}/mirada`,
  punto: `${CONFIG.vision}/punto`,
  calibracion: `${CONFIG.vision}/calibracion`,
  visionCmd: `${CONFIG.vision}/cmd`,
  modo: `${CONFIG.interfaz}/estado`,
  seleccion: `${CONFIG.interfaz}/seleccion`,
};
const BLOQUEO_MS = 1500;                // tras confirmar, ignora confirmaciones (evita dobles)
const MODOS = ["uso", "prueba", "reposo"];

const st = {
  cursor: 1,
  modo: "uso",
  objetivo: null,                       // solo en modo prueba
  tInicio: null,                        // inicio de la selección en curso (performance.now)
  bloqueadoHasta: 0,                    // Date.now()
  visionActiva: true,
  fuente: null,                         // quién movió el cursor por última vez
  nodo: null,                           // "online" / "offline" (retenido por el ESP32)
  activacionesReposo: 0,
  calibrando: null,                     // casilla que hay que mirar durante la calibración de la visión
};
window.st = st;                         // para inspeccionar desde la consola

const $ = (id) => document.getElementById(id);
const frase = (id) => FRASES.find((f) => f.id === id);

// ---- menú ----
for (const f of FRASES) {
  const div = document.createElement("div");
  div.className = "casilla";
  div.id = `casilla-${f.id}`;
  div.innerHTML = `<span class="numero">${f.id}</span><span class="icono">${f.icono}</span><span class="texto">${f.texto}</span>`;
  $("menu").appendChild(div);
}

function render() {
  for (const f of FRASES) {
    const c = $(`casilla-${f.id}`);
    c.classList.toggle("cursor", f.id === st.cursor && !st.calibrando);
    c.classList.toggle("objetivo", f.id === st.objetivo);
    c.classList.toggle("calibrar", f.id === st.calibrando);
  }
  document.body.classList.toggle("calibrando", st.calibrando !== null);
  $("estado-modo").textContent = `Modo: ${st.modo}`;
  $("estado-fuente").textContent = `Cursor: ${{ cabeza: "cabeza", mirada: "mirada", teclado: "teclado" }[st.fuente] || "—"}` +
    (st.visionActiva ? "" : " (mirada off)");
  const nodo = $("estado-nodo");
  nodo.textContent = st.nodo === "online" ? "Nodo: conectado" : st.nodo === "offline" ? "Nodo: DESCONECTADO" : "Nodo: sin datos";
  nodo.className = "pastilla " + (st.nodo === "online" ? "bien" : "mal");

  const aviso = $("aviso");
  if (st.calibrando) {
    aviso.textContent = `Calibrando la mirada · mire la casilla ${st.calibrando} sin mover la cabeza`;
    aviso.className = "aviso";
  } else if (st.modo === "prueba" && st.objetivo) {
    aviso.textContent = `Prueba · selecciona: «${frase(st.objetivo).texto}»`;
    aviso.className = "aviso";
  } else if (st.modo === "reposo") {
    aviso.textContent = `Reposo · no se envían frases · activaciones detectadas: ${st.activacionesReposo}`;
    aviso.className = "aviso reposo";
  } else {
    aviso.className = "aviso oculto";
  }
}

let timerToast;
function toast(texto, tipo = "ok") {
  const t = $("toast");
  t.textContent = texto;
  t.className = `toast ${tipo}`;
  clearTimeout(timerToast);
  timerToast = setTimeout(() => (t.className = "toast oculto"), 1800);
}

function destello(id, clase) {
  const c = $(`casilla-${id}`);
  c.classList.add(clase);
  setTimeout(() => c.classList.remove(clase), 700);
}

// ---- cursor ----
function ponerCursor(id, fuente) {
  st.fuente = fuente;
  if (id !== st.cursor) {
    st.cursor = id;
    if (st.tInicio === null && Date.now() >= st.bloqueadoHasta) st.tInicio = performance.now();
  }
  render();
}

function mover(dir, fuente) {
  let fila = Math.floor((st.cursor - 1) / 3), col = (st.cursor - 1) % 3;
  if (dir === "izq") col = Math.max(0, col - 1);
  else if (dir === "der") col = Math.min(2, col + 1);
  else if (dir === "arriba") fila = 0;
  else if (dir === "abajo") fila = 1;
  else return;
  ponerCursor(fila * 3 + col + 1, fuente);
}

// ---- confirmar / cancelar ----
function confirmar(via) {
  const ahora = Date.now();
  if (ahora < st.bloqueadoHasta) return;
  const id = st.cursor;

  if (st.modo === "reposo") {               // no se envía: se cuenta como activación accidental
    st.activacionesReposo++;
    cliente.publicar(T.seleccion, { modo: "reposo", id, enviado: false, via, ts: ahora }, { qos: 1 });
    toast(`Activación en reposo (${st.activacionesReposo})`, "mal");
    st.bloqueadoHasta = ahora + BLOQUEO_MS;
    render();
    return;
  }

  if (st.modo === "prueba" && st.objetivo === null) {   // el temporizador del objetivo se atrasó (pestaña en segundo plano)
    nuevoObjetivo();
    return;
  }

  const tSel = st.tInicio === null ? null : Math.round(performance.now() - st.tInicio);
  const enviado = cliente.publicar(T.cmd, { accion: "frase", id }, { qos: 1 });
  cliente.publicar(T.seleccion, {
    modo: st.modo, id, frase: frase(id).texto, via, enviado,
    objetivo: st.objetivo, acierto: st.objetivo === null ? null : id === st.objetivo,
    t_seleccion_ms: tSel, ts: ahora,
  }, { qos: 1 });

  destello(id, "enviada");
  if (!enviado) toast("Sin conexión con el broker: no se envió", "mal");
  else if (st.nodo !== "online") toast(`«${frase(id).texto}» · el nodo no está conectado`, "mal");
  else toast(`${frase(id).icono} ${frase(id).texto}`);

  st.bloqueadoHasta = ahora + BLOQUEO_MS;
  st.tInicio = null;
  if (st.modo === "prueba") { st.objetivo = null; setTimeout(nuevoObjetivo, BLOQUEO_MS); }
  render();
}

function cancelar(via) {
  destello(st.cursor, "cancelada");
  toast("Cancelado", "mal");
  if (st.modo === "uso") st.tInicio = null;  // en prueba el tiempo sigue corriendo hasta acertar o fallar
}

// ---- modos ----
function nuevoObjetivo() {
  if (st.modo !== "prueba") return;
  let id;
  do { id = 1 + Math.floor(Math.random() * 6); } while (id === st.objetivo || id === st.cursor);
  st.objetivo = id;
  st.tInicio = performance.now();
  render();
}

function publicarModo() {
  cliente.publicar(T.modo, { modo: st.modo, ts: Date.now() }, { qos: 1, retain: true });
}

function cambiarModo() {
  st.modo = MODOS[(MODOS.indexOf(st.modo) + 1) % MODOS.length];
  st.objetivo = null;
  st.tInicio = null;
  if (st.modo === "prueba") nuevoObjetivo();
  if (st.modo === "reposo") st.activacionesReposo = 0;
  publicarModo();
  render();
}

// ---- cursor de la mirada: punto donde mira el usuario (x, y relativos a la zona del menú) ----
let ultimoPunto = 0;
function moverPunto(m) {
  const p = $("punto-mirada");
  const visible = st.visionActiva && !st.calibrando && typeof m.x === "number";
  p.classList.toggle("oculto", !visible);
  if (!visible) return;
  const r = $("menu").getBoundingClientRect();
  const x = r.left + Math.min(1, Math.max(0, m.x)) * r.width;
  const y = r.top + Math.min(1, Math.max(0, m.y)) * r.height;
  p.style.transform = `translate(${x}px, ${y}px)`;
  ultimoPunto = Date.now();
}
setInterval(() => { if (Date.now() - ultimoPunto > 1000) $("punto-mirada").classList.add("oculto"); }, 500);

// ---- MQTT ----
const cliente = new ClienteMQTT(CONFIG.broker, {
  clientId: "interfaz-" + Math.random().toString(16).slice(2, 8),
  onConnect: () => {
    $("estado-broker").textContent = "Broker: conectado";
    $("estado-broker").className = "pastilla bien";
    publicarModo();
  },
  onClose: () => {
    $("estado-broker").textContent = "Broker: desconectado";
    $("estado-broker").className = "pastilla mal";
  },
  onMessage: (topic, texto) => {
    const m = leerJSON(texto);
    if (topic === T.estadoNodo) { st.nodo = m; render(); }
    else if (topic === T.emg && m.tipo === "confirmar") confirmar("emg");
    else if (topic === T.emg && m.tipo === "cancelar") cancelar("emg");
    else if (topic === T.imu) mover(m.dir, "cabeza");
    else if (topic === T.mirada && st.visionActiva && !st.calibrando && m.region >= 1 && m.region <= 6) ponerCursor(m.region, "mirada");
    else if (topic === T.punto) moverPunto(m);
    else if (topic === T.calibracion) {
      if (m.estado === "mirar") st.calibrando = m.region;
      else if (m.estado === "centrar") {
        const r = $("menu").getBoundingClientRect(), c = $("centro-mirada");
        c.style.left = `${r.left + r.width / 2}px`;
        c.style.top = `${r.top + r.height / 2}px`;
        c.classList.remove("oculto");
      }
      else {
        st.calibrando = null;
        $("centro-mirada").classList.add("oculto");
        if (m.estado === "listo") toast("Mirada calibrada");
        else if (m.estado === "centrado") toast("Mirada recentrada");
        else toast(`Calibración fallida: no se vio la cara en ${(m.faltan || []).join(", ")}`, "mal");
      }
      render();
    }
  },
});
cliente.suscribir(T.estadoNodo, 1);
cliente.suscribir(T.emg, 1);
cliente.suscribir(T.imu, 1);
cliente.suscribir(T.mirada, 0);
cliente.suscribir(T.calibracion, 1);
cliente.suscribir(T.punto, 0);
cliente.conectar();

// ---- teclado ----
const FLECHAS = { ArrowLeft: "izq", ArrowRight: "der", ArrowUp: "arriba", ArrowDown: "abajo" };
document.addEventListener("keydown", (e) => {
  if (FLECHAS[e.key]) mover(FLECHAS[e.key], "teclado");
  else if (e.key === "Enter" || e.key === " ") confirmar("teclado");
  else if (e.key === "Escape" || e.key === "Backspace") cancelar("teclado");
  else if (e.key >= "1" && e.key <= "6") ponerCursor(Number(e.key), "teclado");
  else if (e.key === "m" || e.key === "M") cambiarModo();
  else if (e.key === "v" || e.key === "V") { st.visionActiva = !st.visionActiva; render(); }
  else if (e.key === "o" || e.key === "O") {
    if (cliente.publicar(T.visionCmd, { accion: "centrar" }, { qos: 1 })) toast("Mire el punto del centro");
  }
  else if (e.key === "c" || e.key === "C") {
    if (cliente.publicar(T.visionCmd, { accion: "calibrar" }, { qos: 1 })) toast("Calibrando: siga la casilla marcada con la mirada");
  }
  else if (e.key === "f" || e.key === "F") {
    if (document.fullscreenElement) document.exitFullscreen(); else document.documentElement.requestFullscreen();
  } else return;
  e.preventDefault();
});

render();
