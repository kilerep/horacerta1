// Offline 2.0 - etapa 2: abre as telas do sistema SEM internet no Chrome de verdade.
// uso (Git Bash): MSYS_NO_PATHCONV=1 node qa/tools/offline_telas_check.mjs <sessionid> <base> [pasta-prints]
import { execSync, spawn } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

const [sessionid, BASE = "http://127.0.0.1:8767", shots] = process.argv.slice(2);
if (shots) mkdirSync(shots, { recursive: true });
const host = new URL(BASE).hostname;
const PORT = 9333 + Math.floor(Math.random() * 500);
const chrome = spawn("C:/Program Files/Google/Chrome/Application/chrome.exe", [
  "--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${join(tmpdir(), "hc-tel-" + PORT)}`,
  "--no-first-run", "--disable-gpu", "--hide-scrollbars", "about:blank",
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
const shot = async (name) => {
  if (!shots) return;
  const m = await send("Page.getLayoutMetrics");
  const h = Math.min(Math.ceil(m.result.cssContentSize.height), 3000);
  const s = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true, clip: { x: 0, y: 0, width: 390, height: h, scale: 1 } });
  writeFileSync(join(shots, name + ".png"), Buffer.from(s.result.data, "base64"));
};

await send("Page.enable");
await send("Network.enable");
await send("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
await send("Network.setCookie", { name: "sessionid", value: sessionid, domain: host, path: "/" });
await go("/me/", 5000);
console.log("abriu /me/"); const sw = await evaluate("Promise.race([navigator.serviceWorker.ready.then(r => !!r.active), new Promise(r => setTimeout(() => r(false), 8000))])");
check("service worker ativo", sw);
const uid = await evaluate("document.body.getAttribute('data-user-id')");
const client = await evaluate(`HoraCertaMirror.load(${JSON.stringify(uid)}).then(d => d ? d.clients[0].name : "")`);
check("copia guardada antes de cair a internet", !!client, client);

await send("Network.emulateNetworkConditions", { offline: true, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
// a emulacao do Chrome nao corta a rede do service worker: KILL_CMD derruba o servidor (queda de verdade)
if (process.env.KILL_CMD) { execSync(process.env.KILL_CMD, { stdio: "ignore" }); await sleep(1000); }

const tabOn = "(document.querySelector('[data-tab].on')||{}).getAttribute && document.querySelector('[data-tab].on').getAttribute('data-tab')";
const textOf = "(document.getElementById('viewOther')||{innerText:''}).innerText";

await go("/me/historico/");
check("Historico abre sem internet na aba certa", (await evaluate(tabOn)) === "historico");
check("Historico mostra os horarios do cliente", (await evaluate(textOf)).includes(client));
await shot("off-historico");

await go("/me/painel/");
check("Meu resumo abre sem internet", (await evaluate(tabOn)) === "resumo" && (await evaluate(textOf)).includes("Meu resumo"));
check("Resumo mostra valor estimado", (await evaluate(textOf)).includes("R$"));
await shot("off-resumo");

await go("/me/contrato/");
check("Meus clientes abre sem internet", (await evaluate(tabOn)) === "clientes" && (await evaluate(textOf)).includes("/h"));

await go("/me/servicos/agenda/");
check("Agenda abre sem internet", (await evaluate(tabOn)) === "agenda" && (await evaluate(textOf)).includes("Agenda"));

await go("/me/relatorios-producao/");
check("Producao abre sem internet", (await evaluate(tabOn)) === "producao");
await go("/me/relatorios-producao/notas/");
check("Romaneios abre sem internet", (await evaluate(tabOn)) === "romaneios");

// registrar sem internet e ver no historico como "guardado no celular"
await go("/me/");
check("Registrar abre sem internet", (await evaluate(tabOn)) === "registrar");
await evaluate("document.getElementById('punchBtn').click(); new Promise(r => setTimeout(r, 1200))");
await evaluate("document.querySelector('[data-tab=historico]').click(); true");
await sleep(800);
check("registro feito offline aparece no Historico como pendente", await evaluate("!!document.querySelector('#viewOther .time.pending')"));
check("endereco acompanha a aba", (await evaluate("location.pathname")) === "/me/historico/");
await shot("off-historico-pendente");

const theme = await evaluate("document.documentElement.getAttribute('data-theme')");
check("usa o tema escolhido no sistema", !!theme, theme);

ws.close();
chrome.kill();
const failed = results.filter((r) => !r).length;
console.log(failed ? `${failed} falha(s)` : "tudo certo");
process.exit(failed ? 1 : 0);
