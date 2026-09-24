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
├── index.html         → Página principal de la tienda
├── admin.html         → Panel de administración
├── iniciar.sh         → Atajo para arrancar el servidor
├── css/
│   └── estilos.css    → Todo el diseño
├── js/
│   ├── app.js         → Lógica de la tienda (catálogo, carrito, login)
│   └── admin.js       → Lógica del panel de administración
└── img/               → Logo e imágenes de productos
```

---

## ✨ Funcionalidades

- **Catálogo** cargado desde la base de datos.
- **Filtro por superficie** (madera, metal, exterior, techo, interior) — la
  funcionalidad estrella, también accesible desde el mega-menú.
- **Carrito de compras** que se mantiene aunque cierres la página.
- **Cuentas de usuario** reales: registro e inicio de sesión con contraseñas
  encriptadas (nunca se guardan en texto plano).
- **Pedidos** guardados en la base de datos al finalizar la compra.
- **Panel de administración** protegido: ver pedidos y agregar/eliminar productos.
- **Diseño premium**: cabecera fija estilo Apple con mega-menús, portada
  cinematográfica con efecto parallax y animaciones al hacer scroll.
- **Responsive**: se adapta a celulares y tablets.

---

## 🔐 Buenas prácticas de seguridad aplicadas

- Contraseñas encriptadas con **PBKDF2** (hash con sal, 100.000 iteraciones).
- Sesiones mediante **cookie HttpOnly** (no accesible desde JavaScript).
- **El total de cada pedido lo calcula el servidor**, nunca el navegador.
- Consultas SQL **parametrizadas** (protegen contra inyección SQL).
- Rutas de administrador protegidas (verifican que el usuario sea admin).

---

## 🛠️ Tecnologías

| Capa      | Tecnología                          |
|-----------|-------------------------------------|
| Frontend  | HTML5, CSS3, JavaScript (sin librerías) |
| Backend   | Python 3 (biblioteca estándar)      |
| Base datos| SQLite                              |
