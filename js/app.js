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
  return "$" + (Number(valor) || 0).toLocaleString("es-CL");
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
    actualizarPinturasCalculadora();
    sugerirSuperficieCalculadora(superficieActiva);
  } catch (error) {
    if (contenedorProductos) {
      contenedorProductos.innerHTML =
        "<p class='sin-resultados'>No se pudieron cargar los productos. ¿Está encendido el servidor?</p>";
    }
  }
}

/* -------- 4b. FORMATOS DE VENTA --------
   Cada producto se vende en uno o más formatos (1/4 galón, galón, tineta...),
   y cada formato tiene su propio precio y stock. El carrito guarda FORMATOS. */

// Formato que la persona eligió en cada tarjeta: { id_producto: id_formato }.
// Así, si el catálogo se vuelve a dibujar (filtro, búsqueda), no se pierde.
const formatoElegido = {};

/* Formato que muestra la tarjeta: el elegido; si no, el primero con stock (o el primero) */
function formatoInicial(producto) {
  const elegido = producto.formatos.find(function (f) { return f.id === formatoElegido[producto.id]; });
  return elegido || producto.formatos.find(function (f) { return f.stock > 0; }) || producto.formatos[0] || null;
}

/* Busca un formato por su id en el catálogo cargado: { producto, formato } */
function buscarFormato(formatoId) {
  for (const producto of productos) {
    const formato = producto.formatos.find(function (f) { return f.id === formatoId; });
    if (formato) return { producto: producto, formato: formato };
  }
  return null;
}

/* Lo que guardamos en el carrito por cada formato */
function itemDeCarrito(producto, formato, cantidad) {
  return {
    formato_id: formato.id,
    producto_id: producto.id,
    nombre: producto.nombre,
    formato: formato.nombre,
    precio: formato.precio,
    stock: formato.stock,
    imagen: producto.imagen,
    superficies: producto.superficies,
    cantidad: cantidad,
  };
}

/* Litros con coma decimal chilena: 3,785 L */
function formatearLitros(litros) {
  return litros.toLocaleString("es-CL", { maximumFractionDigits: 3 }) + " L";
}

/* -------- 5. MOSTRAR PRODUCTOS EN PANTALLA --------
   Lista editorial: foto grande, nombre, superficies, formatos y una línea
   con precio, stock y botón. */

/* Precio, stock y botón de UN formato. Se vuelve a dibujar al cambiar de formato. */
function htmlCompra(formato) {
  // Stock del formato: "Agotado" si no queda nada, "Quedan N" si quedan 5 o menos
  const stock = formato ? formato.stock : 0;
  const agotado = stock <= 0;
  let avisoStock = "";
  if (agotado) {
    avisoStock = '<span class="producto__stock producto__stock--agotado">Agotado</span>';
  } else if (stock <= 5) {
    avisoStock = `<span class="producto__stock producto__stock--pocas">Quedan ${stock}</span>`;
  }
  return `
    <span class="producto__precio">
      ${formato ? formatearPrecio(formato.precio) : ""}
      <span class="producto__formato">${formato ? escaparHTML(formato.nombre) + " · " + formatearLitros(formato.litros) : "No disponible"}</span>
    </span>
    <div class="producto__compra">
      ${avisoStock}
      <button type="button" class="boton boton--principal producto__boton"
              data-formato-id="${formato ? formato.id : ""}" ${agotado ? "disabled" : ""}>
        ${agotado ? "Agotado" : "Agregar al carrito"}
      </button>
    </div>`;
}

/* Botones para elegir el formato (solo si hay más de uno) */
function htmlFormatos(producto, elegido) {
  if (producto.formatos.length < 2) return "";
  const opciones = producto.formatos.map(function (f) {
    return `
      <label class="formato-chip ${f.stock <= 0 ? "formato-chip--agotado" : ""}">
        <input type="radio" name="formato-${producto.id}" value="${f.id}" ${f.id === elegido.id ? "checked" : ""} />
        <span>${escaparHTML(f.nombre)}</span>
      </label>`;
  }).join("");
  return `
    <fieldset class="producto__formatos">
      <legend class="solo-lector">Formato de ${escaparHTML(producto.nombre)}</legend>
      ${opciones}
    </fieldset>`;
}

function mostrarProductos(lista, mensajeVacio) {
  if (lista.length === 0) {
    contenedorProductos.innerHTML = `<div class="sin-resultados">${mensajeVacio ||
      "<p>Todavía no hay pinturas para esta superficie.</p>"}</div>`;
    return;
  }

  contenedorProductos.innerHTML = lista.map(function (p) {
    const formato = formatoInicial(p);
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
          ${formato ? htmlFormatos(p, formato) : ""}
          <div class="producto__pie">${htmlCompra(formato)}</div>
        </div>
      </article>
    `;
  }).join("");
}

/* -------- 5b. CLIC EN "AGREGAR AL CARRITO" (delegación de eventos) --------
   En vez de poner onclick="..." en cada botón (la CSP del servidor lo
   bloquea), ponemos UN solo "escuchador" en el contenedor de productos.
   Cuando haces clic en cualquier parte de adentro, revisamos si fue en un
   botón, y leemos el formato desde su atributo data-formato-id. */
// Las páginas del asistente y del visualizador no tienen lista de productos
if (contenedorProductos) {
  contenedorProductos.addEventListener("click", function (evento) {
    const boton = evento.target.closest(".producto__boton");
    if (!boton) return; // el clic no fue en el botón
    agregarAlCarrito(Number(boton.dataset.formatoId));
  });

  /* Al elegir otro formato, cambian el precio, el stock y el botón de esa tarjeta */
  contenedorProductos.addEventListener("change", function (evento) {
    if (!evento.target.matches(".producto__formatos input")) return;
    const tarjeta = evento.target.closest(".producto");
    const encontrado = buscarFormato(Number(evento.target.value));
    if (!encontrado) return;
    formatoElegido[encontrado.producto.id] = encontrado.formato.id;
    tarjeta.querySelector(".producto__pie").innerHTML = htmlCompra(encontrado.formato);
  });
}

/* -------- 6. FILTRO POR SUPERFICIE Y BUSCADOR (funcionalidad estrella) --------
   Viven en catalogo.html. La superficie y el texto buscado se guardan en la
   dirección de la página (catalogo.html?superficie=madera&q=rejas), así:
     - la home puede enlazar directo a "pinturas para madera",
     - el enlace se puede compartir (por ejemplo, por WhatsApp),
     - el botón "atrás" del navegador vuelve al filtro anterior. */
const campoBusqueda = document.getElementById("buscarTexto");
let busqueda = ""; // texto del buscador

/* Lee ?superficie=... de la dirección. Si no hay o no es válida: "todas" */
function superficieDeLaURL() {
  const superficie = new URLSearchParams(location.search).get("superficie");
  return SUPERFICIES[superficie] ? superficie : "todas";
}

function busquedaDeLaURL() {
  return (new URLSearchParams(location.search).get("q") || "").trim().slice(0, 60);
}

/* Para buscar sin importar mayúsculas ni tildes: "Protección" → "proteccion" */
function normalizar(texto) {
  return String(texto || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

/* ¿El producto tiene TODAS las palabras buscadas (en su nombre o descripción)? */
function coincideBusqueda(producto, texto) {
  const palabras = normalizar(texto).split(/\s+/).filter(Boolean);
  const donde = normalizar(producto.nombre + " " + producto.descripcion);
  return palabras.every(function (palabra) { return donde.includes(palabra); });
}

/* Escribe la superficie y la búsqueda en la dirección de la página.
   nuevaEntrada = true crea un paso en el historial (botón "atrás");
   al escribir en el buscador solo se reemplaza, para no llenar el historial. */
function guardarEnURL(nuevaEntrada) {
  // Siempre en el mismo orden (superficie y luego búsqueda): así un mismo
  // filtro produce siempre el mismo enlace
  const url = new URL(location.href);
  url.searchParams.delete("superficie");
  url.searchParams.delete("q");
  if (superficieActiva !== "todas") url.searchParams.set("superficie", superficieActiva);
  if (busqueda) url.searchParams.set("q", busqueda);
  if (url.href === location.href) return;
  if (nuevaEntrada) history.pushState(null, "", url);
  else history.replaceState(null, "", url);
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
  if (guardarEnHistorial !== false) guardarEnURL(true);
  sugerirSuperficieCalculadora(superficie);
}

function elegirBusqueda(texto, guardarEnHistorial) {
  busqueda = texto.trim().slice(0, 60);
  if (campoBusqueda && campoBusqueda.value.trim() !== busqueda) campoBusqueda.value = busqueda;
  mostrarCatalogo();
  if (guardarEnHistorial !== false) guardarEnURL(false);
}

if (contenedorFiltros) {
  // Al abrir el catálogo, partimos con lo que venga en la dirección
  superficieActiva = superficieDeLaURL();
  busqueda = busquedaDeLaURL();
  campoBusqueda.value = busqueda;
  marcarFiltro(superficieActiva);

  // Los botones tienen contenido adentro (miniatura y nombre),
  // así que usamos closest(".filtro") para encontrar el botón completo.
  contenedorFiltros.addEventListener("click", function (evento) {
    const boton = evento.target.closest(".filtro");
    if (!boton || boton.dataset.superficie === superficieActiva) return;
    elegirSuperficie(boton.dataset.superficie);
  });

  // Buscador: filtra mientras se escribe (con una pequeña pausa para no
  // redibujar en cada letra). Enter no recarga la página: solo cierra el teclado.
  let pausa = null;
  campoBusqueda.addEventListener("input", function () {
    clearTimeout(pausa);
    pausa = setTimeout(function () { elegirBusqueda(campoBusqueda.value); }, 200);
  });
  document.getElementById("buscador").addEventListener("submit", function (evento) {
    evento.preventDefault();
    clearTimeout(pausa);
    elegirBusqueda(campoBusqueda.value);
    campoBusqueda.blur();
  });

  // Botón "atrás" / "adelante" del navegador
  window.addEventListener("popstate", function () {
    busqueda = busquedaDeLaURL();
    campoBusqueda.value = busqueda;
    elegirSuperficie(superficieDeLaURL(), false);
  });

  // "Ver todo" y "Borrar búsqueda", junto al texto que dice qué se muestra
  // (también dentro del mensaje "sin resultados")
  document.getElementById("catalogo").addEventListener("click", function (evento) {
    if (evento.target.closest("[data-elegir-superficie]")) elegirSuperficie("todas");
    if (evento.target.closest("[data-borrar-busqueda]")) {
      elegirBusqueda("");
      campoBusqueda.focus();
    }
  });
}

/* Muestra los productos según el filtro y la búsqueda. Se usa también cuando
   el catálogo se recarga (por ejemplo, después de comprar cambia el stock).
   En la home, #productos tiene data-limite="3": solo 3 destacados con stock. */
function mostrarCatalogo() {
  if (!contenedorProductos) return;
  let lista = productos;
  if (superficieActiva !== "todas") {
    lista = lista.filter(function (p) {
      return p.superficies.includes(superficieActiva);
    });
  }
  if (busqueda) {
    lista = lista.filter(function (p) { return coincideBusqueda(p, busqueda); });
  }
  const limite = Number(contenedorProductos.dataset.limite) || 0;
  if (limite) {
    lista = lista.filter(function (p) { return p.stock > 0; }).slice(0, limite);
  }

  const nombreSuperficie = escaparHTML(SUPERFICIES[superficieActiva] || superficieActiva);
  const botonVerTodo = '<button type="button" class="catalogo__quitar" data-elegir-superficie="todas">Ver todas las superficies</button>';
  const botonBorrar = '<button type="button" class="catalogo__quitar" data-borrar-busqueda>Borrar búsqueda</button>';
  let mensajeVacio = "";
  if (busqueda) {
    mensajeVacio = `<p>No encontramos pinturas para «${escaparHTML(busqueda)}»` +
      (superficieActiva !== "todas" ? ` en ${nombreSuperficie}` : "") + ".</p>" +
      `<p class="sin-resultados__acciones">${botonBorrar}${superficieActiva !== "todas" ? botonVerTodo : ""}</p>`;
  }
  mostrarProductos(lista, mensajeVacio);

  if (!filtroActivo) return; // en la home no hay texto de filtro
  // Texto que dice qué se está mostrando
  const cantidad = lista.length === 1 ? "1 producto" : lista.length + " productos";
  const partes = [];
  if (superficieActiva !== "todas") partes.push(`<strong>${nombreSuperficie}</strong>`);
  if (busqueda) partes.push(`«${escaparHTML(busqueda)}»`);
  if (partes.length === 0) {
    filtroActivo.textContent = cantidad;
  } else {
    filtroActivo.innerHTML = `Mostrando ${partes.join(" · ")} · ${cantidad}
      ${busqueda ? botonBorrar : ""}${superficieActiva !== "todas" ? '<button type="button" class="catalogo__quitar" data-elegir-superficie="todas">Ver todo</button>' : ""}`;
  }
}

/* -------- 7. CARRITO: agregar, cambiar cantidad, eliminar -------- */
/* abrir = false: agrega sin abrir el panel (la calculadora agrega varios y lo abre al final) */
function agregarAlCarrito(formatoId, cantidad, abrir) {
  const encontrado = buscarFormato(formatoId);
  if (!encontrado) return;
  const producto = encontrado.producto;
  const formato = encontrado.formato;
  const sumar = cantidad || 1;
  const enCarrito = carrito.find(function (item) { return item.formato_id === formatoId; });
  const yaTengo = enCarrito ? enCarrito.cantidad : 0;

  // No dejamos pedir más de lo que hay en bodega
  if (yaTengo + sumar > formato.stock) {
    avisar("Ya tienes en tu carrito todas las unidades disponibles de " +
           producto.nombre + " (" + formato.nombre + "): " + formato.stock + ".", "info");
    if (yaTengo >= formato.stock) return;
  }
  const nuevaCantidad = Math.min(yaTengo + sumar, formato.stock);
  if (enCarrito) {
    enCarrito.cantidad = nuevaCantidad;
  } else {
    carrito.push(itemDeCarrito(producto, formato, nuevaCantidad));
  }
  actualizarCarrito();
  if (abrir !== false) abrirCarrito();
}

function cambiarCantidad(id, cambio) {
  const item = carrito.find(function (i) { return i.formato_id === id; });
  if (cambio > 0 && item.cantidad >= item.stock) return; // sin más stock
  item.cantidad += cambio;
  if (item.cantidad <= 0) {
    eliminarDelCarrito(id);
  } else {
    actualizarCarrito();
  }
}

function eliminarDelCarrito(id) {
  carrito = carrito.filter(function (item) { return item.formato_id !== id; });
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
      total += (Number(item.precio) || 0) * (Number(item.cantidad) || 0);
      cantidadTotal += Number(item.cantidad) || 0;
      const nombre = escaparHTML(item.nombre);
      const alMaximo = item.cantidad >= item.stock;
      return `
        <div class="item ${claseSuperficie((item.superficies || [])[0])}" data-id="${item.formato_id}">
          <img class="item__imagen" src="${escaparHTML(item.imagen)}" alt="" width="64" height="64" loading="lazy" />
          <div class="item__info">
            <p class="item__nombre">${nombre}</p>
            <p class="item__precio">${item.formato ? escaparHTML(item.formato) + " · " : ""}${formatearPrecio(item.precio)} c/u</p>
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
   y la fila del carrito guarda el id del FORMATO en data-id. */
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
  try {
    localStorage.setItem("carrito_ecocordi", JSON.stringify(carrito));
  } catch (error) { /* modo privado o sin permiso: el carrito vive solo en esta página */ }
}
function cargarCarrito() {
  try {
    const guardado = JSON.parse(localStorage.getItem("carrito_ecocordi") || "[]");
    if (Array.isArray(guardado)) carrito = guardado;
  } catch (error) {
    carrito = []; // guardado dañado o navegador sin localStorage: carrito vacío
  }
}

/* El carrito guardado puede estar desactualizado: quizás el admin borró un
   formato, cambió su precio o se agotó. Cuando llega el catálogo real,
   quitamos lo que ya no existe o está agotado, copiamos nombre, precio,
   imagen y stock actuales, y bajamos la cantidad si supera el stock.
   Los carritos de la versión anterior guardaban el id del PRODUCTO: esos
   pasan al formato que muestra la tarjeta de ese producto. */
function sincronizarCarrito() {
  const nuevo = [];
  carrito.forEach(function (item) {
    let encontrado = buscarFormato(item.formato_id);
    if (!encontrado && item.formato_id === undefined) {
      const producto = productos.find(function (p) { return p.id === item.id; });
      const formato = producto && formatoInicial(producto);
      if (formato) encontrado = { producto: producto, formato: formato };
    }
    if (!encontrado || encontrado.formato.stock <= 0) return;
    const cantidad = Math.min(Number(item.cantidad) || 1, encontrado.formato.stock);
    const repetido = nuevo.find(function (i) { return i.formato_id === encontrado.formato.id; });
    if (repetido) {
      repetido.cantidad = Math.min(repetido.cantidad + cantidad, encontrado.formato.stock);
    } else {
      nuevo.push(itemDeCarrito(encontrado.producto, encontrado.formato, cantidad));
    }
  });
  carrito = nuevo;
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

/* -------- 11. CONTINUAR CON EL PEDIDO --------
   El pedido se completa en pedido.html: datos de contacto, entrega (retiro o
   despacho), boleta o factura, y un resumen final antes de enviarlo.
   El carrito "viaja" a esa página guardado en el navegador (localStorage). */
document.getElementById("btnPagar").addEventListener("click", function () {
  if (carrito.length === 0) {
    avisar("Tu carrito está vacío. ¡Agrega algunas pinturas primero!", "info");
    return;
  }
  guardarCarrito();
  location.href = "pedido.html";
});

/* Desde pedido.html, "Inicia sesión" trae aquí con ?entrar=pedido: abrimos
   la ventana de inicio de sesión y, al entrar, volvemos al pedido. */
let volverAlPedido = false;
function revisarEntrarParaPedido() {
  const url = new URL(location.href);
  if (url.searchParams.get("entrar") !== "pedido") return;
  url.searchParams.delete("entrar");
  history.replaceState(null, "", url);
  volverAlPedido = true;
  abrirLogin();
}

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
  if (volverAlPedido) {
    location.href = "pedido.html";
    return;
  }
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
  // Si venía del pedido, Google nos devuelve directo a pedido.html
  const volver = volverAlPedido ? "pedido.html" : location.pathname.replace(/^\//, "") + location.search;
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
      const formato = it.formato ? ` <span class="mi-pedido__formato">(${escaparHTML(it.formato)})</span>` : "";
      return `<li>${it.cantidad} × ${escaparHTML(it.nombre)}${formato}</li>`;
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
        ${textoEntrega(p) ? `<p class="mi-pedido__entrega">${textoEntrega(p)}</p>` : ""}
      </div>
    `;
  }).join("");
}

/* "Retiro en sucursal Talca" o "Despacho a Comuna, Región (costo)". Ya escapado. */
function textoEntrega(p) {
  if (p.entrega === "retiro") return "Retiro en sucursal " + escaparHTML(p.sucursal_nombre || p.sucursal);
  if (p.entrega === "despacho") {
    const costo = p.costo_despacho === null ? "a coordinar" : formatearPrecio(p.costo_despacho);
    return `Despacho a ${escaparHTML(p.comuna || "")}, ${escaparHTML(p.region_nombre || "")} (${costo})`;
  }
  return "";
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

/* -------- 19. CONFIGURACIÓN DE LA TIENDA: WHATSAPP E IVA --------
   Estos datos NO están en el código: los entrega el servidor (/api/config),
   que los lee de la configuración (.env).
   - WhatsApp: si no hay número (WHATSAPP_NUMERO), el botón queda oculto.
   - IVA: junto a los precios dice si lo incluyen (PRECIOS_INCLUYEN_IVA). */
async function cargarConfiguracion() {
  let config;
  try {
    config = await (await fetch("/api/config")).json();
  } catch (error) {
    return; // sin configuración: WhatsApp sigue oculto y no se muestra la nota del IVA
  }
  document.querySelectorAll("[data-nota-iva]").forEach(function (nota) {
    nota.textContent = config.precios_incluyen_iva ? ", IVA incluido" : ", más IVA";
  });
  const boton = document.getElementById("btnWhatsapp");
  if (!boton || !config.whatsapp || !/^\d{8,15}$/.test(config.whatsapp)) return;
  boton.href = "https://wa.me/" + config.whatsapp + "?" + new URLSearchParams({
    text: "Hola, Pinturas Ecocordi. Tengo una consulta:",
  });
  boton.classList.remove("oculto");
}

/* -------- 19b. CALCULADORA: ¿CUÁNTA PINTURA NECESITO? --------
   litros = metros² × manos ÷ rendimiento (m² que cubre 1 litro en una mano).
   La cuenta la hace el SERVIDOR (GET /api/calcular), con la misma lógica que
   usa el asistente: así las dos siempre dan el mismo resultado. El servidor
   también busca la combinación de formatos MÁS BARATA que cubra esos litros
   con el stock disponible (descontando lo que ya está en tu carrito). */
const formCalculadora = document.getElementById("formCalculadora");

/* Lo que hay en el carrito, como "formato_id:cantidad,..." (para no sugerir más de lo que queda) */
function carritoComoParametro() {
  const porFormato = {};
  carrito.forEach(function (item) {
    porFormato[item.formato_id] = (porFormato[item.formato_id] || 0) + (Number(item.cantidad) || 0);
  });
  return Object.entries(porFormato).slice(0, 50).map(function (par) { return par[0] + ":" + par[1]; }).join(",");
}

/* Detalle de una combinación de formatos (calculadora y asistente). Ya escapado. */
function htmlCombinacion(combinacion, nombreProducto) {
  return `<ul class="calculadora__lista">${combinacion.items.map(function (item) {
      return `<li><span>${item.cantidad} × ${escaparHTML(item.nombre)}
        <span class="calculadora__detalle">${formatearLitros(item.litros)}</span></span>
        <span>${formatearPrecio(item.cantidad * item.precio)}</span></li>`;
    }).join("")}</ul>
    <p class="calculadora__total"><span>${formatearLitros(combinacion.litros)} de ${escaparHTML(nombreProducto)}</span>
      <strong>${formatearPrecio(combinacion.precio)}</strong></p>`;
}

/* "40 m² × 2 manos ÷ 10 m² por litro" */
function explicacionLitros(calculo) {
  const decimales = { maximumFractionDigits: 1 };
  return `${calculo.m2.toLocaleString("es-CL", decimales)} m² × ${calculo.manos} ${calculo.manos === 1 ? "mano" : "manos"}
    ÷ ${calculo.rendimiento.toLocaleString("es-CL", decimales)} m² por litro`;
}

const NOTA_FICHA_DEMO = "El rendimiento es un valor de ejemplo: Ecocordi todavía debe confirmarlo.";

/* Llena la lista de pinturas según la superficie elegida */
function actualizarPinturasCalculadora() {
  if (!formCalculadora) return;
  const superficie = document.getElementById("calcSuperficie").value;
  const selector = document.getElementById("calcProducto");
  const anterior = selector.value;
  const lista = productos.filter(function (p) {
    return p.formatos.length > 0 && p.superficies.includes(superficie);
  });
  if (!superficie) {
    selector.innerHTML = '<option value="">Primero elige la superficie</option>';
    selector.disabled = true;
    return;
  }
  selector.disabled = lista.length === 0;
  selector.innerHTML = lista.length === 0
    ? '<option value="">No hay pinturas para esta superficie</option>'
    : '<option value="">Elige una pintura</option>' + lista.map(function (p) {
        return `<option value="${p.id}">${escaparHTML(p.nombre)}</option>`;
      }).join("");
  if (lista.some(function (p) { return String(p.id) === anterior; })) selector.value = anterior;
  else if (lista.length === 1) selector.value = String(lista[0].id);
}

/* Al filtrar el catálogo por una superficie, la calculadora la toma también
   (solo si la persona todavía no eligió una) */
function sugerirSuperficieCalculadora(superficie) {
  if (!formCalculadora || !SUPERFICIES[superficie]) return;
  const selector = document.getElementById("calcSuperficie");
  if (selector.value) return;
  selector.value = superficie;
  actualizarPinturasCalculadora();
}

let sugerenciaCalculadora = null; // última combinación sugerida (para "Agregar al carrito")

async function calcular() {
  const resultado = document.getElementById("calcResultado");
  const producto = productos.find(function (p) {
    return String(p.id) === document.getElementById("calcProducto").value;
  });
  const metros = Number(document.getElementById("calcMetros").value);
  const manos = Number(document.getElementById("calcManos").value);
  sugerenciaCalculadora = null;

  if (!producto || !(metros > 0) || metros > 10000 || ![1, 2, 3].includes(manos)) {
    resultado.innerHTML = "<p>Revisa los datos: elige la superficie y la pintura, y escribe los metros cuadrados (hasta 10.000).</p>";
    return;
  }
  const parametros = new URLSearchParams({ producto: producto.id, m2: metros, manos: manos });
  const enCarrito = carritoComoParametro();
  if (enCarrito) parametros.set("carrito", enCarrito);
  let calculo;
  try {
    const respuesta = await fetch("/api/calcular?" + parametros);
    calculo = await respuesta.json();
    if (!respuesta.ok) throw new Error(calculo.error);
  } catch (error) {
    resultado.innerHTML = "<p>No pudimos calcularlo ahora. Revisa tu conexión e inténtalo de nuevo.</p>";
    return;
  }

  const nombre = escaparHTML(producto.nombre);
  if (calculo.litros === null) {
    resultado.innerHTML = `<p>Todavía no tenemos el rendimiento de <strong>${nombre}</strong>, así que no podemos
      calcularlo por ti. Escríbenos y te ayudamos a elegir la cantidad.</p>`;
    return;
  }

  let html = `<p class="calculadora__litros">Necesitas unos <strong>${formatearLitros(calculo.litros)}</strong>
    <span>(${explicacionLitros(calculo)})</span></p>`;
  if (!calculo.combinacion) {
    html += `<p>No tenemos stock suficiente de <strong>${nombre}</strong> para cubrir esa cantidad ahora.
      Escríbenos y lo coordinamos.</p>`;
  } else {
    sugerenciaCalculadora = calculo.combinacion;
    html += `<p class="calculadora__subtitulo">Te sugerimos:</p>
      ${htmlCombinacion(calculo.combinacion, producto.nombre)}
      <button type="button" class="boton boton--principal boton--ancho" id="calcAgregar">Agregar al carrito</button>`;
  }
  html += `<p class="calculadora__nota">Es una estimación: el consumo real depende de la superficie
    (porosidad, textura, color anterior) y de cómo se aplique.${calculo.ficha_demo ? " " + NOTA_FICHA_DEMO : ""}</p>`;
  resultado.innerHTML = html;
}

if (formCalculadora) {
  document.getElementById("calcSuperficie").addEventListener("change", actualizarPinturasCalculadora);
  formCalculadora.addEventListener("submit", function (evento) {
    evento.preventDefault();
    calcular();
  });
  // "Agregar al carrito" de la sugerencia (el botón se dibuja con el resultado)
  document.getElementById("calcResultado").addEventListener("click", function (evento) {
    if (!evento.target.closest("#calcAgregar") || !sugerenciaCalculadora) return;
    sugerenciaCalculadora.items.forEach(function (item) {
      agregarAlCarrito(item.formato_id, item.cantidad, false);
    });
    sugerenciaCalculadora = null;
    evento.target.closest("#calcAgregar").disabled = true;
    abrirCarrito();
  });
}

/* ============================================================
   20. ARRANQUE
   ============================================================ */
cargarCarrito();     // recupera el carrito guardado
// trae los productos de la base de datos. Otras páginas (asistente) esperan
// esta "promesa" antes de agregar cosas al carrito.
const catalogoListo = cargarProductos();
cargarUsuario();     // revisa si ya hay sesión iniciada
mostrarBotonGoogle(); // muestra "Continuar con Google" si está disponible
revisarVueltaDeGoogle(); // mensajes al volver de Google
cargarConfiguracion(); // WhatsApp (si hay número) y la nota del IVA junto a los precios
revisarEntrarParaPedido(); // abre "Iniciar sesión" si viene desde pedido.html
actualizarCarrito(); // dibuja el carrito
