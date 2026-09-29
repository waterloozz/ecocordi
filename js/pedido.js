/* ============================================================
   ECOCORDI - Finalizar pedido (pedido.html)
   Paso 1: tus datos, entrega (retiro o despacho) y documento (boleta o factura).
   Paso 2: resumen final calculado por el SERVIDOR, aceptación y envío.
   El carrito viene del navegador (localStorage), igual que en la tienda.
   Los avisos vienen de js/ui.js (avisar).
   ============================================================ */

/* -------- 1. ESTADO -------- */
let carrito = [];     // [{ formato_id, nombre, formato, precio, stock, cantidad, ... }]
let usuario = null;   // datos de la cuenta, o null si compra como invitado
let config = null;    // /api/config: IVA, sucursales, regiones y tarifas de despacho
let cotizacion = null; // último resumen calculado por el servidor (paso 2)

const form = document.getElementById("formPedido");
const errorPedido = document.getElementById("pedidoError");
const errorEnviar = document.getElementById("enviarError");
const campo = function (id) { return document.getElementById(id); };

/* -------- 2. UTILIDADES -------- */
function formatearPrecio(valor) {
  return "$" + (Number(valor) || 0).toLocaleString("es-CL");
}

/* Escapar texto antes de meterlo en el HTML (ver app.js) */
function escaparHTML(texto) {
  return String(texto ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function mostrar(elemento, visible) {
  elemento.classList.toggle("oculto", !visible);
}

/* RUT chileno: revisa el dígito verificador (módulo 11), igual que el servidor.
   Devuelve "12.345.678-5" o null si no es válido. */
function formatearRut(texto) {
  const limpio = String(texto || "").replace(/[.\s-]/g, "").toUpperCase();
  if (!/^\d{7,8}[\dK]$/.test(limpio)) return null;
  const cuerpo = limpio.slice(0, -1);
  const dv = limpio.slice(-1);
  let suma = 0;
  let factor = 2;
  for (let i = cuerpo.length - 1; i >= 0; i--) {
    suma += Number(cuerpo[i]) * factor;
    factor = factor === 7 ? 2 : factor + 1;
  }
  const resto = 11 - (suma % 11);
  const esperado = resto === 11 ? "0" : resto === 10 ? "K" : String(resto);
  if (dv !== esperado) return null;
  return Number(cuerpo).toLocaleString("es-CL") + "-" + dv;
}

/* Neto, IVA y total: la MISMA cuenta que hace el servidor (calcular_totales).
   Sirve para mostrar el resumen mientras se llena el formulario; el monto
   final siempre lo calcula el servidor. */
function calcularTotales(subtotal, despacho) {
  const tasa = config.tasa_iva;
  const base = subtotal + (despacho || 0);
  let neto, iva, total;
  if (config.precios_incluyen_iva) {
    total = base;
    neto = Math.floor((total * 200 + (100 + tasa)) / (2 * (100 + tasa)));
    iva = total - neto;
  } else {
    neto = base;
    iva = Math.floor((neto * tasa * 2 + 100) / 200);
    total = neto + iva;
  }
  return { subtotal: subtotal, despacho: despacho, neto: neto, iva: iva, total: total };
}

/* -------- 3. CARRITO (el mismo de la tienda) -------- */
function cargarCarrito() {
  try {
    const guardado = JSON.parse(localStorage.getItem("carrito_ecocordi") || "[]");
    carrito = Array.isArray(guardado) ? guardado : [];
  } catch (error) {
    carrito = [];
  }
}
function guardarCarrito() {
  try {
    localStorage.setItem("carrito_ecocordi", JSON.stringify(carrito));
  } catch (error) { /* sin localStorage: el carrito vive solo en esta página */ }
}

/* Actualiza precios y stock con el catálogo real (igual que la tienda):
   quita lo que ya no existe o se agotó, y ajusta cantidades al stock. */
function sincronizarCarrito(productos) {
  const formatos = {};
  productos.forEach(function (p) {
    p.formatos.forEach(function (f) { formatos[f.id] = { producto: p, formato: f }; });
  });
  const antes = carrito.length;
  carrito = carrito
    .filter(function (item) { return formatos[item.formato_id] && formatos[item.formato_id].formato.stock > 0; })
    .map(function (item) {
      const { producto, formato } = formatos[item.formato_id];
      return {
        formato_id: formato.id, producto_id: producto.id, nombre: producto.nombre, formato: formato.nombre,
        precio: formato.precio, stock: formato.stock, imagen: producto.imagen, superficies: producto.superficies,
        cantidad: Math.min(Number(item.cantidad) || 1, formato.stock),
      };
    });
  guardarCarrito();
  if (carrito.length < antes) {
    avisar("Quitamos de tu pedido productos que ya no están disponibles.", "info");
  }
}

function subtotalCarrito() {
  return carrito.reduce(function (suma, item) { return suma + item.precio * item.cantidad; }, 0);
}

/* -------- 4. LEER EL FORMULARIO -------- */
function tipoEntrega() { return form.elements.entrega.value; }
function tipoDocumento() { return form.elements.documento.value; }

function datosDelFormulario() {
  const entrega = tipoEntrega() === "retiro"
    ? { tipo: "retiro", sucursal: campo("pSucursal").value }
    : { tipo: "despacho", region: campo("pRegion").value, comuna: campo("pComuna").value, direccion: campo("pDireccion").value };
  const documento = tipoDocumento() === "boleta"
    ? { tipo: "boleta" }
    : { tipo: "factura", rut: campo("pRut").value, razon_social: campo("pRazonSocial").value,
        giro: campo("pGiro").value, direccion: campo("pDireccionFactura").value };
  return {
    items: carrito.map(function (i) { return { formato_id: i.formato_id, cantidad: i.cantidad }; }),
    cliente: { nombre: campo("pNombre").value, correo: campo("pCorreo").value, telefono: campo("pTelefono").value },
    entrega: entrega,
    documento: documento,
  };
}

/* Costo del despacho según lo elegido: 0 (retiro), número, null (coordinar)
   o undefined (todavía no elige región) */
function costoDespacho() {
  if (tipoEntrega() === "retiro") return 0;
  const region = campo("pRegion").value;
  if (!region) return undefined;
  const tarifa = config.tarifas_despacho[region];
  return tarifa === undefined ? null : tarifa;
}

/* -------- 5. RESUMEN (columna derecha) -------- */
function pintarResumen(montos) {
  campo("resumenItems").innerHTML = carrito.map(function (item) {
    return `
      <li class="pedido__item">
        <span><span class="pedido__cantidad">${item.cantidad} ×</span> ${escaparHTML(item.nombre)}
          <span class="pedido__formato">${escaparHTML(item.formato)}</span></span>
        <span class="pedido__precio">${formatearPrecio(item.precio * item.cantidad)}</span>
      </li>`;
  }).join("");

  const despacho = montos ? montos.despacho : costoDespacho();
  const totales = montos || calcularTotales(subtotalCarrito(), despacho || 0);
  let textoDespacho;
  if (tipoEntrega() === "retiro") textoDespacho = "Sin costo (retiro)";
  else if (despacho === undefined) textoDespacho = "Elige la región";
  else if (despacho === null) textoDespacho = "A coordinar";
  else textoDespacho = formatearPrecio(despacho);

  campo("resumenMontos").innerHTML = `
    <div><dt>Productos</dt><dd>${formatearPrecio(totales.subtotal)}</dd></div>
    <div><dt>Despacho</dt><dd>${textoDespacho}</dd></div>
    <div class="pedido__monto-secundario"><dt>Neto</dt><dd>${formatearPrecio(totales.neto)}</dd></div>
    <div class="pedido__monto-secundario"><dt>IVA (${config.tasa_iva} %)</dt><dd>${formatearPrecio(totales.iva)}</dd></div>
    <div class="pedido__monto-total"><dt>Total</dt><dd>${formatearPrecio(totales.total)}</dd></div>`;
  campo("notaIva").textContent = (config.precios_incluyen_iva
    ? "Los precios del catálogo incluyen IVA."
    : "Los precios del catálogo no incluyen IVA: se agrega al total.") +
    (despacho === null ? " El costo del despacho se confirma contigo antes de pagar y no está sumado al total." : "");
}

/* -------- 6. MOSTRAR U OCULTAR SEGÚN LO ELEGIDO --------
   Un <fieldset disabled> no se valida ni se envía: así, si eliges "Retiro",
   el navegador no te pide la dirección de despacho. */
function actualizarOpciones() {
  const despacho = tipoEntrega() === "despacho";
  mostrar(campo("bloqueRetiro"), !despacho);
  campo("bloqueRetiro").disabled = despacho;
  mostrar(campo("bloqueDespacho"), despacho);
  campo("bloqueDespacho").disabled = !despacho;

  const factura = tipoDocumento() === "factura";
  mostrar(campo("bloqueFactura"), factura);
  campo("bloqueFactura").disabled = !factura;

  const costo = costoDespacho();
  const region = config.regiones[campo("pRegion").value];
  campo("tarifaInfo").textContent = !despacho || costo === undefined ? ""
    : costo === null
      ? `Para ${region} coordinamos el despacho contigo: te confirmaremos el costo antes de que pagues.`
      : `Despacho a ${region}: ${formatearPrecio(costo)}.`;
  pintarResumen();
}

/* El RUT se revisa al salir del campo: si no es válido, el navegador lo
   marca y no deja continuar; si es válido, lo escribimos con puntos y guion. */
function revisarRut() {
  const entrada = campo("pRut");
  if (!entrada.value.trim()) {
    entrada.setCustomValidity("");
    return;
  }
  const rut = formatearRut(entrada.value);
  entrada.setCustomValidity(rut ? "" : "El RUT no es válido: revisa el número y el dígito verificador.");
  if (rut) entrada.value = rut;
}

/* -------- 7. PASOS -------- */
function irAlPaso(paso) {
  mostrar(form, paso === 1);
  mostrar(campo("pasoRevisar"), paso === 2);
  mostrar(campo("pasoListo"), paso === 3);
  mostrar(campo("linkEditarCarrito"), paso !== 3);
  [campo("indicadorPaso1"), campo("indicadorPaso2")].forEach(function (li, i) {
    const activo = i + 1 === Math.min(paso, 2);
    li.classList.toggle("pedido__paso--activo", activo);
    if (activo && paso !== 3) li.setAttribute("aria-current", "step");
    else li.removeAttribute("aria-current");
    li.classList.toggle("pedido__paso--hecho", i + 1 < paso);
  });
  window.scrollTo({ top: 0 });
}

/* Paso 1 → 2: el servidor revisa todo y calcula los montos finales */
form.addEventListener("submit", async function (evento) {
  evento.preventDefault();
  errorPedido.textContent = "";
  revisarRut();
  if (!form.reportValidity()) return;

  const boton = campo("btnRevisar");
  boton.disabled = true;
  try {
    const respuesta = await fetch("/api/pedidos/cotizar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(datosDelFormulario()),
    });
    const datos = await respuesta.json();
    if (respuesta.status === 409) {
      await recargarCatalogo();
      errorPedido.textContent = datos.error + " Ajustamos tu pedido al stock disponible.";
      return;
    }
    if (!respuesta.ok) {
      errorPedido.textContent = datos.error || "No pudimos revisar tu pedido. Inténtalo de nuevo.";
      return;
    }
    cotizacion = datos;
    pintarRevision();
    pintarResumen(datos);
    irAlPaso(2);
    campo("revisarTitulo").focus();
  } catch (error) {
    errorPedido.textContent = "No pudimos conectarnos con la tienda. Revisa tu conexión e inténtalo de nuevo.";
  } finally {
    boton.disabled = false;
  }
});

function pintarRevision() {
  const d = datosDelFormulario();
  const filas = [
    ["Contacto", `${escaparHTML(d.cliente.nombre)}<br>${escaparHTML(d.cliente.correo)}<br>${escaparHTML(d.cliente.telefono)}`],
  ];
  if (d.entrega.tipo === "retiro") {
    filas.push(["Entrega", "Retiro en sucursal " + escaparHTML(config.sucursales[d.entrega.sucursal])]);
  } else {
    filas.push(["Entrega", `Despacho a domicilio<br>${escaparHTML(d.entrega.direccion)}<br>
      ${escaparHTML(d.entrega.comuna)}, ${escaparHTML(config.regiones[d.entrega.region])}<br>
      ${cotizacion.despacho_por_coordinar ? "Costo: a coordinar contigo" : "Costo: " + formatearPrecio(cotizacion.despacho)}`]);
  }
  if (d.documento.tipo === "boleta") {
    filas.push(["Documento", "Boleta"]);
  } else {
    filas.push(["Documento", `Factura<br>RUT ${escaparHTML(formatearRut(d.documento.rut) || d.documento.rut)}<br>
      ${escaparHTML(d.documento.razon_social)}<br>Giro: ${escaparHTML(d.documento.giro)}<br>${escaparHTML(d.documento.direccion)}`]);
  }
  campo("revisarDatos").innerHTML = filas.map(function (f) {
    return `<div><dt>${f[0]}</dt><dd>${f[1]}</dd></div>`;
  }).join("");
}

campo("btnEditar").addEventListener("click", function () {
  cotizacion = null;
  errorEnviar.textContent = "";
  irAlPaso(1);
  pintarResumen();
  campo("pNombre").focus();
});

/* Paso 2 → enviar el pedido */
campo("btnEnviar").addEventListener("click", async function () {
  errorEnviar.textContent = "";
  const acepta = campo("aceptaPedido");
  if (!acepta.checked) {
    errorEnviar.textContent = "Para enviar tu pedido, marca la casilla de aceptación de los Términos y la Política de cambios y devoluciones.";
    acepta.focus();
    return;
  }
  const boton = campo("btnEnviar");
  boton.disabled = true; // evita enviar dos veces con un doble clic
  try {
    const cuerpo = datosDelFormulario();
    cuerpo.acepta_terminos = true;
    const respuesta = await fetch("/api/pedidos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cuerpo),
    });
    const datos = await respuesta.json();
    if (respuesta.status === 409) {
      // Alguien compró antes: volvemos al paso 1 con el stock real
      await recargarCatalogo();
      irAlPaso(1);
      errorPedido.textContent = datos.error + " Ajustamos tu pedido al stock disponible: revísalo y vuelve a continuar.";
      return;
    }
    if (!respuesta.ok) {
      errorEnviar.textContent = datos.error || "No se pudo enviar el pedido. Inténtalo de nuevo.";
      return;
    }
    pedidoListo(datos, cuerpo);
  } catch (error) {
    errorEnviar.textContent = "No pudimos conectarnos con la tienda. Revisa tu conexión e inténtalo de nuevo.";
  } finally {
    boton.disabled = false;
  }
});

function pedidoListo(datos, cuerpo) {
  const correo = escaparHTML(usuario ? usuario.correo : cuerpo.cliente.correo);
  let html = `
    <p class="pedido__numero">Pedido N° <strong>${datos.pedido_id}</strong> · Total ${formatearPrecio(datos.total)}</p>
    <p>Te contactaremos a <strong>${correo}</strong> o por teléfono para coordinar el pago y
      ${cuerpo.entrega.tipo === "retiro" ? "el retiro" : "el despacho"}. No se ha cobrado nada.</p>`;
  if (datos.despacho_por_coordinar) {
    html += "<p>El costo del despacho a tu región lo confirmaremos contigo antes de que pagues.</p>";
  }
  html += usuario
    ? '<p>Puedes seguir su estado en «Mis pedidos».</p>'
    : `<p>Guarda tu número de pedido. Si más adelante entras con Google usando ${correo},
        verás este pedido en «Mis pedidos».</p>`;
  campo("listoDetalle").innerHTML = html;
  pintarResumen(datos);
  carrito = [];
  guardarCarrito();
  irAlPaso(3);
  campo("listoTitulo").focus();
}

/* -------- 8. ARRANQUE -------- */
async function recargarCatalogo() {
  const productos = await (await fetch("/api/productos")).json();
  sincronizarCarrito(productos);
  if (carrito.length === 0) {
    mostrar(campo("pedidoGrid"), false);
    mostrar(campo("pedidoVacio"), true);
    return;
  }
  pintarResumen();
}

function llenarOpciones() {
  campo("pSucursal").insertAdjacentHTML("beforeend", Object.entries(config.sucursales).map(function (s) {
    return `<option value="${escaparHTML(s[0])}">${escaparHTML(s[1])}</option>`;
  }).join(""));
  campo("pRegion").insertAdjacentHTML("beforeend", Object.entries(config.regiones).map(function (r) {
    return `<option value="${escaparHTML(r[0])}">${escaparHTML(r[1])}</option>`;
  }).join(""));
}

function mostrarSesion() {
  const info = campo("sesionInfo");
  if (usuario) {
    campo("pNombre").value = usuario.nombre;
    campo("pCorreo").value = usuario.correo;
    campo("pCorreo").readOnly = true;
    campo("ayudaCorreo").textContent = "Es el correo de tu cuenta. Verás este pedido en «Mis pedidos».";
    info.textContent = "Compras con tu cuenta.";
  } else {
    info.innerHTML = 'Compras como invitado. ¿Tienes cuenta? <a href="catalogo.html?entrar=pedido">Inicia sesión</a>.';
  }
}

/* Mensaje al volver de "Continuar con Google" (si se inició sesión desde aquí) */
function revisarVueltaDeGoogle() {
  const url = new URL(location.href);
  const resultado = url.searchParams.get("google");
  if (!resultado) return;
  url.searchParams.delete("google");
  history.replaceState(null, "", url);
  if (resultado === "ok" || resultado === "nuevo") avisar("Sesión iniciada con Google.", "exito");
  else if (resultado === "cancelado") avisar("Cancelaste el inicio de sesión con Google.", "info");
  else avisar("No se pudo iniciar sesión con Google. Puedes seguir como invitado.", "error");
}

async function iniciar() {
  cargarCarrito();
  revisarVueltaDeGoogle();
  if (carrito.length === 0) {
    mostrar(campo("pedidoGrid"), false);
    mostrar(campo("pedidoVacio"), true);
    return;
  }
  try {
    const [me, conf] = await Promise.all([
      fetch("/api/me").then(function (r) { return r.json(); }),
      fetch("/api/config").then(function (r) { return r.json(); }),
    ]);
    usuario = me.invitado ? null : me;
    config = conf;
    llenarOpciones();
    mostrarSesion();
    await recargarCatalogo();
    actualizarOpciones();
  } catch (error) {
    errorPedido.textContent = "No pudimos cargar tu pedido. Revisa tu conexión y recarga la página.";
  }
}

form.addEventListener("change", function (evento) {
  if (evento.target.name === "entrega" || evento.target.name === "documento" || evento.target.id === "pRegion") {
    actualizarOpciones();
  }
});
campo("pRut").addEventListener("blur", revisarRut);
campo("pRut").addEventListener("input", function () { campo("pRut").setCustomValidity(""); });

iniciar();
