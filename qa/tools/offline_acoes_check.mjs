// Offline 2.0 - etapa 3: salva acoes SEM internet e confere que sobem sozinhas quando a internet volta.
// uso (Git Bash):
//   KILL_CMD='...derruba o servidor...' START_CMD='...sobe o servidor...' \
//   MSYS_NO_PATHCONV=1 node qa/tools/offline_acoes_check.mjs <sessionid> <base>
import { execSync, spawn } from "node:child_process";
import { join } from "node:path";
import { tmpdir } from "node:os";

const [sessionid, BASE = "http://127.0.0.1:8769"] = process.argv.slice(2);
const host = new URL(BASE).hostname;
const PORT = 9333 + Math.floor(Math.random() * 500);
const chrome = spawn("C:/Program Files/Google/Chrome/Application/chrome.exe", [
  "--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${join(tmpdir(), "hc-acoes-" + PORT)}`,
  "--no-first-run", "--disable-gpu", "about:blank",
], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function target() {
  for (let i = 0; i < 50; i++) {
    try {
      const page = (await (await fetch(`http://127.0.0.1:${PORT}/json`)).json()).find((t) => t.type === "page");
      if (page) return page.webSocketDebuggerUrl;
    } catch {}
    await sleep(200);
  }
  throw new Error("chrome nao abriu");
}
const ws = new WebSocket(await target());
await new Promise((r) => ws.addEventListener("open", r, { once: true }));
let id = 0;
const pending = new Map();
ws.addEventListener("message", (ev) => {
  const msg = JSON.parse(ev.data);
  if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
});
const send = (method, params = {}) => new Promise((resolve) => { const n = ++id; pending.set(n, resolve); ws.send(JSON.stringify({ id: n, method, params })); });
const evaluate = async (expression) => {
  const r = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (r.result.exceptionDetails) throw new Error(JSON.stringify(r.result.exceptionDetails).slice(0, 400));
  return r.result.result.value;
};
const results = [];
const check = (name, ok, extra = "") => { results.push(ok); console.log(`${ok ? "OK  " : "FALHA"} ${name}${extra ? " - " + extra : ""}`); };
const go = async (path, wait = 2500) => { await send("Page.navigate", { url: BASE + path }); await sleep(wait); };
// preenche e envia um formulario offline: campos {nome: valor}; "client" aceita "ref" (primeiro cliente novo)
const fill = (kind, fields) => evaluate(`(() => {
  const form = document.querySelector('[data-offline-form="${kind}"]');
  if (!form) return "sem formulario";
  const d = form.closest("details"); if (d) d.open = true;
  const fields = ${JSON.stringify(fields)};
  for (const [name, value] of Object.entries(fields)) {
    const el = form.querySelector('[name="' + name + '"]');
    if (!el) return "sem campo " + name;
    if (value === "ref") { const o = Array.from(el.options).find(o => o.value.startsWith("ref:")); if (!o) return "sem cliente novo"; el.value = o.value; }
    else el.value = value;
  }
  form.requestSubmit();
  return "ok";
})()`);
const msg = () => evaluate("new Promise(r => setTimeout(() => r(document.getElementById('appMsg').textContent), 900))");
const queue = () => evaluate("HoraCertaOffline.pending().then(l => l.map(i => i.kind + (i.last_error ? '!' + i.last_error : '')))");

await send("Page.enable");
await send("Network.enable");
await send("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
await send("Network.setCookie", { name: "sessionid", value: sessionid, domain: host, path: "/" });
await go("/me/", 5000);
check("service worker pronto", await evaluate("navigator.serviceWorker.ready.then(r => !!r.active)"));
await evaluate("HoraCertaOffline.pending().then(l => Promise.all(l.map(i => HoraCertaOffline.remove(i.client_ref))))");

// ---- cai a internet ----
await send("Network.emulateNetworkConditions", { offline: true, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
execSync(process.env.KILL_CMD, { stdio: "ignore" });
await sleep(1000);

await go("/me/contrato/");
check("cliente novo", (await fill("client_new", { name: "Padaria Teste Offline", hourly_rate: "70,00" })) === "ok" && (await msg()).startsWith("Cliente guardado"));
check("cliente novo aparece na lista", (await evaluate("document.getElementById('viewOther').innerText")).includes("Padaria Teste Offline"));

await go("/me/servicos/agenda/");
check("servico novo para o cliente novo", (await fill("service_new", { title: "Servico offline", client: "ref", location: "Rua B, 20", description: "teste" })) === "ok"
  && (await msg()).startsWith("Serviço guardado"));
check("rascunho de relatorio", (await fill("report_draft", { title: "Relatorio offline", client_name: "Aurora", service_name: "Quadro" })) === "ok");

await go("/me/");
const today = await evaluate("(() => { const d = new Date(); return [d.getHours(), d.getMinutes()]; })()");
const t1 = today[1] >= 2 ? `${String(today[0]).padStart(2, "0")}:00` : "00:00";
check("horario manual de hoje", (await fill("manual_punch", { t0: t1 })) === "ok" && (await msg()).startsWith("Horários de hoje"));
check("folga", (await fill("day_off", { off_kind: "FERIADO", note: "teste" })) === "ok");

await go("/me/relatorios-producao/notas/");
check("romaneio rascunho", (await evaluate(`(() => { const f = document.querySelector('[data-offline-form="shipment_draft"]'); f.closest('details').open = true;
  f.querySelector('[name=destination]').value = 'Ensimec Offline'; const r = f.querySelector('.item-row');
  r.querySelector('[name=drawing]').value = 'D-OFF'; r.querySelector('[name=quantity]').value = '3'; f.requestSubmit(); return 'ok'; })()`)) === "ok");
await sleep(800);
const q1 = await queue();
check("6 acoes na fila do celular", q1.length === 6, JSON.stringify(q1));

// ---- internet volta ----
spawn(process.env.START_CMD, { shell: true, detached: true, stdio: "ignore" }).unref();
await sleep(6000);
await send("Network.emulateNetworkConditions", { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
let left = q1;
for (let i = 0; i < 20 && left.length; i++) { await sleep(2000); left = await queue(); }
check("fila enviada sozinha quando a internet voltou", left.length === 0, JSON.stringify(left));

ws.close();
chrome.kill();
const failed = results.filter((r) => !r).length;
console.log(failed ? `${failed} falha(s)` : "tudo certo");
process.exit(failed ? 1 : 0);
