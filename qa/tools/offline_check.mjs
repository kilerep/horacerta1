// Confere no Chrome de verdade (sem janela) o Offline 2.0 - etapa 1:
// copia criptografada no aparelho, faixa sem internet / conectado de novo e limpeza ao sair.
// uso (Git Bash): MSYS_NO_PATHCONV=1 node qa/tools/offline_check.mjs <sessionid> [http://127.0.0.1:8766]
import { spawn } from "node:child_process";
import { join } from "node:path";
import { tmpdir } from "node:os";

const [sessionid, BASE = "http://127.0.0.1:8766"] = process.argv.slice(2);
const host = new URL(BASE).hostname;
const PORT = 9333 + Math.floor(Math.random() * 500);
const chrome = spawn("C:/Program Files/Google/Chrome/Application/chrome.exe", [
  "--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${join(tmpdir(), "hc-off-" + PORT)}`,
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
  if (r.result.exceptionDetails) throw new Error(JSON.stringify(r.result.exceptionDetails));
  return r.result.result.value;
};
const results = [];
const check = (name, ok, extra = "") => { results.push(ok); console.log(`${ok ? "OK  " : "FALHA"} ${name}${extra ? " - " + extra : ""}`); };

await send("Page.enable");
await send("Network.enable");
await send("Network.setCookie", { name: "sessionid", value: sessionid, domain: host, path: "/" });
await send("Page.navigate", { url: BASE + "/me/" });
await sleep(4000);

const uid = await evaluate("document.body.getAttribute('data-user-id')");
check("tela logada tem data-user-id", !!uid);
const data = await evaluate(`HoraCertaMirror.load(${JSON.stringify(uid)}).then(d => d && {clients: d.clients.length, name: (d.clients[0]||{}).name || ""})`);
check("copia baixada e aberta com a chave do aparelho", !!data && data.clients > 0, JSON.stringify(data));

const raw = await evaluate(`new Promise(res => { const r = indexedDB.open("hc-mirror"); r.onsuccess = () => {
  const db = r.result; const t = db.transaction(["data","keys"]); let out = {};
  t.objectStore("data").get(${JSON.stringify(uid)}).onsuccess = e => { const row = e.target.result;
    out.isBuffer = row.cipher instanceof ArrayBuffer; out.bytes = row.cipher.byteLength;
    out.text = new TextDecoder("utf-8", {fatal:false}).decode(row.cipher); };
  t.objectStore("keys").get(${JSON.stringify(uid)}).onsuccess = e => { const k = e.target.result.key;
    out.extractable = k.extractable; out.algo = k.algorithm.name; };
  t.oncomplete = () => { db.close(); res(out); }; }; })`);
check("gravado como bytes cifrados", raw.isBuffer && raw.bytes > 0, `${raw.bytes} bytes`);
check("nome do cliente NAO aparece em texto puro", data && data.name && !raw.text.includes(data.name) && !raw.text.includes("hourly_rate"));
check("chave AES-GCM nao exportavel", raw.algo === "AES-GCM" && raw.extractable === false);

await send("Network.emulateNetworkConditions", { offline: true, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
await sleep(1500);
const offlineBar = await evaluate("(() => { const b = document.getElementById('hcConnectionBanner'); return b && !b.hidden ? b.textContent : ''; })()");
check("faixa 'Sem internet' aparece", offlineBar.startsWith("Sem internet"), offlineBar.slice(0, 60));
const offlineData = await evaluate(`HoraCertaMirror.load(${JSON.stringify(uid)}).then(d => !!d && d.clients.length)`);
check("copia abre sem internet", !!offlineData);

await send("Network.emulateNetworkConditions", { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
await sleep(3500);
const backBar = await evaluate("(() => { const b = document.getElementById('hcConnectionBanner'); return b && !b.hidden ? b.textContent : ''; })()");
check("faixa 'Conectado de novo' aparece", backBar.startsWith("Conectado de novo"), backBar.slice(0, 40));

await evaluate("document.querySelector('a[href$=\"/logout/\"]').click(); true");
await sleep(4000);
const dbs = await evaluate("indexedDB.databases().then(l => l.map(d => d.name))");
check("ao sair, a copia some do aparelho", !dbs.includes("hc-mirror"), JSON.stringify(dbs));

ws.close();
chrome.kill();
const failed = results.filter((r) => !r).length;
console.log(failed ? `${failed} falha(s)` : "tudo certo");
process.exit(failed ? 1 : 0);
