#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import paramiko
from scp import SCPClient
from datetime import datetime
import sqlite3
import logging
import json
import socket

logger = logging.getLogger(__name__)

# ========== 数据库配置 ==========
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DB_PATH = os.path.join(DATA_DIR, 'deploy.db')
CONFIG_JSON = os.path.join(BASE_DIR, 'static', 'deploy.json')
STATIC_DIR = os.path.join(BASE_DIR, 'static')

# ========== 全局变量 ==========
CURRENT_SERVER = None
CURRENT_SYSTEM = 'macos'
REMOTE_BASE = None
LOCAL_BASE = None
SERVICES = []
SERVER_LIST = []
HOST = None
USER = None
PASSWORD = None


# ========================== 数据库操作 ==========================

def get_db_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """从 deploy.json 初始化数据库"""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        logger.info(f"🗑️ 已删除旧数据库: {DB_PATH}")

    os.makedirs(DATA_DIR, exist_ok=True)

    with open(CONFIG_JSON, 'r', encoding='utf-8') as f:
        config = json.load(f)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for table_name, table_config in config['tables'].items():
        cursor.execute(table_config['create_sql'])

        if table_config.get('init_data'):
            for data in table_config['init_data']:
                columns = ', '.join(data.keys())
                placeholders = ', '.join(['?' for _ in data])
                sql = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
                cursor.execute(sql, list(data.values()))

    conn.commit()
    conn.close()
    logger.info(f"✅ 数据库初始化完成: {DB_PATH}")


def init_db_with_config(config):
    """使用传入的配置初始化数据库"""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        logger.info(f"🗑️ 已删除旧数据库: {DB_PATH}")

    os.makedirs(DATA_DIR, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for table_name, table_config in config['tables'].items():
        cursor.execute(table_config['create_sql'])

        if table_config.get('init_data'):
            for data in table_config['init_data']:
                columns = ', '.join(data.keys())
                placeholders = ', '.join(['?' for _ in data])
                sql = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
                cursor.execute(sql, list(data.values()))

    conn.commit()
    conn.close()
    logger.info(f"✅ 数据库初始化完成: {DB_PATH}")


# ========================== 模板文件处理 ==========================

def get_template_content(template_name):
    """读取模板文件内容"""
    template_path = os.path.join(STATIC_DIR, template_name)
    if not os.path.exists(template_path):
        logger.warning(f"模板文件不存在: {template_path}")
        return None
    with open(template_path, 'r', encoding='utf-8') as f:
        return f.read()


def render_start_sh(service_name, remote_base):
    """渲染 start.sh 模板"""
    template = get_template_content('start.sh')
    if not template:
        return None

    content = template.replace('APP_NAME', service_name)
    content = content.replace('APP_DIR', f'{remote_base}/{service_name}')
    return content


# ========================== SSH 操作 ==========================

def run_ssh_command(ssh, command, check=False):
    """执行 SSH 命令"""
    stdin, stdout, stderr = ssh.exec_command(command)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if check and err:
        raise Exception(f"Command failed: {command}\n{err}")
    return out, err


def get_ssh_connection():
    """获取 SSH 连接"""
    if not HOST or not USER or not PASSWORD:
        raise Exception("服务器未配置，请先选择服务器")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=PASSWORD, timeout=10)
    return ssh


def ensure_remote_directory(ssh, remote_dir):
    """确保远程目录存在"""
    cmd = f"mkdir -p {remote_dir}"
    run_ssh_command(ssh, cmd)
    return True


def upload_script_file(ssh, remote_path, content):
    """上传脚本文件到远程服务器"""
    temp_path = os.path.join(DATA_DIR, 'temp_script.sh')
    with open(temp_path, 'w', encoding='utf-8') as f:
        f.write(content)

    try:
        with SCPClient(ssh.get_transport()) as scp:
            scp.put(temp_path, remote_path)
        run_ssh_command(ssh, f"chmod +x {remote_path}")
        logger.info(f"✅ 上传脚本成功: {remote_path}")
        return True
    except Exception as e:
        logger.error(f"❌ 上传脚本失败: {str(e)}")
        return False
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def check_and_upload_start_sh(ssh, service_name, remote_base):
    """检查并上传 start.sh 文件"""
    service_dir = os.path.join(remote_base, service_name)
    start_sh_remote = os.path.join(service_dir, "start.sh")

    ensure_remote_directory(ssh, service_dir)

    cmd = f"test -f {start_sh_remote} && echo 'exists'"
    out, _ = run_ssh_command(ssh, cmd)

    if "exists" not in out:
        start_content = render_start_sh(service_name, remote_base)
        if start_content:
            upload_script_file(ssh, start_sh_remote, start_content)
            logger.info(f"✅ 上传 start.sh 到: {start_sh_remote}")
            return True, "start.sh 已上传"

    return True, "start.sh 已就绪"


def check_service_directory(ssh, service_name, remote_base):
    """检查服务目录和 start.sh 是否存在"""
    service_dir = os.path.join(remote_base, service_name)
    start_sh_remote = os.path.join(service_dir, "start.sh")

    cmd = f"test -d {service_dir} && echo 'exists'"
    out, _ = run_ssh_command(ssh, cmd)
    if "exists" not in out:
        return False, f"服务目录不存在: {service_dir}"

    cmd = f"test -f {start_sh_remote} && echo 'exists'"
    out, _ = run_ssh_command(ssh, cmd)
    if "exists" not in out:
        return False, f"start.sh 不存在: {start_sh_remote}"

    return True, "服务目录和 start.sh 已就绪"


def upload_application_yml(ssh, service_name, remote_base, yml_content):
    """上传 application.yml 配置文件"""
    if not yml_content:
        return False, "application.yml 内容为空"

    service_dir = os.path.join(remote_base, service_name)
    ensure_remote_directory(ssh, service_dir)

    remote_yml_path = os.path.join(service_dir, "application.yml")

    temp_path = os.path.join(DATA_DIR, 'temp_application.yml')
    with open(temp_path, 'w', encoding='utf-8') as f:
        f.write(yml_content)

    try:
        with SCPClient(ssh.get_transport()) as scp:
            scp.put(temp_path, remote_yml_path)
        logger.info(f"✅ 上传 application.yml 到: {remote_yml_path}")
        return True, "配置文件上传成功"
    except Exception as e:
        logger.error(f"❌ 上传 application.yml 失败: {str(e)}")
        return False, f"上传失败: {str(e)}"
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def get_process_info(ssh, pid):
    """获取进程的内存占用和监听端口"""
    cmd_mem = f"ps -o vsz,rss -p {pid} | tail -1"
    out, _ = run_ssh_command(ssh, cmd_mem)
    parts = out.split() if out else []
    rss = parts[1] if len(parts) > 1 else 0
    rss_mb = int(rss) // 1024 if rss else 0

    cmd_port = f"ss -tlnp 2>/dev/null | grep 'pid={pid}' | awk '{{print $4}}' | cut -d: -f2 | paste -sd ','"
    port, _ = run_ssh_command(ssh, cmd_port)

    return rss_mb, port


def stop_service(ssh, service_name):
    """停止服务"""
    service_dir = os.path.join(REMOTE_BASE, service_name)
    jar_name = f"{service_name}.jar"

    cmd = f"ps -ef | grep '{jar_name}' | grep -v grep | grep '{service_dir}' | awk '{{print $2}}'"
    out, _ = run_ssh_command(ssh, cmd)
    pids = out.split()

    if pids:
        for pid in pids:
            run_ssh_command(ssh, f"kill {pid}")
            time.sleep(2)
            cmd_check = f"kill -0 {pid} 2>/dev/null && echo 'running'"
            out_check, _ = run_ssh_command(ssh, cmd_check)
            if "running" in out_check:
                run_ssh_command(ssh, f"kill -9 {pid}")
        return True, f"已停止进程: {', '.join(pids)}"
    else:
        return False, "未找到运行中的进程"


def start_service_via_script(ssh, service_name):
    """使用 start.sh 脚本启动服务"""
    start_script = os.path.join(REMOTE_BASE, service_name, "start.sh")
    service_dir = os.path.join(REMOTE_BASE, service_name)

    cmd = f"test -f {start_script} && echo 'exists'"
    out, _ = run_ssh_command(ssh, cmd)
    if "exists" not in out:
        raise Exception(f"start.sh 不存在: {start_script}")

    cmd = f"cd {service_dir} && bash {start_script}"
    out, err = run_ssh_command(ssh, cmd)

    if "SUCCESS" in out or "SUCCESS" in err:
        time.sleep(2)
        jar_name = f"{service_name}.jar"
        cmd_check = f"ps -ef | grep '{jar_name}' | grep -v grep | grep '{service_dir}' | awk '{{print $2}}'"
        out_check, _ = run_ssh_command(ssh, cmd_check)

        if out_check:
            return out_check.split()[0], f"启动成功: {out}\n{err}"

        time.sleep(3)
        out_check, _ = run_ssh_command(ssh, cmd_check)
        if out_check:
            return out_check.split()[0], f"启动成功(延迟): {out}\n{err}"

    if "FAILED" in out or "FAILED" in err:
        raise Exception(f"start.sh 报告启动失败: {out}\n{err}")

    raise Exception(f"服务启动失败: {out}\n{err}")


# ========================== 日志操作 ==========================

def get_client_ip():
    """获取客户端IP"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


def add_operation_log(operation_type, service_name, status, message, detail=None, operator=None, ip_address=None,
                      user_agent=None):
    """添加操作日志"""
    conn = get_db_connection()
    cursor = conn.cursor()
    detail_json = json.dumps(detail, ensure_ascii=False) if detail else None
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    cursor.execute('''
                   INSERT INTO deploy_log
                   (operation_type, service_name, status, message, detail, operator, ip_address, user_agent,
                    create_time, update_time)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ''', (
                       operation_type,
                       service_name,
                       status,
                       message[:500] if message else '',
                       detail_json,
                       operator or 'system',
                       ip_address or get_client_ip(),
                       user_agent or 'Unknown',
                       now,
                       now
                   ))

    conn.commit()
    conn.close()
    return True


def get_operation_logs(limit=100, offset=0, operation_type=None, service_name=None, status=None, start_time=None,
                       end_time=None):
    """获取操作日志"""
    conn = get_db_connection()
    cursor = conn.cursor()

    sql = '''
          SELECT id, operation_type, service_name, status, message, detail,
                 operator, ip_address, user_agent, create_time, update_time
          FROM deploy_log
          WHERE 1=1
          '''
    params = []

    if operation_type:
        sql += " AND operation_type = ?"
        params.append(operation_type)
    if service_name:
        sql += " AND service_name = ?"
        params.append(service_name)
    if status:
        sql += " AND status = ?"
        params.append(status)
    if start_time:
        sql += " AND create_time >= ?"
        params.append(start_time)
    if end_time:
        sql += " AND create_time <= ?"
        params.append(end_time)

    sql += " ORDER BY create_time DESC LIMIT ? OFFSET ?"
    params.append(limit)
    params.append(offset)

    cursor.execute(sql, params)
    logs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return logs


def get_log_count(operation_type=None, service_name=None, status=None):
    """获取日志总数"""
    conn = get_db_connection()
    cursor = conn.cursor()

    sql = "SELECT COUNT(*) FROM deploy_log WHERE 1=1"
    params = []

    if operation_type:
        sql += " AND operation_type = ?"
        params.append(operation_type)
    if service_name:
        sql += " AND service_name = ?"
        params.append(service_name)
    if status:
        sql += " AND status = ?"
        params.append(status)

    cursor.execute(sql, params)
    count = cursor.fetchone()[0]
    conn.close()
    return count


def clear_operation_logs(days=None):
    """清空操作日志"""
    conn = get_db_connection()
    cursor = conn.cursor()

    if days:
        cursor.execute(
            "DELETE FROM deploy_log WHERE DATE(create_time) < DATE('now', '-' || ? || ' days')",
            (days,)
        )
        count = cursor.rowcount
        message = f"已删除 {count} 条 {days} 天前的日志"
    else:
        cursor.execute("DELETE FROM deploy_log")
        count = cursor.rowcount
        message = f"已清空所有日志，共 {count} 条"

    conn.commit()
    conn.close()
    return True, message


def get_log_statistics():
    """获取日志统计信息"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as total FROM deploy_log")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT status, COUNT(*) as count FROM deploy_log GROUP BY status")
    status_stats = {row[0]: row[1] for row in cursor.fetchall()}

    cursor.execute("""
                   SELECT operation_type, COUNT(*) as count
                   FROM deploy_log
                   GROUP BY operation_type
                   ORDER BY count DESC LIMIT 10
                   """)
    type_stats = {row[0]: row[1] for row in cursor.fetchall()}

    cursor.execute("SELECT MAX(create_time) as last_time FROM deploy_log")
    result = cursor.fetchone()
    last_time = result[0] if result and result[0] else '无操作记录'

    conn.close()

    return {
        'total': total,
        'status_stats': status_stats,
        'type_stats': type_stats,
        'last_time': last_time
    }


# ========================== 系统配置管理 ==========================

def get_default_system():
    """获取默认系统配置"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT config_name FROM system_config WHERE is_default = 1 LIMIT 1")
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 'macos'


def get_system_config(system_name):
    """获取系统配置"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
                   SELECT id, config_name, local_base, is_default, create_time, update_time, config_status
                   FROM system_config
                   WHERE config_name = ?
                   ''', (system_name,))
    result = cursor.fetchone()
    conn.close()
    return dict(result) if result else None


def get_all_system_configs():
    """获取所有系统配置"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
                   SELECT id, config_name, local_base, is_default, create_time, update_time, config_status
                   FROM system_config
                   ORDER BY is_default DESC, config_name
                   ''')
    results = cursor.fetchall()
    conn.close()
    return [dict(row) for row in results]


def save_system_config(system_name, local_base, is_default=0):
    """保存系统配置"""
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    existing = get_system_config(system_name)

    if existing:
        cursor.execute('''
                       UPDATE system_config
                       SET local_base = ?, is_default = ?, update_time = ?, config_status = 'active'
                       WHERE config_name = ?
                       ''', (local_base, is_default, now, system_name))
    else:
        cursor.execute('''
                       INSERT INTO system_config (config_name, local_base, is_default, create_time, update_time, config_status)
                       VALUES (?, ?, ?, ?, ?, 'active')
                       ''', (system_name, local_base, is_default, now, now))

    # 如果当前设置为默认，取消其他默认
    if is_default:
        cursor.execute('''
                       UPDATE system_config
                       SET is_default = 0
                       WHERE config_name != ? AND is_default = 1
                       ''', (system_name,))

    conn.commit()
    conn.close()
    return True, f"系统配置 {system_name} 保存成功"


def save_system_config_local_base(system_name, local_base):
    """仅更新系统配置的本地目录"""
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    existing = get_system_config(system_name)

    if existing:
        cursor.execute('''
                       UPDATE system_config
                       SET local_base = ?, update_time = ?
                       WHERE config_name = ?
                       ''', (local_base, now, system_name))
    else:
        cursor.execute('''
                       INSERT INTO system_config (config_name, local_base, create_time, update_time, config_status)
                       VALUES (?, ?, ?, ?, 'active')
                       ''', (system_name, local_base, now, now))

    conn.commit()
    conn.close()
    return True, f"系统配置 {system_name} 本地目录更新成功"


# ========================== 服务器配置管理 ==========================

def get_servers(system_name=None):
    """获取服务器列表（根据 config_name 过滤）"""
    conn = get_db_connection()
    cursor = conn.cursor()

    if system_name is None:
        system_name = CURRENT_SYSTEM or 'macos'

    cursor.execute('''
                   SELECT id, config_name, server_name, host, username, password, port,
                          remote_base, sort_order, is_default, create_time, update_time, config_status
                   FROM server_config
                   WHERE config_name = ?
                   ORDER BY is_default DESC, sort_order ASC, id ASC
                   ''', (system_name,))

    servers = [dict(row) for row in cursor.fetchall()]
    for server in servers:
        test_server_connection(server)
    conn.close()
    return servers


def get_all_servers():
    """获取所有服务器列表"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
                   SELECT id, config_name, server_name, host, username, password, port,
                          remote_base, sort_order, is_default, create_time, update_time, config_status
                   FROM server_config
                   ORDER BY config_name, is_default DESC, sort_order ASC, id ASC
                   ''')

    servers = [dict(row) for row in cursor.fetchall()]
    for server in servers:
        test_server_connection(server)
    conn.close()
    return servers


def get_server(server_id):
    """获取单个服务器信息"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
                   SELECT id, config_name, server_name, host, username, password, port,
                          remote_base, sort_order, is_default, create_time, update_time, config_status
                   FROM server_config
                   WHERE id = ?
                   ''', (server_id,))
    result = cursor.fetchone()
    conn.close()
    return dict(result) if result else None


def get_default_server(system_name=None):
    """获取默认服务器"""
    if system_name is None:
        system_name = CURRENT_SYSTEM or 'macos'

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
                   SELECT id, config_name, server_name, host, username, password, port,
                          remote_base, sort_order, is_default, create_time, update_time, config_status
                   FROM server_config
                   WHERE config_name = ? AND is_default = 1
                   LIMIT 1
                   ''', (system_name,))
    result = cursor.fetchone()
    conn.close()
    return dict(result) if result else None


def test_server_connection(server_data):
    """测试服务器连接"""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(server_data['host'], username=server_data['username'],
                    password=server_data['password'], timeout=10)
        server_data['config_status'] = 'active'
        ssh.close()
    except paramiko.AuthenticationException:
        server_data['config_status'] = 'SSH 认证失败'
    except paramiko.SSHException:
        server_data['config_status'] = 'SSH 协议错误'
    except socket.timeout:
        server_data['config_status'] = 'SSH 连接超时'
    except socket.error:
        server_data['config_status'] = 'SSH 网络错误'
    except Exception:
        server_data['config_status'] = 'SSH 连接失败'


def save_server(server_id, config_name, server_name, host, username, password, port,
                remote_base=None, sort_order=0, is_default=0):
    """保存服务器信息"""
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if remote_base is None:
        remote_base = '/home/question'

    if server_id:
        cursor.execute('''
                       UPDATE server_config
                       SET config_name = ?, server_name = ?, host = ?, username = ?, password = ?,
                           port = ?, remote_base = ?, sort_order = ?, is_default = ?,
                           update_time = ?, config_status = 'active'
                       WHERE id = ?
                       ''', (config_name, server_name, host, username, password, port,
                             remote_base, sort_order, is_default, now, server_id))
    else:
        cursor.execute('''
                       INSERT INTO server_config
                       (config_name, server_name, host, username, password, port,
                        remote_base, sort_order, is_default, create_time, update_time, config_status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
                       ''', (config_name, server_name, host, username, password, port,
                             remote_base, sort_order, is_default, now, now))

    # 如果设置为默认，取消同 config_name 下的其他默认
    if is_default and server_id:
        cursor.execute('''
                       UPDATE server_config
                       SET is_default = 0
                       WHERE config_name = ? AND id != ? AND is_default = 1
                       ''', (config_name, server_id))
    elif is_default:
        cursor.execute('''
                       UPDATE server_config
                       SET is_default = 0
                       WHERE config_name = ? AND is_default = 1
                       ''', (config_name,))

    conn.commit()
    conn.close()

    global SERVER_LIST
    SERVER_LIST = get_servers()

    return True, "服务器保存成功"


def delete_server(server_id):
    """删除服务器"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM service_config WHERE server_id = ?", (server_id,))
    if cursor.fetchone()[0] > 0:
        conn.close()
        return False, "该服务器已被服务配置引用，请先删除相关服务"

    cursor.execute("DELETE FROM server_config WHERE id = ?", (server_id,))
    conn.commit()
    conn.close()

    global SERVER_LIST
    SERVER_LIST = get_servers()

    return True, "服务器删除成功"


def set_current_server(server_id):
    """设置当前服务器"""
    global CURRENT_SERVER, REMOTE_BASE, LOCAL_BASE, HOST, USER, PASSWORD, CURRENT_SYSTEM

    server = get_server(server_id)
    if not server:
        return False, f"服务器 ID {server_id} 不存在"

    CURRENT_SERVER = server
    HOST = server['host']
    USER = server['username']
    PASSWORD = server['password']
    REMOTE_BASE = server.get('remote_base', '/home/question')

    if server.get('config_name'):
        CURRENT_SYSTEM = server['config_name']

    # 加载系统配置
    system_config = get_system_config(CURRENT_SYSTEM)
    if system_config:
        LOCAL_BASE = system_config['local_base']
    else:
        LOCAL_BASE = ''

    load_services_from_db()

    logger.info(f"✅ 切换到服务器: {server['server_name']} ({server['host']}), 系统: {CURRENT_SYSTEM}")
    return True, f"已切换到服务器: {server['server_name']}"


# ========================== 服务配置管理 ==========================

def get_services(system_name=None, server_id=None):
    """获取服务列表"""
    conn = get_db_connection()
    cursor = conn.cursor()

    if system_name is None:
        system_name = CURRENT_SYSTEM or 'macos'

    sql = '''
          SELECT id, config_name, server_id, service_name, local_path, remote_path,
                 create_time, update_time, config_status
          FROM service_config
          WHERE config_name = ?
          '''
    params = [system_name]

    if server_id:
        sql += " AND server_id = ?"
        params.append(server_id)

    sql += " ORDER BY service_name"

    cursor.execute(sql, params)
    results = cursor.fetchall()
    conn.close()
    return [dict(row) for row in results]


def get_service(service_id):
    """获取单个服务信息"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
                   SELECT id, config_name, server_id, service_name, local_path, remote_path,
                          create_time, update_time, config_status
                   FROM service_config
                   WHERE id = ?
                   ''', (service_id,))
    result = cursor.fetchone()
    conn.close()
    return dict(result) if result else None


def get_service_by_name(service_name, system_name=None):
    """根据服务名称获取服务"""
    if system_name is None:
        system_name = CURRENT_SYSTEM or 'macos'

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
                   SELECT id, config_name, server_id, service_name, local_path, remote_path,
                          create_time, update_time, config_status
                   FROM service_config
                   WHERE config_name = ? AND service_name = ?
                   ''', (system_name, service_name))
    result = cursor.fetchone()
    conn.close()
    return dict(result) if result else None


def get_services_for_server(server_id):
    """获取指定服务器的服务列表"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
                   SELECT id, config_name, server_id, service_name, local_path, remote_path,
                          create_time, update_time, config_status
                   FROM service_config
                   WHERE server_id = ?
                   ORDER BY service_name
                   ''', (server_id,))
    results = cursor.fetchall()
    conn.close()
    return [dict(row) for row in results]


def save_service(service_id, config_name, server_id, service_name, local_path, remote_path=None):
    """保存服务配置"""
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if remote_path is None:
        remote_path = service_name

    if service_id:
        cursor.execute('''
                       UPDATE service_config
                       SET config_name = ?, server_id = ?, service_name = ?,
                           local_path = ?, remote_path = ?,
                           update_time = ?, config_status = 'active'
                       WHERE id = ?
                       ''', (config_name, server_id, service_name, local_path, remote_path, now, service_id))
    else:
        cursor.execute('''
                       INSERT INTO service_config
                       (config_name, server_id, service_name, local_path, remote_path,
                        create_time, update_time, config_status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 'active')
                       ''', (config_name, server_id, service_name, local_path, remote_path, now, now))

    conn.commit()
    conn.close()

    load_services_from_db()

    return True, f"服务 {service_name} 保存成功"


def delete_service(service_id):
    """删除服务配置"""
    conn = get_db_connection()
    cursor = conn.cursor()

    service = get_service(service_id)
    service_name = service['service_name'] if service else '未知'

    cursor.execute("DELETE FROM service_config WHERE id = ?", (service_id,))
    conn.commit()
    conn.close()

    load_services_from_db()

    return True, f"服务 {service_name} 已删除"


def load_services_from_db():
    """从数据库加载服务列表"""
    global SERVICES

    if not CURRENT_SERVER:
        SERVICES = []
        return SERVICES

    SERVICES = get_services(CURRENT_SYSTEM, CURRENT_SERVER['id'])
    logger.info(f"✅ 加载了 {len(SERVICES)} 个服务 (系统: {CURRENT_SYSTEM})")
    return SERVICES


def get_service_status(ssh, service):
    """获取单个服务的状态"""
    service_name = service['service_name']
    service_id = service['id']
    config_name = service['config_name']
    server_id = service['server_id']
    local_path = service.get('local_path', '')
    remote_path = service.get('remote_path', service_name)

    if ssh is None:
        return {
            "id": service_id,
            "service": service_name,
            "config_name": config_name,
            "server_id": server_id,
            "path": local_path,
            "remote_path": remote_path,
            "status": "unknown",
            "pid": None,
            "memory": "N/A",
            "port": "N/A",
            "jar_exists": None
        }

    service_dir = os.path.join(REMOTE_BASE, remote_path)
    jar_name = f"{service_name}.jar"

    cmd = f"ps -ef | grep '{jar_name}' | grep -v grep | grep '{service_dir}' | awk '{{print $2}}'"
    out, _ = run_ssh_command(ssh, cmd)
    pids = out.split()

    if pids:
        pid = pids[0]
        mem_mb, port = get_process_info(ssh, pid)

        return {
            "id": service_id,
            "service": service_name,
            "config_name": config_name,
            "server_id": server_id,
            "path": local_path,
            "remote_path": remote_path,
            "status": "running",
            "pid": pid,
            "memory": f"{mem_mb} MB",
            "port": port,
            "jar_exists": True
        }
    else:
        remote_jar = os.path.join(service_dir, f"{service_name}.jar")
        cmd = f"test -f {remote_jar} && echo 'exists'"
        out, _ = run_ssh_command(ssh, cmd)
        jar_exists = "exists" in out

        return {
            "id": service_id,
            "service": service_name,
            "config_name": config_name,
            "server_id": server_id,
            "path": local_path,
            "remote_path": remote_path,
            "status": "stopped" if jar_exists else "not_deployed",
            "pid": None,
            "memory": "N/A",
            "port": "N/A",
            "jar_exists": jar_exists
        }


def get_all_services_status(ssh):
    """获取所有服务的状态"""
    results = []
    services = get_services(CURRENT_SYSTEM, CURRENT_SERVER['id'] if CURRENT_SERVER else None)

    for svc in services:
        status = get_service_status(ssh, svc)
        if status:
            results.append(status)

    return results


# ========================== 服务操作 ==========================

def get_local_jar_path(service_name):
    """获取本地 JAR 路径"""
    service = get_service_by_name(service_name)
    if service and LOCAL_BASE:
        return os.path.join(LOCAL_BASE, service.get('local_path', ''))
    return None


def deploy_service(service_name, local_jar_path=None, operator=None, ip_address=None, user_agent=None,
                   yml_content=None):
    """部署服务"""
    service = get_service_by_name(service_name)
    if not service:
        return False, f"服务 {service_name} 不存在", {}

    if local_jar_path is None:
        local_jar = get_local_jar_path(service_name)
    else:
        local_jar = local_jar_path

    if not local_jar or not os.path.isfile(local_jar):
        add_operation_log('DEPLOY', service_name, 'FAILED', f"本地JAR不存在: {local_jar}",
                          {'local_jar': local_jar}, operator, ip_address, user_agent)
        return False, f"本地JAR不存在: {local_jar}", {}

    result = {
        "service": service_name,
        "local_jar": local_jar,
        "steps": [],
        "pid": None,
        "memory": None,
        "port": None
    }

    ssh = get_ssh_connection()
    try:
        result["steps"].append("SSH连接成功")

        remote_path = service.get('remote_path', service_name)

        success, msg = check_and_upload_start_sh(ssh, remote_path, REMOTE_BASE)
        result["steps"].append(f"start.sh: {msg}")

        valid, check_msg = check_service_directory(ssh, remote_path, REMOTE_BASE)
        if not valid:
            raise Exception(check_msg)
        result["steps"].append(f"目录验证: {check_msg}")

        if yml_content:
            success, msg = upload_application_yml(ssh, remote_path, REMOTE_BASE, yml_content)
            if success:
                result["steps"].append("application.yml 上传成功")
            else:
                result["steps"].append(f"application.yml 上传失败: {msg}")

        stopped, msg = stop_service(ssh, remote_path)
        result["steps"].append(f"停止服务: {msg}")

        remote_jar = os.path.join(REMOTE_BASE, remote_path, f"{service_name}.jar")
        backup_dir = os.path.join(REMOTE_BASE, remote_path, "back")
        run_ssh_command(ssh, f"mkdir -p {backup_dir}")

        cmd = f"test -f {remote_jar} && echo 'exists'"
        out, _ = run_ssh_command(ssh, cmd)
        if "exists" in out:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{service_name}_{timestamp}.jar"
            backup_path = os.path.join(backup_dir, backup_name)
            run_ssh_command(ssh, f"mv {remote_jar} {backup_path}")
            result["steps"].append(f"备份到: {backup_path}")
        else:
            result["steps"].append("没有现有JAR需要备份")

        service_dir = os.path.join(REMOTE_BASE, remote_path)
        run_ssh_command(ssh, f"mkdir -p {service_dir}")

        with SCPClient(ssh.get_transport()) as scp:
            scp.put(local_jar, remote_jar)
        result["steps"].append(f"上传到: {remote_jar}")

        pid, start_msg = start_service_via_script(ssh, remote_path)
        result["pid"] = pid
        result["steps"].append(f"启动成功, PID: {pid}")

        mem, port = get_process_info(ssh, pid)
        result["memory"] = f"{mem} MB"
        result["port"] = port
        result["steps"].append(f"内存: {mem} MB, 端口: {port}")

        ssh.close()

        add_operation_log('DEPLOY', service_name, 'SUCCESS', f"部署成功",
                          result, operator, ip_address, user_agent)

        return True, f"服务 {service_name} 部署成功", result

    except Exception as e:
        result["steps"].append(f"ERROR: {str(e)}")
        add_operation_log('DEPLOY', service_name, 'FAILED', f"部署失败: {str(e)}",
                          result, operator, ip_address, user_agent)
        return False, f"部署失败: {str(e)}", result


def manual_start_service(service_name, operator=None, ip_address=None, user_agent=None):
    """手动启动服务"""
    service = get_service_by_name(service_name)
    if not service:
        return False, f"服务 {service_name} 不存在"

    ssh = get_ssh_connection()
    try:
        remote_path = service.get('remote_path', service_name)

        check_and_upload_start_sh(ssh, remote_path, REMOTE_BASE)

        valid, check_msg = check_service_directory(ssh, remote_path, REMOTE_BASE)
        if not valid:
            raise Exception(check_msg)

        pid, msg = start_service_via_script(ssh, remote_path)
        mem, port = get_process_info(ssh, pid)
        ssh.close()

        add_operation_log('START', service_name, 'SUCCESS', f"启动成功，PID: {pid}, 内存: {mem}MB, 端口: {port}",
                          {'pid': pid, 'memory': f"{mem} MB", 'port': port}, operator, ip_address, user_agent)

        return True, f"服务启动成功，PID: {pid}, 内存: {mem}MB, 端口: {port}"
    except Exception as e:
        ssh.close()
        add_operation_log('START', service_name, 'FAILED', f"启动失败: {str(e)}",
                          None, operator, ip_address, user_agent)
        return False, f"启动失败: {str(e)}"


def manual_stop_service(service_name, operator=None, ip_address=None, user_agent=None):
    """手动停止服务"""
    service = get_service_by_name(service_name)
    if not service:
        return False, f"服务 {service_name} 不存在"

    ssh = get_ssh_connection()
    try:
        remote_path = service.get('remote_path', service_name)
        stopped, msg = stop_service(ssh, remote_path)
        ssh.close()

        if stopped:
            add_operation_log('STOP', service_name, 'SUCCESS', f"停止成功: {msg}",
                              None, operator, ip_address, user_agent)
            return True, f"服务停止成功: {msg}"
        else:
            add_operation_log('STOP', service_name, 'FAILED', f"停止失败: {msg}",
                              None, operator, ip_address, user_agent)
            return False, f"停止失败: {msg}"
    except Exception as e:
        ssh.close()
        add_operation_log('STOP', service_name, 'FAILED', f"停止失败: {str(e)}",
                          None, operator, ip_address, user_agent)
        return False, f"停止失败: {str(e)}"


def upload_service_config(service_name, yml_content, operator=None, ip_address=None, user_agent=None):
    """上传服务配置文件"""
    service = get_service_by_name(service_name)
    if not service:
        return False, f"服务 {service_name} 不存在"

    ssh = get_ssh_connection()
    try:
        remote_path = service.get('remote_path', service_name)
        check_and_upload_start_sh(ssh, remote_path, REMOTE_BASE)

        success, msg = upload_application_yml(ssh, remote_path, REMOTE_BASE, yml_content)
        ssh.close()

        if success:
            add_operation_log('CONFIG_UPDATE', service_name, 'SUCCESS',
                              f"上传配置文件: {remote_path}/application.yml",
                              {'service_name': service_name}, operator, ip_address, user_agent)
        else:
            add_operation_log('CONFIG_UPDATE', service_name, 'FAILED',
                              f"上传配置文件失败: {msg}",
                              {'service_name': service_name}, operator, ip_address, user_agent)

        return success, msg
    except Exception as e:
        ssh.close()
        return False, str(e)


# ========================== 批量操作 ==========================

def batch_start_services(service_names, operator=None, ip_address=None, user_agent=None):
    results = []
    for service_name in service_names:
        try:
            success, msg = manual_start_service(service_name, operator, ip_address, user_agent)
            results.append({"service": service_name, "success": success, "message": msg})
        except Exception as e:
            results.append({"service": service_name, "success": False, "message": str(e)})

    success_count = sum(1 for r in results if r['success'])
    add_operation_log('BATCH_START', None, 'SUCCESS' if success_count == len(service_names) else 'FAILED',
                      f"批量启动: 成功 {success_count}/{len(service_names)}",
                      {'services': service_names, 'results': results}, operator, ip_address, user_agent)
    return results


def batch_stop_services(service_names, operator=None, ip_address=None, user_agent=None):
    results = []
    for service_name in service_names:
        try:
            success, msg = manual_stop_service(service_name, operator, ip_address, user_agent)
            results.append({"service": service_name, "success": success, "message": msg})
        except Exception as e:
            results.append({"service": service_name, "success": False, "message": str(e)})

    success_count = sum(1 for r in results if r['success'])
    add_operation_log('BATCH_STOP', None, 'SUCCESS' if success_count == len(service_names) else 'FAILED',
                      f"批量停止: 成功 {success_count}/{len(service_names)}",
                      {'services': service_names, 'results': results}, operator, ip_address, user_agent)
    return results


def batch_deploy_services(service_names, operator=None, ip_address=None, user_agent=None):
    results = []
    for service_name in service_names:
        try:
            success, msg, detail = deploy_service(service_name, operator=operator, ip_address=ip_address,
                                                  user_agent=user_agent)
            results.append({"service": service_name, "success": success, "message": msg, "detail": detail})
        except Exception as e:
            results.append({"service": service_name, "success": False, "message": str(e),
                            "detail": {"steps": [f"ERROR: {str(e)}"]}})

    success_count = sum(1 for r in results if r['success'])
    add_operation_log('BATCH_DEPLOY', None, 'SUCCESS' if success_count == len(service_names) else 'FAILED',
                      f"批量部署: 成功 {success_count}/{len(service_names)}",
                      {'services': service_names, 'results': results}, operator, ip_address, user_agent)
    return results


# ========================== 同步脚本 ==========================

def sync_start_sh_to_all_servers():
    """同步 start.sh 到所有服务器"""
    servers = get_all_servers()
    results = []

    for server in servers:
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                server['host'],
                username=server['username'],
                password=server['password'],
                timeout=10
            )

            remote_base = server.get('remote_base', '/home/question')
            services = get_services_for_server(server['id'])

            for svc in services:
                service_name = svc.get('service_name')
                remote_path = svc.get('remote_path', service_name)
                if service_name:
                    check_and_upload_start_sh(ssh, remote_path, remote_base)

            ssh.close()
            results.append({
                'server': server['server_name'],
                'success': True,
                'message': '同步成功'
            })
        except Exception as e:
            results.append({
                'server': server['server_name'],
                'success': False,
                'message': str(e)
            })

    return results


# ========================== 初始化 ==========================

def init():
    """初始化：从数据库加载所有配置"""
    global SERVER_LIST, CURRENT_SERVER, REMOTE_BASE, CURRENT_SYSTEM, LOCAL_BASE

    if not os.path.exists(DB_PATH):
        init_db()

    # 获取默认系统
    CURRENT_SYSTEM = get_default_system()

    # 获取默认服务器
    default_server = get_default_server(CURRENT_SYSTEM)

    if default_server:
        set_current_server(default_server['id'])
    else:
        servers = get_servers(CURRENT_SYSTEM)
        if servers:
            set_current_server(servers[0]['id'])
        else:
            logger.warning("没有找到服务器配置，请先添加服务器")

    logger.info(
        f"✅ 初始化完成: {len(SERVICES)} 个服务, 系统: {CURRENT_SYSTEM}, 服务器: {CURRENT_SERVER['server_name'] if CURRENT_SERVER else 'None'}")