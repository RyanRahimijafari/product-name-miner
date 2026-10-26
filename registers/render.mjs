// Needs Node 22+ and Edge, Chrome or Chromium (BROWSER_EXE names it if it is elsewhere).
// node render.mjs URL WAIT_SECONDS [JS_FILE [WAIT_AFTER]]  -> the page's visible text after its scripts ran
import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
const [url, waitArg = "6", jsFile, waitAfterArg = "6"] = process.argv.slice(2);
const sleep = (s) => new Promise((r) => setTimeout(r, s * 1000));
const exe = [process.env.BROWSER_EXE,
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/usr/bin/microsoft-edge", "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser"].filter(Boolean).find(existsSync);
if (!exe) { console.log("ERROR no Edge, Chrome or Chromium found: set BROWSER_EXE to its path"); process.exit(2); }
const profile = mkdtempSync(join(tmpdir(), "rend-"));
const browser = spawn(exe, ["--headless=new", "--remote-debugging-port=0", `--user-data-dir=${profile}`, "--no-first-run", "--disable-extensions", "--mute-audio",
  "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36", "about:blank"], { stdio: "ignore" });
let socket;
try {
  let endpoint = null;
  for (let i = 0; i < 100 && !endpoint; i++) {
    const f = join(profile, "DevToolsActivePort");
    if (existsSync(f)) { const [p, path] = readFileSync(f, "utf8").split("\n"); if (p && path) endpoint = `ws://127.0.0.1:${p.trim()}${path.trim()}`; }
    if (!endpoint) await sleep(0.1);
  }
  socket = new WebSocket(endpoint);
  await new Promise((o, f) => { socket.onopen = o; socket.onerror = f; });
  let n = 0; const pend = new Map(); let loaded = false;
  socket.onmessage = (e) => { const m = JSON.parse(e.data);
    if (m.id && pend.has(m.id)) { const { d, f } = pend.get(m.id); pend.delete(m.id); m.error ? f(new Error(m.error.message)) : d(m.result); }
    else if (m.method === "Page.loadEventFired") loaded = true; };
  const send = (method, params = {}, sessionId) => new Promise((d, f) => { const id = ++n; pend.set(id, { d, f }); socket.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) })); });
  const { targetId } = await send("Target.createTarget", { url: "about:blank" });
  const { sessionId } = await send("Target.attachToTarget", { targetId, flatten: true });
  const page = (m, p) => send(m, p, sessionId);
  const ev = async (x) => { const r = await page("Runtime.evaluate", { expression: x, returnByValue: true, awaitPromise: true }); return r.result?.value ?? r.exceptionDetails?.text; };
  await page("Page.enable"); await page("Runtime.enable");
  await page("Page.navigate", { url });
  for (let i = 0; i < 300 && !loaded; i++) await sleep(0.1);
  await sleep(Number(waitArg));
  if (jsFile) { const out = await ev(readFileSync(jsFile, "utf8")); if (out) console.log("[js]", String(out).slice(0, 30000)); await sleep(Number(waitAfterArg)); }
  console.log("[url]", await ev("location.href"));
  console.log(String(await ev("document.body ? document.body.innerText : ''")).replace(/\n{3,}/g, "\n\n").slice(0, 7000));
} catch (e) { console.log("ERROR", e.message); }
finally { try { socket?.close(); } catch {} browser.kill(); await sleep(0.5); try { rmSync(profile, { recursive: true, force: true }); } catch {} }
