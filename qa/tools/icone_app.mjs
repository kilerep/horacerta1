// Gera os PNGs do icone do app (opcao "vidro com visto", aprovada em 2026-11-22) a partir do SVG abaixo,
// usando o Chrome sem janela. uso (Git Bash): node qa/tools/icone_app.mjs static/pwa
import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

const outdir = process.argv[2] || "static/pwa";
mkdirSync(outdir, { recursive: true });

// rounded: cantos arredondados transparentes (icone "any"/favicon); sem isso o fundo vai ate a borda
// (maskable e iPhone, que recortam sozinhos). scale encolhe o desenho para caber na area segura do maskable.
function svg({ rounded, scale = 1, badge = true }) {
  const t = `translate(256 256) scale(${scale}) translate(-256 -256)`;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#1e1b4b"/><stop offset="1" stop-color="#4338ca"/></linearGradient>
    <linearGradient id="ck" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#a5f3fc"/><stop offset="1" stop-color="#38bdf8"/></linearGradient>
  </defs>
  <rect width="512" height="512" rx="${rounded ? 112 : 0}" fill="url(#bg)"/>
  <g transform="${t}">
    <rect x="118" y="118" width="276" height="276" rx="80" fill="#ffffff" fill-opacity="0.12" stroke="#ffffff" stroke-opacity="0.35" stroke-width="4"/>
    <path d="M190 262 L240 312 L330 200" fill="none" stroke="url(#ck)" stroke-width="44" stroke-linecap="round" stroke-linejoin="round"/>
    ${badge ? `<circle cx="380" cy="132" r="38" fill="#38bdf8"/>
    <path d="M380 132 V112 M380 132 H396" stroke="#1e1b4b" stroke-width="10" stroke-linecap="round"/>` : ""}
  </g>
</svg>`;
}

const targets = [
  { file: "icon-192.png", size: 192, opts: { rounded: true } },
  { file: "icon-512.png", size: 512, opts: { rounded: true } },
  { file: "icon-maskable-192.png", size: 192, opts: { rounded: false, scale: 0.8 } },
  { file: "icon-maskable-512.png", size: 512, opts: { rounded: false, scale: 0.8 } },
  { file: "apple-touch-icon-180.png", size: 180, opts: { rounded: false, scale: 0.9 } },
  { file: "favicon-32.png", size: 32, opts: { rounded: true, scale: 1.15, badge: false } },
];

const PORT = 9333 + Math.floor(Math.random() * 500);
const chrome = spawn("C:/Program Files/Google/Chrome/Application/chrome.exe", [
  "--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${join(tmpdir(), "hc-icon-" + PORT)}`,
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

await send("Page.enable");
await send("Emulation.setDefaultBackgroundColorOverride", { color: { r: 0, g: 0, b: 0, a: 0 } });
for (const { file, size, opts } of targets) {
  // o Chrome nao abre janela muito pequena: tamanhos pequenos sao desenhados 4x maiores e reduzidos no print
  const k = size < 100 ? 4 : 1;
  const css = size * k;
  await send("Emulation.setDeviceMetricsOverride", { width: css, height: css, deviceScaleFactor: 1, mobile: false });
  const html = `<html><body style="margin:0;background:transparent">${svg(opts).replace('width="512" height="512"', `width="${css}" height="${css}"`)}</body></html>`;
  await send("Page.navigate", { url: "data:text/html;base64," + Buffer.from(html).toString("base64") });
  await sleep(400);
  const shot = await send("Page.captureScreenshot", { format: "png", clip: { x: 0, y: 0, width: css, height: css, scale: 1 / k } });
  writeFileSync(join(outdir, file), Buffer.from(shot.result.data, "base64"));
  console.log(file, size);
}
writeFileSync(join(outdir, "icon.svg"), svg({ rounded: true }));
ws.close();
chrome.kill();
process.exit(0);
