# Pendientes antes de lanzar Ecocordi

Datos que **solo puede entregar la empresa** (o decisiones que le tocan a ella).
Nada de esto se inventó: donde falta el dato, la página muestra "Por confirmar"
o la función queda oculta. Cada punto dice **dónde se completa**.

> Los secretos (claves) van en el archivo `.env`, nunca en el código.
> Copia la plantilla con `cp .env.example .env`.

## Seguridad (hacer primero)

- [ ] **Cambiar la clave del administrador.** La base de datos local todavía usa
  la clave de ejemplo `admin123`. Se cambia con `ADMIN_CLAVE=...` en `.env`
  (o `ADMIN_CLAVE='...' python3 server.py`) y reiniciando el servidor.
- [ ] **Reiniciar el servidor** después de actualizar el código, para que tome
  el arreglo que impide descargar la base de datos (`/ecocordi.db`).

## Datos de la empresa

| Dato | Dónde se completa |
|------|-------------------|
| Razón social, RUT, domicilio legal, representante legal, teléfono | `legales/generar.py` (diccionario `EMPRESA`, luego `python3 legales/generar.py`) y el pie de `index.html` / `catalogo.html` |
| Dirección y horario de las sucursales de Talca y Santiago | `index.html` (sección Sucursales) |

## Catálogo

| Dato | Dónde se completa |
|------|-------------------|
| **Formatos reales** de cada producto (1/4 galón, galón, tineta…), con sus **litros, precio y stock** | Panel de administración → Productos. Los productos de ejemplo parten con un solo formato "galón" con precios de ejemplo. |
| Litros exactos del "galón" que vende la empresa (se usó 3,785 L, el galón estadounidense; algunas marcas envasan 3,6 L) | Panel → cada formato. Valor por defecto en `server.py` (`LITROS_GALON`) |
| Litros de la tineta (no hay un tamaño único) | Panel → al crear el formato |
| Productos, descripciones y fotos reales | Panel de administración |

## Revisión final

- [ ] Revisión de un abogado de Términos, Privacidad y Devoluciones.
- [ ] Definir despacho, medios de pago e IVA (se configuran en las fases siguientes).
