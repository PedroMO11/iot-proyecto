// mqtt-ws.js : cliente MQTT 3.1.1 mínimo sobre WebSocket, sin dependencias.
// Soporta lo que necesitan la interfaz y el dashboard: CONNECT (con Last Will),
// SUBSCRIBE, PUBLISH QoS 0/1 (con retain), PUBACK, PINGREQ y reconexión automática.
// Mosquitto debe tener un listener "protocol websockets" (ver laptop/mosquitto.conf).

class ClienteMQTT {
  constructor(url, opciones = {}) {
    this.url = url;
    this.clientId = opciones.clientId || "web-" + Math.random().toString(16).slice(2, 10);
    this.keepalive = opciones.keepalive || 30;      // s
    this.will = opciones.will || null;              // {topic, payload, qos, retain}
    this.onConnect = opciones.onConnect || (() => {});
    this.onClose = opciones.onClose || (() => {});
    this.onMessage = opciones.onMessage || (() => {});
    this.suscripciones = [];                        // [{topic, qos}], se repiten al reconectar
    this.conectado = false;
    this.idPaquete = 1;
    this.buf = new Uint8Array(0);
    this.enc = new TextEncoder();
    this.dec = new TextDecoder();
  }

  conectar() {
    this.ws = new WebSocket(this.url, "mqtt");
    this.ws.binaryType = "arraybuffer";
    this.ws.onopen = () => this.ws.send(this.paqueteConnect());
    this.ws.onmessage = (e) => this.recibir(new Uint8Array(e.data));
    this.ws.onclose = () => {
      const antes = this.conectado;
      this.conectado = false;
      clearInterval(this.timerPing);
      if (antes) this.onClose();
      setTimeout(() => this.conectar(), 2000);       // reintentar
    };
    this.ws.onerror = () => {};                      // onclose se encarga
  }

  suscribir(topic, qos = 0) {
    this.suscripciones.push({ topic, qos });
    if (this.conectado) this.ws.send(this.paqueteSubscribe([{ topic, qos }]));
  }

  publicar(topic, payload, { qos = 0, retain = false } = {}) {
    if (!this.conectado) return false;
    const texto = typeof payload === "string" ? payload : JSON.stringify(payload);
    const partes = [this.cadena(topic)];
    if (qos > 0) partes.push(this.u16(this.nuevoId()));
    partes.push(this.enc.encode(texto));
    this.ws.send(this.paquete(0x30 | (qos << 1) | (retain ? 1 : 0), partes));
    return true;
  }

  // ---- codificación ----
  u16(n) { return new Uint8Array([(n >> 8) & 0xff, n & 0xff]); }
  cadena(s) { const b = this.enc.encode(s); return this.concat([this.u16(b.length), b]); }
  nuevoId() { this.idPaquete = (this.idPaquete % 65535) + 1; return this.idPaquete; }

  concat(partes) {
    const total = partes.reduce((n, p) => n + p.length, 0);
    const out = new Uint8Array(total);
    let i = 0;
    for (const p of partes) { out.set(p, i); i += p.length; }
    return out;
  }

  paquete(cabecera, partes) {                        // cabecera fija + longitud restante (varint)
    const cuerpo = this.concat(partes);
    const largo = [];
    let n = cuerpo.length;
    do { let b = n % 128; n = Math.floor(n / 128); if (n > 0) b |= 0x80; largo.push(b); } while (n > 0);
    return this.concat([new Uint8Array([cabecera, ...largo]), cuerpo]);
  }

  paqueteConnect() {
    let flags = 0x02;                                // clean session
    const payload = [this.cadena(this.clientId)];
    if (this.will) {
      flags |= 0x04 | ((this.will.qos || 0) << 3) | (this.will.retain ? 0x20 : 0);
      payload.push(this.cadena(this.will.topic), this.cadena(this.will.payload));
    }
    return this.paquete(0x10, [this.cadena("MQTT"), new Uint8Array([4, flags]), this.u16(this.keepalive), ...payload]);
  }

  paqueteSubscribe(lista) {
    const partes = [this.u16(this.nuevoId())];
    for (const s of lista) partes.push(this.cadena(s.topic), new Uint8Array([s.qos]));
    return this.paquete(0x82, partes);
  }

  // ---- decodificación (un frame puede traer varios paquetes o uno partido) ----
  recibir(datos) {
    this.buf = this.concat([this.buf, datos]);
    while (this.buf.length >= 2) {
      let mult = 1, largo = 0, i = 1, b;
      do {
        if (i >= this.buf.length) return;            // falta la longitud completa
        b = this.buf[i++]; largo += (b & 0x7f) * mult; mult *= 128;
      } while (b & 0x80);
      if (this.buf.length < i + largo) return;       // falta el cuerpo
      this.procesar(this.buf[0], this.buf.subarray(i, i + largo));
      this.buf = this.buf.slice(i + largo);
    }
  }

  procesar(cab, cuerpo) {
    const tipo = cab >> 4;
    if (tipo === 2) {                                // CONNACK
      if (cuerpo[1] !== 0) { console.warn("CONNACK rechazado:", cuerpo[1]); return; }
      this.conectado = true;
      if (this.suscripciones.length) this.ws.send(this.paqueteSubscribe(this.suscripciones));
      this.timerPing = setInterval(() => this.ws.send(new Uint8Array([0xc0, 0])), this.keepalive * 500);
      this.onConnect();
    } else if (tipo === 3) {                         // PUBLISH
      const qos = (cab >> 1) & 3, retain = !!(cab & 1);
      const lt = (cuerpo[0] << 8) | cuerpo[1];
      const topic = this.dec.decode(cuerpo.subarray(2, 2 + lt));
      let j = 2 + lt;
      if (qos > 0) {
        const id = (cuerpo[j] << 8) | cuerpo[j + 1]; j += 2;
        this.ws.send(new Uint8Array([0x40, 2, id >> 8, id & 0xff]));   // PUBACK
      }
      this.onMessage(topic, this.dec.decode(cuerpo.subarray(j)), { retain });
    }
    // SUBACK, PUBACK y PINGRESP no necesitan respuesta
  }
}

// Evalúa si un topic concreto calza con un filtro con + y #
function calzaTopic(filtro, topic) {
  const f = filtro.split("/"), t = topic.split("/");
  for (let i = 0; i < f.length; i++) {
    if (f[i] === "#") return true;
    if (f[i] !== "+" && f[i] !== t[i]) return false;
  }
  return f.length === t.length;
}

// Interpreta un payload como JSON; si no lo es, devuelve el texto
function leerJSON(texto) {
  try { return JSON.parse(texto); } catch { return texto; }
}
