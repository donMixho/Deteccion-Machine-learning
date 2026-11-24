/* AppleVision Chile — comportamiento de la plataforma (sin librerías) */
(function () {
  "use strict";

  /* ---------- tooltip de los gráficos: cualquier elemento con data-tip ---------- */
  var tip = document.getElementById("tooltip");
  function mostrarTip(el, x, y) {
    if (!tip) return;
    tip.textContent = el.getAttribute("data-tip");
    tip.classList.add("visible");
    var r = tip.getBoundingClientRect();
    var izq = Math.min(Math.max(8, x - r.width / 2), window.innerWidth - r.width - 8);
    var arriba = y - r.height - 12;
    if (arriba < 8) arriba = y + 18;
    tip.style.left = izq + "px";
    tip.style.top = arriba + "px";
  }
  function ocultarTip() { if (tip) tip.classList.remove("visible"); }
  document.addEventListener("mousemove", function (e) {
    var el = e.target.closest && e.target.closest("[data-tip]");
    if (el) mostrarTip(el, e.clientX, e.clientY); else ocultarTip();
  });
  document.addEventListener("focusin", function (e) {
    var el = e.target.closest && e.target.closest("[data-tip]");
    if (!el) return;
    var r = el.getBoundingClientRect();
    mostrarTip(el, r.left + r.width / 2, r.top);
  });
  document.addEventListener("focusout", ocultarTip);
  window.addEventListener("scroll", ocultarTip, { passive: true });

  /* ---------- zona de archivo: nombre elegido + campos solo para video ---------- */
  var EXT_VIDEO = ["mp4", "avi", "mov", "mkv", "wmv", "webm"];
  document.querySelectorAll(".zona-archivo").forEach(function (zona) {
    var input = zona.querySelector("input[type=file]");
    var nombre = zona.querySelector(".nombre-archivo");
    var form = zona.closest("form");
    function actualizar() {
      var archivo = input.files && input.files[0];
      var esVideo = false;
      if (archivo) {
        var ext = archivo.name.split(".").pop().toLowerCase();
        esVideo = EXT_VIDEO.indexOf(ext) >= 0;
        var mb = (archivo.size / 1048576).toFixed(1).replace(".", ",");
        if (nombre) nombre.textContent = (esVideo ? "Video: " : "Foto: ") + archivo.name + " (" + mb + " MB)";
      } else if (nombre) {
        nombre.textContent = "";
      }
      if (form) form.querySelectorAll(".solo-video").forEach(function (el) { el.hidden = !esVideo; });
    }
    input.addEventListener("change", actualizar);
    ["dragenter", "dragover"].forEach(function (ev) {
      zona.addEventListener(ev, function () { zona.classList.add("activa"); });
    });
    ["dragleave", "drop"].forEach(function (ev) {
      zona.addEventListener(ev, function () { zona.classList.remove("activa"); });
    });
    actualizar();
  });

  /* ---------- deslizadores con valor visible ---------- */
  document.querySelectorAll(".rango").forEach(function (r) {
    var input = r.querySelector("input[type=range]");
    var salida = r.querySelector("output");
    function pintar() { salida.textContent = input.value + " %"; }
    input.addEventListener("input", pintar);
    pintar();
  });

  /* ---------- confirmaciones ---------- */
  document.addEventListener("submit", function (e) {
    var form = e.target;
    var mensaje = form.getAttribute("data-confirmar");
    var boton = e.submitter;
    if (boton && boton.getAttribute("data-confirmar")) mensaje = boton.getAttribute("data-confirmar");
    if (mensaje && !window.confirm(mensaje)) { e.preventDefault(); return; }
    if (form.hasAttribute("data-subida")) {   // evita doble envío mientras sube un video grande
      var b = form.querySelector("button[type=submit]");
      if (b) { b.disabled = true; b.textContent = "Subiendo…"; }
    }
  });

  /* ---------- seguimiento de análisis en curso ---------- */
  var enCurso = document.querySelectorAll("[data-analisis][data-estado='en_cola'], [data-analisis][data-estado='procesando']");
  enCurso.forEach(function (el) {
    var id = el.getAttribute("data-analisis");
    var barra = el.querySelector(".progreso");
    var texto = el.querySelector(".progreso-texto");
    function consultar() {
      fetch("/api/analisis/" + id, { headers: { "Accept": "application/json" }, credentials: "same-origin" })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) {
          if (!d) return;
          if (d.estado === "listo" || d.estado === "error") { window.location.reload(); return; }
          if (d.estado === "procesando" && barra) {
            if (d.progreso > 0) {
              barra.classList.remove("indeterminado");
              barra.firstElementChild.style.width = d.progreso + "%";
              if (texto) texto.textContent = "Analizando con YOLO… " + d.progreso + " %";
            } else if (texto) {
              texto.textContent = "Analizando con YOLO…";
            }
          } else if (d.estado === "en_cola" && texto && d.posicion) {
            texto.textContent = "En cola: posición " + d.posicion;
          }
          setTimeout(consultar, 1500);
        })
        .catch(function () { setTimeout(consultar, 4000); });
    }
    setTimeout(consultar, 800);
  });

  /* ---------- tema: automático → claro → oscuro ---------- */
  var botonTema = document.getElementById("cambiar-tema");
  if (botonTema) {
    var nombres = { "": "Tema automático", light: "Tema claro", dark: "Tema oscuro" };
    function etiqueta() {
      var actual = document.documentElement.getAttribute("data-theme") || "";
      botonTema.setAttribute("title", nombres[actual] + " (clic para cambiar)");
      botonTema.setAttribute("aria-label", nombres[actual]);
    }
    botonTema.addEventListener("click", function () {
      var actual = document.documentElement.getAttribute("data-theme") || "";
      var siguiente = actual === "" ? "light" : actual === "light" ? "dark" : "";
      if (siguiente) document.documentElement.setAttribute("data-theme", siguiente);
      else document.documentElement.removeAttribute("data-theme");
      try { if (siguiente) localStorage.setItem("tema", siguiente); else localStorage.removeItem("tema"); } catch (e) { /* sin almacenamiento */ }
      etiqueta();
    });
    etiqueta();
  }
})();
