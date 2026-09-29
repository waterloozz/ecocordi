/* ============================================================
   ECOCORDI - Piezas de interfaz compartidas (tienda y admin)
   Reemplazan a alert() y confirm(), que bloquean la página y no se
   pueden diseñar:
     avisar("texto", "exito")          → aviso que desaparece solo
     await confirmar({ ... })          → diálogo propio, devuelve true/false
   Se carga ANTES que app.js / admin.js.
   ============================================================ */

/* -------- AVISOS (toasts) -------- */
const contenedorAvisos = document.createElement("div");
contenedorAvisos.className = "avisos";
document.body.appendChild(contenedorAvisos);

/* tipo: "info" | "exito" | "error". Los errores duran más y se anuncian
   de inmediato a los lectores de pantalla (role="alert"). */
function avisar(texto, tipo, duracion) {
  tipo = tipo || "info";
  const aviso = document.createElement("div");
  aviso.className = "aviso aviso--" + tipo;
  aviso.setAttribute("role", tipo === "error" ? "alert" : "status");

  // textContent (no innerHTML): el texto puede traer datos del servidor
  const mensaje = document.createElement("p");
  mensaje.className = "aviso__texto";
  mensaje.textContent = texto;

  const cerrar = document.createElement("button");
  cerrar.className = "aviso__cerrar";
  cerrar.type = "button";
  cerrar.setAttribute("aria-label", "Cerrar aviso");
  cerrar.textContent = "×";

  aviso.append(mensaje, cerrar);
  contenedorAvisos.appendChild(aviso);

  function quitar() {
    aviso.classList.add("aviso--saliendo");
    // Esperamos la animación de salida (si hay movimiento reducido es casi 0)
    setTimeout(function () { aviso.remove(); }, 200);
  }
  cerrar.addEventListener("click", quitar);
  setTimeout(quitar, duracion || (tipo === "error" ? 7000 : 4500));
  return aviso;
}

/* -------- DIÁLOGO DE CONFIRMACIÓN --------
   Usa <dialog> del navegador: atrapa el foco del teclado, se cierra con
   Esc y oscurece el fondo. Devuelve una promesa: true si la persona
   confirma, false si cancela.
     const ok = await confirmar({ titulo, mensaje, textoConfirmar, peligro }); */
const dialogo = document.createElement("dialog");
dialogo.className = "dialogo";
dialogo.setAttribute("aria-labelledby", "dialogoTitulo");
dialogo.setAttribute("aria-describedby", "dialogoMensaje");
dialogo.innerHTML = `
  <h2 class="dialogo__titulo" id="dialogoTitulo"></h2>
  <p class="dialogo__mensaje" id="dialogoMensaje"></p>
  <div class="dialogo__acciones">
    <button type="button" class="boton boton--secundario" data-respuesta="no">Cancelar</button>
    <button type="button" class="boton boton--principal" data-respuesta="si">Confirmar</button>
  </div>
`;
document.body.appendChild(dialogo);

let resolverDialogo = null;

function confirmar(opciones) {
  const botonSi = dialogo.querySelector("[data-respuesta='si']");
  dialogo.querySelector("#dialogoTitulo").textContent = opciones.titulo || "¿Estás seguro?";
  dialogo.querySelector("#dialogoMensaje").textContent = opciones.mensaje || "";
  botonSi.textContent = opciones.textoConfirmar || "Confirmar";
  botonSi.className = "boton " + (opciones.peligro ? "boton--peligro" : "boton--principal");

  dialogo.showModal();
  // Foco en "Cancelar": si alguien aprieta Enter sin leer, no se borra nada
  dialogo.querySelector("[data-respuesta='no']").focus();

  return new Promise(function (resolver) { resolverDialogo = resolver; });
}

function responderDialogo(valor) {
  if (dialogo.open) dialogo.close();
  if (resolverDialogo) resolverDialogo(valor);
  resolverDialogo = null;
}

dialogo.addEventListener("click", function (evento) {
  const boton = evento.target.closest("[data-respuesta]");
  if (boton) responderDialogo(boton.dataset.respuesta === "si");
});
// Esc (o cerrar el diálogo de otra forma) cuenta como "Cancelar"
dialogo.addEventListener("cancel", function (evento) {
  evento.preventDefault();
  responderDialogo(false);
});
