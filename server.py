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
import math
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
from xml.sax.saxutils import escape as xml_escape

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
CORREO_EMPRESA = "pinturas@ecocordi.cl"  # correo de contacto público de la empresa
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
MAX_BUSQUEDA = 60         # largo máximo del texto del buscador

# ---- Asistente "¿Qué pintura necesito?" ----
# Ficha técnica de cada producto: con estos datos el asistente elige la pintura.
USOS = ("interior", "exterior", "ambos")          # "ambos" sirve para los dos
ACABADOS = ("mate", "satinado", "brillante")
CONDICIONES = ("humedad", "sol", "normal")        # lo que enfrenta la superficie
MAX_MANOS = 5
MANOS_POR_DEFECTO = 2     # si el producto no dice cuántas manos lleva
MAX_M2 = 10000
# Estas superficies ya dicen si están adentro o afuera (el asistente no lo pregunta)
USO_DE_SUPERFICIE = {"exterior": "exterior", "techo": "exterior", "interior": "interior"}
FRASE_SUPERFICIE = {"madera": "madera", "metal": "metal", "exterior": "muros exteriores y fachadas",
                    "techo": "techos y cubiertas", "interior": "muros y cielos interiores"}
COLUMNAS_FICHA = [
    ("uso", "TEXT CHECK (uso IS NULL OR uso IN ('interior', 'exterior', 'ambos'))"),
    ("acabado", "TEXT CHECK (acabado IS NULL OR acabado IN ('mate', 'satinado', 'brillante'))"),
    ("resiste_humedad", "INTEGER NOT NULL DEFAULT 0 CHECK (resiste_humedad IN (0, 1))"),
    ("resiste_sol", "INTEGER NOT NULL DEFAULT 0 CHECK (resiste_sol IN (0, 1))"),
    ("lavable", "INTEGER NOT NULL DEFAULT 0 CHECK (lavable IN (0, 1))"),
    ("manos_recomendadas", "INTEGER CHECK (manos_recomendadas IS NULL OR manos_recomendadas BETWEEN 1 AND 5)"),
    # 1 = la ficha tiene valores de EJEMPLO que la empresa todavía debe confirmar
    ("ficha_demo", "INTEGER NOT NULL DEFAULT 0 CHECK (ficha_demo IN (0, 1))"),
]
# Fichas de EJEMPLO para los productos iniciales (uso, acabado, humedad, sol,
# lavable, rendimiento m²/L, manos). NO son datos reales de Ecocordi: quedan
# marcadas con ficha_demo = 1 y están listadas en PENDIENTES.md.
FICHAS_DEMO = {
    "Protección de Madera":    ("ambos", "satinado", 1, 1, 0, 10, 2),
    "Anticorrosivo Metal Pro": ("ambos", "brillante", 1, 0, 1, 9, 2),
    "Pinturas para Exterior":  ("exterior", "mate", 1, 1, 1, 10, 2),
    "Línea Constructoras":     ("exterior", "mate", 0, 0, 0, 12, 2),
    "Pinturas para Interior":  ("interior", "mate", 0, 0, 1, 12, 2),
    "Chalk Paint Ecocordi":    ("interior", "mate", 0, 0, 0, 8, 2),
    "Productos Especiales":    ("ambos", "satinado", 1, 0, 1, 10, 2),
    "Impermeabilizante Techo": ("exterior", "mate", 1, 1, 0, 6, 2),
}

# ---- Colores (visualizador y carta de colores) ----
FAMILIAS = {"blancos": "Blancos", "neutros": "Neutros", "calidos": "Cálidos", "frios": "Fríos",
            "verdes": "Verdes", "tierra": "Tierra", "intensos": "Intensos"}
MAX_NOMBRE_COLOR = 40
MAX_CODIGO_COLOR = 12
MAX_FAVORITOS = 60
# Carta de colores de EJEMPLO (es_demo = 1): nombres y códigos propios de
# Ecocordi, inventados para probar el visualizador. NO son la carta oficial:
# la empresa debe reemplazarlos (PENDIENTES.md). Código: EC-<familia><número>.
COLORES_DEMO = {
    "blancos": [("Nieve del Llaima", "#F4F2EC"), ("Bruma de Temuco", "#ECE9E1"), ("Espuma de Lago", "#E9EEEA"),
                ("Harina Tostada", "#EFE4D2"), ("Cal de Adobe", "#E6DDCB"), ("Pétalo Claro", "#F2E9E6")],
    "neutros": [("Piedra Laja", "#CFC8BC"), ("Lino Crudo", "#D9CFBE"), ("Niebla Costera", "#BCC1BF"),
                ("Ceniza Volcánica", "#A5A19A"), ("Canto Rodado", "#8C877E"), ("Grafito Andino", "#4F4E4B")],
    "calidos": [("Mantequilla de Campo", "#F1DDA4"), ("Trigo Maulino", "#E2C48B"), ("Durazno de Huerto", "#EFB38D"),
                ("Arcilla Rosa", "#D69E8A"), ("Miel de Ulmo", "#D6A13F"), ("Atardecer en Talca", "#DD8656")],
    "frios": [("Cielo de Invierno", "#BACCD8"), ("Glaciar Austral", "#9CC2C8"), ("Lavanda de Cerro", "#A9A2C4"),
              ("Lago Villarrica", "#6E98AE"), ("Tormenta del Sur", "#4E5C6C"), ("Azul Pacífico", "#2F5C7B")],
    "verdes": [("Menta de Estero", "#BFD7C5"), ("Salvia Seca", "#A3AF99"), ("Oliva del Valle", "#8A8955"),
               ("Helecho Nativo", "#5D8B60"), ("Musgo de Bosque", "#6A784A"), ("Araucaria", "#3D5A47")],
    "tierra": [("Ocre de Quebrada", "#BF893E"), ("Terracota de Greda", "#B4654A"), ("Greda de Pomaire", "#9C563F"),
               ("Adobe Tostado", "#8B5D45"), ("Café Raulí", "#6A4A37")],
    "intensos": [("Amarillo Aromo", "#E6B425"), ("Rojo Copihue", "#B1263A"), ("Azul Añil", "#27408A"),
                 ("Verde Selva Valdiviana", "#1F6E4A"), ("Carbón de Espino", "#2A2826")],
}
# Qué familias de colores tiene cada producto de ejemplo (también demo)
FAMILIAS_DEMO = {
    "Protección de Madera": ("tierra", "neutros"),
    "Anticorrosivo Metal Pro": ("intensos", "neutros", "blancos"),
    "Pinturas para Exterior": ("blancos", "neutros", "calidos", "frios", "verdes", "tierra"),
    "Línea Constructoras": ("blancos", "neutros", "tierra"),
    "Pinturas para Interior": ("blancos", "neutros", "calidos", "frios", "verdes", "intensos"),
    "Chalk Paint Ecocordi": ("blancos", "neutros", "calidos", "frios", "verdes"),
    "Productos Especiales": ("intensos", "neutros", "blancos"),
    "Impermeabilizante Techo": ("tierra", "neutros"),
}
FAMILIAS_DE_SUPERFICIE = {  # para productos que no están en la lista anterior
    "interior": ("blancos", "neutros", "calidos", "frios", "verdes", "intensos"),
    "exterior": ("blancos", "neutros", "calidos", "frios", "verdes", "tierra"),
    "madera": ("tierra", "neutros", "verdes"), "metal": ("intensos", "neutros", "blancos"),
    "techo": ("tierra", "neutros", "intensos"),
}
LETRA_FAMILIA = {"blancos": "B", "neutros": "N", "calidos": "C", "frios": "F", "verdes": "V",
                 "tierra": "T", "intensos": "I"}

# ---- Checkout (entrega, documento e IVA) ----
TASA_IVA = 19  # IVA en Chile: 19 % (fijado por ley, no es un dato de la empresa)


def _si_no(valor, por_defecto):
    valor = (valor or "").strip().lower()
    if valor in ("1", "si", "sí", "true", "yes"):
        return True
    if valor in ("0", "no", "false"):
        return False
    return por_defecto


# ¿Los precios del catálogo ya incluyen IVA? En Chile, los precios que se
# muestran a consumidores deben incluir los impuestos (Ley 19.496, art. 30),
# por eso el valor por defecto es "sí". La empresa debe confirmarlo (PENDIENTES.md).
PRECIOS_INCLUYEN_IVA = _si_no(os.environ.get("PRECIOS_INCLUYEN_IVA"), True)

# Sucursales para "Retiro en sucursal"
SUCURSALES = {"talca": "Talca", "santiago": "Santiago"}

# Regiones de Chile (para el despacho). La tarifa de cada una la define el
# admin en el panel; si una región no tiene tarifa, se "coordina el despacho".
REGIONES = {
    "arica": "Arica y Parinacota", "tarapaca": "Tarapacá", "antofagasta": "Antofagasta",
    "atacama": "Atacama", "coquimbo": "Coquimbo", "valparaiso": "Valparaíso",
    "metropolitana": "Metropolitana de Santiago", "ohiggins": "Libertador General Bernardo O'Higgins",
    "maule": "Maule", "nuble": "Ñuble", "biobio": "Biobío", "araucania": "La Araucanía",
    "losrios": "Los Ríos", "loslagos": "Los Lagos", "aysen": "Aysén del General Carlos Ibáñez del Campo",
    "magallanes": "Magallanes y de la Antártica Chilena",
}
MAX_TELEFONO = 20
MAX_COMUNA = 60
MAX_DIRECCION = 150
MAX_RAZON_SOCIAL = 100
MAX_GIRO = 80
# Límite de pedidos por IP (evita que alguien "reserve" todo el stock con pedidos falsos)
MAX_PEDIDOS_IP = int(os.environ.get("MAX_PEDIDOS_IP", "10"))
VENTANA_PEDIDOS = 60 * 60  # ...por hora
MAX_LITROS = 1000
# Estados posibles de un pedido (en orden). "cancelado" devuelve el stock.
ESTADOS = ("pendiente", "pagado", "enviado", "entregado", "cancelado")
# Versión de los Términos y la Política de privacidad. Si se cambian esos
# textos, subir esta fecha: así queda registro de QUÉ versión aceptó cada persona.
VERSION_TERMINOS = "2026-09-25.2"  # 2026-09-24.2: login con Google · 2026-09-25: checkout · .2: asistente y visualizador
MAX_NOMBRE = 80           # solo pedimos lo necesario, y con un largo razonable
MAX_CORREO = 254
# En producción con HTTPS: COOKIE_SEGURA=1 python3 server.py
# (la cookie de sesión solo viajará cifrada)
COOKIE_SEGURA = os.environ.get("COOKIE_SEGURA") == "1"

# Dirección pública del sitio, sin "/" al final (ej: https://www.ecocordi.cl).
# Se usa para el sitemap, robots.txt y las etiquetas para compartir en redes
# (Open Graph). Si no está definida, se usa la dirección local.
def _sitio_url(valor):
    valor = valor.strip().rstrip("/")
    return valor if re.fullmatch(r"https?://[A-Za-z0-9.-]+(:\d+)?", valor) else ""


SITIO_URL = _sitio_url(os.environ.get("SITIO_URL", "")) or f"http://localhost:{PUERTO}"
SITIO_CONFIGURADO = bool(_sitio_url(os.environ.get("SITIO_URL", "")))

# Número de WhatsApp de la empresa, con código de país (ej: 56912345678).
# Si no está definido, el botón de WhatsApp no aparece.
WHATSAPP_NUMERO = re.sub(r"[\s+()-]", "", os.environ.get("WHATSAPP_NUMERO", ""))
if not re.fullmatch(r"\d{8,15}", WHATSAPP_NUMERO):
    WHATSAPP_NUMERO = ""

# Inicio de sesión con Google (OAuth 2.0 / OpenID Connect).
# Las credenciales se crean en Google Cloud y NUNCA se escriben en el código:
#   GOOGLE_CLIENT_ID=... GOOGLE_CLIENT_SECRET=... python3 server.py
# Si no están definidas, el botón de Google simplemente no aparece.
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
# Debe coincidir EXACTO con la "URI de redireccionamiento autorizada" en Google Cloud
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI") or f"{SITIO_URL}/api/auth/google/callback"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_EMISORES = ("https://accounts.google.com", "accounts.google.com")
GOOGLE_MINUTOS = 10  # tiempo máximo para completar el inicio de sesión en Google
_DEF_ESTADO = ("TEXT NOT NULL DEFAULT 'pendiente' CHECK (estado IN ("
               + ", ".join(f"'{e}'" for e in ESTADOS) + "))")

# Datos que el checkout guarda en cada pedido. Los pedidos antiguos quedan
# con estas columnas vacías (NULL).
COLUMNAS_CHECKOUT = [
    # Quién compra (con o sin cuenta: si compra como invitado, usuario_id queda NULL)
    ("cliente_nombre", "TEXT"), ("cliente_correo", "TEXT"), ("cliente_telefono", "TEXT"),
    # Entrega: retiro en sucursal o despacho a domicilio
    ("entrega", "TEXT CHECK (entrega IS NULL OR entrega IN ('retiro', 'despacho'))"),
    ("sucursal", "TEXT"), ("region", "TEXT"), ("comuna", "TEXT"), ("direccion", "TEXT"),
    ("costo_despacho", "INTEGER"),  # NULL = "coordinar despacho" (la región no tiene tarifa)
    # Documento tributario
    ("documento", "TEXT CHECK (documento IS NULL OR documento IN ('boleta', 'factura'))"),
    ("factura_rut", "TEXT"), ("factura_razon_social", "TEXT"), ("factura_giro", "TEXT"),
    ("factura_direccion", "TEXT"),
    # Montos (el total ya existía): subtotal de productos, neto e IVA
    ("subtotal", "INTEGER"), ("neto", "INTEGER"), ("iva", "INTEGER"),
    ("precios_incluyen_iva", "INTEGER"),  # cómo se calculó el IVA en ESE momento
]

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
            imagen      TEXT,
            -- Cuántos m² cubre 1 litro en una mano (lo informa la empresa; NULL = sin dato)
            rendimiento_m2_litro REAL CHECK (rendimiento_m2_litro IS NULL OR rendimiento_m2_litro > 0)
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
    # Columnas del checkout (se agregan también a bases de datos antiguas, más abajo)
    for columna, definicion in COLUMNAS_CHECKOUT:
        _agregar_columna(c, "pedidos", columna, definicion)

    # Tarifas de despacho por región (las edita el admin). Si una región no
    # está en esta tabla, el despacho a esa región se coordina con el cliente.
    _regiones = ", ".join(f"'{r}'" for r in REGIONES)
    c.execute(f"""
        CREATE TABLE IF NOT EXISTS tarifas_despacho (
            region TEXT PRIMARY KEY CHECK (region IN ({_regiones})),
            costo  INTEGER NOT NULL CHECK (costo >= 0)
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
    if _agregar_columna(c, "productos", "rendimiento_m2_litro",
                        "REAL CHECK (rendimiento_m2_litro IS NULL OR rendimiento_m2_litro > 0)"):
        print("  Migración: columna 'rendimiento_m2_litro' agregada a productos (sin dato)")
    for columna in ("formato_id INTEGER", "formato TEXT"):
        nombre, tipo = columna.split()
        if _agregar_columna(c, "pedido_items", nombre, tipo):
            print(f"  Migración: columna '{nombre}' agregada a pedido_items")
    # Color elegido en cada ítem (opcional). Igual que el nombre y el formato,
    # se guarda una COPIA del nombre, código y tono: si el color cambia o se
    # borra, el pedido sigue mostrando el que se compró.
    for columna, tipo in (("color_id", "INTEGER"), ("color_nombre", "TEXT"),
                          ("color_codigo", "TEXT"), ("color_hex", "TEXT")):
        _agregar_columna(c, "pedido_items", columna, tipo)
    con.commit()
    _migrar_productos(con)

    # Ficha técnica para el asistente. Si la base ya tenía productos, se les
    # pone una ficha de EJEMPLO (marcada con ficha_demo = 1).
    ficha_nueva = "uso" not in _columnas(c, "productos")
    for columna, definicion in COLUMNAS_FICHA:
        _agregar_columna(c, "productos", columna, definicion)
    if ficha_nueva:
        n = _rellenar_fichas_demo(con)
        if n:
            print(f"  Migración: ficha técnica de EJEMPLO para {n} productos (ver PENDIENTES.md)")

    # Carta de colores y qué colores tiene cada producto (relación "N a N")
    colores_nuevos = not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='colores'").fetchone()
    _familias = ", ".join(f"'{f}'" for f in FAMILIAS)
    c.execute(f"""
        CREATE TABLE IF NOT EXISTS colores (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre  TEXT NOT NULL UNIQUE,
            codigo  TEXT NOT NULL UNIQUE,
            -- "#RRGGBB" en mayúsculas
            hex     TEXT NOT NULL CHECK (length(hex) = 7 AND hex GLOB '#[0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F]'),
            familia TEXT NOT NULL CHECK (familia IN ({_familias})),
            activo  INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1)),
            es_demo INTEGER NOT NULL DEFAULT 0 CHECK (es_demo IN (0, 1))  -- 1 = color de EJEMPLO
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS producto_colores (
            producto_id INTEGER NOT NULL REFERENCES productos(id) ON DELETE CASCADE,
            color_id    INTEGER NOT NULL REFERENCES colores(id) ON DELETE CASCADE,
            PRIMARY KEY (producto_id, color_id)
        )
    """)
    # "Mis colores": favoritos de cada cuenta (se borran si se elimina la cuenta)
    c.execute("""
        CREATE TABLE IF NOT EXISTS colores_favoritos (
            usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
            color_id   INTEGER NOT NULL REFERENCES colores(id) ON DELETE CASCADE,
            agregado   TEXT DEFAULT (datetime('now','localtime')),
            PRIMARY KEY (usuario_id, color_id)
        )
    """)
    con.commit()
    if colores_nuevos:
        n = _seed_colores(con)
        if n:
            print(f"  Carta de colores de EJEMPLO: {n} colores (ver PENDIENTES.md)")

    con.commit()

    # ÍNDICES: como el índice de un libro, permiten encontrar filas sin
    # revisar la tabla completa (por ejemplo, "los pedidos de este usuario").
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_google ON usuarios(google_sub)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_pedidos_usuario ON pedidos(usuario_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_pedidos_estado ON pedidos(estado)")
    # Para vincular pedidos hechos como invitado cuando la persona entra con Google
    c.execute("CREATE INDEX IF NOT EXISTS idx_pedidos_invitado ON pedidos(cliente_correo) WHERE usuario_id IS NULL")
    c.execute("CREATE INDEX IF NOT EXISTS idx_pedido_items_pedido ON pedido_items(pedido_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_sesiones_usuario ON sesiones(usuario_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_sesiones_creada ON sesiones(creada)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_superficies_superficie ON producto_superficies(superficie)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_producto_colores_color ON producto_colores(color_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_colores_familia ON colores(familia)")

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
    _rellenar_fichas_demo(con)
    if con.execute("SELECT COUNT(*) FROM colores").fetchone()[0]:
        _asignar_colores_demo(con)  # base nueva: los colores se crearon antes que los productos


def _seed_colores(con):
    """Carga la carta de colores de EJEMPLO (es_demo = 1) y se la asigna a los
    productos que ya existan. Solo se usa cuando se crea la tabla colores."""
    for familia, lista in COLORES_DEMO.items():
        for i, (nombre, hex_) in enumerate(lista, 1):
            con.execute("INSERT OR IGNORE INTO colores (nombre, codigo, hex, familia, es_demo) VALUES (?,?,?,?,1)",
                        (nombre, f"EC-{LETRA_FAMILIA[familia]}{i:02d}", hex_, familia))
    con.commit()
    _asignar_colores_demo(con)
    return con.execute("SELECT COUNT(*) FROM colores").fetchone()[0]


def _asignar_colores_demo(con):
    """Asigna colores de EJEMPLO a los productos que todavía no tienen ninguno."""
    productos = con.execute("""SELECT id, nombre FROM productos
                               WHERE id NOT IN (SELECT producto_id FROM producto_colores)""").fetchall()
    for p in productos:
        familias = FAMILIAS_DEMO.get(p["nombre"])
        if not familias:
            fila = con.execute("SELECT superficie FROM producto_superficies WHERE producto_id=? ORDER BY rowid",
                               (p["id"],)).fetchone()
            familias = FAMILIAS_DE_SUPERFICIE.get(fila["superficie"] if fila else "", ())
        for familia in familias:
            con.execute("""INSERT OR IGNORE INTO producto_colores (producto_id, color_id)
                           SELECT ?, id FROM colores WHERE familia=? AND es_demo=1""", (p["id"], familia))
    con.commit()


def _ficha_de_ejemplo(nombre, superficies):
    """Ficha de EJEMPLO coherente con el nombre y las superficies del producto:
    (uso, acabado, resiste_humedad, resiste_sol, lavable, rendimiento, manos)."""
    if nombre in FICHAS_DEMO:
        return FICHAS_DEMO[nombre]
    sups = set(superficies)
    if sups and sups <= {"interior"}:
        uso = "interior"
    elif sups and sups <= {"exterior", "techo"}:
        uso = "exterior"
    else:
        uso = "ambos"
    afuera = int(bool(sups & {"exterior", "techo"}))
    return (uso, "satinado", afuera, afuera, int("interior" in sups), 10, MANOS_POR_DEFECTO)


def _rellenar_fichas_demo(con):
    """Pone una ficha técnica de EJEMPLO a todos los productos (ficha_demo = 1).
    Si un producto ya tenía rendimiento (lo cargó el admin), se respeta.
    Solo se usa al crear la base o al agregar las columnas de la ficha."""
    filas = con.execute("SELECT id, nombre FROM productos").fetchall()
    for f in filas:
        sups = [s[0] for s in con.execute(
            "SELECT superficie FROM producto_superficies WHERE producto_id=? ORDER BY rowid", (f["id"],))]
        uso, acabado, humedad, sol, lavable, rendimiento, manos = _ficha_de_ejemplo(f["nombre"], sups)
        con.execute("""
            UPDATE productos SET uso=?, acabado=?, resiste_humedad=?, resiste_sol=?, lavable=?,
                   rendimiento_m2_litro=COALESCE(rendimiento_m2_litro, ?), manos_recomendadas=?, ficha_demo=1
            WHERE id=?""", (uso, acabado, humedad, sol, lavable, rendimiento, manos, f["id"]))
    con.commit()
    return len(filas)


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
    {id, nombre, descripcion, imagen, rendimiento_m2_litro, ficha técnica (uso, acabado,
     resiste_humedad, resiste_sol, lavable, manos_recomendadas, ficha_demo),
     superficies: [...], formatos: [...],
     precio (el del formato más barato), stock (suma de todos los formatos)}."""
    ficha = ", ".join(columna for columna, _ in COLUMNAS_FICHA)
    productos = [dict(f) for f in con.execute(
        f"SELECT id, nombre, descripcion, imagen, rendimiento_m2_litro, {ficha} FROM productos ORDER BY id")]
    superficies, formatos = {}, {}
    # ORDER BY rowid: las superficies salen en el orden en que se guardaron
    # (la primera define el color de la tarjeta, igual que antes)
    for f in con.execute("SELECT producto_id, superficie FROM producto_superficies ORDER BY rowid"):
        superficies.setdefault(f["producto_id"], []).append(f["superficie"])
    for f in con.execute("""SELECT id, producto_id, nombre, litros, precio, stock
                            FROM producto_formatos ORDER BY litros, id"""):
        formatos.setdefault(f["producto_id"], []).append(
            {"id": f["id"], "nombre": f["nombre"], "litros": f["litros"], "precio": f["precio"], "stock": f["stock"]})
    colores = {}
    for f in con.execute("""SELECT pc.producto_id, pc.color_id FROM producto_colores pc
                            JOIN colores c ON c.id = pc.color_id WHERE c.activo = 1 ORDER BY c.id"""):
        colores.setdefault(f["producto_id"], []).append(f["color_id"])
    for p in productos:
        p["superficies"] = superficies.get(p["id"], [])
        p["formatos"] = formatos.get(p["id"], [])
        p["colores"] = colores.get(p["id"], [])  # ids de los colores activos de este producto
        p["precio"] = min((f["precio"] for f in p["formatos"]), default=None)
        p["stock"] = sum(f["stock"] for f in p["formatos"])
    return productos


def listar_colores(con, familia=None, producto_id=None, incluir_inactivos=False):
    """Colores de la carta: {id, nombre, codigo, hex, familia, activo, es_demo, productos: [ids]}."""
    condiciones, params = [], []
    if not incluir_inactivos:
        condiciones.append("c.activo = 1")
    if familia:
        condiciones.append("c.familia = ?")
        params.append(familia)
    if producto_id is not None:
        condiciones.append("c.id IN (SELECT color_id FROM producto_colores WHERE producto_id = ?)")
        params.append(producto_id)
    donde = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""
    colores = [dict(f) for f in con.execute(
        f"SELECT c.id, c.nombre, c.codigo, c.hex, c.familia, c.activo, c.es_demo FROM colores c {donde} ORDER BY c.id",
        params)]
    productos = {}
    for f in con.execute("SELECT color_id, producto_id FROM producto_colores ORDER BY producto_id"):
        productos.setdefault(f["color_id"], []).append(f["producto_id"])
    for c in colores:
        c["productos"] = productos.get(c["id"], [])
    return colores


def _leer_color(datos, parcial=False):
    """Valida los datos de un color que manda el admin. Devuelve (campos, error)."""
    campos = {}
    for campo, maximo in (("nombre", MAX_NOMBRE_COLOR), ("codigo", MAX_CODIGO_COLOR)):
        if campo in datos or not parcial:
            valor = _texto(datos, campo).strip()
            if not valor or len(valor) > maximo:
                return None, f"El color necesita {campo} (máximo {maximo} caracteres)"
            campos[campo] = valor.upper() if campo == "codigo" else valor
    if "hex" in datos or not parcial:
        valor = _texto(datos, "hex").strip().upper()
        if not re.fullmatch(r"#[0-9A-F]{6}", valor):
            return None, "El tono debe ser un color hexadecimal como #A3B09A"
        campos["hex"] = valor
    if "familia" in datos or not parcial:
        if datos.get("familia") not in FAMILIAS:
            return None, "Familia inválida. Usa: " + ", ".join(FAMILIAS)
        campos["familia"] = datos["familia"]
    for campo in ("activo", "es_demo"):
        if campo in datos:
            if not isinstance(datos[campo], bool):
                return None, f"{campo} debe ser true o false"
            campos[campo] = int(datos[campo])
    return campos, None


def color_de_producto(con, color_id, producto_id):
    """El color, solo si está activo y lo tiene ese producto (si no, None)."""
    fila = con.execute("""
        SELECT c.id, c.nombre, c.codigo, c.hex FROM colores c
        JOIN producto_colores pc ON pc.color_id = c.id AND pc.producto_id = ?
        WHERE c.id = ? AND c.activo = 1""", (producto_id, color_id)).fetchone()
    return dict(fila) if fila else None


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


MAX_RENDIMIENTO = 100  # m² por litro (ningún producto rinde más que esto)


def _leer_rendimiento(valor):
    """(rendimiento, error). None es válido: significa "sin dato"."""
    if valor is None:
        return None, None
    if type(valor) not in (int, float) or not 0 < valor <= MAX_RENDIMIENTO:
        return None, f"Rendimiento inválido (m² por litro, mayor que 0 y hasta {MAX_RENDIMIENTO})"
    return float(valor), None


def _leer_superficies(valor):
    """Lista de superficies válidas, sin repetir y en el orden recibido; None si es inválida."""
    if not isinstance(valor, list) or any(s not in SUPERFICIES for s in valor):
        return None
    return list(dict.fromkeys(valor))


def _leer_ficha(datos):
    """Revisa los campos de la ficha técnica que vengan en el JSON del admin.
    Devuelve (cambios, error). Los sí/no llegan como true/false."""
    cambios = {}
    for campo, opciones in (("uso", USOS), ("acabado", ACABADOS)):
        if campo in datos:
            if datos[campo] is not None and datos[campo] not in opciones:
                return None, f"{campo.capitalize()} inválido. Usa: " + ", ".join(opciones) + " (o vacío)"
            cambios[campo] = datos[campo]
    for campo in ("resiste_humedad", "resiste_sol", "lavable", "ficha_demo"):
        if campo in datos:
            if not isinstance(datos[campo], bool):
                return None, f"{campo} debe ser true o false"
            cambios[campo] = int(datos[campo])
    if "manos_recomendadas" in datos:
        manos = datos["manos_recomendadas"]
        if manos is not None and (type(manos) is not int or not 1 <= manos <= MAX_MANOS):
            return None, f"Manos recomendadas inválidas (número entero entre 1 y {MAX_MANOS}, o vacío)"
        cambios["manos_recomendadas"] = manos
    return cambios, None


# ------------------------------------------------------------
#  ASISTENTE "¿QUÉ PINTURA NECESITO?" Y CALCULADORA
#  La misma lógica sirve para las dos: el asistente elige la pintura según
#  reglas simples (sin inteligencia artificial) y la calculadora dice cuántos
#  litros comprar y en qué formatos.
# ------------------------------------------------------------
MAX_PASOS_COMBINACION = 100000  # tope de combinaciones a revisar


def mejor_combinacion(formatos, litros_necesarios):
    """Combinación de formatos más conveniente para cubrir los litros:
    la de menor precio; si empatan, la que sobra menos pintura; y si siguen
    empatadas, la de menos tarros.
    formatos: [(formato, disponibles)]. Devuelve None si el stock no alcanza.
    Prueba cantidades del formato más grande al más chico y descarta los
    caminos que ya son más caros que la mejor opción ("ramificar y podar")."""
    lista = sorted([(f, d) for f, d in formatos if d > 0], key=lambda x: -x[0]["litros"])
    if not lista or sum(f["litros"] * d for f, d in lista) + 1e-9 < litros_necesarios:
        return None
    mejor = None
    pasos = 0
    cantidades = [0] * len(lista)

    def anotar(precio):
        nonlocal mejor
        litros = sum(n * f["litros"] for n, (f, _) in zip(cantidades, lista))
        tarros = sum(cantidades)
        if (mejor is None or precio < mejor["precio"]
                or (precio == mejor["precio"] and (litros < mejor["litros"] - 1e-9
                    or (abs(litros - mejor["litros"]) <= 1e-9 and tarros < mejor["tarros"])))):
            mejor = {"precio": precio, "litros": litros, "tarros": tarros,
                     "items": [(f, n) for n, (f, _) in zip(cantidades, lista) if n > 0]}

    def probar(i, falta, precio):
        nonlocal pasos
        pasos += 1
        if pasos > MAX_PASOS_COMBINACION:
            return
        if falta <= 1e-9:
            anotar(precio)
            return
        if i == len(lista):
            return
        formato, disponibles = lista[i]
        maximo = min(disponibles, math.ceil(falta / formato["litros"] - 1e-9))
        for n in range(maximo, -1, -1):
            nuevo = precio + n * formato["precio"]
            if mejor is not None and nuevo > mejor["precio"]:
                continue  # ya es más caro: no sigue por ahí
            cantidades[i] = n
            probar(i + 1, falta - n * formato["litros"], nuevo)
            if i == len(lista) - 1:
                break  # el formato más chico: solo sirve la cantidad justa
        cantidades[i] = 0

    probar(0, litros_necesarios, 0)
    if mejor is None:
        # Demasiadas combinaciones (un pedido enorme): del más grande al más chico
        falta, items, precio = litros_necesarios, [], 0
        for formato, disponibles in lista:
            n = min(disponibles, math.ceil(falta / formato["litros"] - 1e-9)) if falta > 1e-9 else 0
            if n:
                items.append((formato, n))
                falta -= n * formato["litros"]
                precio += n * formato["precio"]
        mejor = {"precio": precio, "litros": litros_necesarios - falta, "tarros": sum(n for _, n in items),
                 "items": items}
    return mejor


def _disponibles(producto, reservado):
    """[(formato, unidades disponibles)]: el stock menos lo que ya está en el carrito."""
    return [(f, f["stock"] - reservado.get(f["id"], 0)) for f in producto["formatos"]]


def calcular_pintura(producto, m2, manos=None, reservado=None):
    """litros = m² × manos ÷ rendimiento, redondeado hacia arriba (a la décima
    de litro), y la combinación de formatos con stock que los cubre."""
    manos = manos or producto["manos_recomendadas"] or MANOS_POR_DEFECTO
    rendimiento = producto["rendimiento_m2_litro"]
    calculo = {"m2": m2, "manos": manos, "rendimiento": rendimiento, "litros": None, "combinacion": None,
               "ficha_demo": bool(producto.get("ficha_demo"))}
    if not rendimiento:
        return calculo  # sin rendimiento no se puede calcular (no se inventa)
    # El "- 1e-9" evita que un error de decimales convierta 8,0 en 8,1
    calculo["litros"] = math.ceil(m2 * manos / rendimiento * 10 - 1e-9) / 10
    mejor = mejor_combinacion(_disponibles(producto, reservado or {}), calculo["litros"])
    if mejor:
        calculo["combinacion"] = {
            "items": [{"formato_id": f["id"], "nombre": f["nombre"], "litros": f["litros"],
                       "precio": f["precio"], "cantidad": n} for f, n in mejor["items"]],
            "precio": mejor["precio"],
            "litros": round(mejor["litros"], 3),
            "sobrante": round(mejor["litros"] - calculo["litros"], 3),
        }
    return calculo


def _precio_litro(producto, reservado):
    """El precio por litro más bajo entre los formatos con stock (None si no hay stock)."""
    return min((f["precio"] / f["litros"] for f, d in _disponibles(producto, reservado) if d > 0), default=None)


def puntuar(producto, r):
    """Puntaje del producto según las respuestas, y los motivos en lenguaje simple.
    Reglas: humedad + resiste humedad +3 · sol + resiste sol +3 · mismo acabado +2
    ("no sé" le da +1 al satinado) · interior + lavable +1."""
    puntos = 0
    # Primer motivo: pasó el filtro (sirve para esa superficie y ese lugar)
    if r["superficie"] in USO_DE_SUPERFICIE:
        motivos = [f"Es para {FRASE_SUPERFICIE[r['superficie']]}."]
    else:
        motivos = [f"Sirve para {FRASE_SUPERFICIE[r['superficie']]} en {r['uso']}."]
    if r["condicion"] == "humedad" and producto["resiste_humedad"]:
        puntos += 3
        motivos.append("Resiste la humedad: aguanta bien en baños, cocinas o muros que se mojan.")
    if r["condicion"] == "sol" and producto["resiste_sol"]:
        puntos += 3
        motivos.append("Está hecha para el sol directo: el color se mantiene por más tiempo.")
    if r["acabado"] == producto["acabado"]:
        puntos += 2
        motivos.append(f"Tiene el acabado {producto['acabado']} que prefieres.")
    elif r["acabado"] == "no_se" and producto["acabado"] == "satinado":
        puntos += 1
        motivos.append("Su acabado satinado es un buen punto medio: brilla poco y se limpia fácil.")
    if r["uso"] == "interior" and producto["lavable"]:
        puntos += 1
        motivos.append("Es lavable: las manchas salen con un paño húmedo.")
    return puntos, motivos


def recomendar(productos, r, reservado=None):
    """Aplica las reglas del asistente. r = respuestas ya validadas.
    Devuelve {"recomendado", "alternativas", "aviso"}; recomendado None si no hay candidatos."""
    reservado = reservado or {}
    candidatos = []
    for p in productos:
        # Filtro: la superficie, un uso compatible ("ambos" sirve para los dos)
        # y al menos un formato con stock
        if r["superficie"] not in p["superficies"] or p["uso"] not in (r["uso"], "ambos"):
            continue
        precio_litro = _precio_litro(p, reservado)
        if precio_litro is None:
            continue
        puntos, motivos = puntuar(p, r)
        candidatos.append({**p, "puntaje": puntos, "motivos": motivos, "precio_litro": round(precio_litro)})
    # Más puntos primero; si empatan, el más barato por litro
    candidatos.sort(key=lambda c: (-c["puntaje"], c["precio_litro"], c["id"]))

    aviso = None
    elegido = r.get("producto")
    if elegido is not None:
        # Viene del visualizador con un producto ya elegido: va primero si sirve
        preferido = next((c for c in candidatos if c["id"] == elegido), None)
        if preferido:
            candidatos.remove(preferido)
            candidatos.insert(0, preferido)
        else:
            aviso = ("La pintura que elegiste no sirve para lo que vas a pintar o no tiene stock. "
                     "Te mostramos otras opciones.")
    for c in candidatos[:3]:
        if r.get("m2"):
            c["calculo"] = calcular_pintura(c, r["m2"], r.get("manos"), reservado)
    return {"recomendado": candidatos[0] if candidatos else None, "alternativas": candidatos[1:3], "aviso": aviso}


def _numero(texto, entero=False):
    """"12", "12.5" o "12,5" → número; None si no es un número válido."""
    if not re.fullmatch(r"\d{1,6}" if entero else r"\d{1,6}([.,]\d{1,3})?", texto or ""):
        return None
    return int(texto) if entero else float(texto.replace(",", "."))


def leer_carrito_param(texto):
    """"12:2,15:1" (formato_id:cantidad) → {12: 2, 15: 1}; None si es inválido."""
    reservado = {}
    for parte in (texto or "").split(","):
        m = re.fullmatch(r"(\d{1,9}):(\d{1,3})", parte)
        if not m or len(reservado) >= 50:
            return None
        reservado[int(m[1])] = reservado.get(int(m[1]), 0) + int(m[2])
    return reservado


def leer_params(consulta, permitidos, obligatorios=()):
    """Lee la parte ?a=1&b=2 de la dirección. Cada parámetro debe estar en la
    lista permitida y venir una sola vez. Devuelve (params, error)."""
    params = parse_qs(consulta, keep_blank_values=True)
    for nombre, valores in params.items():
        if nombre not in permitidos:
            return None, f"Parámetro desconocido: {nombre}"
        if len(valores) != 1:
            return None, f"El parámetro {nombre} viene repetido"
    params = {k: v[0] for k, v in params.items()}
    for nombre in obligatorios:
        if not params.get(nombre):
            return None, f"Falta el parámetro {nombre}"
    return params, None


def leer_respuestas_asistente(consulta):
    """Valida los parámetros de GET /api/asistente contra listas permitidas.
    Devuelve (respuestas, error)."""
    params, error = leer_params(consulta, ("superficie", "uso", "condicion", "acabado", "m2", "manos",
                                           "producto", "carrito"), ("superficie", "uso"))
    if error:
        return None, error
    r = {"superficie": params["superficie"], "uso": params["uso"],
         "condicion": params.get("condicion", ""), "acabado": params.get("acabado", "")}
    if r["superficie"] not in SUPERFICIES:
        return None, "Superficie inválida. Usa: " + ", ".join(SUPERFICIES)
    if r["uso"] not in ("interior", "exterior"):
        return None, "Uso inválido. Usa: interior o exterior"
    if USO_DE_SUPERFICIE.get(r["superficie"], r["uso"]) != r["uso"]:
        return None, f"La superficie {r['superficie']} es de {USO_DE_SUPERFICIE[r['superficie']]}"
    if "producto" in params:
        r["producto"] = _numero(params["producto"], entero=True)
        if r["producto"] is None:
            return None, "Producto inválido"
        # Con un producto ya elegido, la condición y el acabado son opcionales
        r["condicion"] = r["condicion"] or "normal"
        r["acabado"] = r["acabado"] or "no_se"
    if r["condicion"] not in CONDICIONES:
        return None, "Condición inválida. Usa: " + ", ".join(CONDICIONES)
    if r["acabado"] not in ACABADOS + ("no_se",):
        return None, "Acabado inválido. Usa: " + ", ".join(ACABADOS + ("no_se",))
    if "m2" in params:
        r["m2"] = _numero(params["m2"])
        if r["m2"] is None or not 0 < r["m2"] <= MAX_M2:
            return None, f"Metros cuadrados inválidos (un número mayor que 0 y hasta {MAX_M2})"
    if "manos" in params:
        r["manos"] = _numero(params["manos"], entero=True)
        if r["manos"] is None or not 1 <= r["manos"] <= MAX_MANOS:
            return None, f"Manos inválidas (entre 1 y {MAX_MANOS})"
    r["reservado"] = {}
    if "carrito" in params:
        r["reservado"] = leer_carrito_param(params["carrito"])
        if r["reservado"] is None:
            return None, "Carrito inválido (formato_id:cantidad separados por comas)"
    return r, None


# ------------------------------------------------------------
#  CHECKOUT: validaciones y cálculo de montos
# ------------------------------------------------------------
def normalizar_rut(texto):
    """Revisa un RUT chileno con su dígito verificador (módulo 11).
    Acepta "12.345.678-5", "12345678-5" o "123456785" y devuelve "12345678-5";
    None si el formato o el dígito verificador no calzan."""
    limpio = re.sub(r"[.\s-]", "", texto or "").upper()
    if not re.fullmatch(r"\d{7,8}[\dK]", limpio):
        return None
    cuerpo, dv = limpio[:-1], limpio[-1]
    suma, factor = 0, 2
    for digito in reversed(cuerpo):
        suma += int(digito) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - suma % 11
    esperado = "0" if resto == 11 else "K" if resto == 10 else str(resto)
    return f"{int(cuerpo)}-{dv}" if dv == esperado else None


def normalizar_telefono(texto):
    """Deja solo dígitos (y el + inicial). Entre 8 y 15 dígitos; si no, None."""
    texto = (texto or "").strip()
    digitos = re.sub(r"[\s().-]", "", texto)
    if not re.fullmatch(r"\+?\d{8,15}", digitos):
        return None
    return digitos


def calcular_totales(subtotal, despacho):
    """Neto, IVA y total del pedido (en pesos, sin decimales).
    - Si los precios YA incluyen IVA: el total es la suma y de ahí se separa el IVA.
    - Si NO lo incluyen: la suma es el neto y el IVA se agrega encima.
    El despacho sigue la misma regla que los precios. Si el despacho se
    coordina (None), no se suma todavía."""
    base = subtotal + (despacho or 0)
    if PRECIOS_INCLUYEN_IVA:
        total = base
        neto = (total * 200 + (100 + TASA_IVA)) // (2 * (100 + TASA_IVA))  # redondeo al peso más cercano
        iva = total - neto
    else:
        neto = base
        iva = (neto * TASA_IVA * 2 + 100) // 200
        total = neto + iva
    return {"subtotal": subtotal, "despacho": despacho, "neto": neto, "iva": iva, "total": total}


_pedidos_ip = {}                    # {ip: [hora_pedido1, ...]}
_pedidos_lock = threading.Lock()


def pedidos_recientes_ip(ip, anotar=False):
    """Cuántos pedidos hizo esta IP en la última hora (y, si anotar, suma uno)."""
    with _pedidos_lock:
        limite = time.time() - VENTANA_PEDIDOS
        recientes = [t for t in _pedidos_ip.get(ip, []) if t > limite]
        if anotar:
            recientes.append(time.time())
        if recientes:
            _pedidos_ip[ip] = recientes
        else:
            _pedidos_ip.pop(ip, None)
        return len(recientes)


def limpiar_pedidos_viejos():
    for ip in list(_pedidos_ip):
        pedidos_recientes_ip(ip)


def vincular_pedidos_invitado(con, usuario_id, correo):
    """Los pedidos hechos como invitado con este correo pasan a la cuenta.
    Solo se llama cuando el correo está VERIFICADO (entrar con Google): si no,
    cualquiera podría crear una cuenta con un correo ajeno y ver esos pedidos."""
    return con.execute("UPDATE pedidos SET usuario_id=? WHERE usuario_id IS NULL AND cliente_correo=?",
                       (usuario_id, correo.strip().lower())).rowcount


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
    para redirigir a otra web (open redirect). La dirección se ARMA de nuevo
    solo con lo permitido: la página y los filtros del catálogo."""
    pagina, _, consulta = (volver or "").partition("?")
    if pagina not in ("index.html", "catalogo.html", "pedido.html", "asistente.html", "visualizador.html"):
        return "/"
    params = parse_qs(consulta)
    seguros = {}
    superficie = params.get("superficie", [""])[0]
    if superficie in SUPERFICIES:
        seguros["superficie"] = superficie
    busqueda = params.get("q", [""])[0].strip()
    if busqueda and len(busqueda) <= MAX_BUSQUEDA:
        seguros["q"] = busqueda
    if pagina == "asistente.html":
        # Las respuestas del asistente, solo si son valores conocidos
        for clave, validos in (("uso", ("interior", "exterior")), ("condicion", CONDICIONES),
                               ("acabado", ACABADOS + ("no_se",))):
            if params.get(clave, [""])[0] in validos:
                seguros[clave] = params[clave][0]
        for clave, patron in (("m2", r"\d{1,5}([.,]\d{1,2})?|no"), ("manos", r"[1-5]"), ("producto", r"\d{1,9}"),
                              ("color", r"\d{1,9}")):
            if re.fullmatch(patron, params.get(clave, [""])[0]):
                seguros[clave] = params[clave][0]
    if pagina == "visualizador.html":
        # Ambiente y colores del visualizador (la foto nunca viaja en la dirección)
        for clave, patron in (("modo", r"ambiente|foto"), ("ambiente", r"[a-z]{3,12}"),
                              ("zonas", r"([a-z]{3,12}:\d{1,9},?){1,8}"), ("colores", r"(\d{1,9},?){1,12}"),
                              ("producto", r"\d{1,9}")):
            if re.fullmatch(patron, params.get(clave, [""])[0]):
                seguros[clave] = params[clave][0]
    return "/" + pagina + ("?" + urlencode(seguros) if seguros else "")


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
        limpiar_pedidos_viejos()


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
RAIZ_PUBLICA = {"favicon.ico"}  # además de las páginas .html (robots.txt y sitemap.xml los arma el servidor)

# Páginas que aparecen en el sitemap (las que Google debería mostrar).
# El panel de administración NO va: es privado.
PAGINAS_SITEMAP = ["index.html", "catalogo.html", "asistente.html", "visualizador.html"] + [f"catalogo.html?superficie={s}" for s in SUPERFICIES] + [
    "terminos.html", "privacidad.html", "cookies.html", "devoluciones.html", "creditos.html"]


def generar_robots():
    return ("# Ecocordi: los buscadores pueden ver la tienda, pero no el panel ni la API\n"
            "User-agent: *\n"
            "Allow: /\n"
            "Disallow: /admin.html\n"
            "Disallow: /api/\n\n"
            f"Sitemap: {SITIO_URL}/sitemap.xml\n")


def generar_sitemap():
    """sitemap.xml: la lista de páginas del sitio para los buscadores (Google, Bing...)."""
    urls = []
    for pagina in PAGINAS_SITEMAP:
        archivo = os.path.join(BASE, pagina.split("?")[0])
        if not os.path.isfile(archivo):
            continue
        fecha = time.strftime("%Y-%m-%d", time.localtime(os.path.getmtime(archivo)))
        direccion = SITIO_URL + "/" + ("" if pagina == "index.html" else pagina)
        urls.append(f"  <url><loc>{xml_escape(direccion)}</loc><lastmod>{fecha}</lastmod></url>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + "\n</urlset>\n")


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
        if ruta.path == "/robots.txt":
            return self._texto_plano(generar_robots(), "text/plain; charset=utf-8")
        if ruta.path == "/sitemap.xml":
            return self._texto_plano(generar_sitemap(), "application/xml; charset=utf-8")
        return self._servir_estatico(ruta.path)

    def _texto_plano(self, texto, tipo):
        cuerpo = texto.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def _api_get(self, ruta):
        if ruta.path == "/api/config":
            # Configuración PÚBLICA que necesita la página (nada secreto aquí)
            con = get_db()
            tarifas = {f["region"]: f["costo"] for f in con.execute("SELECT region, costo FROM tarifas_despacho")}
            con.close()
            return self._json({
                "whatsapp": WHATSAPP_NUMERO or None,
                "precios_incluyen_iva": PRECIOS_INCLUYEN_IVA,
                "tasa_iva": TASA_IVA,
                "sucursales": SUCURSALES,
                "regiones": REGIONES,
                "tarifas_despacho": tarifas,  # región sin tarifa = "coordinar despacho"
            })
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
        if ruta.path == "/api/asistente":
            return self._asistente(ruta.query)
        if ruta.path == "/api/colores":
            return self._colores(ruta.query)
        if ruta.path == "/api/mis-colores":
            # Sin sesión no es un error: los favoritos quedan solo en el navegador
            u = self._usuario_actual()
            return self._json({"sesion": bool(u), "colores": self._favoritos(u["id"]) if u else []})
        if ruta.path == "/api/calcular":
            return self._calcular(ruta.query)

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

        if ruta.path == "/api/admin/colores":
            u = self._usuario_actual()
            if not u or not u["es_admin"]:
                return self._json({"error": "Solo administradores"}, 403)
            con = get_db()
            try:
                return self._json(listar_colores(con, incluir_inactivos=True))
            finally:
                con.close()

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
        if ruta.path == "/api/pedidos/cotizar":
            return self._cotizar_pedido(datos)
        if ruta.path == "/api/admin/productos":
            return self._crear_producto(datos)
        if ruta.path == "/api/carrito/item":
            return self._validar_item(datos)
        if ruta.path == "/api/mis-colores":
            return self._guardar_favoritos(datos)
        if ruta.path == "/api/admin/colores":
            return self._crear_color(datos)
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
            color_id = _id_de_ruta(ruta.path, "/api/admin/colores/")
            if color_id is not None:
                return self._editar_color(color_id, datos)
            if ruta.path.startswith("/api/admin/tarifas/"):
                return self._editar_tarifa(ruta.path[len("/api/admin/tarifas/"):], datos)
        return self._json({"error": "Ruta no encontrada"}, 404)

    # ---- DELETE ----
    def do_DELETE(self):
        ruta = urlparse(self.path)
        color_id = _id_de_ruta(ruta.path, "/api/mis-colores/")
        if color_id is not None:
            u = self._usuario_actual()
            if not u:
                return self._json({"error": "No has iniciado sesión"}, 401)
            con = get_db()
            with con:
                con.execute("DELETE FROM colores_favoritos WHERE usuario_id=? AND color_id=?", (u["id"], color_id))
            con.close()
            return self._json({"ok": True, "sesion": True, "colores": self._favoritos(u["id"])})
        if ruta.path.startswith("/api/admin/"):
            u = self._usuario_actual()
            if not u or not u["es_admin"]:
                return self._json({"error": "Solo administradores"}, 403)
            # Al borrar un producto, sus formatos y superficies se borran con él
            # (ON DELETE CASCADE). Los pedidos antiguos conservan su copia de
            # nombre, formato y precio.
            # Al borrar un color, sale de los productos y de los favoritos (los pedidos guardan su copia)
            for prefijo, tabla in (("/api/admin/productos/", "productos"), ("/api/admin/formatos/", "producto_formatos"),
                                   ("/api/admin/colores/", "colores")):
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
    def _asistente(self, consulta):
        """GET /api/asistente?superficie=madera&uso=exterior&condicion=sol&acabado=mate&m2=40&manos=2
        Recomienda una pintura y hasta 2 alternativas, con sus motivos. Si viene m2,
        calcula los litros y la combinación de formatos más conveniente."""
        r, error = leer_respuestas_asistente(consulta)
        if error:
            return self._json({"error": error}, 400)
        con = get_db()
        try:
            productos = listar_productos(con)
        finally:
            con.close()
        resultado = recomendar(productos, r, r["reservado"])
        respuesta = {"respuestas": {k: v for k, v in r.items() if k != "reservado"}, **resultado}
        if not resultado["recomendado"]:
            respuesta["mensaje"] = ("Por ahora no tenemos una pintura en stock para lo que vas a pintar. "
                                    "Escríbenos o visítanos en una sucursal y te ayudamos a encontrar una.")
            respuesta["whatsapp"] = WHATSAPP_NUMERO or None
            respuesta["sucursales"] = list(SUCURSALES.values())
        return self._json(respuesta)

    def _colores(self, consulta):
        """GET /api/colores?familia=verdes&producto=5 — carta de colores (solo activos)."""
        params, error = leer_params(consulta, ("familia", "producto"))
        if error:
            return self._json({"error": error}, 400)
        familia = params.get("familia") or None
        if familia is not None and familia not in FAMILIAS:
            return self._json({"error": "Familia inválida. Usa: " + ", ".join(FAMILIAS)}, 400)
        producto_id = None
        if params.get("producto"):
            producto_id = _numero(params["producto"], entero=True)
            if producto_id is None:
                return self._json({"error": "Producto inválido"}, 400)
        con = get_db()
        try:
            return self._json({"familias": FAMILIAS, "colores": listar_colores(con, familia, producto_id)})
        finally:
            con.close()

    def _validar_item(self, datos):
        """POST /api/carrito/item  {"formato_id", "color_id" (opcional), "cantidad"}
        Revisa ANTES de agregar al carrito que el formato exista y que el color
        corresponda a ese producto. Devuelve los datos actuales del ítem."""
        fid, color_id, cantidad = datos.get("formato_id"), datos.get("color_id"), datos.get("cantidad", 1)
        if type(fid) is not int or (color_id is not None and type(color_id) is not int):
            return self._json({"error": "Ítem inválido"}, 400)
        if type(cantidad) is not int or not 1 <= cantidad <= MAX_CANTIDAD:
            return self._json({"error": f"Cantidad inválida (entre 1 y {MAX_CANTIDAD})"}, 400)
        con = get_db()
        try:
            fmt = con.execute("""
                SELECT f.id, f.producto_id, f.nombre AS formato, f.precio, f.stock, p.nombre, p.imagen
                FROM producto_formatos f JOIN productos p ON p.id = f.producto_id WHERE f.id = ?""", (fid,)).fetchone()
            if not fmt:
                return self._json({"error": "Ese formato ya no existe"}, 404)
            color = None
            if color_id is not None:
                color = color_de_producto(con, color_id, fmt["producto_id"])
                if not color:
                    return self._json({"error": f"Ese color no está disponible para «{fmt['nombre']}»"}, 400)
            if fmt["stock"] < cantidad:
                return self._json({"error": f"Solo quedan {fmt['stock']} de «{fmt['nombre']}» ({fmt['formato']})",
                                   "disponible": fmt["stock"]}, 409)
        finally:
            con.close()
        return self._json({"ok": True, "formato_id": fid, "producto_id": fmt["producto_id"], "nombre": fmt["nombre"],
                           "formato": fmt["formato"], "precio": fmt["precio"], "stock": fmt["stock"],
                           "imagen": fmt["imagen"], "color": color})

    def _favoritos(self, usuario_id):
        con = get_db()
        try:
            return [f["color_id"] for f in con.execute("""
                SELECT f.color_id FROM colores_favoritos f JOIN colores c ON c.id = f.color_id
                WHERE f.usuario_id = ? AND c.activo = 1 ORDER BY f.agregado, f.rowid""", (usuario_id,))]
        finally:
            con.close()

    def _guardar_favoritos(self, datos):
        """POST /api/mis-colores  {"colores": [ids]} — agrega (sin repetir) a "Mis colores".
        Sirve también para subir los favoritos que la persona guardó antes de entrar."""
        u = self._usuario_actual()
        if not u:
            return self._json({"error": "No has iniciado sesión"}, 401)
        ids = datos.get("colores")
        if not isinstance(ids, list) or not ids or len(ids) > MAX_FAVORITOS or any(type(i) is not int for i in ids):
            return self._json({"error": "Envía una lista de colores"}, 400)
        con = get_db()
        try:
            con.execute("BEGIN IMMEDIATE")
            actuales = con.execute("SELECT COUNT(*) FROM colores_favoritos WHERE usuario_id=?", (u["id"],)).fetchone()[0]
            for color_id in dict.fromkeys(ids):
                if actuales >= MAX_FAVORITOS:
                    break
                actuales += con.execute("""INSERT OR IGNORE INTO colores_favoritos (usuario_id, color_id)
                                           SELECT ?, id FROM colores WHERE id=? AND activo=1""",
                                        (u["id"], color_id)).rowcount
            con.commit()
        finally:
            con.close()
        return self._json({"ok": True, "sesion": True, "colores": self._favoritos(u["id"])})

    def _crear_color(self, datos):
        """POST /api/admin/colores  {"nombre", "codigo", "hex", "familia", "activo", "es_demo", "productos": [ids]}"""
        u = self._usuario_actual()
        if not u or not u["es_admin"]:
            return self._json({"error": "Solo administradores"}, 403)
        campos, error = _leer_color(datos)
        if error:
            return self._json({"error": error}, 400)
        productos = datos.get("productos", [])
        if not isinstance(productos, list) or any(type(i) is not int for i in productos):
            return self._json({"error": "Productos inválidos"}, 400)
        con = get_db()
        try:
            con.execute("BEGIN IMMEDIATE")
            cur = con.execute(f"INSERT INTO colores ({', '.join(campos)}) VALUES ({', '.join('?' for _ in campos)})",
                              tuple(campos.values()))
            con.executemany("INSERT OR IGNORE INTO producto_colores (producto_id, color_id) "
                            "SELECT id, ? FROM productos WHERE id=?", [(cur.lastrowid, pid) for pid in productos])
            con.commit()
            return self._json({"ok": True, "id": cur.lastrowid})
        except sqlite3.IntegrityError:
            con.rollback()
            return self._json({"error": "Ya existe un color con ese nombre o código"}, 409)
        finally:
            con.close()

    def _editar_color(self, color_id, datos):
        """PATCH /api/admin/colores/<id> — solo lo que cambia; "productos": [ids] reemplaza la asignación."""
        campos, error = _leer_color(datos, parcial=True)
        if error:
            return self._json({"error": error}, 400)
        productos = datos.get("productos")
        if productos is not None and (not isinstance(productos, list) or any(type(i) is not int for i in productos)):
            return self._json({"error": "Productos inválidos"}, 400)
        if not campos and productos is None:
            return self._json({"error": "No hay nada que cambiar"}, 400)
        con = get_db()
        try:
            con.execute("BEGIN IMMEDIATE")
            if not con.execute("SELECT 1 FROM colores WHERE id=?", (color_id,)).fetchone():
                con.rollback()
                return self._json({"error": "El color no existe"}, 404)
            if campos:
                asignaciones = ", ".join(f"{campo}=?" for campo in campos)  # nombres de nuestra lista fija
                con.execute(f"UPDATE colores SET {asignaciones} WHERE id=?", (*campos.values(), color_id))
            if productos is not None:
                con.execute("DELETE FROM producto_colores WHERE color_id=?", (color_id,))
                con.executemany("INSERT OR IGNORE INTO producto_colores (producto_id, color_id) "
                                "SELECT id, ? FROM productos WHERE id=?", [(color_id, pid) for pid in productos])
            con.commit()
        except sqlite3.IntegrityError:
            con.rollback()
            return self._json({"error": "Ya existe un color con ese nombre o código"}, 409)
        finally:
            con.close()
        return self._json({"ok": True, "id": color_id})

    def _calcular(self, consulta):
        """GET /api/calcular?producto=5&m2=40&manos=2 — la calculadora del catálogo.
        Usa exactamente el mismo cálculo que el asistente (calcular_pintura)."""
        params, error = leer_params(consulta, ("producto", "m2", "manos", "carrito"), ("producto", "m2"))
        if error:
            return self._json({"error": error}, 400)
        producto_id = _numero(params["producto"], entero=True)
        m2 = _numero(params["m2"])
        manos = _numero(params["manos"], entero=True) if "manos" in params else None
        reservado = leer_carrito_param(params["carrito"]) if "carrito" in params else {}
        if producto_id is None:
            return self._json({"error": "Producto inválido"}, 400)
        if m2 is None or not 0 < m2 <= MAX_M2:
            return self._json({"error": f"Metros cuadrados inválidos (un número mayor que 0 y hasta {MAX_M2})"}, 400)
        if "manos" in params and (manos is None or not 1 <= manos <= MAX_MANOS):
            return self._json({"error": f"Manos inválidas (entre 1 y {MAX_MANOS})"}, 400)
        if reservado is None:
            return self._json({"error": "Carrito inválido (formato_id:cantidad separados por comas)"}, 400)
        con = get_db()
        try:
            producto = next((p for p in listar_productos(con) if p["id"] == producto_id), None)
        finally:
            con.close()
        if not producto:
            return self._json({"error": "El producto no existe"}, 404)
        return self._json({"producto_id": producto_id, "nombre": producto["nombre"],
                           **calcular_pintura(producto, m2, manos, reservado)})

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
        con.execute("INSERT INTO sesiones (token, usuario_id, creada) VALUES (?, ?, datetime('now','localtime'))", (token, usuario_id))
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
                # Google verificó el correo: sus compras como invitado pasan a la cuenta
                if vincular_pedidos_invitado(con, u["id"], correo):
                    con.commit()
                return "ok", u["id"]
            # Cuenta nueva: solo si aceptó los Términos y la Política de privacidad
            if not acepta:
                return "necesita_aceptar", None
            cur = con.execute(
                "INSERT INTO usuarios (nombre, correo, clave, terminos_aceptados, google_sub) VALUES (?,?,?,?,?)",
                # Sin contraseña: se guarda una imposible de adivinar (solo entra con Google)
                (nombre, correo, "google$" + secrets.token_hex(32), _registro_consentimiento(), sub),
            )
            vincular_pedidos_invitado(con, cur.lastrowid, correo)
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
            con.execute("DELETE FROM colores_favoritos WHERE usuario_id=?", (u["id"],))
            con.execute(
                "UPDATE usuarios SET nombre=?, correo=?, clave=?, terminos_aceptados=NULL, google_sub=NULL WHERE id=?",
                ("Cuenta eliminada", f"eliminada-{u['id']}@invalid", "eliminada$" + secrets.token_hex(32), u["id"]),
            )
            # En sus pedidos borramos los datos de contacto y la dirección de
            # despacho. Quedan la comuna, la región y los datos de la factura
            # (la empresa debe conservar sus documentos tributarios).
            con.execute("""UPDATE pedidos SET cliente_nombre='Cuenta eliminada', cliente_correo=NULL,
                           cliente_telefono=NULL, direccion=NULL WHERE usuario_id=?""", (u["id"],))
        con.close()
        return self._json({"ok": True}, set_cookie="sesion=; HttpOnly; Path=/; Max-Age=0")

    # ---- Checkout ----
    def _leer_checkout(self, datos, u):
        """Revisa TODO lo que manda el checkout, sin tocar la base de datos.
        Devuelve (checkout, None) o (None, (mensaje, código_http))."""
        items = datos.get("items")
        if not isinstance(items, list):
            return None, ("Pedido con formato inválido", 400)
        if not items:
            return None, ("El carrito está vacío", 400)

        # Cada ítem es un FORMATO de venta (formato_id), un color opcional
        # (color_id) y una cantidad. No confiamos en ninguno: si algo está mal
        # se rechaza todo.
        pedido = {}  # {(formato_id, color_id): cantidad}; junta ítems repetidos en uno
        for it in items:
            if not isinstance(it, dict):
                return None, ("Pedido con formato inválido", 400)
            fid = it.get("formato_id")
            cant = it.get("cantidad")
            color = it.get("color_id")
            # type(...) is int deja fuera textos ("abc"), decimales (1.5) y True/False
            if type(fid) is not int or (color is not None and type(color) is not int):
                return None, ("Pedido con formato inválido", 400)
            if type(cant) is not int or not 1 <= cant <= MAX_CANTIDAD:
                return None, (f"Cantidad inválida (debe ser un número entre 1 y {MAX_CANTIDAD})", 400)
            pedido[(fid, color)] = pedido.get((fid, color), 0) + cant

        # Quién compra. Con cuenta, el correo es el de la cuenta.
        cliente = datos.get("cliente") if isinstance(datos.get("cliente"), dict) else {}
        nombre = _texto(cliente, "nombre").strip()
        correo = u["correo"] if u else _texto(cliente, "correo").strip().lower()
        telefono = normalizar_telefono(_texto(cliente, "telefono"))
        if not nombre or len(nombre) > MAX_NOMBRE:
            return None, ("Escribe tu nombre", 400)
        if len(correo) > MAX_CORREO or not _correo_valido(correo):
            return None, ("Escribe un correo válido", 400)
        if not telefono:
            return None, ("Escribe un teléfono válido (entre 8 y 15 dígitos)", 400)

        # Entrega: retiro en sucursal o despacho a domicilio
        entrega = datos.get("entrega") if isinstance(datos.get("entrega"), dict) else {}
        tipo_entrega = entrega.get("tipo")
        checkout_entrega = {"entrega": tipo_entrega, "sucursal": None, "region": None, "comuna": None, "direccion": None}
        if tipo_entrega == "retiro":
            if entrega.get("sucursal") not in SUCURSALES:
                return None, ("Elige la sucursal donde retirarás", 400)
            checkout_entrega["sucursal"] = entrega["sucursal"]
        elif tipo_entrega == "despacho":
            comuna = _texto(entrega, "comuna").strip()
            direccion = _texto(entrega, "direccion").strip()
            if entrega.get("region") not in REGIONES:
                return None, ("Elige la región de despacho", 400)
            if not comuna or len(comuna) > MAX_COMUNA:
                return None, ("Escribe la comuna de despacho", 400)
            if not direccion or len(direccion) > MAX_DIRECCION:
                return None, (f"Escribe la dirección de despacho (máximo {MAX_DIRECCION} caracteres)", 400)
            checkout_entrega.update(region=entrega["region"], comuna=comuna, direccion=direccion)
        else:
            return None, ("Elige cómo quieres recibir tu pedido: retiro en sucursal o despacho", 400)

        # Documento: boleta o factura (con datos de la empresa que compra)
        documento = datos.get("documento") if isinstance(datos.get("documento"), dict) else {}
        tipo_documento = documento.get("tipo")
        factura = {"factura_rut": None, "factura_razon_social": None, "factura_giro": None, "factura_direccion": None}
        if tipo_documento == "factura":
            rut = normalizar_rut(_texto(documento, "rut"))
            razon = _texto(documento, "razon_social").strip()
            giro = _texto(documento, "giro").strip()
            direccion_f = _texto(documento, "direccion").strip()
            if not rut:
                return None, ("El RUT de la factura no es válido: revisa el número y el dígito verificador", 400)
            if not razon or len(razon) > MAX_RAZON_SOCIAL:
                return None, ("Escribe la razón social para la factura", 400)
            if not giro or len(giro) > MAX_GIRO:
                return None, ("Escribe el giro para la factura", 400)
            if not direccion_f or len(direccion_f) > MAX_DIRECCION:
                return None, ("Escribe la dirección para la factura", 400)
            factura = {"factura_rut": rut, "factura_razon_social": razon, "factura_giro": giro,
                       "factura_direccion": direccion_f}
        elif tipo_documento != "boleta":
            return None, ("Elige boleta o factura", 400)

        return {"items": pedido, "cliente_nombre": nombre, "cliente_correo": correo, "cliente_telefono": telefono,
                **checkout_entrega, "documento": tipo_documento, **factura}, None

    def _calcular_pedido(self, con, checkout):
        """Dentro de una transacción: revisa stock y calcula montos con los
        precios y tarifas REALES de la base de datos. Devuelve (resumen, None)
        o (None, (datos_de_error, código_http))."""
        subtotal = 0
        detalle = []
        # El stock es del FORMATO: 2 galones blancos y 1 azul son 3 galones
        por_formato = {}
        for (fid, _), cant in checkout["items"].items():
            por_formato[fid] = por_formato.get(fid, 0) + cant
        for (fid, color_id), cant in checkout["items"].items():
            fmt = con.execute("""
                SELECT f.id, f.producto_id, f.nombre AS formato, f.precio, f.stock, p.nombre
                FROM producto_formatos f JOIN productos p ON p.id = f.producto_id
                WHERE f.id = ?""", (fid,)).fetchone()
            if not fmt:
                return None, ({"error": "Uno de los productos ya no existe. Revisa tu carrito."}, 400)
            color = None
            if color_id is not None:
                color = color_de_producto(con, color_id, fmt["producto_id"])
                if not color:
                    return None, ({"error": f"Uno de los colores no está disponible para «{fmt['nombre']}». "
                                            "Revisa tu carrito.", "formato_id": fid, "color_id": color_id}, 400)
            if fmt["stock"] < por_formato[fid]:
                return None, ({
                    "error": f"No hay stock suficiente de «{fmt['nombre']}» ({fmt['formato']}): "
                             f"pediste {por_formato[fid]} y quedan {fmt['stock']}.",
                    "formato_id": fid,
                    "nombre": fmt["nombre"],
                    "disponible": fmt["stock"],
                }, 409)
            subtotal += fmt["precio"] * cant
            detalle.append({"producto_id": fmt["producto_id"], "formato_id": fid, "nombre": fmt["nombre"],
                            "formato": fmt["formato"], "precio": fmt["precio"], "cantidad": cant,
                            "color_id": color["id"] if color else None,
                            "color_nombre": color["nombre"] if color else None,
                            "color_codigo": color["codigo"] if color else None,
                            "color_hex": color["hex"] if color else None})
        despacho = 0  # retiro en sucursal: sin costo
        if checkout["entrega"] == "despacho":
            fila = con.execute("SELECT costo FROM tarifas_despacho WHERE region=?", (checkout["region"],)).fetchone()
            despacho = fila["costo"] if fila else None  # sin tarifa: se coordina
        totales = calcular_totales(subtotal, despacho)
        return {"items": detalle, **totales, "despacho_por_coordinar": despacho is None,
                "precios_incluyen_iva": PRECIOS_INCLUYEN_IVA, "tasa_iva": TASA_IVA}, None

    def _cotizar_pedido(self, datos):
        """POST /api/pedidos/cotizar: mismo cálculo que al comprar, pero sin
        guardar nada. El checkout lo usa para mostrar el resumen final."""
        checkout, error = self._leer_checkout(datos, self._usuario_actual())
        if error:
            return self._json({"error": error[0]}, error[1])
        con = get_db()
        try:
            resumen, error = self._calcular_pedido(con, checkout)
        finally:
            con.close()
        if error:
            return self._json(error[0], error[1])
        return self._json(resumen)

    def _crear_pedido(self, datos):
        """POST /api/pedidos: con cuenta o como invitado."""
        u = self._usuario_actual()
        if datos.get("acepta_terminos") is not True:
            return self._json(
                {"error": "Para enviar tu pedido debes aceptar los Términos y la Política de cambios y devoluciones"}, 400)
        checkout, error = self._leer_checkout(datos, u)
        if error:
            return self._json({"error": error[0]}, error[1])
        ip = self.client_address[0]
        if pedidos_recientes_ip(ip) >= MAX_PEDIDOS_IP:
            return self._json({"error": "Recibimos muchos pedidos desde tu conexión en la última hora. "
                                        f"Escríbenos a {CORREO_EMPRESA} y te ayudamos."}, 429)

        # TRANSACCIÓN: revisar stock, descontarlo y guardar el pedido ocurre
        # "todo o nada". BEGIN IMMEDIATE reserva la base de datos para
        # escribir: si dos personas compran el último tarro al mismo tiempo,
        # la segunda ESPERA a que la primera termine y recién ahí lee el stock
        # (que ya será 0). Así nunca se vende de más.
        con = get_db()
        try:
            con.execute("BEGIN IMMEDIATE")
            resumen, error = self._calcular_pedido(con, checkout)
            if error:
                con.rollback()  # deshace todo: no se guarda NADA
                return self._json(error[0], error[1])
            for item in resumen["items"]:
                con.execute("UPDATE producto_formatos SET stock = stock - ? WHERE id=?",
                            (item["cantidad"], item["formato_id"]))
            columnas = {
                "usuario_id": u["id"] if u else None,
                "total": resumen["total"], "subtotal": resumen["subtotal"], "neto": resumen["neto"],
                "iva": resumen["iva"], "costo_despacho": resumen["despacho"],
                "precios_incluyen_iva": 1 if PRECIOS_INCLUYEN_IVA else 0,
                "terminos_aceptados": _registro_consentimiento(),
                **{k: v for k, v in checkout.items() if k != "items"},
            }
            # Los nombres de columna vienen de nuestro propio diccionario, no del usuario
            cur = con.execute(
                f"INSERT INTO pedidos ({', '.join(columnas)}) VALUES ({', '.join('?' for _ in columnas)})",
                tuple(columnas.values()))
            pedido_id = cur.lastrowid
            con.executemany(
                """INSERT INTO pedido_items (pedido_id, producto_id, formato_id, nombre, formato, precio, cantidad,
                                            color_id, color_nombre, color_codigo, color_hex)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                [(pedido_id, i["producto_id"], i["formato_id"], i["nombre"], i["formato"], i["precio"], i["cantidad"],
                  i["color_id"], i["color_nombre"], i["color_codigo"], i["color_hex"])
                 for i in resumen["items"]],
            )
            con.commit()  # recién aquí los cambios quedan guardados de verdad
        except sqlite3.Error:
            con.rollback()
            return self._json({"error": "No se pudo guardar el pedido. Inténtalo de nuevo."}, 500)
        finally:
            con.close()
        pedidos_recientes_ip(ip, anotar=True)
        return self._json({"ok": True, "pedido_id": pedido_id, "invitado": u is None,
                           **{k: v for k, v in resumen.items() if k != "items"}})

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
        """PATCH /api/admin/productos/<id>  {"nombre", "descripcion", "imagen", "superficies", "rendimiento_m2_litro",
        y la ficha técnica: "uso", "acabado", "resiste_humedad", "resiste_sol", "lavable",
        "manos_recomendadas", "ficha_demo"}
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
        if "rendimiento_m2_litro" in datos:
            rendimiento, error = _leer_rendimiento(datos["rendimiento_m2_litro"])
            if error:
                return self._json({"error": error}, 400)
            cambios["rendimiento_m2_litro"] = rendimiento
        ficha, error = _leer_ficha(datos)
        if error:
            return self._json({"error": error}, 400)
        cambios.update(ficha)
        superficies = None
        if "superficies" in datos:
            superficies = _leer_superficies(datos["superficies"])
            if superficies is None:
                return self._json({"error": "Superficies inválidas. Usa: " + ", ".join(SUPERFICIES)}, 400)
        colores = None
        if "colores" in datos:
            colores = datos["colores"]
            if not isinstance(colores, list) or any(type(i) is not int for i in colores):
                return self._json({"error": "Colores inválidos (lista de ids)"}, 400)
        if not cambios and superficies is None and colores is None:
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
            if colores is not None:
                con.execute("DELETE FROM producto_colores WHERE producto_id=?", (producto_id,))
                con.executemany("INSERT OR IGNORE INTO producto_colores (producto_id, color_id) "
                                "SELECT ?, id FROM colores WHERE id=?", [(producto_id, cid) for cid in colores])
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
        """Pedidos con su detalle. usuario_id=None: todos (para el admin)."""
        campos = ("p.id, p.total, p.fecha, p.estado, p.usuario_id, "
                  + ", ".join("p." + c for c, _ in COLUMNAS_CHECKOUT))
        con = get_db()
        if usuario_id is None:  # admin: todos los pedidos
            filas = con.execute(f"""
                SELECT {campos}, u.nombre AS cuenta_nombre, u.correo AS cuenta_correo
                FROM pedidos p LEFT JOIN usuarios u ON u.id = p.usuario_id
                ORDER BY p.id DESC
            """).fetchall()
        else:
            filas = con.execute(f"SELECT {campos} FROM pedidos p WHERE p.usuario_id=? ORDER BY p.id DESC",
                                (usuario_id,)).fetchall()
        pedidos = []
        for f in filas:
            p = dict(f)
            if usuario_id is None:
                # Pedidos antiguos (antes del checkout) no tienen cliente_*: usamos la cuenta
                p["cliente_nombre"] = p["cliente_nombre"] or p.pop("cuenta_nombre", None)
                p["cliente_correo"] = p["cliente_correo"] or p.pop("cuenta_correo", None)
                p.pop("cuenta_nombre", None)
                p.pop("cuenta_correo", None)
                p["invitado"] = p["usuario_id"] is None and p["entrega"] is not None
            p.pop("usuario_id")
            p["sucursal_nombre"] = SUCURSALES.get(p["sucursal"])
            p["region_nombre"] = REGIONES.get(p["region"])
            items = con.execute(
                """SELECT nombre, formato, precio, cantidad, color_nombre, color_codigo, color_hex
                   FROM pedido_items WHERE pedido_id=?""", (p["id"],)
            ).fetchall()
            p["items"] = [dict(i) for i in items]
            pedidos.append(p)
        con.close()
        return pedidos

    def _editar_tarifa(self, region, datos):
        """PATCH /api/admin/tarifas/<region>  {"costo": 4990}  o  {"costo": null}
        null borra la tarifa: el despacho a esa región pasa a "coordinar"."""
        if region not in REGIONES:
            return self._json({"error": "Región desconocida"}, 404)
        if "costo" not in datos:
            return self._json({"error": "Indica el costo (o null para coordinar el despacho)"}, 400)
        costo = datos["costo"]
        if costo is not None and (type(costo) is not int or not 0 <= costo <= MAX_PRECIO):
            return self._json({"error": f"Costo inválido (número entero entre 0 y {MAX_PRECIO})"}, 400)
        con = get_db()
        with con:
            if costo is None:
                con.execute("DELETE FROM tarifas_despacho WHERE region=?", (region,))
            else:
                con.execute("INSERT INTO tarifas_despacho (region, costo) VALUES (?, ?) "
                            "ON CONFLICT(region) DO UPDATE SET costo=excluded.costo", (region, costo))
        con.close()
        return self._json({"ok": True, "region": region, "costo": costo})

    def _crear_producto(self, datos):
        """POST /api/admin/productos
        {"nombre", "descripcion", "imagen", "superficies": [...], "rendimiento_m2_litro", ficha técnica,
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
        rendimiento, error = _leer_rendimiento(datos.get("rendimiento_m2_litro"))
        if error:
            return self._json({"error": error}, 400)
        ficha, error = _leer_ficha(datos)
        if error:
            return self._json({"error": error}, 400)
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
            columnas = {"nombre": nombre, "descripcion": _texto(datos, "descripcion").strip(),
                        "imagen": _texto(datos, "imagen").strip() or "img/prod-interior.webp",
                        "rendimiento_m2_litro": rendimiento, **ficha}
            # Los nombres de columna vienen de nuestras listas fijas, no del usuario
            nuevo_id = con.execute(
                f"INSERT INTO productos ({', '.join(columnas)}) VALUES ({', '.join('?' for _ in columnas)})",
                tuple(columnas.values()),
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
        if archivo.endswith(".html"):
            # Las etiquetas para compartir en redes necesitan la dirección completa
            contenido = contenido.replace(b"__SITIO_URL__", SITIO_URL.encode())
            tipo = "text/html; charset=utf-8"
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
    print("  WhatsApp:              " + ("ACTIVADO" if WHATSAPP_NUMERO else "oculto (falta WHATSAPP_NUMERO)"))
    print("  Dirección pública:     " + (SITIO_URL if SITIO_CONFIGURADO else "sin SITIO_URL (se usa localhost)"))
    print("  (Para detener el servidor: Ctrl + C)")
    print("=" * 50)
    # Hilo en segundo plano que olvida las IP de intentos fallidos viejos
    threading.Thread(target=_limpieza_periodica, daemon=True).start()
    with Servidor(("", PUERTO), Handler) as httpd:
        httpd.serve_forever()
