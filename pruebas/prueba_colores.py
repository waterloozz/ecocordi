#!/usr/bin/env python3
# ============================================================
#  ECOCORDI - Pruebas de la carta de colores (visualizador)
#  GET /api/colores, POST /api/carrito/item, color en los pedidos,
#  "Mis colores" y el CRUD de colores del admin.
#  Uso:  python3 pruebas/prueba_colores.py
#  Cada prueba usa una base de datos TEMPORAL; ecocordi.db no se toca.
# ============================================================
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from utilidades import RAIZ, Servidor, ok, pedido, terminar, titulo  # noqa: E402


def consulta(db, sql, params=()):
    con = sqlite3.connect(db)
    filas = con.execute(sql, params).fetchall()
    con.close()
    return filas


srv = Servidor().arrancar()
cliente, admin = srv.cliente(), srv.admin()
_, productos = cliente.pedir("GET", "/api/productos")
por_nombre = {p["nombre"]: p for p in productos}
madera = por_nombre["Protección de Madera"]
interior = por_nombre["Pinturas para Interior"]

# ------------------------------------------------------------
titulo("Carta de colores de ejemplo")
estado, r = cliente.pedir("GET", "/api/colores")
colores = r["colores"]
ok(estado == 200 and len(colores) == 40, "40 colores de ejemplo", len(colores))
ok(all(c["es_demo"] == 1 for c in colores), "Todos marcados como ejemplo (es_demo = 1)")
ok(len({c["nombre"] for c in colores}) == 40 and len({c["codigo"] for c in colores}) == 40, "Nombres y códigos sin repetir")
ok(all(c["codigo"].startswith("EC-") for c in colores), "Códigos propios de Ecocordi (EC-...)")
ok(set(r["familias"]) == {"blancos", "neutros", "calidos", "frios", "verdes", "tierra", "intensos"}, "7 familias", r["familias"])
ok("Carta de colores de EJEMPLO: 40 colores" in srv.salida, "El servidor avisa que cargó la carta de ejemplo")
por_color = {c["nombre"]: c for c in colores}
blanco, ocre = por_color["Nieve del Llaima"], por_color["Ocre de Quebrada"]
ok(madera["id"] in ocre["productos"] and madera["id"] not in blanco["productos"],
   "La Protección de Madera viene en colores tierra, no en blanco")
ok(sorted(madera["colores"]) == sorted(c["id"] for c in colores if madera["id"] in c["productos"]),
   "/api/productos entrega los colores de cada producto")

# ------------------------------------------------------------
titulo("GET /api/colores con filtros")
_, r = cliente.pedir("GET", "/api/colores?familia=verdes")
ok(len(r["colores"]) == 6 and all(c["familia"] == "verdes" for c in r["colores"]), "?familia=verdes → 6 verdes")
_, r = cliente.pedir("GET", f"/api/colores?producto={madera['id']}")
ok(len(r["colores"]) == 11 and all(madera["id"] in c["productos"] for c in r["colores"]),
   "?producto=<madera> → sus 11 colores", len(r["colores"]))
_, r = cliente.pedir("GET", f"/api/colores?familia=tierra&producto={madera['id']}")
ok(len(r["colores"]) == 5, "Familia y producto juntos (5 tierra)", len(r["colores"]))
_, r = cliente.pedir("GET", f"/api/colores?familia=verdes&producto={madera['id']}")
ok(r["colores"] == [], "Un filtro sin coincidencias devuelve una lista vacía")
for consulta_mala, texto in (("familia=fucsia", "familia desconocida"), ("producto=abc", "producto que no es número"),
                             ("color=1", "parámetro desconocido"), ("familia=verdes&familia=tierra", "parámetro repetido")):
    estado, _ = cliente.pedir("GET", "/api/colores?" + consulta_mala)
    ok(estado == 400, f"{texto} → 400", estado)

# ------------------------------------------------------------
titulo("Agregar al carrito con color (POST /api/carrito/item)")
galon_madera = madera["formatos"][0]["id"]
estado, r = cliente.pedir("POST", "/api/carrito/item", {"formato_id": galon_madera, "color_id": blanco["id"]})
ok(estado == 400 and "no está disponible" in r["error"], "Un color que no corresponde a esa pintura → 400", (estado, r))
estado, r = cliente.pedir("POST", "/api/carrito/item", {"formato_id": galon_madera, "color_id": ocre["id"]})
ok(estado == 200 and r["color"] == {"id": ocre["id"], "nombre": "Ocre de Quebrada", "codigo": "EC-T01", "hex": "#BF893E"},
   "Un color que sí corresponde → 200 con el color", r)
estado, r = cliente.pedir("POST", "/api/carrito/item", {"formato_id": galon_madera})
ok(estado == 200 and r["color"] is None, "Sin color también se puede")
for cuerpo, esperado, texto in (({"formato_id": 99999}, 404, "formato que no existe"),
                                ({"formato_id": "1"}, 400, "formato como texto"),
                                ({"formato_id": galon_madera, "color_id": "3"}, 400, "color como texto"),
                                ({"formato_id": galon_madera, "color_id": 99999}, 400, "color que no existe"),
                                ({"formato_id": galon_madera, "cantidad": 0}, 400, "cantidad 0"),
                                ({"formato_id": galon_madera, "cantidad": 21}, 409, "más que el stock")):
    estado, _ = cliente.pedir("POST", "/api/carrito/item", cuerpo)
    ok(estado == esperado, f"{texto} → {esperado}", estado)

# ------------------------------------------------------------
titulo("El color en los pedidos")
estado, r = cliente.pedir("POST", "/api/pedidos/cotizar",
                          pedido([{"formato_id": galon_madera, "cantidad": 1, "color_id": blanco["id"]}]))
ok(estado == 400 and "color" in r["error"], "Cotizar con un color que no corresponde → 400", (estado, r))
estado, r = cliente.pedir("POST", "/api/pedidos",
                          pedido([{"formato_id": galon_madera, "cantidad": 1, "color_id": blanco["id"]}]))
ok(estado == 400, "Comprar con un color que no corresponde → 400 (y no se guarda nada)", estado)
estado, r = cliente.pedir("POST", "/api/pedidos",
                          pedido([{"formato_id": galon_madera, "cantidad": 15, "color_id": ocre["id"]},
                                  {"formato_id": galon_madera, "cantidad": 6}]))
ok(estado == 409, "El stock se suma entre colores: 15 ocre + 6 sin color > 20 → 409", (estado, r))
comprador = srv.cliente()
comprador.registrar("color@correo.cl")
estado, r = comprador.pedir("POST", "/api/pedidos",
                            pedido([{"formato_id": galon_madera, "cantidad": 2, "color_id": ocre["id"]},
                                    {"formato_id": galon_madera, "cantidad": 1},
                                    {"formato_id": galon_madera, "cantidad": 1, "color_id": ocre["id"]}]))
ok(estado == 200 and r["subtotal"] == 4 * 18990, "Pedido con el mismo galón en ocre (3) y sin color (1)", r)
filas = consulta(srv.db, "SELECT cantidad, color_id, color_nombre, color_codigo, color_hex FROM pedido_items ORDER BY id")
ok(sorted(filas, key=str) == sorted([(3, ocre["id"], "Ocre de Quebrada", "EC-T01", "#BF893E"), (1, None, None, None, None)], key=str),
   "pedido_items guarda el color (copia de nombre, código y tono) y junta las líneas iguales", filas)
ok(consulta(srv.db, "SELECT stock FROM producto_formatos WHERE id=?", (galon_madera,))[0][0] == 16, "Se descuentan 4 galones")
_, mios = comprador.pedir("GET", "/api/pedidos")
ok(any(i["color_nombre"] == "Ocre de Quebrada" for i in mios[0]["items"]), "«Mis pedidos» muestra el color")
_, todos = admin.pedir("GET", "/api/admin/pedidos")
ok(any(i["color_codigo"] == "EC-T01" for i in todos[0]["items"]), "El panel de pedidos muestra el color")

# ------------------------------------------------------------
titulo("Mis colores (favoritos)")
estado, r = cliente.pedir("GET", "/api/mis-colores")
ok(estado == 200 and r == {"sesion": False, "colores": []}, "Sin sesión: 200 y sesion=false (quedan en el navegador)", r)
estado, _ = cliente.pedir("POST", "/api/mis-colores", {"colores": [ocre["id"]]})
ok(estado == 401, "Guardar sin sesión → 401", estado)
estado, r = comprador.pedir("POST", "/api/mis-colores", {"colores": [ocre["id"], blanco["id"], ocre["id"], 99999]})
ok(estado == 200 and r["colores"] == [ocre["id"], blanco["id"]], "Guarda sin repetir e ignora colores que no existen", r)
_, r = comprador.pedir("GET", "/api/mis-colores")
ok(r["sesion"] is True and r["colores"] == [ocre["id"], blanco["id"]], "Se leen desde la cuenta")
estado, r = comprador.pedir("DELETE", f"/api/mis-colores/{blanco['id']}")
ok(estado == 200 and r["colores"] == [ocre["id"]], "Quitar un favorito")
for malo in ([], "1", ["1"], list(range(1, 70))):
    estado, _ = comprador.pedir("POST", "/api/mis-colores", {"colores": malo})
    ok(estado == 400, f"Lista inválida {str(malo)[:20]} → 400", estado)
comprador.pedir("POST", "/api/cuenta/eliminar")
ok(consulta(srv.db, "SELECT COUNT(*) FROM colores_favoritos")[0][0] == 0, "Eliminar la cuenta borra sus favoritos")

# ------------------------------------------------------------
titulo("Admin: CRUD de colores y asignación a productos")
estado, r = admin.pedir("GET", "/api/admin/colores")
ok(estado == 200 and len(r) == 40, "El admin ve toda la carta")
estado, _ = cliente.pedir("GET", "/api/admin/colores")
ok(estado == 403, "Un cliente no ve el CRUD (403)", estado)
estado, _ = cliente.pedir("POST", "/api/admin/colores", {"nombre": "X", "codigo": "X", "hex": "#000000", "familia": "neutros"})
ok(estado == 403, "Un cliente no puede crear colores (403)", estado)
nuevo = {"nombre": "Verde Prueba", "codigo": "ec-p01", "hex": "#a1b2c3", "familia": "verdes", "productos": [interior["id"]]}
estado, r = admin.pedir("POST", "/api/admin/colores", nuevo)
nuevo_id = r.get("id")
_, lista = cliente.pedir("GET", f"/api/colores?producto={interior['id']}")
creado = next((c for c in lista["colores"] if c["id"] == nuevo_id), None)
ok(estado == 200 and creado and creado["hex"] == "#A1B2C3" and creado["codigo"] == "EC-P01" and creado["es_demo"] == 0,
   "Crear un color (hex y código en mayúsculas) asignado a Pinturas para Interior", creado)
for cambio, esperado, texto in (({"hex": "rojo"}, 400, "hex inválido"), ({"hex": "#12345"}, 400, "hex corto"),
                                ({"familia": "fucsia"}, 400, "familia inválida"), ({"nombre": ""}, 400, "nombre vacío"),
                                ({"nombre": "Nieve del Llaima"}, 409, "nombre repetido"), ({"codigo": "EC-B01"}, 409, "código repetido"),
                                ({"activo": 1}, 400, "activo que no es true/false")):
    estado, _ = admin.pedir("POST", "/api/admin/colores", {**nuevo, "nombre": "Otro", "codigo": "EC-P99", **cambio})
    ok(estado == esperado, f"Crear con {texto} → {esperado}", estado)
estado, _ = admin.pedir("PATCH", f"/api/admin/colores/{nuevo_id}", {"activo": False})
_, lista = cliente.pedir("GET", "/api/colores")
_, prods = cliente.pedir("GET", "/api/productos")
ok(estado == 200 and all(c["id"] != nuevo_id for c in lista["colores"]) and
   nuevo_id not in next(p for p in prods if p["id"] == interior["id"])["colores"],
   "Un color inactivo desaparece de la tienda y de los productos")
estado, _ = cliente.pedir("POST", "/api/carrito/item", {"formato_id": interior["formatos"][0]["id"], "color_id": nuevo_id})
ok(estado == 400, "…y ya no se puede comprar (400)", estado)
estado, _ = admin.pedir("PATCH", f"/api/admin/colores/{nuevo_id}", {"activo": True, "productos": [madera["id"]]})
_, r = cliente.pedir("GET", f"/api/colores?producto={madera['id']}")
ok(estado == 200 and any(c["id"] == nuevo_id for c in r["colores"]), "Editar la asignación desde el color")
estado, _ = admin.pedir("PATCH", f"/api/admin/productos/{interior['id']}", {"colores": [blanco["id"], ocre["id"]]})
_, prods = cliente.pedir("GET", "/api/productos")
ok(estado == 200 and sorted(next(p for p in prods if p["id"] == interior["id"])["colores"]) == sorted([blanco["id"], ocre["id"]]),
   "Asignar colores desde el producto (reemplaza la lista)")
estado, _ = admin.pedir("PATCH", f"/api/admin/productos/{interior['id']}", {"colores": "todos"})
ok(estado == 400, "Colores del producto inválidos → 400", estado)
estado, _ = admin.pedir("PATCH", "/api/admin/colores/99999", {"nombre": "Nada"})
ok(estado == 404, "Editar un color que no existe → 404", estado)
estado, _ = admin.pedir("DELETE", f"/api/admin/colores/{ocre['id']}")
ok(estado == 200 and consulta(srv.db, "SELECT COUNT(*) FROM producto_colores WHERE color_id=?", (ocre["id"],))[0][0] == 0,
   "Borrar un color lo quita de los productos")
ok(consulta(srv.db, "SELECT COUNT(*) FROM pedido_items WHERE color_nombre='Ocre de Quebrada'")[0][0] == 1,
   "…y los pedidos antiguos conservan su copia del color")
srv.detener()
srv.arrancar()
ok("Carta de colores" not in srv.salida and consulta(srv.db, "SELECT COUNT(*) FROM colores")[0][0] == 40,
   "Al reiniciar no vuelve a cargar la carta de ejemplo", srv.salida)
srv.borrar()

# ------------------------------------------------------------
titulo("Migración: tu base de datos real (copia)")
real = os.path.join(RAIZ, "ecocordi.db")
if os.path.exists(real):
    srv = Servidor(db_inicial=real).arrancar()
    _, r = srv.cliente().pedir("GET", "/api/colores")
    _, prods = srv.cliente().pedir("GET", "/api/productos")
    ok(len(r["colores"]) == 40 and all(p["colores"] for p in prods),
       "Copia de tu ecocordi.db: carta de ejemplo y colores asignados a todos los productos")
    ok({"color_id", "color_nombre", "color_codigo", "color_hex"} <= {f[1] for f in consulta(srv.db, "PRAGMA table_info(pedido_items)")},
       "pedido_items tiene las columnas del color")
    ok(consulta(srv.db, "PRAGMA foreign_key_check") == [] and consulta(srv.db, "PRAGMA integrity_check")[0][0] == "ok",
       "Integridad y claves foráneas OK")
    srv.borrar()

terminar()
