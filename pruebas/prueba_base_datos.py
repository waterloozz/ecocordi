#!/usr/bin/env python3
# ============================================================
#  ECOCORDI - Pruebas de la Fase 1 (base de datos)
#  Uso:  python3 pruebas/prueba_base_datos.py
#  Cada prueba usa una base de datos TEMPORAL; ecocordi.db no se toca.
# ============================================================
import glob
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from utilidades import RAIZ, Servidor, ok, pedido, terminar, titulo  # noqa: E402


def columnas(db, tabla):
    con = sqlite3.connect(db)
    cols = [r[1] for r in con.execute(f"PRAGMA table_info({tabla})")]
    con.close()
    return cols


def consulta(db, sql, params=()):
    con = sqlite3.connect(db)
    filas = con.execute(sql, params).fetchall()
    con.close()
    return filas


def crear_bd_antigua(ruta, con_stock=True):
    """Base de datos con el esquema ANTERIOR (precio, stock y superficies en productos)."""
    con = sqlite3.connect(ruta)
    stock = ", stock INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0)" if con_stock else ""
    con.executescript(f"""
        CREATE TABLE productos (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL, descripcion TEXT,
                                precio INTEGER NOT NULL, imagen TEXT, superficies TEXT{stock});
        CREATE TABLE usuarios (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL, correo TEXT NOT NULL UNIQUE,
                               clave TEXT NOT NULL, es_admin INTEGER DEFAULT 0);
        CREATE TABLE pedidos (id INTEGER PRIMARY KEY AUTOINCREMENT, usuario_id INTEGER, total INTEGER NOT NULL,
                              fecha TEXT DEFAULT (datetime('now','localtime')),
                              FOREIGN KEY (usuario_id) REFERENCES usuarios(id));
        CREATE TABLE pedido_items (id INTEGER PRIMARY KEY AUTOINCREMENT, pedido_id INTEGER, producto_id INTEGER,
                                   nombre TEXT, precio INTEGER, cantidad INTEGER,
                                   FOREIGN KEY (pedido_id) REFERENCES pedidos(id));
        CREATE TABLE sesiones (token TEXT PRIMARY KEY, usuario_id INTEGER,
                               creada TEXT DEFAULT (datetime('now','localtime')));
    """)
    cols = "nombre, descripcion, precio, imagen, superficies" + (", stock" if con_stock else "")
    marcas = "?,?,?,?,?" + (",?" if con_stock else "")
    filas = [("Madera Vieja", "d", 10000, "img/prod-madera.webp", '["techo", "madera"]', 7),
             ("Metal Viejo", "d", 20000, "img/prod-metal.webp", '["metal", "inventada"]', 3),
             ("Sin superficies", "d", 5000, "img/prod-chalk.webp", None, 0)]
    for f in filas:
        con.execute(f"INSERT INTO productos ({cols}) VALUES ({marcas})", f if con_stock else f[:5])
    con.execute("INSERT INTO usuarios (nombre, correo, clave) VALUES ('Ana', 'ana@correo.cl', 'x$y')")
    con.execute("INSERT INTO pedidos (usuario_id, total) VALUES (1, 40000)")
    con.execute("INSERT INTO pedido_items (pedido_id, producto_id, nombre, precio, cantidad) VALUES (1, 1, 'Madera Vieja', 10000, 2)")
    con.execute("INSERT INTO pedido_items (pedido_id, producto_id, nombre, precio, cantidad) VALUES (1, 2, 'Metal Viejo', 20000, 1)")
    con.commit()
    con.close()


# ------------------------------------------------------------
titulo("Base de datos nueva: tablas, índices y datos de ejemplo")
srv = Servidor().arrancar()
ok(set(columnas(srv.db, "productos")) == {"id", "nombre", "descripcion", "imagen", "rendimiento_m2_litro"},
   "productos ya no tiene precio, stock ni superficies", columnas(srv.db, "productos"))
indices = {r[0] for r in consulta(srv.db, "SELECT name FROM sqlite_master WHERE type='index'")}
for idx in ("idx_pedidos_usuario", "idx_pedidos_estado", "idx_pedido_items_pedido",
            "idx_sesiones_usuario", "idx_sesiones_creada"):
    ok(idx in indices, f"Índice {idx}")
plan = " ".join(r[3] for r in consulta(srv.db, "EXPLAIN QUERY PLAN SELECT * FROM pedidos WHERE usuario_id=1"))
ok("idx_pedidos_usuario" in plan, "La búsqueda de pedidos por usuario usa el índice", plan)

cliente = srv.cliente()
estado, productos = cliente.pedir("GET", "/api/productos")
ok(estado == 200 and len(productos) == 8, "8 productos de ejemplo", estado)
constructoras = next(p for p in productos if p["nombre"] == "Línea Constructoras")
ok(constructoras["superficies"] == ["techo", "exterior"], "Superficies en el mismo orden que antes (define el color)",
   constructoras["superficies"])
f0 = productos[0]["formatos"]
ok(len(f0) == 1 and f0[0]["nombre"] == "galón" and f0[0]["stock"] == 20 and f0[0]["precio"] == 18990,
   "Cada producto parte con un formato 'galón' con su precio y stock", f0)
ok(productos[0]["precio"] == 18990 and productos[0]["stock"] == 20, "La API sigue entregando precio y stock del producto")
estado, techo = cliente.pedir("GET", "/api/productos?superficie=techo")
ok(sorted(p["nombre"] for p in techo) == ["Impermeabilizante Techo", "Línea Constructoras"],
   "Filtro ?superficie=techo responde igual que antes", [p["nombre"] for p in techo])

# ------------------------------------------------------------
titulo("Pedidos por formato")
cliente.registrar("comprador@correo.cl")
fid = productos[0]["formatos"][0]["id"]
estado, r = cliente.pedir("POST", "/api/pedidos", pedido([{"formato_id": fid, "cantidad": 3}]))
ok(estado == 200 and r["total"] == 3 * 18990, "Pedido con formato_id: total calculado por el servidor", r)
stock = consulta(srv.db, "SELECT stock FROM producto_formatos WHERE id=?", (fid,))[0][0]
ok(stock == 17, "El stock se descuenta del formato", stock)
item = consulta(srv.db, "SELECT formato_id, formato, nombre, precio FROM pedido_items WHERE pedido_id=?", (r["pedido_id"],))[0]
ok(item == (fid, "galón", "Protección de Madera", 18990), "El pedido guarda formato, nombre y precio del momento", item)
estado, mis = cliente.pedir("GET", "/api/pedidos")
ok(mis[0]["items"][0]["formato"] == "galón", "Mis pedidos muestra el formato")
for items, texto in (([{"id": fid, "cantidad": 1}], "formato antiguo {id}"),
                     ([{"formato_id": fid, "cantidad": "abc"}], "cantidad 'abc'"),
                     ([{"formato_id": fid, "cantidad": -5}], "cantidad -5"),
                     ([{"formato_id": str(fid), "cantidad": 1}], "formato_id como texto")):
    estado, _ = cliente.pedir("POST", "/api/pedidos", pedido(items))
    ok(estado == 400, f"Rechaza {texto} (400)", estado)
estado, r = cliente.pedir("POST", "/api/pedidos", pedido([{"formato_id": 99999, "cantidad": 1}]))
ok(estado == 400, "Rechaza un formato que no existe (400)", estado)
estado, r = cliente.pedir("POST", "/api/pedidos", pedido([{"formato_id": fid, "cantidad": 18}]))
ok(estado == 409 and r.get("disponible") == 17 and r.get("formato_id") == fid, "Sin stock suficiente: 409 con lo disponible", r)

# Dos compras al mismo tiempo por la última unidad
admin = srv.admin()
admin.pedir("PATCH", f"/api/admin/formatos/{fid}", {"stock": 1})
otro = srv.cliente()
otro.registrar("otro@correo.cl")
respuestas = []
hilos = [threading.Thread(target=lambda c=c: respuestas.append(
    c.pedir("POST", "/api/pedidos", pedido([{"formato_id": fid, "cantidad": 1}]))[0]))
    for c in (cliente, otro)]
[h.start() for h in hilos]
[h.join() for h in hilos]
ok(sorted(respuestas) == [200, 409], "Dos compras simultáneas por la última unidad: una gana, la otra 409", respuestas)
ok(consulta(srv.db, "SELECT stock FROM producto_formatos WHERE id=?", (fid,))[0][0] == 0, "El stock queda en 0 (nunca negativo)")

# Cancelar devuelve al formato
pedido_id = consulta(srv.db, "SELECT MIN(id) FROM pedidos")[0][0]
estado, _ = admin.pedir("PATCH", f"/api/admin/pedidos/{pedido_id}", {"estado": "cancelado"})
ok(estado == 200 and consulta(srv.db, "SELECT stock FROM producto_formatos WHERE id=?", (fid,))[0][0] == 3,
   "Cancelar un pedido devuelve las unidades al stock del formato")

# ------------------------------------------------------------
titulo("Admin: productos, formatos y superficies")
nuevo = {"nombre": "Esmalte Prueba", "descripcion": "x", "superficies": ["metal", "madera"],
         "formatos": [{"nombre": "1/4 galón", "litros": 0.946, "precio": 6990, "stock": 5},
                      {"nombre": "galón", "litros": 3.785, "precio": 19990, "stock": 2}]}
estado, r = cliente.pedir("POST", "/api/admin/productos", nuevo)
ok(estado == 403, "Un cliente no puede crear productos (403)", estado)
estado, r = admin.pedir("POST", "/api/admin/productos", nuevo)
ok(estado == 200, "El admin crea un producto con dos formatos", r)
pid = r.get("id")
_, lista = cliente.pedir("GET", "/api/productos")
p = next(x for x in lista if x["id"] == pid)
ok([f["nombre"] for f in p["formatos"]] == ["1/4 galón", "galón"] and p["precio"] == 6990 and p["stock"] == 7,
   "Formatos ordenados por litros; precio 'desde' y stock total", p)
ok(p["superficies"] == ["metal", "madera"], "Superficies guardadas en orden")
for malo, texto in (({**nuevo, "formatos": []}, "sin formatos"),
                    ({**nuevo, "superficies": ["lava"]}, "superficie inventada"),
                    ({**nuevo, "formatos": [{"nombre": "x", "litros": 0, "precio": 1}]}, "litros 0"),
                    ({**nuevo, "formatos": [{"nombre": "x", "litros": 1, "precio": -1}]}, "precio negativo"),
                    ({**nuevo, "formatos": [{"nombre": "a", "litros": 1, "precio": 1}] * 2}, "formatos repetidos")):
    estado, _ = admin.pedir("POST", "/api/admin/productos", malo)
    ok(estado == 400, f"Rechaza producto con {texto} (400)", estado)
estado, r = admin.pedir("POST", f"/api/admin/productos/{pid}/formatos", {"nombre": "tineta", "litros": 18.9, "precio": 79990, "stock": 1})
ok(estado == 200, "Agregar un formato 'tineta'", r)
tineta = r.get("id")
estado, _ = admin.pedir("POST", f"/api/admin/productos/{pid}/formatos", {"nombre": "tineta", "litros": 18.9, "precio": 1})
ok(estado == 409, "No permite dos formatos con el mismo nombre (409)", estado)
estado, r = admin.pedir("PATCH", f"/api/admin/formatos/{tineta}", {"precio": 75990, "stock": 4})
ok(estado == 200 and r["precio"] == 75990 and r["stock"] == 4, "Editar precio y stock de un formato", r)
estado, _ = admin.pedir("PATCH", f"/api/admin/formatos/{tineta}", {"stock": -1})
ok(estado == 400, "Stock negativo rechazado (400)", estado)
estado, _ = cliente.pedir("PATCH", f"/api/admin/formatos/{tineta}", {"stock": 999})
ok(estado == 403, "Un cliente no puede editar formatos (403)", estado)
estado, _ = admin.pedir("PATCH", f"/api/admin/productos/{pid}", {"superficies": ["exterior"], "nombre": "Esmalte Editado"})
_, lista = cliente.pedir("GET", "/api/productos?superficie=exterior")
ok(estado == 200 and any(x["nombre"] == "Esmalte Editado" for x in lista), "Editar nombre y superficies de un producto")
estado, _ = admin.pedir("DELETE", f"/api/admin/formatos/{tineta}")
ok(estado == 200 and not consulta(srv.db, "SELECT 1 FROM producto_formatos WHERE id=?", (tineta,)), "Borrar un formato")
estado, _ = admin.pedir("DELETE", f"/api/admin/productos/{pid}")
quedan = consulta(srv.db, "SELECT (SELECT COUNT(*) FROM producto_formatos WHERE producto_id=?), "
                          "(SELECT COUNT(*) FROM producto_superficies WHERE producto_id=?)", (pid, pid))[0]
ok(estado == 200 and quedan == (0, 0), "Borrar un producto borra sus formatos y superficies (cascada)", quedan)
estado, _ = admin.pedir("DELETE", "/api/admin/productos/99999")
ok(estado == 404, "Borrar un producto que no existe: 404", estado)

# ------------------------------------------------------------
titulo("Archivos privados: el servidor no los entrega")
for ruta in ("/ecocordi.db", "/server.py", "/backup.py", "/.git/config", "/.env", "/backups/", "/pruebas/utilidades.py",
             "/css/../server.py", "/img/..%2f..%2fserver.py"):
    try:
        codigo = urllib.request.urlopen(srv.url + ruta).status
    except urllib.error.HTTPError as e:
        codigo = e.code
    ok(codigo == 404, f"{ruta} → 404", codigo)
srv.borrar()

# ------------------------------------------------------------
titulo("Migración de una base de datos antigua (sin perder datos)")
carpeta = tempfile.mkdtemp()
antigua = os.path.join(carpeta, "antigua.db")
crear_bd_antigua(antigua)
srv = Servidor(db_inicial=antigua).arrancar()
ok("Migración" in srv.salida, "El servidor avisa la migración")
copias = glob.glob(os.path.join(srv.carpeta, "backups", "antes-de-migrar-*.db"))
ok(len(copias) == 1 and "precio" in columnas(copias[0], "productos"),
   "Guarda una copia de seguridad ANTES de migrar (con el esquema antiguo)", copias)
ok(set(columnas(srv.db, "productos")) == {"id", "nombre", "descripcion", "imagen", "rendimiento_m2_litro"}, "Columnas antiguas eliminadas")
_, lista = srv.cliente().pedir("GET", "/api/productos")
por_nombre = {p["nombre"]: p for p in lista}
ok(por_nombre["Madera Vieja"]["superficies"] == ["techo", "madera"], "Superficies traspasadas en su orden")
ok(por_nombre["Metal Viejo"]["superficies"] == ["metal"], "Superficies desconocidas se descartan")
ok(por_nombre["Sin superficies"]["superficies"] == [], "Producto sin superficies (NULL) no falla")
ok([(f["nombre"], f["precio"], f["stock"]) for f in por_nombre["Madera Vieja"]["formatos"]] == [("galón", 10000, 7)],
   "Precio y stock pasan a un formato 'galón'")
items = consulta(srv.db, "SELECT producto_id, formato_id, formato FROM pedido_items ORDER BY id")
ok(all(fid and fmt == "galón" for _, fid, fmt in items), "Los pedidos antiguos quedan apuntando a su formato", items)
ok(consulta(srv.db, "SELECT COUNT(*) FROM usuarios WHERE correo='ana@correo.cl'")[0][0] == 1, "Los usuarios se conservan")
ok(consulta(srv.db, "SELECT estado FROM pedidos")[0][0] == "pendiente", "Pedido antiguo con estado 'pendiente'")
ok(consulta(srv.db, "PRAGMA foreign_key_check") == [] and consulta(srv.db, "PRAGMA integrity_check")[0][0] == "ok",
   "Integridad y claves foráneas OK después de migrar")
admin = srv.admin()
estado, _ = admin.pedir("PATCH", "/api/admin/pedidos/1", {"estado": "cancelado"})
ok(consulta(srv.db, "SELECT stock FROM producto_formatos f JOIN productos p ON p.id=f.producto_id WHERE p.nombre='Madera Vieja'")[0][0] == 9,
   "Cancelar un pedido antiguo devuelve el stock a su formato")
srv.detener()
srv.arrancar()  # segunda vez: no debe migrar de nuevo
ok("Servidor iniciado" in srv.salida and "Migración" not in srv.salida, "Al arrancar de nuevo no vuelve a migrar", srv.salida)
ok(consulta(srv.db, "SELECT COUNT(*) FROM producto_formatos")[0][0] == 3, "No duplica formatos")
ok(len(glob.glob(os.path.join(srv.carpeta, "backups", "antes-de-migrar-*.db"))) == 1, "No hace otra copia de migración")
srv.borrar()

crear_bd_antigua(os.path.join(carpeta, "muy-antigua.db"), con_stock=False)
srv = Servidor(db_inicial=os.path.join(carpeta, "muy-antigua.db")).arrancar()
_, lista = srv.cliente().pedir("GET", "/api/productos")
ok(lista and all(p["formatos"][0]["stock"] == 20 for p in lista), "BD anterior al stock: los formatos parten con 20 unidades")
srv.borrar()

real = os.path.join(RAIZ, "ecocordi.db")
if os.path.exists(real):
    srv = Servidor(db_inicial=real)  # COPIA de la base real
    antes = {t: consulta(srv.db, f"SELECT COUNT(*) FROM {t}")[0][0] for t in ("productos", "usuarios", "pedidos", "pedido_items")}
    srv.arrancar()
    despues = {t: consulta(srv.db, f"SELECT COUNT(*) FROM {t}")[0][0] for t in antes}
    ok(antes == despues, "Copia de tu ecocordi.db: se conservan productos, usuarios y pedidos", (antes, despues))
    ok(consulta(srv.db, "SELECT COUNT(*) FROM producto_formatos")[0][0] >= antes["productos"],
       "Copia de tu ecocordi.db: cada producto tiene su formato")
    srv.borrar()

# ------------------------------------------------------------
titulo("Copias de seguridad (backup.py)")
bk = os.path.join(carpeta, "bk")
os.makedirs(bk)
for i in range(16):  # 16 copias "antiguas"
    open(os.path.join(bk, f"ecocordi-2020-01-{i + 1:02d}_030000.db"), "w").close()
entorno = dict(os.environ, ECOCORDI_DB=antigua, ECOCORDI_BACKUPS=bk)
r = subprocess.run([sys.executable, os.path.join(RAIZ, "backup.py")], env=entorno, capture_output=True, text=True)
copias = sorted(glob.glob(os.path.join(bk, "ecocordi-*.db")))
ok(r.returncode == 0 and "Copia guardada" in r.stdout, "backup.py termina bien", r.stdout + r.stderr)
ok(len(copias) == 14, "Conserva solo las últimas 14 copias", len(copias))
ok(not os.path.exists(os.path.join(bk, "ecocordi-2020-01-01_030000.db")), "Borra las más antiguas")
ok(consulta(copias[-1], "PRAGMA integrity_check")[0][0] == "ok" and
   consulta(copias[-1], "SELECT COUNT(*) FROM productos")[0][0] == 3, "La copia nueva es una base de datos válida y completa")
ok(oct(os.stat(copias[-1]).st_mode & 0o777) == "0o600", "La copia solo la puede leer su dueño (permisos 600)")
r = subprocess.run([sys.executable, os.path.join(RAIZ, "backup.py")],
                   env=dict(entorno, ECOCORDI_DB=os.path.join(carpeta, "no-existe.db")), capture_output=True, text=True)
ok(r.returncode == 1 and "ERROR" in r.stderr, "Si la base no existe, avisa el error (código 1)")

terminar()
