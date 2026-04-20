"""
config_reader.py — 墨水屏看板配置加载器
支持 config.yaml 配置文件，默认值回退，无文件时使用内置默认值
"""
import os, yaml
from pathlib import Path

DEFAULT_CFG = {
    "enabled_pages": [3, 4],
    "page3": {
        "modes": [
            "history_photo", "countdown", "year_progress", "greeting",
            "poetry", "jokes", "cold_knowledge", "thisday", "riddle",
            "quote", "word", "wisdom", "health", "recipe", "book",
            "qa", "chat", "art", "horoscope", "news",
            "question", "health_tip", "goodnight"
        ],
        "force_mode": None,       # None=随机, "jokes"=强制某个模式
        "layout": "default"
    },
    "page4": {
        "layout": "standard",     # standard / compact / full
        "force_update": False
    },
    "history": {
        "enabled": True,
        "max_entries": 100,
        "file": "history.json"
    }
}

VALID_PAGES = [3, 4, 5]
VALID_LAYOUTS = {"standard", "compact", "full"}


class Config:
    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
        self._path = config_path
        self._cfg = self._load()

    def _load(self) -> dict:
        """加载配置，缺失字段使用默认值"""
        if not os.path.exists(self._path):
            print(f"[Config] 配置文件不存在，使用默认配置: {self._path}")
            return dict(DEFAULT_CFG)

        try:
            with open(self._path, 'r', encoding='utf-8') as f:
                user_cfg = yaml.safe_load(f) or {}
            print(f"[Config] 已加载配置: {self._path}")
        except Exception as e:
            print(f"[Config] 配置加载失败，使用默认: {e}")
            return dict(DEFAULT_CFG)

        # 深度合并默认值
        cfg = dict(DEFAULT_CFG)
        cfg.update(user_cfg)

        # page3 默认值
        if "page3" not in user_cfg:
            cfg["page3"] = dict(DEFAULT_CFG["page3"])
        else:
            for k, v in DEFAULT_CFG["page3"].items():
                cfg["page3"].setdefault(k, v)

        # page4 默认值
        if "page4" not in user_cfg:
            cfg["page4"] = dict(DEFAULT_CFG["page4"])
        else:
            for k, v in DEFAULT_CFG["page4"].items():
                cfg["page4"].setdefault(k, v)

        # history 默认值
        if "history" not in user_cfg:
            cfg["history"] = dict(DEFAULT_CFG["history"])
        else:
            for k, v in DEFAULT_CFG["history"].items():
                cfg["history"].setdefault(k, v)

        # 验证
        cfg["enabled_pages"] = [p for p in cfg.get("enabled_pages", []) if p in VALID_PAGES]
        if not cfg["enabled_pages"]:
            cfg["enabled_pages"] = [3, 4]
            print("[Config] 警告: 无效页面配置，回退到 [3, 4]")

        if cfg["page4"]["layout"] not in VALID_LAYOUTS:
            cfg["page4"]["layout"] = "standard"

        return cfg

    # === 公开属性 ===
    @property
    def enabled_pages(self):
        return self._cfg.get("enabled_pages", [3, 4])

    @property
    def page3_modes(self):
        return self._cfg.get("page3", {}).get("modes", DEFAULT_CFG["page3"]["modes"])

    @property
    def page3_force_mode(self):
        return self._cfg.get("page3", {}).get("force_mode", None)

    @property
    def page3_layout(self):
        return self._cfg.get("page3", {}).get("layout", "default")

    @property
    def page4_layout(self):
        return self._cfg.get("page4", {}).get("layout", "standard")

    @property
    def history_enabled(self):
        return self._cfg.get("history", {}).get("enabled", True)

    @property
    def history_max(self):
        return self._cfg.get("history", {}).get("max_entries", 100)

    @property
    def history_file(self):
        return self._cfg.get("history", {}).get("file", "history.json")

    def is_page_enabled(self, page_id: int) -> bool:
        return page_id in self.enabled_pages

    def get_mode_info(self, mode_id: str) -> str:
        """返回模式的中文名称"""
        mode_names = {
            "history_photo": "历史今日照片",
            "countdown": "节日倒计时",
            "year_progress": "年进度",
            "greeting": "早安语/晚安语",
            "poetry": "每日诗词",
            "jokes": "每日笑话",
            "cold_knowledge": "冷知识",
            "thisday": "历史上的今天",
            "riddle": "脑筋急转弯",
            "quote": "每日语录",
            "word": "每日单词",
            "wisdom": "人生感悟",
            "health": "天气养生",
            "recipe": "时令菜谱",
            "book": "每日书目",
            "qa": "百科问答",
            "chat": "AI对话",
            "art": "每日美图文案",
            "horoscope": "星座运程",
            "news": "IT之家新闻",
            "question": "每日一问",
            "health_tip": "健康提示",
            "goodnight": "晚安语",
        }
        return mode_names.get(mode_id, mode_id)


if __name__ == "__main__":
    cfg = Config()
    print(f"启用页面: {cfg.enabled_pages}")
    print(f"Page3 模式数: {len(cfg.page3_modes)}")
    print(f"Page3 强制模式: {cfg.page3_force_mode}")
    print(f"Page4 布局: {cfg.page4_layout}")
    print(f"历史记录: {cfg.history_enabled}, 最多{cfg.history_max}条")
