// config.js : configuración común de la interfaz y el dashboard.
// El broker se puede cambiar sin editar el archivo: index.html?broker=ws://192.168.1.50:9001
// (útil para abrir el dashboard desde otra computadora o un celular en la misma red).
const parametros = new URLSearchParams(location.search);

const CONFIG = {
  broker: parametros.get("broker") || "ws://localhost:9001",   // listener websockets de laptop/mosquitto.conf
  nodo: "asistivo/nodo1",
  interfaz: "asistivo/interfaz",
  vision: "asistivo/vision",
};

// Menú 2 × 3 (README, sección 1). Las acciones extra de las frases 4 y 5 las hace el ESP32.
const FRASES = [
  { id: 1, texto: "Tengo hambre", icono: "🍽️" },
  { id: 2, texto: "Hola", icono: "👋" },
  { id: 3, texto: "Tengo sed", icono: "💧" },
  { id: 4, texto: "Enciende la luz", icono: "💡" },
  { id: 5, texto: "Llamar al cuidador", icono: "🔔" },
  { id: 6, texto: "Siento dolor", icono: "🤕" },
];

// Metas de las métricas (README, paso 6)
const METAS = {
  aciertos: 90,          // % en modo prueba
  tSeleccion: 5000,      // ms
  accidentales: 1,       // por cada 5 min en reposo
  latencia: 300,         // ms de ida
};

// Rangos de alerta de signos vitales: referenciales, el MAX30102 no es un dispositivo médico
const ALERTAS = { bpmMin: 50, bpmMax: 120, spo2Min: 92 };
