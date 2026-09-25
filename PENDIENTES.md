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

## Configuración del sitio (en `.env`)

| Variable | Qué es | Si falta |
|----------|--------|----------|
| `WHATSAPP_NUMERO` | Número de WhatsApp de la empresa, con código de país (ej: `56912345678`) | El botón de WhatsApp no aparece |
| `SITIO_URL` | Dirección pública del sitio (ej: `https://www.ecocordi.cl`) | El sitemap, robots.txt y las vistas previas en redes usan `http://localhost:8000` |
| `PRECIOS_INCLUYEN_IVA` | `1` si los precios del catálogo ya incluyen IVA; `0` si son netos | Se asume `1` (lo exigido al vender a consumidores en Chile). **Confirmar con la empresa.** |

## Checkout

| Dato | Dónde se completa |
|------|-------------------|
| **Tarifas de despacho** por región | Panel → pestaña "Despacho". Sin tarifa, el checkout dice "Coordinar despacho" y el costo se acuerda antes de pagar. |
| Dirección y horario de retiro en cada sucursal | `index.html` (sección Sucursales). El checkout hoy dice "te avisaremos cuando esté listo para retirar". |
| Medios de pago y plazos de entrega | Términos (`legales/generar.py`). Hoy **no se cobra en línea**: la empresa contacta al cliente. |
| **Envío de correos** (servidor SMTP) | Aún no existe. Hace falta para: enviar una copia del pedido (la exige el Reglamento de Comercio Electrónico), y verificar el correo de las cuentas con contraseña para vincularles sus compras como invitado (hoy solo se vinculan al entrar con Google). |

## Catálogo

| Dato | Dónde se completa |
|------|-------------------|
| **Formatos reales** de cada producto (1/4 galón, galón, tineta…), con sus **litros, precio y stock** | Panel de administración → Productos. Los productos de ejemplo parten con un solo formato "galón" con precios de ejemplo. |
| Litros exactos del "galón" que vende la empresa (se usó 3,785 L, el galón estadounidense; algunas marcas envasan 3,6 L) | Panel → cada formato. Valor por defecto en `server.py` (`LITROS_GALON`) |
| Litros de la tineta (no hay un tamaño único) | Panel → al crear el formato |
| **Ficha técnica** de cada producto — hoy son **valores de EJEMPLO** (marcados en la base de datos con `ficha_demo = 1` y avisados en pantalla): rendimiento (m² por litro en una mano), manos recomendadas, uso (interior / exterior / ambos), acabado (mate / satinado / brillante) y si resiste humedad, resiste sol directo y es lavable. El asistente y la calculadora usan estos datos. Los valores de ejemplo están en `server.py` (`FICHAS_DEMO`). | Panel → Productos → "Ficha técnica" de cada producto: corregir y desmarcar "Valores de ejemplo". |
| Productos, descripciones y fotos reales | Panel de administración |

## Revisión final

- [ ] Revisión de un abogado de Términos, Privacidad y Devoluciones.
- [ ] Revisar con el contador cómo se emitirán las boletas y facturas (el sitio guarda los datos, pero no emite documentos tributarios).
