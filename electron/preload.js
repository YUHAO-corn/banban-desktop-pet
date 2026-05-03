const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  // Receive stress data from main process
  onStressUpdate: (callback) => ipcRenderer.on('stress-update', (_event, data) => callback(data)),

  // Receive camera status from main process
  onCameraStatus: (callback) => ipcRenderer.on('camera-status', (_event, status) => callback(status)),

  // Receive whether camera monitoring is enabled
  onCameraEnabled: (callback) => ipcRenderer.on('camera-enabled', (_event, enabled) => callback(enabled)),

  // Receive Monitor dashboard state
  onMonitorState: (callback) => ipcRenderer.on('monitor-state', (_event, state) => callback(state)),

  // User accepted speech bubble ("好的")
  speechAccepted: () => ipcRenderer.send('speech-accepted'),

  // User dismissed speech bubble (✕)
  speechDismissed: () => ipcRenderer.send('speech-dismissed'),

  // User clicked "打开 Monitor 界面" in settings
  launchMonitor: () => ipcRenderer.send('launch-monitor'),

  // User toggled camera monitoring
  setCameraEnabled: (enabled) => ipcRenderer.send('set-camera-enabled', enabled),

  // Monitor window controls
  closeMonitor: () => ipcRenderer.send('close-monitor'),
  quitApp: () => ipcRenderer.send('quit-app'),

  // Click-through toggle
  setIgnoreMouseEvents: (ignore) => ipcRenderer.send('set-ignore-mouse', ignore),

  // Drag window
  moveWindow: (dx, dy) => ipcRenderer.send('move-window', dx, dy),
});
