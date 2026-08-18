#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通过配置的 Ubuntu 服务器远程构建 Linux 包 (deb/rpm/snap)，并把产物拉回本地 dist/。
构建在服务器上以 nohup 方式后台运行，SSH 断线不会中断构建；
本脚本只负责上传、轮询日志、最后拉取产物。

用法:
    python3 tools/remote_linux_build.py [deb|rpm|snap|linux|all]
环境变量覆盖: JB_HOST / JB_USER / JB_PASSWORD / JB_REMOTE_DIR / JB_POLL_TIMEOUT
"""
import os
import sys
import time

import paramiko

_args = sys.argv[1:]
POLL = "--poll" in _args

# 只支持 x86_64
TARGETS = [a for a in _args if not a.startswith("--")]
TARGET = " ".join(TARGETS) if TARGETS else "all"
POLL_TIMEOUT = int(os.environ.get("JB_POLL_TIMEOUT", "3600"))  # 秒

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HOST = os.environ.get("JB_HOST", "192.168.31.34")
USER = os.environ.get("JB_USER", "root")
PASSWORD = os.environ.get("JB_PASSWORD", "1qaz@WSX")


REMOTE_DIR = os.environ.get("JB_REMOTE_DIR", "/root/jardeploy_build")
LOCAL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_LOG = f"{REMOTE_DIR}/build.log"

UPLOAD = ["app.py", "deploy_core.py", "desktop_app.py", "snapcraft.yaml",
          "build", "assets", "templates", "static"]
SKIP = (".pyc", ".DS_Store", "__pycache__", "linux_pkg", "pyi")


def connect():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=PASSWORD, timeout=15)
    return ssh


def run_checked(ssh, cmd, timeout=30):
    _, out, err = ssh.exec_command(cmd, timeout=timeout)
    o = out.read().decode(errors="replace")
    e = err.read().decode(errors="replace")
    return o, e


def upload():
    print(f"==> 连接 {USER}@{HOST} ...")
    ssh = connect()
    sftp = ssh.open_sftp()
    print(f"==> 清空并重建 {REMOTE_DIR}")
    run_checked(ssh, f"rm -rf {REMOTE_DIR} && mkdir -p {REMOTE_DIR}")

    def up_dir(local, remote):
        for name in os.listdir(local):
            if name in SKIP or name.endswith(SKIP):
                continue
            lp = os.path.join(local, name)
            rp = f"{remote}/{name}"
            if os.path.isdir(lp):
                run_checked(ssh, f"mkdir -p {rp}")
                up_dir(lp, rp)
            else:
                sftp.put(lp, rp)
                print(f"    upload {rp}")

    for item in UPLOAD:
        lp = os.path.join(LOCAL_DIR, item)
        if not os.path.exists(lp):
            continue
        if os.path.isdir(lp):
            run_checked(ssh, f"mkdir -p {REMOTE_DIR}/{item}")
            up_dir(lp, f"{REMOTE_DIR}/{item}")
        else:
            sftp.put(lp, f"{REMOTE_DIR}/{item}")
            print(f"    upload {REMOTE_DIR}/{item}")
    sftp.close()
    ssh.close()


def start_build():
    print(f"==> 服务器后台启动构建: bash build/build_linux.sh {TARGET}")
    ssh = connect()
    run_checked(ssh, f"rm -f {BUILD_LOG}")
    # 直接在 x86_64 服务器上构建
    cmd = (f"cd {REMOTE_DIR} && setsid nohup bash build/build_linux.sh {TARGET} "
           f"> {BUILD_LOG} 2>&1 < /dev/null & echo $!")
    chan = ssh.get_transport().open_session()
    chan.settimeout(5)
    chan.exec_command(cmd)
    time.sleep(2)  # 让后台进程启动，不阻塞等待通道 EOF
    chan.close()
    ssh.close()
    print("    后台构建已启动，开始轮询...")


def poll_and_fetch():
    out_dir = os.path.join(LOCAL_DIR, "dist")
    os.makedirs(out_dir, exist_ok=True)
    deadline = time.time() + POLL_TIMEOUT
    last_tail = ""
    while time.time() < deadline:
        try:
            ssh = connect()
            try:
                tail, _ = run_checked(ssh, f"tail -n 6 {BUILD_LOG} 2>/dev/null")
                if tail.strip() and tail.strip() != last_tail:
                    print("    ... " + tail.strip().replace("\n", " | "))
                    last_tail = tail.strip()
                done, _ = run_checked(
                    ssh, f"grep -q '全部完成' {BUILD_LOG} && echo DONE || "
                         f"(pgrep -f 'build_linux.sh' >/dev/null && echo RUNNING || echo FINISHED)")
                done = done.strip()
                if done == "DONE":
                    print("==> 构建完成，拉取产物")
                    sftp = ssh.open_sftp()
                    for f in sftp.listdir(f"{REMOTE_DIR}/dist"):
                        if f.endswith((".deb", ".rpm", ".snap")):
                            sftp.get(f"{REMOTE_DIR}/dist/{f}", os.path.join(out_dir, f))
                            print(f"    fetch {f}")
                    sftp.close()
                    ssh.close()
                    print("==> 完成")
                    return True
                if done == "FINISHED":
                    print("==> 构建进程已结束，但未见成功标记（可能失败）。日志末尾：")
                    tail, _ = run_checked(ssh, f"tail -n 30 {BUILD_LOG}")
                    print(tail[-2000:])
                    ssh.close()
                    return False
            finally:
                ssh.close()
        except Exception as exc:  # noqa: BLE001
            print(f"!! 连接中断（{exc}），{15}s 后重试 ...")
            time.sleep(15)
            continue
        time.sleep(15)
    print("!! 轮询超时，构建可能仍在服务器上运行；可稍后手动拉取: "
          f"scp root@{HOST}:{REMOTE_DIR}/dist/*.deb root@{HOST}:{REMOTE_DIR}/dist/*.rpm root@{HOST}:{REMOTE_DIR}/dist/*.snap dist/")
    return False


if __name__ == "__main__":
    if POLL:
        # 只轮询并拉取（服务器上已有后台构建）
        print("==> 仅轮询服务器上已有的构建并拉取产物")
        ok = poll_and_fetch()
        sys.exit(0 if ok else 1)
    upload()
    start_build()
    ok = poll_and_fetch()
    sys.exit(0 if ok else 1)