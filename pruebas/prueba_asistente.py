#!/usr/bin/env python3
# ============================================================
#  ECOCORDI - Pruebas del asistente "¿Qué pintura necesito?"
#  (GET /api/asistente, GET /api/calcular y la ficha técnica)
#  Uso:  python3 pruebas/prueba_asistente.py
#  Cada prueba usa una base de datos TEMPORAL; ecocordi.db no se toca.
# ============================================================
import os
import sqlite3
import sys
import tempfile
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from utilidades import RAIZ, Servidor, ok, terminar, titulo  # noqa: E402

BASE = {"superficie": "interior", "uso": "interior", "condicion": "normal", "acabado": "mate"}


def asistente(cliente, **params):
    return cliente.pedir("GET", "/api/asistente?" + urlencode(params))


def nombre(resultado):
    return resultado["recomendado"]["nombre"] if resultado.get("recomendado") else None


srv = Servidor().arrancar()
cliente, admin = srv.cliente(), srv.admin()
_, productos = cliente.pedir("GET", "/api/productos")
por_nombre = {p["nombre"]: p for p in productos}

# ------------------------------------------------------------
titulo("Ficha técnica de ejemplo")
interior = por_nombre["Pinturas para Interior"]
ok((interior["uso"], interior["acabado"], interior["lavable"], interior["rendimiento_m2_litro"],
    interior["manos_recomendadas"]) == ("interior", "mate", 1, 12, 2),
   "Pinturas para Interior: interior, mate, lavable, 12 m²/L, 2 manos", interior)
ok(all(p["ficha_demo"] == 1 for p in productos), "Todas las fichas iniciales están marcadas como ejemplo (ficha_demo = 1)")

# ------------------------------------------------------------
titulo("Parámetros inválidos → 400")
malos = [
    ({}, "sin parámetros"),
    ({"uso": "interior", "condicion": "normal", "acabado": "mate"}, "sin superficie"),
    (dict(BASE, superficie="lava"), "superficie desconocida"),
    (dict(BASE, uso="adentro"), "uso desconocido"),
    (dict(BASE, uso="ambos"), "uso 'ambos' (la persona elige interior o exterior)"),
    (dict(BASE, condicion="lluvia"), "condición desconocida"),
    (dict(BASE, acabado="perlado"), "acabado desconocido"),
    ({k: v for k, v in BASE.items() if k != "acabado"}, "sin acabado"),
    (dict(BASE, m2="-5"), "m2 negativo"),
    (dict(BASE, m2="0"), "m2 = 0"),
    (dict(BASE, m2="abc"), "m2 que no es número"),
    (dict(BASE, m2="20000"), "m2 sobre el máximo"),
    (dict(BASE, manos="9"), "manos = 9"),
    (dict(BASE, manos="1.5"), "manos con decimales"),
    (dict(BASE, x="1"), "parámetro desconocido"),
    (dict(BASE, superficie="exterior", uso="interior"), "superficie exterior con uso interior"),
    (dict(BASE, producto="abc"), "producto que no es número"),
    (dict(BASE, carrito="1:a"), "carrito mal escrito"),
]
for params, texto in malos:
    estado, r = asistente(cliente, **params)
    ok(estado == 400 and "error" in r, f"{texto} → 400", (estado, r))
estado, r = cliente.pedir("GET", "/api/asistente?" + urlencode(BASE) + "&superficie=madera")
ok(estado == 400, "parámetro repetido → 400", (estado, r))

# ------------------------------------------------------------
titulo("Reglas: la humedad y el sol cambian la recomendación")
# Muros interiores, acabado mate:
#  - normal:  Interior 2 (mate) + 1 (lavable) = 3 · Chalk 2 · Especiales 1 · Protección 0
#  - humedad: Especiales 3 + 1 = 4 · Interior 3 · Protección 3 · Chalk 2
estado, normal = asistente(cliente, **BASE)
ok(estado == 200 and nombre(normal) == "Pinturas para Interior" and normal["recomendado"]["puntaje"] == 3,
   "Interior, normal, mate → Pinturas para Interior (3 puntos)", (nombre(normal), normal.get("recomendado", {}).get("puntaje")))
ok([a["nombre"] for a in normal["alternativas"]] == ["Chalk Paint Ecocordi", "Productos Especiales"],
   "…con 2 alternativas en orden de puntaje", [a["nombre"] for a in normal["alternativas"]])
_, humedad = asistente(cliente, **dict(BASE, condicion="humedad"))
ok(nombre(humedad) == "Productos Especiales" and humedad["recomendado"]["puntaje"] == 4,
   "Con humedad → Productos Especiales (4 puntos)", nombre(humedad))
ok([a["nombre"] for a in humedad["alternativas"]] == ["Pinturas para Interior", "Protección de Madera"],
   "Empate a 3 puntos: primero el más barato por litro (Interior $4.225/L antes que Protección $5.017/L)",
   [(a["nombre"], a["precio_litro"]) for a in humedad["alternativas"]])
motivos = humedad["recomendado"]["motivos"]
ok(any("humedad" in m for m in motivos) and any("lavable" in m.lower() for m in motivos),
   "Los motivos explican las reglas que sumaron (humedad y lavable)", motivos)
ok(motivos[0] == "Es para muros y cielos interiores.", "El primer motivo dice para qué sirve", motivos[0])

# Muro exterior, acabado "no sé":
#  - normal: los 3 empatan en 0 → gana el más barato por litro (Anticorrosivo, $5.810/L)
#  - sol:    Pinturas para Exterior resiste sol → 3 puntos
params = {"superficie": "exterior", "uso": "exterior", "condicion": "normal", "acabado": "no_se"}
_, r = asistente(cliente, **params)
ok(nombre(r) == "Anticorrosivo Metal Pro" and r["recomendado"]["puntaje"] == 0,
   "Exterior sin condición especial → empate, gana el más barato por litro (Anticorrosivo)", nombre(r))
_, r = asistente(cliente, **dict(params, condicion="sol"))
ok(nombre(r) == "Pinturas para Exterior" and r["recomendado"]["puntaje"] == 3,
   "Exterior con sol fuerte → Pinturas para Exterior (resiste sol)", nombre(r))
ok(any("sol" in m for m in r["recomendado"]["motivos"]), "…y lo explica en los motivos", r["recomendado"]["motivos"])
_, r = asistente(cliente, superficie="madera", uso="interior", condicion="normal", acabado="no_se")
ok(nombre(r) == "Protección de Madera" and r["recomendado"]["puntaje"] == 1,
   "«No sé» le da +1 al acabado satinado", (nombre(r), r["recomendado"]["motivos"]))
_, r = asistente(cliente, superficie="madera", uso="exterior", condicion="normal", acabado="mate")
ok(nombre(r) == "Protección de Madera" and r["alternativas"] == [],
   "Madera en exterior: solo sirve Protección de Madera (Chalk Paint es solo de interior)",
   [nombre(r)] + [a["nombre"] for a in r["alternativas"]])

# ------------------------------------------------------------
titulo("Cálculo de litros y formatos (verificado a mano)")
fid_galon = interior["formatos"][0]["id"]
estado, cuarto = admin.pedir("POST", f"/api/admin/productos/{interior['id']}/formatos",
                             {"nombre": "1/4 galón", "litros": 0.946, "precio": 4000, "stock": 10})
ok(estado == 200, "Se agrega un formato 1/4 galón ($4.000) a Pinturas para Interior", cuarto)
# 35 m² × 2 manos ÷ 12 m²/L = 5,833 L → redondeado hacia arriba: 5,9 L.
# Opciones: 2 galones (7,57 L) $31.980 · 1 galón + 3 cuartos (6,623 L) $27.990 · 7 cuartos (6,622 L) $28.000
# → la más barata: 1 galón + 3 cuartos = $27.990
_, r = asistente(cliente, **dict(BASE, m2="35"))
c = r["recomendado"]["calculo"]
ok(c["litros"] == 5.9 and c["manos"] == 2 and c["rendimiento"] == 12, "35 m² × 2 manos ÷ 12 m²/L = 5,9 L", c)
items = sorted((i["nombre"], i["cantidad"]) for i in c["combinacion"]["items"])
ok(items == [("1/4 galón", 3), ("galón", 1)] and c["combinacion"]["precio"] == 27990,
   "Combinación más barata: 1 galón + 3 × 1/4 galón = $27.990", c["combinacion"])
ok(abs(c["combinacion"]["litros"] - 6.623) < 0.001 and abs(c["combinacion"]["sobrante"] - 0.723) < 0.001,
   "Cubre 6,623 L (sobran 0,723 L)", c["combinacion"])
# Con 3 manos: 35 × 3 ÷ 12 = 8,75 → 8,8 L. 2 galones + 2 cuartos (9,462 L) = $39.980
_, r = asistente(cliente, **dict(BASE, m2="35", manos="3"))
c = r["recomendado"]["calculo"]
ok(c["litros"] == 8.8 and c["combinacion"]["precio"] == 39980 and
   sorted((i["nombre"], i["cantidad"]) for i in c["combinacion"]["items"]) == [("1/4 galón", 2), ("galón", 2)],
   "Con 3 manos: 8,8 L → 2 galones + 2 × 1/4 galón = $39.980", c)
_, r = asistente(cliente, **dict(BASE, m2="40,5"))
ok(r["recomendado"]["calculo"]["litros"] == 6.8, "Acepta coma decimal: 40,5 m² × 2 ÷ 12 = 6,75 → 6,8 L",
   r["recomendado"]["calculo"]["litros"])
_, r = asistente(cliente, **dict(BASE, m2="36"))
ok(r["recomendado"]["calculo"]["litros"] == 6.0, "Un resultado exacto no se redondea de más (36 × 2 ÷ 12 = 6,0 L)",
   r["recomendado"]["calculo"]["litros"])
ok("calculo" in r["alternativas"][0], "Las alternativas también traen su cálculo")
_, r = asistente(cliente, **BASE)
ok("calculo" not in r["recomendado"], "Sin m², no hay cálculo de litros")

# Lo que ya está en el carrito no se vuelve a ofrecer
_, r = asistente(cliente, **dict(BASE, m2="35", carrito=f"{fid_galon}:20"))
c = r["recomendado"]["calculo"]
ok([(i["nombre"], i["cantidad"]) for i in c["combinacion"]["items"]] == [("1/4 galón", 7)] and c["combinacion"]["precio"] == 28000,
   "Con los 20 galones ya en el carrito: 7 × 1/4 galón ($28.000)", c["combinacion"])

# La calculadora del catálogo usa la misma lógica
estado, calc = cliente.pedir("GET", f"/api/calcular?producto={interior['id']}&m2=35&manos=2")
ok(estado == 200 and calc["litros"] == 5.9 and calc["combinacion"]["precio"] == 27990,
   "GET /api/calcular da el mismo resultado que el asistente", calc)
for consulta, texto in (("producto=abc&m2=10", "producto inválido"), (f"producto={interior['id']}", "sin m2"),
                        (f"producto={interior['id']}&m2=10&manos=0", "manos = 0"),
                        (f"producto={interior['id']}&m2=10&otra=1", "parámetro desconocido")):
    estado, _ = cliente.pedir("GET", "/api/calcular?" + consulta)
    ok(estado == 400, f"/api/calcular con {texto} → 400", estado)
estado, _ = cliente.pedir("GET", "/api/calcular?producto=9999&m2=10")
ok(estado == 404, "/api/calcular con un producto que no existe → 404", estado)

# ------------------------------------------------------------
titulo("Pintura ya elegida (desde el visualizador)")
chalk = por_nombre["Chalk Paint Ecocordi"]
estado, r = asistente(cliente, superficie="interior", uso="interior", producto=str(chalk["id"]), m2="10")
ok(estado == 200 and nombre(r) == "Chalk Paint Ecocordi" and r["aviso"] is None,
   "Con producto, esa pintura va primero aunque otra sume más (y no pide condición ni acabado)", (estado, nombre(r)))
anti = por_nombre["Anticorrosivo Metal Pro"]
_, r = asistente(cliente, superficie="interior", uso="interior", producto=str(anti["id"]))
ok(nombre(r) != "Anticorrosivo Metal Pro" and r["aviso"], "Una pintura que no sirve para esa superficie: aviso y otras opciones",
   (nombre(r), r["aviso"]))

# ------------------------------------------------------------
titulo("Sin candidatos: mensaje amable")
proteccion = por_nombre["Protección de Madera"]
admin.pedir("PATCH", f"/api/admin/formatos/{proteccion['formatos'][0]['id']}", {"stock": 0})
estado, r = asistente(cliente, superficie="madera", uso="exterior", condicion="sol", acabado="mate")
ok(estado == 200 and r["recomendado"] is None and r["alternativas"] == [],
   "Madera en exterior sin stock de Protección de Madera → sin recomendación", r)
ok("Escríbenos" in r["mensaje"] and "sucursal" in r["mensaje"] and r["sucursales"] == ["Talca", "Santiago"],
   "El mensaje sugiere escribir o ir a una sucursal", r.get("mensaje"))
ok(r["whatsapp"] is None, "Sin WHATSAPP_NUMERO, no se ofrece WhatsApp", r.get("whatsapp"))
admin.pedir("PATCH", f"/api/admin/formatos/{proteccion['formatos'][0]['id']}", {"stock": 20})

# ------------------------------------------------------------
titulo("Admin: editar la ficha técnica")
estado, _ = admin.pedir("PATCH", f"/api/admin/productos/{chalk['id']}", {
    "uso": "ambos", "acabado": "satinado", "resiste_humedad": True, "resiste_sol": False,
    "lavable": True, "manos_recomendadas": 3, "ficha_demo": False})
_, productos = cliente.pedir("GET", "/api/productos")
p = next(x for x in productos if x["id"] == chalk["id"])
ok(estado == 200 and (p["uso"], p["acabado"], p["resiste_humedad"], p["lavable"], p["manos_recomendadas"], p["ficha_demo"])
   == ("ambos", "satinado", 1, 1, 3, 0), "El admin guarda toda la ficha", p)
for campo, valor in (("uso", "techo"), ("acabado", "perla"), ("resiste_sol", 1), ("lavable", "si"),
                     ("manos_recomendadas", 0), ("manos_recomendadas", 6), ("ficha_demo", None)):
    estado, _ = admin.pedir("PATCH", f"/api/admin/productos/{chalk['id']}", {campo: valor})
    ok(estado == 400, f"{campo} = {valor!r} rechazado (400)", estado)
estado, _ = cliente.pedir("PATCH", f"/api/admin/productos/{chalk['id']}", {"uso": "interior"})
ok(estado == 403, "Un cliente no puede cambiar la ficha (403)", estado)
estado, nuevo = admin.pedir("POST", "/api/admin/productos", {
    "nombre": "Esmalte Nuevo", "superficies": ["metal"], "uso": "exterior", "acabado": "brillante",
    "resiste_sol": True, "rendimiento_m2_litro": 11, "manos_recomendadas": 2,
    "formatos": [{"nombre": "galón", "litros": 3.785, "precio": 1000, "stock": 5}]})
_, productos = cliente.pedir("GET", "/api/productos")
p = next(x for x in productos if x["nombre"] == "Esmalte Nuevo")
ok(estado == 200 and (p["uso"], p["acabado"], p["resiste_sol"], p["resiste_humedad"], p["ficha_demo"])
   == ("exterior", "brillante", 1, 0, 0), "Crear un producto con su ficha (no queda como ejemplo)", p)
_, r = asistente(cliente, superficie="metal", uso="exterior", condicion="sol", acabado="brillante")
ok(nombre(r) == "Esmalte Nuevo", "El producto nuevo ya participa en el asistente", nombre(r))
admin.pedir("PATCH", f"/api/admin/productos/{p['id']}", {"uso": None})
_, r = asistente(cliente, superficie="metal", uso="exterior", condicion="sol", acabado="brillante")
ok(nombre(r) != "Esmalte Nuevo" and all(a["nombre"] != "Esmalte Nuevo" for a in r["alternativas"]),
   "Sin uso (dato vacío), el producto no aparece en el asistente", nombre(r))
srv.borrar()

# ------------------------------------------------------------
titulo("Migración: base de datos sin ficha técnica")
carpeta = tempfile.mkdtemp()
anterior = os.path.join(carpeta, "sin-ficha.db")
con = sqlite3.connect(anterior)
con.executescript("""
    CREATE TABLE productos (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL, descripcion TEXT,
                            imagen TEXT, rendimiento_m2_litro REAL);
    CREATE TABLE producto_superficies (producto_id INTEGER NOT NULL, superficie TEXT NOT NULL,
                                       PRIMARY KEY (producto_id, superficie));
    CREATE TABLE producto_formatos (id INTEGER PRIMARY KEY AUTOINCREMENT, producto_id INTEGER NOT NULL,
                                    nombre TEXT NOT NULL, litros REAL NOT NULL, precio INTEGER NOT NULL,
                                    stock INTEGER NOT NULL DEFAULT 0, UNIQUE (producto_id, nombre));
    INSERT INTO productos (nombre, descripcion, imagen, rendimiento_m2_litro) VALUES
        ('Pinturas para Interior', 'd', 'img/prod-interior.webp', 14.5),
        ('Barniz Casero', 'd', 'img/prod-madera.webp', NULL);
    INSERT INTO producto_superficies VALUES (1, 'interior'), (2, 'madera'), (2, 'exterior');
    INSERT INTO producto_formatos (producto_id, nombre, litros, precio, stock) VALUES (1, 'galón', 3.785, 15990, 3),
                                                                                    (2, 'galón', 3.785, 9990, 3);
""")
con.commit()
con.close()
srv = Servidor(db_inicial=anterior).arrancar()
ok("ficha técnica de EJEMPLO para 2 productos" in srv.salida, "El servidor avisa la migración de la ficha", srv.salida)
_, lista = srv.cliente().pedir("GET", "/api/productos")
por_nombre = {p["nombre"]: p for p in lista}
ok(por_nombre["Pinturas para Interior"]["rendimiento_m2_litro"] == 14.5,
   "Un rendimiento que el admin ya había cargado se respeta")
ok(por_nombre["Pinturas para Interior"]["uso"] == "interior" and por_nombre["Pinturas para Interior"]["lavable"] == 1,
   "Producto conocido: toma su ficha de ejemplo")
b = por_nombre["Barniz Casero"]
ok((b["uso"], b["resiste_sol"], b["rendimiento_m2_litro"], b["ficha_demo"]) == ("ambos", 1, 10, 1),
   "Producto desconocido: ficha deducida de sus superficies (madera + exterior → ambos, resiste sol)", b)
srv.detener()
srv.arrancar()
ok("ficha técnica" not in srv.salida, "Al arrancar de nuevo no vuelve a rellenar", srv.salida)
srv.borrar()

real = os.path.join(RAIZ, "ecocordi.db")
if os.path.exists(real):
    srv = Servidor(db_inicial=real).arrancar()  # COPIA de tu base real
    _, lista = srv.cliente().pedir("GET", "/api/productos")
    ok(lista and all(p["uso"] and p["ficha_demo"] == 1 for p in lista),
       "Copia de tu ecocordi.db: todos los productos quedan con ficha de ejemplo", [(p["nombre"], p["uso"]) for p in lista])
    estado, r = srv.cliente().pedir("GET", "/api/asistente?superficie=interior&uso=interior&condicion=normal&acabado=mate&m2=20")
    ok(estado == 200 and r["recomendado"], "Copia de tu ecocordi.db: el asistente recomienda", estado)
    srv.borrar()

terminar()
