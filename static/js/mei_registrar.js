(function () {
  var greetingLine = document.getElementById("hcGreetingLine");
  var greetingSalute = greetingLine ? greetingLine.querySelector(".hc-greeting-salute") : null;
  var greetingName = greetingLine ? greetingLine.querySelector(".hc-greeting-name") : null;
  var dateLine = document.getElementById("hcDateLine");
  var clockEl = document.getElementById("hcClock");
  var badgeEl = document.getElementById("hcBadge");
  var badgeHint = document.getElementById("hcBadgeHint");
  var form = document.getElementById("hcPunchForm");
  var punchBtn = document.getElementById("hcPunchBtn");
  var punchLabel = punchBtn ? punchBtn.querySelector(".hc-punch-btn__label") : null;
  var obsToggle = document.getElementById("hcObsToggle");
  var obsWrap = document.getElementById("hcObsWrap");

  function getGreeting(hour) {
    if (hour >= 5 && hour <= 11) return "Bom dia";
    if (hour >= 12 && hour <= 17) return "Boa tarde";
    return "Boa noite";
  }

  function applyGreetingAndDate(now) {
    if (greetingLine) {
      var displayName = greetingLine.getAttribute("data-display-name") || "usuario";
      if (greetingSalute) {
        greetingSalute.textContent = getGreeting(now.getHours()) + ",";
      }
      if (greetingName) {
        greetingName.textContent = displayName;
      }
    }

    if (dateLine) {
      var dateLabel = new Intl.DateTimeFormat("pt-BR", {
        weekday: "long",
        day: "2-digit",
        month: "long",
        year: "numeric"
      }).format(now);
      dateLine.textContent = dateLabel.charAt(0).toUpperCase() + dateLabel.slice(1);
    }
  }

  function renderClock() {
    if (!clockEl) return;
    var now = new Date();
    var hh = String(now.getHours()).padStart(2, "0");
    var mm = String(now.getMinutes()).padStart(2, "0");
    clockEl.textContent = hh + ":" + mm;
  }

  function applyDayBadge() {
    if (!badgeEl) return;
    var rawCount = badgeEl.getAttribute("data-today-count");
    var count = Number(rawCount || "0");
    badgeEl.classList.remove("hc-badge--warn", "hc-badge--ok", "hc-badge--neutral");

    if (count === 0) {
      badgeEl.textContent = "Sem batidas hoje";
      badgeEl.classList.add("hc-badge--neutral");
      if (badgeHint) badgeHint.textContent = "Registre a primeira batida para iniciar o dia.";
      return;
    }

    if (count % 2 === 0) {
      badgeEl.textContent = "Dia completo";
      badgeEl.classList.add("hc-badge--ok");
      if (badgeHint) badgeHint.textContent = "Todas as batidas de hoje estao pareadas.";
      return;
    }

    badgeEl.textContent = "Dia em andamento";
    badgeEl.classList.add("hc-badge--warn");
    if (badgeHint) badgeHint.textContent = "Existe uma batida sem par ate o momento.";
  }

  function setSubmittingState(isLoading) {
    if (!punchBtn || !punchLabel) return;
    if (isLoading) {
      punchBtn.disabled = true;
      punchBtn.classList.add("is-loading");
      punchBtn.setAttribute("aria-busy", "true");
      punchLabel.textContent = "Registrando...";
      return;
    }
    punchBtn.disabled = false;
    punchBtn.classList.remove("is-loading");
    punchBtn.removeAttribute("aria-busy");
    punchLabel.textContent = "REGISTRAR BATIDA";
  }

  function bindPunchSubmit() {
    if (!form || !punchBtn) return;

    form.addEventListener("submit", function (event) {
      if (form.dataset.submitting === "1") {
        event.preventDefault();
        return;
      }

      form.dataset.submitting = "1";
      setSubmittingState(true);
    });

    form.addEventListener(
      "invalid",
      function () {
        form.dataset.submitting = "0";
        setSubmittingState(false);
      },
      true
    );

    window.addEventListener("pageshow", function () {
      form.dataset.submitting = "0";
      setSubmittingState(false);
    });
  }

  function bindObservationToggle() {
    if (!obsToggle || !obsWrap) return;

    obsToggle.addEventListener("click", function () {
      var isOpen = obsWrap.classList.toggle("is-open");
      obsWrap.setAttribute("aria-hidden", isOpen ? "false" : "true");
      obsToggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
      obsToggle.textContent = isOpen ? "Ocultar observacao" : "Adicionar observacao";
    });
  }

  applyDayBadge();
  applyGreetingAndDate(new Date());
  renderClock();
  bindPunchSubmit();
  bindObservationToggle();

  setInterval(renderClock, 1000);
  setInterval(function () {
    applyGreetingAndDate(new Date());
  }, 30000);
})();
