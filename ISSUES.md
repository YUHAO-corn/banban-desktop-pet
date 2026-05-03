# BanBan 问题追踪

## 已修复

- [x] 调试面板在 Electron 模式下仍然显示 → Electron 环境自动隐藏
- [x] Dock 栏占位 → `app.dock.hide()`
- [x] Emotion Watch OpenCV 窗口自动弹出 → 加 `--headless` 模式，Electron 默认用 headless 启动
- [x] 摄像头选错（先开 iPhone Continuity Camera）→ 检测 Continuity Camera 后优先尝试本机摄像头索引，并支持 `BANBAN_CAMERA_INDEX` 覆盖
- [x] 气泡文字截断（CJK 字符宽度计算错误）→ 新版用 HTML 气泡，自动换行
- [x] 无法拖动宠物位置 → mousedown 拖拽 + moveWindow IPC
- [x] 气泡右边被窗口截断 → 新版气泡居中定位，max-width 220px
- [x] 启动时误报摄像头遮挡 → 10 秒启动宽限期
- [x] 压力值波动导致永远无法触发提醒 → 滑动窗口（70% 超标即触发）
- [x] 首次启动等待时间太长 → 首次触发用 15 秒窗口，后续 30 秒
- [x] 猫的形象需要美化 → 替换为 SVG 浣熊（从井盖探头），辨识度高
- [x] Monitor 按钮尚未在 UI 上体现 → 设置菜单中加入"打开 Monitor 界面"按钮
- [x] 动物缩放到 0.5 会钻到 UI 后面 → UI 紧贴井盖下方，动物以井盖下沿为锚点向上缩放
- [x] 缺少摄像头开关 → 设置菜单和 Monitor 都能开关摄像头，关闭时停止 Python 后端
- [x] Monitor 无法关闭/退出 → 改为 Electron 管理的 `monitor.html` 窗口，内置关闭和 Quit
- [x] Monitor 缺少摄像头画面确认 → 后端写入隐私预览图，Monitor 显示马赛克背景 + 人脸区域预览
- [x] 设置菜单向下延伸被窗口截断 → 菜单改为从底部控制条向上展开，窗口高度留出展开空间

## 待优化

- [ ] 摄像头常开绿灯问题 — 现在可手动关闭；自动按场景开关仍需产品策略
- [ ] Python 进程在 Dock 栏显示图标 — 需要在 Info.plist 或启动参数中隐藏
- [ ] 终端 MediaPipe WARNING 日志 — 无害但视觉噪音，可考虑抑制 stderr 输出
- [ ] 尺寸偏好持久化 — 用户调整动物/UI 大小后，下次启动应还原
