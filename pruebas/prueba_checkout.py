#!/usr/bin/env python3
# ============================================================
#  ECOCORDI - Pruebas de la Fase 3 (checkout)
#  Uso:  python3 pruebas/prueba_checkout.py
#  Cada prueba usa una base de datos TEMPORAL; ecocordi.db no se toca.
# ============================================================
import copy
import importlib
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from utilidades import RAIZ, Servidor, ok, pedido, terminar, titulo  # noqa: E402

sys.path.insert(0, RAIZ)


def consulta(db, sql, params=()):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    filas = [dict(f) for f in con.execute(sql, params)]
    con.close()
    return filas


def dv_referencia(cuerpo):
    """Dígito verificador calculado aquí, aparte del servidor (módulo 11)."""
    suma, factor = 0, 2
    for d in reversed(str(cuerpo)):
        suma += int(d) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - suma % 11
    return "0" if resto == 11 else "K" if resto == 10 else str(resto)


FACTURA = {"tipo": "factura", "rut": "76.354.771-k", "razon_social": "Constructora Ejemplo SpA",
           "giro": "Construcción", "direccion": "Av. Siempre Viva 123, Talca"}
DESPACHO = {"tipo": "despacho", "region": "maule", "comuna": "Talca", "direccion": "1 Norte 1234, depto 5"}

# ------------------------------------------------------------
titulo("RUT: dígito verificador (módulo 11)")
os.environ.setdefault("ECOCORDI_DB", os.path.join(RAIZ, "pruebas", "no-se-usa.db"))
server = importlib.import_module("server")
for texto, esperado in (("11.111.111-1", "11111111-1"), ("12345678-5", "12345678-5"), ("76354771k", "76354771-K"),
                        ("10.000.004-0", "10000004-0"), ("9.999.999-3", "9999999-3")):
    ok(server.normalizar_rut(texto) == esperado, f"RUT válido {texto} → {esperado}", server.normalizar_rut(texto))
for malo in ("12.345.678-9", "76354771-0", "1-9", "abc", "", "123456789012", "12.345.678-", "K2345678-5"):
    ok(server.normalizar_rut(malo) is None, f"RUT inválido rechazado: {malo!r}")
todos_bien = all(server.normalizar_rut(f"{c}-{dv_referencia(c)}") == f"{c}-{dv_referencia(c)}"
                 for c in range(1000000, 99999999, 7919))
ok(todos_bien, "Coincide con el cálculo de referencia en 12.500 RUT distintos")

titulo("IVA: neto, IVA y total")
server.PRECIOS_INCLUYEN_IVA = True
t = server.calcular_totales(18990, 0)
ok((t["neto"], t["iva"], t["total"]) == (15958, 3032, 18990), "Precios con IVA: $18.990 = neto $15.958 + IVA $3.032", t)
t = server.calcular_totales(18990, 4990)
ok((t["neto"], t["iva"], t["total"]) == (20151, 3829, 23980), "Con despacho $4.990: neto $20.151 + IVA $3.829 = $23.980", t)
t = server.calcular_totales(18990, None)
ok(t["total"] == 18990 and t["despacho"] is None, "Despacho a coordinar: no se suma al total", t)
server.PRECIOS_INCLUYEN_IVA = False
t = server.calcular_totales(18990, 0)
ok((t["neto"], t["iva"], t["total"]) == (18990, 3608, 22598), "Precios sin IVA: neto $18.990 + IVA $3.608 = $22.598", t)
ok(all(server.calcular_totales(n, 0)["neto"] + server.calcular_totales(n, 0)["iva"] == server.calcular_totales(n, 0)["total"]
       for n in range(0, 200000, 137)), "Siempre neto + IVA = total (sin pesos perdidos por redondeo)")
server.PRECIOS_INCLUYEN_IVA = True
ok(all(server.calcular_totales(n, 0)["neto"] + server.calcular_totales(n, 0)["iva"] == n for n in range(0, 200000, 137)),
   "Con IVA incluido, el total es exactamente la suma de los precios")

# ------------------------------------------------------------
titulo("Compra como invitado")
srv = Servidor().arrancar()
invitado, admin = srv.cliente(), srv.admin()
_, productos = invitado.pedir("GET", "/api/productos")
fid = productos[0]["formatos"][0]["id"]
estado, r = invitado.pedir("POST", "/api/pedidos", pedido([{"formato_id": fid, "cantidad": 1}]))
ok(estado == 200 and r["invitado"] is True, "Un invitado puede comprar (sin cuenta)", r)
fila = consulta(srv.db, "SELECT * FROM pedidos WHERE id=?", (r["pedido_id"],))[0]
ok(fila["usuario_id"] is None and fila["cliente_nombre"] == "Cliente Prueba" and fila["cliente_correo"] == "invitado@correo.cl",
   "Se guardan nombre y correo del invitado (sin usuario)")
ok(fila["cliente_telefono"] == "+56912345678", "El teléfono se guarda normalizado", fila["cliente_telefono"])
ok((fila["entrega"], fila["sucursal"], fila["documento"], fila["costo_despacho"]) == ("retiro", "talca", "boleta", 0),
   "Retiro en sucursal Talca, boleta, sin costo de despacho")
ok((fila["subtotal"], fila["neto"], fila["iva"], fila["total"], fila["precios_incluyen_iva"]) == (18990, 15958, 3032, 18990, 1),
   "Se guardan subtotal, neto, IVA y total", fila)
ok(fila["terminos_aceptados"] and "términos versión" in fila["terminos_aceptados"], "Se guarda la aceptación de los términos")

stock_antes = consulta(srv.db, "SELECT stock FROM producto_formatos WHERE id=?", (fid,))[0]["stock"]
malos = [
    ("sin aceptar los términos", pedido([{"formato_id": fid, "cantidad": 1}], acepta_terminos=False)),
    ("sin nombre", pedido([{"formato_id": fid, "cantidad": 1}], cliente={"correo": "a@b.cl", "telefono": "912345678"})),
    ("correo inválido", pedido([{"formato_id": fid, "cantidad": 1}], cliente={"nombre": "A", "correo": "no-es-correo", "telefono": "912345678"})),
    ("teléfono inválido", pedido([{"formato_id": fid, "cantidad": 1}], cliente={"nombre": "A", "correo": "a@b.cl", "telefono": "123"})),
    ("sin entrega", pedido([{"formato_id": fid, "cantidad": 1}], entrega={})),
    ("sucursal inventada", pedido([{"formato_id": fid, "cantidad": 1}], entrega={"tipo": "retiro", "sucursal": "valparaiso"})),
    ("región inventada", pedido([{"formato_id": fid, "cantidad": 1}], entrega={**DESPACHO, "region": "marte"})),
    ("despacho sin comuna", pedido([{"formato_id": fid, "cantidad": 1}], entrega={**DESPACHO, "comuna": " "})),
    ("despacho sin dirección", pedido([{"formato_id": fid, "cantidad": 1}], entrega={**DESPACHO, "direccion": ""})),
    ("dirección demasiado larga", pedido([{"formato_id": fid, "cantidad": 1}], entrega={**DESPACHO, "direccion": "x" * 151})),
    ("documento inventado", pedido([{"formato_id": fid, "cantidad": 1}], documento={"tipo": "ticket"})),
    ("factura con RUT inválido", pedido([{"formato_id": fid, "cantidad": 1}], documento={**FACTURA, "rut": "76.354.771-0"})),
    ("factura sin giro", pedido([{"formato_id": fid, "cantidad": 1}], documento={**FACTURA, "giro": ""})),
    ("factura sin razón social", pedido([{"formato_id": fid, "cantidad": 1}], documento={**FACTURA, "razon_social": ""})),
    ("factura sin dirección", pedido([{"formato_id": fid, "cantidad": 1}], documento={**FACTURA, "direccion": ""})),
    ("cliente como texto", pedido([{"formato_id": fid, "cantidad": 1}], cliente="hola")),
]
for texto, cuerpo in malos:
    estado, r = invitado.pedir("POST", "/api/pedidos", cuerpo)
    ok(estado == 400 and r.get("error"), f"Rechaza pedido {texto} (400)", (estado, r))
ok(consulta(srv.db, "SELECT stock FROM producto_formatos WHERE id=?", (fid,))[0]["stock"] == stock_antes and
   consulta(srv.db, "SELECT COUNT(*) AS n FROM pedidos")[0]["n"] == 1, "Los pedidos rechazados no guardan nada ni tocan el stock")

titulo("Despacho: tarifas por región")
estado, _ = invitado.pedir("PATCH", "/api/admin/tarifas/maule", {"costo": 4990})
ok(estado == 403, "Un cliente no puede cambiar tarifas (403)", estado)
estado, _ = admin.pedir("PATCH", "/api/admin/tarifas/maule", {"costo": 4990})
_, config = invitado.pedir("GET", "/api/config")
ok(estado == 200 and config["tarifas_despacho"] == {"maule": 4990}, "El admin fija la tarifa del Maule", config["tarifas_despacho"])
ok(len(config["regiones"]) == 16 and config["sucursales"] == {"talca": "Talca", "santiago": "Santiago"},
   "La configuración pública trae las 16 regiones y las 2 sucursales")
for region, cuerpo, codigo in (("marte", {"costo": 1}, 404), ("maule", {"costo": -1}, 400), ("maule", {"costo": "5000"}, 400),
                               ("maule", {}, 400)):
    estado, _ = admin.pedir("PATCH", f"/api/admin/tarifas/{region}", cuerpo)
    ok(estado == codigo, f"Tarifa inválida {region} {cuerpo} → {codigo}", estado)
estado, r = invitado.pedir("POST", "/api/pedidos", pedido([{"formato_id": fid, "cantidad": 1}], entrega=DESPACHO, documento=FACTURA))
fila = consulta(srv.db, "SELECT * FROM pedidos WHERE id=?", (r.get("pedido_id"),))[0] if estado == 200 else {}
ok(estado == 200 and r["despacho"] == 4990 and r["total"] == 23980 and (r["neto"], r["iva"]) == (20151, 3829),
   "Despacho al Maule: suma $4.990 y desglosa neto e IVA", r)
ok((fila.get("region"), fila.get("comuna"), fila.get("direccion"), fila.get("costo_despacho")) == ("maule", "Talca", "1 Norte 1234, depto 5", 4990),
   "Se guarda la dirección de despacho y su costo")
ok((fila.get("documento"), fila.get("factura_rut"), fila.get("factura_razon_social"), fila.get("factura_giro")) ==
   ("factura", "76354771-K", "Constructora Ejemplo SpA", "Construcción"), "Se guardan los datos de la factura (RUT normalizado)")
estado, r = invitado.pedir("POST", "/api/pedidos", pedido([{"formato_id": fid, "cantidad": 1}], entrega={**DESPACHO, "region": "aysen"}))
ok(estado == 200 and r["despacho"] is None and r["despacho_por_coordinar"] is True and r["total"] == 18990,
   "Región sin tarifa: 'coordinar despacho' y no se suma al total", r)
estado, _ = admin.pedir("PATCH", "/api/admin/tarifas/maule", {"costo": None})
_, config = invitado.pedir("GET", "/api/config")
ok(estado == 200 and config["tarifas_despacho"] == {}, "Borrar una tarifa (null) la deja en 'coordinar'")

titulo("Resumen antes de enviar (cotizar)")
pedidos_antes = consulta(srv.db, "SELECT COUNT(*) AS n FROM pedidos")[0]["n"]
stock_antes = consulta(srv.db, "SELECT stock FROM producto_formatos WHERE id=?", (fid,))[0]["stock"]
estado, r = invitado.pedir("POST", "/api/pedidos/cotizar", pedido([{"formato_id": fid, "cantidad": 2}]))
ok(estado == 200 and r["subtotal"] == 37980 and r["total"] == 37980 and r["items"][0]["formato"] == "galón",
   "Cotizar devuelve los montos calculados por el servidor", r)
ok(consulta(srv.db, "SELECT COUNT(*) AS n FROM pedidos")[0]["n"] == pedidos_antes and
   consulta(srv.db, "SELECT stock FROM producto_formatos WHERE id=?", (fid,))[0]["stock"] == stock_antes,
   "Cotizar no guarda pedidos ni descuenta stock")
estado, r = invitado.pedir("POST", "/api/pedidos/cotizar", pedido([{"formato_id": fid, "cantidad": 999}]))
ok(estado == 409 and r.get("disponible") == stock_antes, "Cotizar avisa si no hay stock (409)", r)
estado, r = invitado.pedir("POST", "/api/pedidos/cotizar", pedido([{"formato_id": fid, "cantidad": 1}], documento={**FACTURA, "rut": "1-1"}))
ok(estado == 400 and "RUT" in r.get("error", ""), "Cotizar también revisa el RUT", r)

titulo("Compra con cuenta")
cuenta = srv.cliente()
cuenta.registrar("con-cuenta@correo.cl", nombre="Carla Cuenta")
cuerpo = pedido([{"formato_id": fid, "cantidad": 1}])
cuerpo["cliente"] = {"nombre": "Carla C.", "correo": "otro@correo.cl", "telefono": "912345678"}
estado, r = cuenta.pedir("POST", "/api/pedidos", cuerpo)
fila = consulta(srv.db, "SELECT usuario_id, cliente_correo, cliente_nombre FROM pedidos WHERE id=?", (r.get("pedido_id"),))[0]
ok(estado == 200 and r["invitado"] is False and fila["usuario_id"] and fila["cliente_correo"] == "con-cuenta@correo.cl",
   "Con cuenta, el pedido queda en la cuenta y usa SU correo (no otro)", fila)
_, mis = cuenta.pedir("GET", "/api/pedidos")
ok(len(mis) == 1 and mis[0]["entrega"] == "retiro" and mis[0]["sucursal_nombre"] == "Talca" and "usuario_id" not in mis[0],
   "Mis pedidos muestra la entrega", mis)
_, todos = admin.pedir("GET", "/api/admin/pedidos")
por_id = {p["id"]: p for p in todos}
ok(por_id[r["pedido_id"]]["invitado"] is False and por_id[1]["invitado"] is True and por_id[1]["cliente_telefono"] == "+56912345678",
   "El admin ve quién es invitado y sus datos de contacto")

titulo("Vincular compras de invitado a una cuenta")
# 1) Registrarse con contraseña NO vincula (el correo no está verificado)
comprador = srv.cliente()
comprador.pedir("POST", "/api/pedidos", pedido([{"formato_id": fid, "cantidad": 1}],
                                               cliente={"nombre": "Ana", "correo": "ana@gmail.com", "telefono": "912345678"}))
suplantador = srv.cliente()
suplantador.registrar("ana@gmail.com", nombre="No soy Ana")
_, vistos = suplantador.pedir("GET", "/api/pedidos")
ok(vistos == [], "Registrarse con contraseña usando el correo de otra persona NO muestra sus compras", vistos)
# 2) Entrar con Google (correo verificado por Google) SÍ vincula
server.DB_PATH = srv.db
resultado, usuario_id = server.Handler._google_cuenta(None, {"sub": "google-ana", "email": "ana@gmail.com", "name": "Ana"}, False)
filas = consulta(srv.db, "SELECT usuario_id FROM pedidos WHERE cliente_correo='ana@gmail.com'")
ok(resultado == "ok" and all(f["usuario_id"] == usuario_id for f in filas), "Al entrar con Google con ese correo, sus compras pasan a la cuenta", filas)
comprador.pedir("POST", "/api/pedidos", pedido([{"formato_id": fid, "cantidad": 1}],
                                               cliente={"nombre": "Beto", "correo": "Beto@Gmail.com", "telefono": "912345678"}))
resultado, usuario_id = server.Handler._google_cuenta(None, {"sub": "google-beto", "email": "beto@gmail.com", "name": "Beto"}, True)
filas = consulta(srv.db, "SELECT usuario_id FROM pedidos WHERE cliente_correo='beto@gmail.com'")
ok(resultado == "nuevo" and filas and filas[0]["usuario_id"] == usuario_id, "Cuenta nueva con Google: también vincula (sin importar mayúsculas)")

titulo("Eliminar mi cuenta borra los datos de contacto de sus pedidos")
cuenta.pedir("POST", "/api/pedidos", pedido([{"formato_id": fid, "cantidad": 1}], entrega=DESPACHO, documento=FACTURA))
cuenta.pedir("POST", "/api/cuenta/eliminar")
filas = consulta(srv.db, "SELECT cliente_nombre, cliente_correo, cliente_telefono, direccion, comuna, factura_rut FROM pedidos "
                         "WHERE usuario_id=(SELECT id FROM usuarios WHERE nombre='Cuenta eliminada')")
ok(filas and all(f["cliente_correo"] is None and f["cliente_telefono"] is None and f["direccion"] is None
                 and f["cliente_nombre"] == "Cuenta eliminada" for f in filas),
   "Nombre, correo, teléfono y dirección se borran", filas)
ok(any(f["factura_rut"] == "76354771-K" for f in filas), "Los datos de la factura se conservan (documento tributario)")
srv.borrar()

titulo("Precios sin IVA (PRECIOS_INCLUYEN_IVA=0)")
srv = Servidor(entorno={"PRECIOS_INCLUYEN_IVA": "0"}).arrancar()
_, config = srv.cliente().pedir("GET", "/api/config")
ok(config["precios_incluyen_iva"] is False and config["tasa_iva"] == 19, "La configuración lo informa a la página")
estado, r = srv.cliente().pedir("POST", "/api/pedidos", pedido([{"formato_id": fid, "cantidad": 1}]))
ok(estado == 200 and (r["neto"], r["iva"], r["total"]) == (18990, 3608, 22598), "El IVA se suma encima: total $22.598", r)
srv.borrar()

titulo("Límite de pedidos por conexión")
srv = Servidor(entorno={"MAX_PEDIDOS_IP": "3"}).arrancar()
c = srv.cliente()
estados = [c.pedir("POST", "/api/pedidos", pedido([{"formato_id": fid, "cantidad": 1}]))[0] for _ in range(4)]
ok(estados == [200, 200, 200, 429], "Después de 3 pedidos en una hora desde la misma IP responde 429", estados)
estado, r = c.pedir("POST", "/api/pedidos", pedido([{"formato_id": fid, "cantidad": 1}], cliente={}))
ok(estado == 400, "Un pedido con datos inválidos responde 400 antes del límite (no gasta intentos)", estado)
srv.borrar()

titulo("Base de datos antigua: pedidos anteriores al checkout")
carpeta = Servidor()
antigua = os.path.join(carpeta.carpeta, "antigua.db")
con = sqlite3.connect(antigua)
con.executescript("""
    CREATE TABLE productos (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL, descripcion TEXT,
                            precio INTEGER NOT NULL, imagen TEXT, superficies TEXT, stock INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE usuarios (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL, correo TEXT NOT NULL UNIQUE,
                           clave TEXT NOT NULL, es_admin INTEGER DEFAULT 0);
    CREATE TABLE pedidos (id INTEGER PRIMARY KEY AUTOINCREMENT, usuario_id INTEGER, total INTEGER NOT NULL,
                          fecha TEXT DEFAULT (datetime('now','localtime')));
    CREATE TABLE pedido_items (id INTEGER PRIMARY KEY AUTOINCREMENT, pedido_id INTEGER, producto_id INTEGER,
                               nombre TEXT, precio INTEGER, cantidad INTEGER);
    CREATE TABLE sesiones (token TEXT PRIMARY KEY, usuario_id INTEGER, creada TEXT);
    INSERT INTO productos (nombre, precio, superficies, stock) VALUES ('Vieja', 1000, '["madera"]', 5);
    INSERT INTO usuarios (nombre, correo, clave) VALUES ('Ana Antigua', 'ana@antigua.cl', 'x$y');
    INSERT INTO pedidos (usuario_id, total) VALUES (1, 2000);
    INSERT INTO pedido_items (pedido_id, producto_id, nombre, precio, cantidad) VALUES (1, 1, 'Vieja', 1000, 2);
""")
con.commit()
con.close()
srv = Servidor(db_inicial=antigua).arrancar()
estado, todos = srv.admin().pedir("GET", "/api/admin/pedidos")
ok(estado == 200 and todos[0]["cliente_nombre"] == "Ana Antigua" and todos[0]["entrega"] is None and todos[0]["invitado"] is False,
   "El admin ve los pedidos antiguos con los datos de la cuenta", todos)
carpeta.borrar()
srv.borrar()

terminar()
