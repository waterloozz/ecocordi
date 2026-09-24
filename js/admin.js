/* ============================================================
   ECOCORDI - Panel de administración
   Solo funciona si el usuario tiene sesión de administrador.
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
    });
    tab.classList.add("admin__tab--activo");

    const cual = tab.dataset.tab;
    document.getElementById("tabPedidos").style.display = cual === "pedidos" ? "block" : "none";
    document.getElementById("tabProductos").style.display = cual === "productos" ? "block" : "none";
  });
});

/* Estados posibles de un pedido (los mismos que acepta el servidor) */
const ESTADOS = [
  ["pendiente", "⏳ Pendiente"],
  ["pagado",    "💳 Pagado"],
  ["enviado",   "🚚 Enviado"],
  ["entregado", "✅ Entregado"],
  ["cancelado", "✖ Cancelado"],
];

/* -------- 3. CARGAR Y MOSTRAR LOS PEDIDOS -------- */
async function cargarPedidos() {
  const respuesta = await fetch("/api/admin/pedidos");
  const pedidos = await respuesta.json();
  const contenedor = document.getElementById("listaPedidos");

  if (pedidos.length === 0) {
    contenedor.innerHTML = "<p class='admin__vacio'>Aún no hay pedidos.</p>";
    return;
  }

  contenedor.innerHTML = "";
  pedidos.forEach(function (p) {
    const filas = p.items.map(function (it) {
      return `<li>${it.cantidad} × ${escaparHTML(it.nombre)} — ${formatearPrecio(it.precio)}</li>`;
    }).join("");

    // Selector de estado. Un pedido cancelado ya devolvió su stock y no se
    // puede reactivar, así que su selector queda bloqueado.
    const opciones = ESTADOS.map(function (e) {
      return `<option value="${e[0]}" ${e[0] === p.estado ? "selected" : ""}>${e[1]}</option>`;
    }).join("");

    contenedor.innerHTML += `
      <div class="pedido pedido--${escaparHTML(p.estado)}" data-id="${p.id}">
        <div class="pedido__cabecera">
          <strong>Pedido N° ${p.id}</strong>
          <span class="pedido__total">${formatearPrecio(p.total)}</span>
        </div>
        <label class="pedido__estado">Estado:
          <select class="pedido__selector" data-anterior="${escaparHTML(p.estado)}"
                  ${p.estado === "cancelado" ? "disabled" : ""}>${opciones}</select>
        </label>
        <p class="pedido__cliente">👤 ${escaparHTML(p.cliente || "Invitado")} · ${escaparHTML(p.correo)}</p>
        <p class="pedido__fecha">🕐 ${escaparHTML(p.fecha)}</p>
        <ul class="pedido__items">${filas}</ul>
      </div>
    `;
  });
}

/* -------- 4. CARGAR Y MOSTRAR LOS PRODUCTOS -------- */
async function cargarProductos() {
  const respuesta = await fetch("/api/productos");
  const productos = await respuesta.json();
  const contenedor = document.getElementById("listaProductos");

  contenedor.innerHTML = "";
  productos.forEach(function (p) {
    contenedor.innerHTML += `
      <div class="admin-prod" data-id="${p.id}">
        <img src="${escaparHTML(p.imagen)}" alt="${escaparHTML(p.nombre)}" />
        <div class="admin-prod__info">
          <strong>${escaparHTML(p.nombre)}</strong>
          <span>${formatearPrecio(p.precio)}</span>
          <small>${escaparHTML(p.superficies.join(", "))}</small>
          <small class="${p.stock === 0 ? "admin-prod__agotado" : ""}">
            Stock: ${p.stock}${p.stock === 0 ? " (agotado)" : ""}
          </small>
        </div>
        <button class="admin-prod__borrar" aria-label="Eliminar producto">🗑️</button>
        <form class="admin-prod__editar">
          <label>Precio <input type="number" name="precio" min="0" step="1" value="${p.precio}" required /></label>
          <label>Stock <input type="number" name="stock" min="0" step="1" value="${p.stock}" required /></label>
          <button type="submit" class="admin-prod__guardar">Guardar</button>
        </form>
      </div>
    `;
  });
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
    imagen: document.getElementById("pImagen").value || "img/interior.jpg",
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
    alert("Producto agregado ✓");
  } else {
    const err = await respuesta.json();
    alert("Error: " + (err.error || "no se pudo guardar"));
  }
});

/* -------- 6. BORRAR UN PRODUCTO -------- */
async function borrarProducto(id) {
  if (!confirm("¿Seguro que quieres eliminar este producto?")) return;
  await fetch("/api/admin/productos/" + id, { method: "DELETE" });
  cargarProductos();
}

/* Un solo "escuchador" para todos los botones de borrar (delegación de
   eventos): el id sale del data-id de la fila del producto. */
document.getElementById("listaProductos").addEventListener("click", function (evento) {
  const boton = evento.target.closest(".admin-prod__borrar");
  if (!boton) return;
  borrarProducto(Number(boton.closest(".admin-prod").dataset.id));
});

/* -------- 7. EDITAR PRECIO Y STOCK DE UN PRODUCTO --------
   El evento "submit" también "sube" hasta el contenedor, así que un solo
   escuchador atiende los formularios de todos los productos. */
document.getElementById("listaProductos").addEventListener("submit", async function (evento) {
  evento.preventDefault();
  const form = evento.target;
  const id = Number(form.closest(".admin-prod").dataset.id);
  const respuesta = await fetch("/api/admin/productos/" + id, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      precio: Number(form.precio.value),
      stock: Number(form.stock.value),
    }),
  });
  const datos = await respuesta.json();
  if (!respuesta.ok) {
    alert("Error: " + (datos.error || "no se pudo guardar"));
    return;
  }
  cargarProductos();
});

/* -------- 8. CAMBIAR EL ESTADO DE UN PEDIDO -------- */
document.getElementById("listaPedidos").addEventListener("change", async function (evento) {
  const selector = evento.target.closest(".pedido__selector");
  if (!selector) return;
  const id = Number(selector.closest(".pedido").dataset.id);
  const nuevo = selector.value;

  if (nuevo === "cancelado" &&
      !confirm("¿Cancelar el pedido N° " + id + "? Sus productos volverán al stock y no se podrá reactivar.")) {
    selector.value = selector.dataset.anterior; // deshacer la elección
    return;
  }

  const respuesta = await fetch("/api/admin/pedidos/" + id, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ estado: nuevo }),
  });
  const datos = await respuesta.json();
  if (!respuesta.ok) {
    alert("Error: " + (datos.error || "no se pudo cambiar el estado"));
    selector.value = selector.dataset.anterior;
    return;
  }
  cargarPedidos();
  if (nuevo === "cancelado") cargarProductos(); // el stock volvió
});

/* -------- 9. ARRANQUE -------- */
verificarAdmin();
