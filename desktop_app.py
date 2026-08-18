#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
桌面版启动器：在原生窗口中运行 JAR 包自动部署系统 (Flask Web 服务)
- 后台线程启动 Flask 服务
- 使用 pywebview 打开原生窗口加载本地页面
- 关闭窗口时自动停止服务
"""

import os
import sys
import socket
import time
import logging
import threading
import webbrowser

from werkzeug.serving import make_server

HOST = "127.0.0.1"
PORT = 5001
APP_TITLE = "JAR 包自动部署系统"


def _wait_port(host, port, timeout=20):
    """等待端口可连接"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.2)
    return False


class FlaskServerThread(threading.Thread):
    """在后台线程中运行 Flask 服务"""

    def __init__(self, flask_app):
        super().__init__(daemon=True, name="flask-server")
        self.server = make_server(HOST, PORT, flask_app)

    def run(self):
        logging.getLogger("werkzeug").setLevel(logging.WARNING)
        self.server.serve_forever()

    def shutdown(self):
        try:
            self.server.shutdown()
        except Exception:
            pass


def _gui_available():
    """Linux 下需要 DISPLAY / WAYLAND_DISPLAY 才能用原生窗口"""
    if sys.platform == 'linux':
        return bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))
    return True


def _browser_fallback(url, server):
    """无法打开原生窗口时，回退到默认浏览器"""
    print("无法打开原生窗口，改用默认浏览器打开:", url)
    webbrowser.open(url)
    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        server.shutdown()


def main():
    from app import app as flask_app  # noqa: E402

    server = FlaskServerThread(flask_app)
    server.start()

    if not _wait_port(HOST, PORT):
        print("Web 服务启动失败，请查看日志")
        return 1

    url = "http://{}:{}".format(HOST, PORT)
    if not _gui_available():
        print("未检测到图形环境，使用默认浏览器打开:", url)
        _browser_fallback(url, server)
        return 0

    try:
        import webview  # 延迟导入，避免无 GUI 环境报错

        webview.create_window(
            APP_TITLE,
            url,
            width=1280,
            height=860,
            min_size=(960, 640),
            text_select=True,
        )
        webview.start()
        # 窗口关闭后停止服务
        server.shutdown()
    except Exception as exc:  # noqa: BLE001
        print("打开原生窗口失败: %s" % exc)
        _browser_fallback(url, server)
    return 0


if __name__ == "__main__":
    sys.exit(main())
