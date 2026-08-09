// electron/main.js
const { app, BrowserWindow, dialog } = require("electron");
const path = require("path");
const { spawn, execSync } = require("child_process");

let win;
let backendProc = null;

const PORT = process.env.IG3_PORT || process.env.PORT || 5123;
const HOST = "127.0.0.1";
const UI_PATH = "/home"; // or "/live" if you prefer that page

function resolvePaths() {
  const dev = !app.isPackaged;
  const base = dev ? path.join(__dirname) : process.resourcesPath;
  const backendDir = dev ? path.join(__dirname, "backend") : path.join(base, "backend");
  const pyExe = dev
    ? path.join(__dirname, "python", "Scripts", "python.exe")
    : path.join(base, "python", "Scripts", "python.exe");
  const launcher = path.join(backendDir, "launcher.py");
  return { dev, backendDir, pyExe, launcher };
}

function spawnBackend() {
  const { backendDir, pyExe, launcher } = resolvePaths();
  try {
    execSync(`"${pyExe}" -V`, { stdio: "ignore" });
  } catch {
    dialog.showErrorBox(
      "Python runtime missing",
      `Couldn't find embedded Python:\n${pyExe}\n\nMake sure "electron/python" is in extraResources.`
    );
    return;
  }
  const env = {
    ...process.env,
    IG3_PORT: String(PORT),
    PORT: String(PORT),
    FLASK_PORT: String(PORT),
    FLASK_HOST: HOST,
    PYTHONUNBUFFERED: "1",
  };
  backendProc = spawn(`"${pyExe}"`, [`"${launcher}"`], {
    cwd: backendDir,
    shell: true,
    env,
    windowsHide: true,
  });
  backendProc.stdout?.on("data", (d) => console.log("[backend]", d.toString().trim()));
  backendProc.stderr?.on("data", (d) => console.error("[backend:err]", d.toString().trim()));
  backendProc.on("exit", (code, sig) => {
    console.log(`[backend] exited code=${code} sig=${sig}`);
    backendProc = null;
  });
}

function stopBackend() {
  if (!backendProc) return;
  try {
    if (process.platform === "win32") {
      execSync(`taskkill /PID ${backendProc.pid} /T /F`);
    } else {
      backendProc.kill("SIGTERM");
    }
  } catch {}
  backendProc = null;
}

async function wait(ms) { return new Promise(r => setTimeout(r, ms)); }

async function waitForBackend(retries = 120) {
  const url = `http://${HOST}:${PORT}/health`;
  for (let i = 0; i < retries; i++) {
    try {
      const res = await fetch(url, { cache: "no-store" });
      if (res.ok) return true;
    } catch {}
    await wait(500);
  }
  return false;
}

async function createWindow() {
  win = new BrowserWindow({
    width: 980,
    height: 720,
    show: false, // show after the page is ready
  });
  win.on("closed", () => (win = null));
  await win.loadURL(`http://${HOST}:${PORT}${UI_PATH}`);
  win.once("ready-to-show", () => win.show());
}

app.whenReady().then(async () => {
  spawnBackend();
  const ok = await waitForBackend();
  if (!ok) {
    dialog.showErrorBox("Backend not reachable", `Couldn't reach http://${HOST}:${PORT}/health`);
  }
  await createWindow();
});

app.on("before-quit", stopBackend);
app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });

app.setAppUserModelId("com.yourcompany.ig3");
