/* ============================================================
   ECOCORDI - Panel de administración
   Solo funciona si el usuario tiene sesión de administrador.
   Los avisos y confirmaciones vienen de js/ui.js (avisar / confirmar).
   ============================================================ */

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

// Nombres de superficies; también es la "lista blanca" para las clases CSS
const SUPERFICIES = {
  madera: "Madera", metal: "Metal", exterior: "Exterior", techo: "Techo", interior: "Interior",
};
function claseSuperficie(superficie) {
  return SUPERFICIES[superficie] ? "sup--" + superficie : "";
}

/* -------- 1. VERIFICAR QUE SEAS ADMINISTRADOR -------- */
async function verificarAdmin() {
  const respuesta = await fetch("/api/me");
  const usuario = await respuesta.json();

  if (usuario.invitado || !usuario.es_admin) {
    // No eres admin: mostramos el mensaje de acceso restringido
    document.getElementById("accesoDenegado").style.display = "block";
    return;
  }

  // Sí eres admin: mostramos el panel
  document.getElementById("panel").style.display = "block";
  document.getElementById("adminNombre").textContent = "Hola, " + usuario.nombre;
  cargarPedidos();
  cargarProductos();
}

/* -------- 2. PESTAÑAS (cambiar entre Pedidos y Productos) -------- */
document.querySelectorAll(".admin__tab").forEach(function (tab) {
  tab.addEventListener("click", function () {
    document.querySelectorAll(".admin__tab").forEach(function (t) {
      t.classList.remove("admin__tab--activo");
      t.setAttribute("aria-selected", "false");
    });
    tab.classList.add("admin__tab--activo");
    tab.setAttribute("aria-selected", "true");

    const cual = tab.dataset.tab;
    document.getElementById("tabPedidos").style.display = cual === "pedidos" ? "block" : "none";
    document.getElementById("tabProductos").style.display = cual === "productos" ? "block" : "none";
  });
});

/* Estados posibles de un pedido (los mismos que acepta el servidor) */
const ESTADOS = [
  ["pendiente", "Pendiente"],
  ["pagado",    "Pagado"],
  ["enviado",   "Enviado"],
  ["entregado", "Entregado"],
  ["cancelado", "Cancelado"],
];
const NOMBRE_ESTADO = Object.fromEntries(ESTADOS);

/* -------- 3. CARGAR Y MOSTRAR LOS PEDIDOS (una fila por pedido) -------- */
async function cargarPedidos() {
  const respuesta = await fetch("/api/admin/pedidos");
  const pedidos = await respuesta.json();
  const contenedor = document.getElementById("listaPedidos");
  document.getElementById("contadorPedidos").textContent = pedidos.length;

  if (pedidos.length === 0) {
    contenedor.innerHTML =
      "<tr><td colspan='6' class='admin__vacio tabla__sin-etiqueta'>Aún no hay pedidos.</td></tr>";
    return;
  }

  contenedor.innerHTML = pedidos.map(function (p) {
    const items = p.items.map(function (it) {
      return `<li>${it.cantidad} × ${escaparHTML(it.nombre)} <span class="tabla__secundario">${formatearPrecio(it.precio)} c/u</span></li>`;
    }).join("");

    // Solo usamos estados conocidos para armar clases CSS
    const estado = NOMBRE_ESTADO[p.estado] ? p.estado : "pendiente";
    // Selector de estado. Un pedido cancelado ya devolvió su stock y no se
    // puede reactivar, así que su selector queda bloqueado.
    const opciones = ESTADOS.map(function (e) {
      return `<option value="${e[0]}" ${e[0] === estado ? "selected" : ""}>${e[1]}</option>`;
    }).join("");

    return `
      <tr class="pedido pedido--${estado}" data-id="${p.id}">
        <td class="numero" data-etiqueta="N°">${p.id}</td>
        <td data-etiqueta="Fecha"><span class="numero">${escaparHTML(p.fecha)}</span></td>
        <td data-etiqueta="Cliente">
          ${escaparHTML(p.cliente || "Invitado")}
          <span class="tabla__secundario">${escaparHTML(p.correo)}</span>
        </td>
        <td data-etiqueta="Productos"><ul class="tabla__items">${items}</ul></td>
        <td class="numero" data-etiqueta="Total">${formatearPrecio(p.total)}</td>
        <td data-etiqueta="Estado">
          <select class="pedido__selector estado--${estado}" data-anterior="${estado}"
                  aria-label="Estado del pedido N° ${p.id}"
                  ${estado === "cancelado" ? "disabled" : ""}>${opciones}</select>
        </td>
      </tr>
    `;
  }).join("");
}

/* -------- 4. CARGAR Y MOSTRAR LOS PRODUCTOS (una fila por producto) --------
   Los campos de precio y stock de cada fila pertenecen a un <form> vacío
   gracias al atributo form="editar-ID": así cada fila es un formulario
   aunque sus campos estén en distintas celdas de la tabla. */
async function cargarProductos() {
  const respuesta = await fetch("/api/productos");
  const productos = await respuesta.json();
  const contenedor = document.getElementById("listaProductos");
  document.getElementById("contadorProductos").textContent = productos.length;

  if (productos.length === 0) {
    contenedor.innerHTML =
      "<tr><td colspan='4' class='admin__vacio tabla__sin-etiqueta'>No hay productos. Agrega el primero con el formulario.</td></tr>";
    return;
  }

  contenedor.innerHTML = productos.map(function (p) {
    const nombre = escaparHTML(p.nombre);
    const idForm = "editar-" + p.id;
    const superficies = p.superficies.map(function (s) {
      return `<li class="${claseSuperficie(s)}">${escaparHTML(SUPERFICIES[s] || s)}</li>`;
    }).join("");
    return `
      <tr class="admin-prod ${claseSuperficie(p.superficies[0])}" data-id="${p.id}">
        <td class="tabla__sin-etiqueta">
          <div class="admin-prod__celda">
            <img class="admin-prod__img" src="${escaparHTML(p.imagen)}" alt="" width="52" height="52" loading="lazy" />
            <div>
              <span class="admin-prod__nombre">${nombre}</span>
              <ul class="admin-prod__sups" aria-label="Superficies">${superficies}</ul>
              ${p.stock === 0 ? '<span class="admin-prod__agotado">Agotado</span>' : ""}
            </div>
          </div>
        </td>
        <td data-etiqueta="Precio">
          <form class="admin-prod__editar" id="${idForm}"></form>
          <input class="admin-prod__input" form="${idForm}" type="number" name="precio" min="0" step="1"
                 value="${p.precio}" required aria-label="Precio de ${nombre}" />
        </td>
        <td data-etiqueta="Stock">
          <input class="admin-prod__input admin-prod__input--stock" form="${idForm}" type="number" name="stock" min="0" step="1"
                 value="${p.stock}" required aria-label="Stock de ${nombre}" />
        </td>
        <td data-etiqueta="Acciones">
          <div class="admin-prod__acciones">
            <button type="submit" form="${idForm}" class="admin-prod__guardar">Guardar</button>
            <button type="button" class="admin-prod__borrar" aria-label="Eliminar ${nombre}">
              <svg class="icono" aria-hidden="true"><use href="#i-basura"/></svg>
            </button>
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

/* -------- 5. AGREGAR UN NUEVO PRODUCTO -------- */
document.getElementById("formProducto").addEventListener("submit", async function (e) {
  e.preventDefault();

  // Recogemos las superficies marcadas
  const superficies = [];
  document.querySelectorAll(".admin__superficies input:checked").forEach(function (chk) {
    superficies.push(chk.value);
  });

  const nuevo = {
    nombre: document.getElementById("pNombre").value,
    descripcion: document.getElementById("pDesc").value,
    precio: document.getElementById("pPrecio").value,
    stock: document.getElementById("pStock").value || 0,
    imagen: document.getElementById("pImagen").value || "img/prod-interior.webp",
    superficies: superficies,
  };

  const respuesta = await fetch("/api/admin/productos", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(nuevo),
  });

  if (respuesta.ok) {
    document.getElementById("formProducto").reset();
    cargarProductos();
    avisar("Producto agregado: " + nuevo.nombre, "exito");
  } else {
    const err = await respuesta.json();
    avisar("No se pudo guardar: " + (err.error || "error desconocido"), "error");
  }
});

/* -------- 6. BORRAR UN PRODUCTO (con diálogo de confirmación propio) -------- */
async function borrarProducto(id, nombre) {
  const seguro = await confirmar({
    titulo: "Eliminar producto",
    mensaje: "¿Eliminar «" + nombre + "» del catálogo? Esta acción no se puede deshacer.",
    textoConfirmar: "Eliminar",
    peligro: true,
  });
  if (!seguro) return;
  const respuesta = await fetch("/api/admin/productos/" + id, { method: "DELETE" });
  if (!respuesta.ok) {
    avisar("No se pudo eliminar el producto.", "error");
    return;
  }
  cargarProductos();
  avisar("Producto eliminado: " + nombre, "exito");
}

/* Un solo "escuchador" para todos los botones de borrar (delegación de
   eventos): el id sale del data-id de la fila del producto. */
document.getElementById("listaProductos").addEventListener("click", function (evento) {
  const boton = evento.target.closest(".admin-prod__borrar");
  if (!boton) return;
  const fila = boton.closest(".admin-prod");
  borrarProducto(Number(fila.dataset.id), fila.querySelector(".admin-prod__nombre").textContent);
});

/* -------- 7. EDITAR PRECIO Y STOCK DE UN PRODUCTO --------
   El evento "submit" también "sube" hasta el contenedor, así que un solo
   escuchador atiende los formularios de todos los productos. */
document.getElementById("listaProductos").addEventListener("submit", async function (evento) {
  evento.preventDefault();
  const form = evento.target;
  const fila = form.closest(".admin-prod");
  const id = Number(fila.dataset.id);
  const respuesta = await fetch("/api/admin/productos/" + id, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      precio: Number(form.elements.precio.value),
      stock: Number(form.elements.stock.value),
    }),
  });
  const datos = await respuesta.json();
  if (!respuesta.ok) {
    avisar("No se pudo guardar: " + (datos.error || "error desconocido"), "error");
    return;
  }
  cargarProductos();
  avisar("Cambios guardados: " + fila.querySelector(".admin-prod__nombre").textContent, "exito");
});

/* -------- 8. CAMBIAR EL ESTADO DE UN PEDIDO -------- */
document.getElementById("listaPedidos").addEventListener("change", async function (evento) {
  const selector = evento.target.closest(".pedido__selector");
  if (!selector) return;
  const id = Number(selector.closest(".pedido").dataset.id);
  const nuevo = selector.value;

  if (nuevo === "cancelado") {
    const seguro = await confirmar({
      titulo: "Cancelar pedido N° " + id,
      mensaje: "Sus productos volverán al stock y el pedido no se podrá reactivar.",
      textoConfirmar: "Cancelar pedido",
      peligro: true,
    });
    if (!seguro) {
      selector.value = selector.dataset.anterior; // deshacer la elección
      return;
    }
  }

  const respuesta = await fetch("/api/admin/pedidos/" + id, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ estado: nuevo }),
  });
  const datos = await respuesta.json();
  if (!respuesta.ok) {
    avisar("No se pudo cambiar el estado: " + (datos.error || "error desconocido"), "error");
    selector.value = selector.dataset.anterior;
    return;
  }
  cargarPedidos();
  if (nuevo === "cancelado") cargarProductos(); // el stock volvió
  avisar("Pedido N° " + id + ": " + NOMBRE_ESTADO[nuevo], "exito");
});

/* -------- 9. ARRANQUE -------- */
verificarAdmin();
