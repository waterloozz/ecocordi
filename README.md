# 🎨 Ecocordi — Tienda Online

Sitio e-commerce de **Pinturas Ecocordi** — *"Majestuosas por Naturaleza"*.
Proyecto full-stack con frontend (HTML/CSS/JavaScript) y backend real con
base de datos (Python + SQLite), **sin necesidad de instalar dependencias**.

---

## 📖 ¿De qué se trata?

Ecocordi es una empresa chilena de pinturas con sucursales en **Talca** y
**Santiago**. Este proyecto es su **tienda online**: permite a los clientes
explorar el catálogo de pinturas, encontrar la pintura adecuada según la
**superficie que quieren pintar** (madera, metal, exterior, techo o interior),
agregar productos al carrito, crear una cuenta y realizar pedidos.

Además incluye un **panel de administración** donde el dueño de la tienda
puede revisar los pedidos recibidos y agregar o eliminar productos.

Fue desarrollado como **proyecto semestral** de la universidad, con el
objetivo de construir un e-commerce completo (frontend + backend + base de
datos) usando solo tecnologías estándar, sin frameworks ni librerías externas.

---

## 🚀 Cómo ejecutar el proyecto

Necesitas tener **Python 3** instalado (ya viene en la mayoría de los Linux/Mac).

1. Abre una terminal en la carpeta del proyecto.
2. Ejecuta:

   ```bash
   python3 server.py
   ```

   (o también: `bash iniciar.sh`)

3. Abre tu navegador en: **http://localhost:8000**
4. Para detener el servidor: `Ctrl + C`

---

## 🔑 Cuenta de administrador

La contraseña del administrador **no está en el código** (el repositorio es
público). Hay dos formas de obtenerla:

- **Automática:** la primera vez que ejecutas `python3 server.py` (sin base de
  datos previa), el servidor inventa una clave al azar y la muestra **una sola
  vez** en la terminal. ¡Anótala!
- **Elegirla tú:** define la variable de entorno `ADMIN_CLAVE` al arrancar.
  Esto también sirve para **cambiarla** o recuperarla si la olvidaste:

  ```bash
  ADMIN_CLAVE='tu-clave-secreta' python3 server.py
  ```

El correo del admin es `admin@ecocordi.cl` (se puede cambiar con `ADMIN_CORREO`).

Al iniciar sesión con esta cuenta aparece el enlace **"Admin"** en la cabecera,
que lleva al **panel de administración** (`/admin.html`) para ver pedidos y
gestionar productos.

> Cualquier otra persona puede **crear su propia cuenta** desde el botón 👤.

---

## 📂 Estructura del proyecto

```
ecocordi/
├── server.py          → Backend: servidor + base de datos (API)
├── ecocordi.db        → Base de datos SQLite (se crea sola al arrancar)
├── index.html         → Página principal: portada, superficies y 3 destacados
├── catalogo.html      → Catálogo completo con filtro por superficie (?superficie=madera)
├── admin.html         → Panel de administración
├── terminos.html, privacidad.html, cookies.html, devoluciones.html → Páginas legales
├── legales/generar.py → Genera las páginas legales
├── creditos.html      → Créditos de las fotografías
├── iniciar.sh         → Atajo para arrancar el servidor
├── css/
│   └── estilos.css    → Todo el diseño (variables de color, espacios y tipografía en :root)
├── js/
│   ├── luz.js         → Elige la luz (mañana/tarde/noche) antes de dibujar la página
│   ├── ui.js          → Avisos (toasts) y diálogo de confirmación, compartidos
│   ├── app.js         → Lógica de la tienda (catálogo, carrito, login)
│   └── admin.js       → Lógica del panel de administración
├── fonts/             → Tipografías servidas desde el propio sitio (licencia OFL)
├── actualizar_catalogo.py → Actualiza fotos y descripciones de productos en una ecocordi.db antigua
└── img/               → Fotos (WebP, de Unsplash; ver img/CREDITOS.md) y logo
```

---

## ✨ Funcionalidades

- **Catálogo** cargado desde la base de datos.
- **Filtro por superficie** (madera, metal, exterior, techo, interior): la
  funcionalidad estrella. Vive en `catalogo.html`; la superficie elegida queda en
  la dirección (por ejemplo `catalogo.html?superficie=madera`), así se puede
  compartir el enlace y el botón "atrás" vuelve al filtro anterior.
- **Carrito de compras** que se mantiene aunque cierres la página y no deja
  pedir más unidades de las que hay en bodega.
- **Stock** por producto: la tienda muestra "¡Quedan N!" cuando quedan 5 o
  menos y "Agotado" (botón deshabilitado) cuando no queda nada.
- **Cuentas de usuario** reales: registro e inicio de sesión con contraseñas
  encriptadas (nunca se guardan en texto plano).
- **Pedidos** guardados en la base de datos al finalizar la compra. El stock se
  revisa y descuenta en **una sola transacción**: si dos personas compran el
  último tarro al mismo tiempo, solo una lo consigue (la otra recibe un aviso).
- **Estados de pedido**: pendiente → pagado → enviado → entregado, o cancelado
  (al cancelar, las unidades vuelven al stock).
- **Mis pedidos**: cada cliente ve sus compras y el estado de cada una.
- **Panel de administración** protegido: ver pedidos y cambiar su estado,
  agregar/eliminar productos y editar su precio y stock.
- **Diseño "Luz de ventana"**: el mismo color cambia con la luz del día, y la
  página lo muestra. Según la hora de quien la visita se ve con luz de **mañana**,
  **tarde** o **noche** (fondo oscuro), y también se puede elegir a mano. Todas
  las fotos y colores cambian juntos (`js/luz.js` + variables en `css/estilos.css`).
- **Avisos y confirmaciones propios** (sin `alert()` ni `confirm()`).
- **Responsive desde 360 px**, foco de teclado visible, contraste AA y respeto
  por la opción "reducir movimiento" del sistema.
- **Espacios preparados** (sin lógica todavía): calculadora de m² a litros y
  botón flotante de WhatsApp.

---

## 🔐 Buenas prácticas de seguridad aplicadas

- Contraseñas encriptadas con **PBKDF2** (hash con sal, 100.000 iteraciones).
- Contraseñas de **mínimo 8 caracteres** al registrarse.
- Sesiones mediante **cookie HttpOnly** (no accesible desde JavaScript) que
  **vencen a los 7 días** también en el servidor; las vencidas se borran al arrancar.
- **Límite de intentos:** tras 5 intentos fallidos de login (o de registro) desde
  la misma IP en 10 minutos, el servidor responde `429` hasta que pase el tiempo.
- **El total de cada pedido lo calcula el servidor**, nunca el navegador, y se
  validan el id y la cantidad de cada producto.
- **Integridad de datos**: `PRAGMA foreign_keys = ON` y restricciones `CHECK`
  (el stock nunca puede quedar negativo; el estado solo acepta valores válidos).
- Si la base de datos es de una versión anterior, al arrancar se le agregan las
  columnas nuevas (`stock`, `estado`) **sin borrar datos**.
- Consultas SQL **parametrizadas** (protegen contra inyección SQL).
- Rutas de administrador protegidas (verifican que el usuario sea admin).
- Protección contra **XSS**: todo dato se escapa antes de mostrarse, y la
  cabecera **Content-Security-Policy** impide ejecutar scripts, `onclick="..."`
  o estilos escritos dentro del HTML. Por eso los eventos se conectan con
  `addEventListener` y los estilos viven en `css/estilos.css`.
- Cabeceras `X-Content-Type-Options: nosniff` y `Referrer-Policy: same-origin`.

---

## ⚖️ Aspectos legales y de privacidad

- Páginas: `terminos.html`, `privacidad.html`, `cookies.html` y `devoluciones.html`.
  Se generan con **`python3 legales/generar.py`** (edita ese archivo, no los .html).
  Los datos de la empresa se completan en `EMPRESA`, dentro de ese mismo archivo.
- **Consentimiento:** crear una cuenta y enviar un pedido exigen marcar una casilla
  (desmarcada por defecto). El servidor lo valida y guarda fecha y versión
  (`VERSION_TERMINOS` en `server.py`: súbela si cambias los textos).
- **Cookies:** solo la cookie de sesión (necesaria) y el carrito/luz en el
  navegador. Sin analíticas ni terceros, por eso no hay aviso de cookies.
- **Eliminar mi cuenta** (en "Mis pedidos"): borra nombre, correo y contraseña;
  los pedidos quedan sin datos personales.
- En producción con HTTPS, arranca con `COOKIE_SEGURA=1` para que la cookie
  de sesión solo viaje cifrada.
- **Pendiente antes de publicar:** datos de la empresa (razón social, RUT,
  domicilio), IVA, despacho y medios de pago, copia del pedido por correo y
  **revisión de un abogado**. Busca "Pendiente" y "Por confirmar" en los .html.

---

## 🛠️ Tecnologías

| Capa      | Tecnología                          |
|-----------|-------------------------------------|
| Frontend  | HTML5, CSS3, JavaScript (sin librerías) |
| Backend   | Python 3 (biblioteca estándar)      |
| Base datos| SQLite                              |
