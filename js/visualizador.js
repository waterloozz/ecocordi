/* ============================================================
   ECOCORDI - Visualizador de color (visualizador.html)
   Dos modos:
     A) Ambientes: ilustraciones SVG propias (img/ambientes/*.svg). Cada zona
        que se puede pintar es un <path data-zona="...">. Encima van capas de
        sombra (mix-blend-mode: multiply) y de luz (screen): por eso el color
        nuevo conserva las sombras y no se ve plano.
     B) Tu propia foto: se procesa SOLO aquí, en el navegador, con <canvas>.
        La foto nunca se envía al servidor.
   El estado (ambiente, zonas y colores) se guarda en la dirección de la
   página para poder compartirlo. La foto NUNCA va en la dirección.

   Usa de app.js (se carga antes): escaparHTML, formatearPrecio, productos,
   catalogoListo, agregarAlCarrito, formatoInicial y SUPERFICIES.
   Y de ui.js: avisar y pintarMuestras.
   ============================================================ */

/* -------- 1. DATOS FIJOS -------- */
// Zonas de cada ambiente: qué es (para el asistente) y su nombre visible
const AMBIENTES = {
  living: {
    nombre: "Living", uso: "interior",
    zonas: [
      { id: "muro", nombre: "Muro principal", superficie: "interior" },
      { id: "acento", nombre: "Muro de acento", superficie: "interior" },
      { id: "puerta", nombre: "Puerta", superficie: "madera" },
    ],
  },
  dormitorio: {
    nombre: "Dormitorio", uso: "interior",
    zonas: [
      { id: "acento", nombre: "Muro de acento", superficie: "interior" },
      { id: "muro", nombre: "Muros laterales", superficie: "interior" },
      { id: "puerta", nombre: "Puerta", superficie: "madera" },
    ],
  },
  fachada: {
    nombre: "Fachada", uso: "exterior",
    zonas: [
      { id: "fachada", nombre: "Muro principal", superficie: "exterior" },
      { id: "acento", nombre: "Volumen de acento", superficie: "exterior" },
      { id: "puerta", nombre: "Puerta", superficie: "madera" },
      { id: "reja", nombre: "Reja", superficie: "metal" },
    ],
  },
  terraza: {
    nombre: "Terraza", uso: "exterior",
    zonas: [
      { id: "muro", nombre: "Muro de la casa", superficie: "exterior" },
      { id: "piso", nombre: "Piso de madera", superficie: "madera" },
      { id: "baranda", nombre: "Baranda de madera", superficie: "madera" },
      { id: "reja", nombre: "Reja metálica", superficie: "metal" },
    ],
  },
};
// Ambiente que se abre para cada superficie (al llegar con un producto)
const AMBIENTE_DE_SUPERFICIE = { interior: "living", exterior: "fachada", techo: "fachada", madera: "terraza", metal: "terraza" };
const USO_DE_SUPERFICIE_V = { exterior: "exterior", techo: "exterior", interior: "interior" };
const MAX_RECIENTES = 8;
const MAX_FOTO_MB = 10;
const LADO_MAXIMO = 1600;   // la foto se achica a 1600 px por lado: más rápido
const MAX_ZONAS_FOTO = 6;
const MAX_HISTORIAL = 15;
const CLAVE_RECIENTES = "colores_recientes_ecocordi";
const CLAVE_FAVORITOS = "colores_favoritos_ecocordi";

/* -------- 2. ESTADO -------- */
let colores = [];          // carta de colores (GET /api/colores)
let familias = {};         // { blancos: "Blancos", ... }
const porId = {};          // { id: color }
let modo = "ambiente";     // "ambiente" | "foto"
let ambiente = "living";
let zonaActiva = null;     // zona elegida en el ambiente
const pintado = {};        // { living: { muro: 12, ... }, ... }: colores del lado A
let comparando = false;
let pintadoB = {};         // colores del lado B (solo el ambiente actual)
let colorElegido = null;   // el que muestra el panel
let filtroFamilia = "todas";
let textoBusqueda = "";
let productoFiltro = null; // ?producto=5 → solo sus colores
let recientes = leerLista(CLAVE_RECIENTES);
let favoritos = leerLista(CLAVE_FAVORITOS);
let favoritosEnServidor = false; // true si hay sesión (se guardan también en la cuenta)
const svgs = {};           // texto de cada ilustración ya descargada

const $ = function (id) { return document.getElementById(id); };
const escena = $("escena");
const escenaA = $("escenaA");
const escenaB = $("escenaB");
const grilla = $("paletaGrilla");
const panelColor = $("colorPanel");

/* -------- 3. UTILIDADES -------- */
function leerLista(clave) {
  // localStorage puede fallar (modo privado, permisos): entonces empieza vacía
  try {
    const valor = JSON.parse(localStorage.getItem(clave) || "[]");
    return Array.isArray(valor) ? valor.filter(Number.isInteger) : [];
  } catch (error) {
    return [];
  }
}
function guardarLista(clave, lista) {
  try {
    localStorage.setItem(clave, JSON.stringify(lista));
  } catch (error) { /* sin memoria del navegador: igual funciona en esta visita */ }
}
function hexValido(hex) {
  return /^#[0-9A-F]{6}$/i.test(hex || "");
}
function normalizarTexto(texto) {
  return String(texto || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}
function zonasDe(nombreAmbiente) {
  return AMBIENTES[nombreAmbiente].zonas;
}
function zonaInfo(id) {
  return zonasDe(ambiente).find(function (z) { return z.id === id; });
}
function esperarPintado() {
  return new Promise(function (resolver) { requestAnimationFrame(function () { setTimeout(resolver, 0); }); });
}

/* -------- 4. LA DIRECCIÓN DE LA PÁGINA (para compartir) --------
   ?modo=ambiente&ambiente=living&zonas=muro:12,acento:5&producto=3
   ?modo=foto&colores=12,5  (los colores usados; la foto NUNCA va aquí) */
function leerDireccion() {
  const p = new URLSearchParams(location.search);
  if (/^\d{1,9}$/.test(p.get("producto") || "")) productoFiltro = Number(p.get("producto"));
  if (AMBIENTES[p.get("ambiente")]) ambiente = p.get("ambiente");
  (p.get("zonas") || "").split(",").forEach(function (par) {
    const m = /^([a-z]{3,12}):(\d{1,9})$/.exec(par);
    if (m && zonasDe(ambiente).some(function (z) { return z.id === m[1]; }) && porId[Number(m[2])]) {
      (pintado[ambiente] = pintado[ambiente] || {})[m[1]] = Number(m[2]);
    }
  });
  const compartidos = (p.get("colores") || "").split(",").map(Number).filter(function (id) { return porId[id]; });
  compartidos.forEach(anotarReciente);
  modo = p.get("modo") === "foto" ? "foto" : "ambiente";
  return p;
}

function actualizarDireccion() {
  // Se arma a mano para que el enlace se lea bien (zonas=muro:12,acento:5).
  // Todos los valores son palabras de nuestras listas o números.
  const partes = ["modo=" + modo];
  if (modo === "ambiente") {
    partes.push("ambiente=" + ambiente);
    const zonas = Object.entries(pintado[ambiente] || {}).map(function (par) { return par[0] + ":" + par[1]; });
    if (zonas.length) partes.push("zonas=" + zonas.join(","));
  } else {
    const usados = foto.zonas.map(function (z) { return z.colorId; }).filter(Boolean);
    if (usados.length) partes.push("colores=" + [...new Set(usados)].join(","));
  }
  if (productoFiltro) partes.push("producto=" + productoFiltro);
  history.replaceState(null, "", location.pathname + "?" + partes.join("&"));
}

/* -------- 5. PALETA -------- */
function coloresVisibles() {
  const texto = normalizarTexto(textoBusqueda.trim());
  return colores.filter(function (c) {
    if (filtroFamilia !== "todas" && c.familia !== filtroFamilia) return false;
    if (productoFiltro && !c.productos.includes(productoFiltro)) return false;
    return !texto || normalizarTexto(c.nombre + " " + c.codigo).includes(texto);
  });
}

/* El color que tiene la zona que se está pintando (para marcarlo en la paleta) */
function colorDeZonaActual() {
  if (modo === "foto") return foto.zonas[foto.activa] ? foto.zonas[foto.activa].colorId : null;
  const mapa = comparando ? pintadoB : (pintado[ambiente] || {});
  return mapa[zonaActiva] || null;
}

function htmlMuestra(c, marcado) {
  return `<button type="button" class="muestra" data-color-id="${c.id}" aria-pressed="${marcado ? "true" : "false"}" tabindex="-1">
      <span class="muestra__tono" data-hex="${escaparHTML(c.hex)}"></span>
      <span class="muestra__nombre">${escaparHTML(c.nombre)}</span>
      <span class="muestra__codigo">${escaparHTML(c.codigo)}</span>
    </button>`;
}

function htmlPunto(c) {
  return `<button type="button" class="punto-color" data-color-id="${c.id}" data-hex="${escaparHTML(c.hex)}"
    aria-label="${escaparHTML(c.nombre)}, ${escaparHTML(c.codigo)}" title="${escaparHTML(c.nombre)}"></button>`;
}

function pintarPaleta() {
  const lista = coloresVisibles();
  const actual = colorDeZonaActual();
  grilla.innerHTML = lista.map(function (c) { return htmlMuestra(c, c.id === actual); }).join("");
  // Solo UNA muestra entra en el orden del Tab; con las flechas se recorre el resto
  const marcada = grilla.querySelector('[aria-pressed="true"]') || grilla.querySelector(".muestra");
  if (marcada) marcada.tabIndex = 0;
  $("paletaContador").textContent = lista.length === 0
    ? "No encontramos colores con esa búsqueda."
    : lista.length + (lista.length === 1 ? " color" : " colores");
  pintarMuestras(grilla);
  pintarFilas();
}

function pintarFilas() {
  const recientesValidos = recientes.map(function (id) { return porId[id]; }).filter(Boolean);
  $("filaRecientes").classList.toggle("oculto", recientesValidos.length === 0);
  $("paletaRecientes").innerHTML = recientesValidos.map(htmlPunto).join("");
  const favoritosValidos = favoritos.map(function (id) { return porId[id]; }).filter(Boolean);
  $("paletaFavoritos").innerHTML = favoritosValidos.length
    ? favoritosValidos.map(htmlPunto).join("")
    : '<p class="paleta__vacio">Guarda tus favoritos con el corazón. ' +
      (favoritosEnServidor ? "Quedan en tu cuenta." : "Si inicias sesión, quedan en tu cuenta.") + "</p>";
  pintarMuestras($("paletaRecientes"));
  pintarMuestras($("paletaFavoritos"));
}

function pintarFamilias() {
  const opciones = [["todas", "Todas"]].concat(Object.entries(familias));
  $("paletaFamilias").innerHTML = opciones.map(function (f) {
    return `<button type="button" class="familia" data-familia="${f[0]}" aria-pressed="${f[0] === filtroFamilia}">${escaparHTML(f[1])}</button>`;
  }).join("");
}

async function pintarFiltroProducto() {
  const aviso = $("paletaProducto");
  if (!productoFiltro) {
    aviso.classList.add("oculto");
    return;
  }
  await catalogoListo;
  const producto = productos.find(function (p) { return p.id === productoFiltro; });
  if (!producto) {
    productoFiltro = null;
    aviso.classList.add("oculto");
    pintarPaleta();
    return;
  }
  aviso.innerHTML = `Colores de <strong>${escaparHTML(producto.nombre)}</strong>
    <button type="button" class="catalogo__quitar" data-ver-todos>Ver todos</button>`;
  aviso.classList.remove("oculto");
}

function anotarReciente(id) {
  recientes = [id].concat(recientes.filter(function (r) { return r !== id; })).slice(0, MAX_RECIENTES);
  guardarLista(CLAVE_RECIENTES, recientes);
}

/* Clic en cualquier muestra (grilla, últimos usados o mis colores) */
document.querySelector(".paleta").addEventListener("click", function (evento) {
  const muestra = evento.target.closest("[data-color-id]");
  if (muestra) {
    aplicarColor(Number(muestra.dataset.colorId));
    return;
  }
  const familia = evento.target.closest("[data-familia]");
  if (familia) {
    filtroFamilia = familia.dataset.familia;
    pintarFamilias();
    pintarPaleta();
    return;
  }
  if (evento.target.closest("[data-ver-todos]")) {
    productoFiltro = null;
    pintarFiltroProducto();
    pintarPaleta();
    actualizarDireccion();
  }
});

$("buscarColor").addEventListener("input", function () {
  textoBusqueda = $("buscarColor").value.slice(0, 40);
  pintarPaleta();
});

/* Flechas del teclado dentro de la grilla ("tabindex móvil") */
grilla.addEventListener("keydown", function (evento) {
  const muestras = [...grilla.querySelectorAll(".muestra")];
  const i = muestras.indexOf(document.activeElement);
  if (i < 0) return;
  const primeraFila = muestras.filter(function (m) { return m.offsetTop === muestras[0].offsetTop; }).length || 1;
  const saltos = { ArrowRight: 1, ArrowLeft: -1, ArrowDown: primeraFila, ArrowUp: -primeraFila };
  let destino = null;
  if (saltos[evento.key] !== undefined) destino = Math.min(muestras.length - 1, Math.max(0, i + saltos[evento.key]));
  if (evento.key === "Home") destino = 0;
  if (evento.key === "End") destino = muestras.length - 1;
  if (destino === null) return;
  evento.preventDefault();
  muestras[i].tabIndex = -1;
  muestras[destino].tabIndex = 0;
  muestras[destino].focus();
});

/* -------- 6. APLICAR UN COLOR -------- */
function aplicarColor(id) {
  const color = porId[id];
  if (!color) return;
  if (modo === "ambiente") {
    if (!zonaActiva) elegirZona(zonasDe(ambiente)[0].id);
    if (comparando) pintadoB[zonaActiva] = id;
    else (pintado[ambiente] = pintado[ambiente] || {})[zonaActiva] = id;
    pintarEscena();
  } else {
    const zona = foto.zonas[foto.activa];
    if (!zona) return;
    if (!zona.mascara.some(function (v) { return v > 0; })) {
      avisar("Primero marca en tu foto la zona que quieres pintar: toca la pared.", "info");
      return;
    }
    guardarHistorial({ tipo: "color", zona: foto.activa, anterior: zona.colorId });
    zona.colorId = id;
    $("verSeleccion").checked = false; // para ver el resultado sin la marca encima
    dibujarMascara();
    componer();
    pintarZonasFoto();
  }
  anotarReciente(id);
  mostrarColor(color);
  pintarPaleta();
  actualizarDireccion();
}

/* -------- 7. MODO A: AMBIENTES -------- */
function pintarListaAmbientes() {
  $("ambientesLista").innerHTML = Object.entries(AMBIENTES).map(function (a) {
    const elegido = a[0] === ambiente;
    return `<button type="button" class="ambiente" role="radio" aria-checked="${elegido}" tabindex="${elegido ? 0 : -1}"
      data-ambiente="${a[0]}">${escaparHTML(a[1].nombre)}</button>`;
  }).join("");
}

async function textoSvg(nombre) {
  if (!svgs[nombre]) svgs[nombre] = await (await fetch("img/ambientes/" + nombre + ".svg")).text();
  return svgs[nombre];
}

/* La copia B (para comparar) necesita otros id: si no, sus degradados
   apuntarían a los de la copia A */
function conSufijo(texto, sufijo) {
  return texto.replace(/id="([^"]+)"/g, 'id="$1' + sufijo + '"').replace(/url\(#([^)]+)\)/g, "url(#$1" + sufijo + ")");
}

async function cargarAmbiente(nombre) {
  ambiente = nombre;
  pintarListaAmbientes();
  const texto = await textoSvg(nombre);
  if (ambiente !== nombre) return; // la persona ya eligió otro
  escenaA.innerHTML = texto;
  const svg = escenaA.querySelector("svg");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "Ilustración: " + svg.querySelector("title").textContent);
  if (comparando) {
    escenaB.innerHTML = conSufijo(texto, "-b");
    escenaB.querySelector("svg").setAttribute("aria-hidden", "true");
  }
  if (!zonaInfo(zonaActiva)) zonaActiva = zonaPreferida();
  pintarZonas();
  pintarEscena();
  actualizarDireccion();
}

/* Con un producto elegido, empezamos por la zona que corresponde a su superficie */
function zonaPreferida() {
  const producto = productoFiltro && typeof productos !== "undefined"
    ? productos.find(function (p) { return p.id === productoFiltro; }) : null;
  const zona = producto && zonasDe(ambiente).find(function (z) { return producto.superficies.includes(z.superficie); });
  return (zona || zonasDe(ambiente)[0]).id;
}

function pintarZonas() {
  const mapa = pintado[ambiente] || {};
  $("zonasLista").innerHTML = zonasDe(ambiente).map(function (z) {
    const color = porId[comparando && z.id === zonaActiva ? pintadoB[z.id] : mapa[z.id]];
    return `<button type="button" class="zona" data-zona-boton="${z.id}" aria-pressed="${z.id === zonaActiva}">
      <span class="zona__muestra" ${color ? `data-hex="${escaparHTML(color.hex)}"` : ""}></span>
      <span class="zona__texto"><span class="zona__nombre">${escaparHTML(z.nombre)}</span>
      <span class="zona__color">${color ? escaparHTML(color.nombre) : "Sin pintar"}</span></span></button>`;
  }).join("");
  pintarMuestras($("zonasLista"));
}

function elegirZona(id) {
  if (!zonaInfo(id)) return;
  zonaActiva = id;
  if (comparando) {
    pintadoB = Object.assign({}, pintado[ambiente] || {});
  }
  pintarZonas();
  pintarEscena();
  // Destacamos un momento la zona en el dibujo
  escenaA.querySelectorAll("[data-zona]").forEach(function (el) {
    el.classList.toggle("zona--destacada", el.dataset.zona === id);
  });
  setTimeout(function () {
    escenaA.querySelectorAll(".zona--destacada").forEach(function (el) { el.classList.remove("zona--destacada"); });
  }, 1400);
  const color = porId[colorDeZonaActual()];
  if (color) mostrarColor(color);
  pintarPaleta();
}

/* Pone el color de cada zona en el dibujo (con una transición suave, ver CSS) */
function pintarEscena() {
  const mapaA = pintado[ambiente] || {};
  const pintarEn = function (contenedor, mapa) {
    contenedor.querySelectorAll("[data-zona]").forEach(function (el) {
      const color = porId[mapa[el.dataset.zona]];
      if (color && hexValido(color.hex)) el.style.fill = color.hex;
      else el.style.removeProperty("fill"); // vuelve al color original del dibujo
    });
  };
  pintarEn(escenaA, mapaA);
  if (comparando) pintarEn(escenaB, pintadoB);
  pintarZonas();
  pintarEtiquetasComparar();
}

$("ambientesLista").addEventListener("click", function (evento) {
  const boton = evento.target.closest("[data-ambiente]");
  if (boton && boton.dataset.ambiente !== ambiente) {
    zonaActiva = null;
    cargarAmbiente(boton.dataset.ambiente);
  }
});
// Radio con flechas (como los botones de radio del navegador)
$("ambientesLista").addEventListener("keydown", function (evento) {
  const paso = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[evento.key];
  if (!paso) return;
  evento.preventDefault();
  const nombres = Object.keys(AMBIENTES);
  const siguiente = nombres[(nombres.indexOf(ambiente) + paso + nombres.length) % nombres.length];
  zonaActiva = null;
  cargarAmbiente(siguiente).then(function () { document.querySelector(`[data-ambiente="${siguiente}"]`).focus(); });
});
$("zonasLista").addEventListener("click", function (evento) {
  const boton = evento.target.closest("[data-zona-boton]");
  if (boton) elegirZona(boton.dataset.zonaBoton);
});
// Tocar una zona en el dibujo también la elige
escena.addEventListener("click", function (evento) {
  const zona = evento.target.closest("[data-zona]");
  if (zona) elegirZona(zona.dataset.zona);
});

/* -------- 7b. COMPARAR DOS COLORES --------
   Se superpone una segunda copia del dibujo (B) y el deslizador decide
   cuánto se ve de cada una: A a la izquierda y B a la derecha. */
async function alternarComparar() {
  comparando = !comparando;
  $("btnComparar").setAttribute("aria-pressed", String(comparando));
  ["escenaB", "divisor", "etiquetaA", "etiquetaB", "controlComparar"].forEach(function (id) {
    $(id).classList.toggle("oculto", !comparando);
  });
  if (comparando) {
    pintadoB = Object.assign({}, pintado[ambiente] || {});
    escenaB.innerHTML = conSufijo(await textoSvg(ambiente), "-b");
    escenaB.querySelector("svg").setAttribute("aria-hidden", "true");
    moverDivisor();
    avisar("Elige otro color para «" + zonaInfo(zonaActiva).nombre + "» y compáralo con el actual.", "info");
  } else {
    escenaB.innerHTML = "";
  }
  pintarEscena();
  pintarPaleta();
}

function moverDivisor() {
  const x = Number($("deslizador").value);
  escenaB.style.clipPath = `inset(0 0 0 ${x}%)`;
  $("divisor").style.left = x + "%";
}

function pintarEtiquetasComparar() {
  if (!comparando) return;
  const a = porId[(pintado[ambiente] || {})[zonaActiva]];
  const b = porId[pintadoB[zonaActiva]];
  $("etiquetaA").textContent = "A · " + (a ? a.nombre : "Original");
  $("etiquetaB").textContent = "B · " + (b && b !== a ? b.nombre : "Elige un color");
}

$("btnComparar").addEventListener("click", alternarComparar);
$("deslizador").addEventListener("input", moverDivisor);

/* -------- 8. MODO B: TU PROPIA FOTO --------
   Todo ocurre aquí: la foto se lee con createImageBitmap, se dibuja en un
   <canvas> y se procesa en la memoria del navegador. No hay fetch ni
   formulario que la envíe. */
const foto = {
  ancho: 0, alto: 0,
  original: null,      // píxeles originales (RGBA)
  luz: null,           // luminosidad de cada píxel (0 a 1)
  zonas: [],           // [{ mascara: Uint8Array (0-255 por píxel), colorId, luzMedia }]
  activa: 0,
  herramienta: "relleno",
  historial: [],
  ocupado: false,
};
const lienzo = $("fotoLienzo");
const capaMascara = $("fotoMascara");
const ctxLienzo = lienzo.getContext("2d", { willReadFrequently: true });
const ctxMascara = capaMascara.getContext("2d");

function errorFoto(texto) {
  $("fotoError").textContent = texto;
}

/* Muestra "Pintando…" solo si la tarea demora (así no parpadea en las rápidas) */
async function conCargando(texto, tarea) {
  foto.ocupado = true;
  const cartel = $("fotoCargando");
  cartel.lastElementChild.textContent = texto;
  const reloj = setTimeout(function () { cartel.classList.remove("oculto"); }, 120);
  try {
    return await tarea();
  } finally {
    clearTimeout(reloj);
    cartel.classList.add("oculto");
    foto.ocupado = false;
  }
}

async function cargarFoto(archivo) {
  errorFoto("");
  if (!archivo) return;
  if (!["image/jpeg", "image/png", "image/webp"].includes(archivo.type)) {
    errorFoto("Usa una foto JPG, PNG o WebP.");
    return;
  }
  if (archivo.size > MAX_FOTO_MB * 1024 * 1024) {
    errorFoto(`La foto pesa más de ${MAX_FOTO_MB} MB. Prueba con una más liviana.`);
    return;
  }
  let imagen;
  try {
    imagen = await createImageBitmap(archivo); // se lee en la memoria del navegador
  } catch (error) {
    errorFoto("No pudimos abrir esa foto. Prueba con otra.");
    return;
  }
  const escala = Math.min(1, LADO_MAXIMO / Math.max(imagen.width, imagen.height));
  foto.ancho = Math.max(1, Math.round(imagen.width * escala));
  foto.alto = Math.max(1, Math.round(imagen.height * escala));
  lienzo.width = capaMascara.width = foto.ancho;
  lienzo.height = capaMascara.height = foto.alto;
  ctxLienzo.drawImage(imagen, 0, 0, foto.ancho, foto.alto);
  if (imagen.close) imagen.close();
  foto.original = new Uint8ClampedArray(ctxLienzo.getImageData(0, 0, foto.ancho, foto.alto).data);
  foto.luz = new Float32Array(foto.ancho * foto.alto);
  for (let i = 0, p = 0; i < foto.luz.length; i++, p += 4) {
    foto.luz[i] = (0.3 * foto.original[p] + 0.59 * foto.original[p + 1] + 0.11 * foto.original[p + 2]) / 255;
  }
  foto.zonas = [nuevaZona()];
  foto.activa = 0;
  foto.historial = [];
  $("fotoSubir").classList.add("oculto");
  $("fotoEditor").classList.remove("oculto");
  $("verSeleccion").checked = true;
  elegirHerramienta("relleno");
  pintarZonasFoto();
  dibujarMascara();
  actualizarDeshacer();
  $("fotoAyuda").textContent = "Toca la pared que quieres pintar. Si se marca de más o de menos, ajusta la tolerancia o usa el pincel y la goma.";
}

function nuevaZona() {
  return { mascara: new Uint8Array(foto.ancho * foto.alto), colorId: null, luzMedia: null };
}

["inputFoto", "inputCamara"].forEach(function (id) {
  $(id).addEventListener("change", function () {
    cargarFoto(this.files[0]);
    this.value = ""; // permite elegir la misma foto otra vez
  });
});
// También se puede arrastrar la foto sobre el recuadro
$("fotoSubir").addEventListener("dragover", function (e) { e.preventDefault(); this.classList.add("foto-subir--encima"); });
$("fotoSubir").addEventListener("dragleave", function () { this.classList.remove("foto-subir--encima"); });
$("fotoSubir").addEventListener("drop", function (e) {
  e.preventDefault();
  this.classList.remove("foto-subir--encima");
  cargarFoto(e.dataTransfer.files[0]);
});
$("btnOtraFoto").addEventListener("click", function () {
  $("fotoEditor").classList.add("oculto");
  $("fotoSubir").classList.remove("oculto");
  foto.original = null;
  foto.zonas = [];
  actualizarDireccion();
  $("inputFoto").focus();
});

/* ---- Herramientas ---- */
function elegirHerramienta(nombre) {
  foto.herramienta = nombre;
  document.querySelectorAll("[data-herramienta]").forEach(function (b) {
    b.setAttribute("aria-pressed", String(b.dataset.herramienta === nombre));
  });
  $("ajusteTolerancia").classList.toggle("oculto", nombre !== "relleno");
  $("ajustePincel").classList.toggle("oculto", nombre === "relleno");
  // Con pincel o goma, arrastrar el dedo pinta (no mueve la página)
  $("fotoMarco").classList.toggle("foto-marco--dibujo", nombre !== "relleno");
  if (nombre !== "relleno" && !$("verSeleccion").checked) {
    $("verSeleccion").checked = true;
    dibujarMascara();
  }
}
document.querySelectorAll("[data-herramienta]").forEach(function (b) {
  b.addEventListener("click", function () { elegirHerramienta(b.dataset.herramienta); });
});
$("tolerancia").addEventListener("input", function () { $("valorTolerancia").textContent = this.value; });
$("tamanoPincel").addEventListener("input", function () { $("valorPincel").textContent = this.value; });
$("verSeleccion").addEventListener("change", dibujarMascara);

/* ---- Deshacer ---- */
function guardarHistorial(paso) {
  foto.historial.push(paso);
  if (foto.historial.length > MAX_HISTORIAL) foto.historial.shift();
  actualizarDeshacer();
}
function guardarMascara() {
  guardarHistorial({ tipo: "mascara", zona: foto.activa, copia: foto.zonas[foto.activa].mascara.slice() });
}
function actualizarDeshacer() {
  $("btnDeshacer").disabled = foto.historial.length === 0;
}
function deshacer() {
  const paso = foto.historial.pop();
  if (!paso || foto.ocupado) return;
  if (paso.tipo === "zona") {
    foto.zonas.pop();
    foto.activa = Math.min(foto.activa, foto.zonas.length - 1);
  } else if (foto.zonas[paso.zona]) {
    if (paso.tipo === "mascara") {
      foto.zonas[paso.zona].mascara = paso.copia;
      foto.zonas[paso.zona].luzMedia = null;
    } else {
      foto.zonas[paso.zona].colorId = paso.anterior;
    }
    foto.activa = paso.zona;
  }
  actualizarDeshacer();
  pintarZonasFoto();
  dibujarMascara();
  componer();
  actualizarDireccion();
}
$("btnDeshacer").addEventListener("click", deshacer);
document.addEventListener("keydown", function (e) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z" && modo === "foto" && !e.target.matches("input[type=search]")) {
    e.preventDefault();
    deshacer();
  }
});

/* ---- Zonas de la foto ---- */
function pintarZonasFoto() {
  $("zonasFoto").innerHTML = foto.zonas.map(function (z, i) {
    const color = porId[z.colorId];
    return `<button type="button" class="zona" data-zona-foto="${i}" aria-pressed="${i === foto.activa}">
      <span class="zona__muestra" ${color ? `data-hex="${escaparHTML(color.hex)}"` : ""}></span>
      <span class="zona__texto"><span class="zona__nombre">Zona ${i + 1}</span>
      <span class="zona__color">${color ? escaparHTML(color.nombre) : "Sin color"}</span></span></button>`;
  }).join("") + (foto.zonas.length < MAX_ZONAS_FOTO
    ? `<button type="button" class="zona zona--nueva" data-nueva-zona>
        <svg class="icono" aria-hidden="true"><use href="#i-mas"/></svg>Nueva zona</button>` : "");
  pintarMuestras($("zonasFoto"));
}

$("zonasFoto").addEventListener("click", function (evento) {
  if (evento.target.closest("[data-nueva-zona]")) {
    foto.zonas.push(nuevaZona());
    foto.activa = foto.zonas.length - 1;
    guardarHistorial({ tipo: "zona" });
    elegirHerramienta("relleno");
    $("verSeleccion").checked = true;
    $("fotoAyuda").textContent = "Zona " + foto.zonas.length + ": toca otra parte de la foto (por ejemplo, otro muro o la puerta).";
  } else {
    const boton = evento.target.closest("[data-zona-foto]");
    if (!boton) return;
    foto.activa = Number(boton.dataset.zonaFoto);
    const color = porId[foto.zonas[foto.activa].colorId];
    if (color) mostrarColor(color);
  }
  pintarZonasFoto();
  dibujarMascara();
  pintarPaleta();
});

/* ---- Tocar la foto: relleno, pincel o goma ---- */
function puntoEnFoto(evento) {
  const caja = capaMascara.getBoundingClientRect();
  return {
    x: Math.min(foto.ancho - 1, Math.max(0, Math.floor((evento.clientX - caja.left) * foto.ancho / caja.width))),
    y: Math.min(foto.alto - 1, Math.max(0, Math.floor((evento.clientY - caja.top) * foto.alto / caja.height))),
  };
}

let trazo = null; // { ultimo, inicio } mientras se arrastra

capaMascara.addEventListener("pointerdown", function (evento) {
  if (foto.ocupado || !foto.original) return;
  const punto = puntoEnFoto(evento);
  trazo = { inicio: { x: evento.clientX, y: evento.clientY }, ultimo: punto };
  if (foto.herramienta !== "relleno") {
    capaMascara.setPointerCapture(evento.pointerId);
    guardarMascara();
    pintarCirculo(punto.x, punto.y);
    dibujarMascara();
  }
});
capaMascara.addEventListener("pointermove", function (evento) {
  if (!trazo || foto.herramienta === "relleno") return;
  const punto = puntoEnFoto(evento);
  // Rellenamos entre el punto anterior y el nuevo (si no, quedan "puntos" sueltos)
  const pasos = Math.max(1, Math.ceil(Math.hypot(punto.x - trazo.ultimo.x, punto.y - trazo.ultimo.y) / (radioPincel() / 3)));
  for (let i = 1; i <= pasos; i++) {
    pintarCirculo(Math.round(trazo.ultimo.x + (punto.x - trazo.ultimo.x) * i / pasos),
                  Math.round(trazo.ultimo.y + (punto.y - trazo.ultimo.y) * i / pasos));
  }
  trazo.ultimo = punto;
  dibujarMascara();
});
function terminarTrazo(evento) {
  if (!trazo) return;
  const t = trazo;
  trazo = null;
  if (foto.herramienta === "relleno") {
    // Solo un toque (no un arrastre para mover la página)
    if (evento.type === "pointerup" && Math.hypot(evento.clientX - t.inicio.x, evento.clientY - t.inicio.y) < 10) {
      rellenar(t.ultimo.x, t.ultimo.y);
    }
    return;
  }
  foto.zonas[foto.activa].luzMedia = null;
  componer();
}
capaMascara.addEventListener("pointerup", terminarTrazo);
capaMascara.addEventListener("pointercancel", terminarTrazo);

/* El tamaño del pincel está en píxeles de la PANTALLA; lo pasamos a píxeles de la foto */
function radioPincel() {
  const ancho = capaMascara.getBoundingClientRect().width || foto.ancho;
  return Math.max(1, Number($("tamanoPincel").value) / 2 * foto.ancho / ancho);
}

/* Pincel (suma a la zona) o goma (le quita), con el borde suave */
function pintarCirculo(cx, cy) {
  const r = radioPincel();
  const m = foto.zonas[foto.activa].mascara;
  const goma = foto.herramienta === "goma";
  for (let y = Math.max(0, Math.floor(cy - r)); y <= Math.min(foto.alto - 1, Math.ceil(cy + r)); y++) {
    for (let x = Math.max(0, Math.floor(cx - r)); x <= Math.min(foto.ancho - 1, Math.ceil(cx + r)); x++) {
      const d = Math.hypot(x - cx, y - cy);
      if (d > r) continue;
      const fuerza = Math.min(1, (r - d) / 1.5) * 255; // 1,5 px de borde suave
      const i = y * foto.ancho + x;
      m[i] = goma ? Math.min(m[i], 255 - fuerza) : Math.max(m[i], fuerza);
    }
  }
}

/* RELLENO POR INUNDACIÓN ("flood fill"): desde el punto tocado, marca los
   píxeles vecinos de color parecido. Usa una PILA (no recursión: con fotos
   grandes, la recursión se quedaría sin memoria) y cada tanto le devuelve el
   control al navegador para que la página no se congele.
   Un píxel entra si cumple DOS reglas:
     1) Se parece al punto tocado. El parecido se mide en un espacio de color
        (Y, Cb, Cr) donde la luz (Y) cuenta menos que el tono: así una pared
        con sombra sigue siendo "la pared".
     2) No hay un BORDE entre él y su vecino: la sombra de un muro cambia de a
        poco, pero entre el muro y el piso hay un salto brusco. */
function rellenar(x0, y0) {
  return conCargando("Marcando la zona…", async function () {
    const { ancho, alto, original } = foto;
    const zona = foto.zonas[foto.activa];
    guardarMascara();
    const tolerancia = Number($("tolerancia").value);
    const umbral = 4 + tolerancia * 1.1;     // regla 1: parecido al punto tocado
    const borde = 10 + tolerancia * 0.4;     // regla 2: salto máximo entre vecinos
    const semilla = (y0 * ancho + x0) * 4;
    const [Y0, B0, R0] = ycbcr(original[semilla], original[semilla + 1], original[semilla + 2]);
    const visitado = new Uint8Array(ancho * alto);
    const pila = new Int32Array(ancho * alto);
    let tope = 0;
    pila[tope++] = y0 * ancho + x0;
    visitado[y0 * ancho + x0] = 1;
    let contador = 0;
    let pausa = performance.now();
    while (tope > 0) {
      const i = pila[--tope];
      const p = i * 4;
      const [Y, B, R] = ycbcr(original[p], original[p + 1], original[p + 2]);
      const distancia = Math.sqrt((Y - Y0) * (Y - Y0) * 0.3 + (B - B0) * (B - B0) + (R - R0) * (R - R0));
      if (distancia > umbral) continue;
      zona.mascara[i] = 255;
      const x = i % ancho;
      // Vecinos: izquierda, derecha, arriba y abajo (si no hay un borde de por medio)
      const vecinos = [x > 0 ? i - 1 : -1, x < ancho - 1 ? i + 1 : -1, i >= ancho ? i - ancho : -1,
                       i < ancho * (alto - 1) ? i + ancho : -1];
      for (const j of vecinos) {
        if (j < 0 || visitado[j]) continue;
        const q = j * 4;
        const [Yj, Bj, Rj] = ycbcr(original[q], original[q + 1], original[q + 2]);
        // En el borde el TONO pesa más (×2,5): la sombra cambia la luz, no el tono
        if ((Yj - Y) * (Yj - Y) + 6.25 * ((Bj - B) * (Bj - B) + (Rj - R) * (Rj - R)) > borde * borde) continue;
        visitado[j] = 1;
        pila[tope++] = j;
      }
      if (++contador % 20000 === 0 && performance.now() - pausa > 40) {
        await esperarPintado(); // la página sigue respondiendo
        pausa = performance.now();
      }
    }
    suavizarBorde(zona.mascara);
    zona.luzMedia = null;
    dibujarMascara();
    await componerAhora();
    $("fotoAyuda").textContent = zona.colorId
      ? "Listo. Puedes tocar más partes, corregir con el pincel o la goma, o crear otra zona."
      : "Zona marcada. Ahora elige un color en la paleta.";
    actualizarDireccion();
  });
}

function ycbcr(r, g, b) {
  return [0.299 * r + 0.587 * g + 0.114 * b, -0.1687 * r - 0.3313 * g + 0.5 * b, 0.5 * r - 0.4187 * g - 0.0813 * b];
}

/* Borde suave: los píxeles del borde quedan "a medias" (sin serrucho) */
function suavizarBorde(m) {
  const { ancho, alto } = foto;
  const copia = m.slice();
  for (let y = 1; y < alto - 1; y++) {
    for (let x = 1; x < ancho - 1; x++) {
      const i = y * ancho + x;
      const vecinos = copia[i - 1] + copia[i + 1] + copia[i - ancho] + copia[i + ancho];
      if (vecinos === 0 || vecinos === 1020) continue; // interior o exterior: igual
      m[i] = Math.round((copia[i] * 4 + vecinos) / 8);
    }
  }
}

/* Dibuja la zona activa encima de la foto (azul semitransparente) */
function dibujarMascara() {
  if (!foto.original) return;
  ctxMascara.clearRect(0, 0, foto.ancho, foto.alto);
  const zona = foto.zonas[foto.activa];
  if (!zona || !$("verSeleccion").checked) return;
  const imagen = ctxMascara.createImageData(foto.ancho, foto.alto);
  const d = imagen.data;
  for (let i = 0, p = 0; i < zona.mascara.length; i++, p += 4) {
    if (!zona.mascara[i]) continue;
    d[p] = 45; d[p + 1] = 91; d[p + 2] = 168; d[p + 3] = zona.mascara[i] * 0.42;
  }
  ctxMascara.putImageData(imagen, 0, 0);
}

/* RECOLOREADO REALISTA
   Para cada píxel de la zona: se toma el TONO y la SATURACIÓN del color
   elegido (mezcla tipo "color") y se conserva la luz relativa del píxel
   (sombras, brillos y textura). La luz relativa es la luminosidad del píxel
   dividida por el promedio de la zona: un rincón en sombra queda igual de
   más oscuro que el resto de la pared, ahora en el color nuevo. */
function luminosidad(r, g, b) { return 0.3 * r + 0.59 * g + 0.11 * b; }

function conLuminosidad(r, g, b, l) {
  // SetLum y ClipColor de la especificación de modos de mezcla (W3C Compositing)
  const d = l - luminosidad(r, g, b);
  r += d; g += d; b += d;
  const lum = luminosidad(r, g, b);
  const n = Math.min(r, g, b);
  const x = Math.max(r, g, b);
  if (n < 0) { r = lum + (r - lum) * lum / (lum - n); g = lum + (g - lum) * lum / (lum - n); b = lum + (b - lum) * lum / (lum - n); }
  if (x > 1) { r = lum + (r - lum) * (1 - lum) / (x - lum); g = lum + (g - lum) * (1 - lum) / (x - lum); b = lum + (b - lum) * (1 - lum) / (x - lum); }
  return [r, g, b];
}

function luzMedia(zona) {
  if (zona.luzMedia === null) {
    let suma = 0, peso = 0;
    for (let i = 0; i < zona.mascara.length; i++) {
      if (zona.mascara[i]) { suma += foto.luz[i] * zona.mascara[i]; peso += zona.mascara[i]; }
    }
    zona.luzMedia = peso ? suma / peso : 0.5;
  }
  return zona.luzMedia;
}

let componerPendiente = null;
function componer() {
  // Si llegan varios pedidos seguidos, se hace una sola vez
  if (componerPendiente) return componerPendiente;
  componerPendiente = esperarPintado().then(componerAhora).finally(function () { componerPendiente = null; });
  return componerPendiente;
}

async function componerAhora() {
  if (!foto.original) return;
  const salida = new Uint8ClampedArray(foto.original);
  const zonas = foto.zonas.filter(function (z) { return porId[z.colorId]; }).map(function (z) {
    const hex = porId[z.colorId].hex;
    const r = parseInt(hex.slice(1, 3), 16) / 255, g = parseInt(hex.slice(3, 5), 16) / 255, b = parseInt(hex.slice(5, 7), 16) / 255;
    return { m: z.mascara, r: r, g: g, b: b, luzColor: luminosidad(r, g, b), media: luzMedia(z) };
  });
  let pausa = performance.now();
  for (const z of zonas) {
    for (let i = 0, p = 0; i < z.m.length; i++, p += 4) {
      const a = z.m[i];
      if (!a) continue;
      const relativa = Math.min(1.8, foto.luz[i] / Math.max(z.media, 0.02));
      const [r, g, b] = conLuminosidad(z.r, z.g, z.b, Math.min(1, z.luzColor * relativa));
      const f = a / 255;
      salida[p] = salida[p] * (1 - f) + r * 255 * f;
      salida[p + 1] = salida[p + 1] * (1 - f) + g * 255 * f;
      salida[p + 2] = salida[p + 2] * (1 - f) + b * 255 * f;
      if ((i & 0x3FFFF) === 0 && performance.now() - pausa > 50) {
        await esperarPintado();
        pausa = performance.now();
      }
    }
  }
  ctxLienzo.putImageData(new ImageData(salida, foto.ancho, foto.alto), 0, 0);
}

/* -------- 9. PANEL DEL COLOR ELEGIDO: comprar en ese color -------- */
function superficieActual(producto) {
  if (modo === "ambiente" && zonaInfo(zonaActiva)) return zonaInfo(zonaActiva).superficie;
  return producto ? producto.superficies[0] : null;
}

async function mostrarColor(color) {
  colorElegido = color;
  const favorito = favoritos.includes(color.id);
  panelColor.innerHTML = `
    <div class="color-panel__cabecera">
      <span class="color-panel__muestra" data-hex="${escaparHTML(color.hex)}" aria-hidden="true"></span>
      <div class="color-panel__datos">
        <p class="color-panel__etiqueta">Color elegido</p>
        <h2 class="color-panel__nombre" id="colorNombre">${escaparHTML(color.nombre)}</h2>
        <p class="color-panel__codigo">${escaparHTML(color.codigo)} · ${escaparHTML(familias[color.familia] || color.familia)}</p>
      </div>
      <button type="button" class="color-panel__favorito" data-favorito aria-pressed="${favorito}"
              aria-label="${favorito ? "Quitar de Mis colores" : "Guardar en Mis colores"}">
        <svg class="icono" aria-hidden="true"><use href="#i-corazon"/></svg>
      </button>
    </div>
    ${color.es_demo ? '<p class="color-panel__demo">Color de ejemplo: la carta oficial está por confirmar.</p>' : ""}
    <div id="colorCompra"><p class="color-panel__cargando">Buscando pinturas en este color…</p></div>`;
  pintarMuestras(panelColor);
  panelColor.classList.remove("oculto");
  await catalogoListo;
  if (colorElegido !== color) return;
  pintarCompra(color);
}

function pintarCompra(color) {
  const superficie = superficieActual();
  const opciones = productos
    .filter(function (p) { return (p.colores || []).includes(color.id) && p.formatos.some(function (f) { return f.stock > 0; }); })
    .sort(function (a, b) { return Number(b.superficies.includes(superficie)) - Number(a.superficies.includes(superficie)); });
  const zona = $("colorCompra");
  if (opciones.length === 0) {
    zona.innerHTML = `<p class="color-panel__vacio">Por ahora no tenemos pinturas en stock en este color.
      Escríbenos y te ayudamos a encontrar uno parecido.</p>`;
    return;
  }
  const elegido = opciones.find(function (p) { return p.id === productoFiltro; }) || opciones[0];
  zona.innerHTML = `
    <form class="color-panel__compra" id="formComprarColor">
      <label class="campo">
        <span class="campo__etiqueta">Pintura en este color</span>
        <select class="campo__control" id="compraProducto">${opciones.map(function (p) {
          return `<option value="${p.id}" ${p.id === elegido.id ? "selected" : ""}>${escaparHTML(p.nombre)}${
            superficie && p.superficies.includes(superficie) ? "" : " (otra superficie)"}</option>`;
        }).join("")}</select>
      </label>
      <label class="campo">
        <span class="campo__etiqueta">Formato</span>
        <select class="campo__control" id="compraFormato"></select>
      </label>
      <button type="submit" class="boton boton--principal boton--ancho">
        <svg class="icono" aria-hidden="true"><use href="#i-tarro"/></svg>Agregar al carrito
      </button>
    </form>
    <a class="enlace-flecha color-panel__cuanto" id="enlaceCuanto" href="asistente.html">
      ¿Cuánto necesito? <svg class="icono" aria-hidden="true"><use href="#i-flecha"/></svg></a>`;
  pintarFormatos();
}

function productoDeCompra() {
  const selector = $("compraProducto");
  return selector && productos.find(function (p) { return String(p.id) === selector.value; });
}

function pintarFormatos() {
  const producto = productoDeCompra();
  if (!producto) return;
  const inicial = formatoInicial(producto);
  $("compraFormato").innerHTML = producto.formatos.filter(function (f) { return f.stock > 0; }).map(function (f) {
    return `<option value="${f.id}" ${inicial && f.id === inicial.id ? "selected" : ""}>${escaparHTML(f.nombre)} · ${formatearPrecio(f.precio)}</option>`;
  }).join("");
  // "¿Cuánto necesito?" abre el asistente con la superficie, la pintura y el color
  const superficie = superficieActual(producto) || producto.superficies[0];
  const params = new URLSearchParams({ superficie: superficie });
  const uso = USO_DE_SUPERFICIE_V[superficie] || (modo === "ambiente" ? AMBIENTES[ambiente].uso : null);
  if (uso) params.set("uso", uso);
  params.set("producto", producto.id);
  params.set("color", colorElegido.id);
  $("enlaceCuanto").href = "asistente.html?" + params;
}

panelColor.addEventListener("change", function (evento) {
  if (evento.target.id === "compraProducto") pintarFormatos();
});

panelColor.addEventListener("submit", async function (evento) {
  if (evento.target.id !== "formComprarColor") return;
  evento.preventDefault();
  const formatoId = Number($("compraFormato").value);
  const boton = evento.target.querySelector("button[type=submit]");
  boton.disabled = true;
  try {
    // El servidor revisa que el color corresponda a esa pintura
    const respuesta = await fetch("/api/carrito/item", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ formato_id: formatoId, color_id: colorElegido.id }),
    });
    const datos = await respuesta.json();
    if (!respuesta.ok) {
      avisar(datos.error || "No se pudo agregar al carrito.", "error");
      return;
    }
    agregarAlCarrito(formatoId, 1, true, datos.color);
  } catch (error) {
    avisar("No pudimos conectarnos con la tienda. Inténtalo de nuevo.", "error");
  } finally {
    boton.disabled = false;
  }
});

/* -------- 10. MIS COLORES (favoritos) --------
   Siempre en el navegador (localStorage). Si hay sesión, también en la cuenta. */
panelColor.addEventListener("click", async function (evento) {
  const boton = evento.target.closest("[data-favorito]");
  if (!boton || !colorElegido) return;
  const id = colorElegido.id;
  const quitar = favoritos.includes(id);
  favoritos = quitar ? favoritos.filter(function (f) { return f !== id; }) : favoritos.concat(id);
  guardarLista(CLAVE_FAVORITOS, favoritos);
  boton.setAttribute("aria-pressed", String(!quitar));
  boton.setAttribute("aria-label", quitar ? "Guardar en Mis colores" : "Quitar de Mis colores");
  avisar(quitar ? "Quitado de Mis colores." : "Guardado en Mis colores.", "exito");
  pintarFilas();
  if (!favoritosEnServidor) {
    sincronizarFavoritos(); // quizás inició sesión recién: sube los del navegador
    return;
  }
  try {
    await fetch(quitar ? "/api/mis-colores/" + id : "/api/mis-colores", quitar
      ? { method: "DELETE" }
      : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ colores: [id] }) });
  } catch (error) { /* sin conexión: queda en el navegador */ }
});

async function sincronizarFavoritos() {
  try {
    const respuesta = await fetch("/api/mis-colores");
    const datos = await respuesta.json();
    if (!datos.sesion) return; // sin sesión: solo en este navegador
    let enCuenta = datos.colores;
    const faltan = favoritos.filter(function (id) { return !enCuenta.includes(id); });
    if (faltan.length) {
      const subida = await fetch("/api/mis-colores", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ colores: faltan }),
      });
      if (subida.ok) enCuenta = (await subida.json()).colores;
    }
    favoritosEnServidor = true;
    favoritos = [...new Set(enCuenta.concat(favoritos))].filter(function (id) { return porId[id]; });
    guardarLista(CLAVE_FAVORITOS, favoritos);
    pintarFilas();
  } catch (error) { /* seguimos con los del navegador */ }
}

/* -------- 11. DESCARGAR IMAGEN Y COMPARTIR -------- */
function descargarArchivo(blob, nombre) {
  const url = URL.createObjectURL(blob);
  const enlace = document.createElement("a");
  enlace.href = url;
  enlace.download = nombre;
  document.body.appendChild(enlace);
  enlace.click();
  enlace.remove();
  setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
}

/* Convierte el dibujo SVG (con sus colores) en una imagen para el canvas.
   Dentro de la imagen se escriben los modos de mezcla, que en la página
   vienen de estilos.css. */
function svgComoImagen(svg, ancho, alto) {
  const copia = svg.cloneNode(true);
  copia.setAttribute("width", ancho);
  copia.setAttribute("height", alto);
  const estilo = document.createElementNS("http://www.w3.org/2000/svg", "style");
  estilo.textContent = ".capa-sombra{mix-blend-mode:multiply}.capa-luz{mix-blend-mode:screen}";
  copia.insertBefore(estilo, copia.firstChild);
  const texto = new XMLSerializer().serializeToString(copia);
  const imagen = new Image();
  imagen.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(texto);
  return imagen.decode().then(function () { return imagen; });
}

/* Franja al pie de la imagen: marca, colores y el aviso de colores referenciales */
function dibujarPie(ctx, ancho, alto, lineas) {
  const alturaPie = Math.round(alto * 0.075) + 18 * (lineas.length - 1);
  ctx.fillStyle = "rgba(20, 17, 13, 0.78)";
  ctx.fillRect(0, alto - alturaPie, ancho, alturaPie);
  ctx.fillStyle = "#FFFFFF";
  const tamano = Math.max(13, Math.round(ancho / 70));
  ctx.font = `600 ${tamano}px "Instrument Sans", system-ui, sans-serif`;
  ctx.textBaseline = "middle";
  const margen = Math.round(ancho * 0.02);
  lineas.forEach(function (linea, i) {
    ctx.font = `${i === lineas.length - 1 ? 400 : 600} ${tamano}px "Instrument Sans", system-ui, sans-serif`;
    ctx.fillText(linea, margen, alto - alturaPie + (i + 0.5) * alturaPie / lineas.length, ancho - margen * 2);
  });
}

async function descargar() {
  await document.fonts.ready;
  const aviso = "Pinturas Ecocordi · Colores referenciales: pide una muestra en sucursal.";
  let lienzoFinal;
  if (modo === "ambiente") {
    const ancho = 1800, alto = 1200;
    lienzoFinal = document.createElement("canvas");
    lienzoFinal.width = ancho;
    lienzoFinal.height = alto;
    const ctx = lienzoFinal.getContext("2d");
    ctx.drawImage(await svgComoImagen(escenaA.querySelector("svg"), ancho, alto), 0, 0);
    if (comparando) {
      const x = ancho * Number($("deslizador").value) / 100;
      ctx.save();
      ctx.beginPath();
      ctx.rect(x, 0, ancho - x, alto);
      ctx.clip();
      ctx.drawImage(await svgComoImagen(escenaB.querySelector("svg"), ancho, alto), 0, 0);
      ctx.restore();
      ctx.fillStyle = "#FFFFFF";
      ctx.fillRect(x - 2, 0, 4, alto);
    }
    const partes = zonasDe(ambiente).map(function (z) {
      const c = porId[(pintado[ambiente] || {})[z.id]];
      return c ? `${z.nombre}: ${c.nombre} (${c.codigo})` : null;
    }).filter(Boolean);
    if (comparando && porId[pintadoB[zonaActiva]]) partes.push("B: " + porId[pintadoB[zonaActiva]].nombre);
    dibujarPie(ctx, ancho, alto, [partes.join(" · ") || AMBIENTES[ambiente].nombre, aviso]);
  } else {
    if (!foto.original) return;
    await componer();
    lienzoFinal = document.createElement("canvas");
    lienzoFinal.width = foto.ancho;
    lienzoFinal.height = foto.alto;
    const ctx = lienzoFinal.getContext("2d");
    ctx.drawImage(lienzo, 0, 0);
    const usados = foto.zonas.map(function (z, i) {
      const c = porId[z.colorId];
      return c ? `Zona ${i + 1}: ${c.nombre} (${c.codigo})` : null;
    }).filter(Boolean);
    dibujarPie(ctx, foto.ancho, foto.alto, [usados.join(" · ") || "Tu foto", aviso]);
  }
  // La imagen se arma aquí mismo y se guarda en tu equipo: no pasa por el servidor
  lienzoFinal.toBlob(function (blob) {
    descargarArchivo(blob, modo === "ambiente" ? `ecocordi-${ambiente}.png` : "ecocordi-mi-foto.png");
  }, "image/png");
}

async function compartir() {
  actualizarDireccion();
  const url = location.href;
  const tactil = window.matchMedia("(pointer: coarse)").matches;
  if (navigator.share && tactil) {
    try {
      await navigator.share({ title: "Mis colores Ecocordi", url: url });
      return;
    } catch (error) { /* canceló: probamos copiar */ }
  }
  try {
    await navigator.clipboard.writeText(url);
    avisar(modo === "foto"
      ? "Enlace copiado. Incluye los colores, no tu foto."
      : "Enlace copiado: quien lo abra verá este ambiente con tus colores.", "exito");
  } catch (error) {
    avisar("Copia este enlace:\n" + url, "info", 12000);
  }
}

document.querySelectorAll("[data-descargar]").forEach(function (b) { b.addEventListener("click", descargar); });
document.querySelectorAll("[data-compartir]").forEach(function (b) { b.addEventListener("click", compartir); });

/* -------- 12. PESTAÑAS (Ambientes / Tu propia foto) -------- */
function elegirModo(nuevo, enfocar) {
  modo = nuevo;
  [["ambiente", "tabAmbientes", "modoAmbientes"], ["foto", "tabFoto", "modoFoto"]].forEach(function (m) {
    const activo = m[0] === modo;
    $(m[1]).setAttribute("aria-selected", String(activo));
    $(m[1]).tabIndex = activo ? 0 : -1;
    $(m[2]).classList.toggle("oculto", !activo);
    if (activo && enfocar) $(m[1]).focus();
  });
  colocarPanel();
  const color = porId[colorDeZonaActual()];
  if (color) mostrarColor(color);
  pintarPaleta();
  actualizarDireccion();
}
$("tabAmbientes").addEventListener("click", function () { elegirModo("ambiente"); });
$("tabFoto").addEventListener("click", function () { elegirModo("foto"); });
document.querySelector(".modos").addEventListener("keydown", function (e) {
  if (e.key === "ArrowRight" || e.key === "ArrowLeft") elegirModo(modo === "ambiente" ? "foto" : "ambiente", true);
});

/* -------- 12b. CELULARES --------
   En pantallas angostas la paleta queda DENTRO de la sección, justo debajo
   del dibujo, y el dibujo se queda fijo arriba (position: sticky, ver CSS):
   así se ve el cambio de color mientras se recorre la paleta. */
const panelLateral = document.querySelector(".visualizador__panel");
const pantallaAngosta = window.matchMedia("(max-width: 1000px)");
function colocarPanel() {
  if (pantallaAngosta.matches) {
    if (modo === "ambiente") {
      const herramientas = $("modoAmbientes").querySelector(".herramientas");
      herramientas.parentNode.insertBefore(panelLateral, herramientas);
    } else {
      $("modoFoto").appendChild(panelLateral);
    }
  } else if (panelLateral.parentNode !== document.querySelector(".visualizador__grid")) {
    document.querySelector(".visualizador__grid").appendChild(panelLateral);
  }
  // Alto real de la cabecera (en el celular puede tener dos filas)
  document.documentElement.style.setProperty("--alto-cabecera-real", document.getElementById("cabecera").offsetHeight + "px");
}
pantallaAngosta.addEventListener("change", colocarPanel);
window.addEventListener("resize", colocarPanel);

/* -------- 13. ARRANQUE -------- */
async function iniciar() {
  try {
    const datos = await (await fetch("/api/colores")).json();
    colores = datos.colores.filter(function (c) { return hexValido(c.hex); });
    familias = datos.familias;
    colores.forEach(function (c) { porId[c.id] = c; });
  } catch (error) {
    grilla.innerHTML = '<p class="paleta__vacio">No pudimos cargar los colores. ¿Está encendido el servidor?</p>';
    return;
  }
  recientes = recientes.filter(function (id) { return porId[id]; });
  const params = leerDireccion();
  if (productoFiltro && !params.get("ambiente")) {
    await catalogoListo;
    const producto = productos.find(function (p) { return p.id === productoFiltro; });
    if (producto) ambiente = AMBIENTE_DE_SUPERFICIE[producto.superficies[0]] || "living";
  }
  pintarFamilias();
  pintarFiltroProducto();
  await catalogoListo;
  await cargarAmbiente(ambiente);
  elegirModo(modo);
  const color = porId[colorDeZonaActual()] || porId[recientes[0]];
  if (color) mostrarColor(color);
  sincronizarFavoritos();
}

iniciar();
