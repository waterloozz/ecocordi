/* ============================================================
   ECOCORDI - "Luz de ventana"
   El mismo color no se ve igual en la mañana, la tarde o la noche.
   Este archivo decide con qué luz se muestra la página:
     1. Si la persona ya eligió una luz, usamos esa (se guarda en el navegador).
     2. Si no, usamos la hora real: 6-12 mañana, 13-19 tarde, 20-5 noche.
   Se carga en el <head> (sin "defer") para aplicar la luz ANTES de que
   la página se dibuje: así no hay un parpadeo de claro a oscuro.
   ============================================================ */

const LUCES = ["manana", "tarde", "noche"];
const NOMBRES_LUZ = { manana: "Mañana", tarde: "Tarde", noche: "Noche" };

function luzSegunHora(fecha) {
  const hora = (fecha || new Date()).getHours();
  if (hora >= 6 && hora < 13) return "manana";
  if (hora >= 13 && hora < 20) return "tarde";
  return "noche";
}

function luzGuardada() {
  // localStorage puede fallar (modo privado, permisos): en ese caso, la hora manda
  try {
    const guardada = localStorage.getItem("luz_ecocordi");
    return LUCES.includes(guardada) ? guardada : null;
  } catch (e) {
    return null;
  }
}

function aplicarLuz(luz) {
  document.documentElement.dataset.luz = luz;
  // Los botones que eligen la luz muestran cuál está activa
  document.querySelectorAll("[data-elegir-luz]").forEach(function (boton) {
    boton.setAttribute("aria-pressed", boton.dataset.elegirLuz === luz ? "true" : "false");
  });
  const etiqueta = document.getElementById("luzActual");
  if (etiqueta) etiqueta.textContent = NOMBRES_LUZ[luz].toLowerCase(); // "Luz de mañana"
}

// 1) Apenas se carga este archivo: aplicamos la luz (todavía no hay botones)
aplicarLuz(luzGuardada() || luzSegunHora());

// 2) Cuando el HTML ya existe: conectamos los botones "Mañana / Tarde / Noche"
document.addEventListener("DOMContentLoaded", function () {
  aplicarLuz(document.documentElement.dataset.luz);
  document.addEventListener("click", function (evento) {
    const boton = evento.target.closest("[data-elegir-luz]");
    if (!boton) return;
    const luz = boton.dataset.elegirLuz;
    try { localStorage.setItem("luz_ecocordi", luz); } catch (e) { /* sin memoria: igual funciona */ }
    aplicarLuz(luz);
  });
});
