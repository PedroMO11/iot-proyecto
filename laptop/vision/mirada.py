# Módulo de visión: webcam + MediaPipe Face Landmarker → punto de la pantalla que mira el usuario
# y casilla del menú 2 × 3 bajo ese punto.
# Publica:
#   asistivo/vision/punto   {"x": 0..1, "y": 0..1} | {"x": null}, ~20 veces por segundo (para dibujar el cursor)
#   asistivo/vision/mirada  {"region": 1..6 | null} cuando la casilla cambia y se mantiene
#   asistivo/vision/estado  {"fps", "cara", "calibrado", "region"} cada 2 s
# x e y son relativas a la zona del menú: (0, 0) arriba a la izquierda, (1, 1) abajo a la derecha.
#
# Recentrado (tecla O de la interfaz): mirar 1 s un punto en el centro corrige el desvío acumulado
# (por ejemplo, si la persona se movió) sin repetir la calibración.
#
# Calibración: la interfaz (tecla C) o esta ventana (tecla c) la inician. La interfaz marca las
# 6 casillas una por una (topic vision/calibracion) y aquí se guardan los rasgos de los ojos al
# mirar cada una. Con esas muestras se ajusta una regresión lineal (ridge) rasgos → (x, y).
# Se guarda en calibracion.json (con las muestras) y se reutiliza al volver a abrir el programa.
#
# Uso:  uv run laptop/vision/mirada.py [--broker localhost] [--puerto 1883] [--camara 0] [--sin-ventana]
# Teclas en la ventana: c = calibrar · q = salir
import argparse
import json
import pathlib
import time
from collections import Counter, deque

import cv2
import mediapipe as mp
import numpy as np
import paho.mqtt.client as mqtt
from mediapipe.tasks.python import BaseOptions, vision

AQUI = pathlib.Path(__file__).resolve().parent
TOPIC = "asistivo/vision"
MODELO_URL = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/"
              "face_landmarker/float16/1/face_landmarker.task")

ESPERA_S = 1.0          # al pasar a una casilla nueva, tiempo para que la mirada llegue
MUESTRA_S = 1.5         # tiempo de muestreo por casilla
SUAVIZADO = 0.25        # filtro exponencial del punto (0..1: más bajo = más suave y más lento)
PUNTO_HZ = 20           # publicaciones del punto por segundo
VOTOS = 8               # cuadros para el voto por mayoría de la casilla
ESTABLE_S = 0.3         # la casilla debe mantenerse este tiempo antes de publicarla
PARPADEO = 0.5          # eyeBlink por encima de esto: el cuadro se descarta
RIDGE = 1.0             # regularización de la regresión
# Rasgos que usa la regresión: solo los ojos (iris y blendshapes). Con la cabeza, el modelo se apoyaba
# sobre todo en ella: un giro mínimo movía el cursor un 11 % de la pantalla, y con muestras no vistas
# acertaba 129/144 casillas frente a 143/144 solo con los ojos (calibración del 2026-10-30).
USADOS = [0, 1, 2, 3]
CENTRAR_ESPERA_S, CENTRAR_S = 0.6, 1.2   # recentrado: mirar el centro del menú

# Centro de cada casilla en coordenadas del menú (3 columnas × 2 filas)
CENTROS = {r: (((r - 1) % 3 + 0.5) / 3, ((r - 1) // 3 + 0.5) / 2) for r in range(1, 7)}

# Índices de la malla de 478 puntos (con iris)
OJO_DER = {"esquinas": (33, 133), "parpados": (159, 145), "iris": 468}
OJO_IZQ = {"esquinas": (362, 263), "parpados": (386, 374), "iris": 473}
NARIZ, MEJILLAS, FRENTE_MENTON = 1, (234, 454), (10, 152)


def rasgos(lm, bs):
    """Vector de 6 rasgos: posición del iris (h, v), blendshapes de mirada (h, v) y cabeza (h, v)."""
    def ojo(o):
        a, b = lm[o["esquinas"][0]], lm[o["esquinas"][1]]
        arr, abj = lm[o["parpados"][0]], lm[o["parpados"][1]]
        i = lm[o["iris"]]
        h = (i.x - min(a.x, b.x)) / max(1e-6, abs(b.x - a.x))
        v = (i.y - arr.y) / max(1e-6, abj.y - arr.y)
        return h, v
    hd, vd = ojo(OJO_DER)
    hi, vi = ojo(OJO_IZQ)
    bh = (bs["eyeLookOutLeft"] + bs["eyeLookInRight"] - bs["eyeLookInLeft"] - bs["eyeLookOutRight"]) / 2
    bv = (bs["eyeLookUpLeft"] + bs["eyeLookUpRight"] - bs["eyeLookDownLeft"] - bs["eyeLookDownRight"]) / 2
    m1, m2 = lm[MEJILLAS[0]], lm[MEJILLAS[1]]
    f, c = lm[FRENTE_MENTON[0]], lm[FRENTE_MENTON[1]]
    nx = (lm[NARIZ].x - m1.x) / max(1e-6, m2.x - m1.x)
    ny = (lm[NARIZ].y - f.y) / max(1e-6, c.y - f.y)
    return np.array([(hd + hi) / 2, (vd + vi) / 2, bh, bv, nx, ny])


class Calibracion:
    """Regresión ridge de rasgos normalizados → punto (x, y) de la zona del menú."""

    def __init__(self, archivo):
        self.archivo = archivo
        self.media = self.escala = self.W = None
        self.desvio = np.zeros(2)               # corrección del recentrado
        self.muestras = None
        if archivo.exists():
            d = json.loads(archivo.read_text())
            if "muestras" in d:                 # las calibraciones viejas no guardaban muestras
                self.ajustar({int(k): v for k, v in d["muestras"].items()})
                self.desvio = np.array(d.get("desvio", [0.0, 0.0]))

    def ajustar(self, muestras):                # {region: [vectores]}
        self.muestras = muestras
        X = np.vstack([np.array(v)[:, USADOS] for v in muestras.values()])
        Y = np.vstack([np.tile(CENTROS[r], (len(v), 1)) for r, v in muestras.items()])
        self.media, self.escala = X.mean(axis=0), np.maximum(X.std(axis=0), 1e-6)
        Z = np.hstack([(X - self.media) / self.escala, np.ones((len(X), 1))])
        reg = RIDGE * np.eye(Z.shape[1]); reg[-1, -1] = 0     # no se regulariza el término independiente
        self.W = np.linalg.solve(Z.T @ Z + reg, Z.T @ Y)
        error = np.abs(Z @ self.W - Y).mean(axis=0)
        return error

    def entrenar(self, muestras):
        error = self.ajustar(muestras)
        self.desvio = np.zeros(2)
        self.guardar()
        return error

    def guardar(self):
        self.archivo.write_text(json.dumps({
            "muestras": {str(r): np.array(v).tolist() for r, v in self.muestras.items()},
            "desvio": self.desvio.tolist(), "fecha": time.strftime("%Y-%m-%d %H:%M")}))

    def recentrar(self, puntos_crudos):         # puntos sin corrección mientras se mira el centro (0,5; 0,5)
        self.desvio = np.array([0.5, 0.5]) - np.median(np.array(puntos_crudos), axis=0)
        self.guardar()
        return self.desvio

    @property
    def lista(self):
        return self.W is not None

    def crudo(self, x):
        return np.append((x[USADOS] - self.media) / self.escala, 1.0) @ self.W

    def punto(self, x):
        return np.clip(self.crudo(x) + self.desvio, -0.05, 1.05)


def region_de(p):
    col = min(2, max(0, int(p[0] * 3)))
    fila = min(1, max(0, int(p[1] * 2)))
    return fila * 3 + col + 1


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--broker", default="localhost")
    p.add_argument("--puerto", type=int, default=1883)
    p.add_argument("--camara", type=int, default=0)
    p.add_argument("--sin-ventana", action="store_true")
    args = p.parse_args()

    modelo = AQUI / "face_landmarker.task"
    if not modelo.exists():                     # ~3,7 MB, una sola vez (no se sube al repositorio)
        import urllib.request
        print("[visión] descargando el modelo de MediaPipe...")
        urllib.request.urlretrieve(MODELO_URL, modelo)

    cal_ojos = Calibracion(AQUI / "calibracion.json")
    estado = {"calibrar": False, "centrar": False}

    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="vision")
    c.on_connect = lambda cl, *a: cl.subscribe(f"{TOPIC}/cmd", qos=1)

    def al_recibir(cl, datos, msg):
        try:
            accion = json.loads(msg.payload).get("accion")
            if accion == "calibrar":
                estado["calibrar"] = True
            elif accion == "centrar":
                estado["centrar"] = True
        except (json.JSONDecodeError, AttributeError):
            pass
    c.on_message = al_recibir
    c.connect(args.broker, args.puerto)
    c.loop_start()

    opciones = vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(modelo)),
        running_mode=vision.RunningMode.VIDEO, num_faces=1, output_face_blendshapes=True)
    detector = vision.FaceLandmarker.create_from_options(opciones)
    cam = cv2.VideoCapture(args.camara)

    votos = deque(maxlen=VOTOS)
    candidata, desde, publicada = None, 0.0, "inicial"
    suave, t_punto = None, 0.0                  # punto suavizado y última publicación
    cal = None                                  # {"paso", "inicio", "muestras"} durante la calibración
    centrado = None                             # {"inicio", "puntos"} durante el recentrado
    t_fps, n_fps, fps, t_estado = time.time(), 0, 0.0, 0.0
    print("[visión] listo. c = calibrar · q = salir" + ("" if cal_ojos.lista else " · SIN CALIBRAR"))

    while True:
        ok, cuadro = cam.read()
        if not ok:
            print("[visión] no se pudo leer la cámara"); break
        cuadro = cv2.flip(cuadro, 1)             # espejo: la izquierda de la imagen es la del usuario
        ahora = time.time()
        img = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(cuadro, cv2.COLOR_BGR2RGB))
        r = detector.detect_for_video(img, int(ahora * 1000))
        cara = bool(r.face_landmarks)
        x = None
        if cara:
            bs = {b.category_name: b.score for b in r.face_blendshapes[0]}
            if max(bs["eyeBlinkLeft"], bs["eyeBlinkRight"]) < PARPADEO:
                x = rasgos(r.face_landmarks[0], bs)

        # ---- calibración: una casilla tras otra ----
        if estado["calibrar"] and cal is None:
            estado["calibrar"] = False
            cal = {"paso": 1, "inicio": ahora, "muestras": {}}
            c.publish(f"{TOPIC}/calibracion", json.dumps({"estado": "mirar", "region": 1, "total": 6}), qos=1)
            c.publish(f"{TOPIC}/punto", json.dumps({"x": None}))
            print("[visión] calibrando: mire la casilla 1")
        if cal is not None:
            transcurrido = ahora - cal["inicio"]
            if transcurrido > ESPERA_S and x is not None:
                cal["muestras"].setdefault(cal["paso"], []).append(x)
            if transcurrido > ESPERA_S + MUESTRA_S:
                cal["paso"] += 1
                cal["inicio"] = ahora
                if cal["paso"] > 6:
                    faltan = [k for k in range(1, 7) if len(cal["muestras"].get(k, [])) < 5]
                    if faltan:
                        c.publish(f"{TOPIC}/calibracion", json.dumps({"estado": "error", "faltan": faltan}), qos=1)
                        print(f"[visión] calibración fallida: sin datos de {faltan} (¿cara fuera de cámara?)")
                    else:
                        error = cal_ojos.entrenar(cal["muestras"])
                        c.publish(f"{TOPIC}/calibracion", json.dumps({"estado": "listo"}), qos=1)
                        print(f"[visión] calibración lista · error medio en la calibración: "
                              f"{error[0] * 100:.0f} % del ancho, {error[1] * 100:.0f} % del alto")
                    cal, publicada, suave = None, "inicial", None
                    votos.clear()
                else:
                    c.publish(f"{TOPIC}/calibracion",
                              json.dumps({"estado": "mirar", "region": cal["paso"], "total": 6}), qos=1)

        # ---- recentrado: mirar el centro del menú ----
        if estado["centrar"] and cal is None and centrado is None and cal_ojos.lista:
            estado["centrar"] = False
            centrado = {"inicio": ahora, "puntos": []}
            c.publish(f"{TOPIC}/calibracion", json.dumps({"estado": "centrar"}), qos=1)
        if centrado is not None:
            if ahora - centrado["inicio"] > CENTRAR_ESPERA_S and x is not None:
                centrado["puntos"].append(cal_ojos.crudo(x))
            if ahora - centrado["inicio"] > CENTRAR_ESPERA_S + CENTRAR_S:
                if len(centrado["puntos"]) >= 5:
                    dv = cal_ojos.recentrar(centrado["puntos"])
                    c.publish(f"{TOPIC}/calibracion", json.dumps({"estado": "centrado"}), qos=1)
                    print(f"[visión] recentrado: corrección ({dv[0]:+.2f}, {dv[1]:+.2f})")
                else:
                    c.publish(f"{TOPIC}/calibracion", json.dumps({"estado": "error", "faltan": ["centro"]}), qos=1)
                centrado, suave = None, None

        # ---- punto suavizado y casilla con voto por mayoría y tiempo mínimo ----
        reg = None
        if cal is None and centrado is None and cal_ojos.lista:
            if x is not None:
                bruto = cal_ojos.punto(x)
                suave = bruto if suave is None else SUAVIZADO * bruto + (1 - SUAVIZADO) * suave
                votos.append(region_de(suave))
            elif not cara:
                suave = None
                votos.append(None)
            if ahora - t_punto >= 1 / PUNTO_HZ:
                t_punto = ahora
                c.publish(f"{TOPIC}/punto", json.dumps(
                    {"x": round(float(suave[0]), 3), "y": round(float(suave[1]), 3)} if suave is not None else {"x": None}))
            if votos:
                reg, n = Counter(votos).most_common(1)[0]
                if n < len(votos) // 2 + 1:
                    reg = candidata                  # sin mayoría clara: no cambiar
            if reg != candidata:
                candidata, desde = reg, ahora
            elif ahora - desde >= ESTABLE_S and reg != publicada:
                c.publish(f"{TOPIC}/mirada", json.dumps({"region": reg}))
                publicada = reg

        # ---- estado cada 2 s ----
        n_fps += 1
        if ahora - t_fps >= 1:
            fps, n_fps, t_fps = n_fps / (ahora - t_fps), 0, ahora
        if ahora - t_estado >= 2:
            t_estado = ahora
            c.publish(f"{TOPIC}/estado", json.dumps({
                "fps": round(fps, 1), "cara": cara, "calibrado": cal_ojos.lista,
                "region": publicada if publicada != "inicial" else None}))

        if not args.sin_ventana:
            texto = (f"calibrando: casilla {cal['paso']}" if cal else
                     f"casilla {publicada if publicada not in (None, 'inicial') else '-'}"
                     + ("" if cal_ojos.lista else "  (SIN CALIBRAR: tecla c)"))
            cv2.putText(cuadro, f"{texto}   {fps:.0f} fps", (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                        (80, 220, 80) if cara else (60, 60, 230), 2)
            if cara:
                h, w = cuadro.shape[:2]
                for i in (468, 473):
                    pt = r.face_landmarks[0][i]
                    cv2.circle(cuadro, (int(pt.x * w), int(pt.y * h)), 3, (80, 220, 80), -1)
            cv2.imshow("Vision - mirada", cuadro)
            tecla = cv2.waitKey(1) & 0xFF
            if tecla == ord("q"):
                break
            if tecla == ord("c"):
                estado["calibrar"] = True

    c.publish(f"{TOPIC}/estado", json.dumps({"fps": 0, "cara": False, "calibrado": cal_ojos.lista,
                                             "region": None, "activo": False}))
    c.publish(f"{TOPIC}/mirada", json.dumps({"region": None}))
    c.publish(f"{TOPIC}/punto", json.dumps({"x": None}))
    time.sleep(0.3)
    c.loop_stop()
    cam.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
