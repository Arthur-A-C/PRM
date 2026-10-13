// Local-only Chrome DevTools capture; no credentials or app mutations.
const fs = require("node:fs");

async function main() {
  const [url, widthRaw, heightRaw, output, theme = "light", verifyToggle] = process.argv.slice(2);
  if (!url || !output) throw new Error("Usage: node scripts/visual_smoke.cjs URL WIDTH HEIGHT OUTPUT [light|dark]");
  const width = Number(widthRaw), height = Number(heightRaw);
  if (!Number.isInteger(width) || !Number.isInteger(height) || width < 320 || height < 400) throw new Error("Invalid viewport");
  const tab = await (await fetch("http://127.0.0.1:9225/json/new?about:blank", { method: "PUT" })).json();
  if (!tab?.webSocketDebuggerUrl) throw new Error("No Chrome page target");
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
    let themeSeed;
    if (theme === "dark" || theme === "light") {
      themeSeed = await send("Page.addScriptToEvaluateOnNewDocument", { source: `try { localStorage.setItem('prm-theme', '${theme}'); } catch (_) {}` });
    }
    await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: width < 600 });
    await send("Page.navigate", { url });
    await new Promise((resolve) => setTimeout(resolve, 1200));
    const metrics = await send("Runtime.evaluate", { expression: "JSON.stringify({theme: document.documentElement.dataset.theme || 'light', storedTheme: localStorage.getItem('prm-theme'), toggleLabel: document.querySelector('[data-prm-theme-label]')?.textContent, innerWidth: window.innerWidth, clientWidth: document.documentElement.clientWidth, visualWidth: window.visualViewport?.width, scrollWidth: document.documentElement.scrollWidth, bodyWidth: document.body.scrollWidth, height: document.documentElement.scrollHeight, overflow: [...document.querySelectorAll('body *')].filter(el => el.getBoundingClientRect().right > document.documentElement.clientWidth + 8).slice(0,12).map(el => ({tag:el.tagName.toLowerCase(), id:el.id, cls:String(el.className).slice(0,60), right:Math.round(el.getBoundingClientRect().right)})), logo: (() => { const el = document.querySelector('.company-card-logo'); return el ? {viewBox: el.getAttribute('viewBox'), background: getComputedStyle(el).backgroundImage, image: el.querySelector('image')?.getAttribute('href')} : null; })()})", returnByValue: true });
    const screenshot = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
    fs.writeFileSync(output, Buffer.from(screenshot.data, "base64"));
    const report = JSON.parse(metrics.result.value);
    if (verifyToggle === "verify-toggle") {
      if (themeSeed?.identifier) await send("Page.removeScriptToEvaluateOnNewDocument", { identifier: themeSeed.identifier });
      await send("Runtime.evaluate", { expression: "document.querySelector('[data-prm-theme-toggle]')?.click()" });
      const toggled = await send("Runtime.evaluate", { expression: "JSON.stringify({theme:document.documentElement.dataset.theme,stored:localStorage.getItem('prm-theme')})", returnByValue: true });
      await send("Page.reload", { ignoreCache: true });
      await new Promise((resolve) => setTimeout(resolve, 700));
      const reloaded = await send("Runtime.evaluate", { expression: "JSON.stringify({theme:document.documentElement.dataset.theme,stored:localStorage.getItem('prm-theme'),label:document.querySelector('[data-prm-theme-label]')?.textContent})", returnByValue: true });
      report.togglePersistence = { afterClick: JSON.parse(toggled.result.value), afterReload: JSON.parse(reloaded.result.value) };
    }
    process.stdout.write(JSON.stringify(report) + "\n");
  } finally {
    socket.close();
    await fetch(`http://127.0.0.1:9225/json/close/${tab.id}`);
  }
}
main().catch((error) => { process.stderr.write(error.stack + "\n"); process.exitCode = 1; });
