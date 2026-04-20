#!/usr/bin/env python3
"""
server.py — 墨水屏看板 Web 管理界面
Flask 服务器，端口 8080
"""
import os, sys
from pathlib import Path

# 安装 flask（如果没有）
try:
    from flask import Flask, send_file, jsonify, request, render_template_string
except ImportError:
    import subprocess
    print("[Server] 安装 flask...")
    subprocess.run([sys.executable, "-m", "pip", "install", "flask", "-q"])
    from flask import Flask, send_file, jsonify, request, render_template_string

PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

from api import (
    get_modes, get_mode_preview_png, push_mode,
    get_history, get_config, update_config
)

app = Flask(__name__)

HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>墨水屏看板</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, sans-serif; background: #f5f5f5; color: #333; min-height: 100vh; display: flex; flex-direction: column; }
  header { background: #1a1a2e; color: #fff; padding: 16px 24px; display: flex; align-items: center; justify-content: space-between; }
  header h1 { font-size: 18px; font-weight: 600; }
  .badge { background: #4CAF50; color: #fff; padding: 2px 8px; border-radius: 4px; font-size: 12px; }

  .main { display: flex; flex: 1; overflow: hidden; height: calc(100vh - 60px); }

  /* 左侧：模式列表 */
  .sidebar { width: 220px; background: #fff; border-right: 1px solid #e0e0e0; overflow-y: auto; padding: 16px; }
  .sidebar h3 { font-size: 13px; color: #888; text-transform: uppercase; margin-bottom: 12px; }
  .mode-btn { display: block; width: 100%; padding: 8px 12px; margin-bottom: 6px; background: #f8f8f8; border: 1px solid #e0e0e0; border-radius: 6px; text-align: left; cursor: pointer; font-size: 13px; transition: all 0.15s; }
  .mode-btn:hover { background: #e8f0fe; border-color: #4CAF50; }
  .mode-btn.active { background: #e8f0fe; border-color: #4CAF50; color: #1a73e8; font-weight: 500; }
  .mode-btn .name { display: block; }
  .mode-btn .id { color: #888; font-size: 11px; }

  /* 中间：预览区 */
  .preview-area { flex: 1; display: flex; flex-direction: column; background: #fff; padding: 24px; overflow: auto; }
  .preview-area h2 { font-size: 16px; margin-bottom: 16px; color: #444; }
  .preview-img-wrap { flex: 1; display: flex; align-items: center; justify-content: center; background: #e0e0e0; border-radius: 8px; min-height: 300px; position: relative; }
  .preview-img { max-width: 100%; max-height: 340px; border-radius: 4px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
  .preview-actions { display: flex; gap: 10px; margin-top: 16px; justify-content: center; }
  .btn { padding: 10px 20px; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: 500; transition: opacity 0.15s; }
  .btn:hover { opacity: 0.85; }
  .btn-primary { background: #1a73e8; color: #fff; }
  .btn-success { background: #4CAF50; color: #fff; }
  .btn-secondary { background: #f1f3f4; color: #333; border: 1px solid #dadce0; }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }

  /* 右侧：配置+历史 */
  .right-panel { width: 280px; background: #fff; border-left: 1px solid #e0e0e0; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 20px; }
  .panel-section h4 { font-size: 13px; color: #888; text-transform: uppercase; margin-bottom: 10px; }
  .config-item { display: flex; justify-content: space-between; align-items: center; padding: 6px 0; border-bottom: 1px solid #f0f0f0; font-size: 13px; }
  .config-item label { color: #555; }
  .config-item span { font-weight: 500; color: #333; }

  /* 历史记录 */
  .history-list { font-size: 12px; max-height: 300px; overflow-y: auto; }
  .history-item { padding: 6px 0; border-bottom: 1px solid #f5f5f5; display: flex; justify-content: space-between; }
  .history-item .time { color: #888; font-size: 11px; }
  .history-item .mode { font-weight: 500; }
  .history-item .ok { color: #4CAF50; }
  .history-item .fail { color: #f44336; }

  /* 模式切换 tabs */
  .tabs { display: flex; gap: 4px; margin-bottom: 12px; }
  .tab { padding: 6px 14px; border: 1px solid #e0e0e0; border-radius: 6px; cursor: pointer; font-size: 13px; background: #f8f8f8; }
  .tab.active { background: #1a73e8; color: #fff; border-color: #1a73e8; }

  /* Toast */
  #toast { position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%); background: #333; color: #fff; padding: 12px 24px; border-radius: 8px; font-size: 14px; display: none; z-index: 1000; transition: opacity 0.3s; }
  #toast.show { display: block; opacity: 1; }
  #toast.ok { background: #4CAF50; }
  #toast.err { background: #f44336; }
</style>
</head>
<body>
<header>
  <h1>🖥 墨水屏看板管理</h1>
  <span class="badge">Phase 2</span>
</header>

<div class="main">
  <!-- 左侧：模式列表 -->
  <div class="sidebar">
    <h3>📋 Page 3 模式</h3>
    <div id="modeList"></div>
    <h3 style="margin-top:20px">📋 Page 4</h3>
    <div>
      <button class="mode-btn" onclick="selectMode('weather', 4)" id="btn-weather">
        <span class="id">weather</span>
        <span class="name">天气看板</span>
      </button>
    </div>
  </div>

  <!-- 中间：预览 -->
  <div class="preview-area">
    <h2 id="previewTitle">选择模式预览</h2>
    <div class="preview-img-wrap">
      <img id="previewImg" src="" alt="预览" style="display:none">
      <div id="previewPlaceholder" style="color:#888;font-size:14px">点击左侧模式查看预览</div>
    </div>
    <div class="preview-actions">
      <button class="btn btn-primary" id="btnPushP3" onclick="pushPage(3)" disabled>▶ 推送 Page 3</button>
      <button class="btn btn-success" id="btnPushP4" onclick="pushPage(4)" disabled>▶ 推送 Page 4</button>
      <button class="btn btn-secondary" onclick="refreshPreview()">🔄 刷新预览</button>
    </div>
  </div>

  <!-- 右侧：配置+历史 -->
  <div class="right-panel">
    <div class="panel-section">
      <h4>⚙️ 当前配置</h4>
      <div id="configList"></div>
    </div>

    <div class="panel-section">
      <h4>📜 推送历史</h4>
      <div class="history-list" id="historyList"></div>
    </div>
  </div>
</div>

<div id="toast"></div>

<script>
let currentMode = null;
let currentPage = 3;

function $(id) { return document.getElementById(id); }

function toast(msg, type='ok') {
  const t = $('toast');
  t.textContent = msg;
  t.className = 'show ' + type;
  setTimeout(() => t.className = '', 2500);
}

async function api(url, opts={}) {
  try {
    const r = await fetch(url, opts);
    return await r.json();
  } catch(e) {
    return { error: String(e) };
  }
}

async function loadModes() {
  const data = await api('/api/modes');
  const list = $('modeList');
  list.innerHTML = '';
  data.modes.forEach(([id, name]) => {
    const btn = document.createElement('button');
    btn.className = 'mode-btn' + (currentMode === id ? ' active' : '');
    btn.innerHTML = `<span class="id">${id}</span><span class="name">${name}</span>`;
    btn.onclick = () => selectMode(id, 3);
    list.appendChild(btn);
  });
}

async function loadConfig() {
  const data = await api('/api/config');
  const list = $('configList');
  list.innerHTML = '';
  Object.entries(data).forEach(([k, v]) => {
    if (k === 'page3_modes') return;
    const div = document.createElement('div');
    div.className = 'config-item';
    div.innerHTML = `<label>${k}</label><span>${JSON.stringify(v)}</span>`;
    list.appendChild(div);
  });
  // 模式数量
  const cnt = data.page3_modes ? data.page3_modes.length : 0;
  const div = document.createElement('div');
  div.className = 'config-item';
  div.innerHTML = `<label>page3_modes</label><span>${cnt} 个</span>`;
  list.appendChild(div);
}

async function loadHistory() {
  const data = await api('/api/history');
  const list = $('historyList');
  if (!data.length) { list.innerHTML = '<div style="color:#888;font-size:12px">暂无记录</div>'; return; }
  list.innerHTML = '';
  data.slice(-20).reverse().forEach(e => {
    const div = document.createElement('div');
    div.className = 'history-item';
    const ts = e.timestamp ? e.timestamp.substring(5, 16) : '';
    div.innerHTML = `<span class="time">${ts}</span><span class="mode ${e.pushed?'ok':'fail'}">${e.mode || '-'}</span><span class="${e.pushed?'ok':'fail'}">${e.pushed?'✅':'❌'}</span>`;
    list.appendChild(div);
  });
}

async function selectMode(id, page) {
  currentMode = id;
  currentPage = page;
  $('previewTitle').textContent = `预览: ${id}`;
  $('previewImg').style.display = 'none';
  $('previewPlaceholder').style.display = 'block';
  $('btnPushP3').disabled = false;
  $('btnPushP4').disabled = false;

  // 高亮按钮
  document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
  const btns = document.querySelectorAll('.mode-btn');
  btns.forEach(b => { if (b.id === 'btn-'+id || b.textContent.includes(id)) b.classList.add('active'); });
  if (id === 'weather') $('btn-weather').classList.add('active');

  await refreshPreview();
}

async function refreshPreview() {
  if (!currentMode) return;
  const img = $('previewImg');
  img.src = '/api/preview?mode=' + encodeURIComponent(currentMode) + '&page=' + currentPage + '&t=' + Date.now();
  img.style.display = 'block';
  $('previewPlaceholder').style.display = 'none';
}

async function pushPage(page) {
  if (!currentMode) return;
  const targetMode = (page === 4) ? 'weather' : currentMode;
  const btn = page === 3 ? $('btnPushP3') : $('btnPushP4');
  btn.disabled = true;
  btn.textContent = '⏳ 推送中...';
  const r = await api(`/api/push?mode=${encodeURIComponent(targetMode)}&page=${page}`);
  btn.disabled = false;
  btn.textContent = '▶ 推送 Page ' + page;
  if (r.ok) {
    toast('Page ' + page + ' 推送成功！', 'ok');
    loadHistory();
  } else {
    toast('推送失败: ' + (r.error || r.message || '未知错误'), 'err');
  }
}

// 初始化
loadModes();
loadConfig();
loadHistory();
</script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/modes')
def api_modes():
    modes = get_modes()
    return jsonify({"modes": modes, "count": len(modes)})

@app.route('/api/preview')
def api_preview():
    mode = request.args.get('mode', 'jokes')
    page = int(request.args.get('page', 3))
    try:
        png_bytes = get_mode_preview_png(mode, page)
        from io import BytesIO
        buf = BytesIO(png_bytes)
        buf.seek(0)
        from flask import make_response
        resp = make_response(buf.getvalue())
        resp.headers['Content-Type'] = 'image/png'
        resp.headers['Cache-Control'] = 'no-cache'
        return resp
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/push')
def api_push():
    mode = request.args.get('mode', 'jokes')
    page = int(request.args.get('page', 3))
    result = push_mode(mode, page)
    if result.get("ok"):
        return jsonify(result)
    else:
        return jsonify(result), 400

@app.route('/api/history')
def api_history():
    entries = get_history()
    return jsonify(entries)

@app.route('/api/config')
def api_config():
    return jsonify(get_config())

@app.route('/api/config', methods=['POST'])
def api_config_update():
    data = request.get_json() or {}
    result = update_config(data)
    return jsonify(result)

if __name__ == "__main__":
    port = 8080
    print(f"[Server] 墨水屏看板管理界面启动: http://localhost:{port}")
    print(f"[Server] 访问: http://<本机IP>:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
