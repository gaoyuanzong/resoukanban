"""
history_record.py — 推送历史记录
每次推送记录 page / mode / timestamp / pushed=True|False
自动裁剪超过 max_entries 的旧记录
"""
import os, json
from datetime import datetime

DEFAULT_HISTORY_FILE = "history.json"
DEFAULT_MAX_ENTRIES = 100


class History:
    def __init__(self, history_file: str = None, max_entries: int = None):
        if history_file is None:
            history_file = os.path.join(os.path.dirname(__file__), DEFAULT_HISTORY_FILE)
        self._file = history_file
        self._entries = self._load()
        self._max = max_entries or DEFAULT_MAX_ENTRIES

    def _load(self) -> list:
        if not os.path.exists(self._file):
            return []
        try:
            with open(self._file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            if not content:
                return []
            data = json.loads(content)
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            print(f"[History] 加载失败: {e}")
            return []

    def _save(self):
        try:
            with open(self._file, 'w', encoding='utf-8') as f:
                json.dump(self._entries, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[History] 保存失败: {e}")

    def record(self, page: int, mode: str = None, pushed: bool = True,
               detail: str = None):
        entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "page": page,
            "mode": mode,
            "pushed": pushed,
        }
        if detail:
            entry["detail"] = detail

        self._entries.append(entry)

        # 裁剪超过最大条数
        if len(self._entries) > self._max:
            self._entries = self._entries[-self._max:]

        self._save()

    def get_recent(self, n: int = 10) -> list:
        return self._entries[-n:]

    def print_recent(self, n: int = 20) -> str:
        lines = []
        entries = self.get_recent(n)
        if not entries:
            lines.append("暂无推送记录")
            return "\n".join(lines)

        lines.append(f"{'时间':20s}  {'页面':6s}  {'模式':20s}  {'状态'}")
        lines.append("-" * 65)
        for e in entries:
            ts = e.get("timestamp", "")[:19]
            page = f"Page {e.get('page', '?')}"
            mode = e.get("mode", "-") or "-"
            mode = mode[:18]
            status = "✅" if e.get("pushed") else "❌"
            lines.append(f"{ts:20s}  {page:6s}  {mode:20s}  {status}")

        lines.append("-" * 65)
        lines.append(f"共 {len(self._entries)} 条记录")
        return "\n".join(lines)

    def get_last_push(self, page: int) -> dict:
        for e in reversed(self._entries):
            if e.get("page") == page:
                return e
        return None


if __name__ == "__main__":
    h = History()
    print(h.print_recent(10))
