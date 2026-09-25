#!/usr/bin/env python3
# ============================================================
#  ECOCORDI - El visualizador de color en un Chrome real, sin interfaz
#  Uso:  python3 pruebas/prueba_navegador_visualizador.py
#  Usa una base de datos TEMPORAL. Las capturas quedan en capturas/.
# ============================================================
import glob
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import foto_prueba  # noqa: E402
from navegador import Navegador, buscar_chrome  # noqa: E402
from utilidades import RAIZ, Servidor, ok, terminar, titulo  # noqa: E402

CAPTURAS = os.path.join(RAIZ, "capturas")

if not buscar_chrome():
    print("No hay Chrome instalado: se omiten las pruebas en el navegador.")
    sys.exit(0)

carpeta = tempfile.mkdtemp(prefix="ecocordi-foto-")
FOTO = foto_prueba.crear(os.path.join(carpeta, "mi-living.png"))
ESCALA = 1600 / foto_prueba.ANCHO  # la foto se achica a 1600 px de ancho

srv = Servidor().arrancar()
nav = Navegador(1440, 900)
nav.cmd("Browser.grantPermissions", permissions=["clipboardReadWrite", "clipboardSanitizedWrite"])
_, colores = srv.cliente().pedir("GET", "/api/colores")
por_nombre = {c["nombre"]: c for c in colores["colores"]}
_, productos = srv.cliente().pedir("GET", "/api/productos")
prod = {p["nombre"]: p for p in productos}


def carrito():
    return nav.js("JSON.parse(localStorage.getItem('carrito_ecocordi') || '[]')")


def relleno(zona):
    """El color (rgb) con que se ve pintada una zona del dibujo A."""
    return nav.js(f"getComputedStyle(document.querySelector('#escenaA [data-zona=\"{zona}\"]')).fill")


def rgb(hex_):
    return "rgb(" + ", ".join(str(int(hex_[i:i + 2], 16)) for i in (1, 3, 5)) + ")"


def elegir_color(nombre, toque=False):
    c = por_nombre[nombre]
    nav.js("document.getElementById('buscarColor').value = ''; document.getElementById('buscarColor').dispatchEvent(new Event('input'))")
    selector = f'#paletaGrilla [data-color-id="{c["id"]}"]'
    (nav.toque if toque else nav.clic)(selector)
    return c


def descargas_png():
    return sorted(glob.glob(os.path.join(nav.descargas, "*.png")), key=os.path.getmtime)


def punto_foto(x, y):
    """Coordenadas en pantalla de un punto (x, y) de la foto ORIGINAL."""
    return nav.js(f"""(() => {{ const c = document.getElementById('fotoMascara');
        c.scrollIntoView({{block: 'center', behavior: 'instant'}});
        const r = c.getBoundingClientRect();
        return [r.left + {x * ESCALA} * r.width / c.width, r.top + {y * ESCALA} * r.height / c.height]; }})()""")


def mascara_en(zona, puntos):
    """Valor de la máscara (0-255) de una zona de la foto en varios puntos de la foto original."""
    return nav.js(f"""{json.dumps(puntos)}.map(([x, y]) =>
        foto.zonas[{zona}].mascara[Math.floor(y * {ESCALA}) * foto.ancho + Math.floor(x * {ESCALA})])""")


def pixel_foto(x, y):
    return nav.js(f"""Array.from(document.getElementById('fotoLienzo').getContext('2d')
        .getImageData({int(x * ESCALA)}, {int(y * ESCALA)}, 1, 1).data).slice(0, 3)""")


def esperar_foto_libre():
    nav.esperar("!foto.ocupado", 20)
    time.sleep(0.3)


# Puntos del muro (con luz, sombra y la mancha de sol), sin tocar el sofá ni la puerta
MURO = [(x, y) for x in (100, 400, 700, 1000, 1150, 1650) for y in (80, 350, 650)] + [(100, 1000), (1000, 1000), (1700, 1000)]
PUERTA = [(1300, 400), (1385, 700), (1480, 1000)]
SOFA = [(400, 900), (700, 1000)]
PISO = [(200, 1200), (1000, 1300)]

try:
    # ------------------------------------------------------------
    titulo("Accesos al visualizador")
    nav.ir(srv.url + "/")
    ok(nav.existe('.asistente-cta--colores[href="visualizador.html"]'), "La portada tiene «Prueba colores en tu casa»")
    nav.ir(srv.url + "/catalogo.html")
    nav.esperar("document.querySelectorAll('.producto').length > 0")
    enlaces = nav.js("[...document.querySelectorAll('.producto__colores')].map(a => a.getAttribute('href'))")
    ok(len(enlaces) == 8 and f"visualizador.html?producto={prod['Protección de Madera']['id']}" in enlaces,
       "Cada producto con colores tiene «Ver colores»", enlaces)
    nav.ir(srv.url + "/asistente.html?superficie=interior&condicion=normal&acabado=mate&m2=no")
    nav.esperar("!!document.querySelector('.recomendacion--principal')")
    ok("Ver en el visualizador" in nav.texto(".recomendacion--principal"), "El resultado del asistente tiene «Ver en el visualizador»")

    # ------------------------------------------------------------
    titulo("Modo A: los 4 ambientes")
    nav.ir(srv.url + "/visualizador.html")
    nav.esperar("document.querySelectorAll('#paletaGrilla .muestra').length === 40 && !!document.querySelector('#escenaA svg')")
    ok(nav.texto(".aviso-referencial") == "Los colores en pantalla son referenciales; pide una muestra en sucursal.",
       "Aviso fijo: colores referenciales")
    esperados = {"living": ["muro", "acento", "puerta"], "dormitorio": ["acento", "muro", "puerta"],
                 "fachada": ["fachada", "acento", "puerta", "reja"], "terraza": ["muro", "piso", "baranda", "reja"]}
    nombres_color = ["Lago Villarrica", "Araucaria", "Café Raulí", "Carbón de Espino"]
    for ambiente, zonas in esperados.items():
        nav.clic(f'[data-ambiente="{ambiente}"]')
        nav.esperar(f"document.querySelector('[data-ambiente=\"{ambiente}\"]').getAttribute('aria-checked') === 'true'"
                    f" && !!document.querySelector('#escenaA svg title') && location.search.includes('ambiente={ambiente}')")
        en_svg = nav.js("[...new Set([...document.querySelectorAll('#escenaA [data-zona]')].map(e => e.dataset.zona))]")
        ok(sorted(en_svg) == sorted(zonas), f"{ambiente}: zonas pintables {zonas}", en_svg)
        ok(nav.js("document.querySelectorAll('#escenaA .capa-sombra, #escenaA .capa-luz').length") == 2 and
           nav.js("getComputedStyle(document.querySelector('#escenaA .capa-sombra')).mixBlendMode") == "multiply",
           f"{ambiente}: capas de sombra (multiply) y luz encima")
        bien = True
        for zona, nombre in zip(zonas, nombres_color):
            nav.clic(f'[data-zona-boton="{zona}"]')
            c = elegir_color(nombre)
            time.sleep(0.55)  # la transición del color dura 450 ms
            bien = bien and relleno(zona) == rgb(c["hex"])
        ok(bien, f"{ambiente}: cada zona toma el color elegido")
        nav.js("scrollTo(0, 0)")
        nav.captura(os.path.join(CAPTURAS, f"visualizador-1440-{ambiente}.png"))
    ok(nav.js("getComputedStyle(document.querySelector('#escenaA [data-zona]')).transitionDuration") == "0.45s",
       "El cambio de color es una transición suave (450 ms)")

    # Tocar el dibujo elige la zona
    nav.clic('[data-ambiente="living"]')
    nav.esperar("!!document.querySelector('#escenaA svg title') && location.search.includes('ambiente=living')")
    nav.clic_en(*nav.js("""(() => { const r = document.querySelector('#escenaA [data-zona="puerta"]').getBoundingClientRect();
        return [r.left + r.width / 2, r.top + r.height / 2]; })()"""))
    ok(nav.js("document.querySelector('[data-zona-boton=\"puerta\"]').getAttribute('aria-pressed')") == "true",
       "Tocar la puerta en el dibujo la elige")

    # ------------------------------------------------------------
    titulo("Paleta: familias, buscador y últimos usados")
    nav.clic('[data-familia="verdes"]')
    ok(nav.js("document.querySelectorAll('#paletaGrilla .muestra').length") == 6, "Familia «Verdes»: 6 colores")
    nav.clic('[data-familia="todas"]')
    nav.clic("#buscarColor")
    nav.escribir("llaima")
    ok(nav.js("[...document.querySelectorAll('#paletaGrilla .muestra__nombre')].map(e => e.innerText)") == ["Nieve del Llaima"],
       "Buscar «llaima» (sin mayúscula) encuentra Nieve del Llaima")
    nav.js("{ const b = document.getElementById('buscarColor'); b.value = 'ec-t0'; b.dispatchEvent(new Event('input')) }")
    ok(nav.js("document.querySelectorAll('#paletaGrilla .muestra').length") == 5, "Buscar por código «ec-t0»: 5 colores tierra")
    nav.js("{ const b = document.getElementById('buscarColor'); b.value = 'zzz'; b.dispatchEvent(new Event('input')) }")
    ok("No encontramos" in nav.texto("#paletaContador"), "Búsqueda sin resultados avisa")
    nav.js("{ const b = document.getElementById('buscarColor'); b.value = ''; b.dispatchEvent(new Event('input')) }")
    recientes = nav.js("[...document.querySelectorAll('#paletaRecientes [data-color-id]')].map(e => +e.dataset.colorId)")
    ok(len(recientes) == 4 and recientes[0] == por_nombre["Carbón de Espino"]["id"], "«Últimos usados» con el más reciente primero", recientes)
    nav.clic('[data-zona-boton="muro"]')
    nav.clic(f'#paletaRecientes [data-color-id="{por_nombre["Araucaria"]["id"]}"]')
    time.sleep(0.5)
    ok(relleno("muro") == rgb(por_nombre["Araucaria"]["hex"]), "Un color de «Últimos usados» se aplica con un clic")
    # Teclado: flechas dentro de la grilla y Enter
    nav.js("document.querySelector('#paletaGrilla .muestra[tabindex=\"0\"]').focus()")
    antes = nav.js("document.activeElement.dataset.colorId")
    nav.tecla("ArrowRight")
    despues = nav.js("document.activeElement.dataset.colorId")
    nav.tecla("Enter")
    time.sleep(0.5)
    ok(antes != despues and relleno("muro") == rgb(next(c["hex"] for c in colores["colores"] if str(c["id"]) == despues)),
       "Con las flechas se recorre la paleta y Enter aplica el color", (antes, despues))
    ok(nav.js("document.querySelectorAll('#paletaGrilla .muestra[tabindex=\"0\"]').length") == 1,
       "Solo una muestra entra en el orden del Tab (no hay que pasar por 40)")

    # ------------------------------------------------------------
    titulo("Mis colores (favoritos)")
    salvia = elegir_color("Salvia Seca")
    nav.clic("[data-favorito]")
    ok(nav.js("JSON.parse(localStorage.getItem('colores_favoritos_ecocordi'))") == [salvia["id"]],
       "El corazón guarda el color en el navegador")
    ok(nav.js(f"!!document.querySelector('#paletaFavoritos [data-color-id=\"{salvia['id']}\"]')"), "Aparece en «Mis colores»")
    cliente = srv.cliente()
    cliente.registrar("favoritos@correo.cl")
    nav.js("""fetch('/api/login', {method: 'POST', headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({correo: 'favoritos@correo.cl', clave: 'clave-segura-1'})})""")
    nav.recargar()
    nav.esperar("document.querySelectorAll('#paletaFavoritos [data-color-id]').length === 1")
    time.sleep(0.5)
    _, en_cuenta = cliente.pedir("GET", "/api/mis-colores")
    ok(en_cuenta["colores"] == [salvia["id"]], "Al iniciar sesión, los favoritos del navegador suben a la cuenta", en_cuenta)
    araucaria = elegir_color("Araucaria")
    nav.clic("[data-favorito]")
    time.sleep(0.4)
    _, en_cuenta = cliente.pedir("GET", "/api/mis-colores")
    ok(en_cuenta["colores"] == [salvia["id"], araucaria["id"]], "Con sesión, cada favorito nuevo se guarda en la cuenta", en_cuenta)
    nav.js("fetch('/api/logout', {method: 'POST'})")

    # ------------------------------------------------------------
    titulo("Comparar dos colores")
    nav.clic('[data-zona-boton="muro"]')
    lago = elegir_color("Lago Villarrica")
    nav.clic("#btnComparar")
    nav.esperar("!document.getElementById('escenaB').classList.contains('oculto') && !!document.querySelector('#escenaB svg')")
    ok(nav.js("document.querySelectorAll('#escenaB [id$=\"-b\"]').length > 0 && !document.querySelector('#escenaB #lv-difuso')"),
       "La copia B tiene sus propios id (sus degradados no chocan con los de A)")
    rojo = elegir_color("Rojo Copihue")
    time.sleep(0.5)
    fill_b = nav.js("getComputedStyle(document.querySelector('#escenaB [data-zona=\"muro\"]')).fill")
    ok(relleno("muro") == rgb(lago["hex"]) and fill_b == rgb(rojo["hex"]), "A queda en Lago Villarrica y B en Rojo Copihue", (relleno("muro"), fill_b))
    ok(nav.texto("#etiquetaA") == "A · Lago Villarrica" and nav.texto("#etiquetaB") == "B · Rojo Copihue", "Etiquetas A y B")
    nav.js("{ const d = document.getElementById('deslizador'); d.focus() }")
    for _ in range(10):
        nav.tecla("ArrowLeft")
    ok(nav.js("document.getElementById('escenaB').style.clipPath") == "inset(0px 0px 0px 40%)" and
       nav.js("document.getElementById('divisor').style.left") == "40%",
       "El deslizador (con teclado) mueve la división al 40 %", nav.js("document.getElementById('escenaB').style.clipPath"))
    nav.js("scrollTo(0, 0)")
    nav.captura(os.path.join(CAPTURAS, "visualizador-1440-comparar.png"))

    # ------------------------------------------------------------
    titulo("Descargar imagen y compartir (modo A)")
    antes = len(descargas_png())
    nav.clic("#modoAmbientes [data-descargar]", 0.2)
    nav.esperar(f"true", 1)
    limite = time.time() + 10
    while len(descargas_png()) == antes and time.time() < limite:
        time.sleep(0.2)
    archivo = descargas_png()[-1] if len(descargas_png()) > antes else None
    ok(archivo and os.path.basename(archivo) == "ecocordi-living.png" and foto_prueba.medidas_png(archivo) == (1800, 1200),
       "Descarga un PNG de 1800 × 1200 generado en el navegador", archivo)
    # Las sombras siguen en la imagen descargada: el muro junto al cielo raso sale más oscuro que al centro
    sombra = nav.js("""(async () => {
        const img = await svgComoImagen(document.querySelector('#escenaA svg'), 1200, 800);
        const c = document.createElement('canvas'); c.width = 1200; c.height = 800;
        const ctx = c.getContext('2d'); ctx.drawImage(img, 0, 0);
        const luz = (x, y) => { const d = ctx.getImageData(x, y, 1, 1).data; return d[0] + d[1] + d[2]; };
        return [luz(800, 100), luz(800, 400)]; })()""")
    ok(sombra[0] < sombra[1] * 0.9, "En la imagen descargada se conservan las sombras (multiply)", sombra)
    nav.clic("#btnComparar")  # salir de comparar
    nav.clic("#modoAmbientes [data-compartir]", 0.4)
    enlace = nav.js("navigator.clipboard.readText()")
    ok("modo=ambiente&ambiente=living&zonas=" in enlace and f"muro:{lago['id']}" in enlace,
       "«Compartir» copia el enlace con el ambiente y los colores", enlace)
    nav.ir(enlace)
    nav.esperar("!!document.querySelector('#escenaA svg title')")
    time.sleep(0.6)
    ok(relleno("muro") == rgb(lago["hex"]), "Al abrir el enlace compartido, el ambiente se ve con esos colores")

    # ------------------------------------------------------------
    titulo("Agregar al carrito con el color y «¿Cuánto necesito?»")
    nav.js("localStorage.removeItem('carrito_ecocordi')")
    nav.recargar()
    nav.esperar("!!document.querySelector('#escenaA svg title') && !!document.getElementById('compraProducto')")
    nav.clic('[data-zona-boton="muro"]')
    lago = elegir_color("Lago Villarrica")
    nav.esperar("!!document.getElementById('compraProducto')")
    opciones = nav.js("[...document.getElementById('compraProducto').options].map(o => o.text)")
    ok(opciones[0] == "Pinturas para Interior", "Primero sugiere una pintura para la superficie de la zona (muro interior)", opciones)
    nav.clic("#formComprarColor button[type=submit]", 0.6)
    nav.esperar("document.getElementById('carrito').classList.contains('abierto')")
    items = carrito()
    ok(len(items) == 1 and items[0]["color_id"] == lago["id"] and items[0]["nombre"] == "Pinturas para Interior",
       "Se agrega al carrito con el color", items)
    ok("Lago Villarrica" in nav.texto("#carritoItems") and nav.js("!!document.querySelector('#carritoItems .muestra-color').style.backgroundColor"),
       "El carrito muestra el nombre y la muestra del color")
    nav.tecla("Escape")
    time.sleep(0.5)  # el fondo oscuro del carrito se desvanece
    cuanto = nav.js("document.getElementById('enlaceCuanto').getAttribute('href')")
    ok(cuanto == f"asistente.html?superficie=interior&producto={prod['Pinturas para Interior']['id']}&color={lago['id']}"
       or cuanto == f"asistente.html?superficie=interior&uso=interior&producto={prod['Pinturas para Interior']['id']}&color={lago['id']}",
       "«¿Cuánto necesito?» lleva la superficie, la pintura y el color", cuanto)
    nav.clic("#enlaceCuanto")
    nav.esperar("location.pathname === '/asistente.html' && !!document.getElementById('asistMetros')")
    ok("Pinturas para Interior" in nav.texto("#productoElegido"), "El asistente abre directo en los m² con la pintura elegida")
    nav.js("document.getElementById('asistMetros').focus()")
    nav.escribir("30")
    nav.tecla("Enter")
    nav.esperar("!!document.querySelector('[data-agregar=\"0\"]')")
    ok("Lago Villarrica" in nav.texto(".asistente__resumen") and "se agrega al carrito en este color" in nav.texto(".recomendacion--principal"),
       "El resultado muestra el color elegido")
    nav.clic('[data-agregar="0"]', 0.6)
    items = carrito()
    ok(len(items) == 1 and items[0]["color_id"] == lago["id"] and items[0]["cantidad"] == 3,
       "«Agregar todo al carrito» suma los galones en ese color (30 m² × 2 ÷ 12 = 5 L → 2 galones; 1 + 2 = 3)", items)
    nav.ir(srv.url + "/pedido.html")
    nav.esperar("document.querySelectorAll('.pedido__item').length > 0")
    ok("Lago Villarrica" in nav.texto("#resumenItems"), "El checkout muestra el color")
    nav.js("localStorage.removeItem('carrito_ecocordi')")

    # ------------------------------------------------------------
    titulo("Modo B: tu propia foto")
    nav.ir(srv.url + "/visualizador.html")
    nav.esperar("document.querySelectorAll('#paletaGrilla .muestra').length === 40")
    peticiones_antes = len(nav.peticiones)
    nav.clic("#tabFoto")
    ok(nav.js("location.search.includes('modo=foto')") and "no sale de tu dispositivo" in nav.texto("#fotoSubir"),
       "Pestaña «Tu propia foto» con el aviso de privacidad")
    ok(nav.js("document.getElementById('inputCamara').getAttribute('capture')") == "environment",
       "Botón «Tomar foto» con la cámara del celular (capture)")
    nav.subir_archivo("#inputFoto", FOTO)
    nav.esperar("!document.getElementById('fotoEditor').classList.contains('oculto')", 15)
    ok(nav.js("[foto.ancho, foto.alto]") == [1600, 1200], "La foto de 1800 × 1350 se achica a 1600 × 1200",
       nav.js("[foto.ancho, foto.alto]"))
    # Relleno por inundación: tocar el muro
    nav.clic_en(*punto_foto(150, 700))
    esperar_foto_libre()
    en_muro = mascara_en(0, MURO)
    ok(sum(1 for v in en_muro if v == 255) >= len(MURO) - 1, "Tocar el muro marca el muro (con luz y sombra)", en_muro)
    ok(max(mascara_en(0, PUERTA + SOFA + PISO)) == 0, "…pero no la puerta, el sofá ni el piso", mascara_en(0, PUERTA + SOFA + PISO))
    nav.js("scrollTo({top: document.getElementById('fotoEditor').getBoundingClientRect().top + scrollY - 90, behavior: 'instant'})")
    nav.captura(os.path.join(CAPTURAS, "visualizador-1440-foto-seleccion.png"))
    # Color para la zona 1
    menta = elegir_color("Helecho Nativo")
    esperar_foto_libre()
    claro, oscuro = pixel_foto(150, 100), pixel_foto(1700, 1000)
    original_claro = foto_prueba.color(150, 100)
    original_oscuro = foto_prueba.color(1700, 1000)
    verde = lambda p: p[1] > p[0] and p[1] > p[2]
    ok(verde(claro) and verde(oscuro), "El muro queda verde", (claro, oscuro))
    relacion_nueva = sum(oscuro) / sum(claro)
    relacion_original = sum(original_oscuro) / sum(original_claro)
    ok(abs(relacion_nueva - relacion_original) < 0.1,
       "Se conservan la luz y la sombra: la esquina oscura sigue igual de más oscura", (round(relacion_original, 2), round(relacion_nueva, 2)))
    ok(pixel_foto(1385, 700) == [122, 82, 52] or max(abs(a - b) for a, b in zip(pixel_foto(1385, 700), (122, 82, 52))) <= 6,
       "La puerta no cambia", pixel_foto(1385, 700))
    # Pincel: sumar la puerta a la zona 1, luego goma y deshacer
    nav.clic('[data-herramienta="pincel"]')
    nav.arrastrar([punto_foto(1300, y) for y in range(420, 900, 40)])
    esperar_foto_libre()
    ok(mascara_en(0, [(1300, 600)])[0] == 255, "El pincel agrega a la zona lo que se pinta a mano")
    nav.clic('[data-herramienta="goma"]')
    nav.arrastrar([punto_foto(x, 350) for x in range(350, 700, 30)])
    esperar_foto_libre()
    ok(mascara_en(0, [(500, 350)])[0] == 0, "La goma quita de la zona")
    nav.clic("#btnDeshacer")
    esperar_foto_libre()
    ok(mascara_en(0, [(500, 350)])[0] == 255, "Deshacer devuelve lo que borró la goma")
    nav.clic("#btnDeshacer")
    esperar_foto_libre()
    ok(mascara_en(0, [(1300, 600)])[0] == 0, "Deshacer otra vez quita el trazo del pincel")
    # Zona 2: la puerta, con otro color
    nav.clic("[data-nueva-zona]")
    nav.clic_en(*punto_foto(1385, 700))
    esperar_foto_libre()
    ok(min(mascara_en(1, PUERTA)) == 255 and max(mascara_en(1, MURO + PISO + SOFA)) == 0,
       "Zona 2: tocar la puerta marca solo la puerta (no el muro, el piso ni el sofá)", mascara_en(1, PISO))
    rojo = elegir_color("Rojo Copihue")
    esperar_foto_libre()
    puerta, muro = pixel_foto(1385, 700), pixel_foto(150, 100)
    ok(puerta[0] > puerta[1] + 30 and verde(muro), "Dos zonas con colores distintos: muro verde y puerta roja", (muro, puerta))
    ok(nav.js("location.search") == f"?modo=foto&colores={menta['id']},{rojo['id']}", "El enlace guarda los colores (no la foto)",
       nav.js("location.search"))
    nav.js("document.getElementById('verSeleccion').checked = false; dibujarMascara()")
    nav.js("scrollTo({top: document.getElementById('fotoEditor').getBoundingClientRect().top + scrollY - 90, behavior: 'instant'})")
    nav.captura(os.path.join(CAPTURAS, "visualizador-1440-foto.png"))
    antes = len(descargas_png())
    nav.clic("#fotoEditor [data-descargar]")
    limite = time.time() + 10
    while len(descargas_png()) == antes and time.time() < limite:
        time.sleep(0.2)
    archivo = descargas_png()[-1] if len(descargas_png()) > antes else None
    ok(archivo and os.path.basename(archivo) == "ecocordi-mi-foto.png" and foto_prueba.medidas_png(archivo) == (1600, 1200),
       "Descarga la foto pintada como PNG (1600 × 1200)", archivo)
    # Agregar al carrito con el color desde el modo foto
    nav.clic("#formComprarColor button[type=submit]", 0.6)
    nav.esperar("JSON.parse(localStorage.getItem('carrito_ecocordi') || '[]').length === 1")
    ok(carrito()[0]["color_id"] == rojo["id"], "Desde la foto también se agrega al carrito con el color")
    nav.tecla("Escape")
    time.sleep(0.5)
    # Privacidad: ninguna petición envió la foto
    despues = nav.peticiones[peticiones_antes:]
    enviados = [p for p in despues if p["metodo"] != "GET"]
    ok(all(p["bytes_enviados"] < 2000 for p in enviados) and all(p["url"].startswith(srv.url) for p in despues),
       "Ninguna petición subió la foto (solo pedidos chicos a la tienda)",
       [(p["metodo"], p["url"][-40:], p["bytes_enviados"]) for p in enviados])
    ok(sum(p["bytes_enviados"] for p in despues) < 5000, "En total se enviaron menos de 5 KB (la foto pesa 2 MB)",
       sum(p["bytes_enviados"] for p in despues))

    # Archivos no permitidos
    nav.clic("#btnOtraFoto")
    texto_falso = os.path.join(carpeta, "virus.png.txt")
    with open(texto_falso, "w") as f:
        f.write("no soy una foto")
    nav.subir_archivo("#inputFoto", texto_falso)
    nav.esperar("document.getElementById('fotoError').innerText.length > 0")
    ok("JPG, PNG o WebP" in nav.texto("#fotoError"), "Un archivo que no es foto se rechaza con un mensaje")
    grande = os.path.join(carpeta, "enorme.png")
    with open(FOTO, "rb") as f:
        datos = f.read()
    with open(grande, "wb") as f:
        f.write(datos + b"\0" * (10 * 1024 * 1024))  # PNG válido con 10 MB extra al final
    nav.subir_archivo("#inputFoto", grande)
    nav.esperar("document.getElementById('fotoError').innerText.includes('10 MB')")
    ok(True, "Una foto de más de 10 MB se rechaza")

    # ------------------------------------------------------------
    titulo("Celular de 360 px con toques")
    nav.tamano(360, 740, movil=True, escala=2)
    nav.ir(srv.url + "/visualizador.html?modo=ambiente&ambiente=fachada")
    nav.esperar("!!document.querySelector('#escenaA svg title') && document.querySelectorAll('#paletaGrilla .muestra').length === 40")
    ok(nav.js("document.documentElement.scrollWidth <= 360"), "Sin desplazamiento horizontal en 360 px", nav.js("document.documentElement.scrollWidth"))
    ok(nav.js("document.querySelector('.visualizador__panel').parentElement.id") == "modoAmbientes",
       "En el celular la paleta queda debajo del dibujo")
    nav.toque('[data-zona-boton="reja"]')
    c = elegir_color("Azul Añil", toque=True)
    time.sleep(0.6)
    ok(relleno("reja") == rgb(c["hex"]), "Tocar una zona y un color pinta la reja")
    ok(nav.js("getComputedStyle(document.querySelector('[data-zona-boton=\"reja\"] .zona__muestra')).backgroundImage") == "none",
       "El círculo de la zona muestra su color (sin el rayado de «sin pintar»)")
    ok(nav.js("document.getElementById('escena').getBoundingClientRect().top >= 0 && document.getElementById('escena').getBoundingClientRect().top < 140"),
       "Mientras se recorre la paleta, el dibujo sigue a la vista (fijo arriba)",
       nav.js("document.getElementById('escena').getBoundingClientRect().top"))
    nav.js("scrollTo(0, 0)")
    nav.captura(os.path.join(CAPTURAS, "visualizador-360-ambiente.png"))
    nav.captura(os.path.join(CAPTURAS, "visualizador-360-ambiente-completo.png"), pagina_completa=True)
    nav.toque("#tabFoto")
    nav.subir_archivo("#inputFoto", FOTO)
    nav.esperar("!document.getElementById('fotoEditor').classList.contains('oculto')", 15)
    ok(nav.js("document.documentElement.scrollWidth <= 360"), "Modo foto sin desplazamiento horizontal en 360 px")
    nav.toque_en(*punto_foto(150, 700))
    esperar_foto_libre()
    ok(sum(1 for v in mascara_en(0, MURO) if v == 255) >= len(MURO) - 1, "Un toque con el dedo rellena el muro")
    elegir_color("Durazno de Huerto", toque=True)
    esperar_foto_libre()
    nav.js("scrollTo(0, 0)")
    nav.captura(os.path.join(CAPTURAS, "visualizador-360-foto.png"), pagina_completa=True)

    # ------------------------------------------------------------
    titulo("Consola y CSP")
    ok(nav.violaciones_csp() == [], "Ninguna violación de la CSP", nav.violaciones_csp())
    ok(nav.errores == [], "Ningún error en la consola", nav.errores)
finally:
    nav.cerrar()
    srv.borrar()

print("\nCapturas en: " + CAPTURAS)
terminar()
