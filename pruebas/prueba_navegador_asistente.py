#!/usr/bin/env python3
# ============================================================
#  ECOCORDI - El asistente (burbuja de chat) en un Chrome real, sin interfaz
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

srv = Servidor(entorno={"WHATSAPP_NUMERO": "56912345678"}).arrancar()
nav = Navegador(1440, 900)


def carrito():
    return nav.js("JSON.parse(localStorage.getItem('carrito_ecocordi') || '[]')")


def ultimo_bot():
    """Texto del último mensaje del asistente (sin contar los puntitos de «escribiendo»)."""
    return nav.js("""(() => {
        const m = [...document.querySelectorAll('.mensaje--bot:not(.mensaje--escribiendo)')];
        return m.length ? m[m.length - 1].innerText : '';
    })()""")


def esperar_pregunta(texto):
    """Espera a que el asistente haga esa pregunta y muestre cómo responderla."""
    nav.esperar(f"""(() => {{
        const m = [...document.querySelectorAll('.mensaje--bot:not(.mensaje--escribiendo)')];
        return m.length && m[m.length - 1].innerText.includes({json.dumps(texto)})
            && document.getElementById('chatEntrada').children.length > 0;
    }})()""", mensaje="No apareció la pregunta: " + texto)


def respuestas_de_la_persona():
    return nav.js("[...document.querySelectorAll('.mensaje--yo')].map(m => m.innerText)")


def chat_abierto():
    return nav.js("document.getElementById('asistenteChat').classList.contains('abierto')")


def esperar_resultado():
    nav.esperar("!!document.querySelector('.sugerencia--principal')", mensaje="No apareció el resultado")


try:
    # ------------------------------------------------------------
    titulo("La burbuja y los accesos")
    nav.ir(srv.url + "/")
    nav.esperar("!!document.getElementById('asistenteBurbuja')")
    ok(nav.texto("#asistenteBurbuja") == "Asistente", "Hay una burbuja flotante que dice «Asistente»")
    ok(nav.js("getComputedStyle(document.getElementById('asistenteBurbuja')).position") == "fixed",
       "La burbuja queda fija en la pantalla al bajar")
    ok(not chat_abierto() and nav.js("document.getElementById('asistenteBurbuja').getAttribute('aria-expanded')") == "false",
       "El chat parte cerrado (aria-expanded=false)")
    ok(not nav.existe('a[href="asistente.html"]'), "Ya no hay enlaces a la página vieja asistente.html")
    codigo = nav.js("fetch('/asistente.html').then(r => r.status)")
    ok(codigo == 404, "La página asistente.html ya no existe (404)", codigo)
    # WhatsApp (hay número configurado) queda ENCIMA de la burbuja, sin taparla
    nav.esperar("!document.getElementById('btnWhatsapp').classList.contains('oculto')")
    ok(nav.js("""(() => {
        const w = document.getElementById('btnWhatsapp').getBoundingClientRect();
        const b = document.getElementById('asistenteBurbuja').getBoundingClientRect();
        return w.bottom <= b.top;
    })()"""), "El botón de WhatsApp queda encima de la burbuja, sin taparla")
    nav.captura(os.path.join(CAPTURAS, "asistente-1440-burbuja.png"))

    nav.clic("#asistenteBurbuja")
    esperar_pregunta("¿Qué vas a pintar?")
    ok(chat_abierto() and nav.js("document.getElementById('asistenteBurbuja').getAttribute('aria-expanded')") == "true",
       "Tocar la burbuja abre el chat")
    ok("Soy el asistente" in nav.texto("#chatMensajes"), "El asistente saluda y explica qué hace")
    ok(nav.js("document.querySelectorAll('#chatEntrada [data-clave=\"superficie\"]').length") == 5,
       "Primera pregunta: 5 superficies para tocar")
    ok(nav.js("document.activeElement.dataset.valor") == "madera", "El foco va a la primera opción", nav.enfocado())
    nav.captura(os.path.join(CAPTURAS, "asistente-1440-abierto.png"))
    nav.tecla("Escape")
    ok(not chat_abierto() and nav.js("document.activeElement.id") == "asistenteBurbuja",
       "Escape cierra el chat y el foco vuelve a la burbuja", nav.enfocado())

    nav.clic(".asistente-cta")
    ok(chat_abierto(), "«¿No sabes qué pintura usar?» de la portada abre el chat")
    nav.clic("#chatCerrar")
    ok(not chat_abierto(), "La X cierra el chat")
    nav.clic('.menu__link[href="#asistente"]')
    ok(chat_abierto(), "«Asistente» del menú abre el chat")
    nav.clic("#chatCerrar")
    nav.ir(srv.url + "/catalogo.html#asistente")
    nav.esperar("!!document.getElementById('asistenteChat') && document.getElementById('asistenteChat').classList.contains('abierto')")
    ok(nav.js("location.hash") == "", "Un enlace a catalogo.html#asistente abre el chat directo (y limpia la dirección)")
    nav.clic("#chatCerrar")
    nav.clic(".catalogo-pagina__asistente")
    ok(chat_abierto(), "«Usa el asistente» del catálogo abre el chat")
    nav.clic("#chatCerrar")
    nav.ir(srv.url + "/")

    # ------------------------------------------------------------
    titulo("Conversación completa con el teclado y el ratón")
    # Teclado: Tab hasta la burbuja y Enter
    nav.js("document.body.focus()")
    for _ in range(80):
        nav.tecla("Tab")
        if nav.js("document.activeElement.id === 'asistenteBurbuja'"):
            break
    ok(nav.js("document.activeElement.id") == "asistenteBurbuja", "Con Tab se llega a la burbuja", nav.enfocado())
    nav.tecla("Enter")
    esperar_pregunta("¿Qué vas a pintar?")
    # El foco ya está en «Madera»; Enter la elige
    ok(nav.js("getComputedStyle(document.activeElement).outlineStyle !== 'none'"), "La opción enfocada muestra el anillo de foco")
    nav.tecla("Enter")
    ok(respuestas_de_la_persona() == ["Madera"], "La respuesta aparece como burbuja de la persona", respuestas_de_la_persona())
    ok(nav.existe(".mensaje--escribiendo"), "El asistente muestra «escribiendo…» antes de la siguiente pregunta")
    esperar_pregunta("¿Está adentro o afuera?")
    ok(nav.js("document.activeElement.dataset.valor") == "interior", "El foco pasa a la primera opción nueva", nav.enfocado())
    nav.clic('[data-valor="exterior"]')
    esperar_pregunta("humedad o sol")
    nav.clic('[data-valor="sol"]')
    esperar_pregunta("¿Qué acabado prefieres?")
    ok(nav.js("document.querySelectorAll('#chatEntrada [data-clave]').length") == 4, "Acabado: 4 opciones (con «No sé»)")
    ok("Sin brillo" in nav.texto('[data-valor="mate"]'), "Cada acabado trae una explicación corta")
    ok(nav.js("""(() => {
        const m = document.getElementById('chatMensajes');
        return m.scrollHeight - m.scrollTop - m.clientHeight < 2;
    })()"""), "La conversación baja sola hasta la última pregunta")
    nav.captura(os.path.join(CAPTURAS, "asistente-1440-acabado.png"))
    nav.clic('[data-valor="mate"]')
    esperar_pregunta("¿cuántos m²")
    ok(nav.js("document.activeElement.id") == "chatMetros", "En la pregunta de los m², el foco va al campo", nav.enfocado())

    # Un número inválido muestra el error sin avanzar
    nav.tecla("Enter")
    ok("mayor que 0" in nav.texto("#chatMetrosError") and nav.existe("#chatMetros[aria-invalid='true']"),
       "Sin número: avisa el error y no avanza")

    # «No sé»: el mini cálculo (4 muros de 4 × 2,5 m, 1 puerta y 2 ventanas = 40 − 1,8 − 3 = 35,2 m²)
    nav.clic("[data-medir]")
    for medida, valor in (("largo", "4"), ("alto", "2.5"), ("muros", "4"), ("puertas", "1"), ("ventanas", "2")):
        nav.js(f"""(() => {{ const c = document.querySelector('[data-medida="{medida}"]'); c.focus(); c.select(); }})()""")
        nav.escribir(valor)
    ok(nav.texto("#chatMiniTotal") == "35,2 m²", "Mini cálculo: 4 × 2,5 × 4 − 1 puerta − 2 ventanas = 35,2 m²", nav.texto("#chatMiniTotal"))
    nav.clic("[data-volver-metros]")
    ok(nav.existe("#chatMetros"), "«Volver» regresa al campo de m²")
    nav.clic("#chatMetros")
    nav.escribir("40")
    nav.tecla("Enter")
    esperar_resultado()
    ok(respuestas_de_la_persona()[-1] == "40 m²", "La persona «dice» 40 m²", respuestas_de_la_persona())
    principal = nav.texto(".sugerencia--principal")
    ok("Protección de Madera" in principal and "Te recomendamos" in principal, "Recomienda Protección de Madera")
    ok("sol directo" in principal, "Muestra los motivos (sol directo)")
    ok("8 L" in principal and "3 × galón" in principal and "$56.970" in principal,
       "40 m² × 2 manos ÷ 10 m²/L = 8 L → 3 galones = $56.970")
    ok("Ficha técnica de ejemplo" in principal, "Avisa que la ficha técnica es de ejemplo")
    ok(nav.existe('.sugerencia__catalogo[href^="catalogo.html?q="]'), "Enlace «Ver en el catálogo»")
    ok(nav.js("document.querySelector('.sugerencia--principal').getBoundingClientRect().height") > 200,
       "La tarjeta del resultado se ve completa (no queda aplastada)")
    ok("Madera" in nav.texto(".mensaje__resumen") and "40 m²" in nav.texto(".mensaje__resumen"), "Resume tus respuestas")
    nav.captura(os.path.join(CAPTURAS, "asistente-1440-resultado.png"))

    # ------------------------------------------------------------
    titulo("Cambiar la última respuesta, recordar y empezar de nuevo")
    nav.clic("[data-atras]")
    esperar_pregunta("¿cuántos m²")
    ok(respuestas_de_la_persona() == ["Madera", "Afuera", "Sol fuerte", "Mate"], "«Cambiar mi última respuesta» quita los m²",
       respuestas_de_la_persona())
    nav.clic("[data-omitir-m2]")
    esperar_resultado()
    ok("Prefiero no calcular ahora" in respuestas_de_la_persona()[-1] and nav.existe("#chatEntrada [data-ir-m2]"),
       "Sin m²: recomienda igual y ofrece «Calcular litros»")
    nav.clic("#chatEntrada [data-ir-m2]")
    esperar_pregunta("¿cuántos m²")
    ok(nav.js("document.activeElement.id") == "chatMetros", "«Calcular litros» vuelve a preguntar los m²")
    nav.escribir("40")
    nav.tecla("Enter")
    esperar_resultado()

    # Otra página: la conversación sigue ahí (sessionStorage)
    nav.ir(srv.url + "/catalogo.html")
    nav.esperar("!!document.getElementById('asistenteBurbuja')")
    ok(not chat_abierto(), "En otra página el chat parte cerrado")
    nav.clic("#asistenteBurbuja")
    esperar_resultado()
    ok(respuestas_de_la_persona() == ["Madera", "Afuera", "Sol fuerte", "Mate", "40 m²"],
       "Al abrirlo en el catálogo, la conversación sigue donde quedó", respuestas_de_la_persona())
    # Nunca se confía en lo guardado: un valor inventado se descarta
    nav.js("""sessionStorage.setItem('asistente_ecocordi', JSON.stringify({superficie: 'lava', uso: 'exterior', condicion: 'sol'}))""")
    nav.recargar()
    nav.clic("#asistenteBurbuja")
    esperar_pregunta("¿Qué vas a pintar?")
    ok(respuestas_de_la_persona() == [], "Un valor inventado en lo guardado se ignora (vuelve a preguntar)")
    nav.js("""sessionStorage.setItem('asistente_ecocordi', JSON.stringify({superficie: 'techo'}))""")
    nav.recargar()
    nav.clic("#asistenteBurbuja")
    esperar_pregunta("humedad o sol")
    ok(respuestas_de_la_persona() == ["Techo"], "Techo ya es exterior: se salta «¿Está adentro o afuera?»")
    nav.clic("#chatReiniciar")
    esperar_pregunta("¿Qué vas a pintar?")
    ok(respuestas_de_la_persona() == [] and nav.js("sessionStorage.getItem('asistente_ecocordi')") == "{}",
       "«Empezar de nuevo» borra la conversación")

    # ------------------------------------------------------------
    titulo("Agregar todo al carrito")
    nav.js("""sessionStorage.setItem('asistente_ecocordi', JSON.stringify(
        {superficie: 'madera', uso: 'exterior', condicion: 'sol', acabado: 'mate', m2: 40}))""")
    nav.recargar()
    nav.clic("#asistenteBurbuja")
    esperar_resultado()
    nav.clic('[data-agregar="0"]')
    nav.esperar("document.getElementById('carrito').classList.contains('abierto')")
    items = carrito()
    ok(len(items) == 1 and items[0]["nombre"] == "Protección de Madera" and items[0]["cantidad"] == 3,
       "El carrito tiene 3 galones de Protección de Madera", items)
    ok(nav.texto("#contadorCarrito") == "3" and "56.970" in nav.texto("#carritoTotal"), "El contador y el subtotal se actualizan")
    ok("Agregado" in nav.texto('[data-agregar="0"]'), "El botón confirma «Agregado al carrito»")
    ok(nav.js("document.getElementById('asistenteChat').inert"), "Con el carrito abierto, el chat queda inactivo (inert)")
    nav.tecla("Escape")
    ok(chat_abierto() and not nav.js("document.getElementById('asistenteChat').inert"),
       "Escape cierra solo el carrito: el chat sigue abierto")
    nav.ir(srv.url + "/pedido.html")
    nav.esperar("document.querySelectorAll('.pedido__item').length > 0")
    ok("Protección de Madera" in nav.texto("#resumenItems"), "El carrito llega al checkout (pedido.html)")
    ok(not nav.existe("#asistenteBurbuja"), "En el checkout no aparece la burbuja (sin distracciones)")
    nav.js("localStorage.clear(); sessionStorage.clear()")

    # ------------------------------------------------------------
    titulo("Sin candidatos")
    admin = srv.admin()
    _, productos = admin.pedir("GET", "/api/productos")
    proteccion = next(p for p in productos if p["nombre"] == "Protección de Madera")
    admin.pedir("PATCH", f"/api/admin/formatos/{proteccion['formatos'][0]['id']}", {"stock": 0})
    nav.ir(srv.url + "/")
    nav.js("""sessionStorage.setItem('asistente_ecocordi', JSON.stringify(
        {superficie: 'madera', uso: 'exterior', condicion: 'normal', acabado: 'mate', m2: 'no'}))""")
    nav.recargar()
    nav.clic("#asistenteBurbuja")
    nav.esperar("document.getElementById('chatMensajes').innerText.includes('esa pintura')")
    ok("sucursal" in ultimo_bot() and nav.existe('#chatMensajes a[href="index.html#sucursales"]'),
       "Mensaje amable con enlace a las sucursales")
    ok(nav.existe('#chatMensajes a[href^="https://wa.me/56912345678"]'), "Y con el WhatsApp de la empresa")
    admin.pedir("PATCH", f"/api/admin/formatos/{proteccion['formatos'][0]['id']}", {"stock": 20})
    nav.js("sessionStorage.clear()")

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
    nav.ir(srv.url + "/")
    nav.esperar("!!document.getElementById('asistenteBurbuja')")
    ok(nav.js("document.documentElement.scrollWidth <= 360"), "Sin desplazamiento horizontal en 360 px",
       nav.js("document.documentElement.scrollWidth"))
    nav.captura(os.path.join(CAPTURAS, "asistente-360-burbuja.png"))
    nav.toque("#asistenteBurbuja")
    esperar_pregunta("¿Qué vas a pintar?")
    # (se espera a que termine la animación de apertura)
    nav.esperar("""(() => {
        const c = document.getElementById('asistenteChat').getBoundingClientRect();
        return c.left === 0 && c.top === 0 && c.width === innerWidth && c.height === innerHeight;
    })()""", mensaje="En el celular, el chat no ocupó toda la pantalla")
    ok(True, "En el celular, el chat ocupa toda la pantalla")
    ok(nav.js("getComputedStyle(document.documentElement).overflow") == "hidden", "La página de atrás no se desplaza")
    nav.captura(os.path.join(CAPTURAS, "asistente-360-abierto.png"))
    nav.toque('[data-valor="interior"]')
    esperar_pregunta("humedad o sol")
    ok(respuestas_de_la_persona() == ["Interior"], "Un toque elige «Interior» (y se salta «¿Está adentro o afuera?»)")
    ok(nav.js("Math.min(...[...document.querySelectorAll('#chatEntrada button:not([data-atras])')].map(e => e.getBoundingClientRect().height)) >= 44"),
       "Las opciones miden al menos 44 px de alto (fáciles de tocar)")
    nav.toque('[data-valor="humedad"]')
    esperar_pregunta("¿Qué acabado prefieres?")
    nav.captura(os.path.join(CAPTURAS, "asistente-360-acabado.png"))
    nav.toque('[data-valor="no_se"]')
    esperar_pregunta("¿cuántos m²")
    ok(nav.js("parseFloat(getComputedStyle(document.getElementById('chatMetros')).fontSize)") >= 16,
       "El campo de m² usa letra de 16 px (el iPhone no hace zoom)")
    nav.toque("#chatMetros")
    nav.escribir("25")
    nav.toque(".chat__enviar")
    esperar_resultado()
    ok(nav.js("document.documentElement.scrollWidth <= 360"), "El resultado tampoco se desborda en 360 px")
    ok("Productos Especiales" in nav.texto(".sugerencia--principal"), "Interior con humedad y «No sé» → Productos Especiales")
    nav.captura(os.path.join(CAPTURAS, "asistente-360-resultado.png"))
    nav.toque("#chatCerrar")
    ok(not chat_abierto() and nav.js("getComputedStyle(document.documentElement).overflow") != "hidden",
       "Al cerrar, la página vuelve a desplazarse")

    # ------------------------------------------------------------
    titulo("Consola, CSP y movimiento reducido")
    nav.cmd("Emulation.setEmulatedMedia", features=[{"name": "prefers-reduced-motion", "value": "reduce"}])
    nav.recargar()
    nav.toque("#asistenteBurbuja")
    esperar_resultado()
    duracion = nav.js("getComputedStyle(document.querySelector('.mensaje')).animationDuration")
    ok(duracion in ("1e-05s", "0.00001s", "0s"), "Con «reducir movimiento» los mensajes no se animan", duracion)
    ok(nav.violaciones_csp() == [], "Ninguna violación de la CSP", nav.violaciones_csp())
    # El 404 de asistente.html lo provocamos a propósito al comienzo
    errores = [e for e in nav.errores if "/asistente.html" not in str(e)]
    ok(errores == [], "Ningún error en la consola", errores)
finally:
    nav.cerrar()
    srv.borrar()

print("\nCapturas en: " + CAPTURAS)
terminar()
