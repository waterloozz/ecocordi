#!/usr/bin/env python3
# ============================================================
#  ECOCORDI - Actualiza los productos de ejemplo en una ecocordi.db antigua
#
#  1) Imágenes: el rediseño "Luz de ventana" reemplazó las fotos .jpg por
#     fotos nuevas en WebP. Cambia la columna "imagen" de los productos que
#     TODAVÍA apuntan a una foto antigua.
#  2) Descripciones: se quitaron afirmaciones sin respaldo ("cobertura
#     perfecta", "alto rendimiento"...). Cambia la descripción SOLO si sigue
#     siendo el texto de ejemplo original.
#  No borra nada y no toca lo que el admin haya cambiado.
#
#  Uso (desde la carpeta del proyecto, con el servidor detenido o no):
#      python3 actualizar_catalogo.py
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

# Descripciones de ejemplo antiguas -> nuevas
DESCRIPCIONES = {
    'Acabado y protección para muebles, puertas y decks.': 'Para muebles, puertas y decks de madera.',
    'Protege rejas, portones y estructuras contra el óxido.': 'Para rejas, portones y estructuras de metal.',
    'Resistente al sol y la lluvia para fachadas duraderas.': 'Para fachadas y muros exteriores.',
    'Alto rendimiento para grandes proyectos y obras.': 'Para proyectos y obras de mayor tamaño.',
    'Cobertura perfecta y acabado elegante para muros interiores.': 'Para muros y cielos interiores.',
    'Pintura a la tiza para renovar muebles con estilo vintage.': 'Pintura a la tiza para renovar muebles.',
    'Soluciones específicas de alto desempeño para cada trabajo.': 'Para usos específicos: consúltanos cuál sirve para tu trabajo.',
    'Sella y protege techos y cubiertas contra filtraciones.': 'Para techos y cubiertas.',
}

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
    for pid, nombre, descripcion in con.execute("SELECT id, nombre, descripcion FROM productos").fetchall():
        if descripcion in DESCRIPCIONES:
            con.execute("UPDATE productos SET descripcion = ? WHERE id = ?", (DESCRIPCIONES[descripcion], pid))
            print(f"  {nombre}: descripción actualizada")
            cambios += 1
con.close()
print(f"Listo: {cambios} cambio(s)." if cambios else "No había nada que actualizar.")
