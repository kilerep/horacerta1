// Captura telas do HoraCerta local em computador e celular via Chrome sem janela (CDP).
// uso (Git Bash): MSYS_NO_PATHCONV=1 node qa/tools/telas.mjs <sessionid> <pasta> me/painel/ me/servicos/ ...
import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

const [sessionid, outdir, ...paths] = process.argv.slice(2);
const BASE = "http://127.0.0.1:8765";
const PORT = 9333 + Math.floor(Math.random() * 500);
mkdirSync(outdir, { recursive: true });
const chrome = spawn("C:/Program Files/Google/Chrome/Application/chrome.exe", [
  "--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${join(tmpdir(), "hc-shots-" + PORT)}`,
  "--no-first-run", "--disable-gpu", "--hide-scrollbars", "about:blank",
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
const waiters = [];
ws.addEventListener("message", (ev) => {
  const msg = JSON.parse(ev.data);
  if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
  if (msg.method) waiters.splice(0).forEach((w) => (w.method === msg.method ? w.resolve(msg) : waiters.push(w)));
});
const send = (method, params = {}) => new Promise((resolve) => { const n = ++id; pending.set(n, resolve); ws.send(JSON.stringify({ id: n, method, params })); });
const once = (method, ms = 15000) => Promise.race([new Promise((resolve) => waiters.push({ method, resolve })), sleep(ms)]);

await send("Page.enable");
await send("Network.enable");
await send("Network.setCookie", { name: "sessionid", value: sessionid, domain: "127.0.0.1", path: "/" });
const devices = [
  { tag: "desk", width: 1366, height: 900, mobile: false, scale: 1 },
  { tag: "mob", width: 390, height: 844, mobile: true, scale: 2 },
];
for (const p of paths) {
  for (const d of devices) {
    await send("Emulation.setDeviceMetricsOverride", { width: d.width, height: d.height, deviceScaleFactor: d.scale, mobile: d.mobile });
    const loaded = once("Page.loadEventFired");
    await send("Page.navigate", { url: BASE + "/" + p.replace(/^\/+/, "") });
    await loaded;
    await sleep(700);
    // esconde o tour automatico para ver a tela de verdade
    await send("Runtime.evaluate", { expression: "document.getElementById('hc-tour-overlay')?.remove(); document.querySelectorAll('.hc-tour-bubble,[class*=tour-bubble]').forEach(e=>e.remove())" });
    const metrics = await send("Page.getLayoutMetrics");
    const h = Math.min(Math.ceil(metrics.result.cssContentSize.height), 4000);
    const shot = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true, clip: { x: 0, y: 0, width: d.width, height: h, scale: d.mobile ? 0.5 : 0.6 } });
    const name = (p.replace(/[^a-z0-9]+/gi, "_").replace(/^_|_$/g, "") || "root") + "-" + d.tag + ".png";
    writeFileSync(join(outdir, name), Buffer.from(shot.result.data, "base64"));
    console.log(name, h);
  }
}
ws.close();
chrome.kill();
process.exit(0);
