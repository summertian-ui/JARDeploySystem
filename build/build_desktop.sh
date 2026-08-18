#!/usr/bin/env bash
# ============================================================
#  跨平台打包入口
#
#  用法:
#    bash build/build_desktop.sh        # 当前平台默认包 (macOS: .app)
#    bash build/build_desktop.sh mac    # macOS .app
#    bash build/build_desktop.sh exe    # Windows .exe (需在 Windows 上运行)
#    bash build/build_desktop.sh deb    # Ubuntu .deb
#    bash build/build_desktop.sh rpm    # Ubuntu .rpm
#    bash build/build_desktop.sh snap   # Ubuntu .snap
#    bash build/build_desktop.sh linux  # deb + rpm + snap
#    bash build/build_desktop.sh all    # 本机能构建的全部 + 远程 Linux 包
#
#  说明:
#    - macOS / Linux 上执行 deb/rpm/snap 会通过配置的 Ubuntu 服务器
#      (deploy_core.py 中的 HOST) 远程构建并把产物拉回 dist/
#    - exe 无法跨平台生成，需在 Windows 上运行 build/build_windows.bat
# ============================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."

TARGET="${1:-auto}"
OS="$(uname -s)"
PY="${PYTHON:-/usr/local/bin/python3.15}"

build_mac() {
  echo "==> 打包 macOS .app (Python: $($PY --version 2>&1))"
  "$PY" -m PyInstaller --noconfirm --clean \
    --windowed \
    --name "JARDeploySystem" \
    --icon "assets/app.icns" \
    --add-data "templates:templates" \
    --add-data "static:static" \
    --collect-submodules webview \
    --osx-bundle-identifier "com.jardeploy.system" \
    --workpath "build/pyi" \
    --distpath "build/dist" \
    desktop_app.py
  echo "==> 完成: dist/JARDeploySystem.app"
}

build_exe() {
  case "$OS" in
    MINGW*|MSYS*|CYGWIN*)
      echo "==> 检测到 Windows，执行 build/build_windows.bat"
      cmd //c 'build\build_windows.bat'
      ;;
    *)
      echo "⚠️  当前系统是 $OS，无法直接生成 Windows exe（PyInstaller 不支持跨平台编译）。"
      echo "   请任选其一："
      echo "   1) 在 Windows 机器上运行: build/build_windows.bat"
      echo "   2) 把仓库推到 GitHub，用 .github/workflows/build.yml 自动构建三个平台"
      echo "      产物在 Actions 页面下载"
      exit 1
      ;;
  esac
}

build_linux() {
  if [ "$OS" = "Linux" ]; then
    echo "==> 本机为 Linux，直接构建"
    bash build/build_linux.sh "$1"
  else
    echo "==> 通过 Ubuntu 服务器远程构建 Linux 包 ($1)"
    "$PY" tools/remote_linux_build.py "$1"
  fi
}

case "$TARGET" in
  mac)
    build_mac
    ;;
  exe)
    build_exe
    ;;
  deb|rpm|snap|linux)
    build_linux "$TARGET"
    ;;
  all)
    build_mac
    build_linux all
    echo ""
    echo "exe 需在 Windows 上构建: 运行 build/build_windows.bat（或使用 GitHub Actions）"
    ;;
  auto)
    case "$OS" in
      Darwin)   build_mac ;;
      Linux)    build_linux all ;;
      MINGW*|MSYS*|CYGWIN*) build_exe ;;
      *) echo "不支持的系统: $OS"; exit 1 ;;
    esac
    ;;
  *)
    echo "未知目标: $TARGET"
    echo "可用: mac | exe | deb | rpm | snap | linux | all"
    exit 1
    ;;
esac
