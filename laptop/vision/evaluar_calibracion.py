# evaluar_calibracion.py : análisis de una calibración de la mirada (calibracion.json), para el informe.
#  - tabla de variantes de modelo con su error en validación cruzada (dejando fuera un punto entero)
#  - error por punto de la pantalla y deriva del centro (inicio vs. fin de la calibración)
#  - figura: dónde predice el modelo cada punto cuando ese punto no se usó para entrenar
# Uso:  .venv/bin/python laptop/vision/evaluar_calibracion.py [salida.png]
import json
import pathlib
import sys

import matplotlib
import numpy as np

import modelo as M

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

AQUI = pathlib.Path(__file__).resolve().parent
d = json.loads((AQUI / "calibracion.json").read_text())
if d.get("version") != 2:
    sys.exit("calibracion.json es de una versión anterior: recalibrar con la tecla C")
objetivos = [(tuple(o["punto"]), np.array(o["muestras"])) for o in d["objetivos"]]
print(f"Calibración del {d['fecha']} · {sum(len(m) for _, m in objetivos)} muestras en {len(objetivos)} puntos")

elegido, tabla = M.elegir_modelo(objetivos)
print("\nVariantes (error medio en validación cruzada, % de la zona del menú):")
print(f"  {'modelo':40s} {'x':>6s} {'y':>6s}")
for _, m, e in tabla[:8]:
    print(f"  {m.nombre:40s} {e[0] * 100:6.1f} {e[1] * 100:6.1f}")
print(f"  … {len(tabla) - 8} variantes más; la peor: {tabla[-1][1].nombre} ({tabla[-1][0] * 100:.1f} %)")
print(f"\nModelo elegido: {elegido.nombre}")

# predicción de cada punto dejado fuera
X, Y, g = M.apilar(objetivos)
pred = np.zeros_like(Y)
for k in np.unique(g):
    ent = g != k
    pred[g == k] = M.Modelo(elegido.conjunto, elegido.cuadratico, elegido.lam).ajustar(X[ent], Y[ent]).predecir(X[g == k])
print("\nError por punto (validación cruzada):")
for k, (p, _) in enumerate(objetivos):
    e = np.abs(pred[g == k] - p).mean(axis=0) * 100
    print(f"  punto {k + 1:2d} ({p[0]:.2f}, {p[1]:.2f}): x {e[0]:5.1f} %  y {e[1]:5.1f} %")

cen0, cen1 = np.median(objetivos[0][1], axis=0), np.median(objetivos[-1][1], axis=0)
print(f"\nDeriva del centro entre el inicio y el fin de la calibración: giro {cen1[M.I['giro']] - cen0[M.I['giro']]:+.1f}°, "
      f"cabeceo {cen1[M.I['cabeceo']] - cen0[M.I['cabeceo']]:+.1f}°, distancia {cen1[M.I['dist']] - cen0[M.I['dist']]:+.1f} cm")
if d.get("calidad"):
    q = d["calidad"]
    print(f"Comprobación en los 6 centros de casilla: {q['acierto']:.0f} % de casillas acertadas · error x {q['error_x']:.1f} %, y {q['error_y']:.1f} %")

salida = sys.argv[1] if len(sys.argv) > 1 else str(AQUI / "evaluacion_mirada.png")
fig, ax = plt.subplots(figsize=(9, 5.4))
for c in range(1, 3):
    ax.axvline(c / 3, color="#bbb", lw=1)
ax.axhline(0.5, color="#bbb", lw=1)
colores = plt.cm.tab10(np.linspace(0, 1, len(objetivos)))
for k, (p, _) in enumerate(objetivos):
    q = pred[g == k]
    ax.scatter(q[:, 0], q[:, 1], s=6, color=colores[k], alpha=0.35)
    ax.plot([p[0], q[:, 0].mean()], [p[1], q[:, 1].mean()], color=colores[k], lw=1)
    ax.scatter(*p, marker="+", s=160, color=colores[k], lw=2)
ax.set_xlim(-0.05, 1.05); ax.set_ylim(1.05, -0.05)
ax.set_xlabel("x (fracción del ancho del menú)"); ax.set_ylabel("y (fracción del alto)")
ax.set_title(f"Mirada: predicción de cada punto sin haberlo usado para entrenar\n{elegido.nombre}")
fig.tight_layout(); fig.savefig(salida, dpi=110)
print(f"\nFigura: {salida}")
