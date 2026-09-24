/* ============================================================
   ECOCORDI - Lógica del sitio (frontend)
   Ahora conectado a un backend real con base de datos.
   El navegador pide los datos al servidor con "fetch".
   ============================================================ */

/* -------- 1. ESTADO GLOBAL -------- */
let productos = [];   // se llenará con los productos que envía el servidor
let carrito = [];     // productos que el usuario agregó
let usuario = null;   // datos del usuario si inició sesión (o null)
let superficieActiva = "todas"; // filtro elegido en el catálogo

/* -------- 2. REFERENCIAS A ELEMENTOS DEL HTML -------- */
const contenedorProductos = document.getElementById("productos");
const contenedorFiltros   = document.getElementById("filtros");
const contadorCarrito     = document.getElementById("contadorCarrito");
const carritoItems        = document.getElementById("carritoItems");
const carritoTotal        = document.getElementById("carritoTotal");
const panelCarrito        = document.getElementById("carrito");
const fondoCarrito        = document.getElementById("carritoFondo");
const cuentaArea          = document.getElementById("cuentaArea");

/* -------- 3. UTILIDAD: formatear precios en pesos chilenos -------- */
function formatearPrecio(valor) {
  return "$" + valor.toLocaleString("es-CL");
}

/* -------- UTILIDAD: escapar texto antes de meterlo en el HTML --------
   Convierte los caracteres especiales (< > & " ') en su versión "inofensiva"
   (&lt; &gt; ...). Así, si alguien se registra con el nombre
   <img src=x onerror=alert(1)>, el navegador lo MUESTRA como texto
   en vez de ejecutarlo. Úsala con todo dato que venga del usuario o de la BD. */
function escaparHTML(texto) {
  return String(texto ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/* -------- 4. TRAER LOS PRODUCTOS DESDE EL SERVIDOR --------
   "fetch" pide datos a la API. "await" espera la respuesta.
   Así el catálogo ya no está escrito a mano: viene de la base de datos. */
async function cargarProductos() {
  try {
    const respuesta = await fetch("/api/productos");
    productos = await respuesta.json();
    mostrarCatalogo();
    sincronizarCarrito();
  } catch (error) {
    contenedorProductos.innerHTML =
      "<p class='sin-resultados'>No se pudieron cargar los productos. ¿Está encendido el servidor?</p>";
  }
}

/* -------- 5. MOSTRAR PRODUCTOS EN PANTALLA -------- */
function mostrarProductos(lista) {
  contenedorProductos.innerHTML = "";

  if (lista.length === 0) {
    contenedorProductos.innerHTML =
      "<p class='sin-resultados'>No hay pinturas para esta superficie todavía.</p>";
    return;
  }

  lista.forEach(function (p) {
    // Stock: "Agotado" si no queda nada, "Quedan N" si quedan 5 o menos
    const agotado = p.stock <= 0;
    let avisoStock = "";
    if (agotado) {
      avisoStock = '<p class="producto__stock producto__stock--agotado">Agotado</p>';
    } else if (p.stock <= 5) {
      avisoStock = `<p class="producto__stock">¡Quedan ${p.stock}!</p>`;
    }
    const tarjeta = `
      <div class="producto" data-id="${p.id}">
        <img class="producto__imagen" src="${escaparHTML(p.imagen)}" alt="${escaparHTML(p.nombre)}"
             loading="lazy" decoding="async" />
        <div class="producto__cuerpo">
          <h3 class="producto__nombre">${escaparHTML(p.nombre)}</h3>
          <p class="producto__desc">${escaparHTML(p.descripcion)}</p>
          <p class="producto__precio">${formatearPrecio(p.precio)}</p>
          ${avisoStock}
          <button class="producto__boton" ${agotado ? "disabled" : ""}>
            ${agotado ? "Agotado" : "Agregar al carrito"}
          </button>
        </div>
      </div>
    `;
    contenedorProductos.innerHTML += tarjeta;
  });
}

/* -------- 5b. CLIC EN "AGREGAR AL CARRITO" (delegación de eventos) --------
   En vez de poner onclick="..." en cada botón (la CSP del servidor lo
   bloquea), ponemos UN solo "escuchador" en el contenedor de productos.
   Cuando haces clic en cualquier parte de adentro, revisamos si fue en un
   botón, y leemos el id desde el atributo data-id de la tarjeta. */
contenedorProductos.addEventListener("click", function (evento) {
  const boton = evento.target.closest(".producto__boton");
  if (!boton) return; // el clic no fue en el botón
  const tarjeta = boton.closest(".producto");
  agregarAlCarrito(Number(tarjeta.dataset.id));
});

/* -------- 6. FILTRO POR SUPERFICIE (funcionalidad estrella) -------- */
contenedorFiltros.addEventListener("click", function (evento) {
  if (!evento.target.classList.contains("filtro")) return;

  document.querySelectorAll(".filtro").forEach(function (btn) {
    btn.classList.remove("filtro--activo");
  });
  evento.target.classList.add("filtro--activo");

  superficieActiva = evento.target.dataset.superficie;
  mostrarCatalogo();
});

/* Muestra los productos según el filtro elegido. Se usa también cuando el
   catálogo se recarga (por ejemplo, después de comprar cambia el stock). */
function mostrarCatalogo() {
  if (superficieActiva === "todas") {
    mostrarProductos(productos);
  } else {
    mostrarProductos(productos.filter(function (p) {
      return p.superficies.includes(superficieActiva);
    }));
  }
}

/* -------- 7. CARRITO: agregar, cambiar cantidad, eliminar -------- */
function agregarAlCarrito(id) {
  const producto = productos.find(function (p) { return p.id === id; });
  const enCarrito = carrito.find(function (item) { return item.id === id; });

  if (enCarrito) {
    // No dejamos pedir más de lo que hay en bodega
    if (enCarrito.cantidad >= producto.stock) {
      alert("Ya tienes en tu carrito todas las unidades disponibles de " +
            producto.nombre + " (" + producto.stock + ").");
      return;
    }
    enCarrito.cantidad++;
  } else {
    carrito.push({ ...producto, cantidad: 1 });
  }
  actualizarCarrito();
  abrirCarrito();
}

function cambiarCantidad(id, cambio) {
  const item = carrito.find(function (i) { return i.id === id; });
  if (cambio > 0 && item.cantidad >= item.stock) return; // sin más stock
  item.cantidad += cambio;
  if (item.cantidad <= 0) {
    eliminarDelCarrito(id);
  } else {
    actualizarCarrito();
  }
}

function eliminarDelCarrito(id) {
  carrito = carrito.filter(function (item) { return item.id !== id; });
  actualizarCarrito();
}

/* -------- 8. ACTUALIZAR EL CARRITO EN PANTALLA -------- */
function actualizarCarrito() {
  carritoItems.innerHTML = "";

  if (carrito.length === 0) {
    carritoItems.innerHTML = "<p class='carrito__vacio'>Tu carrito está vacío 🛒</p>";
  }

  let total = 0;
  let cantidadTotal = 0;

  carrito.forEach(function (item) {
    total += item.precio * item.cantidad;
    cantidadTotal += item.cantidad;

    const fila = `
      <div class="item" data-id="${item.id}">
        <img class="item__color" src="${escaparHTML(item.imagen)}" alt="${escaparHTML(item.nombre)}" />
        <div class="item__info">
          <div class="item__nombre">${escaparHTML(item.nombre)}</div>
          <div class="item__precio">${formatearPrecio(item.precio)}</div>
          <div class="item__controles">
            <button class="item__btn" data-accion="restar">−</button>
            <span>${item.cantidad}</span>
            <button class="item__btn" data-accion="sumar"
                    ${item.cantidad >= item.stock ? "disabled" : ""}>+</button>
          </div>
          ${item.cantidad >= item.stock ? `<div class="item__max">Máximo disponible: ${item.stock}</div>` : ""}
        </div>
        <button class="item__eliminar" data-accion="eliminar">🗑️</button>
      </div>
    `;
    carritoItems.innerHTML += fila;
  });

  carritoTotal.textContent = formatearPrecio(total);
  contadorCarrito.textContent = cantidadTotal;
  guardarCarrito(); // guardamos en el navegador para que no se pierda
}

/* -------- 8b. CLICS DENTRO DEL CARRITO (delegación de eventos) --------
   Cada botón dice qué hace con data-accion ("restar", "sumar", "eliminar")
   y la fila del carrito guarda el id del producto en data-id. */
carritoItems.addEventListener("click", function (evento) {
  const boton = evento.target.closest("[data-accion]");
  if (!boton) return;
  const id = Number(boton.closest(".item").dataset.id);
  const accion = boton.dataset.accion;
  if (accion === "restar")   cambiarCantidad(id, -1);
  if (accion === "sumar")    cambiarCantidad(id, 1);
  if (accion === "eliminar") eliminarDelCarrito(id);
});

/* -------- 9. CARRITO PERSISTENTE (localStorage) --------
   localStorage guarda datos en el navegador aunque cierres la página. */
function guardarCarrito() {
  localStorage.setItem("carrito_ecocordi", JSON.stringify(carrito));
}
function cargarCarrito() {
  const guardado = localStorage.getItem("carrito_ecocordi");
  if (guardado) carrito = JSON.parse(guardado);
}

/* El carrito guardado puede estar desactualizado: quizás el admin borró un
   producto, cambió su precio o se agotó. Cuando llega el catálogo real,
   quitamos lo que ya no existe o está agotado, copiamos nombre, precio,
   imagen y stock actuales, y bajamos la cantidad si supera el stock. */
function sincronizarCarrito() {
  carrito = carrito
    .filter(function (item) {
      return productos.some(function (p) { return p.id === item.id && p.stock > 0; });
    })
    .map(function (item) {
      const actual = productos.find(function (p) { return p.id === item.id; });
      return { ...actual, cantidad: Math.min(item.cantidad, actual.stock) };
    });
  actualizarCarrito();
}

/* -------- 10. ABRIR / CERRAR EL PANEL DEL CARRITO -------- */
function abrirCarrito() {
  panelCarrito.classList.add("abierto");
  fondoCarrito.classList.add("abierto");
}
function cerrarCarrito() {
  panelCarrito.classList.remove("abierto");
  fondoCarrito.classList.remove("abierto");
}
document.getElementById("btnAbrirCarrito").addEventListener("click", abrirCarrito);
document.getElementById("btnCerrarCarrito").addEventListener("click", cerrarCarrito);
fondoCarrito.addEventListener("click", cerrarCarrito);

/* -------- 11. FINALIZAR COMPRA (guarda el pedido en la base de datos) -------- */
document.getElementById("btnPagar").addEventListener("click", async function () {
  if (carrito.length === 0) {
    alert("Tu carrito está vacío. ¡Agrega algunas pinturas primero!");
    return;
  }

  // Enviamos solo id y cantidad; el servidor calcula el total con precios reales
  const items = carrito.map(function (i) {
    return { id: i.id, cantidad: i.cantidad };
  });

  const respuesta = await fetch("/api/pedidos", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items: items }),
  });

  if (respuesta.status === 401) {
    alert("Debes iniciar sesión para finalizar tu compra.");
    cerrarCarrito();
    abrirLogin();
    return;
  }

  const datos = await respuesta.json();
  if (respuesta.status === 409) {
    // Alguien compró antes que tú: traemos el stock real y ajustamos el carrito
    alert(datos.error + "\nAjustamos tu carrito al stock disponible.");
    await cargarProductos();
    return;
  }
  if (!respuesta.ok) {
    alert("No se pudo completar la compra: " + (datos.error || "error desconocido"));
    return;
  }
  alert("¡Gracias por tu compra en Ecocordi! 🎨\n" +
        "Pedido N° " + datos.pedido_id + "\n" +
        "Total: " + formatearPrecio(datos.total));

  carrito = [];
  actualizarCarrito();
  cerrarCarrito();
  cargarProductos(); // el stock cambió: refrescamos "Quedan N" / "Agotado"
});

/* ============================================================
   CUENTAS DE USUARIO (registro / inicio de sesión)
   ============================================================ */
const modalLogin = document.getElementById("modalLogin");
const modalFondo  = document.getElementById("modalFondo");
const modalError  = document.getElementById("modalError");
let modoRegistro = false; // false = iniciar sesión, true = crear cuenta

/* -------- 12. SABER QUIÉN INICIÓ SESIÓN -------- */
async function cargarUsuario() {
  const respuesta = await fetch("/api/me");
  const datos = await respuesta.json();
  usuario = datos.invitado ? null : datos;
  renderCuenta();
}

/* Dibuja el área de cuenta en la cabecera según haya sesión o no */
function renderCuenta() {
  if (usuario) {
    const primerNombre = usuario.nombre.split(" ")[0];
    const linkAdmin = usuario.es_admin
      ? '<a href="admin.html" class="cuenta__link">Admin</a>' : "";
    cuentaArea.innerHTML = `
      <span class="cuenta__saludo">Hola, ${escaparHTML(primerNombre)}</span>
      <button class="cuenta__link cuenta__boton" id="btnMisPedidos">Mis pedidos</button>
      ${linkAdmin}
      <button class="cuenta__salir" id="btnLogout">Salir</button>
    `;
    document.getElementById("btnLogout").addEventListener("click", logout);
    document.getElementById("btnMisPedidos").addEventListener("click", abrirMisPedidos);
  } else {
    cuentaArea.innerHTML = `
      <button class="cuenta" id="btnCuenta" aria-label="Iniciar sesión">
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
        </svg>
      </button>
    `;
    document.getElementById("btnCuenta").addEventListener("click", abrirLogin);
  }
}

/* -------- 13. ABRIR / CERRAR LA VENTANA -------- */
function abrirLogin() {
  modalError.textContent = "";
  modalLogin.classList.add("abierto");
  modalFondo.classList.add("abierto");
}
function cerrarLogin() {
  modalLogin.classList.remove("abierto");
  modalFondo.classList.remove("abierto");
}
document.getElementById("btnCerrarModal").addEventListener("click", cerrarLogin);
modalFondo.addEventListener("click", function () {
  cerrarLogin();
  cerrarMisPedidos();
});

/* -------- 14. ALTERNAR ENTRE "INICIAR SESIÓN" Y "CREAR CUENTA" --------
   Ponemos el "escuchador" en el contenedor (#modalToggle), que nunca cambia.
   Esto se llama "delegación de eventos": aunque el enlace de adentro se
   vuelva a dibujar, el clic se sigue detectando. */
function actualizarModoModal() {
  document.getElementById("campoNombre").style.display = modoRegistro ? "block" : "none";
  document.getElementById("modalTitulo").textContent = modoRegistro ? "Crear cuenta" : "Iniciar sesión";
  document.getElementById("modalSubtitulo").textContent = modoRegistro
    ? "Regístrate en Ecocordi" : "Accede a tu cuenta Ecocordi";
  document.getElementById("modalEnviar").textContent = modoRegistro ? "Registrarme" : "Entrar";
  // Al registrarse pedimos mínimo 8 caracteres (el servidor también lo revisa).
  // Al iniciar sesión no, porque hay cuentas antiguas con claves más cortas.
  const campoClave = document.getElementById("loginClave");
  campoClave.minLength = modoRegistro ? 8 : 0;
  campoClave.placeholder = modoRegistro ? "Mínimo 8 caracteres" : "••••••••";
  // Le dice al gestor de contraseñas si debe sugerir una clave nueva o la guardada
  campoClave.autocomplete = modoRegistro ? "new-password" : "current-password";
  document.getElementById("modalToggle").innerHTML = modoRegistro
    ? '¿Ya tienes cuenta? <a href="#" id="linkToggle">Iniciar sesión</a>'
    : '¿No tienes cuenta? <a href="#" id="linkToggle">Crear cuenta</a>';
}

document.getElementById("modalToggle").addEventListener("click", function (e) {
  if (e.target.id !== "linkToggle") return;
  e.preventDefault();
  modoRegistro = !modoRegistro;
  modalError.textContent = "";
  actualizarModoModal();
});

/* -------- 15. ENVIAR EL FORMULARIO (login o registro) -------- */
document.getElementById("formLogin").addEventListener("submit", async function (e) {
  e.preventDefault();
  modalError.textContent = "";

  const correo = document.getElementById("loginCorreo").value;
  const clave  = document.getElementById("loginClave").value;
  const ruta   = modoRegistro ? "/api/register" : "/api/login";
  const cuerpo = { correo: correo, clave: clave };
  if (modoRegistro) cuerpo.nombre = document.getElementById("loginNombre").value;

  const respuesta = await fetch(ruta, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cuerpo),
  });
  const datos = await respuesta.json();

  if (!respuesta.ok) {
    modalError.textContent = datos.error || "Ocurrió un error.";
    return;
  }

  usuario = datos;
  renderCuenta();
  cerrarLogin();
  document.getElementById("formLogin").reset();
});

/* -------- 15b. MIS PEDIDOS --------
   Pide al servidor SOLO los pedidos del usuario con sesión iniciada
   (GET /api/pedidos) y los muestra con su estado. */
const modalPedidos = document.getElementById("modalPedidos");
const listaMisPedidos = document.getElementById("listaMisPedidos");

// Texto amigable para cada estado que guarda el servidor
const NOMBRES_ESTADO = {
  pendiente: "⏳ Pendiente",
  pagado:    "💳 Pagado",
  enviado:   "🚚 Enviado",
  entregado: "✅ Entregado",
  cancelado: "✖ Cancelado",
};

async function abrirMisPedidos() {
  listaMisPedidos.innerHTML = "<p class='mis-pedidos__vacio'>Cargando…</p>";
  modalPedidos.classList.add("abierto");
  modalFondo.classList.add("abierto");

  const respuesta = await fetch("/api/pedidos");
  if (!respuesta.ok) {
    listaMisPedidos.innerHTML = "<p class='mis-pedidos__vacio'>Inicia sesión para ver tus pedidos.</p>";
    return;
  }
  const pedidos = await respuesta.json();
  if (pedidos.length === 0) {
    listaMisPedidos.innerHTML = "<p class='mis-pedidos__vacio'>Aún no tienes pedidos. ¡Anímate con tu primera pintura! 🎨</p>";
    return;
  }
  listaMisPedidos.innerHTML = pedidos.map(function (p) {
    const items = p.items.map(function (it) {
      return `<li>${it.cantidad} × ${escaparHTML(it.nombre)}</li>`;
    }).join("");
    return `
      <div class="mi-pedido">
        <div class="mi-pedido__cabecera">
          <strong>Pedido N° ${p.id}</strong>
          <span class="estado estado--${escaparHTML(p.estado)}">${NOMBRES_ESTADO[p.estado] || escaparHTML(p.estado)}</span>
        </div>
        <p class="mi-pedido__fecha">🕐 ${escaparHTML(p.fecha)} · Total ${formatearPrecio(p.total)}</p>
        <ul class="mi-pedido__items">${items}</ul>
      </div>
    `;
  }).join("");
}

function cerrarMisPedidos() {
  modalPedidos.classList.remove("abierto");
  modalFondo.classList.remove("abierto");
}
document.getElementById("btnCerrarPedidos").addEventListener("click", cerrarMisPedidos);

/* -------- 16. CERRAR SESIÓN -------- */
async function logout() {
  await fetch("/api/logout", { method: "POST" });
  usuario = null;
  cerrarMisPedidos();
  renderCuenta();
}

/* ============================================================
   ANIMACIONES Y MENÚS
   ============================================================ */

/* -------- 17. APARICIÓN AL HACER SCROLL -------- */
const observador = new IntersectionObserver(function (entradas) {
  entradas.forEach(function (entrada) {
    if (entrada.isIntersecting) entrada.target.classList.add("visible");
  });
}, { threshold: 0.2 });
document.querySelectorAll(".revelar").forEach(function (el) { observador.observe(el); });

/* -------- 17b. PARALLAX SUAVE (acelerado por GPU) --------
   Movemos la capa de fondo con "transform", que el navegador dibuja en la
   tarjeta gráfica: fluido y sin tironeos. Usamos requestAnimationFrame para
   sincronizar el movimiento con el refresco de la pantalla. */
const fondos = document.querySelectorAll(".escena__fondo");
let esperandoFrame = false;

function moverParallax() {
  fondos.forEach(function (fondo) {
    const rect = fondo.parentElement.getBoundingClientRect();
    // Solo calculamos si la escena está visible (ahorra trabajo)
    if (rect.bottom > 0 && rect.top < window.innerHeight) {
      const desplazamiento = rect.top * -0.12; // se mueve más lento que el scroll
      fondo.style.transform = "translate3d(0," + desplazamiento + "px, 0)";
    }
  });
  esperandoFrame = false;
}

// Respetamos a quienes configuran "reducir movimiento" en su sistema
const prefiereMenosMovimiento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

if (!prefiereMenosMovimiento) {
  window.addEventListener("scroll", function () {
    if (!esperandoFrame) {
      window.requestAnimationFrame(moverParallax);
      esperandoFrame = true;
    }
  }, { passive: true });   // passive = no bloquea el scroll (más fluido)
  moverParallax();
}

/* -------- 18. ENLACES DEL MENÚ QUE FILTRAN EL CATÁLOGO -------- */
document.querySelectorAll(".submenu__link[data-superficie]").forEach(function (enlace) {
  enlace.addEventListener("click", function () {
    const superficie = enlace.dataset.superficie;
    const botonFiltro = document.querySelector(".filtro[data-superficie='" + superficie + "']");
    if (botonFiltro) botonFiltro.click();
  });
});

/* ============================================================
   19. ARRANQUE
   ============================================================ */
cargarCarrito();     // recupera el carrito guardado
cargarProductos();   // trae los productos de la base de datos
cargarUsuario();     // revisa si ya hay sesión iniciada
actualizarCarrito(); // dibuja el carrito
