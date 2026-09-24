#!/usr/bin/env python3
# ============================================================
#  ECOCORDI - Servidor y base de datos (Python, sin dependencias)
#
#  Este archivo es el "cerebro" del sitio (el backend):
#   - Crea y gestiona la base de datos SQLite (ecocordi.db)
#   - Ofrece una API (endpoints /api/...) que el frontend consume
#   - Sirve los archivos del sitio (HTML, CSS, JS, imágenes)
#
#  Se ejecuta con:  python3 server.py
# ============================================================

import http.server
import socketserver
import json
import sqlite3
import hashlib
import hmac
import secrets
import os
import mimetypes
import threading
import time
from http.cookies import SimpleCookie
from urllib.parse import urlparse, parse_qs

# Carpeta donde vive este archivo, y ruta de la base de datos
BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "ecocordi.db")
PUERTO = 8000
ADMIN_CORREO = os.environ.get("ADMIN_CORREO", "admin@ecocordi.cl")
MAX_CANTIDAD = 999  # unidades máximas de un mismo producto por pedido
CLAVE_MINIMA = 8          # largo mínimo de la contraseña al registrarse
DIAS_SESION = 7           # una sesión vale 7 días (igual que la cookie)
MAX_FALLOS = 5            # intentos fallidos permitidos por IP...
VENTANA_FALLOS = 10 * 60  # ...en esta cantidad de segundos (10 minutos)
STOCK_INICIAL = 20        # unidades con que parten los productos de ejemplo
MAX_STOCK = 100000
MAX_PRECIO = 100000000
# Estados posibles de un pedido (en orden). "cancelado" devuelve el stock.
ESTADOS = ("pendiente", "pagado", "enviado", "entregado", "cancelado")
_DEF_ESTADO = ("TEXT NOT NULL DEFAULT 'pendiente' CHECK (estado IN ("
               + ", ".join(f"'{e}'" for e in ESTADOS) + "))")

# Cabeceras de seguridad que se agregan a TODAS las respuestas.
#  - Content-Security-Policy (CSP): lista de lo que el navegador puede cargar.
#    Con default-src 'self' solo se aceptan archivos de NUESTRO servidor: si
#    alguien lograra meter un <script> o un onclick="..." en la página, el
#    navegador se negaría a ejecutarlo. Es la segunda barrera contra XSS.
#  - X-Content-Type-Options: nosniff → el navegador no "adivina" el tipo de
#    archivo (evita que un .jpg se ejecute como si fuera JavaScript).
#  - Referrer-Policy: same-origin → no le contamos a otros sitios desde qué
#    página de la tienda llegó el usuario.
CABECERAS_SEGURIDAD = {
    "Content-Security-Policy":
        "default-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
}


# ------------------------------------------------------------
#  BASE DE DATOS
# ------------------------------------------------------------
def get_db():
    """Abre una conexión a la base de datos. row_factory permite
    leer las filas como diccionarios (columna -> valor)."""
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    # SQLite NO revisa las FOREIGN KEY a menos que se lo pidamos en CADA
    # conexión. Con esto, por ejemplo, no se puede guardar un pedido de un
    # usuario que no existe.
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db():
    """Crea las tablas si no existen y carga datos iniciales."""
    con = get_db()
    c = con.cursor()

    # Tabla de productos
    c.execute("""
        CREATE TABLE IF NOT EXISTS productos (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre      TEXT NOT NULL,
            descripcion TEXT,
            precio      INTEGER NOT NULL,
            imagen      TEXT,
            superficies TEXT,  -- guardado como JSON: ["madera","interior"]
            stock       INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0)
        )
    """)

    # Tabla de usuarios (la clave se guarda ENCRIPTADA, nunca en texto plano)
    c.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre   TEXT NOT NULL,
            correo   TEXT NOT NULL UNIQUE,
            clave    TEXT NOT NULL,
            es_admin INTEGER DEFAULT 0
        )
    """)

    # Tabla de pedidos (cabecera: quién compró, cuándo y el total)
    c.execute(f"""
        CREATE TABLE IF NOT EXISTS pedidos (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER,
            total      INTEGER NOT NULL,
            fecha      TEXT DEFAULT (datetime('now','localtime')),
            estado     {_DEF_ESTADO},
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        )
    """)

    # Detalle de cada pedido (qué productos y cuántos)
    c.execute("""
        CREATE TABLE IF NOT EXISTS pedido_items (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            pedido_id    INTEGER,
            producto_id  INTEGER,
            nombre       TEXT,
            precio       INTEGER,
            cantidad     INTEGER,
            FOREIGN KEY (pedido_id) REFERENCES pedidos(id)
        )
    """)

    # Sesiones (para recordar quién inició sesión, con un token en una cookie)
    c.execute("""
        CREATE TABLE IF NOT EXISTS sesiones (
            token      TEXT PRIMARY KEY,
            usuario_id INTEGER,
            creada     TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    # MIGRACIONES: si la base de datos es de una versión anterior del
    # proyecto, le agregamos las columnas nuevas SIN borrar los datos.
    if _agregar_columna(c, "productos", "stock",
                        "INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0)"):
        # Los productos que ya existían parten con el stock de ejemplo
        # (si quedaran en 0, la tienda los mostraría todos "Agotado").
        c.execute("UPDATE productos SET stock = ?", (STOCK_INICIAL,))
        print(f"  Migración: columna 'stock' agregada ({STOCK_INICIAL} unidades por producto)")
    if _agregar_columna(c, "pedidos", "estado", _DEF_ESTADO):
        print("  Migración: columna 'estado' agregada (pedidos existentes: 'pendiente')")

    # Limpieza: borramos las sesiones que ya vencieron
    borradas = c.execute(
        "DELETE FROM sesiones WHERE creada IS NULL OR creada <= datetime('now','localtime',?)",
        (f"-{DIAS_SESION} days",),
    ).rowcount
    if borradas:
        print(f"  Se borraron {borradas} sesiones vencidas")

    con.commit()
    _seed_productos(con)
    _seed_admin(con)
    con.close()


def _agregar_columna(c, tabla, columna, definicion):
    """ALTER TABLE ... ADD COLUMN solo si la columna todavía no existe.
    Devuelve True si la agregó. ALTER TABLE conserva todas las filas."""
    existentes = [fila["name"] for fila in c.execute(f"PRAGMA table_info({tabla})")]
    if columna in existentes:
        return False
    c.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")
    return True


def _seed_productos(con):
    """Carga los productos iniciales solo si la tabla está vacía."""
    c = con.cursor()
    if c.execute("SELECT COUNT(*) FROM productos").fetchone()[0] > 0:
        return

    productos = [
        ("Protección de Madera", "Acabado y protección para muebles, puertas y decks.", 18990, "img/prod-madera.webp", ["madera", "interior"]),
        ("Anticorrosivo Metal Pro", "Protege rejas, portones y estructuras contra el óxido.", 21990, "img/prod-metal.webp", ["metal", "exterior"]),
        ("Pinturas para Exterior", "Resistente al sol y la lluvia para fachadas duraderas.", 24990, "img/prod-exterior.webp", ["exterior"]),
        ("Línea Constructoras", "Alto rendimiento para grandes proyectos y obras.", 29990, "img/prod-constructoras.webp", ["techo", "exterior"]),
        ("Pinturas para Interior", "Cobertura perfecta y acabado elegante para muros interiores.", 15990, "img/prod-interior.webp", ["interior"]),
        ("Chalk Paint Ecocordi", "Pintura a la tiza para renovar muebles con estilo vintage.", 12990, "img/prod-chalk.webp", ["madera", "interior"]),
        ("Productos Especiales", "Soluciones específicas de alto desempeño para cada trabajo.", 19990, "img/prod-especiales.webp", ["metal", "interior"]),
        ("Impermeabilizante Techo", "Sella y protege techos y cubiertas contra filtraciones.", 27990, "img/prod-techo.webp", ["techo"]),
    ]
    for nombre, desc, precio, imagen, superf in productos:
        c.execute(
            "INSERT INTO productos (nombre, descripcion, precio, imagen, superficies, stock) VALUES (?,?,?,?,?,?)",
            (nombre, desc, precio, imagen, json.dumps(superf), STOCK_INICIAL),
        )
    con.commit()


def _seed_admin(con):
    """Crea (o actualiza) la cuenta de administrador.

    La contraseña NUNCA se escribe en el código (el repositorio es público).
    Se lee de la "variable de entorno" ADMIN_CLAVE, que se define al arrancar:
        ADMIN_CLAVE='mi-clave-secreta' python3 server.py
    - Si ADMIN_CLAVE existe: el admin queda con esa clave (sirve para cambiarla).
    - Si no existe y aún no hay admin: se inventa una clave al azar y se
      muestra UNA vez en la terminal.
    """
    c = con.cursor()
    fila = c.execute("SELECT id, clave FROM usuarios WHERE correo=?", (ADMIN_CORREO,)).fetchone()
    clave_env = os.environ.get("ADMIN_CLAVE")

    if clave_env:
        if fila:
            c.execute("UPDATE usuarios SET clave=?, es_admin=1 WHERE id=?",
                      (hash_clave(clave_env), fila["id"]))
        else:
            c.execute(
                "INSERT INTO usuarios (nombre, correo, clave, es_admin) VALUES (?,?,?,1)",
                ("Administrador", ADMIN_CORREO, hash_clave(clave_env)),
            )
        con.commit()
        print(f"  Admin {ADMIN_CORREO}: clave tomada de ADMIN_CLAVE")
    elif not fila:
        clave = secrets.token_urlsafe(9)
        c.execute(
            "INSERT INTO usuarios (nombre, correo, clave, es_admin) VALUES (?,?,?,1)",
            ("Administrador", ADMIN_CORREO, hash_clave(clave)),
        )
        con.commit()
        print("=" * 50)
        print("  Se creó la cuenta de administrador:")
        print(f"    Correo: {ADMIN_CORREO}")
        print(f"    Clave:  {clave}")
        print("  ¡Anótala! No se volverá a mostrar.")
        print("=" * 50)
    elif verificar_clave("admin123", fila["clave"]):
        # Bases de datos antiguas quedaron con la clave de ejemplo (pública)
        print("  ⚠️  El admin todavía usa la clave de ejemplo 'admin123'.")
        print("     Cámbiala con:  ADMIN_CLAVE='nueva-clave' python3 server.py")


# ------------------------------------------------------------
#  SEGURIDAD DE CONTRASEÑAS
#  Nunca guardamos la clave tal cual. Guardamos un "hash" con sal:
#  imposible de revertir, pero sí de verificar.
# ------------------------------------------------------------
def hash_clave(clave, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", clave.encode(), salt.encode(), 100000).hex()
    return f"{salt}${h}"


def verificar_clave(clave, guardado):
    try:
        salt, h = guardado.split("$")
    except ValueError:
        return False
    calculado = hashlib.pbkdf2_hmac("sha256", clave.encode(), salt.encode(), 100000).hex()
    return hmac.compare_digest(calculado, h)  # comparación segura


def _id_de_ruta(ruta, prefijo):
    """'/api/admin/pedidos/7' con prefijo '/api/admin/pedidos/' → 7.
    Devuelve None si la ruta no empieza así o si lo que sigue no es un número."""
    if not ruta.startswith(prefijo):
        return None
    resto = ruta[len(prefijo):]
    return int(resto) if resto.isdigit() else None


def _texto(datos, campo):
    """Lee un campo de texto del JSON; si mandan otra cosa (número, lista...), da ""."""
    valor = datos.get(campo)
    return valor if isinstance(valor, str) else ""


# ------------------------------------------------------------
#  LÍMITE DE INTENTOS (rate limiting)
#  Evita que alguien pruebe miles de contraseñas seguidas ("fuerza bruta").
#  Anotamos la hora de cada intento FALLIDO por IP. Si una IP acumula
#  MAX_FALLOS en los últimos VENTANA_FALLOS segundos, la bloqueamos (429)
#  hasta que el fallo más antiguo "caduque".
# ------------------------------------------------------------
_fallos = {}                 # {(ruta, ip): [hora_fallo1, hora_fallo2, ...]}
_fallos_lock = threading.Lock()  # el servidor atiende varias peticiones a la vez


def _fallos_recientes(clave):
    """Devuelve los fallos de los últimos 10 minutos (y olvida los más viejos)."""
    limite = time.time() - VENTANA_FALLOS
    recientes = [t for t in _fallos.get(clave, []) if t > limite]
    if recientes:
        _fallos[clave] = recientes
    else:
        _fallos.pop(clave, None)
    return recientes


def segundos_bloqueado(clave):
    """0 si puede intentar; si no, cuántos segundos le faltan para desbloquearse."""
    with _fallos_lock:
        recientes = _fallos_recientes(clave)
        if len(recientes) < MAX_FALLOS:
            return 0
        return int(recientes[-MAX_FALLOS] + VENTANA_FALLOS - time.time()) + 1


def anotar_fallo(clave):
    with _fallos_lock:
        _fallos_recientes(clave)
        _fallos.setdefault(clave, []).append(time.time())


# ------------------------------------------------------------
#  MANEJADOR DE PETICIONES HTTP
# ------------------------------------------------------------
class Handler(http.server.BaseHTTPRequestHandler):

    # ---- utilidades ----
    def end_headers(self):
        """Se llama justo antes de enviar CUALQUIER respuesta (JSON, archivos
        y errores 404), así que es el lugar para agregar las cabeceras de
        seguridad una sola vez para todo el sitio."""
        for nombre, valor in CABECERAS_SEGURIDAD.items():
            self.send_header(nombre, valor)
        super().end_headers()

    def _json(self, data, status=200, set_cookie=None, extra=None):
        cuerpo = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        if set_cookie:
            self.send_header("Set-Cookie", set_cookie)
        for nombre, valor in (extra or {}).items():
            self.send_header(nombre, valor)
        self.end_headers()
        self.wfile.write(cuerpo)
        return status  # así quien llama sabe si salió bien (200) o no

    def _leer_json(self):
        try:
            largo = int(self.headers.get("Content-Length", 0))
        except ValueError:
            return {}
        if largo <= 0:
            return {}
        try:
            datos = json.loads(self.rfile.read(largo).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}
        # Solo aceptamos un objeto {...}; si mandan una lista u otra cosa, lo ignoramos
        return datos if isinstance(datos, dict) else {}

    def _usuario_actual(self):
        """Devuelve el usuario (dict) según la cookie de sesión, o None."""
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        if "sesion" not in cookie:
            return None
        token = cookie["sesion"].value
        con = get_db()
        fila = con.execute("""
            SELECT u.id, u.nombre, u.correo, u.es_admin
            FROM sesiones s JOIN usuarios u ON u.id = s.usuario_id
            WHERE s.token = ?
              AND s.creada > datetime('now','localtime',?)  -- no vencida
        """, (token, f"-{DIAS_SESION} days")).fetchone()
        con.close()
        return dict(fila) if fila else None

    # ---- GET ----
    def do_GET(self):
        ruta = urlparse(self.path)
        if ruta.path.startswith("/api/"):
            return self._api_get(ruta)
        return self._servir_estatico(ruta.path)

    def _api_get(self, ruta):
        if ruta.path == "/api/productos":
            superficie = parse_qs(ruta.query).get("superficie", [None])[0]
            con = get_db()
            filas = con.execute("SELECT * FROM productos ORDER BY id").fetchall()
            con.close()
            productos = []
            for f in filas:
                p = dict(f)
                p["superficies"] = json.loads(p["superficies"] or "[]")
                if superficie in (None, "todas") or superficie in p["superficies"]:
                    productos.append(p)
            return self._json(productos)

        if ruta.path == "/api/me":
            u = self._usuario_actual()
            return self._json(u if u else {"invitado": True})

        if ruta.path == "/api/pedidos":
            u = self._usuario_actual()
            if not u:
                return self._json({"error": "No has iniciado sesión"}, 401)
            return self._json(self._obtener_pedidos(u["id"]))

        if ruta.path == "/api/admin/pedidos":
            u = self._usuario_actual()
            if not u or not u["es_admin"]:
                return self._json({"error": "Solo administradores"}, 403)
            return self._json(self._obtener_pedidos(None))

        return self._json({"error": "Ruta no encontrada"}, 404)

    # ---- POST ----
    def do_POST(self):
        ruta = urlparse(self.path)
        datos = self._leer_json()

        if ruta.path in ("/api/register", "/api/login"):
            return self._con_limite(ruta.path, datos)
        if ruta.path == "/api/logout":
            return self._logout()
        if ruta.path == "/api/pedidos":
            return self._crear_pedido(datos)
        if ruta.path == "/api/admin/productos":
            return self._crear_producto(datos)

        return self._json({"error": "Ruta no encontrada"}, 404)

    # ---- PATCH (modificar algo que ya existe) ----
    def do_PATCH(self):
        ruta = urlparse(self.path)
        datos = self._leer_json()
        u = self._usuario_actual()
        if ruta.path.startswith("/api/admin/"):
            if not u or not u["es_admin"]:
                return self._json({"error": "Solo administradores"}, 403)
            pedido_id = _id_de_ruta(ruta.path, "/api/admin/pedidos/")
            if pedido_id is not None:
                return self._cambiar_estado(pedido_id, datos)
            producto_id = _id_de_ruta(ruta.path, "/api/admin/productos/")
            if producto_id is not None:
                return self._editar_producto(producto_id, datos)
        return self._json({"error": "Ruta no encontrada"}, 404)

    # ---- DELETE ----
    def do_DELETE(self):
        ruta = urlparse(self.path)
        if ruta.path.startswith("/api/admin/productos/"):
            u = self._usuario_actual()
            if not u or not u["es_admin"]:
                return self._json({"error": "Solo administradores"}, 403)
            pid = ruta.path.rsplit("/", 1)[-1]
            con = get_db()
            con.execute("DELETE FROM productos WHERE id=?", (pid,))
            con.commit()
            con.close()
            return self._json({"ok": True})
        return self._json({"error": "Ruta no encontrada"}, 404)

    # ---- lógica de negocio ----
    def _con_limite(self, ruta, datos):
        """Atiende login/registro, pero antes revisa si esta IP está bloqueada.
        Cada ruta lleva su propio contador. Solo cuentan los intentos FALLIDOS."""
        clave = (ruta, self.client_address[0])
        espera = segundos_bloqueado(clave)
        if espera:
            minutos = (espera + 59) // 60
            return self._json(
                {"error": f"Demasiados intentos fallidos. Espera {minutos} minuto(s) e inténtalo de nuevo."},
                429, extra={"Retry-After": str(espera)})
        manejar = self._registrar if ruta == "/api/register" else self._login
        status = manejar(datos)
        if status != 200:
            anotar_fallo(clave)

    def _registrar(self, datos):
        nombre = _texto(datos, "nombre").strip()
        correo = _texto(datos, "correo").strip().lower()
        clave = _texto(datos, "clave")
        if not nombre or not correo:
            return self._json({"error": "Completa nombre, correo y contraseña"}, 400)
        if len(clave) < CLAVE_MINIMA:
            return self._json(
                {"error": f"La contraseña debe tener al menos {CLAVE_MINIMA} caracteres"}, 400)
        con = get_db()
        if con.execute("SELECT 1 FROM usuarios WHERE correo=?", (correo,)).fetchone():
            con.close()
            return self._json({"error": "Ese correo ya está registrado"}, 409)
        cur = con.execute(
            "INSERT INTO usuarios (nombre, correo, clave) VALUES (?,?,?)",
            (nombre, correo, hash_clave(clave)),
        )
        usuario_id = cur.lastrowid
        con.commit()
        con.close()
        return self._iniciar_sesion(usuario_id, nombre, correo, 0)

    def _login(self, datos):
        correo = _texto(datos, "correo").strip().lower()
        clave = _texto(datos, "clave")
        con = get_db()
        u = con.execute("SELECT * FROM usuarios WHERE correo=?", (correo,)).fetchone()
        con.close()
        if not u or not verificar_clave(clave, u["clave"]):
            return self._json({"error": "Correo o contraseña incorrectos"}, 401)
        return self._iniciar_sesion(u["id"], u["nombre"], u["correo"], u["es_admin"])

    def _iniciar_sesion(self, usuario_id, nombre, correo, es_admin):
        token = secrets.token_hex(32)
        con = get_db()
        con.execute("INSERT INTO sesiones (token, usuario_id) VALUES (?,?)", (token, usuario_id))
        con.commit()
        con.close()
        cookie = f"sesion={token}; HttpOnly; Path=/; SameSite=Lax; Max-Age={DIAS_SESION * 24 * 3600}"
        return self._json(
            {"id": usuario_id, "nombre": nombre, "correo": correo, "es_admin": es_admin},
            set_cookie=cookie,
        )

    def _logout(self):
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        if "sesion" in cookie:
            con = get_db()
            con.execute("DELETE FROM sesiones WHERE token=?", (cookie["sesion"].value,))
            con.commit()
            con.close()
        borrar = "sesion=; HttpOnly; Path=/; Max-Age=0"
        return self._json({"ok": True}, set_cookie=borrar)

    def _crear_pedido(self, datos):
        u = self._usuario_actual()
        if not u:
            return self._json({"error": "Debes iniciar sesión para comprar"}, 401)
        items = datos.get("items")
        if not isinstance(items, list):
            return self._json({"error": "Pedido con formato inválido"}, 400)
        if not items:
            return self._json({"error": "El carrito está vacío"}, 400)

        # 1) Revisamos el FORMATO (sin tocar la base de datos). No confiamos
        #    en id ni cantidad: si algo está mal se rechaza todo (error 400).
        pedido = {}  # {id_producto: cantidad}; junta ids repetidos en uno
        for it in items:
            if not isinstance(it, dict):
                return self._json({"error": "Pedido con formato inválido"}, 400)
            pid = it.get("id")
            cant = it.get("cantidad")
            # type(...) is int deja fuera textos ("abc"), decimales (1.5) y True/False
            if type(pid) is not int:
                return self._json({"error": "Pedido con formato inválido"}, 400)
            if type(cant) is not int or not 1 <= cant <= MAX_CANTIDAD:
                return self._json(
                    {"error": f"Cantidad inválida (debe ser un número entre 1 y {MAX_CANTIDAD})"}, 400)
            pedido[pid] = pedido.get(pid, 0) + cant

        # 2) TRANSACCIÓN: revisar stock, descontarlo y guardar el pedido
        #    ocurre "todo o nada". BEGIN IMMEDIATE reserva la base de datos
        #    para escribir: si dos personas compran el último tarro al mismo
        #    tiempo, la segunda ESPERA a que la primera termine y recién ahí
        #    lee el stock (que ya será 0). Así nunca se vende de más.
        con = get_db()
        try:
            con.execute("BEGIN IMMEDIATE")
            total = 0
            detalle = []
            for pid, cant in pedido.items():
                prod = con.execute("SELECT * FROM productos WHERE id=?", (pid,)).fetchone()
                if not prod:
                    con.rollback()
                    return self._json(
                        {"error": "Uno de los productos ya no existe. Revisa tu carrito."}, 400)
                if prod["stock"] < cant:
                    con.rollback()  # deshace todo: no se guarda NADA
                    return self._json({
                        "error": f"No hay stock suficiente de «{prod['nombre']}»: "
                                 f"pediste {cant} y quedan {prod['stock']}.",
                        "producto_id": pid,
                        "nombre": prod["nombre"],
                        "disponible": prod["stock"],
                    }, 409)
                # El total lo calcula el SERVIDOR con los precios reales
                total += prod["precio"] * cant
                detalle.append((pid, prod["nombre"], prod["precio"], cant))
                con.execute("UPDATE productos SET stock = stock - ? WHERE id=?", (cant, pid))

            cur = con.execute("INSERT INTO pedidos (usuario_id, total) VALUES (?,?)", (u["id"], total))
            pedido_id = cur.lastrowid
            for pid, nombre, precio, cant in detalle:
                con.execute(
                    "INSERT INTO pedido_items (pedido_id, producto_id, nombre, precio, cantidad) VALUES (?,?,?,?,?)",
                    (pedido_id, pid, nombre, precio, cant),
                )
            con.commit()  # recién aquí los cambios quedan guardados de verdad
        except sqlite3.Error:
            con.rollback()
            return self._json({"error": "No se pudo guardar el pedido. Inténtalo de nuevo."}, 500)
        finally:
            con.close()
        return self._json({"ok": True, "pedido_id": pedido_id, "total": total})

    def _cambiar_estado(self, pedido_id, datos):
        """PATCH /api/admin/pedidos/<id>  {"estado": "enviado"}"""
        nuevo = datos.get("estado")
        if nuevo not in ESTADOS:
            return self._json({"error": "Estado inválido. Usa: " + ", ".join(ESTADOS)}, 400)
        con = get_db()
        try:
            con.execute("BEGIN IMMEDIATE")  # igual que al comprar: todo o nada
            fila = con.execute("SELECT estado FROM pedidos WHERE id=?", (pedido_id,)).fetchone()
            if not fila:
                con.rollback()
                return self._json({"error": "El pedido no existe"}, 404)
            actual = fila["estado"]
            if actual == "cancelado" and nuevo != "cancelado":
                # Su stock ya se devolvió; "revivirlo" podría vender algo que ya no hay
                con.rollback()
                return self._json({"error": "Un pedido cancelado no se puede reactivar"}, 409)
            if nuevo == "cancelado" and actual != "cancelado":
                # Devolvemos al stock lo que el pedido había descontado
                # (si el producto fue borrado, simplemente no hay dónde sumarlo)
                con.execute("""
                    UPDATE productos
                    SET stock = stock + (SELECT SUM(i.cantidad) FROM pedido_items i
                                         WHERE i.pedido_id = ? AND i.producto_id = productos.id)
                    WHERE id IN (SELECT producto_id FROM pedido_items WHERE pedido_id = ?)
                """, (pedido_id, pedido_id))
            con.execute("UPDATE pedidos SET estado=? WHERE id=?", (nuevo, pedido_id))
            con.commit()
        except sqlite3.Error:
            con.rollback()
            return self._json({"error": "No se pudo cambiar el estado"}, 500)
        finally:
            con.close()
        return self._json({"ok": True, "id": pedido_id, "estado": nuevo})

    def _editar_producto(self, producto_id, datos):
        """PATCH /api/admin/productos/<id>  {"precio": 19990, "stock": 15}
        Se puede mandar solo uno de los dos."""
        cambios = {}
        for campo, maximo in (("precio", MAX_PRECIO), ("stock", MAX_STOCK)):
            if campo in datos:
                valor = datos[campo]
                if type(valor) is not int or not 0 <= valor <= maximo:
                    return self._json(
                        {"error": f"{campo.capitalize()} inválido (número entero entre 0 y {maximo})"}, 400)
                cambios[campo] = valor
        if not cambios:
            return self._json({"error": "Indica precio y/o stock"}, 400)
        con = get_db()
        # Los nombres de columna vienen de nuestra lista fija, no del usuario
        asignaciones = ", ".join(f"{campo}=?" for campo in cambios)
        cur = con.execute(f"UPDATE productos SET {asignaciones} WHERE id=?",
                          (*cambios.values(), producto_id))
        con.commit()
        fila = con.execute("SELECT * FROM productos WHERE id=?", (producto_id,)).fetchone()
        con.close()
        if cur.rowcount == 0:
            return self._json({"error": "El producto no existe"}, 404)
        return self._json({"ok": True, "id": producto_id, "precio": fila["precio"], "stock": fila["stock"]})

    def _obtener_pedidos(self, usuario_id):
        con = get_db()
        if usuario_id is None:  # admin: todos los pedidos
            filas = con.execute("""
                SELECT p.id, p.total, p.fecha, p.estado, u.nombre AS cliente, u.correo
                FROM pedidos p LEFT JOIN usuarios u ON u.id = p.usuario_id
                ORDER BY p.id DESC
            """).fetchall()
        else:
            filas = con.execute(
                "SELECT id, total, fecha, estado FROM pedidos WHERE usuario_id=? ORDER BY id DESC",
                (usuario_id,),
            ).fetchall()
        pedidos = []
        for f in filas:
            p = dict(f)
            items = con.execute(
                "SELECT nombre, precio, cantidad FROM pedido_items WHERE pedido_id=?", (p["id"],)
            ).fetchall()
            p["items"] = [dict(i) for i in items]
            pedidos.append(p)
        con.close()
        return pedidos

    def _crear_producto(self, datos):
        u = self._usuario_actual()
        if not u or not u["es_admin"]:
            return self._json({"error": "Solo administradores"}, 403)
        try:
            nombre = datos["nombre"].strip()
            precio = int(datos["precio"])
            stock = int(datos.get("stock", 0))
        except (KeyError, ValueError, TypeError, AttributeError):
            return self._json({"error": "Nombre y precio son obligatorios"}, 400)
        if not nombre or not 0 <= precio <= MAX_PRECIO or not 0 <= stock <= MAX_STOCK:
            return self._json({"error": "Nombre, precio o stock inválidos"}, 400)
        con = get_db()
        cur = con.execute(
            "INSERT INTO productos (nombre, descripcion, precio, imagen, superficies, stock) VALUES (?,?,?,?,?,?)",
            (
                nombre,
                datos.get("descripcion", ""),
                precio,
                datos.get("imagen", "img/prod-interior.webp"),
                json.dumps(datos.get("superficies", [])),
                stock,
            ),
        )
        con.commit()
        nuevo_id = cur.lastrowid
        con.close()
        return self._json({"ok": True, "id": nuevo_id})

    # ---- archivos estáticos (HTML, CSS, JS, imágenes) ----
    def _servir_estatico(self, ruta):
        if ruta == "/":
            ruta = "/index.html"
        ruta = ruta.lstrip("/")
        archivo = os.path.normpath(os.path.join(BASE, ruta))
        # Seguridad: no permitir salir de la carpeta del proyecto
        if not archivo.startswith(BASE) or not os.path.isfile(archivo):
            self.send_error(404, "No encontrado")
            return
        tipo = mimetypes.guess_type(archivo)[0] or "application/octet-stream"
        with open(archivo, "rb") as f:
            contenido = f.read()
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(contenido)))
        self.end_headers()
        self.wfile.write(contenido)

    def log_message(self, formato, *args):
        # Log compacto y en español
        print(f"  {self.command} {self.path}")


# ------------------------------------------------------------
#  ARRANQUE DEL SERVIDOR
# ------------------------------------------------------------
class Servidor(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


if __name__ == "__main__":
    init_db()
    print("=" * 50)
    print("  ECOCORDI - Servidor iniciado")
    print(f"  Abre en tu navegador:  http://localhost:{PUERTO}")
    print(f"  Panel admin:           http://localhost:{PUERTO}/admin.html")
    print("  (Para detener el servidor: Ctrl + C)")
    print("=" * 50)
    with Servidor(("", PUERTO), Handler) as httpd:
        httpd.serve_forever()
