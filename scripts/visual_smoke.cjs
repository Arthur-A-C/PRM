// Local-only Chrome DevTools capture; no credentials or app mutations.
const fs = require("node:fs");

async function main() {
  const [url, widthRaw, heightRaw, output, theme = "light"] = process.argv.slice(2);
  if (!url || !output) throw new Error("Usage: node scripts/visual_smoke.cjs URL WIDTH HEIGHT OUTPUT [light|dark]");
  const width = Number(widthRaw), height = Number(heightRaw);
  if (!Number.isInteger(width) || !Number.isInteger(height) || width < 320 || height < 400) throw new Error("Invalid viewport");
  const tabs = await (await fetch("http://127.0.0.1:9225/json")).json();
  const tab = tabs.find((entry) => entry.type === "page");
  if (!tab) throw new Error("No Chrome page target");
  const socket = new WebSocket(tab.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.addEventListener("open", resolve, { once: true }); socket.addEventListener("error", reject, { once: true }); });
  let sequence = 0;
  const pending = new Map();
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (!message.id || !pending.has(message.id)) return;
    const { resolve, reject } = pending.get(message.id);
    pending.delete(message.id);
    message.error ? reject(new Error(message.error.message)) : resolve(message.result);
  });
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++sequence;
    pending.set(id, { resolve, reject });
    socket.send(JSON.stringify({ id, method, params }));
  });
  try {
    await send("Page.enable");
    await send("Network.enable");
    await send("Network.setCacheDisabled", { cacheDisabled: true });
    await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: width < 600 });
    await send("Page.navigate", { url });
    await new Promise((resolve) => setTimeout(resolve, 1200));
    if (theme === "dark") await send("Runtime.evaluate", { expression: "document.documentElement.dataset.theme = 'dark'" });
    const metrics = await send("Runtime.evaluate", { expression: "JSON.stringify({innerWidth: window.innerWidth, scrollWidth: document.documentElement.scrollWidth, bodyWidth: document.body.scrollWidth, height: document.documentElement.scrollHeight, logo: (() => { const el = document.querySelector('.company-card-logo'); return el ? {viewBox: el.getAttribute('viewBox'), background: getComputedStyle(el).backgroundImage, image: el.querySelector('image')?.getAttribute('href')} : null; })()})", returnByValue: true });
    const screenshot = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
    fs.writeFileSync(output, Buffer.from(screenshot.data, "base64"));
    process.stdout.write(metrics.result.value + "\n");
  } finally {
    socket.close();
  }
}
main().catch((error) => { process.stderr.write(error.stack + "\n"); process.exitCode = 1; });
