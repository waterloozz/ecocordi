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
import base64
import re
import urllib.request
import urllib.error
from http.cookies import SimpleCookie
from urllib.parse import urlparse, parse_qs, urlencode, unquote

from backup import hacer_backup

# Carpeta donde vive este archivo
BASE = os.path.dirname(os.path.realpath(__file__))


def _cargar_env(ruta):
    """Lee el archivo .env (si existe) con líneas CLAVE=valor y las deja como
    variables de entorno. Así los secretos no van en el código ni en la línea
    de comandos. Si una variable ya estaba definida al arrancar, esa manda.
    El .env está en .gitignore: NUNCA se sube a GitHub (ver .env.example)."""
    if not os.path.isfile(ruta):
        return
    with open(ruta, encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, valor = linea.split("=", 1)
            valor = valor.strip()
            if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "'\"":
                valor = valor[1:-1]
            os.environ.setdefault(clave.strip(), valor)


_cargar_env(os.path.join(BASE, ".env"))

# Ruta de la base de datos y puerto (se pueden cambiar para hacer pruebas
# con una COPIA de la base de datos, sin tocar la real)
DB_PATH = os.environ.get("ECOCORDI_DB") or os.path.join(BASE, "ecocordi.db")
PUERTO = int(os.environ.get("PUERTO", "8000"))
ADMIN_CORREO = os.environ.get("ADMIN_CORREO", "admin@ecocordi.cl")
MAX_CANTIDAD = 999  # unidades máximas de un mismo producto por pedido
CLAVE_MINIMA = 8          # largo mínimo de la contraseña al registrarse
DIAS_SESION = 7           # una sesión vale 7 días (igual que la cookie)
MAX_FALLOS = 5            # intentos fallidos permitidos por IP...
VENTANA_FALLOS = 10 * 60  # ...en esta cantidad de segundos (10 minutos)
STOCK_INICIAL = 20        # unidades con que parten los productos de ejemplo
MAX_STOCK = 100000
MAX_PRECIO = 100000000
# Superficies que se pueden pintar (el filtro estrella). Es una lista cerrada:
# la base de datos no acepta otras palabras.
SUPERFICIES = ("madera", "metal", "exterior", "techo", "interior")
# Formatos de venta (1/4 galón, galón, tineta...). Cada formato tiene su
# propio precio y stock. Los litros de cada uno los define el admin.
FORMATO_MIGRACION = "galón"   # formato que reciben los productos antiguos
LITROS_GALON = 3.785          # 1 galón = 3,785 litros (confirmar con la empresa)
MAX_NOMBRE_FORMATO = 40
MAX_LITROS = 1000
# Estados posibles de un pedido (en orden). "cancelado" devuelve el stock.
ESTADOS = ("pendiente", "pagado", "enviado", "entregado", "cancelado")
# Versión de los Términos y la Política de privacidad. Si se cambian esos
# textos, subir esta fecha: así queda registro de QUÉ versión aceptó cada persona.
VERSION_TERMINOS = "2026-09-24.2"  # .2: se agregó el inicio de sesión con Google
MAX_NOMBRE = 80           # solo pedimos lo necesario, y con un largo razonable
MAX_CORREO = 254
# En producción con HTTPS: COOKIE_SEGURA=1 python3 server.py
# (la cookie de sesión solo viajará cifrada)
COOKIE_SEGURA = os.environ.get("COOKIE_SEGURA") == "1"

# Inicio de sesión con Google (OAuth 2.0 / OpenID Connect).
# Las credenciales se crean en Google Cloud y NUNCA se escriben en el código:
#   GOOGLE_CLIENT_ID=... GOOGLE_CLIENT_SECRET=... python3 server.py
# Si no están definidas, el botón de Google simplemente no aparece.
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
# Debe coincidir EXACTO con la "URI de redireccionamiento autorizada" en Google Cloud
GOOGLE_REDIRECT_URI = os.environ.get(
    "GOOGLE_REDIRECT_URI", f"http://localhost:{PUERTO}/api/auth/google/callback")
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_EMISORES = ("https://accounts.google.com", "accounts.google.com")
GOOGLE_MINUTOS = 10  # tiempo máximo para completar el inicio de sesión en Google
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
    """Crea las tablas si no existen, migra bases de datos antiguas y carga datos iniciales."""
    con = get_db()
    c = con.cursor()
    # Si la base de datos es de una versión anterior (productos con precio,
    # stock o superficies), guardamos una copia ANTES de cambiarle algo.
    antiguas = {"superficies", "precio", "stock"} & set(_columnas(c, "productos"))
    if antiguas and c.execute("SELECT COUNT(*) FROM productos").fetchone()[0]:
        copia = hacer_backup(DB_PATH, prefijo="antes-de-migrar", conservar=None)
        print(f"  Copia de seguridad antes de migrar: {copia}")

    # Productos: solo lo que describe al producto. El precio y el stock viven
    # en cada FORMATO (producto_formatos) y las superficies en su propia tabla.
    c.execute("""
        CREATE TABLE IF NOT EXISTS productos (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre      TEXT NOT NULL,
            descripcion TEXT,
            imagen      TEXT
        )
    """)

    # Superficies de cada producto (relación "N a N": un producto sirve para
    # varias superficies y una superficie tiene varios productos)
    _sups = ", ".join(f"'{s}'" for s in SUPERFICIES)
    c.execute(f"""
        CREATE TABLE IF NOT EXISTS producto_superficies (
            producto_id INTEGER NOT NULL REFERENCES productos(id) ON DELETE CASCADE,
            superficie  TEXT NOT NULL CHECK (superficie IN ({_sups})),
            PRIMARY KEY (producto_id, superficie)
        )
    """)

    # Formatos de venta de cada producto, cada uno con su precio y su stock
    c.execute("""
        CREATE TABLE IF NOT EXISTS producto_formatos (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER NOT NULL REFERENCES productos(id) ON DELETE CASCADE,
            nombre      TEXT NOT NULL,              -- "1/4 galón", "galón", "tineta"...
            litros      REAL NOT NULL CHECK (litros > 0),
            precio      INTEGER NOT NULL CHECK (precio >= 0),
            stock       INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
            UNIQUE (producto_id, nombre)
        )
    """)

    # Tabla de usuarios (la clave se guarda ENCRIPTADA, nunca en texto plano)
    c.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre   TEXT NOT NULL,
            correo   TEXT NOT NULL UNIQUE,
            clave    TEXT NOT NULL,
            es_admin INTEGER DEFAULT 0,
            terminos_aceptados TEXT,  -- fecha y versión de los términos aceptados
            google_sub TEXT           -- identificador de Google (solo si entra con Google)
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
            terminos_aceptados TEXT,  -- fecha y versión aceptadas al enviar el pedido
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        )
    """)

    # Detalle de cada pedido. Se guarda una COPIA del nombre, formato y precio
    # del momento de la compra: si después el producto cambia o se borra, el
    # pedido sigue mostrando lo que realmente se compró.
    c.execute("""
        CREATE TABLE IF NOT EXISTS pedido_items (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            pedido_id    INTEGER,
            producto_id  INTEGER,
            formato_id   INTEGER,
            nombre       TEXT,
            formato      TEXT,
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
    # proyecto, le agregamos lo nuevo SIN borrar los datos.
    if _agregar_columna(c, "pedidos", "estado", _DEF_ESTADO):
        print("  Migración: columna 'estado' agregada (pedidos existentes: 'pendiente')")
    # Registro del consentimiento: cuándo y qué versión de los términos se aceptó
    # (las filas antiguas quedan en NULL: se registraron antes de que existiera la casilla)
    for tabla in ("usuarios", "pedidos"):
        if _agregar_columna(c, tabla, "terminos_aceptados", "TEXT"):
            print(f"  Migración: columna 'terminos_aceptados' agregada a {tabla}")
    # Cuentas vinculadas a Google: guardamos solo su identificador ("sub")
    if _agregar_columna(c, "usuarios", "google_sub", "TEXT"):
        print("  Migración: columna 'google_sub' agregada a usuarios")
    for columna in ("formato_id INTEGER", "formato TEXT"):
        nombre, tipo = columna.split()
        if _agregar_columna(c, "pedido_items", nombre, tipo):
            print(f"  Migración: columna '{nombre}' agregada a pedido_items")
    con.commit()
    _migrar_productos(con)

    # ÍNDICES: como el índice de un libro, permiten encontrar filas sin
    # revisar la tabla completa (por ejemplo, "los pedidos de este usuario").
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_google ON usuarios(google_sub)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_pedidos_usuario ON pedidos(usuario_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_pedidos_estado ON pedidos(estado)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_pedido_items_pedido ON pedido_items(pedido_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_sesiones_usuario ON sesiones(usuario_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_sesiones_creada ON sesiones(creada)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_superficies_superficie ON producto_superficies(superficie)")

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


def _columnas(c, tabla):
    return [fila["name"] for fila in c.execute(f"PRAGMA table_info({tabla})")]


def _agregar_columna(c, tabla, columna, definicion):
    """ALTER TABLE ... ADD COLUMN solo si la columna todavía no existe.
    Devuelve True si la agregó. ALTER TABLE conserva todas las filas."""
    if columna in _columnas(c, tabla):
        return False
    c.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")
    return True


def _migrar_productos(con):
    """Pasa una base de datos antigua al modelo nuevo, sin perder datos:
      - superficies: de un texto JSON ('["madera","interior"]') a filas en
        producto_superficies;
      - precio y stock: de la tabla productos a un formato "galón" por producto,
        y los pedidos antiguos quedan apuntando a ese formato.
    (init_db ya guardó una copia de seguridad en backups/ antes de empezar.)
    Todo ocurre en UNA transacción: si algo falla, la base queda como estaba."""
    c = con.cursor()
    columnas = _columnas(c, "productos")
    if not {"superficies", "precio", "stock"} & set(columnas):
        return  # ya está en el modelo nuevo
    try:
        c.execute("BEGIN IMMEDIATE")
        if "superficies" in columnas:
            filas = c.execute("SELECT id, superficies FROM productos").fetchall()
            for fila in filas:
                try:
                    lista = json.loads(fila["superficies"] or "[]")
                except ValueError:
                    lista = []
                for sup in lista if isinstance(lista, list) else []:
                    if sup in SUPERFICIES:  # palabras desconocidas se descartan
                        c.execute("INSERT OR IGNORE INTO producto_superficies (producto_id, superficie) VALUES (?,?)",
                                  (fila["id"], sup))
            c.execute("ALTER TABLE productos DROP COLUMN superficies")
            print(f"  Migración: superficies de {len(filas)} productos pasadas a producto_superficies")
        if "precio" in columnas:
            stock = "stock" if "stock" in columnas else str(STOCK_INICIAL)  # BD anterior al stock
            n = c.execute(f"""
                INSERT INTO producto_formatos (producto_id, nombre, litros, precio, stock)
                SELECT id, ?, ?, precio, {stock} FROM productos
                WHERE id NOT IN (SELECT producto_id FROM producto_formatos)
            """, (FORMATO_MIGRACION, LITROS_GALON)).rowcount
            # Los pedidos antiguos quedan apuntando al formato de su producto
            c.execute("""
                UPDATE pedido_items
                SET formato = ?,
                    formato_id = (SELECT f.id FROM producto_formatos f
                                  WHERE f.producto_id = pedido_items.producto_id AND f.nombre = ?)
                WHERE formato_id IS NULL
            """, (FORMATO_MIGRACION, FORMATO_MIGRACION))
            for col in ("precio", "stock"):
                if col in columnas:
                    c.execute(f"ALTER TABLE productos DROP COLUMN {col}")
            print(f"  Migración: {n} productos pasaron su precio y stock a un formato '{FORMATO_MIGRACION}'")
        con.commit()
    except sqlite3.Error:
        con.rollback()
        raise


def _seed_productos(con):
    """Carga los productos iniciales solo si la tabla está vacía."""
    c = con.cursor()
    if c.execute("SELECT COUNT(*) FROM productos").fetchone()[0] > 0:
        return

    productos = [
        ("Protección de Madera", "Para muebles, puertas y decks de madera.", 18990, "img/prod-madera.webp", ["madera", "interior"]),
        ("Anticorrosivo Metal Pro", "Para rejas, portones y estructuras de metal.", 21990, "img/prod-metal.webp", ["metal", "exterior"]),
        ("Pinturas para Exterior", "Para fachadas y muros exteriores.", 24990, "img/prod-exterior.webp", ["exterior"]),
        ("Línea Constructoras", "Para proyectos y obras de mayor tamaño.", 29990, "img/prod-constructoras.webp", ["techo", "exterior"]),
        ("Pinturas para Interior", "Para muros y cielos interiores.", 15990, "img/prod-interior.webp", ["interior"]),
        ("Chalk Paint Ecocordi", "Pintura a la tiza para renovar muebles.", 12990, "img/prod-chalk.webp", ["madera", "interior"]),
        ("Productos Especiales", "Para usos específicos: consúltanos cuál sirve para tu trabajo.", 19990, "img/prod-especiales.webp", ["metal", "interior"]),
        ("Impermeabilizante Techo", "Para techos y cubiertas.", 27990, "img/prod-techo.webp", ["techo"]),
    ]
    # Datos de EJEMPLO: cada producto parte con un solo formato "galón".
    # Los precios y formatos reales los carga el admin desde el panel.
    for nombre, desc, precio, imagen, superf in productos:
        pid = c.execute("INSERT INTO productos (nombre, descripcion, imagen) VALUES (?,?,?)",
                        (nombre, desc, imagen)).lastrowid
        c.executemany("INSERT INTO producto_superficies (producto_id, superficie) VALUES (?,?)",
                      [(pid, s) for s in superf])
        c.execute("INSERT INTO producto_formatos (producto_id, nombre, litros, precio, stock) VALUES (?,?,?,?,?)",
                  (pid, FORMATO_MIGRACION, LITROS_GALON, precio, STOCK_INICIAL))
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
    if guardado.startswith(("google$", "eliminada$")):
        return False  # cuenta sin contraseña (entra con Google) o eliminada
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


def _correo_valido(correo):
    """Revisión simple de formato: algo@algo.algo, sin espacios."""
    if " " in correo or correo.count("@") != 1:
        return False
    usuario, dominio = correo.split("@")
    return bool(usuario) and "." in dominio and not dominio.startswith(".") and not dominio.endswith(".")


def _registro_consentimiento():
    """Texto que guardamos como prueba del consentimiento: fecha y versión."""
    return time.strftime("%Y-%m-%d %H:%M:%S") + f" (términos versión {VERSION_TERMINOS})"


def _texto(datos, campo):
    """Lee un campo de texto del JSON; si mandan otra cosa (número, lista...), da ""."""
    valor = datos.get(campo)
    return valor if isinstance(valor, str) else ""


# ------------------------------------------------------------
#  CATÁLOGO: productos con sus superficies y formatos
# ------------------------------------------------------------
def listar_productos(con):
    """Lista de productos tal como la entrega /api/productos:
    {id, nombre, descripcion, imagen, superficies: [...], formatos: [...],
     precio (el del formato más barato), stock (suma de todos los formatos)}."""
    productos = [dict(f) for f in con.execute(
        "SELECT id, nombre, descripcion, imagen FROM productos ORDER BY id")]
    superficies, formatos = {}, {}
    # ORDER BY rowid: las superficies salen en el orden en que se guardaron
    # (la primera define el color de la tarjeta, igual que antes)
    for f in con.execute("SELECT producto_id, superficie FROM producto_superficies ORDER BY rowid"):
        superficies.setdefault(f["producto_id"], []).append(f["superficie"])
    for f in con.execute("""SELECT id, producto_id, nombre, litros, precio, stock
                            FROM producto_formatos ORDER BY litros, id"""):
        formatos.setdefault(f["producto_id"], []).append(
            {"id": f["id"], "nombre": f["nombre"], "litros": f["litros"], "precio": f["precio"], "stock": f["stock"]})
    for p in productos:
        p["superficies"] = superficies.get(p["id"], [])
        p["formatos"] = formatos.get(p["id"], [])
        p["precio"] = min((f["precio"] for f in p["formatos"]), default=None)
        p["stock"] = sum(f["stock"] for f in p["formatos"])
    return productos


def _leer_formato(datos, parcial=False):
    """Valida los datos de un formato. Devuelve (campos, error).
    parcial=True: solo revisa los campos que vengan (para editar)."""
    campos = {}
    if "nombre" in datos or not parcial:
        nombre = _texto(datos, "nombre").strip()
        if not nombre or len(nombre) > MAX_NOMBRE_FORMATO:
            return None, f"El formato necesita un nombre (máximo {MAX_NOMBRE_FORMATO} caracteres)"
        campos["nombre"] = nombre
    if "litros" in datos or not parcial:
        litros = datos.get("litros")
        if type(litros) not in (int, float) or not 0 < litros <= MAX_LITROS:
            return None, f"Litros inválidos (un número mayor que 0 y hasta {MAX_LITROS})"
        campos["litros"] = float(litros)
    for campo, maximo in (("precio", MAX_PRECIO), ("stock", MAX_STOCK)):
        if campo in datos or (not parcial and campo == "precio"):
            valor = datos.get(campo)
            if type(valor) is not int or not 0 <= valor <= maximo:
                return None, f"{campo.capitalize()} inválido (número entero entre 0 y {maximo})"
            campos[campo] = valor
    return campos, None


def _leer_superficies(valor):
    """Lista de superficies válidas, sin repetir y en el orden recibido; None si es inválida."""
    if not isinstance(valor, list) or any(s not in SUPERFICIES for s in valor):
        return None
    return list(dict.fromkeys(valor))


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


def limpiar_fallos_viejos():
    """Borra de la memoria las IP cuyos fallos ya tienen más de 10 minutos.
    Se ejecuta cada minuto: así ninguna IP se guarda más de ~11 minutos."""
    with _fallos_lock:
        for clave in list(_fallos):
            _fallos_recientes(clave)


# ------------------------------------------------------------
#  INICIO DE SESIÓN CON GOOGLE: datos temporales de cada intento
#  Cada vez que alguien aprieta "Continuar con Google" guardamos, por
#  10 minutos y solo en memoria, un "state" (evita CSRF), un "nonce"
#  (evita reusar tokens) y el verificador PKCE (el código de Google no
#  le sirve a quien lo intercepte).
# ------------------------------------------------------------
_google_intentos = {}   # {state: {"nonce", "verificador", "acepta", "volver", "expira"}}
_google_lock = threading.Lock()


def _b64url(datos):
    return base64.urlsafe_b64encode(datos).rstrip(b"=").decode()


def _b64url_decodificar(texto):
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def google_configurado():
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


def _volver_seguro(volver):
    """Solo permitimos volver a páginas propias: así nadie puede usar el sitio
    para redirigir a otra web (open redirect)."""
    if volver and re.fullmatch(r"(index|catalogo)\.html(\?superficie=[a-z]+)?", volver):
        return "/" + volver
    return "/"


def _agregar_param(url, clave, valor):
    return url + ("&" if "?" in url else "?") + urlencode({clave: valor})


def limpiar_google_viejos():
    ahora = time.time()
    with _google_lock:
        for state in [k for k, v in _google_intentos.items() if v["expira"] < ahora]:
            del _google_intentos[state]


def validar_id_token(id_token, nonce):
    """Revisa el "id_token" de Google y devuelve sus datos, o None si algo falla.
    El token llega directo desde el servidor de Google por HTTPS (con certificado
    verificado), así que, según OpenID Connect (sección 3.1.3.7), basta con
    revisar su contenido: emisor, destinatario, vencimiento y nonce."""
    try:
        partes = id_token.split(".")
        if len(partes) != 3:
            return None
        datos = json.loads(_b64url_decodificar(partes[1]))
    except (ValueError, TypeError):
        return None
    if datos.get("iss") not in GOOGLE_EMISORES:
        return None
    if datos.get("aud") != GOOGLE_CLIENT_ID:
        return None
    if not isinstance(datos.get("exp"), (int, float)) or datos["exp"] < time.time():
        return None
    if not nonce or not hmac.compare_digest(str(datos.get("nonce", "")), nonce):
        return None
    if datos.get("email_verified") is not True or not datos.get("sub") or not datos.get("email"):
        return None
    return datos


def _limpieza_periodica():
    while True:
        time.sleep(60)
        limpiar_fallos_viejos()
        limpiar_google_viejos()


def anotar_fallo(clave):
    with _fallos_lock:
        _fallos_recientes(clave)
        _fallos.setdefault(clave, []).append(time.time())


# ------------------------------------------------------------
#  ARCHIVOS PÚBLICOS
#  El servidor solo entrega lo que forma parte de la página. Todo lo demás
#  (la base de datos, los respaldos, server.py, .env, .git...) queda fuera:
#  si no está en esta lista, responde 404.
# ------------------------------------------------------------
CARPETAS_PUBLICAS = {"css", "js", "img", "fonts"}
EXTENSIONES_PUBLICAS = {".css", ".js", ".webp", ".png", ".jpg", ".jpeg", ".svg", ".ico", ".woff2", ".txt"}
RAIZ_PUBLICA = {"robots.txt", "favicon.ico"}  # además de las páginas .html


def archivo_publico(ruta_url):
    """Devuelve la ruta en disco del archivo pedido, o None si no es público."""
    partes = [p for p in ruta_url.split("/") if p]
    if not partes or "\x00" in ruta_url or any(p.startswith(".") or "\\" in p for p in partes):
        return None
    if len(partes) == 1:
        if not (partes[0].endswith(".html") or partes[0] in RAIZ_PUBLICA):
            return None
    elif partes[0] not in CARPETAS_PUBLICAS or os.path.splitext(partes[-1])[1].lower() not in EXTENSIONES_PUBLICAS:
        return None
    archivo = os.path.realpath(os.path.join(BASE, *partes))
    # Aunque haya enlaces simbólicos o "..", el archivo debe quedar DENTRO del proyecto
    if os.path.commonpath([archivo, BASE]) != BASE or not os.path.isfile(archivo):
        return None
    return archivo


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
        if ruta.path == "/api/auth/google/disponible":
            return self._json({"disponible": google_configurado()})
        if ruta.path == "/api/auth/google/iniciar":
            return self._google_iniciar(parse_qs(ruta.query))
        if ruta.path == "/api/auth/google/callback":
            return self._google_callback(parse_qs(ruta.query))
        if ruta.path == "/api/productos":
            superficie = parse_qs(ruta.query).get("superficie", [None])[0]
            con = get_db()
            productos = listar_productos(con)
            con.close()
            if superficie not in (None, "todas"):
                productos = [p for p in productos if superficie in p["superficies"]]
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
        if ruta.path == "/api/cuenta/eliminar":
            return self._eliminar_cuenta()
        if ruta.path == "/api/pedidos":
            return self._crear_pedido(datos)
        if ruta.path == "/api/admin/productos":
            return self._crear_producto(datos)
        if ruta.path.startswith("/api/admin/productos/") and ruta.path.endswith("/formatos"):
            return self._agregar_formato(_id_de_ruta(ruta.path[:-len("/formatos")], "/api/admin/productos/"), datos)

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
            formato_id = _id_de_ruta(ruta.path, "/api/admin/formatos/")
            if formato_id is not None:
                return self._editar_formato(formato_id, datos)
        return self._json({"error": "Ruta no encontrada"}, 404)

    # ---- DELETE ----
    def do_DELETE(self):
        ruta = urlparse(self.path)
        if ruta.path.startswith("/api/admin/"):
            u = self._usuario_actual()
            if not u or not u["es_admin"]:
                return self._json({"error": "Solo administradores"}, 403)
            # Al borrar un producto, sus formatos y superficies se borran con él
            # (ON DELETE CASCADE). Los pedidos antiguos conservan su copia de
            # nombre, formato y precio.
            for prefijo, tabla in (("/api/admin/productos/", "productos"), ("/api/admin/formatos/", "producto_formatos")):
                id_ = _id_de_ruta(ruta.path, prefijo)
                if id_ is not None:
                    con = get_db()
                    borradas = con.execute(f"DELETE FROM {tabla} WHERE id=?", (id_,)).rowcount
                    con.commit()
                    con.close()
                    if not borradas:
                        return self._json({"error": "No existe"}, 404)
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
        if len(nombre) > MAX_NOMBRE or len(correo) > MAX_CORREO or not _correo_valido(correo):
            return self._json({"error": "Revisa tu nombre y tu correo"}, 400)
        # Consentimiento: la casilla debe venir marcada (True, no un texto cualquiera)
        if datos.get("acepta_terminos") is not True:
            return self._json(
                {"error": "Para crear tu cuenta debes aceptar los Términos y la Política de privacidad"}, 400)
        if len(clave) < CLAVE_MINIMA:
            return self._json(
                {"error": f"La contraseña debe tener al menos {CLAVE_MINIMA} caracteres"}, 400)
        con = get_db()
        if con.execute("SELECT 1 FROM usuarios WHERE correo=?", (correo,)).fetchone():
            con.close()
            return self._json({"error": "Ese correo ya está registrado"}, 409)
        cur = con.execute(
            "INSERT INTO usuarios (nombre, correo, clave, terminos_aceptados) VALUES (?,?,?,?)",
            (nombre, correo, hash_clave(clave), _registro_consentimiento()),
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

    def _cookie_de_sesion(self, usuario_id):
        """Crea una sesión en la base de datos y devuelve su cookie."""
        token = secrets.token_hex(32)
        con = get_db()
        con.execute("INSERT INTO sesiones (token, usuario_id) VALUES (?,?)", (token, usuario_id))
        con.commit()
        con.close()
        cookie = f"sesion={token}; HttpOnly; Path=/; SameSite=Lax; Max-Age={DIAS_SESION * 24 * 3600}"
        if COOKIE_SEGURA:
            cookie += "; Secure"
        return cookie

    def _redirigir(self, url, cookies=()):
        """Respuesta 302: el navegador va a "url" (y guarda las cookies)."""
        self.send_response(302)
        self.send_header("Location", url)
        for cookie in cookies:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    # ---- Inicio de sesión con Google ----
    def _google_iniciar(self, params):
        """Paso 1: guarda el intento y manda al navegador a Google."""
        volver = _volver_seguro(params.get("volver", [""])[0])
        if not google_configurado():
            return self._redirigir(_agregar_param(volver, "google", "no_configurado"))
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        verificador = secrets.token_urlsafe(64)  # PKCE
        with _google_lock:
            _google_intentos[state] = {
                "nonce": nonce, "verificador": verificador, "volver": volver,
                "acepta": params.get("acepta", ["0"])[0] == "1",
                "expira": time.time() + GOOGLE_MINUTOS * 60,
            }
        destino = GOOGLE_AUTH_URL + "?" + urlencode({
            "client_id": GOOGLE_CLIENT_ID,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": "openid email profile",   # solo nombre y correo verificado
            "state": state,
            "nonce": nonce,
            "code_challenge": _b64url(hashlib.sha256(verificador.encode()).digest()),
            "code_challenge_method": "S256",
            "prompt": "select_account",
        })
        # La cookie amarra el intento a ESTE navegador (defensa contra CSRF)
        cookie = (f"google_estado={state}; HttpOnly; Path=/api/auth/google; SameSite=Lax; "
                  f"Max-Age={GOOGLE_MINUTOS * 60}" + ("; Secure" if COOKIE_SEGURA else ""))
        return self._redirigir(destino, [cookie])

    def _google_callback(self, params):
        """Paso 2: Google vuelve aquí con un código de un solo uso."""
        borrar = "google_estado=; HttpOnly; Path=/api/auth/google; Max-Age=0"
        state = params.get("state", [""])[0]
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        en_cookie = cookie["google_estado"].value if "google_estado" in cookie else ""
        with _google_lock:
            intento = _google_intentos.pop(state, None) if state else None
        # El state debe existir, no haber vencido y ser el de ESTE navegador
        if (not intento or intento["expira"] < time.time()
                or not en_cookie or not hmac.compare_digest(en_cookie, state)):
            return self._redirigir(_agregar_param("/", "google", "error"), [borrar])
        volver = intento["volver"]
        if params.get("error"):  # la persona canceló en Google
            return self._redirigir(_agregar_param(volver, "google", "cancelado"), [borrar])
        codigo = params.get("code", [""])[0]
        if not codigo:
            return self._redirigir(_agregar_param(volver, "google", "error"), [borrar])

        # Canjeamos el código por el id_token, directo con Google (HTTPS)
        cuerpo = urlencode({
            "code": codigo, "client_id": GOOGLE_CLIENT_ID, "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": GOOGLE_REDIRECT_URI, "grant_type": "authorization_code",
            "code_verifier": intento["verificador"],
        }).encode()
        try:
            pedido = urllib.request.Request(GOOGLE_TOKEN_URL, data=cuerpo, method="POST",
                                            headers={"Content-Type": "application/x-www-form-urlencoded"})
            with urllib.request.urlopen(pedido, timeout=10) as resp:
                respuesta = json.loads(resp.read())
        except (urllib.error.URLError, ValueError, TimeoutError):
            return self._redirigir(_agregar_param(volver, "google", "error"), [borrar])
        datos = validar_id_token(respuesta.get("id_token", ""), intento["nonce"])
        if not datos:
            return self._redirigir(_agregar_param(volver, "google", "error"), [borrar])

        resultado, usuario_id = self._google_cuenta(datos, intento["acepta"])
        if not usuario_id:
            return self._redirigir(_agregar_param(volver, "google", resultado), [borrar])
        return self._redirigir(_agregar_param(volver, "google", resultado),
                               [borrar, self._cookie_de_sesion(usuario_id)])

    def _google_cuenta(self, datos, acepta):
        """Busca o crea la cuenta de quien entró con Google.
        Devuelve (resultado, id_de_usuario) — id None si no puede entrar."""
        sub = str(datos["sub"])
        correo = str(datos["email"]).strip().lower()
        nombre = str(datos.get("name") or correo.split("@")[0]).strip()[:MAX_NOMBRE]
        con = get_db()
        try:
            u = con.execute("SELECT id, es_admin FROM usuarios WHERE google_sub=?", (sub,)).fetchone()
            if not u:
                # ¿Ya tenía cuenta con ese correo? Google lo verificó: la vinculamos
                u = con.execute("SELECT id, es_admin FROM usuarios WHERE correo=?", (correo,)).fetchone()
                if u and not u["es_admin"]:
                    con.execute("UPDATE usuarios SET google_sub=? WHERE id=?", (sub, u["id"]))
                    con.commit()
            if u and u["es_admin"]:
                return "admin", None  # el admin entra solo con su contraseña
            if u:
                return "ok", u["id"]
            # Cuenta nueva: solo si aceptó los Términos y la Política de privacidad
            if not acepta:
                return "necesita_aceptar", None
            cur = con.execute(
                "INSERT INTO usuarios (nombre, correo, clave, terminos_aceptados, google_sub) VALUES (?,?,?,?,?)",
                # Sin contraseña: se guarda una imposible de adivinar (solo entra con Google)
                (nombre, correo, "google$" + secrets.token_hex(32), _registro_consentimiento(), sub),
            )
            con.commit()
            return "nuevo", cur.lastrowid
        finally:
            con.close()

    def _iniciar_sesion(self, usuario_id, nombre, correo, es_admin):
        cookie = self._cookie_de_sesion(usuario_id)
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

    def _eliminar_cuenta(self):
        """Derecho de supresión: borra los datos personales de la cuenta.
        Los pedidos NO se borran (la empresa debe conservar el registro de sus
        ventas), pero quedan desvinculados de la persona: el nombre y el correo
        se reemplazan y la contraseña deja de servir."""
        u = self._usuario_actual()
        if not u:
            return self._json({"error": "No has iniciado sesión"}, 401)
        if u["es_admin"]:
            return self._json({"error": "La cuenta de administrador no se puede eliminar desde aquí"}, 403)
        con = get_db()
        with con:  # una sola transacción
            con.execute("DELETE FROM sesiones WHERE usuario_id=?", (u["id"],))
            con.execute(
                "UPDATE usuarios SET nombre=?, correo=?, clave=?, terminos_aceptados=NULL, google_sub=NULL WHERE id=?",
                ("Cuenta eliminada", f"eliminada-{u['id']}@invalid", "eliminada$" + secrets.token_hex(32), u["id"]),
            )
        con.close()
        return self._json({"ok": True}, set_cookie="sesion=; HttpOnly; Path=/; Max-Age=0")

    def _crear_pedido(self, datos):
        u = self._usuario_actual()
        if not u:
            return self._json({"error": "Debes iniciar sesión para comprar"}, 401)
        items = datos.get("items")
        if not isinstance(items, list):
            return self._json({"error": "Pedido con formato inválido"}, 400)
        if not items:
            return self._json({"error": "El carrito está vacío"}, 400)
        if datos.get("acepta_terminos") is not True:
            return self._json(
                {"error": "Para enviar tu pedido debes aceptar los Términos y la Política de cambios y devoluciones"}, 400)

        # 1) Revisamos que los datos vengan bien (sin tocar la base de datos).
        #    Cada ítem es un FORMATO de venta (formato_id) y una cantidad. No
        #    confiamos en ninguno de los dos: si algo está mal se rechaza todo (400).
        pedido = {}  # {formato_id: cantidad}; junta ids repetidos en uno
        for it in items:
            if not isinstance(it, dict):
                return self._json({"error": "Pedido con formato inválido"}, 400)
            pid = it.get("formato_id")
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
            for fid, cant in pedido.items():
                fmt = con.execute("""
                    SELECT f.id, f.producto_id, f.nombre AS formato, f.precio, f.stock, p.nombre
                    FROM producto_formatos f JOIN productos p ON p.id = f.producto_id
                    WHERE f.id = ?""", (fid,)).fetchone()
                if not fmt:
                    con.rollback()
                    return self._json(
                        {"error": "Uno de los productos ya no existe. Revisa tu carrito."}, 400)
                if fmt["stock"] < cant:
                    con.rollback()  # deshace todo: no se guarda NADA
                    return self._json({
                        "error": f"No hay stock suficiente de «{fmt['nombre']}» ({fmt['formato']}): "
                                 f"pediste {cant} y quedan {fmt['stock']}.",
                        "formato_id": fid,
                        "nombre": fmt["nombre"],
                        "disponible": fmt["stock"],
                    }, 409)
                # El total lo calcula el SERVIDOR con los precios reales
                total += fmt["precio"] * cant
                detalle.append((fmt["producto_id"], fid, fmt["nombre"], fmt["formato"], fmt["precio"], cant))
                con.execute("UPDATE producto_formatos SET stock = stock - ? WHERE id=?", (cant, fid))

            cur = con.execute("INSERT INTO pedidos (usuario_id, total, terminos_aceptados) VALUES (?,?,?)",
                              (u["id"], total, _registro_consentimiento()))
            pedido_id = cur.lastrowid
            con.executemany(
                """INSERT INTO pedido_items (pedido_id, producto_id, formato_id, nombre, formato, precio, cantidad)
                   VALUES (?,?,?,?,?,?,?)""",
                [(pedido_id, *fila) for fila in detalle],
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
                # Devolvemos al stock de cada formato lo que el pedido había descontado
                # (si el formato fue borrado, simplemente no hay dónde sumarlo)
                con.execute("""
                    UPDATE producto_formatos
                    SET stock = stock + (SELECT SUM(i.cantidad) FROM pedido_items i
                                         WHERE i.pedido_id = ? AND i.formato_id = producto_formatos.id)
                    WHERE id IN (SELECT formato_id FROM pedido_items WHERE pedido_id = ?)
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
        """PATCH /api/admin/productos/<id>  {"nombre", "descripcion", "imagen", "superficies"}
        Se puede mandar solo lo que cambia. El precio y el stock se editan en
        cada formato (PATCH /api/admin/formatos/<id>)."""
        cambios = {}
        if "nombre" in datos:
            nombre = _texto(datos, "nombre").strip()
            if not nombre:
                return self._json({"error": "El nombre no puede quedar vacío"}, 400)
            cambios["nombre"] = nombre
        for campo in ("descripcion", "imagen"):
            if campo in datos:
                cambios[campo] = _texto(datos, campo).strip()
        superficies = None
        if "superficies" in datos:
            superficies = _leer_superficies(datos["superficies"])
            if superficies is None:
                return self._json({"error": "Superficies inválidas. Usa: " + ", ".join(SUPERFICIES)}, 400)
        if not cambios and superficies is None:
            return self._json({"error": "No hay nada que cambiar"}, 400)
        con = get_db()
        try:
            con.execute("BEGIN IMMEDIATE")
            if not con.execute("SELECT 1 FROM productos WHERE id=?", (producto_id,)).fetchone():
                con.rollback()
                return self._json({"error": "El producto no existe"}, 404)
            if cambios:
                # Los nombres de columna vienen de nuestra lista fija, no del usuario
                asignaciones = ", ".join(f"{campo}=?" for campo in cambios)
                con.execute(f"UPDATE productos SET {asignaciones} WHERE id=?", (*cambios.values(), producto_id))
            if superficies is not None:
                con.execute("DELETE FROM producto_superficies WHERE producto_id=?", (producto_id,))
                con.executemany("INSERT INTO producto_superficies (producto_id, superficie) VALUES (?,?)",
                                [(producto_id, sup) for sup in superficies])
            con.commit()
        finally:
            con.close()
        return self._json({"ok": True, "id": producto_id})

    def _editar_formato(self, formato_id, datos):
        """PATCH /api/admin/formatos/<id>  {"precio": 19990, "stock": 15}
        También acepta "nombre" y "litros". Se puede mandar solo lo que cambia."""
        cambios, error = _leer_formato(datos, parcial=True)
        if error:
            return self._json({"error": error}, 400)
        if not cambios:
            return self._json({"error": "Indica precio y/o stock"}, 400)
        con = get_db()
        try:
            asignaciones = ", ".join(f"{campo}=?" for campo in cambios)
            cur = con.execute(f"UPDATE producto_formatos SET {asignaciones} WHERE id=?",
                              (*cambios.values(), formato_id))
            con.commit()
        except sqlite3.IntegrityError:
            con.close()
            return self._json({"error": "Este producto ya tiene un formato con ese nombre"}, 409)
        fila = con.execute("SELECT * FROM producto_formatos WHERE id=?", (formato_id,)).fetchone()
        con.close()
        if cur.rowcount == 0:
            return self._json({"error": "El formato no existe"}, 404)
        return self._json({"ok": True, **dict(fila)})

    def _agregar_formato(self, producto_id, datos):
        """POST /api/admin/productos/<id>/formatos  {"nombre", "litros", "precio", "stock"}"""
        u = self._usuario_actual()
        if not u or not u["es_admin"]:
            return self._json({"error": "Solo administradores"}, 403)
        if producto_id is None:
            return self._json({"error": "Ruta no encontrada"}, 404)
        formato, error = _leer_formato(datos)
        if error:
            return self._json({"error": error}, 400)
        con = get_db()
        try:
            if not con.execute("SELECT 1 FROM productos WHERE id=?", (producto_id,)).fetchone():
                return self._json({"error": "El producto no existe"}, 404)
            cur = con.execute(
                "INSERT INTO producto_formatos (producto_id, nombre, litros, precio, stock) VALUES (?,?,?,?,?)",
                (producto_id, formato["nombre"], formato["litros"], formato["precio"], formato.get("stock", 0)))
            con.commit()
            return self._json({"ok": True, "id": cur.lastrowid})
        except sqlite3.IntegrityError:
            return self._json({"error": "Este producto ya tiene un formato con ese nombre"}, 409)
        finally:
            con.close()

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
                "SELECT nombre, formato, precio, cantidad FROM pedido_items WHERE pedido_id=?", (p["id"],)
            ).fetchall()
            p["items"] = [dict(i) for i in items]
            pedidos.append(p)
        con.close()
        return pedidos

    def _crear_producto(self, datos):
        """POST /api/admin/productos
        {"nombre", "descripcion", "imagen", "superficies": [...],
         "formatos": [{"nombre": "galón", "litros": 3.785, "precio": 19990, "stock": 20}, ...]}"""
        u = self._usuario_actual()
        if not u or not u["es_admin"]:
            return self._json({"error": "Solo administradores"}, 403)
        nombre = _texto(datos, "nombre").strip()
        if not nombre:
            return self._json({"error": "El nombre es obligatorio"}, 400)
        superficies = _leer_superficies(datos.get("superficies", []))
        if superficies is None:
            return self._json({"error": "Superficies inválidas. Usa: " + ", ".join(SUPERFICIES)}, 400)
        lista = datos.get("formatos")
        if not isinstance(lista, list) or not lista:
            return self._json({"error": "Agrega al menos un formato con su precio"}, 400)
        formatos = []
        for f in lista:
            formato, error = _leer_formato(f if isinstance(f, dict) else {})
            if error:
                return self._json({"error": error}, 400)
            formatos.append(formato)
        if len({f["nombre"] for f in formatos}) != len(formatos):
            return self._json({"error": "Hay dos formatos con el mismo nombre"}, 400)
        con = get_db()
        try:
            con.execute("BEGIN IMMEDIATE")  # producto, superficies y formatos: todo o nada
            nuevo_id = con.execute(
                "INSERT INTO productos (nombre, descripcion, imagen) VALUES (?,?,?)",
                (nombre, _texto(datos, "descripcion").strip(),
                 _texto(datos, "imagen").strip() or "img/prod-interior.webp"),
            ).lastrowid
            con.executemany("INSERT INTO producto_superficies (producto_id, superficie) VALUES (?,?)",
                            [(nuevo_id, sup) for sup in superficies])
            con.executemany(
                "INSERT INTO producto_formatos (producto_id, nombre, litros, precio, stock) VALUES (?,?,?,?,?)",
                [(nuevo_id, f["nombre"], f["litros"], f["precio"], f.get("stock", 0)) for f in formatos])
            con.commit()
        except sqlite3.Error:
            con.rollback()
            return self._json({"error": "No se pudo guardar el producto"}, 500)
        finally:
            con.close()
        return self._json({"ok": True, "id": nuevo_id})

    # ---- archivos estáticos (HTML, CSS, JS, imágenes) ----
    def _servir_estatico(self, ruta):
        if ruta == "/":
            ruta = "/index.html"
        # Seguridad: solo archivos de la página (nunca la base de datos, .env, .git...)
        archivo = archivo_publico(unquote(ruta))
        if not archivo:
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
    if google_configurado():
        print("  Login con Google:      ACTIVADO")
    else:
        print("  Login con Google:      desactivado (faltan GOOGLE_CLIENT_ID")
        print("                         y GOOGLE_CLIENT_SECRET; ver README)")
    print("  (Para detener el servidor: Ctrl + C)")
    print("=" * 50)
    # Hilo en segundo plano que olvida las IP de intentos fallidos viejos
    threading.Thread(target=_limpieza_periodica, daemon=True).start()
    with Servidor(("", PUERTO), Handler) as httpd:
        httpd.serve_forever()
