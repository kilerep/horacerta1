/*
 * Relatorio de producao: anotar o item falando.
 *
 * O celular transforma a fala em texto (Web Speech API, pt-BR) e o parser abaixo
 * preenche o formulario: codigo, guincho/implemento, inicio/fim ou duracao. Nada e
 * salvo sozinho: a pessoa confere os campos e toca em "Salvar item".
 *
 * Exemplos: "codigo 0011 024 implemento das 7 as 11"
 *           "guincho uma hora e meia"
 *           "codigo X 123 guincho comecei agora"
 */
(function (root) {
  "use strict";

  var NUMBERS = {
    zero: 0, um: 1, uma: 1, dois: 2, duas: 2, tres: 3, quatro: 4, cinco: 5, seis: 6, sete: 7, oito: 8,
    nove: 9, dez: 10, onze: 11, doze: 12, treze: 13, quatorze: 14, catorze: 14, quinze: 15, dezesseis: 16,
    dezessete: 17, dezoito: 18, dezenove: 19, vinte: 20, trinta: 30, quarenta: 40, cinquenta: 50,
  };

  function normalize(text) {
    return (text || "")
      .toLowerCase()
      .normalize("NFD").replace(/[̀-ͯ]/g, "")
      .replace(/(\d)\s*h\s*(\d{1,2})\b/g, "$1:$2")
      .replace(/(\d)\s*h\b/g, "$1 horas")
      .replace(/[,.;!?]/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  // "vinte e cinco" -> "25", "sete" -> "7" (so palavras de numero soltas)
  function wordsToDigits(text) {
    var tokens = text.split(" ");
    var out = [];
    for (var i = 0; i < tokens.length; i++) {
      var word = tokens[i];
      if (NUMBERS.hasOwnProperty(word)) {
        var value = NUMBERS[word];
        if (value >= 20 && tokens[i + 1] === "e" && NUMBERS.hasOwnProperty(tokens[i + 2]) && NUMBERS[tokens[i + 2]] < 10) {
          value += NUMBERS[tokens[i + 2]];
          i += 2;
        }
        out.push(String(value));
      } else {
        out.push(word);
      }
    }
    return out.join(" ");
  }

  function pad(n) { return (n < 10 ? "0" : "") + n; }

  function nowHHMM(now) {
    var d = now || new Date();
    return pad(d.getHours()) + ":" + pad(d.getMinutes());
  }

  // "7" / "7:30" / "7 e meia" / "7 e 15" -> "07:30"
  function readTime(text) {
    var m = text.match(/^(\d{1,2})(?::(\d{2}))?(?: e (meia|\d{1,2}))?/);
    if (!m) return null;
    var hours = parseInt(m[1], 10);
    var mins = m[2] ? parseInt(m[2], 10) : 0;
    if (m[3]) mins = m[3] === "meia" ? 30 : parseInt(m[3], 10);
    if (hours > 23 || mins > 59) return null;
    return pad(hours) + ":" + pad(mins);
  }

  var STOP = /\b(guincho|implemento|das|da|de|desde|comecei|comecou|inicio|terminei|terminou|fim|ate|as|a|durou|duracao|levou|obs|observacao)\b/;

  function parse(rawText, now) {
    var result = { code: "", destination: "", start: "", end: "", duration: "", note: "" };
    var text = wordsToDigits(normalize(rawText));
    if (!text) return result;
    var used = false;

    if (/\bguincho\b/.test(text)) { result.destination = "GUINCHO"; used = true; }
    else if (/\bimplementos?\b/.test(text)) { result.destination = "IMPLEMENTO"; used = true; }

    // codigo: tudo depois de "codigo"/"item"/"peca" ate a proxima palavra-chave
    var code = text.match(/\b(?:codigo|item|peca)\s+(.+)/);
    if (code) {
      var rest = code[1];
      var stop = rest.search(STOP);
      var raw = (stop >= 0 ? rest.slice(0, stop) : rest).trim();
      var parts = raw.split(" ").filter(Boolean).map(function (p) { return p === "traco" || p === "hifen" ? "-" : p; });
      var joined = parts.join(" ").replace(/\s*-\s*/g, "-");
      // "0011 024" -> "0011-024"; "x 123" -> "X 123"
      if (/^\d+( \d+)+$/.test(joined)) joined = joined.replace(/ /g, "-");
      // so vale como codigo se tiver algum numero ("peca quebrou" nao e codigo)
      if (/\d/.test(joined)) {
        result.code = joined.toUpperCase();
        used = true;
      }
    }

    // inicio e fim: "das 7 as 11", "de 7 e meia ate 11", "7:30 as 11:15"
    var range = text.match(/(?:\bdas?\b|\bde\b|\bdesde\b|^|\s)(\d{1,2}(?::\d{2})?(?: e (?:meia|\d{1,2}))?)\s+(?:as|a|ate)\s+(\d{1,2}(?::\d{2})?(?: e (?:meia|\d{1,2}))?)/);
    if (range) {
      var s = readTime(range[1]);
      var e = readTime(range[2]);
      if (s && e) { result.start = s; result.end = e; used = true; }
    }
    if (!result.start) {
      var started = text.match(/\b(?:comecei|comecou|inicio|iniciei)\b(?: (?:as|a))?\s*(agora|\d{1,2}(?::\d{2})?(?: e (?:meia|\d{1,2}))?)/);
      if (started) { result.start = started[1] === "agora" ? nowHHMM(now) : (readTime(started[1]) || ""); used = used || !!result.start; }
    }
    if (!result.end) {
      var ended = text.match(/\b(?:terminei|terminou|acabei|acabou|fim)\b(?: (?:as|a))?\s*(agora|\d{1,2}(?::\d{2})?(?: e (?:meia|\d{1,2}))?)/);
      if (ended) { result.end = ended[1] === "agora" ? nowHHMM(now) : (readTime(ended[1]) || ""); used = used || !!result.end; }
    }

    // duracao: "1 hora e meia", "2 horas e 15", "40 minutos", "meia hora"
    if (!(result.start && result.end)) {
      var minutes = null;
      var hm = text.match(/(\d+)\s*horas?(?:\s*e\s*(meia|\d{1,2})(?:\s*minutos?)?)?/);
      if (hm) {
        minutes = parseInt(hm[1], 10) * 60;
        if (hm[2]) minutes += hm[2] === "meia" ? 30 : parseInt(hm[2], 10);
      } else if (/\bmeia hora\b/.test(text)) {
        minutes = 30;
      } else {
        var mm = text.match(/(\d+)\s*min(?:utos?)?\b/);
        if (mm) minutes = parseInt(mm[1], 10);
      }
      if (minutes === null && !result.start && !result.end) {
        var clock = text.match(/(?:^|\s)(\d{1,2}):(\d{2})\b/);
        if (clock) minutes = parseInt(clock[1], 10) * 60 + parseInt(clock[2], 10);
      }
      if (minutes) {
        result.duration = Math.floor(minutes / 60) + ":" + pad(minutes % 60);
        used = true;
      }
    }

    var obs = text.match(/\b(?:obs|observacao)\s+(.+)/);
    if (obs) result.note = obs[1].trim();
    else if (!used) result.note = (rawText || "").trim().slice(0, 160);
    return result;
  }

  function fill(form, parsed) {
    function set(name, value) {
      var field = form.querySelector('[name="' + name + '"]');
      if (field && value) field.value = value;
    }
    set("item_code", parsed.code);
    set("start_time", parsed.start);
    set("end_time", parsed.end);
    set("duration", parsed.duration);
    set("note", parsed.note);
    if (parsed.destination) {
      var radio = form.querySelector('input[name="destination"][value="' + parsed.destination + '"]');
      if (radio) radio.checked = true;
    }
  }

  function describe(parsed) {
    var parts = [];
    if (parsed.code) parts.push("código " + parsed.code);
    if (parsed.destination) parts.push(parsed.destination === "GUINCHO" ? "guincho" : "implemento");
    if (parsed.start) parts.push("início " + parsed.start);
    if (parsed.end) parts.push("fim " + parsed.end);
    if (parsed.duration) parts.push("duração " + parsed.duration);
    if (parsed.note) parts.push("observação “" + parsed.note + "”");
    return parts.join(", ");
  }

  function setup(button) {
    var form = button.closest("form");
    var status = form && form.querySelector("[data-voice-status]");
    var Recognition = root.SpeechRecognition || root.webkitSpeechRecognition;
    if (!form) return;
    if (!Recognition) {
      button.hidden = true;
      return;
    }
    button.hidden = false;
    var listening = false;
    var recognition = new Recognition();
    recognition.lang = "pt-BR";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    function say(text) { if (status) { status.textContent = text; status.hidden = !text; } }

    recognition.onresult = function (event) {
      var transcript = event.results[0][0].transcript;
      var parsed = parse(transcript);
      fill(form, parsed);
      var summary = describe(parsed);
      say("Você disse: “" + transcript + "”. " + (summary ? "Preenchi: " + summary + ". Confira e toque em Salvar item." : "Não entendi os campos; confira abaixo."));
    };
    recognition.onerror = function (event) {
      if (event.error === "not-allowed" || event.error === "service-not-allowed") {
        say("O microfone está bloqueado. Libere o microfone para este site nas configurações do navegador.");
      } else if (event.error === "no-speech") {
        say("Não ouvi nada. Toque em Falar e diga o item.");
      } else {
        say("Não deu para ouvir agora. Tente de novo ou preencha à mão.");
      }
    };
    recognition.onend = function () {
      listening = false;
      button.classList.remove("is-listening");
      button.textContent = button.getAttribute("data-label") || "Falar o item";
    };
    button.addEventListener("click", function () {
      if (listening) { recognition.stop(); return; }
      listening = true;
      button.classList.add("is-listening");
      button.textContent = "Ouvindo... toque para parar";
      say("Fale, por exemplo: “código 0011 024 implemento das 7 às 11”.");
      try { recognition.start(); } catch (error) { listening = false; }
    });
  }

  var api = { parse: parse, describe: describe, normalize: normalize, fill: fill };
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    root.HoraCertaProductionVoice = api;
    document.querySelectorAll("[data-voice-entry]").forEach(setup);
  }
})(typeof window !== "undefined" ? window : globalThis);
