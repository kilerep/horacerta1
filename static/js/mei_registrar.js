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
  var defaultPunchLabel = punchLabel ? punchLabel.textContent : "Registrar horario";
  var geoLatitudeInput = document.getElementById("hcGeoLatitude");
  var geoLongitudeInput = document.getElementById("hcGeoLongitude");
  var geoAccuracyInput = document.getElementById("hcGeoAccuracy");

  var manualOpenBtn = document.getElementById("hcManualOpen");
  var manualModal = document.getElementById("hcManualModal");
  var manualOverlay = document.getElementById("hcManualOverlay");
  var manualCloseTop = document.getElementById("hcManualCloseTop");
  var manualCancel = document.getElementById("hcManualCancel");
  var manualForm = document.getElementById("hcManualForm");
  var manualSaveBtn = document.getElementById("hcManualSave");
  var manualErrors = document.getElementById("hcManualErrors");
  var manualContract = document.getElementById("hcManualContract");
  var manualDate = document.getElementById("hcManualDate");
  var timesList = document.getElementById("hcTimesList");
  var addTimeBtn = document.getElementById("hcAddTimeBtn");

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
      badgeEl.textContent = "Sem horarios hoje";
      badgeEl.classList.add("hc-badge--neutral");
      if (badgeHint) badgeHint.textContent = "Registre o primeiro horario para iniciar o dia.";
      return;
    }

    if (count % 2 === 0) {
      badgeEl.textContent = "Dia completo";
      badgeEl.classList.add("hc-badge--ok");
      if (badgeHint) badgeHint.textContent = "Todos os horarios de hoje estao pareados.";
      return;
    }

    badgeEl.textContent = "Dia em andamento";
    badgeEl.classList.add("hc-badge--warn");
    if (badgeHint) badgeHint.textContent = "Existe um horario sem par ate o momento.";
  }

  function setSubmittingState(isLoading) {
    if (!punchBtn || !punchLabel) return;
    if (isLoading) {
      punchBtn.disabled = true;
      punchBtn.classList.add("is-loading");
      punchBtn.setAttribute("aria-busy", "true");
      punchLabel.textContent = "Registrando horário...";
      return;
    }
    punchBtn.disabled = false;
    punchBtn.classList.remove("is-loading");
    punchBtn.removeAttribute("aria-busy");
    punchLabel.textContent = defaultPunchLabel;
  }

  function bindPunchSubmit() {
    if (!form || !punchBtn) return;
    form.dataset.submitting = "0";
    form.dataset.geoReady = "0";

    function clearGeoFields() {
      if (geoLatitudeInput) geoLatitudeInput.value = "";
      if (geoLongitudeInput) geoLongitudeInput.value = "";
      if (geoAccuracyInput) geoAccuracyInput.value = "";
    }

    function submitWithGeo(coords) {
      clearGeoFields();
      if (coords) {
        if (geoLatitudeInput && typeof coords.latitude === "number") {
          geoLatitudeInput.value = String(coords.latitude.toFixed(6));
        }
        if (geoLongitudeInput && typeof coords.longitude === "number") {
          geoLongitudeInput.value = String(coords.longitude.toFixed(6));
        }
        if (geoAccuracyInput && typeof coords.accuracy === "number") {
          geoAccuracyInput.value = String(Math.round(coords.accuracy * 100) / 100);
        }
      }
      form.dataset.geoReady = "1";
      form.submit();
    }

    function resolveGeolocationAndSubmit() {
      if (!navigator.geolocation) {
        submitWithGeo(null);
        return;
      }

      var completed = false;
      function complete(coords) {
        if (completed) return;
        completed = true;
        submitWithGeo(coords);
      }

      var fallbackTimer = window.setTimeout(function () {
        complete(null);
      }, 2600);

      navigator.geolocation.getCurrentPosition(
        function (position) {
          window.clearTimeout(fallbackTimer);
          complete(position && position.coords ? position.coords : null);
        },
        function () {
          window.clearTimeout(fallbackTimer);
          complete(null);
        },
        {
          enableHighAccuracy: false,
          timeout: 2200,
          maximumAge: 60000
        }
      );
    }

    form.addEventListener("submit", function (event) {
      if (form.dataset.geoReady === "1") {
        return;
      }

      event.preventDefault();
      if (form.dataset.submitting === "1") {
        return;
      }

      form.dataset.submitting = "1";
      setSubmittingState(true);
      resolveGeolocationAndSubmit();
    });

    form.addEventListener(
      "invalid",
      function () {
        form.dataset.submitting = "0";
        form.dataset.geoReady = "0";
        clearGeoFields();
        setSubmittingState(false);
      },
      true
    );

    window.addEventListener("pageshow", function () {
      form.dataset.submitting = "0";
      form.dataset.geoReady = "0";
      clearGeoFields();
      setSubmittingState(false);
    });
  }

  function showManualErrors(messages) {
    if (!manualErrors) return;
    if (!messages || !messages.length) {
      manualErrors.hidden = true;
      manualErrors.innerHTML = "";
      return;
    }
    manualErrors.hidden = false;
    manualErrors.innerHTML = messages
      .map(function (message) {
        return "<div>" + message + "</div>";
      })
      .join("");
  }

  function syncRemoveButtons() {
    if (!timesList) return;
    var rows = timesList.querySelectorAll(".hc-time-row");
    for (var i = 0; i < rows.length; i += 1) {
      var removeBtn = rows[i].querySelector(".hc-time-remove");
      if (!removeBtn) continue;
      var shouldDisable = rows.length === 1;
      removeBtn.disabled = shouldDisable;
      removeBtn.hidden = shouldDisable;
    }
  }

  function addTimeRow(defaultValue) {
    if (!timesList) return;

    var row = document.createElement("div");
    row.className = "hc-time-row";

    var input = document.createElement("input");
    input.type = "time";
    input.name = "times";
    input.step = "60";
    input.required = true;
    if (defaultValue) input.value = defaultValue;

    var removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "btn hc-time-remove";
    removeBtn.setAttribute("aria-label", "Remover horario");
    removeBtn.textContent = "Remover";
    removeBtn.addEventListener("click", function () {
      row.remove();
      syncRemoveButtons();
    });

    row.appendChild(input);
    row.appendChild(removeBtn);
    timesList.appendChild(row);
    syncRemoveButtons();
  }

  function openManualModal() {
    if (!manualModal) return;
    manualModal.classList.add("is-open");
    manualModal.setAttribute("aria-hidden", "false");
    document.body.classList.add("hc-modal-open");
    showManualErrors([]);

    if (timesList && !timesList.querySelector(".hc-time-row")) {
      addTimeRow("");
    } else {
      syncRemoveButtons();
    }
  }

  function closeManualModal() {
    if (!manualModal) return;
    manualModal.classList.remove("is-open");
    manualModal.setAttribute("aria-hidden", "true");
    document.body.classList.remove("hc-modal-open");
    showManualErrors([]);
  }

  function bindManualModal() {
    if (!manualModal || !manualForm) return;

    if (manualOpenBtn) {
      manualOpenBtn.addEventListener("click", openManualModal);
    }
    if (manualOverlay) {
      manualOverlay.addEventListener("click", closeManualModal);
    }
    if (manualCloseTop) {
      manualCloseTop.addEventListener("click", closeManualModal);
    }
    if (manualCancel) {
      manualCancel.addEventListener("click", closeManualModal);
    }

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && manualModal.classList.contains("is-open")) {
        closeManualModal();
      }
    });

    if (addTimeBtn) {
      addTimeBtn.addEventListener("click", function () {
        addTimeRow("");
      });
    }

    if (timesList) {
      var initialRows = timesList.querySelectorAll(".hc-time-row");
      for (var i = 0; i < initialRows.length; i += 1) {
        (function bindRowRemove(row) {
          var btn = row.querySelector(".hc-time-remove");
          if (!btn) return;
          btn.addEventListener("click", function () {
            row.remove();
            syncRemoveButtons();
          });
        })(initialRows[i]);
      }
      syncRemoveButtons();
    }

    manualForm.addEventListener("submit", function (event) {
      event.preventDefault();
      showManualErrors([]);

      var selectedContract = manualContract ? (manualContract.value || "").trim() : "";
      var selectedDate = manualDate ? (manualDate.value || "").trim() : "";
      var timeInputs = timesList ? timesList.querySelectorAll('input[name="times"]') : [];
      var times = [];
      for (var idx = 0; idx < timeInputs.length; idx += 1) {
        var value = (timeInputs[idx].value || "").trim();
        if (value) times.push(value);
      }

      var clientErrors = [];
      if (!selectedContract) clientErrors.push("Selecione cliente e contrato.");
      if (!selectedDate) clientErrors.push("Informe a data do registro.");
      if (!times.length) clientErrors.push("Informe pelo menos 1 horario.");

      if (clientErrors.length) {
        showManualErrors(clientErrors);
        return;
      }

      var payload = new FormData();
      var csrfInput = manualForm.querySelector('input[name="csrfmiddlewaretoken"]');
      if (csrfInput) payload.append("csrfmiddlewaretoken", csrfInput.value);
      payload.append("contract", selectedContract);
      payload.append("manual_date", selectedDate);
      for (var j = 0; j < times.length; j += 1) {
        payload.append("times", times[j]);
      }

      if (manualSaveBtn) {
        manualSaveBtn.disabled = true;
        manualSaveBtn.textContent = "Salvando...";
      }

      fetch(manualForm.getAttribute("action"), {
        method: "POST",
        body: payload,
        credentials: "same-origin",
        headers: {
          "X-Requested-With": "XMLHttpRequest"
        }
      })
        .then(function (response) {
          return response.json().catch(function () {
            return { ok: false, errors: ["Falha ao processar resposta do servidor."] };
          });
        })
        .then(function (data) {
          if (!data || !data.ok) {
            var backendErrors = data && data.errors && data.errors.length ? data.errors : ["Nao foi possivel salvar o lancamento manual."];
            showManualErrors(backendErrors);
            return;
          }

          closeManualModal();
          var nextUrl =
            window.location.pathname +
            "?contract=" +
            encodeURIComponent(selectedContract) +
            "&event=manual_saved&created=" +
            encodeURIComponent(String(data.created_count || times.length));
          window.location.assign(nextUrl);
        })
        .catch(function () {
          showManualErrors(["Erro de rede ao enviar lancamento manual."]);
        })
        .finally(function () {
          if (manualSaveBtn) {
            manualSaveBtn.disabled = false;
            manualSaveBtn.textContent = "Salvar registro manual";
          }
        });
    });
  }

  applyDayBadge();
  applyGreetingAndDate(new Date());
  renderClock();
  bindPunchSubmit();
  bindManualModal();

  setInterval(renderClock, 1000);
  setInterval(function () {
    applyGreetingAndDate(new Date());
  }, 30000);
})();

