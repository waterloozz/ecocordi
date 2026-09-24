#!/usr/bin/env python3
# ============================================================
#  ECOCORDI - Actualiza las imágenes de productos en ecocordi.db
#
#  El rediseño "Luz de ventana" reemplazó las fotos .jpg antiguas por
#  fotos nuevas en WebP. Este script cambia la columna "imagen" de los
#  productos que TODAVÍA apuntan a una foto antigua. No borra nada y no
#  toca productos con otras imágenes (por ejemplo, las que puso el admin).
#
#  Uso (desde la carpeta del proyecto, con el servidor detenido o no):
#      python3 actualizar_imagenes.py
#  Se puede ejecutar varias veces: la segunda vez no cambia nada.
# ============================================================
import os
import sqlite3

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "ecocordi.db")

# Imagen nueva de cada producto de ejemplo (por nombre)
POR_NOMBRE = {
    "Protección de Madera":    "img/prod-madera.webp",
    "Anticorrosivo Metal Pro": "img/prod-metal.webp",
    "Pinturas para Exterior":  "img/prod-exterior.webp",
    "Línea Constructoras":     "img/prod-constructoras.webp",
    "Pinturas para Interior":  "img/prod-interior.webp",
    "Chalk Paint Ecocordi":    "img/prod-chalk.webp",
    "Productos Especiales":    "img/prod-especiales.webp",
    "Impermeabilizante Techo": "img/prod-techo.webp",
}
# Fotos antiguas que ya no existen, y con qué reemplazarlas si el nombre
# del producto no está en la lista de arriba (productos creados por el admin)
ANTIGUAS = {
    "img/madera.jpg":        "img/prod-madera.webp",
    "img/especiales.jpg":    "img/prod-especiales.webp",
    "img/exterior.jpg":      "img/prod-exterior.webp",
    "img/constructoras.jpg": "img/prod-constructoras.webp",
    "img/interior.jpg":      "img/prod-interior.webp",
    "img/chalk.jpg":         "img/prod-chalk.webp",
}

if not os.path.exists(DB_PATH):
    raise SystemExit("No encontré ecocordi.db. Ejecuta este script desde la carpeta del proyecto.")

con = sqlite3.connect(DB_PATH)
cambios = 0
with con:  # "with" = una sola transacción: o se guarda todo, o nada
    for pid, nombre, imagen in con.execute("SELECT id, nombre, imagen FROM productos").fetchall():
        if imagen not in ANTIGUAS:
            continue  # ya usa una imagen nueva o una elegida por el admin
        nueva = POR_NOMBRE.get(nombre, ANTIGUAS[imagen])
        con.execute("UPDATE productos SET imagen = ? WHERE id = ?", (nueva, pid))
        print(f"  {nombre}: {imagen} -> {nueva}")
        cambios += 1
con.close()
print(f"Listo: {cambios} producto(s) actualizados." if cambios else "No había nada que actualizar.")
