#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask, render_template, request, jsonify
import deploy_core
from deploy_core import (
    deploy_service,
    get_all_services_status, manual_start_service, manual_stop_service,
    LOCAL_BASE, REMOTE_BASE, get_ssh_connection,
    batch_start_services, batch_stop_services, batch_deploy_services,
    init,
    get_operation_logs, get_log_count, clear_operation_logs, get_log_statistics,
    add_operation_log, load_services_from_db,
    get_servers, get_all_servers, get_server, save_server, delete_server,
    set_current_server, get_default_server,
    CURRENT_SERVER, CURRENT_SYSTEM, init_db, init_db_with_config,
    upload_service_config, check_and_upload_start_sh, sync_start_sh_to_all_servers,
    get_system_config, get_all_system_configs, save_system_config,
    save_system_config_local_base, get_default_system,
    get_services, get_service, save_service, delete_service, get_service_by_name,
    get_services_for_server
)
import os
import sys
import logging
import json
import socket

# 配置日志
if getattr(sys, 'frozen', False):
    if sys.platform == 'darwin':
        LOG_DIR = os.path.join(os.path.expanduser('~'), 'Library', 'Logs', 'JarDeploySystem')
    elif sys.platform == 'win32':
        LOG_DIR = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'JarDeploySystem', 'logs')
    else:
        LOG_DIR = os.path.join(os.path.expanduser('~'), '.local', 'share', 'JarDeploySystem', 'logs')
else:
    LOG_DIR = os.path.join(os.path.dirname(__file__), 'logs')

os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, 'web.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ==================== 启动时加载配置 ====================
init()


# ==================== 获取客户端信息 ====================

def get_client_info():
    """获取客户端IP和User-Agent"""
    ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
    if ip_address and ',' in ip_address:
        ip_address = ip_address.split(',')[0].strip()
    user_agent = request.headers.get('User-Agent', 'Unknown')
    return ip_address, user_agent


# ==================== 页面路由 ====================

@app.route('/')
def index():
    """主页"""
    services = get_services()
    service_names = [s['service_name'] for s in services]
    return render_template('index.html',
                           services=service_names,
                           local_base=LOCAL_BASE,
                           current_system=CURRENT_SYSTEM)


# ==================== 系统配置管理 API ====================

@app.route('/api/system/configs', methods=['GET'])
def api_get_system_configs():
    """获取所有系统配置"""
    try:
        configs = get_all_system_configs()
        return jsonify({
            'success': True,
            'data': {
                'configs': configs,
                'current': CURRENT_SYSTEM,
                'default': get_default_system()
            }
        })
    except Exception as e:
        logger.error(f"获取系统配置失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/system/config', methods=['GET'])
def api_get_system_config():
    """获取当前系统配置"""
    try:
        config = get_system_config(CURRENT_SYSTEM)
        if config:
            return jsonify({
                'success': True,
                'data': {
                    **config,
                    'remote_base': REMOTE_BASE,
                    'current_server': CURRENT_SERVER['id'] if CURRENT_SERVER else None
                }
            })
        else:
            return jsonify({
                'success': True,
                'data': {
                    'config_name': CURRENT_SYSTEM,
                    'local_base': LOCAL_BASE or '',
                    'remote_base': REMOTE_BASE or '/home/question',
                    'current_server': CURRENT_SERVER['id'] if CURRENT_SERVER else None
                }
            })
    except Exception as e:
        logger.error(f"获取系统配置失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/system/config', methods=['POST'])
def api_save_system_config():
    """保存系统配置"""
    try:
        data = request.get_json()
        config_name = data.get('config_name', '').strip()
        local_base = data.get('local_base', '').strip()
        is_default = data.get('is_default', 0)

        if not config_name:
            return jsonify({'success': False, 'error': '配置名称不能为空'}), 400
        if not local_base:
            return jsonify({'success': False, 'error': '本地目录不能为空'}), 400

        ip_address, user_agent = get_client_info()
        success, message = save_system_config(config_name, local_base, is_default)

        if success:
            add_operation_log('SYSTEM_CONFIG_SAVE', config_name, 'SUCCESS',
                              f"保存系统配置: {config_name} -> {local_base}",
                              {'config_name': config_name, 'local_base': local_base, 'is_default': is_default},
                              'web', ip_address, user_agent)

        return jsonify({'success': success, 'message': message})
    except Exception as e:
        logger.error(f"保存系统配置失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/system/switch', methods=['POST'])
def api_switch_system():
    """切换系统"""
    try:
        data = request.get_json()
        system_name = data.get('system_name', '').strip()

        if not system_name:
            return jsonify({'success': False, 'error': '系统名称不能为空'}), 400

        ip_address, user_agent = get_client_info()

        # 获取系统配置
        system_config = get_system_config(system_name)
        if not system_config:
            return jsonify({'success': False, 'error': f'系统配置 {system_name} 不存在'}), 400

        # 查找对应的服务器
        servers = get_servers(system_name)
        if not servers:
            return jsonify({'success': False, 'error': f'系统 {system_name} 没有配置服务器'}), 400

        # 选择默认服务器或第一个
        server = next((s for s in servers if s.get('is_default') == 1), servers[0])

        # 切换服务器
        success, message = set_current_server(server['id'])

        if success:
            add_operation_log('SYSTEM_SWITCH', None, 'SUCCESS',
                              f"切换到系统: {system_name}",
                              {'system_name': system_name, 'server_name': server['server_name']},
                              'web', ip_address, user_agent)

            # 获取当前系统配置
            current_config = get_system_config(system_name)

            return jsonify({
                'success': True,
                'message': f"已切换到系统: {system_name}",
                'data': {
                    'system_name': system_name,
                    'local_base': current_config['local_base'] if current_config else '',
                    'remote_base': REMOTE_BASE,
                    'server_id': server['id'],
                    'server_name': server['server_name']
                }
            })
        else:
            return jsonify({'success': False, 'error': message}), 500

    except Exception as e:
        logger.error(f"切换系统失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== 服务器管理 API ====================

@app.route('/api/servers', methods=['GET'])
def api_get_servers():
    """获取当前系统的服务器列表"""
    try:
        servers = get_servers()
        return jsonify({
            'success': True,
            'data': servers,
            'current_server': CURRENT_SERVER['id'] if CURRENT_SERVER else None,
            'current_system': CURRENT_SYSTEM
        })
    except Exception as e:
        logger.error(f"获取服务器列表失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/servers/all', methods=['GET'])
def api_get_all_servers():
    """获取所有服务器列表"""
    try:
        servers = get_all_servers()
        return jsonify({
            'success': True,
            'data': servers
        })
    except Exception as e:
        logger.error(f"获取所有服务器列表失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/servers/<int:server_id>', methods=['GET'])
def api_get_server(server_id):
    """获取单个服务器信息"""
    try:
        server = get_server(server_id)
        if server:
            return jsonify({'success': True, 'data': server})
        else:
            return jsonify({'success': False, 'error': '服务器不存在'}), 404
    except Exception as e:
        logger.error(f"获取服务器信息失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/servers', methods=['POST'])
def api_save_server():
    """保存服务器"""
    try:
        data = request.get_json()
        server_id = data.get('id', '').strip() or None
        config_name = data.get('config_name', '').strip() or CURRENT_SYSTEM
        server_name = data.get('server_name', '').strip()
        host = data.get('host', '').strip()
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        port = data.get('port', 22)
        remote_base = data.get('remote_base', '').strip() or '/home/question'
        sort_order = data.get('sort_order', 0)
        is_default = data.get('is_default', 0)

        if not server_name:
            return jsonify({'success': False, 'error': '服务器名称不能为空'}), 400
        if not host:
            return jsonify({'success': False, 'error': '主机地址不能为空'}), 400
        if not username:
            return jsonify({'success': False, 'error': '用户名不能为空'}), 400
        if not password:
            return jsonify({'success': False, 'error': '密码不能为空'}), 400

        ip_address, user_agent = get_client_info()
        success, message = save_server(
            server_id, config_name, server_name, host, username, password,
            port, remote_base, sort_order, is_default
        )

        if success:
            add_operation_log(
                'SERVER_EDIT' if server_id else 'SERVER_ADD',
                server_name, 'SUCCESS',
                f"{'编辑' if server_id else '添加'}服务器: {server_name} ({host})",
                {'server_name': server_name, 'host': host, 'config_name': config_name, 'remote_base': remote_base},
                'web', ip_address, user_agent
            )

        return jsonify({'success': success, 'message': message})
    except Exception as e:
        logger.error(f"保存服务器失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/servers/<int:server_id>', methods=['DELETE'])
def api_delete_server(server_id):
    """删除服务器"""
    try:
        ip_address, user_agent = get_client_info()
        server = get_server(server_id)
        server_name = server['server_name'] if server else '未知'

        success, message = delete_server(server_id)

        if success:
            add_operation_log(
                'SERVER_DELETE', server_name, 'SUCCESS',
                f"删除服务器: {server_name}",
                {'server_id': server_id},
                'web', ip_address, user_agent
            )

        return jsonify({'success': success, 'message': message})
    except Exception as e:
        logger.error(f"删除服务器失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/servers/switch', methods=['POST'])
def api_switch_server():
    """切换服务器"""
    try:
        data = request.get_json()
        server_id = data.get('server_id')

        if not server_id:
            return jsonify({'success': False, 'error': '服务器ID不能为空'}), 400

        ip_address, user_agent = get_client_info()
        server = get_server(server_id)
        server_name = server['server_name'] if server else '未知'

        success, message = set_current_server(server_id)

        if success:
            add_operation_log(
                'SERVER_SWITCH', server_name, 'SUCCESS',
                f"切换到服务器: {server_name}",
                {'server_id': server_id, 'server_name': server_name},
                'web', ip_address, user_agent
            )

            system_config = get_system_config(CURRENT_SYSTEM)

            return jsonify({
                'success': success,
                'message': message,
                'data': {
                    'server_id': server_id,
                    'server_name': server_name,
                    'remote_base': REMOTE_BASE,
                    'local_base': system_config['local_base'] if system_config else '',
                    'system_name': CURRENT_SYSTEM
                }
            })
        else:
            return jsonify({'success': False, 'error': message}), 500
    except Exception as e:
        logger.error(f"切换服务器失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/servers/current', methods=['GET'])
def api_get_current_server():
    """获取当前服务器"""
    try:
        if CURRENT_SERVER:
            system_config = get_system_config(CURRENT_SYSTEM)
            return jsonify({
                'success': True,
                'data': {
                    'id': CURRENT_SERVER['id'],
                    'server_name': CURRENT_SERVER['server_name'],
                    'host': CURRENT_SERVER['host'],
                    'remote_base': CURRENT_SERVER.get('remote_base', '/home/question'),
                    'config_name': CURRENT_SERVER.get('config_name'),
                    'system_name': CURRENT_SYSTEM,
                    'local_base': system_config['local_base'] if system_config else LOCAL_BASE
                }
            })
        else:
            return jsonify({'success': True, 'data': None})
    except Exception as e:
        logger.error(f"获取当前服务器失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== 服务管理 API ====================

@app.route('/api/services', methods=['GET'])
def api_get_services():
    """获取服务列表"""
    try:
        services = get_services()
        return jsonify({
            'success': True,
            'data': services,
            'local_base': LOCAL_BASE,
            'remote_base': REMOTE_BASE
        })
    except Exception as e:
        logger.error(f"获取服务列表失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/services/status', methods=['GET'])
def api_services_status():
    """获取所有服务状态"""
    try:
        ssh = None
        try:
            ssh = get_ssh_connection()
        except Exception as e:
            logger.warning(f"SSH 连接失败: {str(e)}")

        status = get_all_services_status(ssh)

        if ssh:
            ssh.close()

        return jsonify({'success': True, 'status': status})
    except Exception as e:
        logger.error(f"获取服务状态失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/service/<int:service_id>', methods=['GET'])
def api_get_service(service_id):
    """获取单个服务信息"""
    try:
        service = get_service(service_id)
        if service:
            return jsonify({'success': True, 'data': service})
        else:
            return jsonify({'success': False, 'error': '服务不存在'}), 404
    except Exception as e:
        logger.error(f"获取服务信息失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/service', methods=['POST'])
def api_save_service():
    """保存服务"""
    try:
        data = request.get_json()
        service_id = data.get('id', '').strip() or None
        config_name = data.get('config_name', '').strip() or CURRENT_SYSTEM
        server_id = data.get('server_id')
        service_name = data.get('service_name', '').strip()
        local_path = data.get('local_path', '').strip()
        remote_path = data.get('remote_path', '').strip() or service_name

        if not service_name:
            return jsonify({'success': False, 'error': '服务名称不能为空'}), 400
        if not server_id:
            return jsonify({'success': False, 'error': '请选择服务器'}), 400
        if not local_path:
            return jsonify({'success': False, 'error': '本地路径不能为空'}), 400

        # 检查服务是否已存在
        existing = get_service_by_name(service_name, config_name)
        if existing and existing['id'] != service_id:
            return jsonify({'success': False, 'error': f'服务 {service_name} 已存在'}), 400

        ip_address, user_agent = get_client_info()
        success, message = save_service(service_id, config_name, server_id, service_name, local_path, remote_path)

        if success:
            add_operation_log('SAVE_SERVICE', service_name, 'SUCCESS',
                              f"保存服务: {service_name} -> {local_path}",
                              {'service_name': service_name, 'local_path': local_path, 'server_id': server_id},
                              'web', ip_address, user_agent)

            # 同步 start.sh
            try:
                ssh = get_ssh_connection()
                if ssh:
                    check_and_upload_start_sh(ssh, remote_path or service_name, REMOTE_BASE)
                    ssh.close()
            except Exception as e:
                logger.warning(f"同步 start.sh 失败: {str(e)}")

        return jsonify({'success': success, 'message': message})
    except Exception as e:
        logger.error(f"保存服务失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/service/<int:service_id>', methods=['DELETE'])
def api_delete_service(service_id):
    """删除服务"""
    try:
        ip_address, user_agent = get_client_info()
        service = get_service(service_id)
        service_name = service['service_name'] if service else '未知'

        success, message = delete_service(service_id)

        if success:
            add_operation_log('DELETE_SERVICE', service_name, 'SUCCESS',
                              f"删除服务: {service_name}",
                              {'service_id': service_id},
                              'web', ip_address, user_agent)

        return jsonify({'success': success, 'message': message})
    except Exception as e:
        logger.error(f"删除服务失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== 单服务操作 API ====================

@app.route('/api/service/start', methods=['POST'])
def api_start_service():
    """启动服务"""
    try:
        data = request.get_json()
        service_name = data.get('service_name', '').strip()

        if not service_name:
            return jsonify({'success': False, 'error': '服务名称不能为空'}), 400

        ip_address, user_agent = get_client_info()
        logger.info(f"启动服务: {service_name}")
        success, message = manual_start_service(service_name, 'web', ip_address, user_agent)

        return jsonify({'success': success, 'message': message})
    except Exception as e:
        logger.error(f"启动服务失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/service/stop', methods=['POST'])
def api_stop_service():
    """停止服务"""
    try:
        data = request.get_json()
        service_name = data.get('service_name', '').strip()

        if not service_name:
            return jsonify({'success': False, 'error': '服务名称不能为空'}), 400

        ip_address, user_agent = get_client_info()
        logger.info(f"停止服务: {service_name}")
        success, message = manual_stop_service(service_name, 'web', ip_address, user_agent)

        return jsonify({'success': success, 'message': message})
    except Exception as e:
        logger.error(f"停止服务失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/deploy', methods=['POST'])
def api_deploy():
    """部署服务"""
    try:
        data = request.get_json()
        service_name = data.get('service_name', '').strip()
        yml_content = data.get('yml_content', '')

        if not service_name:
            return jsonify({'success': False, 'error': '服务名称不能为空'}), 400

        ip_address, user_agent = get_client_info()
        logger.info(f"部署服务: {service_name}")
        success, message, detail = deploy_service(
            service_name,
            operator='web',
            ip_address=ip_address,
            user_agent=user_agent,
            yml_content=yml_content if yml_content else None
        )

        return jsonify({'success': success, 'message': message, 'detail': detail})
    except Exception as e:
        logger.error(f"部署服务失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/service/config', methods=['POST'])
def api_upload_service_config():
    """上传服务配置文件"""
    try:
        data = request.get_json()
        service_name = data.get('service_name', '').strip()
        yml_content = data.get('yml_content', '')

        if not service_name:
            return jsonify({'success': False, 'error': '服务名称不能为空'}), 400
        if not yml_content:
            return jsonify({'success': False, 'error': '配置文件内容不能为空'}), 400

        ip_address, user_agent = get_client_info()
        success, message = upload_service_config(
            service_name, yml_content, 'web', ip_address, user_agent
        )

        return jsonify({'success': success, 'message': message})
    except Exception as e:
        logger.error(f"上传配置文件失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== 批量操作 API ====================

@app.route('/api/batch-start', methods=['POST'])
def api_batch_start():
    """批量启动服务"""
    try:
        data = request.get_json()
        services = data.get('services', [])

        if not services or not isinstance(services, list):
            return jsonify({'success': False, 'error': 'services 参数必须是非空数组'}), 400

        ip_address, user_agent = get_client_info()
        results = batch_start_services(services, 'web', ip_address, user_agent)
        success_count = sum(1 for r in results if r['success'])

        return jsonify({
            'success': True,
            'message': f'成功启动 {success_count}/{len(services)} 个服务',
            'results': results
        })
    except Exception as e:
        logger.error(f"批量启动服务失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/batch-stop', methods=['POST'])
def api_batch_stop():
    """批量停止服务"""
    try:
        data = request.get_json()
        services = data.get('services', [])

        if not services or not isinstance(services, list):
            return jsonify({'success': False, 'error': 'services 参数必须是非空数组'}), 400

        ip_address, user_agent = get_client_info()
        results = batch_stop_services(services, 'web', ip_address, user_agent)
        success_count = sum(1 for r in results if r['success'])

        return jsonify({
            'success': True,
            'message': f'成功停止 {success_count}/{len(services)} 个服务',
            'results': results
        })
    except Exception as e:
        logger.error(f"批量停止服务失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/batch-deploy', methods=['POST'])
def api_batch_deploy():
    """批量部署服务"""
    try:
        data = request.get_json()
        services = data.get('services', [])

        if not services or not isinstance(services, list):
            return jsonify({'success': False, 'error': 'services 参数必须是非空数组'}), 400

        ip_address, user_agent = get_client_info()
        results = batch_deploy_services(services, 'web', ip_address, user_agent)
        success_count = sum(1 for r in results if r['success'])

        return jsonify({
            'success': True,
            'message': f'成功部署 {success_count}/{len(services)} 个服务',
            'results': results
        })
    except Exception as e:
        logger.error(f"批量部署服务失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== 日志管理 API ====================

@app.route('/api/logs', methods=['GET'])
def api_get_logs():
    """获取操作日志"""
    try:
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)
        operation_type = request.args.get('operation_type', None)
        service_name = request.args.get('service_name', None)
        status = request.args.get('status', None)
        start_time = request.args.get('start_time', None)
        end_time = request.args.get('end_time', None)

        logs = get_operation_logs(limit, offset, operation_type, service_name, status, start_time, end_time)
        total = get_log_count(operation_type, service_name, status)

        return jsonify({
            'success': True,
            'data': {
                'logs': logs,
                'total': total,
                'limit': limit,
                'offset': offset
            }
        })
    except Exception as e:
        logger.error(f"获取日志失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/logs/statistics', methods=['GET'])
def api_get_log_statistics():
    """获取日志统计信息"""
    try:
        stats = get_log_statistics()
        return jsonify({'success': True, 'data': stats})
    except Exception as e:
        logger.error(f"获取日志统计失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/logs/clear', methods=['POST'])
def api_clear_logs():
    """清空日志"""
    try:
        data = request.get_json() or {}
        days = data.get('days', None)

        if days is not None:
            try:
                days = int(days)
            except ValueError:
                return jsonify({'success': False, 'error': 'days 参数必须是整数'}), 400

        success, message = clear_operation_logs(days)

        if success:
            ip_address, user_agent = get_client_info()
            add_operation_log('LOG_CLEAR', None, 'SUCCESS', message,
                              {'days': days}, 'web', ip_address, user_agent)
            return jsonify({'success': True, 'message': message})
        else:
            return jsonify({'success': False, 'error': message}), 500
    except Exception as e:
        logger.error(f"清空日志失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== 数据库初始化 API ====================

@app.route('/api/db/init', methods=['POST'])
def api_init_database():
    """初始化数据库"""
    try:
        ip_address, user_agent = get_client_info()

        if 'file' not in request.files or request.files['file'].filename == '':
            logger.info("使用默认配置初始化数据库")
            init_db()
            filename = 'default (static/deploy.json)'
        else:
            file = request.files['file']
            if not file.filename.endswith('.json'):
                return jsonify({'success': False, 'error': '请上传 JSON 格式的文件'}), 400

            try:
                json_content = file.read().decode('utf-8')
                config = json.loads(json_content)
            except json.JSONDecodeError as e:
                return jsonify({'success': False, 'error': f'JSON 格式错误: {str(e)}'}), 400

            if 'tables' not in config:
                return jsonify({'success': False, 'error': 'JSON 文件缺少 tables 字段'}), 400

            init_db_with_config(config)
            filename = file.filename

        # 重新初始化
        init()

        add_operation_log(
            'DB_INIT', None, 'SUCCESS',
            f"数据库初始化成功，使用配置文件: {filename}",
            {'filename': filename}, 'web', ip_address, user_agent
        )

        return jsonify({'success': True, 'message': f'数据库初始化成功，使用配置文件: {filename}'})
    except Exception as e:
        logger.error(f"初始化数据库失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== 脚本同步 API ====================

@app.route('/api/service/scripts/sync', methods=['POST'])
def api_sync_scripts():
    """同步 start.sh 脚本到服务器"""
    try:
        data = request.get_json() or {}
        service_name = data.get('service_name', '').strip()

        if service_name:
            service = get_service_by_name(service_name)
            if not service:
                return jsonify({'success': False, 'error': f'服务 {service_name} 不存在'}), 404

            ssh = get_ssh_connection()
            if not ssh:
                return jsonify({'success': False, 'error': 'SSH 连接失败'}), 500

            remote_path = service.get('remote_path', service_name)
            success, msg = check_and_upload_start_sh(ssh, remote_path, REMOTE_BASE)
            ssh.close()

            if success:
                return jsonify({'success': True, 'message': f"start.sh 同步成功: {service_name}"})
            else:
                return jsonify({'success': False, 'error': msg}), 500
        else:
            results = sync_start_sh_to_all_servers()
            success_count = sum(1 for r in results if r['success'])

            return jsonify({
                'success': True,
                'message': f"start.sh 同步完成: {success_count}/{len(results)} 个服务器成功",
                'results': results
            })
    except Exception as e:
        logger.error(f"同步 start.sh 失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== 刷新 API ====================

@app.route('/api/refresh-services', methods=['POST'])
def api_refresh_services():
    """刷新服务列表"""
    try:
        load_services_from_db()
        services = get_services()
        return jsonify({
            'success': True,
            'message': f'服务列表已刷新，共 {len(services)} 个服务',
            'services': [s['service_name'] for s in services]
        })
    except Exception as e:
        logger.error(f"刷新服务列表失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== 错误处理 ====================

@app.errorhandler(404)
def not_found(error):
    return jsonify({'success': False, 'error': '接口不存在'}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({'success': False, 'error': '服务器内部错误'}), 500


# ==================== 启动服务 ====================

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


if __name__ == '__main__':
    local_ip = get_local_ip()

    print("=" * 60)
    print("🚀 JAR 包自动部署系统 Web 服务")
    print("=" * 60)
    print(f"📦 服务数量: {len(get_services())}")
    print(f"📁 本地基础目录: {LOCAL_BASE}")
    print(f"📁 远端基础目录: {REMOTE_BASE}")
    print(f"💻 当前系统: {CURRENT_SYSTEM}")
    print(f"🖥️ 当前服务器: {CURRENT_SERVER['server_name'] if CURRENT_SERVER else 'None'}")
    if CURRENT_SERVER:
        print(f"📋 服务器配置名称: {CURRENT_SERVER.get('config_name', 'N/A')}")
    print(f"📁 日志目录: {LOG_DIR}")
    print(f"🌐 本机访问: http://localhost:5001")
    print(f"🌐 局域网访问: http://{local_ip}:5001")
    print("=" * 60)
    print("按 Ctrl+C 停止服务")
    print("=" * 60)

    app.run(host='0.0.0.0', port=5001, debug=False)