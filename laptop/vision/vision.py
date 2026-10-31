# vision.py : módulo de visión (README, paso 6). Webcam → MediaPipe FaceLandmarker (478 landmarks,
# con iris) → región de la mirada 1..6 en el menú 2 × 3 → asistivo/vision/mirada.
# Publica {"region":N} solo cuando la región cambia (así la cabeza puede seguir moviendo el cursor)
# y {"region":null} si se pierde la cara.
# Teclas en la ventana de vista previa:
#   c → calibrar: mirar cada casilla cuando se ilumina (≈ 15 s)    r → volver a la calibración por defecto
#   p → pausar / reanudar la publicación                           q / Esc → salir
# Uso:  python laptop/vision/vision.py [--broker localhost] [--camara 0] [--sin-mqtt]
import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
import paho.mqtt.client as mqtt
from mediapipe.tasks.python import BaseOptions, vision

AQUI = Path(__file__).resolve().parent
MODELO = AQUI / "modelos" / "face_landmarker.task"
URL_MODELO = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/"
              "face_landmarker/float16/latest/face_landmarker.task")
ARCHIVO_CALIB = AQUI / "calibracion.json"

# Landmarks de Face Mesh: (esquina, esquina, párpado superior, párpado inferior) de cada ojo,
# y el anillo de cada iris (468–477, solo existen en el modelo con iris)
OJOS = [(33, 133, 159, 145), (362, 263, 386, 374)]
IRIS = [(469, 470, 471, 472), (474, 475, 476, 477)]

# Señales candidatas por eje; la calibración se queda con la que mejor separa columnas y filas
RASGOS_H = ["h_iris", "h_bs"]
RASGOS_V = ["v_iris", "v_apertura", "v_bs"]

# Sin calibrar: valores aproximados para alguien a 50–70 cm mirando de frente (imagen en espejo)
CALIB_DEFECTO = {
    "calibrado": False,
    "h": {"rasgo": "h_iris", "medias": [0.42, 0.50, 0.58]},
    "v": {"rasgo": "v_iris", "medias": [-0.03, 0.03]},
    "parpadeo": 0.6,
}

# Colores de laptop/interfaz/interfaz.css (BGR)
FONDO, CASILLA, CURSOR, TENUE, TEXTO = (28, 21, 16), (51, 38, 29), (63, 210, 255), (168, 151, 138), (250, 246, 243)

sys.stdout.reconfigure(encoding="utf-8")     # en Windows, con la salida redirigida, cp1252 rompe las tildes

p = argparse.ArgumentParser()
p.add_argument("--broker", default="localhost")
p.add_argument("--puerto", type=int, default=1883)
p.add_argument("--topic", default="asistivo/vision/mirada")
p.add_argument("--camara", type=int, default=0)
p.add_argument("--sin-mqtt", action="store_true", help="solo vista previa, no publica")
p.add_argument("--suavizado", type=float, default=0.35, help="peso del cuadro nuevo en la media exponencial")
p.add_argument("--estable", type=int, default=4, help="cuadros seguidos en la región nueva antes de cambiar")
p.add_argument("--histeresis", type=float, default=0.25, help="fracción de la distancia entre casillas")
p.add_argument("--rondas", type=int, default=1, help="vueltas por las 6 casillas al calibrar")
args = p.parse_args()


# ---- modelo y cámara ----
def preparar_modelo():
    if not MODELO.exists():
        print(f"[vision] descargando el modelo en {MODELO} ...")
        MODELO.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(URL_MODELO, MODELO)
    opciones = vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(MODELO)),
        running_mode=vision.RunningMode.VIDEO,
        num_faces=1,
        output_face_blendshapes=True,
    )
    return vision.FaceLandmarker.create_from_options(opciones)


def tamano_pantalla():
    try:
        import ctypes
        u = ctypes.windll.user32
        u.SetProcessDPIAware()
        return u.GetSystemMetrics(0), u.GetSystemMetrics(1)
    except Exception:
        return 1280, 720


# ---- rasgos de la mirada ----
def rasgos(lm, bs, ancho, alto):
    P = lambda i: np.array([lm[i].x * ancho, lm[i].y * alto])
    centros = [np.mean([P(i) for i in anillo], axis=0) for anillo in IRIS]
    h, v, ap, puntos = [], [], [], []
    for a, b, sup, inf in OJOS:
        A, B = P(a), P(b)
        if A[0] > B[0]:
            A, B = B, A                                  # A: esquina de la izquierda en la imagen
        u = B - A
        n2 = u @ u
        I = min(centros, key=lambda c: np.linalg.norm(c - (A + B) / 2))
        d = I - A
        h.append((u @ d) / n2)                           # 0 en A, 1 en B
        v.append((u[0] * d[1] - u[1] * d[0]) / n2)       # > 0: iris por debajo de la línea de las esquinas
        ap.append(np.linalg.norm(P(sup) - P(inf)) / np.sqrt(n2))
        puntos.append((A, B, I))
    s = {c.category_name: c.score for c in bs}
    r = {
        "h_iris": float(np.mean(h)),
        "v_iris": float(np.mean(v)),
        "v_apertura": -float(np.mean(ap)),               # mirar abajo cierra un poco el ojo
        "h_bs": (s["eyeLookInLeft"] + s["eyeLookOutRight"] - s["eyeLookOutLeft"] - s["eyeLookInRight"]) / 2,
        "v_bs": (s["eyeLookDownLeft"] + s["eyeLookDownRight"] - s["eyeLookUpLeft"] - s["eyeLookUpRight"]) / 2,
    }
    return r, (s["eyeBlinkLeft"] + s["eyeBlinkRight"]) / 2, puntos


def indice(x, medias, actual, histeresis):
    """Casilla (0..n-1) más cercana a x sobre un eje, con histéresis alrededor de la casilla actual."""
    if medias[0] > medias[-1]:
        x, medias = -x, [-m for m in medias]
    i = 0
    for k in range(len(medias) - 1):
        corte = (medias[k] + medias[k + 1]) / 2
        if actual is not None:
            margen = histeresis * (medias[k + 1] - medias[k]) / 2
            corte += margen if actual <= k else -margen
        if x > corte:
            i = k + 1
    return i


# ---- calibración ----
class Calibracion:
    ORDEN = [1, 2, 3, 6, 5, 4]                           # en serpiente, sin saltos largos
    ESPERA, MUESTREO = 1.0, 1.5                          # s: la vista llega a la casilla y luego se mide

    def __init__(self, rondas):
        self.orden = []
        for n in range(rondas):
            self.orden += self.ORDEN if n % 2 == 0 else self.ORDEN[::-1]
        self.t0 = time.time()
        self.muestras = {r: [] for r in range(1, 7)}

    def paso(self, ahora):
        """(casilla objetivo, midiendo?, avance 0..1 dentro de la casilla); casilla None al terminar."""
        t = ahora - self.t0
        n = int(t // (self.ESPERA + self.MUESTREO))
        if n >= len(self.orden):
            return None, False, 1.0
        dentro = t - n * (self.ESPERA + self.MUESTREO)
        return self.orden[n], dentro >= self.ESPERA, dentro / (self.ESPERA + self.MUESTREO)

    def agregar(self, region, r, parpadeo):
        self.muestras[region].append((r, parpadeo))

    def ajustar(self):
        limpias = {}
        for region, lista in self.muestras.items():
            if len(lista) < 5:
                raise ValueError(f"pocas muestras en la casilla {region}: ¿se perdió la cara?")
            med = np.median([b for _, b in lista])
            limpias[region] = [(r, b) for r, b in lista if b <= med + 0.25]   # descarta parpadeos
        cols = [[r for reg in (c + 1, c + 4) for r, _ in limpias[reg]] for c in range(3)]
        filas = [[r for reg in range(3 * f + 1, 3 * f + 4) for r, _ in limpias[reg]] for f in range(2)]
        h, sep_h = mejor_rasgo(cols, RASGOS_H)
        v, sep_v = mejor_rasgo(filas, RASGOS_V)
        if h is None or v is None:
            raise ValueError("las casillas no quedaron en orden en ninguna señal; repetir con más luz")
        parp = np.percentile([b for lista in limpias.values() for _, b in lista], 95)
        return {
            "calibrado": True,
            "fecha": time.strftime("%Y-%m-%d %H:%M"),
            "h": {"rasgo": h, "medias": medias(cols, h), "separacion": round(sep_h, 2)},
            "v": {"rasgo": v, "medias": medias(filas, v), "separacion": round(sep_v, 2)},
            "parpadeo": float(np.clip(parp + 0.2, 0.45, 0.9)),
        }


def medias(grupos, rasgo):
    return [float(np.median([r[rasgo] for r in g])) for g in grupos]


def mejor_rasgo(grupos, candidatos):
    """Rasgo cuyas medianas por grupo están en orden y más separadas (en desviaciones estándar)."""
    mejor, mejor_sep = None, 0.0
    for rasgo in candidatos:
        m = medias(grupos, rasgo)
        saltos = np.diff(m)
        if not (np.all(saltos > 0) or np.all(saltos < 0)):
            continue
        s = np.sqrt(np.mean([np.var([r[rasgo] for r in g]) for g in grupos])) + 1e-9
        sep = float(np.min(np.abs(saltos)) / s)
        if sep > mejor_sep:
            mejor, mejor_sep = rasgo, sep
    return mejor, mejor_sep


def cargar_calibracion():
    try:
        return json.loads(ARCHIVO_CALIB.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(CALIB_DEFECTO)


# ---- dibujo ----
def casillas(ancho, alto):
    """Rectángulos de las 6 casillas con la misma disposición que la interfaz (barra arriba, ayuda abajo)."""
    arriba, abajo, borde, gap = int(alto * 0.06), int(alto * 0.05), int(alto * 0.015), int(alto * 0.017)
    cw = (ancho - 2 * borde - 2 * gap) / 3
    ch = (alto - arriba - abajo - 2 * borde - gap) / 2
    return {f * 3 + c + 1: (int(borde + c * (cw + gap)), int(arriba + borde + f * (ch + gap)),
                            int(borde + c * (cw + gap) + cw), int(arriba + borde + f * (ch + gap) + ch))
            for f in range(2) for c in range(3)}


def pantalla_calibracion(ancho, alto, objetivo, midiendo, avance, cara):
    img = np.full((alto, ancho, 3), FONDO, np.uint8)
    for reg, (x0, y0, x1, y1) in casillas(ancho, alto).items():
        cv2.rectangle(img, (x0, y0), (x1, y1), CASILLA, -1)
        if reg == objetivo:
            cv2.rectangle(img, (x0, y0), (x1, y1), CURSOR, max(6, alto // 100))
            cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
            radio = int(alto * (0.035 if midiendo else 0.02))
            cv2.circle(img, (cx, cy), radio, CURSOR, -1)
            if midiendo:
                cv2.ellipse(img, (cx, cy), (radio * 2, radio * 2), -90, 0, int(360 * avance), CURSOR, 4)
    msg = "Mira el punto amarillo sin mover la cabeza" if cara else "No se ve la cara: acercate a la camara"
    cv2.putText(img, msg, (int(ancho * 0.02), int(alto * 0.04)), cv2.FONT_HERSHEY_SIMPLEX,
                alto / 1100, TEXTO if cara else (80, 80, 230), 2, cv2.LINE_AA)
    return img


def vista_previa(frame, puntos, r, region, calib, estado):
    for A, B, I in puntos:
        cv2.circle(frame, tuple(A.astype(int)), 2, (0, 255, 0), -1)
        cv2.circle(frame, tuple(B.astype(int)), 2, (0, 255, 0), -1)
        cv2.circle(frame, tuple(I.astype(int)), 3, CURSOR, -1)
    lineas = [estado]
    if r:
        lineas.append(f"{calib['h']['rasgo']}={r[calib['h']['rasgo']]:+.3f}  {calib['v']['rasgo']}={r[calib['v']['rasgo']]:+.3f}")
    if not calib.get("calibrado"):
        lineas.append("SIN CALIBRAR: presiona c")
    for i, t in enumerate(lineas):
        cv2.putText(frame, t, (10, 22 + 22 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(frame, t, (10, 22 + 22 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.55, TEXTO, 1, cv2.LINE_AA)
    # mini menú 2 × 3 abajo a la derecha
    alto, ancho = frame.shape[:2]
    w, h = 40, 28
    for reg in range(1, 7):
        f, c = divmod(reg - 1, 3)
        x0, y0 = ancho - 3 * (w + 4) - 6 + c * (w + 4), alto - 2 * (h + 4) - 6 + f * (h + 4)
        cv2.rectangle(frame, (x0, y0), (x0 + w, y0 + h), CURSOR if reg == region else CASILLA, -1)
        cv2.putText(frame, str(reg), (x0 + 14, y0 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                    FONDO if reg == region else TENUE, 1, cv2.LINE_AA)
    return frame


# ---- MQTT ----
mqtt_estado = {"conectado": False, "republicar": False}
cliente = None
if not args.sin_mqtt:
    def al_conectar(c, datos, flags, rc, props=None):
        print(f"[vision] conectado al broker {args.broker}:{args.puerto} (rc={rc})")
        mqtt_estado.update(conectado=True, republicar=True)

    def al_desconectar(c, datos, flags, rc, props=None):
        mqtt_estado["conectado"] = False

    cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"vision-{os.getpid()}")
    cliente.on_connect = al_conectar
    cliente.on_disconnect = al_desconectar
    cliente.connect_async(args.broker, args.puerto, keepalive=10)
    cliente.loop_start()                                 # reconecta solo


def publicar(region):
    if cliente and mqtt_estado["conectado"]:
        cliente.publish(args.topic, json.dumps({"region": region}), qos=0)


# ---- bucle principal ----
detector = preparar_modelo()
cam = cv2.VideoCapture(args.camara)
if not cam.isOpened():
    raise SystemExit(f"[vision] no se pudo abrir la cámara {args.camara}")
calib = cargar_calibracion()
print(f"[vision] calibración: {'guardada del ' + calib.get('fecha', '?') if calib.get('calibrado') else 'por defecto'}")
pw, ph = tamano_pantalla()

suave = None                     # rasgos suavizados
fila = col = None                # casilla aceptada sobre cada eje
region = None                    # región publicada
candidata, cuenta = None, 0
ultima_cara = 0.0
pausa = False
calibrando = None
t_prev, fps = time.time(), 0.0
ts_prev = -1

while True:
    ok, frame = cam.read()
    if not ok:
        print("[vision] la cámara no entrega imagen")
        break
    frame = cv2.flip(frame, 1)                            # espejo: mirar a la derecha mueve el iris a la derecha
    alto, ancho = frame.shape[:2]
    ahora = time.time()
    ts = max(ts_prev + 1, int(time.monotonic() * 1000))   # FaceLandmarker exige marcas crecientes
    ts_prev = ts
    res = detector.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB,
                                             data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)), ts)
    r, puntos, parpadeo = None, [], 0.0
    if res.face_landmarks:
        r, parpadeo, puntos = rasgos(res.face_landmarks[0], res.face_blendshapes[0], ancho, alto)
        ultima_cara = ahora

    # --- calibración en curso ---
    if calibrando:
        objetivo, midiendo, avance = calibrando.paso(ahora)
        if objetivo is None:
            cv2.destroyWindow("calibracion")
            try:
                calib = calibrando.ajustar()
                ARCHIVO_CALIB.write_text(json.dumps(calib, indent=2), encoding="utf-8")
                print(f"[vision] calibrado: columnas con {calib['h']['rasgo']} (separación {calib['h']['separacion']}), "
                      f"filas con {calib['v']['rasgo']} (separación {calib['v']['separacion']})")
                if min(calib["h"]["separacion"], calib["v"]["separacion"]) < 1.5:
                    print("[vision] separación baja (< 1,5): la selección puede fallar; mejorar la luz o acercarse")
            except ValueError as e:
                print(f"[vision] calibración fallida: {e}")
            calibrando, suave, fila, col = None, None, None, None
        else:
            if midiendo and r:
                calibrando.agregar(objetivo, r, parpadeo)
            cv2.imshow("calibracion", pantalla_calibracion(pw, ph, objetivo, midiendo, avance, r is not None))

    # --- región de la mirada ---
    elif r and parpadeo < calib["parpadeo"]:              # en un parpadeo se mantiene el valor anterior
        a = args.suavizado
        suave = r if suave is None else {k: a * r[k] + (1 - a) * suave[k] for k in r}
        col = indice(suave[calib["h"]["rasgo"]], calib["h"]["medias"], col, args.histeresis)
        fila = indice(suave[calib["v"]["rasgo"]], calib["v"]["medias"], fila, args.histeresis)
        nueva = fila * 3 + col + 1
        if nueva == region:
            candidata, cuenta = None, 0
        elif nueva == candidata:
            cuenta += 1
        else:
            candidata, cuenta = nueva, 1
        if candidata is not None and cuenta >= args.estable:
            region, candidata, cuenta = candidata, None, 0
            print(f"[vision] región {region}")
            if not pausa:
                publicar(region)
    elif not r and region is not None and ahora - ultima_cara > 0.5:
        region, suave, fila, col = None, None, None, None
        print("[vision] sin cara")
        if not pausa:
            publicar(None)

    if mqtt_estado["republicar"]:                          # tras (re)conectar, la interfaz recibe la región actual
        mqtt_estado["republicar"] = False
        if not pausa:
            publicar(region)

    fps = 0.9 * fps + 0.1 / max(ahora - t_prev, 1e-3)
    t_prev = ahora
    red = "sin MQTT" if cliente is None else ("MQTT ok" if mqtt_estado["conectado"] else "MQTT desconectado")
    estado = f"region {region or '-'} | {fps:4.1f} fps | {red}" + (" | PAUSA" if pausa else "")
    cv2.imshow("vision", vista_previa(frame, puntos, r, region, calib, estado))

    tecla = cv2.waitKey(1) & 0xFF
    if tecla in (ord("q"), 27):
        break
    elif tecla == ord("c") and not calibrando:
        calibrando = Calibracion(args.rondas)
        cv2.namedWindow("calibracion", cv2.WINDOW_NORMAL)
        cv2.setWindowProperty("calibracion", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        print("[vision] calibrando: mirar cada casilla cuando se ilumine")
    elif tecla == ord("r"):
        calib, suave, fila, col = dict(CALIB_DEFECTO), None, None, None
        ARCHIVO_CALIB.unlink(missing_ok=True)
        print("[vision] calibración por defecto")
    elif tecla == ord("p"):
        pausa = not pausa
        print(f"[vision] publicación {'en pausa' if pausa else 'reanudada'}")

if not pausa:
    publicar(None)
if cliente:
    time.sleep(0.2)
    cliente.loop_stop()
cam.release()
cv2.destroyAllWindows()
