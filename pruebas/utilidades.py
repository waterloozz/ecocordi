# ============================================================
#  ECOCORDI - Herramientas para las pruebas automáticas
#
#  Cada prueba arranca su PROPIO servidor en un puerto libre y con una base
#  de datos temporal (ECOCORDI_DB). Nunca se toca el ecocordi.db real.
# ============================================================
import http.cookiejar
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
ADMIN_CORREO = "admin@ecocordi.cl"
ADMIN_CLAVE = "ClaveDePrueba123"

resultados = {"ok": 0, "fallas": []}


def ok(condicion, texto, extra=""):
    if condicion:
        resultados["ok"] += 1
        print("  ✅ " + texto)
    else:
        resultados["fallas"].append(texto)
        print("  ❌ " + texto + (f"   [{extra}]" if extra != "" else ""))


def titulo(texto):
    print("\n### " + texto)


def terminar():
    total = resultados["ok"] + len(resultados["fallas"])
    print(f"\nResultado: {resultados['ok']}/{total} pruebas pasaron")
    if resultados["fallas"]:
        print("Fallaron:")
        for f in resultados["fallas"]:
            print("  - " + f)
    sys.exit(1 if resultados["fallas"] else 0)


def puerto_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Servidor:
    """Arranca server.py con una base de datos temporal.
    db_inicial: ruta de una base de datos a COPIAR (por ejemplo, una antigua)."""

    def __init__(self, db_inicial=None, entorno=None):
        self.carpeta = tempfile.mkdtemp(prefix="ecocordi-prueba-")
        self.db = os.path.join(self.carpeta, "prueba.db")
        if db_inicial:
            shutil.copy(db_inicial, self.db)
        self.puerto = puerto_libre()
        self.url = f"http://127.0.0.1:{self.puerto}"
        self.entorno = dict(os.environ, ECOCORDI_DB=self.db, PUERTO=str(self.puerto),
                            ECOCORDI_BACKUPS=os.path.join(self.carpeta, "backups"),
                            ADMIN_CORREO=ADMIN_CORREO, ADMIN_CLAVE=ADMIN_CLAVE,
                            GOOGLE_CLIENT_ID="", GOOGLE_CLIENT_SECRET="", PYTHONUNBUFFERED="1",
                            **(entorno or {}))
        self.proceso = None
        self.salida = ""

    def arrancar(self):
        self.log = open(os.path.join(self.carpeta, "servidor.log"), "a+")
        inicio = self.log.tell()
        self.proceso = subprocess.Popen([sys.executable, os.path.join(RAIZ, "server.py")],
                                        env=self.entorno, stdout=self.log, stderr=subprocess.STDOUT)
        for _ in range(100):
            try:
                urllib.request.urlopen(self.url + "/api/me", timeout=1)
                break
            except (urllib.error.URLError, ConnectionError):
                if self.proceso.poll() is not None:
                    break
                time.sleep(0.05)
        self.log.seek(inicio)
        self.salida = self.log.read()  # solo lo que escribió ESTE arranque
        return self

    def detener(self):
        if self.proceso:
            self.proceso.terminate()
            self.proceso.wait(5)
            self.proceso = None
            self.log.close()

    def borrar(self):
        self.detener()
        shutil.rmtree(self.carpeta, ignore_errors=True)

    def cliente(self):
        return Cliente(self.url)

    def admin(self):
        c = Cliente(self.url)
        c.pedir("POST", "/api/login", {"correo": ADMIN_CORREO, "clave": ADMIN_CLAVE})
        return c


class Cliente:
    """Un "navegador" mínimo: guarda las cookies y habla JSON con la API."""

    def __init__(self, url):
        self.url = url
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def pedir(self, metodo, ruta, datos=None):
        cuerpo = None if datos is None else json.dumps(datos).encode()
        req = urllib.request.Request(self.url + ruta, data=cuerpo, method=metodo,
                                     headers={"Content-Type": "application/json"})
        try:
            with self.opener.open(req, timeout=10) as r:
                return r.status, _decodificar(r.read())
        except urllib.error.HTTPError as e:
            return e.code, _decodificar(e.read())

    def registrar(self, correo, nombre="Cliente Prueba", clave="clave-segura-1"):
        return self.pedir("POST", "/api/register", {"nombre": nombre, "correo": correo, "clave": clave,
                                                    "acepta_terminos": True})


def _decodificar(bytes_):
    try:
        return json.loads(bytes_)
    except ValueError:
        return bytes_.decode("utf-8", "replace")
