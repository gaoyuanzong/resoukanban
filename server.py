#!/usr/bin/env python3
"""
server.py — 墨水屏看板 Web 管理界面 (InkSight 风格)
Flask 服务器，端口 8080
"""
import os, sys
from pathlib import Path

# 安装依赖
try:
    from flask import Flask, send_file, jsonify, request, render_template
except ImportError:
    import subprocess
    print("[Server] 安装 flask...")
    subprocess.run([sys.executable, "-m", "pip", "install", "flask", "-q"])
    from flask import Flask, send_file, jsonify, request, render_template

PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

from api import (
    get_modes, get_mode_preview_png, push_mode,
    get_history, get_config, update_config,
    get_stats, get_mode_catalog, trigger_refresh
)

app = Flask(__name__, template_folder='templates')

# ── 页面路由 ─────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('config.html', page='config')

@app.route('/config')
def config_page():
    return render_template('config.html', page='config')

@app.route('/preview')
def preview_page():
    return render_template('preview.html', page='preview')

@app.route('/dashboard')
def dashboard_page():
    return render_template('dashboard.html', page='dashboard')

# ── API 端点（保留全部现有接口）──────────────────────────────

@app.route('/api/modes', methods=['GET'])
def api_modes():
    """返回所有模式列表"""
    modes = get_modes()
    return jsonify({"ok": True, "modes": modes, "count": len(modes)})

@app.route('/api/preview', methods=['GET'])
def api_preview():
    """生成预览 PNG"""
    mode = request.args.get('mode', 'jokes')
    page = int(request.args.get('page', 3))
    layout = request.args.get('layout', 'standard')
    try:
        png_bytes = get_mode_preview_png(mode, page, layout)
        from io import BytesIO
        buf = BytesIO(png_bytes)
        buf.seek(0)
        from flask import make_response
        resp = make_response(buf.getvalue())
        resp.headers['Content-Type'] = 'image/png'
        resp.headers['Cache-Control'] = 'no-cache'
        return resp
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route('/api/push', methods=['GET', 'POST'])
def api_push():
    """推送到墨水屏"""
    mode = request.args.get('mode', 'jokes')
    page = int(request.args.get('page', 3))
    layout = request.args.get('layout', 'standard')
    result = push_mode(mode, page, layout=layout)
    if result.get("ok"):
        return jsonify({"ok": True, "data": result})
    else:
        return jsonify({"ok": False, "error": result.get("error", "推送失败")}), 400

@app.route('/api/history', methods=['GET'])
def api_history():
    """返回推送历史"""
    entries = get_history()
    return jsonify(entries)

@app.route('/api/config', methods=['GET'])
def api_config_get():
    """读取当前配置"""
    return jsonify(get_config())

@app.route('/api/config', methods=['POST'])
def api_config_post():
    """更新配置"""
    data = request.get_json() or {}
    result = update_config(data)
    return jsonify({"ok": True, "data": result})

# ── 新增 API 端点 ────────────────────────────────────────────

@app.route('/api/refresh', methods=['POST'])
def api_refresh():
    """触发立即刷新"""
    result = trigger_refresh()
    return jsonify(result)

@app.route('/api/stats', methods=['GET'])
def api_stats():
    """返回全局统计"""
    stats = get_stats()
    return jsonify({"ok": True, "data": stats})

@app.route('/api/mode_catalog', methods=['GET'])
def api_mode_catalog():
    """返回模式目录（22 个模式的元数据）"""
    catalog = get_mode_catalog()
    return jsonify({"ok": True, "data": catalog})

# ── 静态文件（可选） ─────────────────────────────────────────

@app.route('/favicon.ico')
def favicon():
    from flask import send_from_directory
    return send_from_directory(PROJECT_DIR, 'favicon.ico', mimetype='image/x-icon')

# ── 启动 ─────────────────────────────────────────────────────

if __name__ == "__main__":
    port = 8080
    print(f"[Server] 墨水屏看板管理界面启动")
    print(f"[Server] 配置页: http://localhost:{port}/config")
    print(f"[Server] 预览页: http://localhost:{port}/preview")
    print(f"[Server] 数据看板: http://localhost:{port}/dashboard")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True, use_reloader=False)