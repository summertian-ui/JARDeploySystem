#!/usr/bin/env bash
# ============================================================
# 在 Ubuntu 上打包 Linux 桌面包 (x86_64)
# 用法: bash build/build_linux.sh [deb|rpm|snap|all]   (默认 all)
# 输出: dist/*.deb  dist/*.rpm  dist/*.snap
# ============================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."

TARGET="${1:-all}"
APP_NAME="JARDeploySystem"
APP_ID="jardeploysystem"
VERSION="1.0.0"
ARCH="amd64"
RPM_ARCH="x86_64"
APP_DIST="$(pwd)/dist/$APP_NAME"
OUT_DIR="$(pwd)/dist"
PKG_DIR="$(pwd)/build/linux_pkg"
SUDO=""
[ "$(id -u)" -ne 0 ] && SUDO="sudo"

need_deb() { [[ "$TARGET" == "all" || "$TARGET" == "linux" || "$TARGET" == "deb" ]]; }
need_rpm() { [[ "$TARGET" == "all" || "$TARGET" == "linux" || "$TARGET" == "rpm" ]]; }
need_snap() { [[ "$TARGET" == "all" || "$TARGET" == "linux" || "$TARGET" == "snap" ]]; }

log() { echo ""; echo "==> $*"; }

install_system_deps() {
  log "安装系统构建依赖"
  $SUDO apt-get update -qq
  $SUDO apt-get install -y -qq python3-venv python3-pip python3-gi \
    rpm squashfs-tools \
    libgirepository1.0-dev libcairo2-dev pkg-config \
    gir1.2-webkit2-4.1 libwebkit2gtk-4.1-0 >/dev/null
}

setup_venv() {
  log "准备 Python 虚拟环境"
  [ -d venv ] || python3 -m venv venv
  venv/bin/pip install -q --timeout 60 --upgrade pip
  venv/bin/pip install -q --timeout 60 --prefer-binary \
    flask paramiko scp pymysql pywebview "pyinstaller>=6.16"
}

build_app() {
  log "PyInstaller 构建 Linux 可执行文件 (x86_64)"
  rm -rf "$PKG_DIR" "$APP_DIST" build/pyi
  # 让 PyInstaller 能解析系统 PyGObject (gi)，打包 webview 的 GTK 后端
  PYTHONPATH="/usr/lib/python3/dist-packages" venv/bin/pyinstaller \
    --noconfirm --clean --windowed \
    --name "$APP_NAME" \
    --add-data "templates:templates" \
    --add-data "static:static" \
    --collect-submodules webview \
    --workpath "build/pyi" \
    --distpath "dist" \
    desktop_app.py
  # 确认可执行文件存在
  [ -x "$APP_DIST/$APP_NAME" ] || { echo "!! PyInstaller 输出缺失"; exit 1; }
}

make_desktop_and_icon() {
  log "准备 .desktop 与图标"
  mkdir -p "$PKG_DIR"
  cp assets/icon_512.png "$PKG_DIR/$APP_ID.png"
  cat > "$PKG_DIR/$APP_ID.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=JAR 包自动部署系统
Name[en]=JAR Deploy System
Comment=JAR 包自动部署管理工具
Exec=/usr/bin/$APP_ID
Icon=$APP_ID
Terminal=false
Categories=Development;Utility;
EOF
}

build_deb() {
  log "构建 .deb (x86_64)"
  local root="$PKG_DIR/deb_root"
  rm -rf "$root"
  mkdir -p "$root/DEBIAN" \
           "$root/usr/share/$APP_NAME" \
           "$root/usr/bin" \
           "$root/usr/share/applications" \
           "$root/usr/share/icons/hicolor/512x512/apps"

  cp -r "$APP_DIST/." "$root/usr/share/$APP_NAME/"
  ln -sf "/usr/share/$APP_NAME/$APP_NAME" "$root/usr/bin/$APP_ID"
  cp "$PKG_DIR/$APP_ID.desktop" "$root/usr/share/applications/"
  cp "$PKG_DIR/$APP_ID.png" "$root/usr/share/icons/hicolor/512x512/apps/"

  cat > "$root/DEBIAN/control" <<EOF
Package: $APP_ID
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Maintainer: JarDeploy <root@localhost>
Depends: libwebkit2gtk-4.1-0, gir1.2-webkit2-4.1, libgirepository-1.0-1
Description: JAR 包自动部署系统桌面版
 内置 Flask 服务与原生窗口的 JAR 包自动部署管理工具。
EOF

  $SUDO dpkg-deb --build --root-owner-group "$root" "$OUT_DIR/${APP_ID}_${VERSION}_${ARCH}.deb"
  log ".deb 完成: $(ls "$OUT_DIR"/*.deb 2>/dev/null || echo '无 .deb 文件')"
}

build_rpm() {
  log "构建 .rpm (x86_64)"
  local rpmdir="$PKG_DIR/rpmbuild"
  local buildroot="$rpmdir/BUILDROOT/${APP_ID}-${VERSION}-1.${RPM_ARCH}"
  rm -rf "$rpmdir"
  mkdir -p "$rpmdir"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS} \
           "$buildroot/usr/share/$APP_NAME" \
           "$buildroot/usr/bin" \
           "$buildroot/usr/share/applications" \
           "$buildroot/usr/share/icons/hicolor/512x512/apps"

  cp -r "$APP_DIST/." "$buildroot/usr/share/$APP_NAME/"
  ln -sf "/usr/share/$APP_NAME/$APP_NAME" "$buildroot/usr/bin/$APP_ID"
  cp "$PKG_DIR/$APP_ID.desktop" "$buildroot/usr/share/applications/"
  cp "$PKG_DIR/$APP_ID.png" "$buildroot/usr/share/icons/hicolor/512x512/apps/"

  cat > "$rpmdir/SPECS/$APP_ID.spec" <<EOF
Name: $APP_ID
Version: $VERSION
Release: 1
Summary: JAR auto deploy system desktop client
License: Proprietary
BuildArch: $RPM_ARCH
Requires: webkit2gtk4.1, python3-gobject
%global debug_package %{nil}
%description
JAR 包自动部署系统桌面版：内置 Flask 服务与原生窗口的部署管理工具。
%files
%defattr(-,root,root,-)
/usr/share/$APP_NAME
/usr/bin/$APP_ID
/usr/share/applications/$APP_ID.desktop
/usr/share/icons/hicolor/512x512/apps/$APP_ID.png
EOF

  rpmbuild --define "_topdir $rpmdir" --buildroot "$buildroot" -bb "$rpmdir/SPECS/$APP_ID.spec" >/dev/null
  cp "$rpmdir"/RPMS/*/*.rpm "$OUT_DIR/" 2>/dev/null || true
  log ".rpm 完成: $(ls "$OUT_DIR"/*.rpm 2>/dev/null || echo '无 .rpm 文件')"
}

manual_snap() {
  log "构建 .snap (手动 squashfs, devmode) (x86_64)"
  local stage="$PKG_DIR/snapstage"
  rm -rf "$stage"
  mkdir -p "$stage/meta"
  cp -r "$APP_DIST/." "$stage/"
  cat > "$stage/meta/snap.yaml" <<EOF
name: $APP_ID
version: "$VERSION"
summary: JAR 包自动部署系统桌面版
description: JAR 包自动部署系统的桌面客户端，内置 Flask 服务与原生窗口。
base: core24
grade: devel
confinement: devmode
apps:
  $APP_ID:
    command: $APP_NAME
    plugs: [network, network-bind, home, removable-media]
EOF
  mksquashfs "$stage" "$OUT_DIR/${APP_ID}_${VERSION}_${RPM_ARCH}.snap" \
    -noappend -comp xz -all-root -no-xattrs >/dev/null
  log ".snap 完成: $(ls "$OUT_DIR"/*.snap 2>/dev/null || echo '无 .snap 文件')"
}

build_snap() {
  if command -v snapcraft >/dev/null 2>&1; then
    log "构建 .snap (snapcraft)"
    if [ -f snapcraft.yaml ]; then
      snapcraft 2>&1 | tail -20 || { echo "!! snapcraft 失败，回退手动打包"; manual_snap; }
    else
      manual_snap
    fi
  else
    log "未检测到 snapcraft，尝试安装 (snapd + snapcraft)..."
    if $SUDO apt-get install -y -qq snapd >/dev/null 2>&1 && $SUDO snap install snapcraft --classic >/dev/null 2>&1; then
      build_snap
    else
      echo "!! 无法安装 snapcraft，使用手动 squashfs 方式打包"
      manual_snap
    fi
  fi
}

# ============ 主流程 ============
log "目标: $TARGET | 架构: x86_64"
install_system_deps
setup_venv
build_app
make_desktop_and_icon
mkdir -p "$OUT_DIR"
need_deb && build_deb
need_rpm && build_rpm
need_snap && build_snap

log "全部完成，产物:"
ls -lh "$OUT_DIR"/*.deb "$OUT_DIR"/*.rpm "$OUT_DIR"/*.snap 2>/dev/null || echo "无产物"