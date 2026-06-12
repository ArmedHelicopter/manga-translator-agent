# 漫画翻译助手 — 桌面版快速上手

让普通用户开箱即用，无需命令行知识。

## 启动方式

### Windows
双击根目录下的 **`MangaTranslateAgent.bat`**。

### macOS / Linux
双击 **`MangaTranslateAgent.command`**
（macOS 首次需在终端执行一次 `chmod +x MangaTranslateAgent.command` 赋予执行权限）。

启动后会自动弹出一个原生应用窗口（不是浏览器），首次启动会进入语言选择和配置向导。

## 首次运行说明

启动脚本会自动完成一次性准备工作：

1. 如果检测到前端尚未构建（`web/dist` 不存在），会自动运行 `npm install` + `npm run build`。
   - 这一步需要电脑上装有 [Node.js](https://nodejs.org)。
   - 仅首次需要，之后启动会直接打开。
2. 启动内置后端服务（自动选择空闲端口，默认 8000）。
3. 打开桌面窗口。

## 依赖准备（开发者/打包者）

```bash
# Python 端（含桌面窗口库 pywebview）
pip install -e ".[dev]"

# 前端构建（仅首次或更新前端后）
cd web && npm install && npm run build
```

之后任何时候都可以用以下任一方式启动：

```bash
# 方式 1：双击启动脚本（推荐给最终用户）
#   Windows:  MangaTranslateAgent.bat
#   macOS/Linux: ./MangaTranslateAgent.command

# 方式 2：控制台命令
manga-translate-app

# 方式 3：模块方式
python -m mga.web.desktop
```

## 工作原理

```
双击启动脚本
   │
   ├─ 启动 FastAPI 后端（后台线程，自动选端口）
   │     └─ 同时提供 REST API 和构建好的前端静态资源
   │
   └─ pywebview 打开原生窗口 → 指向本地后端
         （未安装 pywebview 时自动降级为打开默认浏览器）
```

- 前端用 **HashRouter**，静态资源由后端同源 serve，API 走相对路径，无跨域问题。
- 项目数据默认保存在用户目录：`~/MangaTranslateAgent/projects`，跨次启动保留。

## 制作免安装分发包（可选，进阶）

由于本项目依赖 PyTorch、Transformers 等大型库，推荐用 PyInstaller 打包：

```bash
pip install pyinstaller
pyinstaller --name "MangaTranslateAgent" \
  --add-data "web/dist:web/dist" \
  --windowed \
  -m mga.web.desktop
```

打包时通过环境变量 `MGA_FRONTEND_DIST` 指向随包的前端目录即可让后端找到 UI 资源。
（完整离线包体积较大，建议按需裁剪模型依赖。）
