/* ============================================================
   ECOCORDI - Asistente "¿Qué pintura necesito?" en burbuja de chat
   Una burbuja «Asistente» flota abajo a la derecha (portada y catálogo).
   Al tocarla se abre un chat que hace las preguntas una a una; se responde
   tocando botones. La recomendación la hace el SERVIDOR (GET /api/asistente)
   con reglas simples; este archivo solo conversa y muestra el resultado.

   Las respuestas se guardan en sessionStorage: si pasas de la portada al
   catálogo y vuelves a abrir el chat, sigue donde lo dejaste (se borra al
   cerrar la pestaña).

   Cualquier enlace a "#asistente" o botón con data-abrir-asistente abre el chat.

   Usa lo que ya define app.js (se carga antes): escaparHTML, formatearPrecio,
   formatearLitros, agregarAlCarrito, abrirCarrito, catalogoListo,
   carritoComoParametro, htmlCombinacion y explicacionLitros.
   ============================================================ */

/* -------- 1. LAS PREGUNTAS -------- */
// Estas superficies ya dicen si están adentro o afuera: no se pregunta "¿Dónde está?"
const USO_DE_SUPERFICIE = { exterior: "exterior", techo: "exterior", interior: "interior" };

const PREGUNTAS = {
  superficie: {
    mensaje: "¿Qué vas a pintar?",
    ayuda: "Cada superficie necesita su pintura.",
    opciones: [
      { valor: "madera", titulo: "Madera", foto: "img/sup-madera-mini.webp" },
      { valor: "metal", titulo: "Metal", foto: "img/sup-metal-mini.webp" },
      { valor: "exterior", titulo: "Muro exterior", foto: "img/sup-exterior-mini.webp" },
      { valor: "techo", titulo: "Techo", foto: "img/sup-techo-mini.webp" },
      { valor: "interior", titulo: "Interior", foto: "img/sup-interior-mini.webp" },
    ],
  },
  uso: {
    mensaje: "¿Está adentro o afuera?",
    ayuda: "Afuera, la pintura tiene que aguantar el sol, la lluvia y el viento.",
    opciones: [
      { valor: "interior", titulo: "Adentro", detalle: "Dentro de la casa, protegido", icono: "i-sofa" },
      { valor: "exterior", titulo: "Afuera", detalle: "Al aire libre", icono: "i-casa" },
    ],
  },
  condicion: {
    mensaje: "¿Le llega humedad o sol directo?",
    ayuda: "Si no estás seguro, elige «Nada especial».",
    opciones: [
      { valor: "humedad", titulo: "Humedad", detalle: "Baño, cocina o un muro que se moja", icono: "i-gota" },
      { valor: "sol", titulo: "Sol fuerte", detalle: "Le da el sol directo varias horas al día", icono: "i-sol" },
      { valor: "normal", titulo: "Nada especial", detalle: "Un lugar seco y protegido", icono: "i-hoja" },
    ],
  },
  acabado: {
    mensaje: "¿Qué acabado prefieres?",
    ayuda: "El acabado es cuánto brilla la pintura una vez seca.",
    opciones: [
      { valor: "mate", titulo: "Mate", detalle: "Sin brillo. Disimula las imperfecciones del muro.", brillo: 0 },
      { valor: "satinado", titulo: "Satinado", detalle: "Brillo suave. Se limpia con más facilidad.", brillo: 1 },
      { valor: "brillante", titulo: "Brillante", detalle: "Mucho brillo. Se limpia muy fácil, pero resalta las imperfecciones.", brillo: 2 },
      { valor: "no_se", titulo: "No sé", detalle: "Te sugiero el más versátil.", brillo: null },
    ],
  },
  m2: {
    mensaje: "Por último: ¿cuántos m² vas a pintar?",
    ayuda: "Con eso calculo cuántos litros necesitas y qué formatos te convienen.",
  },
};
// Orden de las preguntas
const ORDEN = ["superficie", "uso", "condicion", "acabado", "m2"];
// Medidas típicas para el mini cálculo de m² (la persona puede corregir el total)
const M2_PUERTA = 1.8;
const M2_VENTANA = 1.5;
// Pausa de "escribiendo…" antes de cada pregunta (sin pausa si se pidió reducir movimiento)
const PAUSA_ESCRIBIENDO = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 450;
const CLAVE_GUARDADO = "asistente_ecocordi";

const SALUDO = `<p>¡Hola! Soy el asistente de Pinturas Ecocordi.</p>
  <p>Te hago unas preguntas cortas y te digo qué pintura usar, cuánta necesitas y cuánto cuesta.</p>`;

/* -------- 2. LAS RESPUESTAS --------
   Nunca confiamos en lo guardado: un valor que no está en la lista se descarta
   (y el asistente vuelve a hacer esa pregunta). */
function valoresDe(clave) {
  return PREGUNTAS[clave].opciones.map(function (o) { return o.valor; });
}

/* Preguntas que corresponden según lo ya respondido */
function pasosDe(r) {
  return ORDEN.filter(function (clave) {
    return clave !== "uso" || !USO_DE_SUPERFICIE[r.superficie];
  });
}

/* La primera pregunta sin responder, o "resultado" si ya están todas */
function pasoActual(r) {
  return pasosDe(r).find(function (clave) { return r[clave] === undefined; }) || "resultado";
}

/* Las preguntas ya respondidas, en orden */
function pasosRespondidos(r) {
  return pasosDe(r).filter(function (clave) { return r[clave] !== undefined; });
}

function limpiarRespuestas(datos) {
  const r = {};
  if (!datos || typeof datos !== "object") return r;
  if (valoresDe("superficie").includes(datos.superficie)) r.superficie = datos.superficie;
  if (r.superficie) {
    const uso = USO_DE_SUPERFICIE[r.superficie] || datos.uso;
    if (valoresDe("uso").includes(uso)) r.uso = uso;
  }
  ["condicion", "acabado"].forEach(function (clave) {
    if (valoresDe(clave).includes(datos[clave])) r[clave] = datos[clave];
  });
  if (datos.m2 === "no") {
    r.m2 = "no"; // eligió no calcular
  } else if (typeof datos.m2 === "number" && datos.m2 > 0 && datos.m2 <= 10000) {
    r.m2 = Math.round(datos.m2 * 100) / 100;
  }
  if ([1, 2, 3].includes(datos.manos) && typeof r.m2 === "number") r.manos = datos.manos;
  // Solo vale lo respondido en orden: si falta una respuesta, se borran las que siguen
  let falta = false;
  pasosDe(r).forEach(function (clave) {
    if (falta) delete r[clave];
    else if (r[clave] === undefined) falta = true;
  });
  if (typeof r.m2 !== "number") delete r.manos;
  return r;
}

function leerGuardadas() {
  try {
    return limpiarRespuestas(JSON.parse(sessionStorage.getItem(CLAVE_GUARDADO) || "{}"));
  } catch (error) {
    return {}; // navegador sin almacenamiento (modo privado estricto): se empieza de cero
  }
}

function guardar() {
  try {
    sessionStorage.setItem(CLAVE_GUARDADO, JSON.stringify(respuestas));
  } catch (error) {
    // Sin almacenamiento, el chat funciona igual; solo no se recuerda al cambiar de página
  }
}

let respuestas = leerGuardadas();
let resultadoActual = null; // [recomendado, alternativa1, alternativa2] que se están mostrando
let turno = 0;              // cada cambio de conversación suma 1: una espera vieja no dibuja nada
let iniciado = false;       // la conversación se dibuja la primera vez que se abre
let midiendo = false;       // la zona de respuesta muestra el mini cálculo de m²
let focoAntesDelChat = null;

/* -------- 3. LA BURBUJA Y LA VENTANA DEL CHAT --------
   Se crean desde aquí para no repetir el mismo HTML en cada página. */
const burbuja = document.createElement("button");
burbuja.type = "button";
burbuja.className = "asistente-burbuja";
burbuja.id = "asistenteBurbuja";
burbuja.setAttribute("aria-expanded", "false");
burbuja.setAttribute("aria-controls", "asistenteChat");
burbuja.innerHTML = '<svg class="icono" aria-hidden="true"><use href="#i-asistente"/></svg>Asistente';

const chat = document.createElement("section");
chat.className = "chat";
chat.id = "asistenteChat";
chat.setAttribute("role", "dialog");
chat.setAttribute("aria-labelledby", "chatTitulo");
chat.innerHTML = `
  <header class="chat__cabecera">
    <span class="chat__avatar" aria-hidden="true">E</span>
    <div class="chat__nombre">
      <h2 class="chat__titulo" id="chatTitulo">Asistente Ecocordi</h2>
      <p class="chat__subtitulo">Te ayudo a elegir tu pintura</p>
    </div>
    <button type="button" class="chat__accion" id="chatReiniciar" aria-label="Empezar de nuevo" title="Empezar de nuevo">
      <svg class="icono" aria-hidden="true"><use href="#i-reiniciar"/></svg>
    </button>
    <button type="button" class="chat__accion" id="chatCerrar" aria-label="Cerrar el asistente" title="Cerrar">
      <svg class="icono" aria-hidden="true"><use href="#i-cerrar"/></svg>
    </button>
  </header>
  <div class="chat__mensajes" id="chatMensajes" role="log" aria-label="Conversación con el asistente" tabindex="-1"></div>
  <div class="chat__entrada" id="chatEntrada"></div>`;

document.body.append(burbuja, chat);
const mensajes = document.getElementById("chatMensajes");
const entrada = document.getElementById("chatEntrada");

/* -------- 4. MENSAJES -------- */
function agregarMensaje(de, html, clase) {
  const mensaje = document.createElement("div");
  mensaje.className = "mensaje mensaje--" + de + (clase ? " " + clase : "");
  mensaje.innerHTML = html;
  mensajes.append(mensaje);
  mensajes.scrollTop = mensajes.scrollHeight;
  return mensaje;
}

/* Los tres puntitos mientras el asistente "escribe" (los lectores de pantalla no los leen) */
function mostrarEscribiendo() {
  const puntos = agregarMensaje("bot", '<span class="escribiendo"><span></span><span></span><span></span></span>', "mensaje--escribiendo");
  puntos.setAttribute("aria-hidden", "true");
  return puntos;
}

function esperar(milisegundos) {
  return new Promise(function (listo) { setTimeout(listo, milisegundos); });
}

function htmlPregunta(clave) {
  const pregunta = PREGUNTAS[clave];
  return `<p class="mensaje__titulo">${pregunta.mensaje}</p><p class="mensaje__ayuda">${pregunta.ayuda}</p>`;
}

function formatearNumero(valor) {
  return valor.toLocaleString("es-CL", { maximumFractionDigits: 1 });
}

/* Lo que "dice" la persona al responder: "Madera", "40 m² · 2 manos"... */
function textoRespuesta(clave, r) {
  if (clave === "m2") {
    if (r.m2 === "no") return "Prefiero no calcular ahora";
    return formatearNumero(r.m2) + " m²" + (r.manos ? " · " + r.manos + (r.manos === 1 ? " mano" : " manos") : "");
  }
  const opcion = PREGUNTAS[clave].opciones.find(function (o) { return o.valor === r[clave]; });
  return opcion ? opcion.titulo : "";
}

/* Dibuja toda la conversación de nuevo (al abrir por primera vez, volver atrás
   o empezar de nuevo). Lo ya respondido aparece al instante, sin pausas. */
function dibujarTodo() {
  mensajes.innerHTML = "";
  resultadoActual = null;
  midiendo = false;
  agregarMensaje("bot", SALUDO);
  pasosRespondidos(respuestas).forEach(function (clave) {
    agregarMensaje("bot", htmlPregunta(clave));
    agregarMensaje("yo", escaparHTML(textoRespuesta(clave, respuestas)));
  });
  return continuar(false);
}

/* Muestra lo que sigue: la próxima pregunta o el resultado */
async function continuar(conPausa) {
  const miTurno = ++turno;
  const actual = pasoActual(respuestas);
  entrada.innerHTML = ""; // mientras "escribe", no hay opciones para tocar
  const puntos = conPausa || actual === "resultado" ? mostrarEscribiendo() : null;

  let datos = null;
  if (actual === "resultado") datos = await buscarPintura();
  else if (conPausa) await esperar(PAUSA_ESCRIBIENDO);
  if (miTurno !== turno) return; // la conversación cambió mientras esperábamos
  if (puntos) puntos.remove();

  if (actual === "resultado") {
    mostrarResultado(datos);
  } else {
    agregarMensaje("bot", htmlPregunta(actual));
    dibujarEntrada(actual);
    // Las opciones de abajo achican la conversación: bajamos hasta la última pregunta
    mensajes.scrollTop = mensajes.scrollHeight;
  }
}

/* -------- 5. RESPONDER, VOLVER ATRÁS Y EMPEZAR DE NUEVO -------- */
function responder(clave, valor, extra) {
  // Al cambiar una respuesta, las que venían después podrían ya no servir
  ORDEN.slice(ORDEN.indexOf(clave)).forEach(function (k) { delete respuestas[k]; });
  delete respuestas.manos;
  respuestas[clave] = valor;
  Object.assign(respuestas, extra || {});
  respuestas = limpiarRespuestas(respuestas);
  guardar();
  midiendo = false;
  agregarMensaje("yo", escaparHTML(textoRespuesta(clave, respuestas)));
  // El botón tocado desaparece: el foco espera en la conversación y luego va a las opciones nuevas
  mensajes.focus({ preventScroll: true });
  continuar(true).then(enfocarEntrada);
}

function atras() {
  const respondidos = pasosRespondidos(respuestas);
  const ultimo = respondidos[respondidos.length - 1];
  if (!ultimo) return;
  delete respuestas[ultimo];
  if (ultimo === "m2") delete respuestas.manos;
  if (ultimo === "superficie") delete respuestas.uso; // el uso podía venir de la superficie
  guardar();
  dibujarTodo();
  enfocarEntrada();
}

function empezarDeNuevo() {
  respuestas = {};
  guardar();
  dibujarTodo();
  enfocarEntrada();
}

/* El foco va a lo primero que se puede responder (o a la conversación) */
function enfocarEntrada() {
  if (!chat.classList.contains("abierto")) return;
  const primero = entrada.querySelector("input, button:not([data-atras]), select");
  (primero || mensajes).focus({ preventScroll: true });
}

/* -------- 6. LA ZONA DE RESPUESTA (abajo del chat) -------- */
/* Muestra de brillo para el acabado: un círculo con más o menos reflejo */
function htmlBrillo(brillo, indice) {
  if (brillo === null) {
    return `<svg class="brillo" viewBox="0 0 56 56" aria-hidden="true">
      <circle cx="28" cy="28" r="25" class="brillo__vacio"/>
      <text x="28" y="36" text-anchor="middle" class="brillo__signo">?</text></svg>`;
  }
  const id = "chatBrillo" + indice;
  const reflejo = [0, 0.35, 0.85][brillo];
  const tamano = ["0", "0.55", "0.32"][brillo];
  return `<svg class="brillo" viewBox="0 0 56 56" aria-hidden="true">
    <defs><radialGradient id="${id}" cx="0.36" cy="0.3" r="${tamano}">
      <stop offset="0" stop-color="#FFFFFF" stop-opacity="${reflejo}"/>
      <stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/>
    </radialGradient></defs>
    <circle cx="28" cy="28" r="25" class="brillo__base"/>
    <circle cx="28" cy="28" r="25" fill="url(#${id})"/></svg>`;
}

function htmlOpciones(clave) {
  const pregunta = PREGUNTAS[clave];
  const conDetalle = clave !== "superficie";
  const botones = pregunta.opciones.map(function (o, i) {
    let visual;
    if (o.foto) visual = `<img class="chat__opcion-foto" src="${o.foto}" alt="" width="32" height="32" decoding="async" />`;
    else if (o.brillo !== undefined) visual = `<span class="chat__opcion-icono chat__opcion-icono--brillo">${htmlBrillo(o.brillo, i)}</span>`;
    else visual = `<span class="chat__opcion-icono"><svg class="icono" aria-hidden="true"><use href="#${o.icono}"/></svg></span>`;
    return `
      <button type="button" class="chat__opcion ${conDetalle ? "chat__opcion--detalle" : ""}" data-clave="${clave}" data-valor="${o.valor}">
        ${visual}
        <span class="chat__opcion-texto">
          <span class="chat__opcion-titulo">${o.titulo}</span>
          ${o.detalle ? `<span class="chat__opcion-detalle">${o.detalle}</span>` : ""}
        </span>
      </button>`;
  }).join("");
  return `<div class="chat__opciones ${conDetalle ? "chat__opciones--lista" : ""}" role="group"
    aria-label="${pregunta.mensaje}">${botones}</div>`;
}

function htmlMetros() {
  return `
    <form class="chat__metros" id="chatFormMetros" novalidate>
      <label class="campo">
        <span class="campo__etiqueta">Metros cuadrados</span>
        <input class="campo__control" type="number" id="chatMetros" min="0.1" max="10000" step="any"
               inputmode="decimal" placeholder="Ej: 40" aria-describedby="chatMetrosError" />
      </label>
      <label class="campo">
        <span class="campo__etiqueta">Manos</span>
        <select class="campo__control" id="chatManos">
          <option value="">Recomendadas</option>
          <option value="1">1 mano</option><option value="2">2 manos</option><option value="3">3 manos</option>
        </select>
      </label>
      <button type="submit" class="chat__enviar" aria-label="Enviar">
        <svg class="icono" aria-hidden="true"><use href="#i-flecha"/></svg>
      </button>
    </form>
    <p class="formulario__error" id="chatMetrosError" role="alert"></p>
    <div class="chat__opciones">
      <button type="button" class="chat__opcion chat__opcion--suave" data-medir>
        <svg class="icono" aria-hidden="true"><use href="#i-regla"/></svg>No sé cuántos m² son</button>
      <button type="button" class="chat__opcion chat__opcion--suave" data-omitir-m2>Prefiero no calcular ahora</button>
    </div>`;
}

/* Mini cálculo: largo × alto × muros − puertas − ventanas */
function htmlMedir() {
  const campo = function (medida, etiqueta, atributos) {
    return `<label class="campo"><span class="campo__etiqueta">${etiqueta}</span>
      <input class="campo__control" type="number" data-medida="${medida}" ${atributos} /></label>`;
  };
  return `
    <p class="chat__nota">Mide un muro con una huincha. Si hay varios muros del mismo tamaño, indica cuántos.</p>
    <div class="chat__medidas">
      ${campo("largo", "Largo (m)", 'min="0" max="200" step="any" inputmode="decimal" placeholder="Ej: 4"')}
      ${campo("alto", "Alto (m)", 'min="0" max="50" step="any" inputmode="decimal" placeholder="Ej: 2,4"')}
      ${campo("muros", "Muros", 'min="1" max="50" step="1" inputmode="numeric" value="1"')}
      ${campo("puertas", "Puertas", 'min="0" max="50" step="1" inputmode="numeric" value="0"')}
      ${campo("ventanas", "Ventanas", 'min="0" max="50" step="1" inputmode="numeric" value="0"')}
    </div>
    <p class="chat__total" aria-live="polite">Son unos <strong id="chatMiniTotal">0 m²</strong></p>
    <p class="chat__nota chat__nota--chica">Restamos ${formatearNumero(M2_PUERTA)} m² por puerta y ${formatearNumero(M2_VENTANA)} m²
      por ventana (medidas típicas).</p>
    <div class="chat__botones">
      <button type="button" class="boton boton--principal" id="chatUsarMedida" disabled>Usar esta medida</button>
      <button type="button" class="boton boton--secundario" data-volver-metros>Volver</button>
    </div>`;
}

function calcularMiniMedida() {
  const medida = function (nombre) {
    const valor = Number(entrada.querySelector(`[data-medida="${nombre}"]`).value.replace(",", "."));
    return Number.isFinite(valor) && valor > 0 ? valor : 0;
  };
  const bruto = medida("largo") * medida("alto") * Math.max(1, Math.round(medida("muros")) || 1);
  const total = Math.max(0, bruto - Math.round(medida("puertas")) * M2_PUERTA - Math.round(medida("ventanas")) * M2_VENTANA);
  return Math.min(10000, Math.round(total * 10) / 10);
}

/* paso: una pregunta, "resultado" o "error" */
function dibujarEntrada(paso, datos) {
  let html;
  if (paso === "m2") {
    html = midiendo ? htmlMedir() : htmlMetros();
  } else if (paso === "error") {
    html = `<div class="chat__opciones"><button type="button" class="chat__opcion" data-reintentar>Reintentar</button></div>`;
  } else if (paso === "resultado") {
    const puedeCalcular = datos && datos.recomendado && typeof respuestas.m2 !== "number";
    html = `<div class="chat__opciones">
      ${puedeCalcular ? `<button type="button" class="chat__opcion" data-ir-m2>
        <svg class="icono" aria-hidden="true"><use href="#i-regla"/></svg>Calcular litros</button>` : ""}
      <button type="button" class="chat__opcion chat__opcion--suave" data-reiniciar>
        <svg class="icono" aria-hidden="true"><use href="#i-reiniciar"/></svg>Empezar de nuevo</button>
    </div>`;
  } else {
    html = htmlOpciones(paso);
  }
  if (pasosRespondidos(respuestas).length) {
    html += `<button type="button" class="chat__atras" data-atras>
      <svg class="icono" aria-hidden="true"><use href="#i-atras"/></svg>Cambiar mi última respuesta</button>`;
  }
  entrada.innerHTML = html;
  entrada.classList.toggle("chat__entrada--medir", paso === "m2" && midiendo);
}

/* -------- 7. EL RESULTADO -------- */
async function buscarPintura() {
  const r = respuestas;
  const params = new URLSearchParams({ superficie: r.superficie, uso: r.uso });
  ["condicion", "acabado", "manos"].forEach(function (clave) {
    if (r[clave] !== undefined) params.set(clave, r[clave]);
  });
  if (typeof r.m2 === "number") params.set("m2", r.m2);
  try {
    await catalogoListo;
    // Lo que ya está en el carrito no se vuelve a ofrecer
    const enCarrito = carritoComoParametro();
    if (enCarrito) params.set("carrito", enCarrito);
    const respuesta = await fetch("/api/asistente?" + params);
    const datos = await respuesta.json();
    if (!respuesta.ok) throw new Error(datos.error);
    return datos;
  } catch (error) {
    return null;
  }
}

function mostrarResultado(datos) {
  if (!datos) {
    agregarMensaje("bot", `<p class="mensaje__titulo">No pude buscar tu pintura.</p>
      <p class="mensaje__ayuda">Revisa tu conexión e inténtalo de nuevo.</p>`);
    dibujarEntrada("error");
    return;
  }
  if (!datos.recomendado) {
    agregarMensaje("bot", htmlSinResultado(datos));
    dibujarEntrada("resultado", datos);
    return;
  }
  resultadoActual = [datos.recomendado].concat(datos.alternativas);
  // El comienzo del resultado queda arriba de la ventana (la tarjeta es larga)
  const primero = agregarMensaje("bot", `<p class="mensaje__titulo">¡Listo! Esta es la que te recomiendo:</p>${htmlResumen(respuestas)}`);
  if (datos.aviso) agregarMensaje("bot", `<p>${escaparHTML(datos.aviso)}</p>`, "mensaje--aviso");
  agregarMensaje("bot", htmlSugerencia(datos.recomendado, 0), "mensaje--tarjeta");
  if (datos.alternativas.length) {
    agregarMensaje("bot", "<p>También te pueden servir:</p>");
    datos.alternativas.forEach(function (p, i) {
      agregarMensaje("bot", htmlSugerencia(p, i + 1), "mensaje--tarjeta");
    });
  }
  mensajes.scrollTop = primero.offsetTop - 12;
  dibujarEntrada("resultado", datos);
}

/* "Madera · Afuera · Sol fuerte · Mate · 40 m²" */
function htmlResumen(r) {
  const partes = ["superficie", "uso", "condicion", "acabado"].map(function (clave) {
    return textoRespuesta(clave, r);
  }).filter(Boolean);
  if (typeof r.m2 === "number") partes.push(textoRespuesta("m2", r));
  return `<ul class="mensaje__resumen" aria-label="Tus respuestas">${partes.map(function (p) {
    return `<li>${escaparHTML(p)}</li>`;
  }).join("")}</ul>`;
}

function htmlCalculo(p, indice) {
  const nombre = escaparHTML(p.nombre);
  if (!p.calculo) {
    if (indice !== 0) return "";
    return `<div class="sugerencia__calculo"><p>¿Cuántos litros necesitas? Dime los m² y te digo qué formatos comprar.</p>
      <button type="button" class="boton boton--secundario" data-ir-m2>Calcular litros</button></div>`;
  }
  const c = p.calculo;
  if (c.litros === null) {
    return `<div class="sugerencia__calculo"><p>Todavía no tenemos el rendimiento de <strong>${nombre}</strong>,
      así que no puedo calcular los litros. Escríbenos y te ayudamos.</p></div>`;
  }
  let html = `<p class="calculadora__litros">Necesitas unos <strong>${formatearLitros(c.litros)}</strong>
    <span>(${explicacionLitros(c)})</span></p>`;
  if (!c.combinacion) {
    html += `<p>No tenemos stock suficiente de <strong>${nombre}</strong> para cubrir esa cantidad ahora.
      Escríbenos y lo coordinamos.</p>`;
  } else {
    html += htmlCombinacion(c.combinacion, p.nombre) + `
      <button type="button" class="boton boton--principal boton--ancho" data-agregar="${indice}">
        <svg class="icono" aria-hidden="true"><use href="#i-tarro"/></svg>${indice === 0 ? "Agregar todo al carrito" : "Agregar al carrito"}
      </button>`;
  }
  return `<div class="sugerencia__calculo">${html}</div>`;
}

function htmlSugerencia(p, indice) {
  const principal = indice === 0;
  const motivos = `<ul class="sugerencia__motivos">${p.motivos.map(function (m) {
    return `<li><svg class="icono" aria-hidden="true"><use href="#i-check"/></svg><span>${escaparHTML(m)}</span></li>`;
  }).join("")}</ul>`;
  return `
    <article class="sugerencia ${principal ? "sugerencia--principal" : "sugerencia--alternativa"}">
      <div class="sugerencia__foto">
        <img src="${escaparHTML(p.imagen)}" alt="" width="800" height="600" loading="lazy" decoding="async" />
        ${principal ? '<span class="imagen-referencial">Imagen referencial</span>' : ""}
      </div>
      <div class="sugerencia__cuerpo">
        ${principal ? '<p class="sugerencia__etiqueta">Te recomendamos</p>' : ""}
        <h3 class="sugerencia__nombre">${escaparHTML(p.nombre)}</h3>
        <p class="sugerencia__precio">Desde ${formatearPrecio(p.precio_litro)} por litro</p>
        ${principal ? `<p class="solo-lector">Por qué te la recomendamos:</p>${motivos}`
          : `<details class="sugerencia__porque"><summary>Por qué esta</summary>${motivos}</details>`}
        ${htmlCalculo(p, indice)}
        ${p.ficha_demo ? `<p class="sugerencia__demo">Ficha técnica de ejemplo: Ecocordi todavía debe confirmar
          el rendimiento y las resistencias de esta pintura.</p>` : ""}
        <a class="enlace-flecha sugerencia__catalogo" href="catalogo.html?${new URLSearchParams({ q: p.nombre.slice(0, 60) })}">
          Ver en el catálogo <svg class="icono" aria-hidden="true"><use href="#i-flecha"/></svg></a>
      </div>
    </article>`;
}

function htmlSinResultado(datos) {
  const whatsapp = datos.whatsapp && /^\d{8,15}$/.test(datos.whatsapp)
    ? `<a class="boton boton--principal" target="_blank" rel="noopener" href="https://wa.me/${datos.whatsapp}?${new URLSearchParams({
        text: "Hola, Pinturas Ecocordi. Usé el asistente y no encontré una pintura para lo que quiero pintar. ¿Me ayudan?",
      })}"><svg class="icono" aria-hidden="true"><use href="#i-chat"/></svg>Escríbenos por WhatsApp</a>`
    : `<a class="boton boton--principal" href="mailto:pinturas@ecocordi.cl">
        <svg class="icono" aria-hidden="true"><use href="#i-correo"/></svg>Escríbenos</a>`;
  return `
    <p class="mensaje__titulo">Aún no tenemos esa pintura.</p>
    <p class="mensaje__ayuda">${escaparHTML(datos.mensaje)}</p>
    <p class="mensaje__acciones">
      ${whatsapp}
      <a class="boton boton--secundario" href="index.html#sucursales">
        <svg class="icono" aria-hidden="true"><use href="#i-pin"/></svg>Ver sucursales</a>
    </p>`;
}

/* -------- 8. ABRIR Y CERRAR -------- */
function abrirAsistente() {
  if (!chat.classList.contains("abierto")) focoAntesDelChat = document.activeElement;
  chat.classList.add("abierto");
  burbuja.classList.add("oculta");
  burbuja.setAttribute("aria-expanded", "true");
  document.documentElement.classList.add("chat-abierto");
  if (!iniciado) {
    iniciado = true;
    dibujarTodo();
  }
  enfocarEntrada();
}

function cerrarAsistente() {
  if (!chat.classList.contains("abierto")) return;
  chat.classList.remove("abierto");
  burbuja.classList.remove("oculta");
  burbuja.setAttribute("aria-expanded", "false");
  document.documentElement.classList.remove("chat-abierto");
  // El foco vuelve a donde estaba (o a la burbuja)
  const volver = focoAntesDelChat && focoAntesDelChat.isConnected && focoAntesDelChat !== document.body
    ? focoAntesDelChat : burbuja;
  volver.focus();
}

burbuja.addEventListener("click", abrirAsistente);
document.getElementById("chatCerrar").addEventListener("click", cerrarAsistente);
document.getElementById("chatReiniciar").addEventListener("click", empezarDeNuevo);

// Escape cierra el chat (solo si el foco está adentro: así no choca con el carrito)
chat.addEventListener("keydown", function (evento) {
  if (evento.key === "Escape") cerrarAsistente();
});

// Los accesos de la página: menú "Asistente", "¿No sabes qué pintura usar?"...
document.addEventListener("click", function (evento) {
  const acceso = evento.target.closest('a[href="#asistente"], [data-abrir-asistente]');
  if (!acceso) return;
  evento.preventDefault();
  abrirAsistente();
});

/* -------- 9. CLICS Y FORMULARIOS DENTRO DEL CHAT (delegación de eventos) -------- */
chat.addEventListener("click", async function (evento) {
  const objetivo = evento.target;
  const opcion = objetivo.closest("[data-clave]");
  if (opcion) {
    responder(opcion.dataset.clave, opcion.dataset.valor);
    return;
  }
  if (objetivo.closest("[data-omitir-m2]")) { responder("m2", "no"); return; }
  if (objetivo.closest("[data-atras]")) { atras(); return; }
  if (objetivo.closest("[data-reiniciar]")) { empezarDeNuevo(); return; }
  if (objetivo.closest("[data-reintentar]")) { dibujarTodo().then(enfocarEntrada); return; }
  if (objetivo.closest("[data-medir]") || objetivo.closest("[data-volver-metros]")) {
    midiendo = !!objetivo.closest("[data-medir]");
    dibujarEntrada("m2");
    mensajes.scrollTop = mensajes.scrollHeight;
    enfocarEntrada();
    return;
  }
  if (objetivo.closest("#chatUsarMedida")) {
    responder("m2", calcularMiniMedida());
    return;
  }
  if (objetivo.closest("[data-ir-m2]")) {
    delete respuestas.m2;
    delete respuestas.manos;
    guardar();
    dibujarTodo();
    enfocarEntrada();
    return;
  }
  const agregar = objetivo.closest("[data-agregar]");
  if (agregar && resultadoActual) {
    const sugerida = resultadoActual[Number(agregar.dataset.agregar)];
    if (!sugerida || !sugerida.calculo || !sugerida.calculo.combinacion) return;
    await catalogoListo;
    sugerida.calculo.combinacion.items.forEach(function (item) {
      agregarAlCarrito(item.formato_id, item.cantidad, false);
    });
    agregar.disabled = true;
    agregar.innerHTML = '<svg class="icono" aria-hidden="true"><use href="#i-check"/></svg>Agregado al carrito';
    abrirCarrito();
  }
});

// El mini cálculo se actualiza mientras se escribe
chat.addEventListener("input", function (evento) {
  if (!evento.target.matches("[data-medida]")) return;
  const total = calcularMiniMedida();
  document.getElementById("chatMiniTotal").textContent = formatearNumero(total) + " m²";
  document.getElementById("chatUsarMedida").disabled = !(total > 0);
});

chat.addEventListener("submit", function (evento) {
  if (evento.target.id !== "chatFormMetros") return;
  evento.preventDefault();
  const campo = document.getElementById("chatMetros");
  const error = document.getElementById("chatMetrosError");
  const metros = Math.round(Number(campo.value.replace(",", ".")) * 100) / 100;
  if (!(metros > 0) || metros > 10000) {
    error.textContent = "Escribe un número mayor que 0 y hasta 10.000. Si no lo sabes, toca «No sé cuántos m² son».";
    campo.setAttribute("aria-invalid", "true");
    campo.focus();
    return;
  }
  const manos = document.getElementById("chatManos").value;
  responder("m2", metros, manos ? { manos: Number(manos) } : null);
});

/* -------- 10. ARRANQUE --------
   Un enlace desde otra página (index.html#asistente) abre el chat directo. */
if (location.hash === "#asistente") {
  history.replaceState(null, "", location.pathname + location.search);
  abrirAsistente();
}
