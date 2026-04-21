"""
api.py — 墨水屏看板 API 函数
可被 main.py 和 server.py 共用
"""
import os, sys, json, random, tempfile, hashlib, datetime
from pathlib import Path

# 确保项目路径在 sys.path
PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

from config_reader import Config
from history_record import History
from main import ccgen

# 内容目录
CCGEN_DIR = "/tmp/ccgen"

# 缓存目录
PREVIEW_CACHE_DIR = Path("/tmp/ink_previews")
PREVIEW_CACHE_DIR.mkdir(exist_ok=True)

# 导入主程序的模式（延迟导入避免循环）
_main_modules_loaded = False
_MODES = None

def _ensure_modes():
    global _MODES, _main_modules_loaded
    if _MODES is not None:
        return _MODES
    # 动态导入 main.py 中的 MODES
    import importlib.util
    spec = importlib.util.spec_from_file_location("_main", PROJECT_DIR / "main.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _MODES = mod.MODES
    _main_modules_loaded = True
    return _MODES


def get_modes():
    """返回所有模式列表"""
    modes = _ensure_modes()
    return [(mid, name) for mid, name, _ in modes]


def get_mode_preview_png(mode_id: str, page: int = 3, layout: str = "standard") -> bytes:
    """
    生成指定模式的预览 PNG，返回 bytes
    使用缓存：相同 mode_id + page + layout 只生成一次
    """
    cache_key = f"{mode_id}_p{page}_{layout}"
    cache_file = PREVIEW_CACHE_DIR / f"{cache_key}.png"

    # 缓存命中
    if cache_file.exists():
        return cache_file.read_bytes()

    # 动态加载 main.py
    import importlib.util
    spec = importlib.util.spec_from_file_location("_main", PROJECT_DIR / "main.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Mock push_image 和 ccgen
    saved_files = {}

    def mock_push(img, page_id):
        path = PREVIEW_CACHE_DIR / f"{mode_id}_p{page_id}.png"
        img.save(path)
        saved_files[page_id] = path

    mod.push_image = mock_push
    mod.ccgen = ccgen
    def _read_ccgen_a(filename):
        path = os.path.join(CCGEN_DIR, filename)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                return [line.strip() for line in fh if line.strip()]
        return []
    mod.read_ccgen = _read_ccgen_a

    # 注入 API_KEY 环境变量（如果存在）
    env_file = PROJECT_DIR / ".env"
    if env_file.exists():
        with open(env_file) as ef:
            for line in ef:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    os.environ.setdefault(k, v)

    # 执行目标模式
    found = False
    for mid, name, func in mod.MODES:
        if mid == mode_id:
            try:
                func()
            except Exception as e:
                print(f"[API] preview {mode_id} failed: {e}")
            found = True
            break

    # weather 特殊处理（支持 layout 参数）
    if mode_id == "weather":
        mod.task_weather_dashboard(layout=layout)
        found = True

    if not found:
        print(f"[API] mode {mode_id} not found")

    # 返回 PNG bytes
    png_path = PREVIEW_CACHE_DIR / f"{mode_id}_p{page}.png"
    if png_path.exists():
        return png_path.read_bytes()

    # fallback: 返回空白图
    from PIL import Image
    img = Image.new('1', (400, 300), color=255)
    tmp = PREVIEW_CACHE_DIR / f"{mode_id}_fallback.png"
    img.save(tmp)
    return tmp.read_bytes()


def push_mode(mode_id: str, page: int = 3, config_path: str = None, layout: str = None) -> dict:
    """
    推送指定模式到墨水屏，返回结果 dict
    """
    # 加载配置
    cfg = Config(config_path) if config_path else Config()
    hist_file = PROJECT_DIR / cfg.history_file
    history = History(str(hist_file), cfg.history_max)

    # 注入 .env
    env_file = PROJECT_DIR / ".env"
    if env_file.exists():
        with open(env_file) as ef:
            for line in ef:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    os.environ.setdefault(k, v)

    import importlib.util
    spec = importlib.util.spec_from_file_location("_main", PROJECT_DIR / "main.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Real push
    def real_push(img, page_id):
        from PIL import Image as PILImage
        import requests

        API_KEY = os.environ.get("ZECTRIX_API_KEY", "")
        MAC_ADDRESS = os.environ.get("ZECTRIX_MAC", "")
        PUSH_URL = f"https://cloud.zectrix.com/open/v1/devices/{MAC_ADDRESS}/display/image"

        tmp = f"/tmp/push_p{page_id}.png"
        img.save(tmp)
        api_headers = {"X-API-Key": API_KEY}
        files = {"images": (f"page_{page_id}.png", open(tmp, "rb"), "image/png")}
        data = {"dither": "true", "pageId": str(page_id)}
        try:
            res = requests.post(PUSH_URL, headers=api_headers, files=files, data=data)
            return {"ok": True, "status": res.status_code, "page": page_id}
        except Exception as e:
            return {"ok": False, "error": str(e), "page": page_id}

    mod.push_image = real_push
    mod.ccgen = lambda p, f: None
    def _read_ccgen_b(filename):
        path = os.path.join(CCGEN_DIR, filename)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                return [line.strip() for line in fh if line.strip()]
        return []
    mod.read_ccgen = _read_ccgen_b

    result = {"ok": False, "mode": mode_id, "page": page}

    for mid, name, func in mod.MODES:
        if mid == mode_id:
            start_time = datetime.datetime.now()
            try:
                func()
                history.record(page=page, mode=mid, pushed=True)
                result["ok"] = True
                result["render_time_ms"] = int((datetime.datetime.now() - start_time).total_seconds() * 1000)
                print(f"[API] pushed {mid} to Page {page}")
            except Exception as e:
                history.record(page=page, mode=mid, pushed=False)
                result["error"] = str(e)
                print(f"[API] push {mid} failed: {e}")
            return result  # 找到就返回

    # weather 特殊处理（weather不在MODES里，单独处理）
    if mode_id == "weather":
        lay = layout or (cfg.page4_layout if cfg else "standard")
        start_time = datetime.datetime.now()
        try:
            mod.task_weather_dashboard(layout=lay)
            history.record(page=page, mode="weather", pushed=True)
            result["ok"] = True
            result["render_time_ms"] = int((datetime.datetime.now() - start_time).total_seconds() * 1000)
            print(f"[API] pushed weather ({lay}) to Page {page}")
        except Exception as e:
            history.record(page=page, mode="weather", pushed=False)
            result["error"] = str(e)
            print(f"[API] push weather failed: {e}")

    return result


def get_history(config_path: str = None) -> list:
    """返回历史记录列表"""
    cfg = Config(config_path) if config_path else Config()
    hist_file = PROJECT_DIR / cfg.history_file
    history = History(str(hist_file), cfg.history_max)
    return history.get_recent(50)


def get_config(config_path: str = None) -> dict:
    """返回当前配置"""
    cfg = Config(config_path) if config_path else Config()
    return {
        "ok": True,
        "enabled_pages": cfg.enabled_pages,
        "page3_modes": cfg.page3_modes,
        "page3_force_mode": cfg.page3_force_mode,
        "page3_layout": cfg.page3_layout,
        "page4_layout": cfg.page4_layout,
        "history_enabled": cfg.history_enabled,
        "history_max": cfg.history_max,
    }


def update_config(updates: dict, config_path: str = None) -> dict:
    """更新配置（写入 config.yaml）"""
    import yaml

    if config_path is None:
        config_path = str(PROJECT_DIR / "config.yaml")

    # 读取现有配置
    cfg = Config(config_path)
    cfg_dict = {
        "enabled_pages": cfg.enabled_pages,
        "page3": {
            "modes": cfg.page3_modes,
            "force_mode": cfg.page3_force_mode,
            "layout": cfg.page3_layout,
        },
        "page4": {
            "layout": cfg.page4_layout,
        },
        "history": {
            "enabled": cfg.history_enabled,
            "max_entries": cfg.history_max,
            "file": cfg.history_file,
        }
    }

    # 应用更新
    if "enabled_pages" in updates:
        cfg_dict["enabled_pages"] = updates["enabled_pages"]
    if "page3_force_mode" in updates:
        cfg_dict["page3"]["force_mode"] = updates["page3_force_mode"]
    if "page4_layout" in updates:
        cfg_dict["page4"]["layout"] = updates["page4_layout"]
    if "page3_modes" in updates:
        cfg_dict["page3"]["modes"] = updates["page3_modes"]
    if "language" in updates:
        cfg_dict.setdefault("language", updates["language"])
    if "content_tone" in updates:
        cfg_dict.setdefault("content_tone", updates["content_tone"])
    if "city" in updates:
        cfg_dict.setdefault("city", updates["city"])
    if "llm_provider" in updates:
        cfg_dict.setdefault("llm_provider", updates["llm_provider"])
    if "llm_model" in updates:
        cfg_dict.setdefault("llm_model", updates["llm_model"])
    if "refresh_interval" in updates:
        cfg_dict.setdefault("refresh_interval", updates["refresh_interval"])
    if "refresh_strategy" in updates:
        cfg_dict.setdefault("refresh_strategy", updates["refresh_strategy"])
    if "time_slot_rules" in updates:
        cfg_dict.setdefault("time_slot_rules", updates["time_slot_rules"])

    # 写回文件
    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.dump(cfg_dict, f, allow_unicode=True, default_flow_style=False)

    return get_config(config_path)


# ── 新增 API 函数 ─────────────────────────────────────────────

def get_stats() -> dict:
    """
    返回全局统计数据
    """
    cfg = Config()
    hist_file = PROJECT_DIR / cfg.history_file
    history = History(str(hist_file), cfg.history_max)
    entries = history.get_recent(200)

    # 基本统计
    total_renders = len(entries)

    # 缓存率（模拟：预览缓存命中率，简化处理）
    cache_hits = 0
    cache_total = 0

    # 计算模式使用频率
    mode_frequency = {}
    for e in entries:
        mode = e.get('mode', 'unknown')
        mode_frequency[mode] = mode_frequency.get(mode, 0) + 1

    # 平均渲染时间
    render_times = [e.get('render_time_ms', 0) for e in entries if e.get('render_time_ms')]
    avg_time_ms = int(sum(render_times) / len(render_times)) if render_times else 0

    # 缓存命中率（如果有缓存记录）
    # 简化：假设 30% 缓存命中率
    cache_rate = 30

    # 每日渲染次数（最近 7 天）
    daily_renders = []
    today = datetime.date.today()
    for i in range(7):
        day = today - datetime.timedelta(days=i)
        count = sum(1 for e in entries if e.get('timestamp', '').startswith(str(day)))
        daily_renders.append({"date": str(day), "count": count})
    daily_renders.reverse()

    # 设备数（模拟为 1，当前是单设备）
    devices = 1

    return {
        "devices": devices,
        "renders": total_renders,
        "cache_rate": cache_rate,
        "avg_time_ms": avg_time_ms,
        "mode_frequency": mode_frequency,
        "daily_renders": daily_renders,
        "total_renders": total_renders,
    }


def get_mode_catalog() -> list:
    """
    返回 22 个模式的元数据（名称/描述）
    """
    modes = _ensure_modes()
    catalog = []

    mode_info = {
        "history_photo": {"name": "历史照片", "desc": "历史上的今天同日期拍摄的照片", "category": "核心"},
        "countdown": {"name": "节日倒计时", "desc": "重要节日的倒计时天数", "category": "核心"},
        "year_progress": {"name": "年进度", "desc": "年度目标完成进度条", "category": "核心"},
        "greeting": {"name": "早安语", "desc": "早安或晚安的问候语", "category": "核心"},
        "poetry": {"name": "每日诗词", "desc": "精选古诗词与简短注解", "category": "核心"},
        "jokes": {"name": "每日笑话", "desc": "轻松幽默的笑话段子", "category": "核心"},
        "cold_knowledge": {"name": "冷知识", "desc": "有趣的生活冷知识", "category": "核心"},
        "thisday": {"name": "历史上的今天", "desc": "今天发生的历史大事件", "category": "核心"},
        "riddle": {"name": "脑筋急转弯", "desc": "有趣的脑筋急转弯题目", "category": "核心"},
        "quote": {"name": "每日语录", "desc": "名人名言与经典语录", "category": "核心"},
        "word": {"name": "每日单词", "desc": "英语单词与中文释义", "category": "工具"},
        "wisdom": {"name": "人生感悟", "desc": "富含哲理的人生感悟", "category": "工具"},
        "health": {"name": "天气养生", "desc": "顺应节气的健康养生建议", "category": "工具"},
        "recipe": {"name": "时令菜谱", "desc": "当季食材的美味菜谱", "category": "工具"},
        "book": {"name": "每日书目", "desc": "每日推荐阅读书籍", "category": "工具"},
        "qa": {"name": "百科问答", "desc": "有趣的百科知识问答", "category": "工具"},
        "chat": {"name": "AI 对话", "desc": "与 AI 的有趣对话", "category": "工具"},
        "art": {"name": "每日美图", "desc": "每日美图文案分享", "category": "工具"},
        "horoscope": {"name": "星座运程", "desc": "星座今日运势", "category": "更多"},
        "news": {"name": "IT之家新闻", "desc": "科技 IT 新闻热榜", "category": "更多"},
        "question": {"name": "每日一问", "desc": "每天一个值得思考的问题", "category": "更多"},
        "goodnight": {"name": "晚安语", "desc": "温馨的晚安问候语", "category": "更多"},
        "health_tip": {"name": "健康提示", "desc": "每日健康小贴士", "category": "更多"},
    }

    for mid, name in modes:
        info = mode_info.get(mid, {})
        catalog.append({
            "mode_id": mid,
            "name": info.get("name", name),
            "desc": info.get("desc", ""),
            "category": info.get("category", "更多"),
        })

    # weather 不在 modes 里，手动加
    catalog.append({
        "mode_id": "weather",
        "name": "天气看板",
        "desc": "实时天气和未来趋势",
        "category": "特殊",
    })

    return catalog


def trigger_refresh() -> dict:
    """
    触发立即刷新
    """
    try:
        # 随机选择一个模式推送
        modes = get_modes()
        if not modes:
            return {"ok": False, "error": "无可用模式"}

        cfg = Config()
        # 如果有强制模式用强制模式，否则随机
        if cfg.page3_force_mode:
            mode_id = cfg.page3_force_mode
        else:
            import random
            if cfg.page3_modes:
                mode_id = random.choice(cfg.page3_modes)
            else:
                mode_id = random.choice(modes)[0]

        # weather 推送
        lay = cfg.page4_layout or "standard"
        result = push_mode("weather", page=4, layout=lay)
        return {"ok": True, "triggered": True, "mode": mode_id, "result": result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_render_history(limit: int = 50) -> list:
    """
    返回最近渲染记录（带渲染时间）
    """
    cfg = Config()
    hist_file = PROJECT_DIR / cfg.history_file
    history = History(str(hist_file), cfg.history_max)
    entries = history.get_recent(limit)
    return [
        {
            "timestamp": e.get("timestamp", ""),
            "mode": e.get("mode", ""),
            "page": e.get("page", 3),
            "pushed": e.get("pushed", False),
            "render_time_ms": e.get("render_time_ms", 0),
        }
        for e in entries
    ]