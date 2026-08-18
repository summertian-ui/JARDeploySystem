# 🚀 JAR 包自动部署系统（桌面版）

[![Python](https://img.shields.io/badge/Python-3.14+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.x-000000?logo=flask)](https://flask.palletsprojects.com/)
[![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Windows%20%7C%20Ubuntu-47C0E9)]()
[![License](https://img.shields.io/badge/License-内部使用-yellow)]()

一个基于 **Flask + pywebview** 的 JAR 包自动部署管理工具，支持通过 SSH 对远程服务器上的多个 Java 服务进行**一键部署、启动、停止、批量操作与状态监控**。既可作为 Web 应用在浏览器中使用，也可打包为 **macOS / Windows / Ubuntu** 原生桌面程序。

---

## ✨ 功能特性

| 功能 | 说明 |
| --- | --- |
| 📋 服务管理 | 从数据库自动加载服务列表（`deploy_config`，`config_type=2`） |
| 🩺 状态监控 | 实时查看各服务运行状态（进程 / URL 探测） |
| ▶️ 启动 / ⏹️ 停止 | 单个服务或**批量**启动、停止 |
| 📦 一键部署 | 自动上传本地 JAR → 备份远端旧包 → 重启服务 |
| ⚙️ 全局配置 | 远端基础目录（`remote_base`）、本地基础目录（`local_base`）可在线修改并持久化到数据库 |
| 🖥️ 双形态 | 浏览器 Web 界面 + 原生桌面窗口（pywebview） |
| 🔌 远程管理 | 基于 SSH（paramiko）/ SCP 与远端服务器交互 |

---

## 🧰 技术栈

- **后端**：Python 3.14 + Flask 3.x
- **远程操作**：paramiko + scp
- **数据存储**：MySQL（PyMySQL），配置表 `deploy_config`
- **桌面壳**：pywebview（macOS Cocoa / Windows EdgeChromium / Linux GTK-WebKit）
- **打包工具**：PyInstaller

---

## 📁 目录结构

```
py/
├── app.py                  # Flask Web 应用入口（含全部 API 路由）
├── deploy_core.py          # 核心业务：数据库、SSH、部署逻辑
├── desktop_app.py          # 桌面版启动器（原生窗口 + Flask 后台服务）
├── templates/index.html    # Web 界面
├── static/web.css          # 样式
├── assets/                 # 应用图标（.icns / .ico / .png）
├── build/                  # 打包脚本
│   ├── build_desktop.sh    # 跨平台打包入口（mac/exe/deb/rpm/snap/linux/all）
│   ├── build_windows.bat   # Windows exe 打包脚本
│   └── build_linux.sh      # Ubuntu 原生打包脚本（deb/rpm/snap）
├── snapcraft.yaml          # Snap 构建配置
├── tools/remote_linux_build.py  # 通过远程 Ubuntu 服务器构建 Linux 包
└── .github/workflows/build.yml  # GitHub Actions 三平台自动构建
```

---

## 🚀 快速开始（源码运行）

### 环境要求

- Python 3.14+（本项目使用 `/usr/local/bin/python3.15`）
- MySQL 数据库（配置见 `deploy_core.py`）

### 安装依赖

```bash
cd /Users/summer/IdeaProjects/py
python3 -m pip install flask paramiko scp pymysql pywebview
```

### 以 Web 方式运行

```bash
python3 app.py
# 浏览器访问 http://localhost:5001
```

### 以桌面方式运行

```bash
python3 desktop_app.py
# 弹出原生窗口，关闭窗口自动停止服务
```

> 桌面版启动后内置服务默认监听 `127.0.0.1:5001`，仅本机可访问，更安全。

---

## 📦 打包为桌面应用

### 一键打包入口 `build/build_desktop.sh`

```bash
cd /Users/summer/IdeaProjects/py
bash build/build_desktop.sh            # 当前平台默认包（macOS: .app）
bash build/build_desktop.sh mac        # macOS .app
bash build/build_desktop.sh exe        # Windows exe（需在 Windows 上运行）
bash build/build_desktop.sh deb        # Ubuntu .deb
bash build/build_desktop.sh rpm        # Ubuntu .rpm
bash build/build_desktop.sh snap       # Ubuntu .snap
bash build/build_desktop.sh linux      # deb + rpm + snap
bash build/build_desktop.sh all        # 全部
```

> 💡 在 macOS / Linux 上执行 `deb / rpm / snap / linux` 时，会自动通过配置的 Ubuntu 服务器（`deploy_core.py` 中的 `HOST`）远程构建并把产物拉回本地 `dist/`，SSH 断线不会中断构建（服务器端 `nohup` 后台执行）。

### Windows exe

在 **Windows 10/11** 上：

```bat
build\build_windows.bat
```

或推送到 GitHub，使用仓库内置的 [GitHub Actions](.github/workflows/build.yml) 自动构建三平台产物（在 Actions 页面下载）。

### Ubuntu 原生打包

在 Ubuntu 上执行：

```bash
bash build/build_linux.sh all   # 或 deb / rpm / snap
```

---

## 📂 产物清单

构建产物统一输出到 `dist/`：

| 平台 | 产物 | 大小 | 说明 |
| --- | --- | --- | --- |
| macOS | `JARDeploySystem.app` | ~46 MB | 拖入「应用程序」即可使用 |
| Windows | `JARDeploySystem.exe` | ~50 MB | 单文件，双击运行 |
| Ubuntu | `jardeploysystem_1.0.0_amd64.deb` | ~78 MB | dpkg 安装 |
| Ubuntu | `jardeploysystem-1.0.0-1.x86_64.rpm` | ~82 MB | rpm 安装（RHEL 系亦可） |
| Ubuntu | `jardeploysystem_1.0.0_x86_64.snap` | ~86 MB | snap 安装（devmode） |

---

## 🖥️ 安装与使用

### macOS

```bash
open dist/JARDeploySystem.app
```

或手动拖到「应用程序」文件夹。

### Windows

双击 `dist\JARDeploySystem.exe` 即可（单文件，无需安装）。

### Ubuntu

```bash
# .deb
sudo dpkg -i dist/jardeploysystem_1.0.0_amd64.deb || sudo apt -f install -y

# .rpm
sudo rpm -ivh dist/jardeploysystem-1.0.0-1.x86_64.rpm

# .snap
sudo snap install dist/jardeploysystem_1.0.0_x86_64.snap --devmode
```

安装后在应用菜单找到 **「JAR 包自动部署系统」**，或在终端运行：

```bash
jardeploysystem
```

> deb/rpm 已声明运行时依赖（`libwebkit2gtk-4.1-0`、`python3-gi` 等）；Snap 为 devmode 版本（内部使用足够，如需 strict 版本请在 Ubuntu 桌面机上用 `snapcraft` 正式构建）。

---

## ⚙️ 配置说明

所有连接配置集中在 `deploy_core.py`：

| 配置项 | 位置 | 说明 |
| --- | --- | --- |
| 数据库 | `DB_CONFIG` | MySQL 连接（默认 `192.168.31.34:3306`） |
| SSH 服务器 | `HOST / USER / PASSWORD` | 部署目标服务器 |
| 远端基础目录 | `DEFAULT_REMOTE_BASE` | 默认 `/home/question` |
| 本地基础目录 | `DEFAULT_LOCAL_BASE` | 默认 `/Users/summer/IdeaProjects/zy/zy-cloud-plus` |
| 服务列表 | `deploy_config` 表 | `config_type=2` 的记录自动加载为服务 |

> 首次启动会从数据库加载全局配置与 12 个服务（示例环境）；数据库不可用时回退到默认配置。

---

## 🔑 API 一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/` | 主页 |
| GET | `/api/config` | 获取全局配置 |
| POST | `/api/config` | 更新全局配置 |
| GET | `/api/config/current` | 获取当前生效配置 |
| GET | `/api/services` | 获取服务列表 |
| GET | `/api/services/status` | 获取所有服务状态 |
| POST | `/api/service/start` | 启动单个服务 |
| POST | `/api/service/stop` | 停止单个服务 |
| POST | `/api/deploy` | 部署单个服务 |
| POST | `/api/batch-start` | 批量启动 |
| POST | `/api/batch-stop` | 批量停止 |
| POST | `/api/batch-deploy` | 批量部署 |

---

## ❓ 常见问题

**Q1：为什么服务列表为空？**
> 早期版本存在 `SERVICES` 引用失效 bug，已修复为实时读取 `deploy_core.SERVICES`。若仍为空，请检查数据库连接与服务列表配置。

**Q2：Linux 上双击无窗口弹出？**
> 无图形环境（无 `DISPLAY` / `WAYLAND_DISPLAY`）时程序会自动改用默认浏览器打开；在带桌面的 Ubuntu 上运行会正常弹出原生窗口。

**Q3：exe 在 macOS 上能直接打包吗？**
> 不能。PyInstaller 不支持跨平台编译，exe 必须在 Windows 上构建（见 `build/build_windows.bat` 或 GitHub Actions）。

**Q4：端口 5001 被占用？**
> 修改 `desktop_app.py` 中的 `PORT`，或先结束占用进程。

**Q5：日志在哪里？**
> 打包后日志按平台写入：macOS `~/Library/Logs/JarDeploySystem/`、Windows `%LOCALAPPDATA%\JarDeploySystem\logs`、Linux `~/.local/share/JarDeploySystem/logs`。

---

## 📝 更新日志

### v1.0.0（2026-08-15）

- 首次交付三平台桌面安装包（macOS .app / Windows exe / Ubuntu deb·rpm·snap）
- 修复服务列表为空的问题（`SERVICES` 实时读取）
- 修复 Linux 无显示环境 GTK 初始化崩溃，自动回退浏览器
- 日志路径跨平台化
- 新增 `build/build_desktop.sh` 统一打包入口、GitHub Actions 三平台 CI

---

*项目仅供内部使用。*
