/*
 * Tour guiado generico (baloes explicativos por elemento da tela).
 *
 * Uso: window.HoraCertaTour.start({
 *   tourKey: "mei_panel",
 *   dismissUrl: "/me/tour/dispensar/",
 *   csrfToken: "...",
 *   steps: [{selector: ".summary-hero", title: "...", text: "..."}, ...],
 * });
 *
 * Passos cujo seletor nao existe na pagina (ex.: card de onboarding ja
 * concluido e escondido) sao pulados sem quebrar o tour.
 */
(function () {
  var STYLE_ID = "hc-tour-style";
  var OVERLAY_ID = "hc-tour-overlay";

  function ensureStyle() {
    if (document.getElementById(STYLE_ID)) return;
    var style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = [
      "#" + OVERLAY_ID + "{position:fixed;inset:0;z-index:3000;background:rgba(3,7,20,.55);}",
      ".hc-tour-highlight{position:relative;z-index:3001;outline:3px solid var(--color-primary-strong,#3b82f6);outline-offset:4px;border-radius:10px;box-shadow:0 0 0 9999px rgba(3,7,20,.55);}",
      ".hc-tour-bubble{position:fixed;z-index:3002;max-width:min(340px,86vw);background:var(--color-card,#111a2e);color:var(--text,#f3f6fb);border:1px solid var(--line,rgba(255,255,255,.14));border-radius:14px;padding:14px;box-shadow:0 18px 40px rgba(0,0,0,.45);font-size:14px;line-height:1.45;}",
      ".hc-tour-bubble h3{margin:0 0 6px;font-size:15px;}",
      ".hc-tour-bubble p{margin:0 0 12px;color:var(--muted,#9aa7c2);}",
      ".hc-tour-bubble__footer{display:flex;align-items:center;justify-content:space-between;gap:10px;}",
      ".hc-tour-bubble__step{font-size:12px;color:var(--muted,#9aa7c2);white-space:nowrap;}",
      ".hc-tour-bubble__actions{display:flex;gap:8px;}",
      ".hc-tour-bubble button{border-radius:10px;padding:8px 12px;font:inherit;font-weight:800;cursor:pointer;border:1px solid var(--line,rgba(255,255,255,.14));background:transparent;color:inherit;}",
      ".hc-tour-bubble button.hc-tour-primary{background:var(--color-primary-strong,#3b82f6);border-color:var(--color-primary-strong,#3b82f6);color:#fff;}",
    ].join("\n");
    document.head.appendChild(style);
  }

  function postDismiss(dismissUrl, csrfToken, tourKey) {
    if (!dismissUrl) return;
    try {
      var body = new URLSearchParams();
      body.set("tour", tourKey);
      fetch(dismissUrl, {
        method: "POST",
        headers: { "X-CSRFToken": csrfToken, "Content-Type": "application/x-www-form-urlencoded" },
        body: body.toString(),
        credentials: "same-origin",
      });
    } catch (error) {
      // Falha silenciosa: o pior caso e o tour aparecer de novo na proxima visita.
    }
  }

  function positionBubble(bubble, targetRect) {
    var margin = 12;
    var bubbleRect = bubble.getBoundingClientRect();
    var top = targetRect.bottom + margin;
    if (top + bubbleRect.height > window.innerHeight - margin) {
      top = targetRect.top - bubbleRect.height - margin;
    }
    if (top < margin) top = margin;

    var left = targetRect.left;
    if (left + bubbleRect.width > window.innerWidth - margin) {
      left = window.innerWidth - bubbleRect.width - margin;
    }
    if (left < margin) left = margin;

    bubble.style.top = top + "px";
    bubble.style.left = left + "px";
  }

  function start(config) {
    var steps = (config.steps || [])
      .map(function (step) {
        return { step: step, el: document.querySelector(step.selector) };
      })
      .filter(function (item) {
        return !!item.el;
      });

    if (!steps.length) return;

    ensureStyle();
    var overlay = document.createElement("div");
    overlay.id = OVERLAY_ID;
    document.body.appendChild(overlay);

    var index = 0;
    var currentHighlight = null;

    function clearHighlight() {
      if (currentHighlight) currentHighlight.classList.remove("hc-tour-highlight");
      var bubble = document.querySelector(".hc-tour-bubble");
      if (bubble) bubble.remove();
    }

    function reposition() {
      var bubble = document.querySelector(".hc-tour-bubble");
      if (!bubble || !currentHighlight) return;
      positionBubble(bubble, currentHighlight.getBoundingClientRect());
    }

    // A pessoa pode rolar a tela manualmente enquanto o balao esta aberto
    // (a tela do Meu Resumo e mais alta que a viewport) - sem isso o balao
    // ficava "grudado" no lugar antigo em vez de seguir o elemento marcado.
    window.addEventListener("scroll", reposition, true);
    window.addEventListener("resize", reposition);

    function finish() {
      clearHighlight();
      overlay.remove();
      window.removeEventListener("scroll", reposition, true);
      window.removeEventListener("resize", reposition);
      postDismiss(config.dismissUrl, config.csrfToken, config.tourKey);
    }

    function renderStep() {
      clearHighlight();
      var current = steps[index];
      current.el.scrollIntoView({ block: "center", behavior: "smooth" });
      current.el.classList.add("hc-tour-highlight");
      currentHighlight = current.el;

      var bubble = document.createElement("div");
      bubble.className = "hc-tour-bubble";
      var isLast = index === steps.length - 1;
      bubble.innerHTML =
        "<h3>" + current.step.title + "</h3>" +
        "<p>" + current.step.text + "</p>" +
        '<div class="hc-tour-bubble__footer">' +
        '<span class="hc-tour-bubble__step">' + (index + 1) + " de " + steps.length + "</span>" +
        '<div class="hc-tour-bubble__actions">' +
        '<button type="button" data-tour-action="skip">Pular tour</button>' +
        '<button type="button" class="hc-tour-primary" data-tour-action="next">' + (isLast ? "Concluir" : "Próximo") + "</button>" +
        "</div></div>";
      document.body.appendChild(bubble);

      window.requestAnimationFrame(function () {
        positionBubble(bubble, current.el.getBoundingClientRect());
      });

      bubble.querySelector('[data-tour-action="skip"]').addEventListener("click", finish);
      bubble.querySelector('[data-tour-action="next"]').addEventListener("click", function () {
        if (isLast) {
          finish();
        } else {
          index += 1;
          renderStep();
        }
      });
    }

    renderStep();
  }

  window.HoraCertaTour = { start: start };
})();
