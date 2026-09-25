#!/usr/bin/env python3
# ============================================================
#  ECOCORDI - Genera los 4 ambientes del visualizador de color
#  (living, dormitorio, fachada y terraza) como ilustraciones SVG propias.
#
#  Uso:  python3 img/ambientes/generar.py
#
#  Cada ambiente tiene 4 capas (grupos <g>), en este orden:
#   1. capa-base   → fondo, piso y las ZONAS PINTABLES (<path data-zona="...">)
#   2. capa-sombra → sombras en escala de grises con mix-blend-mode: multiply:
#                    oscurecen el color que haya debajo sin taparlo
#   3. capa-luz    → luces con mix-blend-mode: screen: aclaran
#   4. capa-frente → muebles y plantas (no se pintan)
#  Así, cuando el visualizador cambia el color de una zona, las sombras y la
#  luz siguen encima y el muro no se ve plano.
#  Las perspectivas usan un "punto de fuga": todas las líneas que van hacia
#  el fondo de la pieza apuntan a ese punto.
# ============================================================
import os

CARPETA = os.path.dirname(os.path.abspath(__file__))


def pts(*puntos):
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in puntos)


def ruta(*puntos):
    """Un polígono como <path d="...">"""
    return "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in puntos) + " Z"


def svg(prefijo, titulo, defs, base, sombra, luz, frente):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 800" data-prefijo="{prefijo}">
  <!-- Ilustración propia de Pinturas Ecocordi, generada por img/ambientes/generar.py -->
  <title>{titulo}</title>
  <defs>
    <filter id="{prefijo}-difuso" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="9"/></filter>
    <filter id="{prefijo}-muy-difuso" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="26"/></filter>
{defs}
  </defs>
  <g class="capa-base">
{base}
  </g>
  <g class="capa-sombra">
{sombra}
  </g>
  <g class="capa-luz">
{luz}
  </g>
  <g class="capa-frente">
{frente}
  </g>
</svg>
'''


class Pieza:
    """Una pieza vista de frente: muro del fondo, dos muros laterales, piso y cielo."""

    def __init__(self, fuga, fondo):
        self.fx, self.fy = fuga           # punto de fuga
        self.x1, self.y1, self.x2, self.y2 = fondo  # rectángulo del muro del fondo

    def punto(self, esquina_x, esquina_y, x=None, y=None):
        """Sigue la línea que va del punto de fuga a una esquina del fondo, hasta x (o y)."""
        dx, dy = esquina_x - self.fx, esquina_y - self.fy
        t = (x - self.fx) / dx if x is not None else (y - self.fy) / dy
        return self.fx + dx * t, self.fy + dy * t

    def lateral(self, lado, x, desde, hasta):
        """Cuadrilátero sobre un muro lateral (lado 'izq' o 'der'), entre x y x+ancho, a una
        altura relativa (0 = piso, 1 = cielo) desde..hasta. x es una tupla (xa, xb)."""
        ex = self.x1 if lado == "izq" else self.x2
        esquinas = []
        for xi in x:
            _, arriba = self.punto(ex, self.y1, x=xi)
            _, abajo = self.punto(ex, self.y2, x=xi)
            alto = abajo - arriba
            esquinas.append((xi, abajo - alto * hasta, abajo - alto * desde))
        (xa, ta, ba), (xb, tb, bb) = esquinas
        return [(xa, ta), (xb, tb), (xb, bb), (xa, ba)]


# ------------------------------------------------------------
#  1. LIVING: muro principal (fondo y derecha), muro de acento (izquierda) y puerta
# ------------------------------------------------------------
def living():
    p = Pieza((600, 325), (200, 90, 1000, 560))
    ci = p.punto(200, 90, y=0)[0]           # donde el cielo corta el borde de arriba
    cd = p.punto(1000, 90, y=0)[0]
    _, pi = p.punto(200, 560, x=0)          # donde el piso corta el borde izquierdo
    _, pd = p.punto(1000, 560, x=1200)
    cielo = [(ci, 0), (cd, 0), (1000, 90), (200, 90)]
    fondo = [(200, 90), (1000, 90), (1000, 560), (200, 560)]
    izq = [(0, 0), (ci, 0), (200, 90), (200, 560), (0, pi)]
    der = [(cd, 0), (1200, 0), (1200, pd), (1000, 560), (1000, 90)]
    piso = [(0, pi), (200, 560), (1000, 560), (1200, pd), (1200, 800), (0, 800)]
    ventana = p.lateral("izq", (55, 150), 0.34, 0.86)
    marco_v = p.lateral("izq", (45, 160), 0.32, 0.88)
    puerta = p.lateral("der", (1035, 1125), 0, 0.74)
    marco_p = p.lateral("der", (1027, 1134), 0, 0.77)
    panel1 = p.lateral("der", (1047, 1113), 0.43, 0.68)
    panel2 = p.lateral("der", (1047, 1113), 0.08, 0.38)
    zocalo_d = p.lateral("der", (1000, 1200), 0, 0.03)
    zocalo_i = p.lateral("izq", (0, 200), 0, 0.03)
    # Tablas del piso: líneas que van hacia el punto de fuga
    tablas = "".join(
        f'<line x1="{x0:.1f}" y1="800" x2="{p.punto(x0, 800, y=560)[0]:.1f}" y2="560"/>'
        for x0 in range(-600, 1900, 115))
    defs = '''    <linearGradient id="lv-cielo" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#B9D6EA"/><stop offset="1" stop-color="#F3EFE2"/></linearGradient>
    <linearGradient id="lv-sombra-fondo" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#C4C4C4"/><stop offset="0.22" stop-color="#F0F0F0"/><stop offset="0.8" stop-color="#FFFFFF"/><stop offset="1" stop-color="#DCDCDC"/></linearGradient>
    <linearGradient id="lv-sombra-izq" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#A9A9A9"/><stop offset="1" stop-color="#D9D9D9"/></linearGradient>
    <linearGradient id="lv-sombra-der" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#E4E4E4"/><stop offset="1" stop-color="#C2C2C2"/></linearGradient>
    <linearGradient id="lv-sombra-piso" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#9C9C9C"/><stop offset="1" stop-color="#E6E6E6"/></linearGradient>
    <radialGradient id="lv-lampara"><stop offset="0" stop-color="#6B5A3E"/><stop offset="1" stop-color="#000000"/></radialGradient>
    <linearGradient id="lv-sofa" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#8E918B"/><stop offset="1" stop-color="#6F726C"/></linearGradient>'''
    base = f'''    <polygon points="{pts(*cielo)}" fill="#F2F0EB"/>
    <path data-zona="acento" d="{ruta(*izq)}" fill="#D9D1C5"/>
    <path data-zona="muro" d="{ruta(*fondo)}" fill="#E8E3DA"/>
    <path data-zona="muro" d="{ruta(*der)}" fill="#E8E3DA"/>
    <polygon points="{pts(*piso)}" fill="#AF8B66"/>
    <polygon points="{pts(*marco_v)}" fill="#F6F4EF"/>
    <polygon points="{pts(*ventana)}" fill="url(#lv-cielo)"/>
    <polygon points="{pts(*marco_p)}" fill="#F6F4EF"/>
    <path data-zona="puerta" d="{ruta(*puerta)}" fill="#B48C64"/>
    <polygon points="200,548 1000,548 1000,560 200,560" fill="#F4F2ED"/>
    <polygon points="{pts(*zocalo_d)}" fill="#F4F2ED"/>
    <polygon points="{pts(*zocalo_i)}" fill="#F4F2ED"/>
    <polygon points="330,610 870,610 980,720 220,720" fill="#D7CDBD"/>'''
    sombra = f'''    <path d="{ruta(*fondo)}" fill="url(#lv-sombra-fondo)"/>
    <path d="{ruta(*izq)}" fill="url(#lv-sombra-izq)"/>
    <path d="{ruta(*der)}" fill="url(#lv-sombra-der)"/>
    <polygon points="{pts(*piso)}" fill="url(#lv-sombra-piso)"/>
    <g stroke="#8B8B8B" stroke-width="3" clip-path="url(#lv-recorte-piso)" opacity="0.5">{tablas}</g>
    <g stroke="#8A8A8A" stroke-width="14" filter="url(#lv-difuso)" opacity="0.8">
      <line x1="200" y1="90" x2="200" y2="560"/><line x1="1000" y1="90" x2="1000" y2="560"/>
      <line x1="200" y1="90" x2="1000" y2="90"/><line x1="200" y1="560" x2="1000" y2="560"/>
    </g>
    <polygon points="{pts(*panel1)}" fill="#D2D2D2" stroke="#9E9E9E" stroke-width="2"/>
    <polygon points="{pts(*panel2)}" fill="#D2D2D2" stroke="#9E9E9E" stroke-width="2"/>
    <polygon points="{pts(puerta[0], puerta[3], (puerta[3][0] + 9, puerta[3][1]), (puerta[0][0] + 9, puerta[0][1]))}" fill="#9A9A9A"/>
    <rect x="370" y="420" width="470" height="150" rx="40" fill="#A6A6A6" filter="url(#lv-muy-difuso)"/>
    <ellipse cx="600" cy="595" rx="290" ry="26" fill="#6E6E6E" filter="url(#lv-difuso)"/>
    <rect x="532" y="218" width="160" height="112" fill="#B5B5B5" filter="url(#lv-difuso)"/>
    <ellipse cx="905" cy="578" rx="60" ry="12" fill="#7A7A7A" filter="url(#lv-difuso)"/>'''
    luz = f'''    <polygon points="235,600 470,590 640,760 250,795" fill="#4C4232" filter="url(#lv-muy-difuso)"/>
    <polygon points="208,230 318,248 318,520 208,540" fill="#3A3226" filter="url(#lv-muy-difuso)"/>
    <circle cx="300" cy="300" r="170" fill="url(#lv-lampara)"/>'''
    frente = f'''    <!-- Lámpara de pie -->
    <line x1="300" y1="330" x2="300" y2="580" stroke="#3B3833" stroke-width="5"/>
    <ellipse cx="300" cy="582" rx="38" ry="8" fill="#3B3833"/>
    <polygon points="258,250 342,250 360,330 240,330" fill="#EFE6D2"/>
    <!-- Cuadro -->
    <rect x="520" y="205" width="160" height="112" fill="#F7F4EE" stroke="#4A433A" stroke-width="6"/>
    <path d="M538 290 C 575 240, 610 300, 662 232" fill="none" stroke="#C07A52" stroke-width="10" stroke-linecap="round"/>
    <circle cx="566" cy="245" r="17" fill="#7C9A86"/>
    <!-- Sofá -->
    <rect x="395" y="415" width="410" height="90" rx="22" fill="#858881"/>
    <rect x="365" y="470" width="470" height="85" rx="18" fill="url(#lv-sofa)"/>
    <rect x="345" y="445" width="62" height="118" rx="22" fill="#7D807A"/>
    <rect x="793" y="445" width="62" height="118" rx="22" fill="#7D807A"/>
    <rect x="410" y="468" width="190" height="40" rx="14" fill="#999C95"/>
    <rect x="600" y="468" width="190" height="40" rx="14" fill="#959891"/>
    <rect x="430" y="430" width="92" height="62" rx="16" fill="#C9A77B" transform="rotate(-6 476 461)"/>
    <line x1="385" y1="560" x2="380" y2="585" stroke="#3B3833" stroke-width="7" stroke-linecap="round"/>
    <line x1="815" y1="560" x2="820" y2="585" stroke="#3B3833" stroke-width="7" stroke-linecap="round"/>
    <!-- Planta -->
    <path d="M870 520 L940 520 L930 580 L880 580 Z" fill="#B7654A"/>
    <g fill="#5E8A5E">
      <ellipse cx="880" cy="470" rx="16" ry="52" transform="rotate(-28 880 470)"/>
      <ellipse cx="905" cy="455" rx="15" ry="62"/>
      <ellipse cx="932" cy="470" rx="16" ry="52" transform="rotate(26 932 470)"/>
      <ellipse cx="895" cy="490" rx="12" ry="36" transform="rotate(-55 895 490)" fill="#4E7A52"/>
    </g>
    <!-- Mesa de centro -->
    <polygon points="480,640 720,640 750,672 450,672" fill="#6C4F37"/>
    <rect x="450" y="672" width="300" height="12" fill="#5A4130"/>
    <line x1="470" y1="684" x2="468" y2="730" stroke="#4A3627" stroke-width="8"/>
    <line x1="730" y1="684" x2="732" y2="730" stroke="#4A3627" stroke-width="8"/>
    <ellipse cx="560" cy="648" rx="30" ry="8" fill="#E9E1D3"/>'''
    defs += f'''
    <clipPath id="lv-recorte-piso"><path d="{ruta(*piso)}"/></clipPath>'''
    return svg("lv", "Living con muro principal, muro de acento y puerta", defs, base, sombra, luz, frente)


# ------------------------------------------------------------
#  2. DORMITORIO: muro de acento (respaldo de la cama), muros y puerta
# ------------------------------------------------------------
def dormitorio():
    p = Pieza((640, 330), (330, 120, 950, 540))
    ci = p.punto(330, 120, y=0)[0]
    cd = p.punto(950, 120, y=0)[0]
    _, pi = p.punto(330, 540, x=0)
    _, pd = p.punto(950, 540, x=1200)
    cielo = [(ci, 0), (cd, 0), (950, 120), (330, 120)]
    fondo = [(330, 120), (950, 120), (950, 540), (330, 540)]
    izq = [(0, 0), (ci, 0), (330, 120), (330, 540), (0, pi)]
    der = [(cd, 0), (1200, 0), (1200, pd), (950, 540), (950, 120)]
    piso = [(0, pi), (330, 540), (950, 540), (1200, pd), (1200, 800), (0, 800)]
    puerta = p.lateral("izq", (75, 195), 0, 0.74)
    marco_p = p.lateral("izq", (66, 205), 0, 0.77)
    panel = p.lateral("izq", (95, 175), 0.1, 0.64)
    ventana = p.lateral("der", (1015, 1130), 0.36, 0.86)
    marco_v = p.lateral("der", (1005, 1140), 0.34, 0.88)
    cortina1 = p.lateral("der", (985, 1022), 0.12, 0.92)
    cortina2 = p.lateral("der", (1122, 1165), 0.12, 0.92)
    # Cama: cabecera en el muro del fondo y colchón hacia adelante
    cama_atras_i, cama_atras_d = (470, 470), (810, 470)
    cama_frente_i = p.punto(*cama_atras_i, y=612)
    cama_frente_d = p.punto(*cama_atras_d, y=612)
    tablas = "".join(
        f'<line x1="{x0:.1f}" y1="800" x2="{p.punto(x0, 800, y=540)[0]:.1f}" y2="540"/>'
        for x0 in range(-500, 1900, 125))
    defs = '''    <linearGradient id="dm-cielo" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#C6D9E6"/><stop offset="1" stop-color="#F4EEE2"/></linearGradient>
    <linearGradient id="dm-sombra-fondo" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#BDBDBD"/><stop offset="0.25" stop-color="#EDEDED"/><stop offset="0.85" stop-color="#FFFFFF"/><stop offset="1" stop-color="#D8D8D8"/></linearGradient>
    <linearGradient id="dm-sombra-izq" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#E2E2E2"/><stop offset="1" stop-color="#C4C4C4"/></linearGradient>
    <linearGradient id="dm-sombra-der" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#D4D4D4"/><stop offset="1" stop-color="#A8A8A8"/></linearGradient>
    <linearGradient id="dm-sombra-piso" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#A0A0A0"/><stop offset="1" stop-color="#E8E8E8"/></linearGradient>
    <radialGradient id="dm-velador"><stop offset="0" stop-color="#6E5B3C"/><stop offset="1" stop-color="#000000"/></radialGradient>
    <linearGradient id="dm-plumon" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#F2EEE7"/><stop offset="1" stop-color="#DCD5CA"/></linearGradient>'''
    base = f'''    <polygon points="{pts(*cielo)}" fill="#F3F1EC"/>
    <path data-zona="muro" d="{ruta(*izq)}" fill="#E6E1D8"/>
    <path data-zona="acento" d="{ruta(*fondo)}" fill="#C9BFB1"/>
    <path data-zona="muro" d="{ruta(*der)}" fill="#E6E1D8"/>
    <polygon points="{pts(*piso)}" fill="#C29C75"/>
    <polygon points="{pts(*marco_p)}" fill="#F6F4EF"/>
    <path data-zona="puerta" d="{ruta(*puerta)}" fill="#EDE8DF"/>
    <polygon points="{pts(*marco_v)}" fill="#F6F4EF"/>
    <polygon points="{pts(*ventana)}" fill="url(#dm-cielo)"/>
    <polygon points="330,528 950,528 950,540 330,540" fill="#F4F2ED"/>
    <polygon points="{pts(*p.lateral("izq", (0, 330), 0, 0.03))}" fill="#F4F2ED"/>
    <polygon points="{pts(*p.lateral("der", (950, 1200), 0, 0.03))}" fill="#F4F2ED"/>
    <ellipse cx="640" cy="690" rx="360" ry="70" fill="#D9CDB9"/>'''
    sombra = f'''    <path d="{ruta(*fondo)}" fill="url(#dm-sombra-fondo)"/>
    <path d="{ruta(*izq)}" fill="url(#dm-sombra-izq)"/>
    <path d="{ruta(*der)}" fill="url(#dm-sombra-der)"/>
    <polygon points="{pts(*piso)}" fill="url(#dm-sombra-piso)"/>
    <g stroke="#8E8E8E" stroke-width="3" clip-path="url(#dm-recorte-piso)" opacity="0.45">{tablas}</g>
    <g stroke="#8A8A8A" stroke-width="14" filter="url(#dm-difuso)" opacity="0.8">
      <line x1="330" y1="120" x2="330" y2="540"/><line x1="950" y1="120" x2="950" y2="540"/>
      <line x1="330" y1="120" x2="950" y2="120"/><line x1="330" y1="540" x2="950" y2="540"/>
    </g>
    <polygon points="{pts(*panel)}" fill="#DADADA" stroke="#A5A5A5" stroke-width="2"/>
    <polygon points="{pts(puerta[1], puerta[2], (puerta[2][0] - 8, puerta[2][1]), (puerta[1][0] - 8, puerta[1][1]))}" fill="#A0A0A0"/>
    <rect x="455" y="300" width="370" height="190" rx="30" fill="#A2A2A2" filter="url(#dm-muy-difuso)"/>
    <polygon points="{pts((cama_frente_i[0] - 10, 640), (cama_frente_d[0] + 10, 640), (cama_frente_d[0] + 40, 700), (cama_frente_i[0] - 40, 700))}" fill="#7A7A7A" filter="url(#dm-muy-difuso)"/>'''
    luz = f'''    <polygon points="760,650 960,630 1040,790 800,800" fill="#4A4031" filter="url(#dm-muy-difuso)"/>
    <circle cx="400" cy="400" r="150" fill="url(#dm-velador)"/>
    <circle cx="880" cy="400" r="150" fill="url(#dm-velador)"/>'''
    frente = f'''    <!-- Cortinas -->
    <polygon points="{pts(*cortina1)}" fill="#E8DCCB"/>
    <polygon points="{pts(*cortina2)}" fill="#E8DCCB"/>
    <!-- Cama -->
    <rect x="455" y="318" width="370" height="160" rx="18" fill="#6E5A48"/>
    <rect x="472" y="334" width="336" height="126" rx="12" fill="#7E6955"/>
    <polygon points="{pts(cama_atras_i, cama_atras_d, cama_frente_d, cama_frente_i)}" fill="url(#dm-plumon)"/>
    <rect x="{cama_frente_i[0]:.1f}" y="612" width="{cama_frente_d[0] - cama_frente_i[0]:.1f}" height="44" fill="#CFC6B8"/>
    <polygon points="{pts((cama_atras_i[0] - 6, 520), (cama_atras_d[0] + 6, 520), (cama_frente_d[0] + 4, 600), (cama_frente_i[0] - 4, 600))}" fill="#B9C7BD"/>
    <rect x="{cama_frente_i[0] - 4:.1f}" y="600" width="{cama_frente_d[0] - cama_frente_i[0] + 8:.1f}" height="28" fill="#A7B6AB"/>
    <rect x="495" y="440" width="135" height="48" rx="18" fill="#FAF8F4"/>
    <rect x="650" y="440" width="135" height="48" rx="18" fill="#F6F3EE"/>
    <line x1="{cama_frente_i[0] + 8:.1f}" y1="660" x2="{cama_frente_i[0] + 8:.1f}" y2="680" stroke="#4A3A2E" stroke-width="8"/>
    <line x1="{cama_frente_d[0] - 8:.1f}" y1="660" x2="{cama_frente_d[0] - 8:.1f}" y2="680" stroke="#4A3A2E" stroke-width="8"/>
    <!-- Veladores y lámparas -->
    <rect x="360" y="470" width="82" height="80" rx="4" fill="#8A6C50"/>
    <rect x="838" y="470" width="82" height="80" rx="4" fill="#8A6C50"/>
    <line x1="366" y1="505" x2="436" y2="505" stroke="#6F563F" stroke-width="3"/>
    <line x1="844" y1="505" x2="914" y2="505" stroke="#6F563F" stroke-width="3"/>
    <polygon points="382,418 420,418 430,452 372,452" fill="#F0E6D3"/>
    <rect x="397" y="452" width="8" height="18" fill="#3B3833"/>
    <polygon points="860,418 898,418 908,452 850,452" fill="#F0E6D3"/>
    <rect x="875" y="452" width="8" height="18" fill="#3B3833"/>'''
    defs += f'''
    <clipPath id="dm-recorte-piso"><path d="{ruta(*piso)}"/></clipPath>'''
    return svg("dm", "Dormitorio con muro de acento detrás de la cama, muros laterales y puerta",
               defs, base, sombra, luz, frente)


# ------------------------------------------------------------
#  3. FACHADA: fachada, volumen de acento, puerta y reja
# ------------------------------------------------------------
def fachada():
    barras = "".join(f"M{x} 574 h8 v124 h-8 Z " for x in range(96, 1112, 30))
    pilares = "".join(f"M{x} 552 h26 v150 h-26 Z " for x in (70, 590, 1112))
    reja = barras + pilares + "M70 580 H1138 v9 H70 Z M70 668 H1138 v9 H70 Z"
    sombra_reja = "".join(f"M{x} 704 l-40 60 h8 l40 -60 Z " for x in range(96, 1112, 30))
    defs = '''    <linearGradient id="fc-cielo" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#BCD7E9"/><stop offset="1" stop-color="#F2EBDD"/></linearGradient>
    <linearGradient id="fc-sombra-muro" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#FFFFFF"/><stop offset="1" stop-color="#CFCFCF"/></linearGradient>
    <linearGradient id="fc-sombra-alero" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#8C8C8C"/><stop offset="1" stop-color="#FFFFFF"/></linearGradient>
    <linearGradient id="fc-sombra-reja" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#F2F2F2"/><stop offset="1" stop-color="#9C9C9C"/></linearGradient>
    <linearGradient id="fc-vidrio" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#9DB9C9"/><stop offset="0.55" stop-color="#6F8C9D"/><stop offset="1" stop-color="#58707F"/></linearGradient>
    <radialGradient id="fc-sol" cx="0.15" cy="0.1" r="0.8"><stop offset="0" stop-color="#5C4A2C"/><stop offset="1" stop-color="#000000"/></radialGradient>'''
    ventana = lambda x, y, w, h: (f'<rect x="{x - 8}" y="{y - 8}" width="{w + 16}" height="{h + 16}" fill="#F6F4EF"/>'
                                   f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="url(#fc-vidrio)"/>'
                                   f'<rect x="{x + w / 2 - 3}" y="{y}" width="6" height="{h}" fill="#F6F4EF"/>'
                                   f'<polygon points="{x + 12},{y + h - 10} {x + w * 0.42},{y + 12} {x + w * 0.42 + 26},{y + 12} {x + 38},{y + h - 10}" fill="#FFFFFF" opacity="0.25"/>')
    base = f'''    <rect width="1200" height="600" fill="url(#fc-cielo)"/>
    <path d="M0 470 C 180 400, 330 450, 520 410 S 900 380, 1200 440 V600 H0 Z" fill="#B8C3A9"/>
    <rect y="590" width="1200" height="210" fill="#8EA06A"/>
    <rect y="704" width="1200" height="56" fill="#D2CABB"/>
    <rect y="760" width="1200" height="40" fill="#96918A"/>
    <path data-zona="fachada" d="M180 300 H800 V640 H180 Z" fill="#EDE7DC"/>
    <path data-zona="acento" d="M800 232 H1060 V640 H800 Z" fill="#9FA89A"/>
    <rect x="788" y="218" width="284" height="16" fill="#F3F1EC"/>
    <polygon points="140,305 490,125 840,305" fill="#9C5540"/>
    <polygon points="140,305 490,125 840,305 822,305 490,142 158,305" fill="#7C4232"/>
    <rect x="410" y="428" width="120" height="212" fill="#F6F4EF"/>
    <path data-zona="puerta" d="M422 440 H518 V640 H422 Z" fill="#7A5A40"/>
    {ventana(228, 392, 142, 118)}
    {ventana(596, 392, 150, 118)}
    {ventana(862, 300, 136, 190)}
    <rect x="160" y="636" width="660" height="10" fill="#CFC8BB"/>'''
    sombra = f'''    <path d="M180 300 H800 V640 H180 Z" fill="url(#fc-sombra-muro)"/>
    <path d="M800 232 H1060 V640 H800 Z" fill="url(#fc-sombra-muro)"/>
    <polygon points="180,300 800,300 800,338 180,338" fill="url(#fc-sombra-alero)"/>
    <rect x="800" y="234" width="260" height="24" fill="url(#fc-sombra-alero)"/>
    <rect x="800" y="232" width="22" height="408" fill="#C6C6C6" filter="url(#fc-difuso)"/>
    <polygon points="422,440 518,440 518,452 422,452" fill="#8F8F8F"/>
    <polygon points="422,440 432,440 432,640 422,640" fill="#9A9A9A"/>
    <rect x="436" y="460" width="68" height="70" fill="none" stroke="#9B9B9B" stroke-width="3"/>
    <rect x="436" y="548" width="68" height="76" fill="none" stroke="#9B9B9B" stroke-width="3"/>
    <rect x="160" y="628" width="920" height="22" fill="#9C9C9C" filter="url(#fc-difuso)"/>
    <path d="{reja}" fill="url(#fc-sombra-reja)"/>
    <path d="{sombra_reja}" fill="#8E8E8E" filter="url(#fc-difuso)" opacity="0.7"/>'''
    luz = '''    <rect width="1200" height="700" fill="url(#fc-sol)"/>'''
    frente = f'''    <!-- Árbol -->
    <rect x="62" y="380" width="22" height="220" fill="#6A4E38"/>
    <circle cx="70" cy="330" r="78" fill="#6E8F5C"/>
    <circle cx="120" cy="370" r="56" fill="#5F8150"/>
    <circle cx="30" cy="378" r="50" fill="#7A9A66"/>
    <!-- Arbustos -->
    <ellipse cx="300" cy="610" rx="90" ry="40" fill="#5E8150"/>
    <ellipse cx="680" cy="612" rx="100" ry="38" fill="#688B58"/>
    <ellipse cx="960" cy="614" rx="92" ry="36" fill="#5E8150"/>
    <!-- Reja (zona pintable, va delante de la casa) -->
    <path data-zona="reja" d="{reja}" fill="#3C3F41"/>'''
    return svg("fc", "Fachada de una casa con muro principal, volumen de acento, puerta y reja",
               defs, base, sombra, luz, frente)


# ------------------------------------------------------------
#  4. TERRAZA: muro de la casa, piso de madera, baranda de madera y reja metálica
# ------------------------------------------------------------
def terraza():
    fx, fy = 700, 360
    borde = lambda x: 470 + (300 - x) * 82.5 / 300     # borde izquierdo del piso (hacia el punto de fuga)
    alto = lambda x: 0.22 * (700 - x)                  # alto de la baranda (más grande adelante)
    postes, rieles = [], []
    for x in (292, 222, 150, 76, 4):
        ancho = 0.03 * (700 - x)
        y0 = borde(x)
        postes.append(f"M{x:.1f} {y0:.1f} h{ancho:.1f} v{-alto(x) - 6:.1f} h{-ancho:.1f} Z")
    for frac, grosor in ((1.0, 0.045), (0.5, 0.03)):
        a, b = 300, -20
        ya, yb = borde(a) - alto(a) * frac, borde(b) - alto(b) * frac
        ga, gb = grosor * (700 - a), grosor * (700 - b)
        rieles.append(f"M{a} {ya:.1f} L{b} {yb:.1f} L{b} {yb + gb:.1f} L{a} {ya + ga:.1f} Z")
    baranda = " ".join(postes + rieles)
    piso = [(300, 470), (1200, 470), (1200, 800), (0, 800), (0, borde(0))]
    tablas = "".join(
        f'<line x1="{x0}" y1="800" x2="{fx + (x0 - fx) * (470 - fy) / (800 - fy):.1f}" y2="470"/>'
        for x0 in range(-900, 2200, 70))
    barrotes = "".join(f"M{x} 206 h7 v152 h-7 Z " for x in range(918, 1100, 24))
    reja = barrotes + "M906 204 h206 v8 h-206 Z M906 280 h206 v7 h-206 Z M906 352 h206 v8 h-206 Z"
    defs = '''    <linearGradient id="tz-cielo" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#AFCFE6"/><stop offset="1" stop-color="#EFE9DA"/></linearGradient>
    <linearGradient id="tz-sombra-muro" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#9E9E9E"/><stop offset="0.18" stop-color="#EDEDED"/><stop offset="1" stop-color="#D2D2D2"/></linearGradient>
    <linearGradient id="tz-sombra-piso" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ABABAB"/><stop offset="1" stop-color="#F2F2F2"/></linearGradient>
    <linearGradient id="tz-sombra-baranda" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#C8C8C8"/><stop offset="1" stop-color="#F4F4F4"/></linearGradient>
    <linearGradient id="tz-vidrio" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#A4BFCE"/><stop offset="1" stop-color="#5E7686"/></linearGradient>
    <radialGradient id="tz-sol" cx="0.2" cy="0.2" r="0.7"><stop offset="0" stop-color="#5A4A2E"/><stop offset="1" stop-color="#000000"/></radialGradient>'''
    base = f'''    <rect width="1200" height="600" fill="url(#tz-cielo)"/>
    <path d="M0 330 C 120 300, 220 320, 320 300 V600 H0 Z" fill="#B3C0A2"/>
    <rect y="400" width="330" height="200" fill="#8FA26B"/>
    <path data-zona="muro" d="M300 120 H1200 V470 H300 Z" fill="#E4DCCD"/>
    <rect x="290" y="92" width="910" height="30" fill="#5E534B"/>
    <rect x="520" y="190" width="300" height="280" fill="#F6F4EF"/>
    <rect x="532" y="202" width="134" height="268" fill="url(#tz-vidrio)"/>
    <rect x="674" y="202" width="134" height="268" fill="url(#tz-vidrio)"/>
    <rect x="898" y="196" width="222" height="172" fill="#F6F4EF"/>
    <rect x="908" y="206" width="202" height="152" fill="url(#tz-vidrio)"/>
    <path data-zona="piso" d="{ruta(*piso)}" fill="#A77B52"/>
    <path data-zona="reja" d="{reja}" fill="#34383B"/>'''
    sombra = f'''    <path d="M300 120 H1200 V470 H300 Z" fill="url(#tz-sombra-muro)"/>
    <rect x="300" y="455" width="900" height="26" fill="#8E8E8E" filter="url(#tz-difuso)"/>
    <path d="{ruta(*piso)}" fill="url(#tz-sombra-piso)"/>
    <g stroke="#7B7B7B" stroke-width="3" opacity="0.55" clip-path="url(#tz-recorte-piso)">{tablas}</g>
    <polygon points="560,470 790,470 900,560 520,560" fill="#8A8A8A" filter="url(#tz-muy-difuso)"/>
    <path d="{barrotes}" fill="#9A9A9A" transform="translate(12 10)" filter="url(#tz-difuso)" opacity="0.6"/>
    <path d="{baranda}" fill="url(#tz-sombra-baranda)"/>
    <path d="{baranda}" fill="#7E7E7E" transform="translate(120 150) skewX(-30)" filter="url(#tz-difuso)" opacity="0.55"/>'''
    luz = '''    <rect width="1200" height="800" fill="url(#tz-sol)"/>'''
    frente = f'''    <!-- Baranda de madera (zona pintable) -->
    <path data-zona="baranda" d="{baranda}" fill="#8B6340"/>
    <!-- Maceteros y sillas -->
    <path d="M880 560 L990 560 L975 660 L895 660 Z" fill="#B0634A"/>
    <g fill="#5E8A5E">
      <ellipse cx="905" cy="505" rx="20" ry="64" transform="rotate(-24 905 505)"/>
      <ellipse cx="936" cy="486" rx="19" ry="76"/>
      <ellipse cx="966" cy="505" rx="20" ry="64" transform="rotate(24 966 505)"/>
    </g>
    <polygon points="600,560 760,560 780,640 580,640" fill="#E7DFD0"/>
    <polygon points="600,500 760,500 760,560 600,560" fill="#DDD3C2"/>
    <line x1="590" y1="640" x2="585" y2="700" stroke="#3E3A35" stroke-width="7"/>
    <line x1="770" y1="640" x2="775" y2="700" stroke="#3E3A35" stroke-width="7"/>
    <ellipse cx="460" cy="690" rx="70" ry="16" fill="#3E3A35"/>
    <line x1="460" y1="690" x2="460" y2="620" stroke="#3E3A35" stroke-width="6"/>
    <ellipse cx="460" cy="618" rx="62" ry="14" fill="#56504A"/>'''
    defs += f'''
    <clipPath id="tz-recorte-piso"><path d="{ruta(*piso)}"/></clipPath>'''
    return svg("tz", "Terraza con muro de la casa, piso de madera, baranda de madera y reja metálica",
               defs, base, sombra, luz, frente)


if __name__ == "__main__":
    for nombre, funcion in (("living", living), ("dormitorio", dormitorio), ("fachada", fachada), ("terraza", terraza)):
        with open(os.path.join(CARPETA, nombre + ".svg"), "w", encoding="utf-8") as f:
            f.write(funcion())
        print("  img/ambientes/" + nombre + ".svg")
