# ============================================================
#  ECOCORDI - Foto de prueba para el visualizador (modo "Tu propia foto")
#  Dibuja con Python (sin librerías) una "foto" de una pieza: un muro beige
#  con luz y sombra (más claro arriba a la izquierda), una puerta de madera
#  con marco oscuro, un sofá gris y el piso. Tiene una textura leve (ruido)
#  como una foto real. Se guarda como PNG.
#  Las medidas (1800 × 1350) superan los 1600 px: así se prueba que el
#  visualizador la achica.
# ============================================================
import random
import struct
import zlib

ANCHO, ALTO = 1800, 1350
PUERTA = (1250, 300, 1520, 1080)   # x1, y1, x2, y2
MARCO = 22
SOFA = (250, 800, 850, 1080)
PISO_Y = 1080


def region(x, y):
    """Qué hay en el punto (x, y) de la foto."""
    if y >= PISO_Y:
        return "piso"
    x1, y1, x2, y2 = PUERTA
    if x1 <= x < x2 and y1 <= y:
        return "puerta"
    if x1 - MARCO <= x < x2 + MARCO and y1 - MARCO <= y:
        return "marco"
    x1, y1, x2, y2 = SOFA
    if x1 <= x < x2 and y1 <= y < y2:
        return "sofa"
    return "muro"


def luz_muro(x, y):
    """Luz del muro: más clara arriba a la izquierda y una mancha de sol."""
    luz = 1.08 - 0.25 * x / ANCHO - 0.12 * y / ALTO
    if (x - 500) ** 2 + (y - 350) ** 2 < 250 ** 2:
        luz += 0.06
    return luz


def color(x, y):
    zona = region(x, y)
    if zona == "muro":
        f = luz_muro(x, y)
        return (214 * f, 198 * f, 170 * f)
    if zona == "puerta":
        return (122, 82, 52)
    if zona == "marco":
        return (60, 55, 50)
    if zona == "sofa":
        return (92, 97, 104)
    return (135, 130, 125) if x % 90 < 3 else (150, 145, 140)  # piso de piedra con juntas


def crear(ruta, semilla=7):
    azar = random.Random(semilla)
    filas = []
    for y in range(ALTO):
        fila = bytearray([0])  # filtro PNG "ninguno"
        # El color cambia poco dentro de una fila: lo calculamos por tramos de 6 px
        for x0 in range(0, ANCHO, 6):
            r, g, b = color(x0, y)
            for x in range(x0, min(x0 + 6, ANCHO)):
                if region(x, y) != region(x0, y):
                    r, g, b = color(x, y)
                ruido = azar.randint(-5, 5)
                fila += bytes((max(0, min(255, int(r) + ruido)), max(0, min(255, int(g) + ruido)),
                               max(0, min(255, int(b) + ruido))))
        filas.append(bytes(fila))

    def bloque(tipo, datos):
        return struct.pack(">I", len(datos)) + tipo + datos + struct.pack(">I", zlib.crc32(tipo + datos))

    png = (b"\x89PNG\r\n\x1a\n" + bloque(b"IHDR", struct.pack(">IIBBBBB", ANCHO, ALTO, 8, 2, 0, 0, 0))
           + bloque(b"IDAT", zlib.compress(b"".join(filas), 6)) + bloque(b"IEND", b""))
    with open(ruta, "wb") as f:
        f.write(png)
    return ruta


def medidas_png(ruta):
    """(ancho, alto) leídos de la cabecera de un PNG."""
    with open(ruta, "rb") as f:
        cabecera = f.read(24)
    if cabecera[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", cabecera[16:24])
