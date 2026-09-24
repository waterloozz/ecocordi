/* ============================================================
   ECOCORDI - Panel de administración
   Solo funciona si el usuario tiene sesión de administrador.
   ============================================================ */

function formatearPrecio(valor) {
  return "$" + valor.toLocaleString("es-CL");
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
      return `<li>${it.cantidad} × ${it.nombre} — ${formatearPrecio(it.precio)}</li>`;
    }).join("");

    contenedor.innerHTML += `
      <div class="pedido">
        <div class="pedido__cabecera">
          <strong>Pedido N° ${p.id}</strong>
          <span class="pedido__total">${formatearPrecio(p.total)}</span>
        </div>
        <p class="pedido__cliente">👤 ${p.cliente || "Invitado"} · ${p.correo || ""}</p>
        <p class="pedido__fecha">🕐 ${p.fecha}</p>
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
      <div class="admin-prod">
        <img src="${p.imagen}" alt="${p.nombre}" />
        <div class="admin-prod__info">
          <strong>${p.nombre}</strong>
          <span>${formatearPrecio(p.precio)}</span>
          <small>${p.superficies.join(", ")}</small>
        </div>
        <button class="admin-prod__borrar" onclick="borrarProducto(${p.id})">🗑️</button>
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

/* -------- 7. ARRANQUE -------- */
verificarAdmin();
