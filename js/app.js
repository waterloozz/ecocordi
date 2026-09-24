/* ============================================================
   ECOCORDI - Lógica del sitio (frontend)
   Conectado a un backend real con base de datos.
   El navegador pide los datos al servidor con "fetch".
   Los avisos y confirmaciones vienen de js/ui.js (avisar / confirmar).
   ============================================================ */

/* -------- 1. ESTADO GLOBAL -------- */
let productos = [];   // se llenará con los productos que envía el servidor
let carrito = [];     // productos que el usuario agregó
let usuario = null;   // datos del usuario si inició sesión (o null)
let superficieActiva = "todas"; // filtro elegido en el catálogo

// Nombres visibles de cada superficie. También sirve como "lista blanca":
// solo estas palabras se usan para armar clases CSS (sup--madera, etc.).
const SUPERFICIES = {
  madera: "Madera",
  metal: "Metal",
  exterior: "Exterior",
  techo: "Techo",
  interior: "Interior",
};

/* -------- 2. REFERENCIAS A ELEMENTOS DEL HTML -------- */
const contenedorProductos = document.getElementById("productos");
// Los filtros solo existen en catalogo.html (en la home no están: son null)
const contenedorFiltros   = document.getElementById("filtros");
const filtroActivo        = document.getElementById("filtroActivo");
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

/* Clase de color de una superficie ("sup--madera"), solo si es conocida */
function claseSuperficie(superficie) {
  return SUPERFICIES[superficie] ? "sup--" + superficie : "";
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

/* -------- 5. MOSTRAR PRODUCTOS EN PANTALLA --------
   Lista editorial: foto grande, nombre, superficies y una línea con
   precio, stock y botón. */
function mostrarProductos(lista) {
  if (lista.length === 0) {
    contenedorProductos.innerHTML =
      "<p class='sin-resultados'>Todavía no hay pinturas para esta superficie.</p>";
    return;
  }

  contenedorProductos.innerHTML = lista.map(function (p) {
    // Stock: "Agotado" si no queda nada, "Quedan N" si quedan 5 o menos
    const agotado = p.stock <= 0;
    let avisoStock = "";
    if (agotado) {
      avisoStock = '<span class="producto__stock producto__stock--agotado">Agotado</span>';
    } else if (p.stock <= 5) {
      avisoStock = `<span class="producto__stock producto__stock--pocas">Quedan ${p.stock}</span>`;
    }

    const superficies = p.superficies.map(function (s) {
      return `<li class="${claseSuperficie(s)}">${escaparHTML(SUPERFICIES[s] || s)}</li>`;
    }).join("");

    return `
      <article class="producto ${claseSuperficie(p.superficies[0])}" data-id="${p.id}">
        <div class="producto__foto">
          <img src="${escaparHTML(p.imagen)}" alt="" width="800" height="600"
               loading="lazy" decoding="async" />
          <span class="imagen-referencial">Imagen referencial</span>
        </div>
        <div class="producto__cuerpo">
          <h3 class="producto__nombre">${escaparHTML(p.nombre)}</h3>
          <p class="producto__desc">${escaparHTML(p.descripcion)}</p>
          <ul class="producto__superficies" aria-label="Superficies">${superficies}</ul>
          <div class="producto__pie">
            <span class="producto__precio">${formatearPrecio(p.precio)}</span>
            <div class="producto__compra">
              ${avisoStock}
              <button type="button" class="boton boton--principal producto__boton" ${agotado ? "disabled" : ""}>
                ${agotado ? "Agotado" : "Agregar al carrito"}
              </button>
            </div>
          </div>
        </div>
      </article>
    `;
  }).join("");
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

/* -------- 6. FILTRO POR SUPERFICIE (funcionalidad estrella) --------
   Vive en catalogo.html. La superficie elegida se guarda en la dirección
   de la página (catalogo.html?superficie=madera), así:
     - la home puede enlazar directo a "pinturas para madera",
     - el enlace se puede compartir (por ejemplo, por WhatsApp),
     - el botón "atrás" del navegador vuelve al filtro anterior. */

/* Lee ?superficie=... de la dirección. Si no hay o no es válida: "todas" */
function superficieDeLaURL() {
  const superficie = new URLSearchParams(location.search).get("superficie");
  return SUPERFICIES[superficie] ? superficie : "todas";
}

/* Marca como activo el botón de la superficie elegida */
function marcarFiltro(superficie) {
  document.querySelectorAll(".filtro[data-superficie]").forEach(function (btn) {
    const activo = btn.dataset.superficie === superficie;
    btn.classList.toggle("filtro--activo", activo);
    btn.setAttribute("aria-pressed", activo ? "true" : "false");
  });
}

/* guardarEnHistorial = false cuando la elección viene del botón "atrás" */
function elegirSuperficie(superficie, guardarEnHistorial) {
  marcarFiltro(superficie);
  superficieActiva = superficie;
  mostrarCatalogo();
  if (guardarEnHistorial !== false) {
    const url = new URL(location.href);
    if (superficie === "todas") url.searchParams.delete("superficie");
    else url.searchParams.set("superficie", superficie);
    history.pushState(null, "", url);
  }
}

if (contenedorFiltros) {
  // Al abrir el catálogo, partimos con la superficie que venga en la dirección
  superficieActiva = superficieDeLaURL();
  marcarFiltro(superficieActiva);

  // Los botones tienen contenido adentro (miniatura y nombre),
  // así que usamos closest(".filtro") para encontrar el botón completo.
  contenedorFiltros.addEventListener("click", function (evento) {
    const boton = evento.target.closest(".filtro");
    if (!boton || boton.dataset.superficie === superficieActiva) return;
    elegirSuperficie(boton.dataset.superficie);
  });

  // Botón "atrás" / "adelante" del navegador
  window.addEventListener("popstate", function () {
    elegirSuperficie(superficieDeLaURL(), false);
  });

  // El "Ver todo" que aparece junto al filtro activo
  filtroActivo.addEventListener("click", function (evento) {
    if (evento.target.closest("[data-elegir-superficie]")) elegirSuperficie("todas");
  });
}

/* Muestra los productos según el filtro elegido. Se usa también cuando el
   catálogo se recarga (por ejemplo, después de comprar cambia el stock).
   En la home, #productos tiene data-limite="3": solo 3 destacados con stock. */
function mostrarCatalogo() {
  let lista = productos;
  if (superficieActiva !== "todas") {
    lista = productos.filter(function (p) {
      return p.superficies.includes(superficieActiva);
    });
  }
  const limite = Number(contenedorProductos.dataset.limite) || 0;
  if (limite) {
    lista = lista.filter(function (p) { return p.stock > 0; }).slice(0, limite);
  }
  mostrarProductos(lista);

  if (!filtroActivo) return; // en la home no hay texto de filtro
  // Texto que dice qué se está mostrando
  const cantidad = lista.length === 1 ? "1 producto" : lista.length + " productos";
  if (superficieActiva === "todas") {
    filtroActivo.textContent = cantidad;
  } else {
    filtroActivo.innerHTML = `Mostrando <strong>${escaparHTML(SUPERFICIES[superficieActiva] || superficieActiva)}</strong> · ${cantidad}
      <button type="button" class="catalogo__quitar" data-elegir-superficie="todas">Ver todo</button>`;
  }
}

/* -------- 7. CARRITO: agregar, cambiar cantidad, eliminar -------- */
function agregarAlCarrito(id) {
  const producto = productos.find(function (p) { return p.id === id; });
  const enCarrito = carrito.find(function (item) { return item.id === id; });

  if (enCarrito) {
    // No dejamos pedir más de lo que hay en bodega
    if (enCarrito.cantidad >= producto.stock) {
      avisar("Ya tienes en tu carrito todas las unidades disponibles de " +
             producto.nombre + " (" + producto.stock + ").", "info");
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
  let total = 0;
  let cantidadTotal = 0;

  if (carrito.length === 0) {
    carritoItems.innerHTML = `
      <div class="carrito__vacio">
        <svg class="icono" aria-hidden="true"><use href="#i-tarro"/></svg>
        <p>Tu carrito está vacío.</p>
        <p>Elige una superficie y agrega tus pinturas.</p>
      </div>`;
  } else {
    carritoItems.innerHTML = carrito.map(function (item) {
      total += item.precio * item.cantidad;
      cantidadTotal += item.cantidad;
      const nombre = escaparHTML(item.nombre);
      const alMaximo = item.cantidad >= item.stock;
      return `
        <div class="item ${claseSuperficie((item.superficies || [])[0])}" data-id="${item.id}">
          <img class="item__imagen" src="${escaparHTML(item.imagen)}" alt="" width="64" height="64" loading="lazy" />
          <div class="item__info">
            <p class="item__nombre">${nombre}</p>
            <p class="item__precio">${formatearPrecio(item.precio)} c/u</p>
            <div class="item__controles">
              <button type="button" class="item__btn" data-accion="restar" aria-label="Quitar una unidad de ${nombre}">−</button>
              <span class="item__cantidad" aria-label="Cantidad">${item.cantidad}</span>
              <button type="button" class="item__btn" data-accion="sumar" aria-label="Agregar una unidad de ${nombre}"
                      ${alMaximo ? "disabled" : ""}>+</button>
            </div>
            ${alMaximo ? `<p class="item__max">Máximo disponible: ${item.stock}</p>` : ""}
          </div>
          <button type="button" class="item__eliminar" data-accion="eliminar" aria-label="Eliminar ${nombre} del carrito">
            <svg class="icono" aria-hidden="true"><use href="#i-basura"/></svg>
          </button>
        </div>
      `;
    }).join("");
  }

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

/* -------- 9b. BLOQUEAR EL FONDO --------
   Cuando hay una ventana o el carrito abierto, marcamos el resto de la página
   como "inert": el teclado (Tab) y los lectores de pantalla se quedan dentro
   de la ventana, como en una ventana real. */
function bloquearFondo(bloquear) {
  document.querySelectorAll(".saltar, .cabecera, main, .pie, .whatsapp").forEach(function (el) {
    el.inert = bloquear;
  });
}

/* -------- 10. ABRIR / CERRAR PANELES --------
   Recordamos qué botón abrió cada panel para devolverle el foco al cerrar
   (importante para quien navega con teclado). */
let focoAnterior = null;

function abrirCarrito() {
  focoAnterior = document.activeElement;
  panelCarrito.classList.add("abierto");
  fondoCarrito.classList.add("abierto");
  bloquearFondo(true);
  document.getElementById("btnCerrarCarrito").focus();
}
function cerrarCarrito() {
  if (!panelCarrito.classList.contains("abierto")) return;
  panelCarrito.classList.remove("abierto");
  fondoCarrito.classList.remove("abierto");
  bloquearFondo(false);
  if (focoAnterior) focoAnterior.focus();
}
document.getElementById("btnAbrirCarrito").addEventListener("click", abrirCarrito);
document.getElementById("btnCerrarCarrito").addEventListener("click", cerrarCarrito);
fondoCarrito.addEventListener("click", cerrarCarrito);

/* -------- 11. FINALIZAR COMPRA (guarda el pedido en la base de datos) -------- */
const botonPagar = document.getElementById("btnPagar");
botonPagar.addEventListener("click", async function () {
  if (carrito.length === 0) {
    avisar("Tu carrito está vacío. ¡Agrega algunas pinturas primero!", "info");
    return;
  }

  // Antes de enviar: aceptar los Términos y la Política de cambios y devoluciones
  const aceptaPedido = document.getElementById("aceptaPedido");
  if (!aceptaPedido.checked) {
    avisar("Para enviar tu pedido, marca la casilla de aceptación de los Términos y la Política de cambios y devoluciones.", "error");
    aceptaPedido.focus();
    return;
  }

  // Enviamos solo id y cantidad; el servidor calcula el total con precios reales
  const items = carrito.map(function (i) {
    return { id: i.id, cantidad: i.cantidad };
  });

  botonPagar.disabled = true; // evita comprar dos veces con un doble clic
  try {
    const respuesta = await fetch("/api/pedidos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items: items, acepta_terminos: true }),
    });

    if (respuesta.status === 401) {
      avisar("Inicia sesión para finalizar tu compra.", "info");
      cerrarCarrito();
      abrirLogin();
      return;
    }

    const datos = await respuesta.json();
    if (respuesta.status === 409) {
      // Alguien compró antes que tú: traemos el stock real y ajustamos el carrito
      avisar(datos.error + "\nAjustamos tu carrito al stock disponible.", "error");
      await cargarProductos();
      return;
    }
    if (!respuesta.ok) {
      avisar("No se pudo completar la compra: " + (datos.error || "error desconocido"), "error");
      return;
    }
    avisar("¡Recibimos tu pedido!\n" +
           "Pedido N° " + datos.pedido_id + " · Total " + formatearPrecio(datos.total) + "\n" +
           "Te contactaremos para coordinar el pago y la entrega. Puedes seguirlo en \"Mis pedidos\".", "exito", 9000);
    aceptaPedido.checked = false;

    carrito = [];
    actualizarCarrito();
    cerrarCarrito();
    cargarProductos(); // el stock cambió: refrescamos "Quedan N" / "Agotado"
  } finally {
    botonPagar.disabled = false;
  }
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
      <button type="button" class="cuenta__boton" id="btnMisPedidos">Mis pedidos</button>
      ${linkAdmin}
      <button type="button" class="cuenta__salir" id="btnLogout">Salir</button>
    `;
    document.getElementById("btnLogout").addEventListener("click", logout);
    document.getElementById("btnMisPedidos").addEventListener("click", abrirMisPedidos);
  } else {
    cuentaArea.innerHTML = `
      <button type="button" class="cuenta__entrar" id="btnCuenta">
        <svg class="icono" aria-hidden="true"><use href="#i-usuario"/></svg>Entrar
      </button>
    `;
    document.getElementById("btnCuenta").addEventListener("click", abrirLogin);
  }
}

/* -------- 13. ABRIR / CERRAR LA VENTANA DE LOGIN -------- */
function abrirLogin() {
  focoAnterior = document.activeElement;
  modalError.textContent = "";
  modalLogin.classList.add("abierto");
  modalFondo.classList.add("abierto");
  bloquearFondo(true);
  // Foco en el primer campo para escribir de inmediato
  document.getElementById(modoRegistro ? "loginNombre" : "loginCorreo").focus();
}
function cerrarLogin() {
  if (!modalLogin.classList.contains("abierto")) return;
  modalLogin.classList.remove("abierto");
  modalFondo.classList.remove("abierto");
  bloquearFondo(false);
  if (focoAnterior && document.body.contains(focoAnterior)) focoAnterior.focus();
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
  document.getElementById("campoConsentimiento").style.display = modoRegistro ? "block" : "none";
  document.getElementById("aceptaTerminos").required = modoRegistro;
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
  document.getElementById(modoRegistro ? "loginNombre" : "loginCorreo").focus();
});

/* -------- 15. ENVIAR EL FORMULARIO (login o registro) -------- */
document.getElementById("formLogin").addEventListener("submit", async function (e) {
  e.preventDefault();
  modalError.textContent = "";

  const correo = document.getElementById("loginCorreo").value;
  const clave  = document.getElementById("loginClave").value;
  const ruta   = modoRegistro ? "/api/register" : "/api/login";
  const cuerpo = { correo: correo, clave: clave };
  if (modoRegistro) {
    cuerpo.nombre = document.getElementById("loginNombre").value;
    cuerpo.acepta_terminos = document.getElementById("aceptaTerminos").checked;
  }

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
  const primerNombre = usuario.nombre.split(" ")[0];
  avisar(modoRegistro
    ? "Cuenta creada. ¡Te damos la bienvenida, " + primerNombre + "!"
    : "Sesión iniciada. Hola, " + primerNombre + ".", "exito");
});

/* -------- 15a. INICIAR SESIÓN CON GOOGLE --------
   El botón lleva al servidor (/api/auth/google/iniciar), que manda a Google.
   Al terminar, Google vuelve al servidor y este nos devuelve a esta misma
   página con ?google=ok | nuevo | necesita_aceptar | cancelado | admin | error.
   No se carga ningún script de Google en la página (la CSP lo bloquearía). */
const bloqueGoogle = document.getElementById("bloqueGoogle");

// El botón solo aparece si el servidor tiene configuradas las credenciales
async function mostrarBotonGoogle() {
  try {
    const respuesta = await fetch("/api/auth/google/disponible");
    const datos = await respuesta.json();
    if (datos.disponible) bloqueGoogle.style.display = "block";
  } catch (error) { /* sin Google: queda solo el correo y contraseña */ }
}

document.getElementById("btnGoogle").addEventListener("click", function () {
  const casilla = document.getElementById("aceptaTerminos");
  // Crear una cuenta (también con Google) exige aceptar los términos
  if (modoRegistro && !casilla.checked) {
    modalError.textContent = "Para crear tu cuenta, marca primero la casilla de aceptación.";
    casilla.focus();
    return;
  }
  const volver = location.pathname.replace(/^\//, "") + location.search;
  location.href = "/api/auth/google/iniciar?" + new URLSearchParams({
    acepta: modoRegistro && casilla.checked ? "1" : "0",
    volver: volver,
  });
});

// Mensajes al volver de Google
function revisarVueltaDeGoogle() {
  const url = new URL(location.href);
  const resultado = url.searchParams.get("google");
  if (!resultado) return;
  url.searchParams.delete("google"); // limpiamos la dirección
  history.replaceState(null, "", url);

  const mensajes = {
    ok: ["Sesión iniciada con Google.", "exito"],
    nuevo: ["Cuenta creada con Google. ¡Te damos la bienvenida!", "exito"],
    cancelado: ["Cancelaste el inicio de sesión con Google.", "info"],
    admin: ["La cuenta de administrador entra solo con correo y contraseña.", "error"],
    no_configurado: ["El inicio de sesión con Google no está disponible por ahora.", "error"],
    error: ["No se pudo iniciar sesión con Google. Inténtalo de nuevo.", "error"],
  };
  if (resultado === "necesita_aceptar") {
    // Cuenta nueva sin aceptar términos: abrimos "Crear cuenta" para que acepte
    modoRegistro = true;
    actualizarModoModal();
    abrirLogin();
    modalError.textContent = "Para crear tu cuenta con Google, marca la casilla de aceptación y vuelve a presionar «Continuar con Google».";
    document.getElementById("aceptaTerminos").focus();
    return;
  }
  const mensaje = mensajes[resultado] || mensajes.error;
  avisar(mensaje[0], mensaje[1]);
}

/* -------- 15b. MIS PEDIDOS --------
   Pide al servidor SOLO los pedidos del usuario con sesión iniciada
   (GET /api/pedidos) y los muestra con su estado. */
const modalPedidos = document.getElementById("modalPedidos");
const listaMisPedidos = document.getElementById("listaMisPedidos");

// Texto amigable para cada estado que guarda el servidor
const NOMBRES_ESTADO = {
  pendiente: "Pendiente",
  pagado:    "Pagado",
  enviado:   "Enviado",
  entregado: "Entregado",
  cancelado: "Cancelado",
};

async function abrirMisPedidos() {
  focoAnterior = document.activeElement;
  listaMisPedidos.innerHTML = "<p class='mis-pedidos__vacio'>Cargando…</p>";
  modalPedidos.classList.add("abierto");
  modalFondo.classList.add("abierto");
  bloquearFondo(true);
  document.getElementById("btnCerrarPedidos").focus();

  const respuesta = await fetch("/api/pedidos");
  if (!respuesta.ok) {
    listaMisPedidos.innerHTML = "<p class='mis-pedidos__vacio'>Inicia sesión para ver tus pedidos.</p>";
    return;
  }
  const pedidos = await respuesta.json();
  if (pedidos.length === 0) {
    listaMisPedidos.innerHTML = "<p class='mis-pedidos__vacio'>Aún no tienes pedidos. ¡Anímate con tu primera pintura!</p>";
    return;
  }
  listaMisPedidos.innerHTML = pedidos.map(function (p) {
    const items = p.items.map(function (it) {
      return `<li>${it.cantidad} × ${escaparHTML(it.nombre)}</li>`;
    }).join("");
    // La clase de color solo se arma con estados conocidos
    const estado = NOMBRES_ESTADO[p.estado] ? p.estado : "pendiente";
    return `
      <div class="mi-pedido">
        <div class="mi-pedido__cabecera">
          <strong>Pedido N° ${p.id}</strong>
          <span class="estado estado--${estado}">${NOMBRES_ESTADO[p.estado] || escaparHTML(p.estado)}</span>
        </div>
        <p class="mi-pedido__fecha">${escaparHTML(p.fecha)} · Total ${formatearPrecio(p.total)}</p>
        <ul class="mi-pedido__items">${items}</ul>
      </div>
    `;
  }).join("");
}

function cerrarMisPedidos() {
  if (!modalPedidos.classList.contains("abierto")) return;
  modalPedidos.classList.remove("abierto");
  modalFondo.classList.remove("abierto");
  bloquearFondo(false);
  if (focoAnterior && document.body.contains(focoAnterior)) focoAnterior.focus();
}
document.getElementById("btnCerrarPedidos").addEventListener("click", cerrarMisPedidos);

/* -------- 15c. ELIMINAR MI CUENTA (derecho de supresión) -------- */
document.getElementById("btnEliminarCuenta").addEventListener("click", async function () {
  const seguro = await confirmar({
    titulo: "Eliminar mi cuenta",
    mensaje: "Borraremos tu nombre, tu correo y tu contraseña. Tus pedidos quedan registrados sin tus datos. Esta acción no se puede deshacer.",
    textoConfirmar: "Eliminar mi cuenta",
    peligro: true,
  });
  if (!seguro) return;
  const respuesta = await fetch("/api/cuenta/eliminar", { method: "POST" });
  const datos = await respuesta.json();
  if (!respuesta.ok) {
    avisar("No se pudo eliminar la cuenta: " + (datos.error || "error desconocido"), "error");
    return;
  }
  usuario = null;
  cerrarMisPedidos();
  renderCuenta();
  avisar("Tu cuenta y tus datos personales fueron eliminados.", "exito");
});

/* -------- 16. CERRAR SESIÓN -------- */
async function logout() {
  await fetch("/api/logout", { method: "POST" });
  usuario = null;
  cerrarMisPedidos();
  renderCuenta();
  avisar("Sesión cerrada.", "info");
}

/* ============================================================
   MENÚ, TECLADO Y ESPACIOS PREPARADOS
   ============================================================ */

/* -------- 17. MENÚ EN CELULARES -------- */
const botonMenu = document.getElementById("btnMenu");
const menu = document.getElementById("menu");

function cerrarMenu() {
  menu.classList.remove("menu--abierto");
  botonMenu.setAttribute("aria-expanded", "false");
  botonMenu.setAttribute("aria-label", "Abrir menú");
}
botonMenu.addEventListener("click", function () {
  const abierto = menu.classList.toggle("menu--abierto");
  botonMenu.setAttribute("aria-expanded", abierto ? "true" : "false");
  botonMenu.setAttribute("aria-label", abierto ? "Cerrar menú" : "Abrir menú");
});
// Al elegir una sección, el menú se cierra
menu.addEventListener("click", function (evento) {
  if (evento.target.closest(".menu__link")) cerrarMenu();
});

/* -------- 18. TECLA ESC: cierra lo que esté abierto -------- */
document.addEventListener("keydown", function (evento) {
  if (evento.key !== "Escape") return;
  cerrarLogin();
  cerrarMisPedidos();
  cerrarCarrito();
  cerrarMenu();
});

/* -------- 19. BOTÓN DE WHATSAPP (espacio preparado) --------
   Cuando tengan el número, reemplazar esto por un enlace a
   https://wa.me/569XXXXXXXX y borrar este aviso. */
document.getElementById("btnWhatsapp").addEventListener("click", function () {
  avisar("Muy pronto podrás escribirnos por WhatsApp. Mientras tanto: pinturas@ecocordi.cl", "info");
});

/* ============================================================
   20. ARRANQUE
   ============================================================ */
cargarCarrito();     // recupera el carrito guardado
cargarProductos();   // trae los productos de la base de datos
cargarUsuario();     // revisa si ya hay sesión iniciada
mostrarBotonGoogle(); // muestra "Continuar con Google" si está disponible
revisarVueltaDeGoogle(); // mensajes al volver de Google
actualizarCarrito(); // dibuja el carrito
