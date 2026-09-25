#!/usr/bin/env python3
# ============================================================
#  ECOCORDI - El asistente en un Chrome real, sin interfaz (headless)
#  Uso:  python3 pruebas/prueba_navegador_asistente.py
#  Usa una base de datos TEMPORAL. Las capturas quedan en capturas/.
# ============================================================
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from navegador import Navegador, buscar_chrome  # noqa: E402
from utilidades import RAIZ, Servidor, ok, terminar, titulo  # noqa: E402

CAPTURAS = os.path.join(RAIZ, "capturas")

if not buscar_chrome():
    print("No hay Chrome instalado: se omiten las pruebas en el navegador.")
    sys.exit(0)

srv = Servidor().arrancar()
nav = Navegador(1440, 900)


def carrito():
    return nav.js("JSON.parse(localStorage.getItem('carrito_ecocordi') || '[]')")


def paso():
    return nav.texto("#asistentePaso")


def pregunta():
    return nav.texto("#asistentePregunta")


try:
    # ------------------------------------------------------------
    titulo("Accesos al asistente")
    nav.ir(srv.url + "/")
    ok(nav.existe('.asistente-cta[href="asistente.html"]') and "¿No sabes qué pintura usar?" in nav.texto(".asistente-cta"),
       "La portada tiene el botón destacado «¿No sabes qué pintura usar?»")
    nav.ir(srv.url + "/catalogo.html")
    ok(nav.existe('.catalogo-pagina__asistente[href="asistente.html"]'), "El catálogo tiene el acceso al asistente")
    nav.ir(srv.url + "/")
    nav.clic(".asistente-cta")
    nav.esperar("location.pathname === '/asistente.html' && !!document.querySelector('.eleccion')")
    ok(pregunta() == "¿Qué vas a pintar?" and paso() == "Pregunta 1 de 5", "El botón de la portada abre la primera pregunta")
    nav.captura(os.path.join(CAPTURAS, "asistente-1440-paso1.png"))
    ok(nav.js("document.getElementById('asistenteAtras').offsetParent === null"), "En la primera pregunta no hay botón «Atrás»")

    # ------------------------------------------------------------
    titulo("Recorrido completo con el teclado y el ratón")
    # Teclado: Tab hasta la opción «Madera» y Enter
    nav.js("document.body.focus()")
    for _ in range(40):
        nav.tecla("Tab")
        if nav.js("document.activeElement.dataset.valor === 'madera'"):
            break
    ok(nav.js("document.activeElement.dataset.valor === 'madera'"), "Con Tab se llega a la opción «Madera»", nav.enfocado())
    ok(nav.js("getComputedStyle(document.activeElement).outlineStyle !== 'none'"), "La opción enfocada muestra el anillo de foco")
    nav.tecla("Enter")
    nav.esperar("location.search.includes('superficie=madera')")
    ok(pregunta() == "¿Dónde está?" and paso() == "Pregunta 2 de 5", "Enter elige la opción y pasa a «¿Dónde está?»", paso())
    ok(nav.js("document.activeElement.id === 'asistentePregunta'"), "El foco pasa al título de la nueva pregunta", nav.enfocado())
    nav.clic('[data-valor="exterior"]')
    nav.esperar("location.search.includes('uso=exterior')")
    ok("humedad o sol" in pregunta(), "Afuera → pregunta por humedad o sol", pregunta())
    nav.clic('[data-valor="sol"]')
    nav.esperar("location.search.includes('condicion=sol')")
    ok(pregunta() == "¿Qué acabado prefieres?" and nav.js("document.querySelectorAll('.eleccion').length") == 4,
       "Acabado: 4 opciones (con «No sé»)")
    ok("Sin brillo" in nav.texto('[data-valor="mate"]'), "Cada acabado trae una explicación corta")
    nav.clic('[data-valor="mate"]')
    nav.esperar("!!document.getElementById('asistMetros')")
    ok(paso() == "Pregunta 5 de 5", "Última pregunta: los m²", paso())

    # «No sé»: el mini cálculo (4 muros de 4 × 2,5 m, 1 puerta y 2 ventanas = 40 − 1,8 − 3 = 35,2 m²)
    nav.clic(".mini-calculo__abrir")
    for medida, valor in (("largo", "4"), ("alto", "2.5"), ("muros", "4"), ("puertas", "1"), ("ventanas", "2")):
        nav.js(f"""(() => {{ const c = document.querySelector('[data-medida="{medida}"]'); c.focus(); c.select(); }})()""")
        nav.escribir(valor)
    ok(nav.texto("#miniTotal") == "35,2 m²", "Mini cálculo: 4 × 2,5 × 4 − 1 puerta − 2 ventanas = 35,2 m²", nav.texto("#miniTotal"))
    nav.clic("#usarMedida")
    ok(nav.js("document.getElementById('asistMetros').value") == "35.2", "«Usar esta medida» llena los m²")
    # Escribimos 40 a mano y enviamos con Enter
    nav.js("(() => { const c = document.getElementById('asistMetros'); c.focus(); c.select(); })()")
    nav.escribir("40")
    nav.tecla("Enter")
    nav.esperar("!!document.querySelector('.recomendacion--principal')", mensaje="No apareció el resultado")
    ok("m2=40" in nav.url() and paso() == "Tu resultado", "Resultado con todas las respuestas en la dirección", nav.url())
    principal = nav.texto(".recomendacion--principal")
    ok("Protección de Madera" in principal and "Te recomendamos" in principal, "Recomienda Protección de Madera")
    ok("sol directo" in principal, "Muestra los motivos (sol directo)")
    ok("8 L" in principal and "3 × galón" in principal and "$56.970" in principal,
       "40 m² × 2 manos ÷ 10 m²/L = 8 L → 3 galones = $56.970")
    ok("Ficha técnica de ejemplo" in principal, "Avisa que la ficha técnica es de ejemplo")
    ok(nav.existe('.recomendacion__acciones a[href^="catalogo.html?q="]'), "Enlace «Ver en el catálogo»")
    nav.captura(os.path.join(CAPTURAS, "asistente-1440-resultado.png"), pagina_completa=True)

    # ------------------------------------------------------------
    titulo("Botón Atrás, historial y enlace compartido")
    resultado = nav.url()
    nav.clic("#asistenteAtras")
    nav.esperar("!!document.getElementById('asistMetros')")
    ok("m2=" not in nav.url() and paso() == "Pregunta 5 de 5", "«Atrás» vuelve a la pregunta de los m²", nav.url())
    nav.clic("#asistenteAtras")
    nav.esperar("location.search.indexOf('acabado') === -1")
    ok(pregunta() == "¿Qué acabado prefieres?", "Otra vez «Atrás» → acabado")
    nav.js("history.forward()")
    nav.esperar("!!document.getElementById('asistMetros')")
    nav.js("history.forward()")
    nav.esperar("!!document.querySelector('.recomendacion--principal')")
    ok(nav.url() == resultado, "«Adelante» del navegador vuelve al resultado")

    # Enlace compartido: se abre directo en el resultado (recarga completa)
    nav.ir(resultado)
    nav.esperar("!!document.querySelector('.recomendacion--principal')")
    ok("Protección de Madera" in nav.texto(".recomendacion--principal"), "Al abrir el enlace compartido se ve el mismo resultado")
    nav.recargar()
    nav.esperar("!!document.querySelector('.recomendacion--principal')")
    ok(paso() == "Tu resultado", "Recargar la página no pierde nada")
    nav.clic("#asistenteAtras")
    nav.esperar("!!document.getElementById('asistMetros')")
    ok("m2=" not in nav.url() and "acabado=mate" in nav.url(), "Desde un enlace compartido, «Atrás» quita la última respuesta", nav.url())
    nav.ir(srv.url + "/asistente.html?superficie=lava&uso=exterior")
    nav.esperar("!!document.querySelector('.eleccion')")
    ok(pregunta() == "¿Qué vas a pintar?", "Un valor inventado en la dirección se ignora (vuelve a preguntar)")
    nav.ir(srv.url + "/asistente.html?superficie=techo")
    nav.esperar("!!document.querySelector('.eleccion')")
    ok("humedad o sol" in pregunta() and paso() == "Pregunta 2 de 4", "Techo ya es exterior: se salta «¿Dónde está?»", paso())

    # ------------------------------------------------------------
    titulo("Agregar todo al carrito")
    nav.ir(resultado)
    nav.esperar("!!document.querySelector('[data-agregar=\"0\"]')")
    nav.clic('[data-agregar="0"]')
    nav.esperar("document.getElementById('carrito').classList.contains('abierto')")
    items = carrito()
    ok(len(items) == 1 and items[0]["nombre"] == "Protección de Madera" and items[0]["cantidad"] == 3,
       "El carrito tiene 3 galones de Protección de Madera", items)
    ok(nav.texto("#contadorCarrito") == "3" and "56.970" in nav.texto("#carritoTotal"), "El contador y el subtotal se actualizan")
    ok("Agregado" in nav.texto('[data-agregar="0"]'), "El botón confirma «Agregado al carrito»")
    nav.tecla("Escape")
    # Con esos 3 galones en el carrito, el resultado ya no los vuelve a ofrecer más allá del stock
    nav.recargar()
    nav.esperar("!!document.querySelector('.recomendacion--principal')")
    ok("3 × galón" in nav.texto(".recomendacion--principal"), "Con stock suficiente, vuelve a sugerir 3 galones")
    nav.ir(srv.url + "/pedido.html")
    nav.esperar("document.querySelectorAll('.pedido__item').length > 0")
    ok("Protección de Madera" in nav.texto("#resumenItems"), "El carrito llega al checkout (pedido.html)")
    nav.js("localStorage.clear()")

    # ------------------------------------------------------------
    titulo("Sin candidatos")
    admin = srv.admin()
    _, productos = admin.pedir("GET", "/api/productos")
    proteccion = next(p for p in productos if p["nombre"] == "Protección de Madera")
    admin.pedir("PATCH", f"/api/admin/formatos/{proteccion['formatos'][0]['id']}", {"stock": 0})
    nav.ir(srv.url + "/asistente.html?superficie=madera&uso=exterior&condicion=normal&acabado=mate&m2=no")
    nav.esperar("document.getElementById('asistentePregunta').innerText.includes('esa pintura')")
    ok("sucursal" in nav.texto("#asistentePantalla") and nav.existe('a[href="index.html#sucursales"]'),
       "Mensaje amable con enlace a las sucursales")
    admin.pedir("PATCH", f"/api/admin/formatos/{proteccion['formatos'][0]['id']}", {"stock": 20})

    # ------------------------------------------------------------
    titulo("Calculadora del catálogo (misma lógica del servidor)")
    nav.ir(srv.url + "/catalogo.html")
    nav.esperar("document.querySelectorAll('.producto').length > 0")
    interior = next(p for p in productos if p["nombre"] == "Pinturas para Interior")
    nav.js(f"""(() => {{
        const s = document.getElementById('calcSuperficie'); s.value = 'interior'; s.dispatchEvent(new Event('change'));
        document.getElementById('calcProducto').value = '{interior["id"]}';
        document.getElementById('calcMetros').value = '35';
    }})()""")
    nav.clic(".calculadora__boton")
    nav.esperar("document.getElementById('calcResultado').innerText.includes('Necesitas')")
    calc = nav.texto("#calcResultado")
    ok("5,9 L" in calc and "$31.980" in calc and "valor de ejemplo" in calc,
       "35 m² de Pinturas para Interior → 5,9 L, 2 galones, $31.980 (con nota de ejemplo)", calc)
    ok(any("/api/calcular?" in p["url"] for p in nav.peticiones), "La calculadora le pregunta al servidor (/api/calcular)")

    # ------------------------------------------------------------
    titulo("Celular de 360 px con toques")
    nav.tamano(360, 740, movil=True, escala=2)
    nav.ir(srv.url + "/asistente.html")
    nav.esperar("!!document.querySelector('.eleccion')")
    ok(nav.js("document.documentElement.scrollWidth <= 360"), "Sin desplazamiento horizontal en 360 px",
       nav.js("document.documentElement.scrollWidth"))
    nav.captura(os.path.join(CAPTURAS, "asistente-360-paso1.png"), pagina_completa=True)
    nav.toque('[data-valor="interior"]')
    nav.esperar("location.search.includes('superficie=interior')")
    ok("humedad o sol" in pregunta(), "Un toque elige «Interior» (y se salta «¿Dónde está?»)")
    ok(nav.js("Math.min(...[...document.querySelectorAll('.eleccion')].map(e => e.getBoundingClientRect().height)) >= 44"),
       "Las opciones miden al menos 44 px de alto (fáciles de tocar)")
    nav.toque('[data-valor="humedad"]')
    nav.esperar("location.search.includes('condicion=humedad')")
    nav.captura(os.path.join(CAPTURAS, "asistente-360-acabado.png"), pagina_completa=True)
    nav.toque('[data-valor="no_se"]')
    nav.esperar("!!document.getElementById('asistMetros')")
    nav.toque("#asistMetros")
    nav.escribir("25")
    nav.toque(".metros__enviar")
    nav.esperar("!!document.querySelector('.recomendacion--principal')")
    ok(nav.js("document.documentElement.scrollWidth <= 360"), "El resultado tampoco se desborda en 360 px")
    ok("Productos Especiales" in nav.texto(".recomendacion--principal"), "Interior con humedad y «No sé» → Productos Especiales")
    nav.captura(os.path.join(CAPTURAS, "asistente-360-resultado.png"), pagina_completa=True)

    # ------------------------------------------------------------
    titulo("Consola, CSP y movimiento reducido")
    nav.cmd("Emulation.setEmulatedMedia", features=[{"name": "prefers-reduced-motion", "value": "reduce"}])
    nav.recargar()
    nav.esperar("!!document.querySelector('.recomendacion--principal')")
    duracion = nav.js("getComputedStyle(document.querySelector('.recomendacion')).animationDuration")
    ok(duracion in ("1e-05s", "0.00001s", "0s"), "Con «reducir movimiento» no hay animación de entrada", duracion)
    ok(nav.violaciones_csp() == [], "Ninguna violación de la CSP", nav.violaciones_csp())
    ok(nav.errores == [], "Ningún error en la consola", nav.errores)
finally:
    nav.cerrar()
    srv.borrar()

print("\nCapturas en: " + CAPTURAS)
terminar()
