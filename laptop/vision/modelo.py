# modelo.py : rasgos de la mirada y modelo rasgos → punto de la pantalla, con su evaluación.
# Lo usan mirada.py (en vivo) y evaluar_calibracion.py (análisis para el informe).
#
# Coordenadas del punto: relativas a la zona del menú de la interfaz, (0, 0) arriba a la
# izquierda y (1, 1) abajo a la derecha. Casillas: 3 columnas × 2 filas.
import math

import numpy as np

# ---- puntos de la calibración y de la validación ----
# Calibración: rejilla de 3 × 3 que cubre el centro y los bordes (el centro se repite al final
# para medir la deriva). Validación: el centro de las 6 casillas, que es lo que se elige en uso.
CALIBRACION = [(0.5, 0.5), (0.08, 0.1), (0.5, 0.1), (0.92, 0.1), (0.92, 0.5),
               (0.92, 0.9), (0.5, 0.9), (0.08, 0.9), (0.08, 0.5), (0.5, 0.5)]
VALIDACION = [((c + 0.5) / 3, (f + 0.5) / 2) for f in range(2) for c in range(3)]

# ---- rasgos ----
# Malla de 478 puntos de MediaPipe. "D"/"I": ojo que aparece a la derecha/izquierda de la imagen
# (la imagen se procesa en espejo, así que coincide con el ojo derecho/izquierdo del usuario).
OJOS = {
    "D": {"ext": 33, "int": 133, "arriba": 159, "abajo": 145, "iris": [468, 469, 470, 471, 472]},
    "I": {"ext": 263, "int": 362, "arriba": 386, "abajo": 374, "iris": [473, 474, 475, 476, 477]},
}
BLENDSHAPES = ["eyeLookInLeft", "eyeLookOutLeft", "eyeLookUpLeft", "eyeLookDownLeft",
               "eyeLookInRight", "eyeLookOutRight", "eyeLookUpRight", "eyeLookDownRight"]
NOMBRES = (["iris_x_D", "iris_y_D", "iris_x_I", "iris_y_I", "apertura_D", "apertura_I"]
           + [f"bs_{b[7:]}" for b in BLENDSHAPES]
           + ["giro", "cabeceo", "alabeo", "pos_x", "pos_y", "dist"])
N_RASGOS = len(NOMBRES)                 # 20


def pose_cabeza(m):
    """Giro (yaw), cabeceo (pitch) y alabeo (roll) en grados, y posición en cm, de la matriz 4 × 4."""
    R, t = m[:3, :3], m[:3, 3]
    frente = R @ np.array([0.0, 0.0, 1.0])
    derecha = R @ np.array([1.0, 0.0, 0.0])
    giro = math.degrees(math.atan2(frente[0], frente[2]))
    cabeceo = math.degrees(math.atan2(-frente[1], math.hypot(frente[0], frente[2])))
    alabeo = math.degrees(math.atan2(derecha[1], derecha[0]))
    return giro, cabeceo, alabeo, t[0], t[1], -t[2]


def rasgos(lm, bs, matriz, ancho, alto):
    """Vector de N_RASGOS. lm: puntos normalizados; bs: dict de blendshapes; matriz: pose 4 × 4."""
    P = lambda i: np.array([lm[i].x * ancho, lm[i].y * alto])      # píxeles reales (sin deformar)
    v = []
    for o in OJOS.values():
        a, b = P(o["ext"]), P(o["int"])
        ancho_ojo = np.linalg.norm(b - a)
        u = (b - a) / ancho_ojo                                    # eje del ojo (corrige el alabeo)
        n = np.array([-u[1], u[0]])
        iris = np.mean([P(i) for i in o["iris"]], axis=0)
        rel = iris - (a + b) / 2
        v += [rel @ u / ancho_ojo, rel @ n / ancho_ojo]
    for o in OJOS.values():
        v.append(np.linalg.norm(P(o["abajo"]) - P(o["arriba"])) / np.linalg.norm(P(o["int"]) - P(o["ext"])))
    v += [bs[b] for b in BLENDSHAPES]
    v += list(pose_cabeza(np.asarray(matriz)))
    return np.array(v, dtype=float)


# ---- variantes de modelo ----
I = {n: i for i, n in enumerate(NOMBRES)}
_ojos = [I[n] for n in NOMBRES[:6]] + list(range(6, 14))
CONJUNTOS = {
    "iris": [I["iris_x_D"], I["iris_y_D"], I["iris_x_I"], I["iris_y_I"]],
    "ojos": _ojos,
    "ojos+pose": _ojos + [I["giro"], I["cabeceo"]],
    "ojos+pose+posición": _ojos + [I["giro"], I["cabeceo"], I["pos_x"], I["pos_y"], I["dist"]],
}
LAMBDAS = [0.3, 1.0, 3.0, 10.0, 30.0, 100.0]


def expandir(X, cols, cuadratico):
    """Rasgos elegidos, más (opcional) términos de 2.º orden de la posición media del iris."""
    Z = X[:, cols]
    if cuadratico:
        ix = (X[:, I["iris_x_D"]] + X[:, I["iris_x_I"]]) / 2
        iy = (X[:, I["iris_y_D"]] + X[:, I["iris_y_I"]]) / 2
        Z = np.column_stack([Z, ix * ix, iy * iy, ix * iy])
    return Z


class Modelo:
    """Regresión ridge sobre rasgos normalizados → (x, y)."""

    def __init__(self, conjunto="ojos+pose", cuadratico=False, lam=3.0):
        self.conjunto, self.cuadratico, self.lam = conjunto, cuadratico, lam
        self.media = self.escala = self.W = None

    @property
    def nombre(self):
        return f"{self.conjunto}{' (2.º orden)' if self.cuadratico else ''}, λ={self.lam:g}"

    def ajustar(self, X, Y):
        Z = expandir(X, CONJUNTOS[self.conjunto], self.cuadratico)
        self.media, self.escala = Z.mean(axis=0), np.maximum(Z.std(axis=0), 1e-9)
        Zn = np.column_stack([(Z - self.media) / self.escala, np.ones(len(Z))])
        reg = self.lam * np.eye(Zn.shape[1]); reg[-1, -1] = 0          # sin regularizar la constante
        self.W = np.linalg.solve(Zn.T @ Zn + reg, Zn.T @ Y)
        return self

    def predecir(self, X):
        X = np.atleast_2d(X)
        Z = expandir(X, CONJUNTOS[self.conjunto], self.cuadratico)
        return np.column_stack([(Z - self.media) / self.escala, np.ones(len(Z))]) @ self.W

    def guardar(self):
        return {"conjunto": self.conjunto, "cuadratico": self.cuadratico, "lam": self.lam}


def apilar(objetivos):
    """objetivos: [((x, y), [vectores])] → X, Y, índice del objetivo de cada muestra."""
    X = np.vstack([np.array(m) for _, m in objetivos])
    Y = np.vstack([np.tile(p, (len(m), 1)) for p, m in objetivos])
    g = np.concatenate([np.full(len(m), k) for k, (_, m) in enumerate(objetivos)])
    return X, Y, g


def validacion_cruzada(objetivos, modelo):
    """Deja fuera cada punto de la calibración entero y lo predice con el resto.
    Mide lo que importa: acertar en lugares de la pantalla que no se calibraron."""
    X, Y, g = apilar(objetivos)
    errores = []
    for k in np.unique(g):
        ent, pru = g != k, g == k
        if len(np.unique(Y[ent], axis=0)) < 3:
            continue
        pred = Modelo(modelo.conjunto, modelo.cuadratico, modelo.lam).ajustar(X[ent], Y[ent]).predecir(X[pru])
        errores.append(np.abs(pred - Y[pru]).mean(axis=0))
    return np.mean(errores, axis=0)                 # error medio |x|, |y| (fracción de la zona)


def elegir_modelo(objetivos):
    """Prueba todas las variantes y devuelve la de menor error en validación cruzada, con la tabla."""
    tabla = []
    for conjunto in CONJUNTOS:
        for cuad in (False, True):
            for lam in LAMBDAS:
                m = Modelo(conjunto, cuad, lam)
                e = validacion_cruzada(objetivos, m)
                tabla.append((float(e[0] + e[1]), m, e))
    tabla.sort(key=lambda r: r[0])
    mejor = tabla[0][1]
    X, Y, _ = apilar(objetivos)
    return Modelo(mejor.conjunto, mejor.cuadratico, mejor.lam).ajustar(X, Y), tabla


def limpiar(muestras, k=3.0):
    """Quita muestras atípicas (más de k desviaciones robustas de la mediana en algún rasgo)."""
    M = np.array(muestras)
    if len(M) < 5:
        return M
    med = np.median(M, axis=0)
    mad = np.median(np.abs(M - med), axis=0) * 1.4826 + 1e-9
    return M[(np.abs(M - med) / mad <= k).all(axis=1)]


def casilla(p):
    col = min(2, max(0, int(p[0] * 3)))
    fila = min(1, max(0, int(p[1] * 2)))
    return fila * 3 + col + 1


def dentro_con_margen(p, c, margen):
    """¿El punto está dentro de la casilla c, a más de `margen` de sus bordes?"""
    col, fila = (c - 1) % 3, (c - 1) // 3
    x0, x1, y0, y1 = col / 3, (col + 1) / 3, fila / 2, (fila + 1) / 2
    return x0 + margen <= p[0] <= x1 - margen and y0 + margen <= p[1] <= y1 - margen


class UnoEuro:
    """Filtro One Euro (Casiez et al., CHI 2012): suaviza mucho en reposo y poco al moverse."""

    def __init__(self, corte_min=0.8, beta=0.6, corte_d=1.0):
        self.corte_min, self.beta, self.corte_d = corte_min, beta, corte_d
        self.x = self.dx = self.t = None

    @staticmethod
    def _alfa(corte, dt):
        return 1.0 / (1.0 + 1.0 / (2 * math.pi * corte * dt))

    def __call__(self, x, t):
        x = np.asarray(x, dtype=float)
        if self.t is None or t - self.t > 0.5:      # primer dato o tras una pausa: reiniciar
            self.x, self.dx, self.t = x, np.zeros_like(x), t
            return x
        dt = max(1e-3, t - self.t)
        self.t = t
        dx = (x - self.x) / dt
        a_d = self._alfa(self.corte_d, dt)
        self.dx = a_d * dx + (1 - a_d) * self.dx
        corte = self.corte_min + self.beta * np.linalg.norm(self.dx)
        a = self._alfa(corte, dt)
        self.x = a * x + (1 - a) * self.x
        return self.x

    def reiniciar(self):
        self.t = None
