/*
 * Relatorio de producao: enviar o PDF anexado pelo WhatsApp.
 *
 * No celular (Android/iPhone) o navegador abre o "Compartilhar" com o arquivo PDF;
 * a pessoa escolhe o WhatsApp e o contato. Onde isso nao existe (computador), o
 * botao segue o link normal: WhatsApp com a mensagem e os links do PDF e do Excel.
 *
 * O PDF e baixado antes do toque porque o navegador so permite compartilhar logo
 * apos o toque; esperar o servidor gerar o arquivo depois do toque faria falhar.
 */
(function () {
  "use strict";

  var button = document.querySelector("[data-share-pdf]");
  if (!button || !navigator.canShare || !window.File || !window.fetch) return;

  var probe;
  try {
    probe = new File(["x"], "teste.pdf", { type: "application/pdf" });
  } catch (error) {
    return;
  }
  if (!navigator.canShare({ files: [probe] })) return;

  var hint = document.querySelector("[data-share-hint]");
  var pdfFile = null;
  var loading = null;

  function loadPdf() {
    if (!loading) {
      loading = fetch(button.getAttribute("data-share-pdf"), { credentials: "same-origin", cache: "no-store" })
        .then(function (response) {
          if (!response.ok) throw new Error("pdf " + response.status);
          return response.blob();
        })
        .then(function (blob) {
          pdfFile = new File([blob], button.getAttribute("data-share-name") || "relatorio.pdf", { type: "application/pdf" });
          return pdfFile;
        })
        .catch(function () {
          loading = null;
          return null;
        });
    }
    return loading;
  }

  // Ja deixa o PDF pronto alguns segundos depois de abrir a pagina.
  setTimeout(loadPdf, 1200);

  button.addEventListener("click", function (event) {
    if (!pdfFile) {
      // Ainda gerando (ou falhou): segue pelo link com a mensagem e os links.
      loadPdf();
      return;
    }
    event.preventDefault();
    navigator
      .share({ files: [pdfFile], title: button.getAttribute("data-share-text"), text: button.getAttribute("data-share-text") })
      .catch(function (error) {
        if (error && error.name === "AbortError") return; // a pessoa cancelou
        if (hint) hint.textContent = "Não deu para anexar o PDF aqui. Abrindo o WhatsApp com o link do PDF.";
        window.open(button.href, "_blank", "noopener");
      });
  });
})();
