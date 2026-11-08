// Teste ponta a ponta do modo sem internet com Chrome sem janela (CDP).
// Fluxo: abre o app logado (guarda clientes), servidor cai, registra horario offline,
// servidor volta e a fila e enviada sozinha.
// uso: MSYS_NO_PATHCONV=1 node qa/tools/offline_e2e.mjs <sessionid> <comando-para-parar> <comando-para-subir>
// Os comandos de parar/subir o servidor sao passados pelo chamador (ex.: scripts .cmd).
import { spawn, execSync } from "node:child_process";
import { join } from "node:path";
import { tmpdir } from "node:os";

const [sessionid, stopCmd, startCmd] = process.argv.slice(2);
const BASE = "http://127.0.0.1:8765";
const PORT = 9333 + Math.floor(Math.random() * 500);
const chrome = spawn("C:/Program Files/Google/Chrome/Application/chrome.exe", [
  "--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${join(tmpdir(), "hc-off-" + PORT)}`,
  "--no-first-run", "--disable-gpu", "about:blank",
], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function target() {
  for (let i = 0; i < 50; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json`)).json();
      const page = list.find((t) => t.type === "page");
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
const evalJs = async (expression) => (await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true })).result?.result?.value;
const log = (...a) => console.log(...a);

await send("Page.enable");
await send("Network.enable");
await send("Network.setCookie", { name: "sessionid", value: sessionid, domain: "127.0.0.1", path: "/" });

await send("Page.navigate", { url: BASE + "/me/" });
await sleep(4000);
log("1 online:", await evalJs("document.title"));
const swReady = await evalJs("navigator.serviceWorker.ready.then(r => !!r.active)");
log("  service worker ativo:", swReady);
await sleep(2500);
const profile = await evalJs("HoraCertaOffline.getProfile().then(p => p ? p.contracts.length : 0)");
log("  clientes guardados no aparelho:", profile);

execSync(stopCmd, { stdio: "ignore" });
await sleep(1500);
await send("Page.navigate", { url: BASE + "/me/" });
await sleep(3500);
log("2 offline:", await evalJs("document.title"));
await evalJs("document.getElementById('punchBtn').click()");
await sleep(1200);
log("  mensagem:", await evalJs("document.getElementById('msg').textContent"));
log("  na fila:", await evalJs("HoraCertaOffline.pending().then(i => i.length)"));

const child = spawn(startCmd, { shell: true, stdio: "ignore", detached: true });
child.unref();
for (let i = 0; i < 40; i++) { try { if ((await fetch(BASE + "/ping/")).status === 204) break; } catch {} await sleep(1000); }
await sleep(20000); // pagina offline confere a internet a cada 15s e envia
log("3 de volta:", await evalJs("document.getElementById('net').textContent"));
log("  mensagem:", await evalJs("document.getElementById('msg').textContent"));
log("  na fila:", await evalJs("HoraCertaOffline.pending().then(i => i.length)"));
ws.close();
chrome.kill();
process.exit(0);
