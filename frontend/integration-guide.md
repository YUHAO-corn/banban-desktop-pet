# 桌宠 UI 模块 - 集成指南（浣熊版）

本指南面向负责把 `pet-widget.html` 接入到桌面宠物完整产品的开发者。

---

## 1. 模块定位

```
┌─────────────────────────────────────────┐
│  你的核心系统（产品方已有）             │
│  - 摄像头管理 + 人脸识别                │
│  - 情绪/压力检测                        │
│  - 数据存储与分析                       │
│  - Monitor 界面                         │
│  - 提醒策略决策                         │
└─────────────────┬───────────────────────┘
                  │
                  │ 输入：压力值、摄像头状态、触发指令
                  │ 输出：用户接受/忽略事件、点击事件、设置变更
                  ▼
┌─────────────────────────────────────────┐
│  本模块：pet-widget.html                │
│  - 渲染浣熊与井盖                        │
│  - 表情/警告牌/汗珠的视觉切换            │
│  - 处理说话气泡 + 接受/忽略按钮          │
│  - 处理设置菜单 + 尺寸调整               │
└─────────────────────────────────────────┘
```

**核心原则**：模块只接收输入、渲染画面、上报事件。所有"压力怎么算、什么时候该说话、Monitor 长什么样"都由你的核心系统决定。

---

## 2. 文件清单

- `pet-widget.html` — 完整可运行的 UI 模块（自包含 HTML/CSS/JS/SVG）
- `monitor.html` — Electron Monitor 窗口 UI（自带关闭按钮、Quit 和摄像头隐私预览）
- `pet-widget-spec.md` — 完整设计规范
- `integration-guide.md` — 本文档

---

## 3. 快速开始

### 3.1 浏览器预览

直接用浏览器打开 `pet-widget.html`。打开浏览器开发者控制台，可以手动调用 API 测试：

```javascript
window.PetWidget.setStress(75);          // 看担心+黄牌
window.PetWidget.setStress(90);          // 看难过+红牌
window.PetWidget.setCameraStatus('blind'); // 看摄像头看不到状态
window.PetWidget.setCameraStatus('off');   // 看手动关闭状态
window.PetWidget.setCameraStatus('ok');    // 恢复
window.PetWidget.triggerSpeech();          // 主动弹气泡
```

### 3.2 接入到 Electron

```javascript
// main.js
const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');

let petWindow;

function createPetWindow() {
  petWindow = new BrowserWindow({
    width: 360,
    height: 240,
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    hasShadow: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true
    }
  });

  petWindow.loadFile('pet-widget.html');

  // 默认开启鼠标穿透 - 透明区域不响应点击
  // 配合下面 setIgnoreMouseEvents 的动态切换实现"只在浣熊上响应点击"
  petWindow.setIgnoreMouseEvents(true, { forward: true });

  return petWindow;
}

ipcMain.on('set-ignore-mouse', (event, ignore) => {
  if (petWindow) petWindow.setIgnoreMouseEvents(ignore, { forward: true });
});

ipcMain.on('open-monitor', () => {
  // 这里打开你的 Monitor 窗口
  createMonitorWindow();
});

app.whenReady().then(createPetWindow);
```

```javascript
// preload.js
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('petAPI', {
  setIgnoreMouseEvents: (ignore) => ipcRenderer.send('set-ignore-mouse', ignore),
  openMonitor: () => ipcRenderer.send('open-monitor'),
  setCameraEnabled: (enabled) => ipcRenderer.send('set-camera-enabled', enabled),
  onStressUpdate: (callback) => ipcRenderer.on('stress-update', (_, value) => callback(value)),
  onCameraStatus: (callback) => ipcRenderer.on('camera-status', (_, status) => callback(status)),
  onCameraEnabled: (callback) => ipcRenderer.on('camera-enabled', (_, enabled) => callback(enabled))
});
```

### 3.3 鼠标穿透：核心交互处理

桌宠最关键的体验：透明区域不应该阻挡用户点击桌面，但浣熊和 UI 必须能被点击。

在 `pet-widget.html` 的 `<script>` 末尾追加这段（部署到 Electron 时）：

```javascript
const petContainer = document.getElementById('pet-container');

petContainer.addEventListener('mousemove', (e) => {
  // 检查鼠标是否在"实体元素"上（浣熊、井盖、UI 卡片、气泡、设置菜单）
  const target = document.elementFromPoint(e.clientX, e.clientY);
  const onSolid = target && target.closest && (
    target.closest('#pet-svg') ||
    target.closest('#ui-elements') ||
    target.closest('#speech-bubble') ||
    target.closest('#settings-menu')
  );
  if (window.petAPI) {
    window.petAPI.setIgnoreMouseEvents(!onSolid);
  }
});
```

### 3.4 Tauri 同等实现

Tauri 中对应 API 是 `appWindow.setIgnoreCursorEvents()`，逻辑相同。

---

## 4. 与你的核心系统对接

### 4.1 推送压力值

```javascript
// 主进程
function onStressCalculated(stress) {
  petWindow.webContents.send('stress-update', stress);
}

// 渲染进程（pet-widget.html 末尾追加）
window.petAPI.onStressUpdate((stress) => {
  window.PetWidget.setStress(stress);
});
```

### 4.2 推送摄像头状态

这是关键的对接点之一。当核心系统检测到摄像头异常时（未授权、画面全黑、人脸 N 秒未检测到），推送 `'blind'` 状态；当用户手动关闭摄像头时，推送 `'off'` 状态：

```javascript
// 主进程（举例）
function onCameraCheck() {
  if (cameraNotAvailable() || screenIsBlackForTooLong()) {
    petWindow.webContents.send('camera-status', 'blind');
  } else if (cameraIsManuallyOff()) {
    petWindow.webContents.send('camera-status', 'off');
  } else {
    petWindow.webContents.send('camera-status', 'ok');
  }
}

// 渲染进程
window.petAPI.onCameraStatus((status) => {
  window.PetWidget.setCameraStatus(status);
});
```

**判定建议**（由你的核心系统决定）：
- 未授权摄像头权限 → 立刻 `blind`
- 摄像头返回画面但持续 N 秒（如 10s）画面整体亮度 < 阈值 → `blind`
- 摄像头返回画面但持续 N 秒检测不到人脸 → `blind`（用户可能离开了）
- 用户手动关闭摄像头 → `off`
- 检测到人脸恢复 → `ok`

### 4.3 对接 "打开 Monitor 界面" 按钮

```javascript
// 渲染进程
window.PetWidget.onOpenMonitor(() => {
  // 通知主进程打开 Monitor 窗口
  window.petAPI.openMonitor();
});
```

主进程的 `open-monitor` IPC 处理函数已在 3.2 步骤里展示。本项目内置的 Electron Monitor 使用 `frontend/monitor.html`，由主进程创建常规 BrowserWindow，因此右上角关闭按钮和 Quit 都能正常结束窗口/应用。Monitor 会读取 `/tmp/banban_preview.jpg` 显示隐私预览，画面为马赛克背景 + 人脸区域。

### 4.4 对接摄像头开关

```javascript
window.PetWidget.onCameraToggle((enabled) => {
  window.petAPI.setCameraEnabled(enabled);
});

window.petAPI.onCameraEnabled((enabled) => {
  window.PetWidget.setCameraEnabled(enabled);
});
```

宿主系统应该在关闭时停止后端摄像头进程并清理旧 JSON；重新打开时再启动后端并恢复轮询。

### 4.5 监听用户行为

模块上报三种用户事件，对应不同的产品语义：

```javascript
// 用户点了 "好的"（接受提醒）
window.PetWidget.onSpeechAccept(() => {
  // 强信号：用户主动接受了关怀
  // 建议：记录时间戳，分析"接受率"，作为提醒策略优化的指标
  // 也可以触发额外奖励（成就解锁等，由你的核心系统决定）
});

// 用户点了 ✕（忽略提醒）
window.PetWidget.onSpeechDismiss(() => {
  // 弱信号：用户没接受
  // 建议：如果连续多次忽略，调整提醒频率/文案策略
});

// 用户点了浣熊（撸一下）
window.PetWidget.onPetClick(() => {
  // 中性信号：用户主动互动
  // 建议：可以适度"奖励"——下次说话的文案更亲切之类
});
```

### 4.6 持久化用户尺寸偏好

模块本身不持久化任何数据。如果用户调了"动物大小""UI 大小"，你的核心系统应该负责存到 settings 文件，下次启动时还原：

```javascript
// 启动时还原
const saved = readUserSettings();
if (saved.animalScale) window.PetWidget.setAnimalScale(saved.animalScale);
if (saved.uiScale) window.PetWidget.setUIScale(saved.uiScale);

// 监听变更并保存
window.PetWidget.onAnimalScaleChange((v) => {
  saveUserSettings({ animalScale: v });
});
window.PetWidget.onUIScaleChange((v) => {
  saveUserSettings({ uiScale: v });
});
```

### 4.7 自定义文案

```javascript
window.PetWidget.setMessages({
  low: ['..', '..'],
  mid: ['..', '..'],
  high: ['..', '..'],
  blind: ['..', '..'],
  off: ['..', '..']
});
```

如果你的核心系统希望完全控制说话时机和内容（比如根据用户专注时长说不同的话），可以：

```javascript
window.PetWidget.setAutoSpeech(false);  // 关闭模块的自动触发
// 由你自己的逻辑判断后调用
window.PetWidget.triggerSpeech('你已经专注 90 分钟了，\n要不站起来走两步？');
```

---

## 5. 完整 API 参考

| 方法 | 参数 | 说明 |
|------|------|------|
| `setStress(value)` | 0-100 | 设置压力值，触发表情和警告牌切换 |
| `setCameraStatus(status)` | `'ok'` / `'blind'` / `'off'` | 设置摄像头状态，触发困惑/关闭模式 |
| `triggerSpeech(message?)` | 可选字符串 | 触发说话气泡 |
| `dismissSpeech()` | 无 | 主动关闭气泡（视为忽略，会触发 onSpeechDismiss） |
| `setMessages(messages)` | `{low, mid, high, blind, off}` | 替换文案库 |
| `setAutoSpeech(enabled)` | 布尔 | 开关自动触发说话（默认开启） |
| `setCameraEnabled(enabled)` | 布尔 | 同步摄像头开关 UI 状态 |
| `setAnimalScale(value)` | 0.5-1.5 | 程序化调整动物大小 |
| `setUIScale(value)` | 0.5-1.5 | 程序化调整 UI 大小 |
| `onPetClick(cb)` | 函数 | 用户点击浣熊时回调 |
| `onSpeechAccept(cb)` | 函数 | 用户点 "好的" 时回调 |
| `onSpeechDismiss(cb)` | 函数 | 用户点 ✕ 时回调 |
| `onOpenMonitor(cb)` | 函数 | 用户点设置菜单的 "打开 Monitor" |
| `onCameraToggle(cb)` | `(enabled) => void` | 用户点设置菜单的摄像头开关 |
| `onAnimalScaleChange(cb)` | `(v) => void` | 用户拖动尺寸滑块 |
| `onUIScaleChange(cb)` | `(v) => void` | 同上 |
| `getState()` | 无 | 调试用，获取内部状态 |

---

## 6. 部署清单

正式上线前确认：

- [ ] Electron/Tauri 透明窗口已配置
- [ ] 鼠标穿透动态切换已实现（透明区域可点桌面，浣熊和 UI 区可被点击）
- [ ] 你的核心系统的压力检测输出已对接到 `setStress()`
- [ ] 摄像头状态检测已对接到 `setCameraStatus()`
- [ ] Monitor 界面打开逻辑已对接 `onOpenMonitor` 回调
- [ ] 尺寸偏好的持久化已实现
- [ ] 测试 4 个压力档位的视觉差异都正常（0-32, 33-65, 66-84, 85-100）
- [ ] 测试 blind 状态进入/退出，包括 2 秒后的自动说话
- [ ] 测试"好的"按钮的正反馈动画（眯眼笑 + 爱心）
- [ ] 测试 ✕ 按钮的忽略行为
- [ ] 文案根据产品调性做了定制（默认文案的"裁判""黄牌"梗如不合适需替换）

---

## 7. 后续可扩展点

V1 已足够发布，后续不影响现有架构的扩展：

- **更多动物**：把 SVG 结构封装成 `Character` 模板，外部可换不同动物（猫、狗、水豚等）。当前浣熊 SVG 在 `<g id="raccoon">` 里集中定义，替换成其他动物即可
- **节日彩蛋**：在浣熊头上叠加帽子（圣诞帽、生日帽），按日期显示
- **拖动浣熊**：监听 mousedown + mousemove，移动整个 Electron 窗口的位置（`win.setPosition`）
- **多种警告等级**：除了黄牌红牌，还可以加"哨子"、"红黑牌"等更多裁判梗
- **更复杂的正反馈**：除了爱心，可以根据"接受次数"解锁不同的反馈动画（比如累计 10 次解锁烟花动画）
- **声音效果**：浣熊说话时播一个轻微的 "啵" 声，点 "好的" 时播一个 "叮" 声
- **多桌宠**：同时显示多只浣熊（井盖排成一排），适合多任务监督场景

这些都是增量工程，模块的核心 API 不需要改动。
