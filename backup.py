#!/usr/bin/env python3
# ============================================================
#  ECOCORDI - Copia de seguridad de la base de datos
#
#  Guarda una copia de ecocordi.db en la carpeta backups/ con la fecha en
#  el nombre (ecocordi-2026-09-24_030000.db) y borra las más antiguas:
#  conserva solo las últimas 14.
#
#  Usa la "API de backup" de SQLite: copia la base de datos de forma segura
#  AUNQUE el servidor esté funcionando y alguien esté comprando en ese
#  momento (copiar el archivo con cp podría dejar una copia a medias).
#
#  Uso manual:     python3 backup.py
#  Todos los días a las 3 AM con cron (ver README):
#      0 3 * * * cd /ruta/a/ecocordi && /usr/bin/python3 backup.py >> backups/backup.log 2>&1
#
#  Para restaurar una copia: detén el servidor, reemplaza ecocordi.db por
#  la copia elegida y vuelve a arrancarlo.
# ============================================================
import glob
import os
import sqlite3
import sys
import time

BASE = os.path.dirname(os.path.realpath(__file__))
CARPETA = os.environ.get("ECOCORDI_BACKUPS") or os.path.join(BASE, "backups")
CONSERVAR = 14


def hacer_backup(db_path, carpeta=CARPETA, prefijo="ecocordi", conservar=CONSERVAR):
    """Copia db_path a carpeta/<prefijo>-<fecha>.db y devuelve la ruta de la copia.
    Si conservar es un número, borra las copias más antiguas con ese prefijo."""
    if not os.path.isfile(db_path):
        raise FileNotFoundError(f"No existe la base de datos: {db_path}")
    os.makedirs(carpeta, mode=0o700, exist_ok=True)
    destino = os.path.join(carpeta, f"{prefijo}-{time.strftime('%Y-%m-%d_%H%M%S')}.db")
    n = 1
    while os.path.exists(destino):  # dos copias en el mismo segundo
        n += 1
        destino = os.path.join(carpeta, f"{prefijo}-{time.strftime('%Y-%m-%d_%H%M%S')}-{n}.db")

    origen = sqlite3.connect(db_path)
    copia = sqlite3.connect(destino)
    try:
        with copia:
            origen.backup(copia)  # copia página por página, de forma consistente
        # Revisamos que la copia sirva antes de darla por buena
        if copia.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise sqlite3.DatabaseError("La copia no pasó la revisión de integridad")
    except Exception:
        copia.close()
        os.remove(destino)
        raise
    finally:
        origen.close()
        copia.close()
    os.chmod(destino, 0o600)  # contiene datos personales: solo el dueño puede leerla

    if conservar:
        # El nombre lleva la fecha, así que ordenar por nombre = ordenar por fecha
        copias = sorted(glob.glob(os.path.join(carpeta, f"{prefijo}-*.db")))
        for vieja in copias[:-conservar]:
            os.remove(vieja)
    return destino


if __name__ == "__main__":
    import server  # lee el .env y sabe dónde está la base de datos (ECOCORDI_DB)
    try:
        ruta = hacer_backup(server.DB_PATH)
    except (OSError, sqlite3.Error) as e:
        print(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  ERROR en la copia de seguridad: {e}", file=sys.stderr)
        sys.exit(1)
    total = len(glob.glob(os.path.join(CARPETA, "ecocordi-*.db")))
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  Copia guardada: {os.path.relpath(ruta, BASE)} "
          f"({total} copias en {os.path.relpath(CARPETA, BASE)}/)")
