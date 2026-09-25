#!/usr/bin/env python3
# ============================================================
#  ECOCORDI - Pruebas de la Fase 2 (catálogo, configuración y SEO)
#  Uso:  python3 pruebas/prueba_catalogo.py
#  Cada prueba usa una base de datos TEMPORAL; ecocordi.db no se toca.
# ============================================================
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from utilidades import Servidor, ok, terminar, titulo  # noqa: E402


class SinRedirigir(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def obtener(url, seguir=True):
    """(código, cabeceras, cuerpo) sin lanzar error en 3xx/4xx."""
    abridor = urllib.request.build_opener() if seguir else urllib.request.build_opener(SinRedirigir)
    try:
        with abridor.open(url, timeout=10) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


SITIO = "https://www.ejemplo-ecocordi.cl"

# ------------------------------------------------------------
titulo("Configuración pública (/api/config) y WhatsApp")
srv = Servidor().arrancar()
_, config = srv.cliente().pedir("GET", "/api/config")
ok(config["whatsapp"] is None, "Sin WHATSAPP_NUMERO: whatsapp = null (el botón se oculta)", config)
ok("WhatsApp:              oculto" in srv.salida, "El servidor avisa al arrancar que WhatsApp está oculto")
srv.borrar()
srv = Servidor(entorno={"WHATSAPP_NUMERO": "+56 9 1234-5678"}).arrancar()
_, config = srv.cliente().pedir("GET", "/api/config")
ok(config["whatsapp"] == "56912345678", "WHATSAPP_NUMERO con +, espacios y guion queda solo en dígitos", config)
srv.borrar()
srv = Servidor(entorno={"WHATSAPP_NUMERO": "javascript:alert(1)"}).arrancar()
_, config = srv.cliente().pedir("GET", "/api/config")
ok(config["whatsapp"] is None, "Un WHATSAPP_NUMERO inválido se ignora", config)
srv.borrar()

# ------------------------------------------------------------
titulo("SEO: robots.txt, sitemap.xml y etiquetas para compartir")
srv = Servidor(entorno={"SITIO_URL": SITIO + "/"}).arrancar()
codigo, cab, cuerpo = obtener(srv.url + "/robots.txt")
robots = cuerpo.decode()
ok(codigo == 200 and cab["Content-Type"].startswith("text/plain"), "robots.txt responde texto plano")
ok("Disallow: /admin.html" in robots and "Disallow: /api/" in robots, "robots.txt bloquea el panel y la API")
ok(f"Sitemap: {SITIO}/sitemap.xml" in robots, "robots.txt apunta al sitemap con SITIO_URL (sin '/' doble)", robots)

codigo, cab, cuerpo = obtener(srv.url + "/sitemap.xml")
ok(codigo == 200 and "xml" in cab["Content-Type"], "sitemap.xml responde XML")
raiz = ET.fromstring(cuerpo)
ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
urls = [u.find("s:loc", ns).text for u in raiz.findall("s:url", ns)]
fechas = [u.find("s:lastmod", ns).text for u in raiz.findall("s:url", ns)]
ok(len(urls) == 12 and all(u.startswith(SITIO + "/") for u in urls), "12 páginas, todas con el dominio de SITIO_URL", urls)
ok(SITIO + "/catalogo.html?superficie=madera" in urls and SITIO + "/" in urls, "Incluye la portada y el catálogo por superficie")
ok(not any("admin" in u for u in urls), "El panel de administración NO está en el sitemap")
ok(all(len(f) == 10 and f[4] == "-" for f in fechas), "Cada página tiene su fecha (lastmod)")

for pagina in ("/", "/catalogo.html"):
    codigo, cab, cuerpo = obtener(srv.url + pagina)
    html = cuerpo.decode()
    ok("__SITIO_URL__" not in html, f"{pagina}: no quedan marcadores sin reemplazar")
    ok(f'<meta property="og:image" content="{SITIO}/img/og-ecocordi.jpg" />' in html and
       'name="twitter:card" content="summary_large_image"' in html, f"{pagina}: Open Graph y Twitter con URL absoluta")
    ok(f'<link rel="canonical" href="{SITIO}/' in html, f"{pagina}: enlace canónico")
codigo, cab, cuerpo = obtener(srv.url + "/img/og-ecocordi.jpg")
ok(codigo == 200 and cab["Content-Type"] == "image/jpeg" and cuerpo[:3] == b"\xff\xd8\xff", "La imagen para redes existe (JPEG)")
srv.borrar()

srv = Servidor(entorno={"SITIO_URL": "javascript:alert(1)"}).arrancar()
_, _, cuerpo = obtener(srv.url + "/robots.txt")
ok(f"Sitemap: http://localhost:" in cuerpo.decode(), "Un SITIO_URL inválido se ignora (se usa localhost)")
srv.borrar()

# ------------------------------------------------------------
titulo("Rendimiento por producto (para la calculadora)")
srv = Servidor().arrancar()
cliente, admin = srv.cliente(), srv.admin()
_, productos = cliente.pedir("GET", "/api/productos")
ok(all(p["rendimiento_m2_litro"] is None for p in productos), "Los productos de ejemplo NO tienen rendimiento inventado (null)")
pid = productos[0]["id"]
estado, _ = admin.pedir("PATCH", f"/api/admin/productos/{pid}", {"rendimiento_m2_litro": 12.5})
_, productos = cliente.pedir("GET", "/api/productos")
ok(estado == 200 and productos[0]["rendimiento_m2_litro"] == 12.5, "El admin guarda el rendimiento (12,5 m²/L)")
estado, _ = admin.pedir("PATCH", f"/api/admin/productos/{pid}", {"rendimiento_m2_litro": None})
_, productos = cliente.pedir("GET", "/api/productos")
ok(estado == 200 and productos[0]["rendimiento_m2_litro"] is None, "Se puede borrar (vuelve a 'sin dato')")
for malo in (0, -3, 1000, "10", True):
    estado, _ = admin.pedir("PATCH", f"/api/admin/productos/{pid}", {"rendimiento_m2_litro": malo})
    ok(estado == 400, f"Rendimiento {malo!r} rechazado (400)", estado)
estado, _ = cliente.pedir("PATCH", f"/api/admin/productos/{pid}", {"rendimiento_m2_litro": 10})
ok(estado == 403, "Un cliente no puede cambiar el rendimiento (403)", estado)
estado, r = admin.pedir("POST", "/api/admin/productos", {
    "nombre": "Con rendimiento", "superficies": ["interior"], "rendimiento_m2_litro": 9,
    "formatos": [{"nombre": "galón", "litros": 3.785, "precio": 1000, "stock": 1}]})
_, productos = cliente.pedir("GET", "/api/productos")
ok(estado == 200 and productos[-1]["rendimiento_m2_litro"] == 9, "Crear un producto con rendimiento")
srv.borrar()

# ------------------------------------------------------------
titulo("Volver a la misma página después de Google (sin redirecciones abiertas)")
srv = Servidor(entorno={"SITIO_URL": SITIO, "GOOGLE_CLIENT_ID": "cliente-prueba", "GOOGLE_CLIENT_SECRET": "secreto"}).arrancar()
codigo, cab, _ = obtener(srv.url + "/api/auth/google/iniciar?volver=catalogo.html", seguir=False)
destino = parse_qs(urlparse(cab["Location"]).query)
ok(destino.get("redirect_uri") == [SITIO + "/api/auth/google/callback"],
   "Sin GOOGLE_REDIRECT_URI, la vuelta de Google usa SITIO_URL", destino.get("redirect_uri"))
srv.borrar()

srv = Servidor().arrancar()  # Google NO configurado: /iniciar devuelve directo a "volver"
casos = [
    ("catalogo.html?superficie=madera&q=rejas", "/catalogo.html?superficie=madera&q=rejas&google=no_configurado"),
    ("catalogo.html?q=pintura+%C3%B3leo", "/catalogo.html?q=pintura+%C3%B3leo&google=no_configurado"),
    ("catalogo.html?superficie=lava&x=1", "/catalogo.html?google=no_configurado"),
    ("https://sitio-malo.com", "/?google=no_configurado"),
    ("//sitio-malo.com/catalogo.html", "/?google=no_configurado"),
    ("admin.html", "/?google=no_configurado"),
]
for volver, esperado in casos:
    codigo, cab, _ = obtener(srv.url + "/api/auth/google/iniciar?" + urllib.parse.urlencode({"volver": volver}), seguir=False)
    ok(codigo == 302 and cab["Location"] == esperado, f"volver={volver} → {esperado}", cab["Location"])
srv.borrar()

terminar()
