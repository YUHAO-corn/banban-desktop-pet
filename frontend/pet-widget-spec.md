# 桌面宠物 - UI 模块设计规范

本文档描述桌面宠物的 UI 层（视觉、动画、交互）。情绪检测、摄像头管理、压力计算等核心逻辑由产品的另一套系统负责，本模块只接收输入、渲染画面、上报事件。

---

## 1. 设计基调

- **风格**：SVG 矢量卡通，粗黑描边 + 平涂色块，参考 Bongo Cat 的画风
- **形象**：从下水道井盖里探出半个身子的浣熊（trash panda 偷窥梗）
- **气质**：搞笑、贱萌、不说教
- **背景**：完全透明 — 浣熊"住"在用户的桌面上
- **UI 组件**：独立小组件浮在画面下沿，组件之间是透明间隙，不是一整块面板

---

## 2. 容器尺寸

- 主容器：360 × 240 px
- SVG 画布：360 × 240，viewBox `0 0 360 240`
- 实际部署到桌面时，整个容器作为 Electron/Tauri 透明窗口的内容
- 浣熊和井盖的视觉中心在 (180, 180)

---

## 3. 视觉资产

### 3.1 调色板

| 用途 | 色值 |
|------|------|
| 浣熊主体灰 | `#9a9a9a` |
| 浣熊深色（身体下部） | `#7a7a7a` |
| 浣熊眼罩黑 | `#1a1a1a` |
| 眼罩内深色 | `#5a5a5a` |
| 眼白 / 鼻尖白 | `#FAFAFA` |
| 描边黑 | `#1a1a1a` |
| 井盖深 | `#2a2a2a` |
| 井盖中 | `#3a3a3a` |
| 井盖亮 | `#4a4a4a` |
| 井盖文字灰 | `#5a5a5a` |
| 黄牌 | `#FFD43B` |
| 红牌 | `#E24B4A` |
| 汗珠蓝 | `#6BA4D8` |
| 爱心粉 | `#F4537E` |
| 压力数值 - 绿 | `#A8D88C` |
| 压力数值 - 黄 | `#FFE898` |
| 压力数值 - 橙 | `#FFB870` |
| 压力数值 - 红 | `#FF8888` |
| UI 卡片背景 | `rgba(28, 26, 24, 0.92)` |
| UI 文字次要 | `rgba(255, 255, 255, 0.45)` |
| UI 图标 | `rgba(255, 255, 255, 0.7)` |

### 3.2 关键 SVG 结构

整个画面由以下图层组成（自底向上）：

1. **井盖阴影** (`#manhole-shadow`) — 椭圆，给井盖一点立体感
2. **井盖** (`#manhole`) — 椭圆，含 SEWER 文字和铆钉细节
3. **浣熊主体** (`#raccoon`) — 用 `clipPath` 限制在井盖范围内
   - 身体下半部分（深灰椭圆）
   - 身体上半部分（浅灰椭圆）
   - 左耳、右耳（含粉色内耳）
   - 黑色眼罩（左右各一）
   - 双眼（眼白 + 瞳孔 + 高光）
   - 鼻子（白底椭圆 + 黑色鼻尖）
   - 嘴巴（左右两条曲线）
4. **黄牌/红牌组** (`#card-arm`) — 默认隐藏，含手臂、牌子、感叹号
5. **汗珠组** (`#sweat-drops`) — 默认隐藏，下滑动画
6. **困惑浣熊** (`#confused-raccoon`) — 摄像头看不到时显示，含问号
7. **爱心组** (`#feedback-hearts`) — 正反馈动画，三颗爱心
8. **眯眼笑表情** (`#happy-eyes`) — 正反馈期间替换正常眼睛

**关键设计决策**：浣熊的核心 SVG 几何永远不变。所有压力等级的视觉差异通过**叠加层（汗、牌子）+ transform 动画**实现，不修改基础结构。

### 3.3 UI 组件

两个独立的小组件，水平排列，不是一整块面板：

- **STRESS 数值显示**：黑色半透明胶囊，padding 5px 10px，圆角 6px
  - 标签 "STRESS"（11px，半透明白）
  - 数值（13px，等宽字体，颜色根据压力变化）
- **设置按钮**：26×26 黑色半透明方块，圆角 6px，内含汉堡图标

组件之间间距 4px。整组 UI 贴在井盖下方（top: 196px）。

---

## 4. 状态系统

### 4.1 压力等级映射

外部输入 0-100 的 `stress` 数字，内部映射 4 档情绪：

| 压力区间 | 情绪档位 | 内部代号 |
|---------|---------|---------|
| 0-32 | 放松 | mood=0 |
| 33-65 | 平静 | mood=1 |
| 66-84 | 担心 | mood=2 |
| 85-100 | 难过/警告 | mood=3 |

### 4.2 状态对应表

| 状态 | 浣熊动画 | 装饰 | UI 数值颜色 | 自动说话 |
|------|---------|------|-----------|---------|
| 放松 | 缓慢呼吸 | 无 | 绿 (`#A8D88C`) | 否 |
| 平静 | 呼吸 + 微微左右 | 单侧汗珠 | 黄 (`#FFE898`) | 否 |
| 担心 | 呼吸加快 + 轻微抖动 + 瞳孔变小 + 眨眼变快 | 双侧汗珠 + 黄牌（带 "!"） + 黄牌轻微抖 | 橙 (`#FFB870`) | 是（≥65 触发）|
| 难过 | 剧烈抖动（XY 双向）+ 瞳孔最小 | 红牌（带白色 "!"）+ 红牌剧抖 | 红 (`#FF8888`) | 是 |
| Camera Blind | 困惑模式：左右晃动找寻 + 头顶问号忽隐忽现 | 隐藏所有装饰 | `---`（灰）| 是（进入后 2 秒）|

### 4.3 摄像头看不到状态

由外部调用 `setCameraStatus('blind' | 'ok')` 触发：

- 进入 blind 状态：隐藏正常浣熊，显示 `#confused-raccoon`，2 秒后自动弹气泡解释情况
- 持续 blind 时：每 15 秒可重复提醒一次
- 退出 blind：自动恢复正常浣熊，关闭已有气泡
- blind 期间忽略压力值更新（数值显示为 `---`）

---

## 5. 动画系统

基于全局 `frame` 计数器（每帧 +1，约 60fps），用三角函数驱动。

### 5.1 持续循环动画

| 元素 | 动画 | 周期 / 实现 |
|------|------|-----------|
| 放松呼吸 | translate Y ±1.5px | `Math.sin(frame * 0.04)` |
| 平静呼吸 + 左右 | translate XY 各 ~1.5px | `Math.sin(frame * 0.05)` + `Math.sin(frame * 0.02)` |
| 担心呼吸 + 抖 | Y ±2px + X ±0.8px | `Math.sin(frame * 0.08)` + `Math.sin(frame * 0.4)` |
| 难过剧抖 | X ±2px + Y ±1.5px | `Math.sin(frame * 0.6)` + `Math.cos(frame * 0.5)` |
| 瞳孔大小 | 半径 1.5-3px 随压力 | `3 - (stress / 100) * 1.5` |
| 眨眼频率 | 普通每 200 帧，紧张每 60 帧 | `frame % freq < 8` |
| 汗珠下滑 | 60 帧一周期，淡出 | `(frame % 60) * 0.3` 偏移 |
| 黄牌晃 | X ±0.5px | `Math.sin(frame * 0.3)` |
| 红牌剧晃 | XY 各 ~1-1.5px | `Math.sin(frame * 0.5)` + `Math.sin(frame * 0.4)` |
| 困惑左右晃 | X ±8px | `Math.sin(frame * 0.05)` |
| 问号闪烁 | opacity 0-1 | `(Math.sin(frame * 0.08) + 1) / 2` |

### 5.2 触发动画 - 正反馈（用户点 "好的" 后）

两个动画同时播放：

**眯眼笑**（`happyTimer = 60`，1 秒）：
- 隐藏正常眼睛，显示 `#happy-eyes`（两条 ^ ^ 弧线）
- 嘴巴形状切换为更明显的笑

**爱心飘散**（`heartAnimFrame` 0-90，1.5 秒）：
- 三颗爱心从浣熊头顶冒出
- 中间一颗向上飘 50px，左右两颗各偏离 12px
- 大小从 1.0 缓慢放大到 1.3
- opacity 从 1 线性降到 0

---

## 6. 说话气泡

### 6.1 触发规则

- **自动触发**：
  - 压力 ≥ 65 且距离上次气泡关闭超过 8 秒，自动弹出
  - 进入 blind 状态 2 秒后自动弹出
  - blind 持续期间每 15 秒可重复一次
- **手动触发**：外部调用 `triggerSpeech(message?)` API

### 6.2 关闭规则

气泡有两种关闭方式，区别明确：

- **"好的"按钮**（黑色圆角小按钮，气泡右下角）— 表示用户接受了提醒，触发**正反馈动画**（眯眼笑 + 爱心飘散）
- **✕ 按钮**（灰色，气泡右上角）— 表示用户忽略，无正反馈

两种关闭都会启动 8 秒冷却。两种都需要外部回调（`onSpeechAccept` / `onSpeechDismiss`），便于产品分析用户行为。

### 6.3 视觉规范

- 白底黑色描边（粗描边 2.5px）
- 圆角 14px
- 含 padding：上 10、左 14、右 14、下 12
- 字号 13px，行高 1.5
- 阶梯状黑色描边小尾巴指向浣熊头部
- 最大宽度 220px，超出则换行

### 6.4 文案库

```javascript
const messages = {
  low: ['你今天看起来不错', '保持这个状态啊', '我在偷偷看你呢～'],
  mid: ['有点紧张了哦', '休息一下？', '来，深呼吸'],
  high: ['🟨 黄牌警告！\n你压力太大了', '🟥 红牌！\n现在必须休息', '裁判我来了\n请你下场冷静'],
  blind: [
    '咦？看不到你了…\n摄像头是不是被挡住啦？',
    '你跑哪去了？\n摄像头可能出问题啦',
    '这里黑黑的什么都看不见…\n检查一下摄像头吧'
  ]
};
```

文案规则：
- 每句不超过 20 字
- high 档位用裁判梗保持幽默
- blind 档位必须明确说出"摄像头"，让用户秒懂状况
- off 档位明确告诉用户摄像头已手动关闭，不反复打扰
- 换行用 `\n`

---

## 7. 设置菜单

点击设置按钮（汉堡图标）展开菜单，包含：

### 7.1 摄像头开关

- 一个按钮在 "关闭摄像头" / "打开摄像头" 之间切换
- 点击触发 `onCameraToggle(enabled)` 回调
- 关闭后进入 `cameraStatus: 'off'`，压力值显示 `OFF`
- 重新打开后等待宿主系统推送 `'ok'` 或 `'blind'`

### 7.2 打开 Monitor 界面

- 一个按钮文字 "打开 Monitor"
- 点击触发 `onOpenMonitor` 回调
- **实际窗口由产品的核心系统提供**，UI 模块只触发回调
- 点击后菜单自动关闭

### 7.3 动物大小调整

- 滑块范围 0.5×–1.5×，步长 0.1
- 实时改变 SVG 的 transform: scale，transform-origin 锚定井盖下沿 `180px 206px`
- 缩放时动物向上变化，底部 UI 紧贴井盖下方，不被遮挡
- 触发 `onAnimalScaleChange(value)` 回调

### 7.4 UI 大小调整

- 滑块范围 0.5×–1.5×，步长 0.1
- 实时改变 UI 组件容器的 transform: scale，transform-origin 为 `center top`
- 触发 `onUIScaleChange(value)` 回调

### 7.5 菜单交互

- 点设置按钮切换显示
- 点菜单内不关闭
- 点菜单外任意位置自动关闭

---

## 8. 模块对外接口（API）

```typescript
// 设置压力值（0-100），自动映射到 4 档情绪
window.PetWidget.setStress(value: number): void;

// 设置摄像头状态
window.PetWidget.setCameraStatus(status: 'ok' | 'blind' | 'off'): void;

// 主动触发一次说话气泡
window.PetWidget.triggerSpeech(message?: string): void;

// 主动关闭气泡
window.PetWidget.dismissSpeech(): void;

// 替换文案库
window.PetWidget.setMessages(messages: {
  low: string[];
  mid: string[];
  high: string[];
  blind: string[];
  off: string[];
}): void;

// 开关自动触发说话
window.PetWidget.setAutoSpeech(enabled: boolean): void;

// 设置摄像头开关 UI 状态
window.PetWidget.setCameraEnabled(enabled: boolean): void;

// 调整尺寸（程序化调用，等同于设置菜单的滑块）
window.PetWidget.setAnimalScale(value: number): void;
window.PetWidget.setUIScale(value: number): void;

// 事件回调
window.PetWidget.onPetClick(callback: () => void): void;
window.PetWidget.onSpeechAccept(callback: () => void): void;     // 用户点 "好的"
window.PetWidget.onSpeechDismiss(callback: () => void): void;    // 用户点 ✕
window.PetWidget.onOpenMonitor(callback: () => void): void;      // 设置菜单点击
window.PetWidget.onCameraToggle(callback: (enabled: boolean) => void): void;
window.PetWidget.onAnimalScaleChange(callback: (v: number) => void): void;
window.PetWidget.onUIScaleChange(callback: (v: number) => void): void;
```

---

## 9. 模块边界（明确不做）

以下功能**不在本模块范围**，由产品的核心系统负责：

- 压力值的实际计算（人脸识别 / 表情分析 / 行为统计）
- 摄像头本身的开启、状态检测、画面分析
- Monitor 界面的实现（UI 模块只触发"打开"事件）
- 通知策略（什么时候该说话由产品决策；模块只默认压力≥65自动触发）
- 数据存储、历史记录、用户偏好持久化
- 跨进程通信、桌面集成、点击穿透

模块只负责：**接收输入 → 渲染画面 → 上报点击/接受/忽略事件**。
