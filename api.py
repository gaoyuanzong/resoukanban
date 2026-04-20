"""
api.py — 墨水屏看板 API 函数
可被 main.py 和 server.py 共用
"""
import os, sys, json, random, tempfile, hashlib
from pathlib import Path

# 确保项目路径在 sys.path
PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

from config_reader import Config
from history_record import History

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


def get_mode_preview_png(mode_id: str, page: int = 3) -> bytes:
    """
    生成指定模式的预览 PNG，返回 bytes
    使用缓存：相同 mode_id + page 只生成一次
    """
    cache_key = f"{mode_id}_p{page}"
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
    mod.ccgen = lambda p, f: None
    mod.read_ccgen = lambda f: []

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

    # weather 特殊处理
    if mode_id == "weather":
        mod.task_weather_dashboard()
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


def push_mode(mode_id: str, page: int = 3, config_path: str = None) -> dict:
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
    mod.read_ccgen = lambda f: []

    result = {"ok": False, "mode": mode_id, "page": page}

    for mid, name, func in mod.MODES:
        if mid == mode_id:
            try:
                func()
                history.record(page=page, mode=mid, pushed=True)
                result["ok"] = True
                print(f"[API] pushed {mid} to Page {page}")
            except Exception as e:
                history.record(page=page, mode=mid, pushed=False)
                result["error"] = str(e)
                print(f"[API] push {mid} failed: {e}")
            break

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

    # 写回文件
    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.dump(cfg_dict, f, allow_unicode=True, default_flow_style=False)

    return get_config(config_path)
