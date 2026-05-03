const { app, BrowserWindow, ipcMain, screen } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
const { pathToFileURL } = require('url');

// --- Config ---
const STRESS_JSON = '/tmp/banban_stress.json';
const PREVIEW_IMAGE = '/tmp/banban_preview.jpg';
const POLL_INTERVAL = 3000;        // 3s sampling interval
const STRESS_THRESHOLD = 60;
const FIRST_TRIGGER_WINDOW = 15000;  // 15s window for first alert
const NORMAL_TRIGGER_WINDOW = 30000; // 30s window for subsequent alerts
const TRIGGER_RATIO = 0.7;          // 70% of samples must exceed threshold
const ALERT_TIMEOUT = 60000;         // 1min auto-dismiss
const COOLDOWN_DURATION = 300000;    // 5min cooldown after alert
const STARTUP_GRACE = 10000;         // 10s grace — ignore camera_blocked during startup
const PET_WIDTH = 360;
const PET_HEIGHT = 320;

let win;
let monitorWin;
let pythonProcess = null;
let cameraEnabled = true;
let backendStatus = 'stopped';
let latestStressData = null;
const appStartTime = Date.now();

// --- Alert State Machine ---
// States: 'idle' | 'alert' | 'cooldown'
const alertState = {
  state: 'idle',
  alertStart: null,
  cooldownStart: null,
  hasTriggeredOnce: false,
};

// Sliding window of recent stress readings: { score, timestamp }
const stressWindow = [];

function resetToIdle() {
  alertState.state = 'idle';
  alertState.alertStart = null;
  alertState.cooldownStart = null;
}

function sendToPet(channel, payload) {
  if (win && !win.isDestroyed()) {
    win.webContents.send(channel, payload);
  }
}

function sendToMonitor(channel, payload) {
  if (monitorWin && !monitorWin.isDestroyed()) {
    monitorWin.webContents.send(channel, payload);
  }
}

function getCameraStatus() {
  if (!cameraEnabled) return 'off';
  if (latestStressData && latestStressData.camera_blocked) return 'blind';
  return 'ok';
}

function publishCameraState() {
  const status = getCameraStatus();
  sendToPet('camera-enabled', cameraEnabled);
  sendToPet('camera-status', status);
  sendToMonitor('camera-enabled', cameraEnabled);
  sendToMonitor('camera-status', status);
  publishMonitorState();
}

function publishMonitorState() {
  const previewUrl = fs.existsSync(PREVIEW_IMAGE)
    ? `${pathToFileURL(PREVIEW_IMAGE).href}?t=${Date.now()}`
    : null;

  sendToMonitor('monitor-state', {
    cameraEnabled,
    cameraStatus: getCameraStatus(),
    backendStatus,
    alert: { ...alertState },
    stress: latestStressData,
    previewUrl,
    stressJson: STRESS_JSON,
    updatedAt: new Date().toISOString(),
  });
}

function processStressData(data) {
  if (!cameraEnabled) return;
  const now = Date.now();
  latestStressData = data;

  // Always push stress to UI
  sendToPet('stress-update', data);
  sendToMonitor('stress-update', data);

  // Camera blocked — switch to blind mode
  // Skip during startup grace period (camera may still be initializing)
  if (data.camera_blocked) {
    if (now - appStartTime > STARTUP_GRACE) {
      sendToPet('camera-status', 'blind');
      sendToMonitor('camera-status', 'blind');
    }
    stressWindow.length = 0;
    resetToIdle();
    publishMonitorState();
    return;
  }

  // Camera OK — ensure widget is not stuck in blind mode
  sendToPet('camera-status', 'ok');
  sendToMonitor('camera-status', 'ok');

  const score = data.stress_score || 0;

  // Add to sliding window
  stressWindow.push({ score, timestamp: now });

  // Use shorter window for first trigger, normal window after
  const windowDuration = alertState.hasTriggeredOnce ? NORMAL_TRIGGER_WINDOW : FIRST_TRIGGER_WINDOW;

  // Prune old entries outside the window
  while (stressWindow.length > 0 && now - stressWindow[0].timestamp > windowDuration) {
    stressWindow.shift();
  }

  switch (alertState.state) {
    case 'idle':
      if (data.face_detected && stressWindow.length >= 3) {
        const aboveCount = stressWindow.filter(s => s.score >= STRESS_THRESHOLD).length;
        const ratio = aboveCount / stressWindow.length;
        const expectedSamples = Math.floor(windowDuration / POLL_INTERVAL);
        const windowFull = stressWindow.length >= expectedSamples * 0.7;

        if (ratio >= TRIGGER_RATIO && windowFull) {
          alertState.state = 'alert';
          alertState.alertStart = now;
          alertState.hasTriggeredOnce = true;
          stressWindow.length = 0;
          if (win && !win.isDestroyed()) {
            win.webContents.executeJavaScript(`window.PetWidget.triggerSpeech()`);
          }
        }
      }
      break;

    case 'alert':
      if (now - alertState.alertStart >= ALERT_TIMEOUT) {
        if (win && !win.isDestroyed()) {
          win.webContents.executeJavaScript(`window.PetWidget.dismissSpeech()`);
        }
        alertState.state = 'cooldown';
        alertState.cooldownStart = now;
      }
      break;

    case 'cooldown':
      if (now - alertState.cooldownStart >= COOLDOWN_DURATION) {
        resetToIdle();
      }
      break;
  }
  publishMonitorState();
}

// --- JSON Polling ---
let pollTimer = null;

function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(() => {
    if (!cameraEnabled) return;
    try {
      const raw = fs.readFileSync(STRESS_JSON, 'utf8');
      const data = JSON.parse(raw);
      processStressData(data);
    } catch (e) {
      // File doesn't exist yet or is being written — skip this cycle
    }
  }, POLL_INTERVAL);
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

// --- Python Backend Process ---
function startPythonBackend() {
  if (pythonProcess || !cameraEnabled) return;
  const scriptPath = path.join(__dirname, '../backend/emotion_watch.py');
  backendStatus = 'starting';
  publishMonitorState();
  const child = spawn('python3', [scriptPath, '--headless'], {
    stdio: ['ignore', 'pipe', 'pipe'],
    detached: false,
  });
  pythonProcess = child;
  child.stderr.on('data', (data) => {
    console.error('[Python]', data.toString().trim());
  });
  child.stdout.on('data', (data) => {
    console.log('[Python]', data.toString().trim());
  });
  child.on('error', (err) => {
    console.error('Failed to start Python backend:', err.message);
    if (pythonProcess === child) {
      backendStatus = 'error';
      publishMonitorState();
    }
  });
  child.on('exit', (code) => {
    console.log(`Python backend exited with code ${code}`);
    if (pythonProcess === child) {
      pythonProcess = null;
      backendStatus = cameraEnabled ? 'stopped' : 'off';
      publishMonitorState();
    }
  });
  backendStatus = 'running';
  publishMonitorState();
}

function stopPythonBackend() {
  if (pythonProcess) {
    pythonProcess.kill('SIGTERM');
    pythonProcess = null;
  }
  try { fs.unlinkSync(STRESS_JSON); } catch (e) {}
  try { fs.unlinkSync(PREVIEW_IMAGE); } catch (e) {}
  backendStatus = cameraEnabled ? 'stopped' : 'off';
  latestStressData = null;
  publishMonitorState();
}

function setCameraEnabled(enabled) {
  cameraEnabled = !!enabled;
  stressWindow.length = 0;
  resetToIdle();

  if (cameraEnabled) {
    backendStatus = 'starting';
    startPythonBackend();
  } else {
    stopPythonBackend();
  }

  publishCameraState();
}

// --- Electron Window ---
function createPetWindow() {
  const { width, height } = screen.getPrimaryDisplay().workAreaSize;

  win = new BrowserWindow({
    width: PET_WIDTH,
    height: PET_HEIGHT,
    x: width - PET_WIDTH,
    y: height - PET_HEIGHT,
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    hasShadow: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
    },
  });

  win.loadFile(path.join(__dirname, '../frontend/pet-widget.html'));

  win.webContents.on('did-finish-load', () => {
    publishCameraState();
  });

  // Click-through by default, renderer toggles on mouse over solid elements
  win.setIgnoreMouseEvents(true, { forward: true });
}

function createMonitorWindow() {
  if (monitorWin && !monitorWin.isDestroyed()) {
    monitorWin.focus();
    publishMonitorState();
    return;
  }

  monitorWin = new BrowserWindow({
    width: 860,
    height: 560,
    minWidth: 760,
    minHeight: 500,
    frame: false,
    title: 'BanBan Monitor',
    backgroundColor: '#f4f1ea',
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
    },
  });

  monitorWin.loadFile(path.join(__dirname, '../frontend/monitor.html'));
  monitorWin.once('ready-to-show', () => {
    monitorWin.show();
    publishMonitorState();
  });
  monitorWin.webContents.on('did-finish-load', () => {
    publishMonitorState();
  });
  monitorWin.on('closed', () => {
    monitorWin = null;
  });
}

// --- IPC Handlers ---

// Click-through toggle from renderer
ipcMain.on('set-ignore-mouse', (_event, ignore) => {
  if (win) {
    win.setIgnoreMouseEvents(ignore, { forward: true });
  }
});

// User accepted speech bubble ("好的") — enter cooldown
ipcMain.on('speech-accepted', () => {
  if (alertState.state === 'alert') {
    alertState.state = 'cooldown';
    alertState.cooldownStart = Date.now();
    publishMonitorState();
  }
});

// User dismissed speech bubble (✕) — enter cooldown
ipcMain.on('speech-dismissed', () => {
  if (alertState.state === 'alert') {
    alertState.state = 'cooldown';
    alertState.cooldownStart = Date.now();
    publishMonitorState();
  }
});

// Launch Monitor window
ipcMain.on('launch-monitor', () => {
  createMonitorWindow();
});

ipcMain.on('set-camera-enabled', (_event, enabled) => {
  setCameraEnabled(enabled);
});

ipcMain.on('close-monitor', () => {
  if (monitorWin && !monitorWin.isDestroyed()) {
    monitorWin.close();
  }
});

ipcMain.on('quit-app', () => {
  app.quit();
});

// Drag window by delta
ipcMain.on('move-window', (_event, dx, dy) => {
  if (win) {
    const [x, y] = win.getPosition();
    win.setPosition(x + dx, y + dy);
  }
});

// --- App Lifecycle ---
app.whenReady().then(() => {
  app.dock.hide();
  createPetWindow();
  startPythonBackend();
  startPolling();
});

app.on('window-all-closed', () => {
  stopPolling();
  stopPythonBackend();
  app.quit();
});

app.on('before-quit', () => {
  stopPolling();
  stopPythonBackend();
});
