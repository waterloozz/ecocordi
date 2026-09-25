# ============================================================
#  ECOCORDI - Chrome "sin interfaz" (headless) para las pruebas
#
#  Controla Google Chrome con el Chrome DevTools Protocol (el mismo que usan
#  las herramientas de desarrollador): abrir páginas, hacer clic, tocar como
#  en un celular, escribir, subir archivos, sacar capturas y revisar errores.
#  Solo usa la librería estándar de Python: la conexión WebSocket está
#  escrita aquí mismo (clase WebSocket).
# ============================================================
import base64
import json
import os
import shutil
import socket
import struct
import subprocess
import tempfile
import threading
import time
import urllib.request
from urllib.parse import urlparse

CHROMES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")

# Se inyecta en cada página ANTES que sus scripts: anota las violaciones de la
# CSP (lo que el navegador bloqueó) para poder revisarlas después.
ESPIA_CSP = """
window.__violacionesCSP = [];
document.addEventListener("securitypolicyviolation", function (e) {
  window.__violacionesCSP.push(e.violatedDirective + " → " + (e.blockedURI || "inline"));
});
"""


def buscar_chrome():
    for nombre in CHROMES:
        ruta = shutil.which(nombre)
        if ruta:
            return ruta
    return None


def _puerto_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class WebSocket:
    """Cliente WebSocket mínimo (RFC 6455): solo lo que necesita el protocolo de Chrome."""

    def __init__(self, url):
        u = urlparse(url)
        self.sock = socket.create_connection((u.hostname, u.port), timeout=60)
        clave = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET {u.path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\n"
                           "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                           f"Sec-WebSocket-Key: {clave}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        respuesta = b""
        while b"\r\n\r\n" not in respuesta:
            respuesta += self.sock.recv(1)
        if b" 101 " not in respuesta.split(b"\r\n")[0]:
            raise ConnectionError("Chrome rechazó la conexión: " + respuesta.decode(errors="replace"))
        self.lock = threading.Lock()

    def enviar(self, texto):
        datos = texto.encode()
        cabecera = bytearray([0x81])  # un solo marco de texto
        n = len(datos)
        if n < 126:
            cabecera.append(0x80 | n)
        elif n < 65536:
            cabecera += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            cabecera += bytes([0x80 | 127]) + struct.pack(">Q", n)
        mascara = os.urandom(4)  # el cliente siempre enmascara lo que envía
        cabecera += mascara
        entero = int.from_bytes(datos, "big") ^ int.from_bytes((mascara * (n // 4 + 1))[:n], "big") if n else 0
        with self.lock:
            self.sock.sendall(bytes(cabecera) + (entero.to_bytes(n, "big") if n else b""))

    def _leer(self, n):
        partes, falta = [], n
        while falta:
            parte = self.sock.recv(min(falta, 1 << 20))
            if not parte:
                raise ConnectionError("Chrome cerró la conexión")
            partes.append(parte)
            falta -= len(parte)
        return b"".join(partes)

    def recibir(self):
        mensaje = b""
        while True:
            b1, b2 = self._leer(2)
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._leer(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._leer(8))[0]
            datos = self._leer(n)
            codigo = b1 & 0x0F
            if codigo == 8:
                raise ConnectionError("Chrome cerró la conexión")
            if codigo in (9, 10):  # ping / pong
                continue
            mensaje += datos
            if b1 & 0x80:  # último fragmento
                return mensaje.decode()


class Navegador:
    """Un Chrome sin interfaz con una pestaña. Guarda los errores de consola,
    las excepciones de JavaScript y todas las peticiones de red."""

    def __init__(self, ancho=1440, alto=900):
        chrome = buscar_chrome()
        if not chrome:
            raise RuntimeError("No se encontró Google Chrome ni Chromium")
        self.carpeta = tempfile.mkdtemp(prefix="ecocordi-chrome-")
        self.descargas = os.path.join(self.carpeta, "descargas")
        os.makedirs(self.descargas)
        self.puerto = _puerto_libre()
        self.proceso = subprocess.Popen(
            [chrome, "--headless=new", f"--remote-debugging-port={self.puerto}",
             f"--user-data-dir={os.path.join(self.carpeta, 'perfil')}", "--no-first-run",
             "--no-default-browser-check", "--disable-extensions", "--disable-gpu", "--hide-scrollbars",
             "--mute-audio", "--disable-background-networking", "--disable-component-update",
             f"--window-size={ancho},{alto}", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        pagina = None
        for _ in range(200):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.puerto}/json/list", timeout=1) as r:
                    pagina = next((t for t in json.load(r) if t["type"] == "page"), None)
                if pagina:
                    break
            except OSError:
                pass
            time.sleep(0.05)
        if not pagina:
            self.cerrar()
            raise RuntimeError("Chrome no arrancó")
        self.ws = WebSocket(pagina["webSocketDebuggerUrl"])
        self.siguiente_id = 0
        self.respuestas = {}
        self.condicion = threading.Condition()
        self.errores = []        # errores de consola y excepciones
        self.peticiones = []     # {"url", "metodo", "bytes_enviados"}
        self.descargas_listas = []
        self.cargada = threading.Event()
        threading.Thread(target=self._escuchar, daemon=True).start()
        for dominio in ("Page", "Runtime", "Log", "Network", "DOM"):
            self.cmd(dominio + ".enable")
        self.cmd("Page.addScriptToEvaluateOnNewDocument", source=ESPIA_CSP)
        self.cmd("Browser.setDownloadBehavior", behavior="allow", downloadPath=self.descargas, eventsEnabled=True)
        self.tamano(ancho, alto)

    # ---- comunicación con Chrome ----
    def _escuchar(self):
        try:
            while True:
                mensaje = json.loads(self.ws.recibir())
                if "id" in mensaje:
                    with self.condicion:
                        self.respuestas[mensaje["id"]] = mensaje
                        self.condicion.notify_all()
                else:
                    self._evento(mensaje["method"], mensaje.get("params", {}))
        except (ConnectionError, OSError, ValueError):
            pass

    def _evento(self, metodo, p):
        if metodo == "Page.loadEventFired":
            self.cargada.set()
        elif metodo == "Runtime.consoleAPICalled" and p["type"] in ("error", "assert"):
            texto = " ".join(str(a.get("value", a.get("description", ""))) for a in p["args"])
            self.errores.append("console.error: " + texto)
        elif metodo == "Runtime.exceptionThrown":
            d = p["exceptionDetails"]
            self.errores.append("Excepción: " + d.get("exception", {}).get("description", d.get("text", "")))
        elif metodo == "Log.entryAdded" and p["entry"]["level"] == "error":
            self.errores.append(f"[{p['entry']['source']}] {p['entry']['text']} {p['entry'].get('url', '')}")
        elif metodo == "Network.requestWillBeSent":
            req = p["request"]
            enviados = sum(len(e.get("bytes", "")) for e in req.get("postDataEntries", []))
            self.peticiones.append({"url": req["url"], "metodo": req["method"],
                                    "bytes_enviados": max(enviados, len(req.get("postData", "")))})
        elif metodo == "Browser.downloadProgress" and p["state"] == "completed":
            self.descargas_listas.append(p["guid"])

    def cmd(self, metodo, **params):
        with self.condicion:
            self.siguiente_id += 1
            numero = self.siguiente_id
        self.ws.enviar(json.dumps({"id": numero, "method": metodo, "params": params}))
        with self.condicion:
            if not self.condicion.wait_for(lambda: numero in self.respuestas, timeout=60):
                raise TimeoutError(metodo)
            respuesta = self.respuestas.pop(numero)
        if "error" in respuesta:
            raise RuntimeError(f"{metodo}: {respuesta['error']}")
        return respuesta.get("result", {})

    # ---- páginas y JavaScript ----
    def ir(self, url):
        self.cargada.clear()
        self.cmd("Page.navigate", url=url)
        if not self.cargada.wait(30):
            raise TimeoutError("La página no terminó de cargar: " + url)
        time.sleep(0.15)

    def recargar(self):
        self.cargada.clear()
        self.cmd("Page.reload")
        self.cargada.wait(30)
        time.sleep(0.15)

    def js(self, expresion):
        """Evalúa JavaScript en la página y devuelve el resultado (espera las promesas)."""
        r = self.cmd("Runtime.evaluate", expression=expresion, awaitPromise=True, returnByValue=True,
                     userGesture=True)
        if "exceptionDetails" in r:
            raise RuntimeError("Error en JS: " + r["exceptionDetails"].get("exception", {}).get("description", ""))
        return r["result"].get("value")

    def esperar(self, expresion, segundos=10, mensaje=None):
        """Espera hasta que la expresión de JavaScript sea verdadera."""
        limite = time.time() + segundos
        while time.time() < limite:
            if self.js(expresion):
                return True
            time.sleep(0.05)
        raise TimeoutError(mensaje or "No se cumplió: " + expresion)

    def url(self):
        return self.js("location.href")

    def texto(self, selector):
        return self.js(f"(document.querySelector({json.dumps(selector)}) || {{}}).innerText || ''")

    def existe(self, selector):
        return self.js(f"!!document.querySelector({json.dumps(selector)})")

    def violaciones_csp(self):
        return self.js("window.__violacionesCSP || []")

    # ---- ratón, dedo y teclado ----
    def centro(self, selector):
        """Lleva el elemento a la vista y devuelve su centro en pantalla."""
        caja = self.js(f"""(() => {{
            const el = document.querySelector({json.dumps(selector)});
            if (!el) return null;
            el.scrollIntoView({{block: "center", inline: "center", behavior: "instant"}});
            const r = el.getBoundingClientRect();
            return {{x: r.left + r.width / 2, y: r.top + r.height / 2, w: r.width, h: r.height}};
        }})()""")
        if not caja:
            raise LookupError("No existe: " + selector)
        time.sleep(0.05)
        return caja

    def clic(self, selector, espera=0.1):
        c = self.centro(selector)
        self.clic_en(c["x"], c["y"])
        time.sleep(espera)

    def clic_en(self, x, y):
        self.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
        self.cmd("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", buttons=1, clickCount=1)
        self.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", buttons=0, clickCount=1)

    def arrastrar(self, puntos):
        """Arrastra el ratón (botón apretado) por una lista de puntos (x, y) de la pantalla."""
        x, y = puntos[0]
        self.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
        self.cmd("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", buttons=1, clickCount=1)
        for x, y in puntos[1:]:
            self.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y, button="left", buttons=1)
        self.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", buttons=0, clickCount=1)

    def toque(self, selector, espera=0.15):
        """Un toque con el dedo (como en un celular). Requiere tamano(..., movil=True)."""
        c = self.centro(selector)
        self.toque_en(c["x"], c["y"])
        time.sleep(espera)

    def toque_en(self, x, y):
        self.cmd("Input.dispatchTouchEvent", type="touchStart", touchPoints=[{"x": x, "y": y}])
        self.cmd("Input.dispatchTouchEvent", type="touchEnd", touchPoints=[])

    def deslizar_dedo(self, puntos):
        x, y = puntos[0]
        self.cmd("Input.dispatchTouchEvent", type="touchStart", touchPoints=[{"x": x, "y": y}])
        for x, y in puntos[1:]:
            self.cmd("Input.dispatchTouchEvent", type="touchMove", touchPoints=[{"x": x, "y": y}])
        self.cmd("Input.dispatchTouchEvent", type="touchEnd", touchPoints=[])

    TECLAS = {"Tab": 9, "Enter": 13, "Escape": 27, " ": 32, "ArrowRight": 39, "ArrowLeft": 37,
              "ArrowUp": 38, "ArrowDown": 40, "Backspace": 8}

    def tecla(self, tecla, shift=False):
        codigo = self.TECLAS[tecla]
        base = {"key": tecla, "code": "Space" if tecla == " " else tecla, "windowsVirtualKeyCode": codigo,
                "modifiers": 8 if shift else 0}
        texto = {"Enter": "\r", " ": " "}.get(tecla)
        self.cmd("Input.dispatchKeyEvent", type="keyDown", **base, **({"text": texto} if texto else {}))
        self.cmd("Input.dispatchKeyEvent", type="keyUp", **base)
        time.sleep(0.05)

    def escribir(self, texto):
        self.cmd("Input.insertText", text=texto)

    def enfocado(self):
        """Descripción corta del elemento con el foco del teclado."""
        return self.js("""(() => { const e = document.activeElement;
            return e ? e.tagName + (e.id ? '#' + e.id : '') + ' ' + (e.innerText || e.value || e.getAttribute('aria-label') || '').trim().slice(0, 60) : ''; })()""")

    # ---- tamaño, capturas, archivos ----
    def tamano(self, ancho, alto, movil=False, escala=1):
        self.cmd("Emulation.setDeviceMetricsOverride", width=ancho, height=alto, deviceScaleFactor=escala, mobile=movil)
        self.cmd("Emulation.setTouchEmulationEnabled", enabled=movil, maxTouchPoints=5 if movil else 1)

    def captura(self, ruta, pagina_completa=False):
        if pagina_completa:
            # Carga las imágenes diferidas (loading="lazy") y vuelve arriba (la cabecera es fija)
            self.js("document.querySelectorAll('img[loading=lazy]').forEach(i => i.loading = 'eager')")
            self.js("Promise.all([...document.images].map(i => i.complete ? 0 : new Promise(r => i.onload = i.onerror = r)))")
            self.js("scrollTo({top: 0, behavior: 'instant'})")
        time.sleep(0.5)  # que terminen las animaciones de entrada
        params = {"format": "png"}
        if pagina_completa:
            medidas = self.cmd("Page.getLayoutMetrics")["cssContentSize"]
            params.update(captureBeyondViewport=True,
                          clip={"x": 0, "y": 0, "width": medidas["width"], "height": medidas["height"], "scale": 1})
        datos = self.cmd("Page.captureScreenshot", **params)["data"]
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        with open(ruta, "wb") as f:
            f.write(base64.b64decode(datos))
        return ruta

    def subir_archivo(self, selector, ruta):
        raiz = self.cmd("DOM.getDocument", depth=0)["root"]["nodeId"]
        nodo = self.cmd("DOM.querySelector", nodeId=raiz, selector=selector)["nodeId"]
        if not nodo:
            raise LookupError("No existe: " + selector)
        self.cmd("DOM.setFileInputFiles", nodeId=nodo, files=[os.path.abspath(ruta)])

    def cerrar(self):
        if self.proceso.poll() is None:
            self.proceso.terminate()
            try:
                self.proceso.wait(5)
            except subprocess.TimeoutExpired:
                self.proceso.kill()
        shutil.rmtree(self.carpeta, ignore_errors=True)
