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
  cargarTarifas();
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
    document.getElementById("tabDespacho").style.display = cual === "despacho" ? "block" : "none";
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
      "<tr><td colspan='7' class='admin__vacio tabla__sin-etiqueta'>Aún no hay pedidos.</td></tr>";
    return;
  }

  contenedor.innerHTML = pedidos.map(function (p) {
    const items = p.items.map(function (it) {
      const formato = it.formato ? " (" + escaparHTML(it.formato) + ")" : "";
      return `<li>${it.cantidad} × ${escaparHTML(it.nombre)}${formato} <span class="tabla__secundario">${formatearPrecio(it.precio)} c/u</span></li>`;
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
          <div>
            ${escaparHTML(p.cliente_nombre || "Sin nombre")}
            ${p.invitado ? '<span class="etiqueta-invitado">Invitado</span>' : ""}
            <span class="tabla__secundario">${escaparHTML(p.cliente_correo || "")}</span>
            <span class="tabla__secundario">${escaparHTML(p.cliente_telefono || "")}</span>
          </div>
        </td>
        <td data-etiqueta="Entrega">${entregaYDocumento(p)}</td>
        <td data-etiqueta="Productos"><ul class="tabla__items">${items}</ul></td>
        <td data-etiqueta="Total">${montos(p)}</td>
        <td data-etiqueta="Estado">
          <select class="pedido__selector estado--${estado}" data-anterior="${estado}"
                  aria-label="Estado del pedido N° ${p.id}"
                  ${estado === "cancelado" ? "disabled" : ""}>${opciones}</select>
        </td>
      </tr>
    `;
  }).join("");
}

/* Entrega (retiro/despacho) y documento (boleta/factura) de un pedido. Ya escapado. */
function entregaYDocumento(p) {
  if (!p.entrega) return '<span class="tabla__secundario">Pedido anterior al checkout</span>';
  let entrega;
  if (p.entrega === "retiro") {
    entrega = "Retiro en " + escaparHTML(p.sucursal_nombre || p.sucursal);
  } else {
    const costo = p.costo_despacho === null
      ? '<strong class="tabla__coordinar">Coordinar despacho</strong>' : formatearPrecio(p.costo_despacho);
    entrega = `Despacho · ${costo}
      <span class="tabla__secundario">${escaparHTML(p.direccion || "(dirección borrada)")}</span>
      <span class="tabla__secundario">${escaparHTML(p.comuna)}, ${escaparHTML(p.region_nombre || p.region)}</span>`;
  }
  const documento = p.documento === "factura"
    ? `<span class="tabla__documento">Factura</span>
       <span class="tabla__secundario">RUT ${escaparHTML(p.factura_rut)} · ${escaparHTML(p.factura_razon_social)}</span>
       <span class="tabla__secundario">Giro: ${escaparHTML(p.factura_giro)}</span>
       <span class="tabla__secundario">${escaparHTML(p.factura_direccion)}</span>`
    : '<span class="tabla__documento">Boleta</span>';
  return `<div>${entrega}${documento}</div>`;
}

/* Total, con neto e IVA si el pedido los tiene */
function montos(p) {
  let html = `<span class="numero">${formatearPrecio(p.total)}</span>`;
  if (p.neto !== null && p.neto !== undefined) {
    html += `<span class="tabla__secundario">Neto ${formatearPrecio(p.neto)} · IVA ${formatearPrecio(p.iva)}</span>`;
    if (p.costo_despacho) html += `<span class="tabla__secundario">Incluye despacho ${formatearPrecio(p.costo_despacho)}</span>`;
  }
  return `<div>${html}</div>`;
}

/* -------- 4. FORMATOS DE VENTA --------
   Cada producto se vende en uno o más formatos (1/4 galón, galón, tineta...),
   cada uno con su propio precio y stock. */

// Litros de los formatos conocidos: se completan solos si el campo está vacío.
// La tineta no tiene un tamaño único, así que sus litros se escriben a mano.
const LITROS_CONOCIDOS = { "1/4 galón": 0.946, "galón": 3.785 };

function completarLitros(campoNombre, campoLitros) {
  campoNombre.addEventListener("change", function () {
    const litros = LITROS_CONOCIDOS[campoNombre.value.trim().toLowerCase()];
    if (litros && !campoLitros.value) campoLitros.value = litros;
  });
}

function formatearLitros(litros) {
  return litros.toLocaleString("es-CL", { maximumFractionDigits: 3 }) + " L";
}

/* -------- 5. CARGAR Y MOSTRAR LOS PRODUCTOS (una fila por producto) --------
   Cada formato es un pequeño formulario (precio, stock, Guardar y borrar).
   Al final de la celda, "Agregar formato" abre un formulario para uno nuevo. */
async function cargarProductos() {
  const respuesta = await fetch("/api/productos");
  const productos = await respuesta.json();
  const contenedor = document.getElementById("listaProductos");
  document.getElementById("contadorProductos").textContent = productos.length;

  if (productos.length === 0) {
    contenedor.innerHTML =
      "<tr><td colspan='3' class='admin__vacio tabla__sin-etiqueta'>No hay productos. Agrega el primero con el formulario.</td></tr>";
    return;
  }

  contenedor.innerHTML = productos.map(function (p) {
    const nombre = escaparHTML(p.nombre);
    const superficies = p.superficies.map(function (s) {
      return `<li class="${claseSuperficie(s)}">${escaparHTML(SUPERFICIES[s] || s)}</li>`;
    }).join("");
    const formatos = p.formatos.map(function (f) {
      const formato = escaparHTML(f.nombre);
      return `
        <li class="admin-formato" data-formato-id="${f.id}">
          <form class="admin-formato__form">
            <span class="admin-formato__nombre">${formato}
              <span class="tabla__secundario">${formatearLitros(f.litros)}</span>
              ${f.stock === 0 ? '<span class="admin-prod__agotado">Agotado</span>' : ""}
            </span>
            <label class="admin-formato__campo">
              <span>Precio</span>
              <input class="admin-prod__input" type="number" name="precio" min="0" step="1"
                     value="${f.precio}" required aria-label="Precio de ${nombre}, ${formato}" />
            </label>
            <label class="admin-formato__campo">
              <span>Stock</span>
              <input class="admin-prod__input admin-prod__input--stock" type="number" name="stock" min="0" step="1"
                     value="${f.stock}" required aria-label="Stock de ${nombre}, ${formato}" />
            </label>
            <button type="submit" class="admin-prod__guardar">Guardar</button>
            <button type="button" class="admin-prod__borrar admin-formato__borrar" aria-label="Eliminar el formato ${formato} de ${nombre}">
              <svg class="icono" aria-hidden="true"><use href="#i-basura"/></svg>
            </button>
          </form>
        </li>`;
    }).join("");
    return `
      <tr class="admin-prod ${claseSuperficie(p.superficies[0])}" data-id="${p.id}">
        <td class="tabla__sin-etiqueta">
          <div class="admin-prod__celda">
            <img class="admin-prod__img" src="${escaparHTML(p.imagen)}" alt="" width="52" height="52" loading="lazy" />
            <div>
              <span class="admin-prod__nombre">${nombre}</span>
              <ul class="admin-prod__sups" aria-label="Superficies">${superficies}</ul>
              ${p.formatos.length === 0 ? '<span class="admin-prod__agotado">Sin formatos: no se puede comprar</span>' : ""}
            </div>
          </div>
          ${htmlFicha(p, nombre)}
        </td>
        <td data-etiqueta="Formatos">
          <ul class="admin-formatos">${formatos}</ul>
          <details class="admin-formato-nuevo">
            <summary>Agregar formato</summary>
            <form class="admin-formato-nuevo__form">
              <label class="admin-formato__campo"><span>Formato</span>
                <input class="admin-prod__input" type="text" name="nombre" list="formatosSugeridos" maxlength="40" required
                       placeholder="1/4 galón" aria-label="Nombre del nuevo formato de ${nombre}" /></label>
              <label class="admin-formato__campo"><span>Litros</span>
                <input class="admin-prod__input admin-prod__input--stock" type="number" name="litros" min="0.001" max="1000" step="any" required
                       aria-label="Litros del nuevo formato de ${nombre}" /></label>
              <label class="admin-formato__campo"><span>Precio</span>
                <input class="admin-prod__input" type="number" name="precio" min="0" step="1" required
                       aria-label="Precio del nuevo formato de ${nombre}" /></label>
              <label class="admin-formato__campo"><span>Stock</span>
                <input class="admin-prod__input admin-prod__input--stock" type="number" name="stock" min="0" step="1" value="0" required
                       aria-label="Stock del nuevo formato de ${nombre}" /></label>
              <button type="submit" class="admin-prod__guardar">Agregar</button>
            </form>
          </details>
        </td>
        <td data-etiqueta="Acciones">
          <button type="button" class="admin-prod__borrar admin-prod__borrar-producto" aria-label="Eliminar ${nombre}">
            <svg class="icono" aria-hidden="true"><use href="#i-basura"/></svg>
          </button>
        </td>
      </tr>
    `;
  }).join("");

  document.querySelectorAll(".admin-formato-nuevo__form").forEach(function (form) {
    completarLitros(form.elements.nombre, form.elements.litros);
  });
}

/* -------- 5b. FICHA TÉCNICA (asistente y calculadora) --------
   Uso, acabado, resistencias, rendimiento y manos. "ficha_demo" marca los
   valores de EJEMPLO que la empresa todavía debe confirmar. */
const NOMBRES_USO = { interior: "Interior", exterior: "Exterior", ambos: "Interior y exterior" };
const NOMBRES_ACABADO = { mate: "Mate", satinado: "Satinado", brillante: "Brillante" };

/* Los campos del formulario, tal como los espera el servidor (vacío = null) */
function datosFicha(rendimiento, manos, uso, acabado, humedad, sol, lavable) {
  return {
    rendimiento_m2_litro: rendimiento.trim() === "" ? null : Number(rendimiento),
    manos_recomendadas: manos.trim() === "" ? null : Number(manos),
    uso: uso || null,
    acabado: acabado || null,
    resiste_humedad: humedad,
    resiste_sol: sol,
    lavable: lavable,
  };
}

function opcionesSelect(nombres, actual, textoVacio) {
  return `<option value="">${textoVacio}</option>` + Object.entries(nombres).map(function (par) {
    return `<option value="${par[0]}" ${par[0] === actual ? "selected" : ""}>${par[1]}</option>`;
  }).join("");
}

/* Resumen de la ficha + formulario para editarla (se despliega con "Ficha técnica") */
function htmlFicha(p, nombre) {
  const resumen = [
    NOMBRES_USO[p.uso] || "Sin uso: no aparece en el asistente",
    NOMBRES_ACABADO[p.acabado],
    p.rendimiento_m2_litro ? p.rendimiento_m2_litro.toLocaleString("es-CL") + " m²/L" : "Sin rendimiento",
  ].filter(Boolean).join(" · ");
  const casilla = function (nombreCampo, texto, marcada) {
    return `<label class="casilla"><input type="checkbox" name="${nombreCampo}" ${marcada ? "checked" : ""} />${texto}</label>`;
  };
  return `
    <details class="admin-ficha">
      <summary>Ficha técnica <span class="tabla__secundario">${escaparHTML(resumen)}</span>
        ${p.ficha_demo ? '<span class="etiqueta-demo">Ejemplo</span>' : ""}</summary>
      <form class="admin-ficha__form">
        <label class="admin-formato__campo"><span>Rendimiento (m²/L)</span>
          <input class="admin-prod__input admin-prod__input--stock" type="number" name="rendimiento" min="0.1" max="100" step="any"
                 value="${p.rendimiento_m2_litro ?? ""}" placeholder="Sin dato"
                 aria-label="Rendimiento de ${nombre} en metros cuadrados por litro" /></label>
        <label class="admin-formato__campo"><span>Manos</span>
          <input class="admin-prod__input admin-prod__input--stock" type="number" name="manos" min="1" max="5" step="1"
                 value="${p.manos_recomendadas ?? ""}" placeholder="—" aria-label="Manos recomendadas de ${nombre}" /></label>
        <label class="admin-formato__campo"><span>Uso</span>
          <select class="admin-prod__input" name="uso" aria-label="Uso de ${nombre}">${opcionesSelect(NOMBRES_USO, p.uso, "Sin dato")}</select></label>
        <label class="admin-formato__campo"><span>Acabado</span>
          <select class="admin-prod__input" name="acabado" aria-label="Acabado de ${nombre}">${opcionesSelect(NOMBRES_ACABADO, p.acabado, "Sin dato")}</select></label>
        <div class="admin__casillas">
          ${casilla("humedad", "Resiste humedad", p.resiste_humedad)}
          ${casilla("sol", "Resiste sol", p.resiste_sol)}
          ${casilla("lavable", "Lavable", p.lavable)}
          ${casilla("demo", "Valores de ejemplo (por confirmar)", p.ficha_demo)}
        </div>
        <button type="submit" class="admin-prod__guardar">Guardar ficha</button>
      </form>
    </details>`;
}

/* Envía un cambio a la API y avisa el resultado. Devuelve true si salió bien. */
async function enviar(metodo, ruta, datos, textoOk) {
  const respuesta = await fetch(ruta, {
    method: metodo,
    headers: { "Content-Type": "application/json" },
    body: datos ? JSON.stringify(datos) : undefined,
  });
  const resultado = await respuesta.json().catch(function () { return {}; });
  if (!respuesta.ok) {
    avisar("No se pudo guardar: " + (resultado.error || "error desconocido"), "error");
    return false;
  }
  avisar(textoOk, "exito");
  return true;
}

/* -------- 6. AGREGAR UN NUEVO PRODUCTO (con su primer formato) -------- */
completarLitros(document.getElementById("pFormato"), document.getElementById("pLitros"));

document.getElementById("formProducto").addEventListener("submit", async function (e) {
  e.preventDefault();

  // Recogemos las superficies marcadas
  const superficies = [];
  document.querySelectorAll(".admin__superficies input:checked").forEach(function (chk) {
    superficies.push(chk.value);
  });

  const campo = function (id) { return document.getElementById(id); };
  const nuevo = {
    ...datosFicha(campo("pRendimiento").value, campo("pManos").value, campo("pUso").value, campo("pAcabado").value,
                  campo("pHumedad").checked, campo("pSol").checked, campo("pLavable").checked),
    nombre: document.getElementById("pNombre").value,
    descripcion: document.getElementById("pDesc").value,
    imagen: document.getElementById("pImagen").value || "img/prod-interior.webp",
    superficies: superficies,
    formatos: [{
      nombre: document.getElementById("pFormato").value.trim(),
      litros: Number(document.getElementById("pLitros").value),
      precio: Number(document.getElementById("pPrecio").value),
      stock: Number(document.getElementById("pStock").value || 0),
    }],
  };

  if (await enviar("POST", "/api/admin/productos", nuevo, "Producto agregado: " + nuevo.nombre)) {
    document.getElementById("formProducto").reset();
    cargarProductos();
  }
});

/* -------- 7. BORRAR PRODUCTOS Y FORMATOS (con diálogo de confirmación propio) --------
   Un solo "escuchador" para todos los botones (delegación de eventos). */
document.getElementById("listaProductos").addEventListener("click", async function (evento) {
  const fila = evento.target.closest(".admin-prod");
  if (!fila) return;
  const nombre = fila.querySelector(".admin-prod__nombre").textContent;

  if (evento.target.closest(".admin-prod__borrar-producto")) {
    const seguro = await confirmar({
      titulo: "Eliminar producto",
      mensaje: "¿Eliminar «" + nombre + "» y todos sus formatos del catálogo? Esta acción no se puede deshacer.",
      textoConfirmar: "Eliminar",
      peligro: true,
    });
    if (seguro && await enviar("DELETE", "/api/admin/productos/" + fila.dataset.id, null, "Producto eliminado: " + nombre)) {
      cargarProductos();
    }
    return;
  }

  const botonFormato = evento.target.closest(".admin-formato__borrar");
  if (botonFormato) {
    const item = botonFormato.closest(".admin-formato");
    const formato = item.querySelector(".admin-formato__nombre").firstChild.textContent.trim();
    const seguro = await confirmar({
      titulo: "Eliminar formato",
      mensaje: "¿Eliminar el formato «" + formato + "» de «" + nombre + "»? Los pedidos ya hechos no cambian.",
      textoConfirmar: "Eliminar",
      peligro: true,
    });
    if (seguro && await enviar("DELETE", "/api/admin/formatos/" + item.dataset.formatoId, null,
                               "Formato eliminado: " + nombre + " (" + formato + ")")) {
      cargarProductos();
    }
  }
});

/* -------- 7b. GUARDAR PRECIO Y STOCK, O AGREGAR UN FORMATO --------
   El evento "submit" también "sube" hasta el contenedor, así que un solo
   escuchador atiende los formularios de todos los productos. */
document.getElementById("listaProductos").addEventListener("submit", async function (evento) {
  evento.preventDefault();
  const form = evento.target;
  const fila = form.closest(".admin-prod");
  const nombre = fila.querySelector(".admin-prod__nombre").textContent;

  if (form.matches(".admin-formato__form")) {
    const item = form.closest(".admin-formato");
    if (await enviar("PATCH", "/api/admin/formatos/" + item.dataset.formatoId, {
      precio: Number(form.elements.precio.value),
      stock: Number(form.elements.stock.value),
    }, "Cambios guardados: " + nombre)) {
      cargarProductos();
    }
    return;
  }

  if (form.matches(".admin-ficha__form")) {
    const e = form.elements;
    if (await enviar("PATCH", "/api/admin/productos/" + fila.dataset.id, {
      ...datosFicha(e.rendimiento.value, e.manos.value, e.uso.value, e.acabado.value,
                    e.humedad.checked, e.sol.checked, e.lavable.checked),
      ficha_demo: e.demo.checked,
    }, "Ficha técnica guardada: " + nombre)) {
      cargarProductos();
    }
    return;
  }

  if (form.matches(".admin-formato-nuevo__form")) {
    const formato = form.elements.nombre.value.trim();
    if (await enviar("POST", "/api/admin/productos/" + fila.dataset.id + "/formatos", {
      nombre: formato,
      litros: Number(form.elements.litros.value),
      precio: Number(form.elements.precio.value),
      stock: Number(form.elements.stock.value),
    }, "Formato agregado: " + nombre + " (" + formato + ")")) {
      cargarProductos();
    }
  }
});

/* -------- 7c. TARIFAS DE DESPACHO POR REGIÓN --------
   Vacío = sin tarifa: en el checkout aparece "Coordinar despacho". */
async function cargarTarifas() {
  const config = await (await fetch("/api/config")).json();
  document.getElementById("listaTarifas").innerHTML = Object.entries(config.regiones).map(function (r) {
    const costo = config.tarifas_despacho[r[0]];
    const nombre = escaparHTML(r[1]);
    return `
      <tr class="tarifa" data-region="${escaparHTML(r[0])}">
        <td data-etiqueta="Región">${nombre}</td>
        <td data-etiqueta="Costo">
          <form class="admin-formato__form tarifa__form">
            <input class="admin-prod__input" type="number" name="costo" min="0" step="1"
                   value="${costo === undefined ? "" : costo}" placeholder="Coordinar"
                   aria-label="Costo de despacho a ${nombre} (vacío para coordinar)" />
            <button type="submit" class="admin-prod__guardar">Guardar</button>
            ${costo === undefined ? '<span class="tabla__secundario">Se coordina con el cliente</span>' : ""}
          </form>
        </td>
      </tr>`;
  }).join("");
}

document.getElementById("listaTarifas").addEventListener("submit", async function (evento) {
  evento.preventDefault();
  const fila = evento.target.closest(".tarifa");
  const valor = evento.target.elements.costo.value.trim();
  const region = fila.querySelector("td").textContent;
  if (await enviar("PATCH", "/api/admin/tarifas/" + encodeURIComponent(fila.dataset.region),
                   { costo: valor === "" ? null : Number(valor) },
                   valor === "" ? "Despacho a " + region + ": se coordina" : "Tarifa guardada: " + region)) {
    cargarTarifas();
  }
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
