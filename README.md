# BanBan / 斑斑

> 过载前，先停一下。

BanBan 是一个本地运行的压力觉察桌宠。它会在电脑桌面上安静陪伴使用者，并在摄像头开启时，通过本地模型观察皱眉、眯眼、嘴唇紧绷等面部压力线索。当压力持续升高时，BanBan 会举起黄牌或红牌，用温和的气泡提醒你先停一下、喝口水、整理思路，再继续工作。

这个项目最初面向心智障碍群体就业支持场景：许多人并非没有就业潜力，而是在真实岗位中容易遇到压力积累、自我察觉困难、主动求助不及时等问题。BanBan 不做医疗诊断，也不替代医生、心理咨询师或专业就业支持员；它尝试提供一种轻量、私密、低打扰的辅助提醒方式，把“快要过载了”这件事提前变得可见。

[![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)](#运行环境)
[![Local First](https://img.shields.io/badge/privacy-local--first-2f855a)](#隐私说明)
[![Electron](https://img.shields.io/badge/Electron-30-47848f)](https://www.electronjs.org/)
[![MediaPipe](https://img.shields.io/badge/MediaPipe-FaceLandmarker-fbbc04)](https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker)

## 项目亮点

- **压力线索识别，而不是情绪贴标签**：关注皱眉、眯眼、嘴唇紧绷、表情冻结等压力相关线索，做压力状态估计，不判断“真实情绪”。
- **个人平静基线校准**：启动时建立使用者自己的平静基线，后续根据相对变化计算压力，减少默认表情差异带来的误判。
- **桌宠式温和提醒**：用黄牌 / 红牌和气泡提醒替代生硬弹窗，让提醒更像陪伴，而不是警告。
- **默认本地处理**：人脸分析在本机完成，未使用云端识别 API。
- **隐私预览**：Monitor 面板使用马赛克背景 + 主要人脸区域的预览，方便确认摄像头状态，同时减少办公场景中的隐私暴露。
- **仍然是一只桌宠**：关闭摄像头后，BanBan 依然可以拖动、点击互动、陪你工作。

## 它怎么工作

```text
摄像头
  ↓
backend/emotion_watch.py
  - OpenCV 读取摄像头
  - MediaPipe FaceLandmarker 提取 blendshapes
  - 计算压力分数和四类压力线索
  - 写入 /tmp/banban_stress.json
  - 写入 /tmp/banban_preview.jpg
  ↓
electron/main.js
  - 启动/停止 Python 后端
  - 每 3 秒轮询压力 JSON
  - 维护 idle / alert / cooldown 提醒状态机
  - 创建透明置顶桌宠窗口和 Monitor 窗口
  ↓
frontend/pet-widget.html
  - Canvas 渲染桌宠 spritesheet
  - 根据压力、摄像头状态、校准状态切换动画和 UI
  - 支持拖拽、点击、气泡、设置菜单
  ↓
frontend/monitor.html
  - 展示压力分数、四类信号、校准状态和隐私预览
```

## 功能清单

- 本地摄像头压力线索识别。
- 12 秒个人平静基线校准。
- 输出 0-100 压力分数。
- 输出 `brow_furrow`、`lip_press`、`eye_squint`、`expression_freeze` 四类信号。
- 压力达到 warning / critical 条件后触发气泡提醒。
- 气泡 1 分钟自动消失，用户点击“好的”或关闭后进入 5 分钟冷却。
- 桌宠透明置顶、跳过任务栏、支持拖动位置。
- 桌宠菜单支持打开 Monitor、开关摄像头、调整动物和 UI 大小。
- Monitor 窗口展示压力分数、状态、信号条、最新样本时间和隐私预览。
- 退出应用时停止 Python 后端，并清理 `/tmp/banban_stress.json` 与 `/tmp/banban_preview.jpg`。

## 运行环境

- macOS。
- Node.js / npm。
- Python 3。
- 可用摄像头，并给终端或 Electron 授权摄像头权限。

Python 依赖：

```bash
python3 -m pip install -r requirements.txt
```

Electron 依赖：

```bash
cd electron
npm install
```

## 启动

从仓库根目录执行：

```bash
cd electron
npm start
```

`npm start` 会启动 Electron 应用，并自动拉起 Python 后端：

```bash
python3 ../backend/emotion_watch.py --headless
```

如果 macOS 首次询问摄像头权限，请允许当前终端或 Electron 访问摄像头。

## 单独调试后端

在仓库根目录执行：

```bash
python3 backend/emotion_watch.py
```

无窗口模式：

```bash
python3 backend/emotion_watch.py --headless
```

指定摄像头：

```bash
python3 backend/emotion_watch.py --camera-index 1
```

也可以通过环境变量调整摄像头选择：

```bash
BANBAN_CAMERA_INDEX=1 python3 backend/emotion_watch.py --headless
BANBAN_CAMERA_ORDER=1,2,3,0 python3 backend/emotion_watch.py --headless
```

## 目录结构

```text
banban-desktop-pet-skill-submission/
├── assets/
│   └── pets/banban/
│       ├── pet.json
│       └── spritesheet.webp
├── backend/
│   ├── emotion_watch.py
│   ├── face_landmarker_v2_with_blendshapes.task
│   └── capture.sh
├── electron/
│   ├── main.js
│   ├── preload.js
│   ├── package.json
│   └── package-lock.json
├── frontend/
│   ├── pet-widget.html
│   ├── monitor.html
│   ├── pet-widget-spec.md
│   └── integration-guide.md
├── ISSUES.md
├── PRD.md
├── README.md
└── requirements.txt
```

## 隐私说明

BanBan 的设计原则是站在使用者一侧，帮助使用者自己觉察状态，而不是向雇主或他人暴露状态。

- 人脸分析在本机完成。
- 当前代码未使用云端识别 API，也不会上传摄像头画面。
- 压力分数和状态通过本地临时文件 `/tmp/banban_stress.json` 在 Python 与 Electron 之间通信。
- Monitor 使用 `/tmp/banban_preview.jpg` 作为临时隐私预览图，画面为马赛克背景 + 主要人脸区域。
- 关闭摄像头或退出应用时，会清理上述临时文件。

## 注意事项

- BanBan 不是医疗诊断工具，也不能替代医生、心理咨询师或专业就业支持员。
- 当前是 macOS 原型，尚未适配 Windows / Linux。
- 当前没有历史数据存储和趋势分析。
- 项目依赖 `backend/face_landmarker_v2_with_blendshapes.task`，请不要删除该模型文件。
- 如果摄像头选错，可以使用 `BANBAN_CAMERA_INDEX` 或 `BANBAN_CAMERA_ORDER` 指定摄像头。

## 开发状态

这个项目是 TRAE SOLO 挑战赛公益赛道原型。它已经完成从本地压力线索识别、桌宠提醒到 Monitor 面板的基本闭环，但仍有许多可以继续打磨的地方：

- 更细分的提醒话术。
- 面向不同岗位场景的提醒策略。
- 更好的自我记录和状态回看。
- 和真实就业支持者、公益机构、当事人继续交流验证。

## 致谢

- [TRAE SOLO](https://www.trae.cn/)：项目构思、实现和迭代过程中的共创伙伴。
- [MediaPipe Face Landmarker](https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker)：本地人脸关键点和 blendshape 信号能力。
- OpenCV、Electron，以及所有让桌面小工具能快速跑起来的开源项目。
