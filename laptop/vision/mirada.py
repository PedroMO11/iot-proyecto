# Módulo de visión: webcam + MediaPipe Face Landmarker → punto de la pantalla que mira el usuario
# y casilla del menú 2 × 3 bajo ese punto. Rasgos y modelo en modelo.py.
#
# Publica:
#   asistivo/vision/punto        {"x": 0..1, "y": 0..1} | {"x": null}, ~20 veces por segundo
#   asistivo/vision/mirada       {"region": 1..6 | null} cuando la casilla cambia y se mantiene
#   asistivo/vision/estado       {"fps", "cara", "calibrado", "region", "calidad"} cada 2 s
#   asistivo/vision/calibracion  pasos de la calibración, la validación y el recentrado
# Escucha asistivo/vision/cmd: {"accion": "calibrar"}, {"accion": "validar"} o {"accion": "centrar"}.
#
# Calibración (tecla C de la interfaz): 10 puntos (rejilla de 3 × 3 con el centro al inicio y al final),
# luego validación en los 6 centros de casilla. El modelo (qué rasgos y cuánta regularización) se
# elige solo, con validación cruzada dejando fuera un punto entero. Recentrado (tecla O): 1 punto.
#
# Uso:  .venv/bin/python laptop/vision/mirada.py [--broker localhost] [--camara 0] [--sin-ventana]
# Teclas en la ventana: c = calibrar · o = recentrar · q = salir
import argparse
import json
import pathlib
import time

import cv2
import mediapipe as mp
import numpy as np
import paho.mqtt.client as mqtt
from mediapipe.tasks.python import BaseOptions, vision

import modelo as M

AQUI = pathlib.Path(__file__).resolve().parent
TOPIC = "asistivo/vision"
ARCHIVO = AQUI / "calibracion.json"
MODELO_URL = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/"
              "face_landmarker/float16/1/face_landmarker.task")

# Tiempos de cada punto: espera (la mirada llega y se asienta) y captura
CAL_ESPERA, CAL_CAPTURA = 1.0, 1.4
VAL_ESPERA, VAL_CAPTURA = 0.8, 1.0
CEN_ESPERA, CEN_CAPTURA = 0.6, 1.2
MIN_MUESTRAS = 15

PARPADEO = 0.45         # eyeBlink por encima: cuadro descartado
GIRO_MAX = 35           # grados: más allá, la cara está demasiado de lado
PUNTO_HZ = 20
MARGEN = 0.04           # histéresis: para cambiar de casilla, el punto debe entrar 4 % en la nueva
ESTABLE_S = 0.25        # y quedarse ahí este tiempo


class Secuencia:
    """Recorre una lista de puntos: muestra cada uno, espera, captura rasgos y avisa por MQTT."""

    def __init__(self, fase, puntos, espera, captura, publicar):
        self.fase, self.puntos, self.espera, self.captura = fase, puntos, espera, captura
        self.publicar = publicar
        self.k, self.inicio = 0, None
        self.muestras = [[] for _ in puntos]

    def paso(self, ahora, x):
        """Devuelve True cuando terminó todos los puntos."""
        if self.inicio is None:
            self.inicio = ahora
            self._avisar()
        t = ahora - self.inicio
        if t > self.espera and x is not None:
            self.muestras[self.k].append(x)
        if t > self.espera + self.captura:
            self.k += 1
            self.inicio = ahora
            if self.k == len(self.puntos):
                return True
            self._avisar()
        return False

    def _avisar(self):
        x, y = self.puntos[self.k]
        self.publicar({"estado": "mirar", "fase": self.fase, "x": round(x, 3), "y": round(y, 3),
                       "paso": self.k + 1, "total": len(self.puntos), "espera": self.espera,
                       "duracion": self.espera + self.captura})

    def objetivos(self):
        return [(p, M.limpiar(m)) for p, m in zip(self.puntos, self.muestras)]


class Calibracion:
    """Modelo vigente + datos de la calibración, guardados en calibracion.json."""

    def __init__(self):
        self.modelo, self.desvio, self.calidad, self.objetivos = None, np.zeros(2), None, None
        if ARCHIVO.exists():
            d = json.loads(ARCHIVO.read_text())
            if d.get("version") == 2:
                self.objetivos = [(tuple(o["punto"]), np.array(o["muestras"])) for o in d["objetivos"]]
                X, Y, _ = M.apilar(self.objetivos)
                self.modelo = M.Modelo(**d["modelo"]).ajustar(X, Y)
                self.desvio = np.array(d.get("desvio", [0, 0]))
                self.calidad = d.get("calidad")

    @property
    def lista(self):
        return self.modelo is not None

    def crudo(self, x):
        return self.modelo.predecir(x)[0]

    def punto(self, x):
        return np.clip(self.crudo(x) + self.desvio, -0.05, 1.05)

    def puntos(self, X):                        # varias muestras a la vez → (n, 2)
        return np.clip(self.modelo.predecir(X) + self.desvio, -0.05, 1.05)

    def guardar(self, tabla=None):
        ARCHIVO.write_text(json.dumps({
            "version": 2, "fecha": time.strftime("%Y-%m-%d %H:%M"), "rasgos": M.NOMBRES,
            "modelo": self.modelo.guardar(), "desvio": self.desvio.tolist(), "calidad": self.calidad,
            "objetivos": [{"punto": list(p), "muestras": np.asarray(m).tolist()} for p, m in self.objetivos],
            "tabla": [{"modelo": m.nombre, "error_x": float(e[0]), "error_y": float(e[1])} for _, m, e in (tabla or [])],
        }))


def ajustar_camara(i):
    """En Linux: filtro antiparpadeo de 60 Hz (red de Perú; de fábrica viene en 50 Hz y con luces de
    60 Hz salen bandas) y sin bajar los fps con poca luz (si no, cae a 10 fps). Se restablece al
    desconectar la cámara."""
    import shutil
    import subprocess
    if shutil.which("v4l2-ctl"):
        subprocess.run(["v4l2-ctl", "-d", f"/dev/video{i}", "--set-ctrl=power_line_frequency=2",
                        "--set-ctrl=exposure_dynamic_framerate=0"], capture_output=True)


def abrir_camara(i):
    ajustar_camara(i)
    cam = cv2.VideoCapture(i, cv2.CAP_V4L2)
    cam.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))   # 1280 × 720 a 30 fps solo en MJPG
    cam.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cam.set(cv2.CAP_PROP_FPS, 30)
    if not cam.isOpened():
        cam = cv2.VideoCapture(i)
    return cam


def dibujar(cuadro, r, cal, p, region, texto, fps):
    """Ventana de diagnóstico: cámara con ojos marcados, ojos ampliados y minimapa del menú."""
    h, w = cuadro.shape[:2]
    lienzo = cuadro.copy()
    zoom = []
    if r.face_landmarks:
        lm = r.face_landmarks[0]
        for o in M.OJOS.values():
            pts = np.array([[lm[i].x * w, lm[i].y * h] for i in (o["ext"], o["int"], o["arriba"], o["abajo"])])
            iris = np.mean([[lm[i].x * w, lm[i].y * h] for i in o["iris"]], axis=0)
            for q in pts:
                cv2.circle(lienzo, tuple(int(c) for c in q), 2, (255, 200, 80), -1)
            cv2.circle(lienzo, tuple(int(c) for c in iris), 3, (80, 230, 80), -1)
            x0, y0 = pts.min(axis=0) - 12
            x1, y1 = pts.max(axis=0) + 12
            ojo = cuadro[max(0, int(y0)):int(y1), max(0, int(x0)):int(x1)]
            if ojo.size:
                zoom.append(cv2.resize(ojo, (240, int(240 * ojo.shape[0] / max(1, ojo.shape[1])))))
    # minimapa del menú (3 × 2) con el punto
    mapa = np.full((180, 300, 3), 24, np.uint8)
    for c in range(1, 7):
        col, fila = (c - 1) % 3, (c - 1) // 3
        color = (60, 180, 240) if c == region else (70, 70, 70)
        cv2.rectangle(mapa, (col * 100 + 3, fila * 90 + 3), (col * 100 + 97, fila * 90 + 87), color, 2 if c == region else 1)
        cv2.putText(mapa, str(c), (col * 100 + 8, fila * 90 + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    if p is not None:
        cv2.circle(mapa, (int(np.clip(p[0], 0, 1) * 300), int(np.clip(p[1], 0, 1) * 180)), 9, (80, 230, 80), 2)
    # componer: cámara reducida a la izquierda, ojos y minimapa a la derecha
    cam = cv2.resize(lienzo, (640, int(640 * h / w)))
    lado = np.full((cam.shape[0], 300, 3), 16, np.uint8)
    y = 6
    for z in zoom:
        z = z[:, :min(z.shape[1], 288)]
        if y + z.shape[0] < lado.shape[0] - 190:
            lado[y:y + z.shape[0], 6:6 + z.shape[1]] = z
            y += z.shape[0] + 6
    lado[-184:-4, :300] = mapa
    img = np.hstack([cam, lado])
    cv2.putText(img, f"{texto}   {fps:.0f} fps", (10, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (230, 230, 230), 2)
    brillo = cuadro.mean()
    if brillo < 60:
        cv2.putText(img, f"POCA LUZ ({brillo:.0f}/255): ilumine la cara de frente", (10, img.shape[0] - 200),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (60, 60, 240), 2)
    if cal.calidad:
        cv2.putText(img, f"validacion: {cal.calidad['acierto']:.0f} % casillas, error {cal.calidad['error']:.1f} %",
                    (10, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)
    return img


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--broker", default="localhost")
    a.add_argument("--camara", type=int, default=0)
    a.add_argument("--sin-ventana", action="store_true")
    args = a.parse_args()

    modelo_mp = AQUI / "face_landmarker.task"
    if not modelo_mp.exists():                  # ~3,7 MB, una sola vez (no se sube al repositorio)
        import urllib.request
        print("[visión] descargando el modelo de MediaPipe...")
        urllib.request.urlretrieve(MODELO_URL, modelo_mp)

    cal = Calibracion()
    pedido = {"accion": None}

    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="vision")
    c.on_connect = lambda cl, *x: cl.subscribe(f"{TOPIC}/cmd", qos=1)

    def al_recibir(cl, datos, msg):
        try:
            pedido["accion"] = json.loads(msg.payload).get("accion")
        except (json.JSONDecodeError, AttributeError):
            pass
    c.on_message = al_recibir
    c.connect(args.broker, 1883)
    c.loop_start()
    avisar = lambda d: c.publish(f"{TOPIC}/calibracion", json.dumps(d), qos=1)

    detector = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(modelo_mp)), running_mode=vision.RunningMode.VIDEO,
        num_faces=1, output_face_blendshapes=True, output_facial_transformation_matrixes=True))
    cam = abrir_camara(args.camara)
    w, h = int(cam.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cam.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"[visión] cámara {w}×{h}" + ("" if cal.lista else " · SIN CALIBRAR (tecla C en la interfaz)"))

    filtro = M.UnoEuro()
    secuencia = None                            # Secuencia en curso (calibración, validación o centro)
    region, candidata, desde = None, None, 0.0
    p_suave, t_punto, t_estado = None, 0.0, 0.0
    t_fps, n_fps, fps = time.time(), 0, 0.0
    t_prev = 0

    while True:
        ok, cuadro = cam.read()
        if not ok:
            print("[visión] no se pudo leer la cámara"); break
        cuadro = cv2.flip(cuadro, 1)             # espejo: la izquierda de la imagen es la del usuario
        ahora = time.time()
        t_ms = max(t_prev + 1, int(ahora * 1000)); t_prev = t_ms
        r = detector.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB,
                                               data=cv2.cvtColor(cuadro, cv2.COLOR_BGR2RGB)), t_ms)
        cara = bool(r.face_landmarks)
        x = None
        if cara:
            bs = {b.category_name: b.score for b in r.face_blendshapes[0]}
            v = M.rasgos(r.face_landmarks[0], bs, r.facial_transformation_matrixes[0], w, h)
            if max(bs["eyeBlinkLeft"], bs["eyeBlinkRight"]) < PARPADEO and abs(v[M.I["giro"]]) < GIRO_MAX:
                x = v

        # ---- pedidos de la interfaz o de la ventana ----
        if pedido["accion"] and secuencia is None:
            if pedido["accion"] == "calibrar":
                secuencia = Secuencia("calibracion", M.CALIBRACION, CAL_ESPERA, CAL_CAPTURA, avisar)
                print("[visión] calibrando (10 puntos)")
            elif pedido["accion"] == "validar" and cal.lista:
                secuencia = Secuencia("validacion", M.VALIDACION, VAL_ESPERA, VAL_CAPTURA, avisar)
            elif pedido["accion"] == "centrar" and cal.lista:
                secuencia = Secuencia("centro", [(0.5, 0.5)], CEN_ESPERA, CEN_CAPTURA, avisar)
            c.publish(f"{TOPIC}/punto", json.dumps({"x": None}))
        pedido["accion"] = None

        # ---- secuencias ----
        if secuencia is not None and secuencia.paso(ahora, x):
            terminada, secuencia = secuencia, None
            objetivos = terminada.objetivos()
            pocos = [i + 1 for i, (_, m) in enumerate(objetivos) if len(m) < MIN_MUESTRAS]
            if pocos:
                avisar({"estado": "error", "fase": terminada.fase, "faltan": pocos})
                print(f"[visión] {terminada.fase}: pocos datos en los puntos {pocos} (¿cara fuera de cámara o parpadeos?)")
            elif terminada.fase == "calibracion":
                cal.modelo, tabla = M.elegir_modelo(objetivos)
                cal.objetivos, cal.desvio, cal.calidad = objetivos, np.zeros(2), None   # la precisión se mide de nuevo
                deriva = np.median(objetivos[-1][1], axis=0) - np.median(objetivos[0][1], axis=0)
                print(f"[visión] modelo elegido: {cal.modelo.nombre} · error en validación cruzada: "
                      f"x {tabla[0][2][0] * 100:.1f} %, y {tabla[0][2][1] * 100:.1f} %")
                print(f"[visión] deriva del centro (inicio → fin), giro {deriva[M.I['giro']]:+.1f}°, "
                      f"iris {deriva[M.I['iris_x_D']]:+.3f}")
                cal.guardar(tabla)
                secuencia = Secuencia("validacion", M.VALIDACION, VAL_ESPERA, VAL_CAPTURA, avisar)
            elif terminada.fase == "validacion":
                pred = [(p, cal.puntos(m)) for p, m in objetivos]
                err = np.mean([np.abs(pp - p).mean(axis=0) for p, pp in pred], axis=0) * 100
                acierto = 100 * np.mean([M.casilla(q) == M.casilla(p) for p, pp in pred for q in pp])
                cal.calidad = {"acierto": float(acierto), "error": float(err.mean()),
                               "error_x": float(err[0]), "error_y": float(err[1])}
                cal.guardar()
                avisar({"estado": "listo", **{k: round(v, 1) for k, v in cal.calidad.items()}})
                print(f"[visión] validación: {acierto:.0f} % de casillas acertadas · error x {err[0]:.1f} %, y {err[1]:.1f} %")
            elif terminada.fase == "centro":
                cal.desvio = np.array([0.5, 0.5]) - np.median(cal.modelo.predecir(objetivos[0][1]), axis=0)
                cal.guardar()
                avisar({"estado": "centrado", "desvio": [round(float(d), 3) for d in cal.desvio]})
                print(f"[visión] recentrado: corrección ({cal.desvio[0]:+.3f}, {cal.desvio[1]:+.3f})")
            filtro.reiniciar(); region = candidata = None

        # ---- punto filtrado y casilla con histéresis ----
        p = None
        if secuencia is None and cal.lista:
            if x is not None:
                p = filtro(cal.punto(x), ahora)
                nueva = M.casilla(p)
                if nueva != region and (region is None or M.dentro_con_margen(p, nueva, MARGEN)):
                    if nueva != candidata:
                        candidata, desde = nueva, ahora
                    elif ahora - desde >= ESTABLE_S:
                        region = nueva
                        c.publish(f"{TOPIC}/mirada", json.dumps({"region": region}))
                else:
                    candidata = None
            elif not cara:
                filtro.reiniciar()
            p_suave = p
            if ahora - t_punto >= 1 / PUNTO_HZ:
                t_punto = ahora
                c.publish(f"{TOPIC}/punto", json.dumps(
                    {"x": round(float(p[0]), 3), "y": round(float(p[1]), 3)} if p is not None else {"x": None}))

        # ---- estado cada 2 s ----
        n_fps += 1
        if ahora - t_fps >= 1:
            fps, n_fps, t_fps = n_fps / (ahora - t_fps), 0, ahora
        if ahora - t_estado >= 2:
            t_estado = ahora
            c.publish(f"{TOPIC}/estado", json.dumps({"fps": round(fps, 1), "cara": cara, "calibrado": cal.lista,
                                                      "region": region, "calidad": cal.calidad,
                                                      "brillo": round(float(cuadro.mean()))}))

        if not args.sin_ventana:
            if secuencia is not None:
                texto = f"{secuencia.fase}: punto {secuencia.k + 1}/{len(secuencia.puntos)}"
            elif not cal.lista:
                texto = "SIN CALIBRAR: tecla C en la interfaz (o c aqui)"
            else:
                texto = f"casilla {region or '-'}" + ("" if cara else "   SIN CARA")
            cv2.imshow("Vision - mirada", dibujar(cuadro, r, cal, p_suave, region, texto, fps))
            tecla = cv2.waitKey(1) & 0xFF
            if tecla == ord("q"):
                break
            if tecla in (ord("c"), ord("o")):
                pedido["accion"] = "calibrar" if tecla == ord("c") else "centrar"

    c.publish(f"{TOPIC}/estado", json.dumps({"fps": 0, "cara": False, "calibrado": cal.lista,
                                             "region": None, "activo": False}))
    c.publish(f"{TOPIC}/mirada", json.dumps({"region": None}))
    c.publish(f"{TOPIC}/punto", json.dumps({"x": None}))
    time.sleep(0.3)
    c.loop_stop()
    cam.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
