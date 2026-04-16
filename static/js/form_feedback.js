(function () {
  function setLoadingState(form, isLoading) {
    var buttons = form.querySelectorAll('button[type="submit"], input[type="submit"]');
    for (var i = 0; i < buttons.length; i += 1) {
      var button = buttons[i];
      var loadingText = button.getAttribute("data-loading-text");
      if (isLoading) {
        button.dataset.originalText = button.tagName === "BUTTON" ? button.textContent : button.value;
        button.disabled = true;
        button.setAttribute("aria-busy", "true");
        if (loadingText) {
          if (button.tagName === "BUTTON") button.textContent = loadingText;
          else button.value = loadingText;
        }
      } else {
        button.disabled = false;
        button.removeAttribute("aria-busy");
        if (button.dataset.originalText) {
          if (button.tagName === "BUTTON") button.textContent = button.dataset.originalText;
          else button.value = button.dataset.originalText;
        }
      }
    }
  }

  function bindForm(form) {
    form.addEventListener("submit", function (event) {
      if (form.dataset.submitting === "1") {
        event.preventDefault();
        return;
      }
      form.dataset.submitting = "1";
      setLoadingState(form, true);
    });
  }

  var forms = document.querySelectorAll("form[data-submit-once='true']");
  for (var i = 0; i < forms.length; i += 1) {
    bindForm(forms[i]);
  }

  window.addEventListener("pageshow", function () {
    for (var i = 0; i < forms.length; i += 1) {
      forms[i].dataset.submitting = "0";
      setLoadingState(forms[i], false);
    }
  });
})();
