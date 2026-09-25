/* ============================================================
   ECOCORDI - Asistente "¿Qué pintura necesito?" (asistente.html)
   Una pregunta por pantalla. Cada respuesta se guarda en la dirección de la
   página (asistente.html?superficie=madera&uso=exterior&condicion=sol&acabado=mate&m2=40):
     - el enlace se puede compartir o recargar sin perder nada,
     - el botón "atrás" del navegador vuelve a la pregunta anterior.
   La recomendación la hace el SERVIDOR (GET /api/asistente) con reglas
   simples; este archivo solo pregunta y muestra el resultado.

   Usa lo que ya define app.js (se carga antes): escaparHTML, formatearPrecio,
   formatearLitros, agregarAlCarrito, abrirCarrito, catalogoListo, productos,
   carritoComoParametro, htmlCombinacion, explicacionLitros y NOTA_FICHA_DEMO.
   ============================================================ */

/* -------- 1. LAS PREGUNTAS -------- */
// Estas superficies ya dicen si están adentro o afuera: no se pregunta "¿Dónde está?"
const USO_DE_SUPERFICIE = { exterior: "exterior", techo: "exterior", interior: "interior" };

const PREGUNTAS = {
  superficie: {
    titulo: "¿Qué vas a pintar?",
    ayuda: "Cada superficie necesita su pintura.",
    opciones: [
      { valor: "madera", titulo: "Madera", detalle: "Puertas, muebles y terrazas", foto: "img/sup-madera.webp" },
      { valor: "metal", titulo: "Metal", detalle: "Rejas, portones y estructuras", foto: "img/sup-metal.webp" },
      { valor: "exterior", titulo: "Muro exterior", detalle: "Fachadas y muros de afuera", foto: "img/sup-exterior.webp" },
      { valor: "techo", titulo: "Techo", detalle: "Cubiertas y techumbres", foto: "img/sup-techo.webp" },
      { valor: "interior", titulo: "Interior", detalle: "Muros y cielos de tu casa", foto: "img/sup-interior.webp" },
    ],
  },
  uso: {
    titulo: "¿Dónde está?",
    ayuda: "Afuera, la pintura tiene que aguantar el sol, la lluvia y el viento.",
    opciones: [
      { valor: "interior", titulo: "Adentro", detalle: "Dentro de la casa, protegido", icono: "i-sofa" },
      { valor: "exterior", titulo: "Afuera", detalle: "Al aire libre", icono: "i-casa" },
    ],
  },
  condicion: {
    titulo: "¿Le llega humedad o sol directo?",
    ayuda: "Si no estás seguro, elige «Nada especial».",
    opciones: [
      { valor: "humedad", titulo: "Humedad", detalle: "Baño, cocina o un muro que se moja", icono: "i-gota" },
      { valor: "sol", titulo: "Sol fuerte", detalle: "Le da el sol directo varias horas al día", icono: "i-sol" },
      { valor: "normal", titulo: "Nada especial", detalle: "Un lugar seco y protegido", icono: "i-hoja" },
    ],
  },
  acabado: {
    titulo: "¿Qué acabado prefieres?",
    ayuda: "El acabado es cuánto brilla la pintura una vez seca.",
    opciones: [
      { valor: "mate", titulo: "Mate", detalle: "Sin brillo. Disimula las imperfecciones del muro.", brillo: 0 },
      { valor: "satinado", titulo: "Satinado", detalle: "Brillo suave. Se limpia con más facilidad.", brillo: 1 },
      { valor: "brillante", titulo: "Brillante", detalle: "Mucho brillo. Se limpia muy fácil, pero resalta las imperfecciones.", brillo: 2 },
      { valor: "no_se", titulo: "No sé", detalle: "Te sugerimos el más versátil.", brillo: null },
    ],
  },
};
// Orden de las preguntas (y de los parámetros en la dirección)
const ORDEN = ["superficie", "uso", "condicion", "acabado", "m2"];
const PARAMETROS = ORDEN.concat(["manos", "producto", "color"]);
// Para "Ver en el visualizador": qué ambiente y qué zona corresponden a cada superficie
const AMBIENTE_DE = {
  interior: ["living", "muro"], exterior: ["fachada", "fachada"], techo: ["fachada", "fachada"],
  madera: ["terraza", "baranda"], metal: ["terraza", "reja"],
};
// Medidas típicas para el mini cálculo de m² (la persona puede corregir el total)
const M2_PUERTA = 1.8;
const M2_VENTANA = 1.5;

/* -------- 2. REFERENCIAS -------- */
const pantalla = document.getElementById("asistentePantalla");
const barraProgreso = document.getElementById("asistenteProgreso");
const textoPaso = document.getElementById("asistentePaso");
const botonAtras = document.getElementById("asistenteAtras");
const enlaceReiniciar = document.getElementById("asistenteReiniciar");

let resultadoActual = null; // [recomendado, alternativa1, alternativa2] que se están mostrando
let dibujoActual = 0;       // evita que una respuesta lenta del servidor pise una pantalla más nueva

/* -------- 3. LEER LAS RESPUESTAS DE LA DIRECCIÓN --------
   Nunca confiamos en la dirección: un valor que no está en la lista se ignora
   (y el asistente vuelve a hacer esa pregunta). */
function valoresDe(clave) {
  return PREGUNTAS[clave].opciones.map(function (o) { return o.valor; });
}

function leerRespuestas() {
  const url = new URLSearchParams(location.search);
  const r = {};
  if (valoresDe("superficie").includes(url.get("superficie"))) r.superficie = url.get("superficie");
  if (r.superficie) {
    const uso = USO_DE_SUPERFICIE[r.superficie] || url.get("uso");
    if (valoresDe("uso").includes(uso)) r.uso = uso;
  }
  ["condicion", "acabado"].forEach(function (clave) {
    if (valoresDe(clave).includes(url.get(clave))) r[clave] = url.get(clave);
  });
  const m2 = url.get("m2");
  if (m2 === "no") {
    r.m2 = "no"; // eligió no calcular
  } else if (/^\d{1,5}([.,]\d{1,2})?$/.test(m2 || "")) {
    const numero = Number(m2.replace(",", "."));
    if (numero > 0 && numero <= 10000) r.m2 = numero;
  }
  if (/^[1-5]$/.test(url.get("manos") || "")) r.manos = Number(url.get("manos"));
  if (/^\d{1,9}$/.test(url.get("producto") || "")) r.producto = Number(url.get("producto"));
  // Color elegido en el visualizador: se usa al agregar al carrito
  if (/^\d{1,9}$/.test(url.get("color") || "")) r.color = Number(url.get("color"));
  return r;
}

/* Preguntas que corresponden según lo ya respondido */
function pasosDe(r) {
  return ORDEN.filter(function (clave) {
    if (clave === "uso") return !USO_DE_SUPERFICIE[r.superficie];
    // Si viene con una pintura ya elegida (desde el visualizador), solo falta la medida
    if (clave === "condicion" || clave === "acabado") return r.producto === undefined;
    return true;
  });
}

/* La primera pregunta sin responder, o "resultado" si ya están todas */
function pasoActual(r) {
  return pasosDe(r).find(function (clave) { return r[clave] === undefined; }) || "resultado";
}

/* Escribe las respuestas en la dirección, siempre en el mismo orden */
function urlCon(respuestas) {
  const params = new URLSearchParams();
  PARAMETROS.forEach(function (clave) {
    if (respuestas[clave] !== undefined) params.set(clave, respuestas[clave]);
  });
  // "uso" no hace falta si la superficie ya lo dice
  if (USO_DE_SUPERFICIE[respuestas.superficie]) params.delete("uso");
  const texto = params.toString();
  return location.pathname + (texto ? "?" + texto : "");
}

/* Guarda una respuesta y borra las que venían después (podrían ya no servir) */
function responder(clave, valor, extra) {
  const r = leerRespuestas();
  ORDEN.slice(ORDEN.indexOf(clave)).forEach(function (k) { delete r[k]; });
  delete r.manos;
  r[clave] = valor;
  Object.assign(r, extra || {});
  // Un paso nuevo en el historial: el botón "atrás" del navegador vuelve aquí
  history.pushState({ asistente: true }, "", urlCon(r));
  dibujar(true);
}

/* -------- 4. DIBUJAR LA PANTALLA ACTUAL -------- */
function dibujar(enfocar) {
  const r = leerRespuestas();
  const pasos = pasosDe(r);
  const actual = pasoActual(r);
  const numero = actual === "resultado" ? pasos.length : pasos.indexOf(actual) + 1;

  barraProgreso.max = pasos.length;
  barraProgreso.value = numero;
  textoPaso.textContent = actual === "resultado" ? "Tu resultado" : `Pregunta ${numero} de ${pasos.length}`;
  botonAtras.classList.toggle("oculto", numero === 1 && actual !== "resultado");
  enlaceReiniciar.classList.toggle("oculto", Object.keys(r).length === 0);

  dibujoActual++;
  resultadoActual = null;
  if (actual === "resultado") {
    dibujarResultado(r, dibujoActual, enfocar);
  } else {
    pantalla.innerHTML = (actual === "m2" ? htmlMetros() : htmlPregunta(actual)) + htmlProductoElegido(r);
    mostrarProductoElegido(r);
    if (enfocar) enfocarTitulo();
  }
}

/* Al cambiar de pantalla, el foco va al título de la pregunta: así quien usa
   teclado o lector de pantalla sabe que cambió (y sigue con Tab desde ahí). */
function enfocarTitulo() {
  const titulo = document.getElementById("asistentePregunta");
  if (!titulo) return;
  titulo.focus({ preventScroll: true });
  const arriba = pantalla.closest(".asistente").getBoundingClientRect().top + window.scrollY;
  if (window.scrollY > arriba) window.scrollTo({ top: arriba });
}

/* Muestra de brillo para el acabado: un círculo con más o menos reflejo */
function htmlBrillo(brillo, indice) {
  if (brillo === null) {
    return `<svg class="brillo" viewBox="0 0 56 56" aria-hidden="true">
      <circle cx="28" cy="28" r="25" class="brillo__vacio"/>
      <text x="28" y="36" text-anchor="middle" class="brillo__signo">?</text></svg>`;
  }
  const id = "brillo" + indice;
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

function htmlPregunta(clave) {
  const pregunta = PREGUNTAS[clave];
  const opciones = pregunta.opciones.map(function (o, i) {
    let visual;
    if (o.foto) visual = `<img class="eleccion__foto" src="${o.foto}" alt="" width="800" height="1000" decoding="async" />`;
    else if (o.brillo !== undefined) visual = `<span class="eleccion__icono eleccion__icono--brillo">${htmlBrillo(o.brillo, i)}</span>`;
    else visual = `<span class="eleccion__icono"><svg class="icono" aria-hidden="true"><use href="#${o.icono}"/></svg></span>`;
    return `
      <button type="button" class="eleccion ${o.foto ? "eleccion--foto" : ""}" data-clave="${clave}" data-valor="${o.valor}">
        ${visual}
        <span class="eleccion__texto">
          <span class="eleccion__titulo">${o.titulo}</span>
          <span class="eleccion__detalle">${o.detalle}</span>
        </span>
      </button>`;
  }).join("");
  return `
    <h2 class="asistente__pregunta" id="asistentePregunta" tabindex="-1">${pregunta.titulo}</h2>
    <p class="asistente__ayuda">${pregunta.ayuda}</p>
    <div class="elecciones elecciones--${clave}" role="group" aria-labelledby="asistentePregunta">${opciones}</div>`;
}

function htmlMetros() {
  return `
    <h2 class="asistente__pregunta" id="asistentePregunta" tabindex="-1">¿Cuántos m² vas a pintar?</h2>
    <p class="asistente__ayuda">Con eso calculamos cuántos litros necesitas y qué formatos te convienen.</p>
    <form class="metros" id="formMetros" novalidate>
      <div class="metros__campos">
        <label class="campo">
          <span class="campo__etiqueta">Metros cuadrados</span>
          <input class="campo__control metros__numero" type="number" id="asistMetros" min="0.1" max="10000" step="any"
                 inputmode="decimal" placeholder="Ej: 40" aria-describedby="metrosError" />
        </label>
        <label class="campo">
          <span class="campo__etiqueta">Manos de pintura</span>
          <select class="campo__control" id="asistManos">
            <option value="">Las recomendadas</option>
            <option value="1">1 mano</option><option value="2">2 manos</option><option value="3">3 manos</option>
          </select>
        </label>
      </div>
      <p class="formulario__error" id="metrosError" role="alert"></p>
      <button type="submit" class="boton boton--principal metros__enviar">
        Ver mi pintura <svg class="icono" aria-hidden="true"><use href="#i-flecha"/></svg>
      </button>
    </form>

    <details class="mini-calculo" id="miniCalculo">
      <summary class="mini-calculo__abrir">
        <svg class="icono" aria-hidden="true"><use href="#i-regla"/></svg>No sé cuántos m² son
      </summary>
      <div class="mini-calculo__cuerpo">
        <p class="mini-calculo__texto">Mide un muro con una huincha. Si hay varios muros del mismo tamaño, indica cuántos.</p>
        <div class="mini-calculo__campos">
          <label class="campo"><span class="campo__etiqueta">Largo (m)</span>
            <input class="campo__control" type="number" data-medida="largo" min="0" max="200" step="any" inputmode="decimal" placeholder="Ej: 4" /></label>
          <label class="campo"><span class="campo__etiqueta">Alto (m)</span>
            <input class="campo__control" type="number" data-medida="alto" min="0" max="50" step="any" inputmode="decimal" placeholder="Ej: 2,4" /></label>
          <label class="campo"><span class="campo__etiqueta">Cantidad de muros</span>
            <input class="campo__control" type="number" data-medida="muros" min="1" max="50" step="1" inputmode="numeric" value="1" /></label>
          <label class="campo"><span class="campo__etiqueta">Puertas</span>
            <input class="campo__control" type="number" data-medida="puertas" min="0" max="50" step="1" inputmode="numeric" value="0" /></label>
          <label class="campo"><span class="campo__etiqueta">Ventanas</span>
            <input class="campo__control" type="number" data-medida="ventanas" min="0" max="50" step="1" inputmode="numeric" value="0" /></label>
        </div>
        <p class="mini-calculo__resultado" aria-live="polite">Son unos <strong id="miniTotal">0 m²</strong></p>
        <p class="mini-calculo__nota">Restamos ${formatearNumero(M2_PUERTA)} m² por puerta y ${formatearNumero(M2_VENTANA)} m² por ventana
          (medidas típicas). Si las tuyas son muy distintas, corrige el total.</p>
        <button type="button" class="boton boton--secundario" id="usarMedida" disabled>Usar esta medida</button>
      </div>
    </details>

    <button type="button" class="asistente__omitir" data-omitir-m2>Prefiero no calcular ahora</button>`;
}

function formatearNumero(valor) {
  return valor.toLocaleString("es-CL", { maximumFractionDigits: 1 });
}

/* Mini cálculo: largo × alto × muros − puertas − ventanas */
function calcularMiniMedida() {
  const medida = function (nombre) {
    const valor = Number(pantalla.querySelector(`[data-medida="${nombre}"]`).value.replace(",", "."));
    return Number.isFinite(valor) && valor > 0 ? valor : 0;
  };
  const bruto = medida("largo") * medida("alto") * Math.max(1, Math.round(medida("muros")) || 1);
  const total = Math.max(0, bruto - Math.round(medida("puertas")) * M2_PUERTA - Math.round(medida("ventanas")) * M2_VENTANA);
  return Math.min(10000, Math.round(total * 10) / 10);
}

/* Si viene con una pintura elegida (desde el visualizador), la mostramos */
function htmlProductoElegido(r) {
  if (r.producto === undefined) return "";
  return `<p class="asistente__producto">Calcularemos para <strong id="productoElegido">la pintura que elegiste</strong>.
    <button type="button" class="catalogo__quitar" data-quitar-producto>Prefiero que me recomienden</button></p>`;
}

async function mostrarProductoElegido(r) {
  if (r.producto === undefined) return;
  await catalogoListo;
  const producto = productos.find(function (p) { return p.id === r.producto; });
  const nombre = document.getElementById("productoElegido");
  if (producto && nombre) nombre.textContent = producto.nombre; // textContent: sin riesgo de XSS
}

/* -------- 5. EL RESULTADO -------- */
let colorDelVisualizador = null; // { id, nombre, codigo, hex, productos } si viene ?color=

async function cargarColorDelVisualizador(r) {
  if (r.color === undefined) return;
  if (colorDelVisualizador && colorDelVisualizador.id === r.color) return;
  try {
    const datos = await (await fetch("/api/colores")).json();
    colorDelVisualizador = datos.colores.find(function (c) { return c.id === r.color; }) || null;
  } catch (error) {
    colorDelVisualizador = null;
  }
}

/* El enlace al visualizador: el ambiente de esa superficie y, si hay color, pintado */
function enlaceVisualizador(p, r) {
  const destino = AMBIENTE_DE[r.superficie] || ["living", "muro"];
  const params = new URLSearchParams({ modo: "ambiente", ambiente: destino[0] });
  if (colorDelVisualizador && (p.colores || []).includes(colorDelVisualizador.id)) {
    params.set("zonas", destino[1] + ":" + colorDelVisualizador.id);
  }
  params.set("producto", p.id);
  return "visualizador.html?" + params;
}
async function dibujarResultado(r, numeroDibujo, enfocar) {
  pantalla.innerHTML = `<h2 class="asistente__pregunta" id="asistentePregunta" tabindex="-1">Buscando tu pintura…</h2>`;
  if (enfocar) enfocarTitulo();

  const params = new URLSearchParams({ superficie: r.superficie, uso: r.uso });
  ["condicion", "acabado", "manos", "producto"].forEach(function (clave) {
    if (r[clave] !== undefined) params.set(clave, r[clave]);
  });
  if (typeof r.m2 === "number") params.set("m2", r.m2);
  let datos;
  try {
    await Promise.all([catalogoListo, cargarColorDelVisualizador(r)]);
    // Lo que ya está en el carrito no se vuelve a ofrecer
    const enCarrito = carritoComoParametro();
    if (enCarrito) params.set("carrito", enCarrito);
    const respuesta = await fetch("/api/asistente?" + params);
    datos = await respuesta.json();
    if (!respuesta.ok) throw new Error(datos.error);
  } catch (error) {
    if (numeroDibujo !== dibujoActual) return;
    pantalla.innerHTML = `
      <h2 class="asistente__pregunta" id="asistentePregunta" tabindex="-1">No pudimos buscar tu pintura</h2>
      <p class="asistente__ayuda">Revisa tu conexión e inténtalo de nuevo.</p>
      <p class="recomendacion__acciones"><button type="button" class="boton boton--principal" data-reintentar>Reintentar</button></p>`;
    if (enfocar) enfocarTitulo();
    return;
  }
  if (numeroDibujo !== dibujoActual) return; // la persona ya se fue a otra pantalla

  if (!datos.recomendado) {
    pantalla.innerHTML = htmlSinResultado(datos);
  } else {
    resultadoActual = [datos.recomendado].concat(datos.alternativas);
    pantalla.innerHTML = `
      <h2 class="asistente__pregunta" id="asistentePregunta" tabindex="-1">Tu <em>pintura</em></h2>
      ${htmlResumenRespuestas(r)}
      ${datos.aviso ? `<p class="asistente__aviso">${escaparHTML(datos.aviso)}</p>` : ""}
      ${htmlRecomendacion(datos.recomendado, 0, r)}
      ${datos.alternativas.length ? `
        <h2 class="alternativas__titulo">Otras <em>opciones</em></h2>
        <div class="alternativas">${datos.alternativas.map(function (p, i) { return htmlRecomendacion(p, i + 1, r); }).join("")}</div>` : ""}`;
    pintarMuestras(pantalla);
  }
  if (enfocar) enfocarTitulo();
}

/* "Madera · Afuera · Sol fuerte · Mate · 40 m²" */
function htmlResumenRespuestas(r) {
  const partes = ["superficie", "uso", "condicion", "acabado"].map(function (clave) {
    const opcion = r[clave] && PREGUNTAS[clave].opciones.find(function (o) { return o.valor === r[clave]; });
    return opcion ? opcion.titulo : null;
  }).filter(Boolean);
  if (typeof r.m2 === "number") partes.push(formatearNumero(r.m2) + " m²");
  if (r.manos) partes.push(r.manos + (r.manos === 1 ? " mano" : " manos"));
  const color = r.color !== undefined && colorDelVisualizador;
  return `<ul class="asistente__resumen" aria-label="Tus respuestas">${partes.map(function (p) {
    return `<li>${escaparHTML(p)}</li>`;
  }).join("")}${color ? `<li>${htmlColorElegido(color.nombre, color.codigo, color.hex)}</li>` : ""}</ul>`;
}

function htmlCalculo(p, indice) {
  const nombre = escaparHTML(p.nombre);
  if (!p.calculo) {
    if (indice !== 0) return "";
    return `<div class="recomendacion__calculo">
      <p>¿Cuántos litros necesitas? Dinos los m² y te decimos qué formatos comprar.</p>
      <p><button type="button" class="boton boton--secundario" data-ir-m2>Calcular litros</button></p></div>`;
  }
  const c = p.calculo;
  if (c.litros === null) {
    return `<div class="recomendacion__calculo"><p>Todavía no tenemos el rendimiento de <strong>${nombre}</strong>,
      así que no podemos calcular los litros. Escríbenos y te ayudamos.</p></div>`;
  }
  let html = `<p class="calculadora__litros">Necesitas unos <strong>${formatearLitros(c.litros)}</strong>
    <span>(${explicacionLitros(c)})</span></p>`;
  if (!c.combinacion) {
    html += `<p>No tenemos stock suficiente de <strong>${nombre}</strong> para cubrir esa cantidad ahora.
      Escríbenos y lo coordinamos.</p>`;
  } else {
    html += htmlCombinacion(c.combinacion, p.nombre) + `
      <button type="button" class="boton boton--principal ${indice === 0 ? "boton--ancho" : ""}" data-agregar="${indice}">
        <svg class="icono" aria-hidden="true"><use href="#i-tarro"/></svg>${indice === 0 ? "Agregar todo al carrito" : "Agregar al carrito"}
      </button>`;
  }
  return `<div class="recomendacion__calculo">${html}</div>`;
}

function htmlRecomendacion(p, indice, r) {
  const principal = indice === 0;
  const motivos = p.motivos.map(function (m) {
    return `<li><svg class="icono" aria-hidden="true"><use href="#i-check"/></svg><span>${escaparHTML(m)}</span></li>`;
  }).join("");
  return `
    <article class="recomendacion ${principal ? "recomendacion--principal" : "recomendacion--alternativa"}">
      <div class="recomendacion__foto">
        <img src="${escaparHTML(p.imagen)}" alt="" width="800" height="600" loading="lazy" decoding="async" />
        <span class="imagen-referencial">Imagen referencial</span>
      </div>
      <div class="recomendacion__cuerpo">
        ${principal ? '<p class="recomendacion__etiqueta">Te recomendamos</p>' : ""}
        <h3 class="recomendacion__nombre">${escaparHTML(p.nombre)}</h3>
        <p class="recomendacion__precio-litro">Desde ${formatearPrecio(p.precio_litro)} por litro</p>
        <p class="solo-lector">Por qué te la recomendamos:</p>
        <ul class="recomendacion__motivos">${motivos}</ul>
        ${htmlColorDeProducto(p)}
        ${htmlCalculo(p, indice)}
        ${p.ficha_demo ? `<p class="recomendacion__demo">Ficha técnica de ejemplo: Ecocordi todavía debe confirmar
          el rendimiento y las resistencias de esta pintura.</p>` : ""}
        <p class="recomendacion__acciones">
          ${(p.colores || []).length ? `<a class="boton boton--secundario" href="${escaparHTML(enlaceVisualizador(p, r))}">
            <span class="producto__paleta" aria-hidden="true"></span>Ver en el visualizador</a>` : ""}
          <a class="enlace-flecha" href="catalogo.html?${new URLSearchParams({ q: p.nombre.slice(0, 60) })}">
            Ver en el catálogo <svg class="icono" aria-hidden="true"><use href="#i-flecha"/></svg></a>
        </p>
      </div>
    </article>`;
}

/* Si viene un color del visualizador: ¿esta pintura viene en ese color? */
function htmlColorDeProducto(p) {
  const c = colorDelVisualizador;
  if (!c) return "";
  return (p.colores || []).includes(c.id)
    ? `<p class="recomendacion__color">${htmlColorElegido(c.nombre, c.codigo, c.hex)} <span>(se agrega al carrito en este color)</span></p>`
    : `<p class="recomendacion__color recomendacion__color--no">Esta pintura no viene en el color ${escaparHTML(c.nombre)}.</p>`;
}

function htmlSinResultado(datos) {
  const whatsapp = datos.whatsapp && /^\d{8,15}$/.test(datos.whatsapp)
    ? `<a class="boton boton--principal" target="_blank" rel="noopener" href="https://wa.me/${datos.whatsapp}?${new URLSearchParams({
        text: "Hola, Pinturas Ecocordi. Usé el asistente y no encontré una pintura para lo que quiero pintar. ¿Me ayudan?",
      })}"><svg class="icono" aria-hidden="true"><use href="#i-chat"/></svg>Escríbenos por WhatsApp</a>`
    : `<a class="boton boton--principal" href="mailto:pinturas@ecocordi.cl">
        <svg class="icono" aria-hidden="true"><use href="#i-correo"/></svg>Escríbenos</a>`;
  return `
    <h2 class="asistente__pregunta" id="asistentePregunta" tabindex="-1">Aún no tenemos <em>esa pintura</em></h2>
    <p class="asistente__ayuda">${escaparHTML(datos.mensaje)}</p>
    <p class="recomendacion__acciones">
      ${whatsapp}
      <a class="boton boton--secundario" href="index.html#sucursales">
        <svg class="icono" aria-hidden="true"><use href="#i-pin"/></svg>Ver sucursales</a>
    </p>`;
}

/* -------- 6. CLICS Y FORMULARIOS (delegación de eventos) -------- */
pantalla.addEventListener("click", async function (evento) {
  const eleccion = evento.target.closest("[data-clave]");
  if (eleccion) {
    responder(eleccion.dataset.clave, eleccion.dataset.valor);
    return;
  }
  if (evento.target.closest("[data-omitir-m2]")) {
    responder("m2", "no");
    return;
  }
  if (evento.target.closest("[data-reintentar]")) {
    dibujar(true);
    return;
  }
  if (evento.target.closest("[data-ir-m2]") || evento.target.closest("[data-quitar-producto]")) {
    const r = leerRespuestas();
    if (evento.target.closest("[data-quitar-producto]")) delete r.producto;
    else delete r.m2;
    delete r.manos;
    history.pushState({ asistente: true }, "", urlCon(r));
    dibujar(true);
    return;
  }
  if (evento.target.closest("#usarMedida")) {
    const total = calcularMiniMedida();
    const campo = document.getElementById("asistMetros");
    campo.value = total;
    campo.focus();
    return;
  }
  const agregar = evento.target.closest("[data-agregar]");
  if (agregar && resultadoActual) {
    const opcion = resultadoActual[Number(agregar.dataset.agregar)];
    if (!opcion || !opcion.calculo || !opcion.calculo.combinacion) return;
    await catalogoListo;
    // Con el color del visualizador (el servidor revisa que esa pintura venga en ese color)
    let color = null;
    const c = colorDelVisualizador;
    if (c && (opcion.colores || []).includes(c.id)) {
      const respuesta = await fetch("/api/carrito/item", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ formato_id: opcion.calculo.combinacion.items[0].formato_id, color_id: c.id }),
      });
      const datos = await respuesta.json();
      if (!respuesta.ok) {
        avisar(datos.error || "Ese color no está disponible.", "error");
        return;
      }
      color = datos.color;
    }
    opcion.calculo.combinacion.items.forEach(function (item) {
      agregarAlCarrito(item.formato_id, item.cantidad, false, color);
    });
    agregar.disabled = true;
    agregar.innerHTML = '<svg class="icono" aria-hidden="true"><use href="#i-check"/></svg>Agregado al carrito';
    abrirCarrito();
  }
});

// El mini cálculo se actualiza mientras se escribe
pantalla.addEventListener("input", function (evento) {
  if (!evento.target.matches("[data-medida]")) return;
  const total = calcularMiniMedida();
  document.getElementById("miniTotal").textContent = formatearNumero(total) + " m²";
  document.getElementById("usarMedida").disabled = !(total > 0);
});

pantalla.addEventListener("submit", function (evento) {
  if (evento.target.id !== "formMetros") return;
  evento.preventDefault();
  const campo = document.getElementById("asistMetros");
  const error = document.getElementById("metrosError");
  const metros = Math.round(Number(campo.value.replace(",", ".")) * 100) / 100;
  if (!(metros > 0) || metros > 10000) {
    error.textContent = "Escribe los metros cuadrados: un número mayor que 0 y hasta 10.000. Si no lo sabes, usa «No sé cuántos m² son».";
    campo.setAttribute("aria-invalid", "true");
    campo.focus();
    return;
  }
  const manos = document.getElementById("asistManos").value;
  responder("m2", String(metros), manos ? { manos: Number(manos) } : null);
});

/* -------- 7. ATRÁS -------- */
botonAtras.addEventListener("click", function () {
  // Si la pregunta anterior está en el historial, usamos el "atrás" del navegador
  if (history.state && history.state.asistente) {
    history.back();
    return;
  }
  // Llegó con un enlace compartido: quitamos la última respuesta
  const r = leerRespuestas();
  const pasos = pasosDe(r);
  const actual = pasoActual(r);
  const respondidas = actual === "resultado" ? pasos : pasos.slice(0, pasos.indexOf(actual));
  const ultima = respondidas[respondidas.length - 1];
  if (!ultima) return;
  delete r[ultima];
  if (ultima === "m2") delete r.manos;
  history.replaceState({ asistente: false }, "", urlCon(r));
  dibujar(true);
});

// Botones "atrás" y "adelante" del navegador
window.addEventListener("popstate", function () { dibujar(true); });

/* -------- 8. ARRANQUE -------- */
dibujar(false);
