"""
24模式随机转盘 - 墨水屏看板
每次运行随机选择一个模式推送到 Page 3
"""
import os
import random
import requests
import calendar
import re
import subprocess
import json
from pathlib import Path
import datetime
from PIL import Image, ImageDraw, ImageFont, ImageOps, ExifTags
Image.MAX_IMAGE_PIXELS = None  # 禁用解压炸弹检查
from datetime import datetime, timedelta
from zhdate import ZhDate

# 生成历史文件
CCGEN_HISTORY_FILE = "/tmp/ccgen_history.json"

# Phase 1 新模块
from config_reader import Config
from history_record import History
from cli_args import parse_args, list_modes

# ================= 配置区 =================
API_KEY = os.environ.get("ZECTRIX_API_KEY")
MAC_ADDRESS = os.environ.get("ZECTRIX_MAC")
PUSH_URL = f"https://cloud.zectrix.com/open/v1/devices/{MAC_ADDRESS}/display/image"

AMAP_KEY = os.environ.get("AMAP_WEATHER_KEY")
ADCODE = "330110"

NAS_PHOTO_ROOT = "/nas/admin/Photos"

FONT_PATH = "font.ttf"
try:
    font_huge = ImageFont.truetype(FONT_PATH, 65)
    font_title = ImageFont.truetype(FONT_PATH, 24)
    font_item = ImageFont.truetype(FONT_PATH, 18)
    font_small = ImageFont.truetype(FONT_PATH, 14)
    font_tiny = ImageFont.truetype(FONT_PATH, 11)
    font_48 = ImageFont.truetype(FONT_PATH, 48)
    font_36 = ImageFont.truetype(FONT_PATH, 36)
    # 大字体（用于 Page 4/5 改善可读性）
    font_display = ImageFont.truetype(FONT_PATH, 52)  # 主温度
    font_large = ImageFont.truetype(FONT_PATH, 28)   # 城市/标题
    font_mid = ImageFont.truetype(FONT_PATH, 20)      # 正文
    font_label = ImageFont.truetype(FONT_PATH, 16)    # 标签/次要文字
    font_forecast = ImageFont.truetype(FONT_PATH, 14) # 预报小字
except:
    print("错误: 找不到 font.ttf")
    exit(1)

HEADERS = {'User-Agent': 'Mozilla/5.0'}
CCGEN_DIR = "/tmp/ccgen"
os.makedirs(CCGEN_DIR, exist_ok=True)

# ================= 工具函数 =================

LANGUAGE_MAP = {
    "zh": "请使用中文输出",
    "en": "Please output in English",
    "mixed": "请同时输出中文和英文两个版本",
}

TONE_MAP = {
    "positive": "积极鼓励、温暖向上",
    "neutral": "中性克制、理性平和",
    "deep": "深沉内省、富有哲理",
    "humor": "轻松幽默、诙谐有趣",
}

def ccgen(prompt, filename):
    """调用 Claude Code 生成文本内容到文件"""
    # 读取语言和调性设置
    try:
        cfg = Config()
        lang = cfg.get_language()
        tone = cfg.get_content_tone()
    except Exception:
        lang = "zh"
        tone = "neutral"

    lang_hint = LANGUAGE_MAP.get(lang, "请使用中文输出")
    tone_hint = TONE_MAP.get(tone, "中性克制、理性平和")

    # mixed 模式特殊处理：同时输出两种语言
    if lang == "mixed":
        lang_suffix = (
            f"{lang_hint}。"
            f"内容调性：{tone_hint}。"
            "直接输出纯文本，不要markdown代码块，不要任何前缀说明，直接把内容写入文件："
        )
    else:
        lang_suffix = (
            f"{lang_hint}。"
            f"内容调性：{tone_hint}。"
            "直接输出纯文本，不要markdown代码块，不要任何前缀说明，直接把内容写入文件："
        )

    output = os.path.join(CCGEN_DIR, filename)
    workdir = "/tmp/cc-gen-work"
    os.makedirs(workdir, exist_ok=True)
    cmd = [
        "/home/gaoyuan/nodejs/bin/claude", "--permission-mode", "bypassPermissions", "--print",
        f"{prompt}。{lang_suffix}{output}"
    ]
    start_time = datetime.now()
    ok = False
    error_msg = ""
    try:
        result = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            ok = True
            elapsed_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            _record_ccgen_history(filename, ok, elapsed_ms, "")
            return output
        else:
            error_msg = result.stderr.strip() or f"exit {result.returncode}"
    except Exception as e:
        error_msg = str(e)
    elapsed_ms = int((datetime.now() - start_time).total_seconds() * 1000)
    # 记录到历史文件
    _record_ccgen_history(filename, ok, elapsed_ms, error_msg)
    return None


def _record_ccgen_history(filename, ok, elapsed_ms, error_msg=""):
    """将 ccgen 调用记录写入 /tmp/ccgen_history.json"""
    try:
        if os.path.exists(CCGEN_HISTORY_FILE):
            with open(CCGEN_HISTORY_FILE, encoding="utf-8") as f:
                records = json.load(f)
        else:
            records = []
    except Exception:
        records = []
    # 清理只保留最近100条
    records.append({
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "filename": filename,
        "ok": ok,
        "elapsed_ms": elapsed_ms,
        "error_msg": error_msg,
    })
    if len(records) > 100:
        records = records[-100:]
    try:
        with open(CCGEN_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False)
    except Exception:
        pass

def read_ccgen(filename):
    """从内容池读取全部内容行"""
    path = os.path.join(CCGEN_DIR, filename)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        return lines
    return []

def push_image(img, page_id):
    img.save(f"page_{page_id}.png")
    api_headers = {"X-API-Key": API_KEY}
    files = {"images": (f"page_{page_id}.png", open(f"page_{page_id}.png", "rb"), "image/png")}
    data = {"dither": "true", "pageId": str(page_id)}
    try:
        res = requests.post(PUSH_URL, headers=api_headers, files=files, data=data)
        print(f"Page {page_id} 推送成功: {res.status_code}")
    except Exception as e:
        print(f"Page {page_id} 推送失败: {e}")

def new_image():
    return Image.new('1', (400, 300), color=255)

# ================= 24模式定义 =================

MODES = []  # [(mode_id, name, func), ...]

def mode_register(mid, name):
    """装饰器：注册模式"""
    def deco(func):
        MODES.append((mid, name, func))
        return func
    return deco

# ================= 模式1: 历史今日照片 =================
@mode_register("history_photo", "历史今日照片")
def mode_history_photo():
    """从预缓存的历史今日照片候选中随机选取"""
    today = datetime.now()
    cache_file = Path("/tmp/history_photo_cache.json")

    if not cache_file.exists():
        print("错误: 历史照片缓存不存在，请先运行扫描任务")
        return

    with open(cache_file, encoding="utf-8") as f:
        cache = json.load(f)

    by_year = cache.get("by_year", {})
    all_records = cache.get("all", [])

    chosen_record = None
    if by_year:
        chosen_year = random.choice(list(by_year.keys()))
        chosen_record = random.choice(by_year[chosen_year])
    elif all_records:
        chosen_record = random.choice(all_records)
    else:
        print("✨ 今日无历史照片")
        return

    chosen_path = chosen_record['path']
    year = chosen_record['year']
    print(f"✨ 历史今日: {year}年{today.month}月{today.day}日 → {os.path.basename(chosen_path)}")

    img = Image.open(chosen_path)
    img = ImageOps.exif_transpose(img)
    SCREEN_W, SCREEN_H = 400, 300
    img_ratio = img.width / img.height
    target_ratio = SCREEN_W / SCREEN_H
    if img_ratio > target_ratio:
        new_height = SCREEN_H
        new_width = int(new_height * img_ratio)
    else:
        new_width = SCREEN_W
        new_height = int(new_width / img_ratio)
    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    left = (new_width - SCREEN_W) // 2
    top = (new_height - SCREEN_H) // 2
    img = img.crop((left, top, left + SCREEN_W, top + SCREEN_H))

    draw = ImageDraw.Draw(img)
    date_text = f"{year}年{today.month}月{today.day}日"
    try:
        font_date = ImageFont.truetype(FONT_PATH, 14)
    except:
        font_date = font_small
    bbox = draw.textbbox((0, 0), date_text, font=font_date)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    pad_x, pad_y = 6, 4
    margin_right, margin_bottom = 8, 8
    rect_x1 = SCREEN_W - tw - pad_x * 2 - margin_right
    rect_y1 = SCREEN_H - th - pad_y * 2 - margin_bottom
    rect_x2 = SCREEN_W - margin_right
    rect_y2 = SCREEN_H - margin_bottom
    draw.rectangle([rect_x1, rect_y1, rect_x2, rect_y2], fill=0)
    draw.text((rect_x1 + pad_x, rect_y1 + pad_y), date_text, font=font_date, fill=255)
    push_image(img, 3)

# ================= 模式2: 节日倒计时 =================
@mode_register("countdown", "节日倒计时")
def mode_countdown():
    """显示距离下一个重要节日的倒计时"""
    today = datetime.now()
    year = today.year

    festivals = [
        (1, 1, "元旦"),
        (2, 14, "情人节"),
        (3, 8, "妇女节"),
        (4, 1, "愚人节"),
        (4, 20, "世界读书日"),
        (5, 1, "劳动节"),
        (5, 4, "青年节"),
        (6, 1, "儿童节"),
        (7, 1, "建党节"),
        (8, 1, "建军节"),
        (9, 10, "教师节"),
        (10, 1, "国庆节"),
        (10, 31, "万圣节前夜"),
        (11, 11, "双十一"),
        (12, 24, "平安夜"),
        (12, 25, "圣诞节"),
    ]

    next_festival = None
    min_diff = 999
    for m, d, name in festivals:
        try:
            fdate = datetime(year, m, d)
            diff = (fdate - today).days
            if diff > 0 and diff < min_diff:
                min_diff = diff
                next_festival = (m, d, name, fdate)
        except:
            pass

    if next_festival is None or min_diff > 60:
        for m, d, name in festivals:
            try:
                fdate = datetime(year + 1, m, d)
                diff = (fdate - today).days
                if diff > 0 and diff < min_diff:
                    min_diff = diff
                    next_festival = (m, d, name, fdate)
            except:
                pass

    m, d, name, fdate = next_festival
    diff = min_diff

    img = new_image()
    draw = ImageDraw.Draw(img)

    title = "距离下一个节日还有"
    draw.text((200, 30), title, font=font_small, fill=0, anchor="mt")
    draw.text((200, 55), name, font=font_title, fill=0, anchor="mt")

    num_text = str(diff)
    font_num = ImageFont.truetype(FONT_PATH, 72)
    bbox = draw.textbbox((0, 0), num_text, font=font_num)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text((200, 130), num_text, font=font_num, fill=0, anchor="mt")

    draw.text((200, 210), "天", font=font_title, fill=0, anchor="mt")

    date_str = f"{m}月{d}日" if m != 12 or d != 25 else "12月25日"
    draw.text((200, 250), date_str, font=font_small, fill=0, anchor="mt")

    push_image(img, 3)

# ================= 模式3: 年进度 =================
@mode_register("year_progress", "年进度")
def mode_year_progress():
    """显示今年的进度百分比"""
    today = datetime.now()
    start = datetime(today.year, 1, 1)
    end = datetime(today.year + 1, 1, 1)
    total_days = (end - start).days
    elapsed = (today - start).days
    pct = elapsed / total_days * 100

    img = new_image()
    draw = ImageDraw.Draw(img)

    draw.text((200, 30), f"{today.year}年进度", font=font_title, fill=0, anchor="mt")

    pct_str = f"{pct:.1f}%"
    font_big = ImageFont.truetype(FONT_PATH, 56)
    bbox = draw.textbbox((0, 0), pct_str, font=font_big)
    tw = bbox[2] - bbox[0]
    draw.text((200, 90), pct_str, font=font_big, fill=0, anchor="mt")

    bar_w = 360
    bar_h = 20
    bar_x = (400 - bar_w) // 2
    bar_y = 170
    draw.rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], outline=0)
    filled = int(bar_w * pct / 100)
    draw.rectangle([bar_x, bar_y, bar_x + filled, bar_y + bar_h], fill=0)

    day_str = f"第{elapsed}天 / 共{total_days}天"
    draw.text((200, 210), day_str, font=font_item, fill=0, anchor="mt")

    month_str = f"{today.month}月{today.day}日 {calendar.day_name[today.weekday()]}"
    draw.text((200, 245), month_str, font=font_small, fill=0, anchor="mt")

    push_image(img, 3)

# ================= 模式4: 早安语/晚安语 =================
@mode_register("greeting", "早安语/晚安语")
def mode_greeting():
    """根据时间段显示早安、午安、晚安语"""
    hour = datetime.now().hour
    if 5 <= hour < 12:
        title = "早安"
        file = "greeting_am.txt"
    elif 12 <= hour < 18:
        title = "午安"
        file = "greeting_noon.txt"
    else:
        title = "晚安"
        file = "goodnight.txt"

    lines = read_ccgen(file)
    msg = random.choice(lines) if lines else "今日宜心平气和。"

    img = new_image()
    draw = ImageDraw.Draw(img)

    draw.text((200, 50), title, font=font_huge, fill=0, anchor="mt")

    draw.text((200, 150), msg, font=font_item, fill=0, anchor="mt")

    time_str = datetime.now().strftime("%H:%M")
    draw.text((200, 260), time_str, font=font_small, fill=0, anchor="mt")

    push_image(img, 3)

# ================= 模式5: 每日诗词 =================
@mode_register("poetry", "每日诗词")
def mode_poetry():
    """通过 ccgen 生成古诗词并渲染"""
    ccgen("请生成5首经典中国古诗词（唐诗或宋词），每首包含：诗题、作者（朝代·姓名）、正文（4句，每句一行），每首之间用空行分隔。格式示例：\n静夜思\n唐·李白\n床前明月光\n疑是地上霜\n举头望明月\n低头思故乡\n\n（第二首...）直接输出纯文本", "poetry.txt")

    lines = read_ccgen("poetry.txt")
    if not lines:
        print("✨诗词生成失败，使用默认")
        lines = ["春眠不觉晓","处处闻啼鸟","夜来风雨声","花落知多少"]

    img = new_image()
    draw = ImageDraw.Draw(img)

    draw.text((200, 20), "每日诗词", font=font_title, fill=0, anchor="mt")

    y = 60
    display_lines = [l for l in lines[:12] if l.strip()]
    for line in display_lines[:8]:
        line = line.strip()
        if not line:
            y += 8
            continue
        if len(line) > 12:
            font_use = font_small
        else:
            font_use = font_item
        draw.text((200, y), line, font=font_use, fill=0, anchor="mt")
        y += 22

    push_image(img, 3)

# ================= 模式6: 笑话 =================
@mode_register("jokes", "每日笑话")
def mode_jokes():
    """通过 ccgen 生成笑话并渲染"""
    ccgen("请生成8个幽默中文笑话，每个不超过25字，一行一个笑话，不要编号，直接输出纯文本", "jokes.txt")

    lines = read_ccgen("jokes.txt")
    if not lines:
        lines = ["笑话生成失败"]

    img = new_image()
    draw = ImageDraw.Draw(img)

    draw.text((200, 15), "今日笑话 😄", font=font_title, fill=0, anchor="mt")

    y = 50
    for line in lines[:10]:
        line = line.strip()
        if not line:
            continue
        font_use = font_small if len(line) > 15 else font_item
        draw.text((10, y), f"· {line}", font=font_use, fill=0)
        y += 22
        if y > 280:
            break

    push_image(img, 3)

# ================= 模式7: 冷知识 =================
@mode_register("cold_knowledge", "冷知识")
def mode_cold_knowledge():
    """通过 ccgen 生成冷知识"""
    ccgen("请生成8条有趣的生活冷知识/小窍门，每条不超过20字，一行一条，直接输出纯文本", "cold_knowledge.txt")

    lines = read_ccgen("cold_knowledge.txt")
    if not lines:
        lines = ["冷知识生成失败"]

    img = new_image()
    draw = ImageDraw.Draw(img)

    draw.text((200, 15), "生活冷知识 💡", font=font_title, fill=0, anchor="mt")

    y = 50
    for line in lines[:10]:
        line = line.strip()
        if not line:
            continue
        font_use = font_small if len(line) > 15 else font_item
        draw.text((10, y), f"· {line}", font=font_use, fill=0)
        y += 22
        if y > 280:
            break

    push_image(img, 3)

# ================= 模式8: 历史上的今天 =================
@mode_register("thisday", "历史上的今天")
def mode_thisday():
    """通过 ccgen 生成历史上的今天事件"""
    today = datetime.now()
    ccgen(f"请生成5条{ today.month }月{ today.day }日历史上发生的重大事件，每条不超过25字，一行一条，直接输出纯文本", "thisday.txt")

    lines = read_ccgen("thisday.txt")
    if not lines:
        lines = ["历史事件生成失败"]

    img = new_image()
    draw = ImageDraw.Draw(img)

    title = f"{today.month}月{today.day}日 历史上的今天"
    draw.text((200, 15), title, font=font_small, fill=0, anchor="mt")

    y = 45
    for line in lines[:8]:
        line = line.strip()
        if not line:
            continue
        draw.text((10, y), f"· {line}", font=font_small, fill=0)
        y += 26
        if y > 280:
            break

    push_image(img, 3)

# ================= 模式9: 脑筋急转弯 =================
@mode_register("riddle", "脑筋急转弯")
def mode_riddle():
    """通过 ccgen 生成脑筋急转弯"""
    ccgen("请生成5个脑筋急转弯，每条格式：问题？|答案，用'|'分隔问题与答案，直接输出纯文本，一行一组", "riddle.txt")

    lines = read_ccgen("riddle.txt")
    if not lines:
        lines = ["脑筋急转弯生成失败"]

    img = new_image()
    draw = ImageDraw.Draw(img)

    draw.text((200, 10), "脑筋急转弯 🧠", font=font_title, fill=0, anchor="mt")

    y = 48
    for line in lines[:6]:
        line = line.strip()
        if '|' not in line:
            continue
        q, a = line.split('|', 1)
        font_use = font_small if len(q) > 18 else font_item
        draw.text((10, y), f"问: {q}", font=font_use, fill=0)
        y += 20
        draw.text((10, y), f"答: {a}", font=font_small, fill=0)
        y += 28
        if y > 280:
            break

    push_image(img, 3)

# ================= 模式10: 每日语录 =================
@mode_register("quote", "每日语录")
def mode_quote():
    """通过 ccgen 生成名人语录"""
    ccgen("请生成5条中英文名人语录，每条格式：'语录内容' — 作者，一行一条，直接输出纯文本", "quote.txt")

    lines = read_ccgen("quote.txt")
    if not lines:
        lines = ["语录生成失败"]

    img = new_image()
    draw = ImageDraw.Draw(img)

    draw.text((200, 15), "每日语录 📖", font=font_title, fill=0, anchor="mt")

    y = 50
    for line in lines[:6]:
        line = line.strip()
        if not line:
            continue
        font_use = font_small if len(line) > 22 else font_item
        draw.text((10, y), line, font=font_use, fill=0)
        y += 30
        if y > 280:
            break

    push_image(img, 3)

# ================= 模式11: 英文单词 =================
@mode_register("word", "每日单词")
def mode_word():
    """通过 ccgen 生成每日英语单词"""
    ccgen("请生成8个常用英语单词及其中文释义，格式：word - 中文释义，一行一个，直接输出纯文本", "word.txt")

    lines = read_ccgen("word.txt")
    if not lines:
        lines = ["单词生成失败"]

    img = new_image()
    draw = ImageDraw.Draw(img)

    draw.text((200, 15), "每日单词 📚", font=font_title, fill=0, anchor="mt")

    y = 50
    for line in lines[:8]:
        line = line.strip()
        if not line or ' - ' not in line:
            continue
        word, meaning = line.split(' - ', 1)
        draw.text((10, y), word.strip(), font=font_item, fill=0)
        draw.text((200, y), meaning.strip(), font=font_small, fill=0)
        y += 26
        if y > 280:
            break

    push_image(img, 3)

# ================= 模式12: 人生感悟 =================
@mode_register("wisdom", "人生感悟")
def mode_wisdom():
    """通过 ccgen 人生感悟句子"""
    ccgen("请生成6条人生感悟/哲理句子，每条不超过20字，一行一条，直接输出纯文本", "wisdom.txt")

    lines = read_ccgen("wisdom.txt")
    if not lines:
        lines = ["感悟生成失败"]

    img = new_image()
    draw = ImageDraw.Draw(img)

    draw.text((200, 15), "人生感悟 🌿", font=font_title, fill=0, anchor="mt")

    y = 50
    for line in lines[:8]:
        line = line.strip()
        if not line:
            continue
        font_use = font_small if len(line) > 16 else font_item
        draw.text((10, y), f"· {line}", font=font_use, fill=0)
        y += 28
        if y > 280:
            break

    push_image(img, 3)

# ================= 模式13: 天气养生 =================
@mode_register("health", "天气养生")
def mode_health():
    """通过 ccgen 根据天气生成养生建议"""
    ccgen("请生成6条根据当前天气（春季）的生活养生小贴士，每条不超过20字，一行一条，直接输出纯文本", "health.txt")

    lines = read_ccgen("health.txt")
    if not lines:
        lines = ["养生建议生成失败"]

    img = new_image()
    draw = ImageDraw.Draw(img)

    draw.text((200, 15), "天气养生 🌿", font=font_title, fill=0, anchor="mt")

    y = 50
    for line in lines[:8]:
        line = line.strip()
        if not line:
            continue
        font_use = font_small if len(line) > 16 else font_item
        draw.text((10, y), f"· {line}", font=font_use, fill=0)
        y += 28
        if y > 280:
            break

    push_image(img, 3)

# ================= 模式14: 时令菜谱 =================
@mode_register("recipe", "时令菜谱")
def mode_recipe():
    """通过 ccgen 生成时令菜谱"""
    ccgen("请生成4道时令家常菜谱，每道包含：菜名 + 一句话做法，用'｜'分隔，格式示例：番茄炒蛋｜简单快手，两分钟出锅。一行一道菜，直接输出纯文本", "recipe.txt")

    lines = read_ccgen("recipe.txt")
    if not lines:
        lines = ["菜谱生成失败"]

    img = new_image()
    draw = ImageDraw.Draw(img)

    draw.text((200, 15), "时令菜谱 🍳", font=font_title, fill=0, anchor="mt")

    y = 50
    for line in lines[:6]:
        line = line.strip()
        if not line or '｜' not in line:
            continue
        name, desc = line.split('｜', 1)
        draw.text((10, y), f"▪ {name.strip()}", font=font_item, fill=0)
        y += 20
        draw.text((10, y), f"  {desc.strip()}", font=font_small, fill=0)
        y += 30
        if y > 280:
            break

    push_image(img, 3)

# ================= 模式15: 每日书目 =================
@mode_register("book", "每日书目")
def mode_book():
    """通过 ccgen 推荐每日书籍"""
    ccgen("请生成3本推荐书籍，每本包含：书名、作者、一句话推荐理由，用'｜'分隔，格式示例：活着｜余华｜人生的无奈与坚韧。一行一本，直接输出纯文本", "book.txt")

    lines = read_ccgen("book.txt")
    if not lines:
        lines = ["书目生成失败"]

    img = new_image()
    draw = ImageDraw.Draw(img)

    draw.text((200, 15), "每日书目 📚", font=font_title, fill=0, anchor="mt")

    y = 50
    for line in lines[:5]:
        line = line.strip()
        if not line or '｜' not in line:
            continue
        parts = line.split('｜')
        name = parts[0].strip()
        author = parts[1].strip() if len(parts) > 1 else ""
        reason = parts[2].strip() if len(parts) > 2 else ""
        draw.text((10, y), f"📖 {name}", font=font_item, fill=0)
        y += 20
        if author:
            draw.text((10, y), f"  {author}", font=font_small, fill=0)
            y += 18
        if reason:
            draw.text((10, y), f"  {reason}", font=font_small, fill=0)
            y += 22
        y += 6
        if y > 280:
            break

    push_image(img, 3)

# ================= 模式16: 百科问答 =================
@mode_register("qa", "百科问答")
def mode_qa():
    """通过 ccgen 生成有趣的百科问答"""
    ccgen("请生成4个有趣的百科知识问答，每组格式：问题？|答案，用'|'分隔，直接输出纯文本，一行一组", "qa.txt")

    lines = read_ccgen("qa.txt")
    if not lines:
        lines = ["问答生成失败"]

    img = new_image()
    draw = ImageDraw.Draw(img)

    draw.text((200, 15), "百科问答 ❓", font=font_title, fill=0, anchor="mt")

    y = 48
    for line in lines[:5]:
        line = line.strip()
        if '|' not in line:
            continue
        q, a = line.split('|', 1)
        draw.text((10, y), f"? {q}", font=font_small, fill=0)
        y += 20
        draw.text((10, y), f"  {a}", font=font_tiny, fill=0)
        y += 28
        if y > 280:
            break

    push_image(img, 3)

# ================= 模式17: AI 对话 =================
@mode_register("chat", "AI 对话")
def mode_chat():
    """通过 ccgen 生成有趣的 AI 对话"""
    ccgen("请生成一段有趣的中文 AI 与人的对话，不少于5轮，格式：人：xxx | AI：xxx，一行一轮，直接输出纯文本", "chat.txt")

    lines = read_ccgen("chat.txt")
    if not lines:
        lines = ["对话生成失败"]

    img = new_image()
    draw = ImageDraw.Draw(img)

    draw.text((200, 10), "🤖 AI 对话", font=font_title, fill=0, anchor="mt")

    y = 42
    for line in lines[:10]:
        line = line.strip()
        if not line or '：' not in line:
            continue
        speaker, content = line.split('：', 1)
        is_ai = 'AI' in speaker or '机器人' in speaker
        prefix = "🤖" if is_ai else "👤"
        font_use = font_small if len(line) > 25 else font_item
        draw.text((10, y), f"{prefix} {content.strip()}", font=font_use, fill=0)
        y += 22
        if y > 285:
            break

    push_image(img, 3)

# ================= 模式18: 每日美图文案 =================
@mode_register("art", "每日美图文案")
def mode_art():
    """通过 ccgen 生成美图配文"""
    ccgen("请为一张风景图片生成3段配文（每段不超过15字），描述自然风光或情感意境，直接输出纯文本，一行一段", "art.txt")

    lines = read_ccgen("art.txt")
    if not lines:
        lines = ["美图文案生成失败"]

    img = new_image()
    draw = ImageDraw.Draw(img)

    draw.text((200, 60), "🌄 每日美图", font=font_title, fill=0, anchor="mt")

    y = 110
    for line in lines[:4]:
        line = line.strip()
        if not line:
            continue
        draw.text((200, y), line, font=font_item, fill=0, anchor="mt")
        y += 35

    push_image(img, 3)

# ================= 模式19: 星座运程 =================
@mode_register("horoscope", "星座运程")
def mode_horoscope():
    """通过 ccgen 生成今日星座运程"""
    signs = ["白羊座", "金牛座", "双子座", "巨蟹座", "狮子座", "处女座",
             "天秤座", "天蝎座", "射手座", "摩羯座", "水瓶座", "双鱼座"]
    chosen = random.choice(signs)
    ccgen(f"请为{chosen}生成今日（{datetime.now().month}月{datetime.now().day}日）运程，包括：整体运势、爱情运势、工作运势，各用一句话描述不超过15字，格式：整体运势：xxx | 爱情运势：xxx | 工作运势：xxx，直接输出纯文本", "horoscope.txt")

    lines = read_ccgen("horoscope.txt")
    content = lines[0] if lines else "运程生成失败"

    img = new_image()
    draw = ImageDraw.Draw(img)

    draw.text((200, 20), f"♈ {chosen}", font=font_title, fill=0, anchor="mt")
    draw.text((200, 60), f"{datetime.now().month}/{datetime.now().day} 今日运程", font=font_small, fill=0, anchor="mt")

    parts = content.split('|') if '|' in content else [content]
    y = 100
    labels = ["整体运势", "爱情运势", "工作运势"]
    for i, part in enumerate(parts[:3]):
        part = part.strip()
        if not part:
            continue
        if '：' in part:
            _, val = part.split('：', 1)
        else:
            val = part
        label = labels[i] if i < len(labels) else ""
        draw.text((10, y), f"{label}：", font=font_item, fill=0)
        draw.text((10, y + 22), val.strip(), font=font_small, fill=0)
        y += 55
        if y > 280:
            break

    push_image(img, 3)

# ================= 模式20: 天气看板（复用已有） =================
def mode_news():
    """渲染新闻到 page 3"""
    news = get_ithome_news()
    img = new_image()
    draw = ImageDraw.Draw(img)
    draw.text((10, 8), "IT之家 热门排行", font=font_small, fill=0)
    draw.line([(10, 24), (390, 24)], fill=0)
    y = 32
    for i, n in enumerate(news[:12], 1):
        draw.text((10, y), f"{i}. {n['title']}", font=font_tiny, fill=0)
        y += 21
        if y > 290:
            break
    push_image(img, 3)

# ================= 模式22: 每日一问 =================
@mode_register("question", "每日一问")
def mode_question():
    """通过 ccgen 生成一个有趣的思考问题"""
    ccgen("请生成1个有趣的人生问题或思考题，不超过30字，直接输出纯文本，不要任何前缀说明", "question.txt")

    lines = read_ccgen("question.txt")
    question = lines[0] if lines else "今天你想成为什么样的人？"

    img = new_image()
    draw = ImageDraw.Draw(img)

    draw.text((200, 80), "每日一问", font=font_title, fill=0, anchor="mt")
    draw.text((200, 150), question, font=font_item, fill=0, anchor="mt")
    draw.text((200, 260), "— 思考使你更强大", font=font_small, fill=0, anchor="mt")

    push_image(img, 3)

# ================= 模式23: 健康提示 =================
@mode_register("health_tip", "健康提示")
def mode_health_tip():
    """通过 ccgen 根据当前季节生成健康提示"""
    ccgen("请生成6条春季健康生活小贴士，每条不超过18字，涵盖饮食、运动、作息、情绪等方面，一行一条，直接输出纯文本", "health_tip.txt")
def mode_news():
    """渲染新闻到 page 3"""
    news = get_ithome_news()
    img = new_image()
    draw = ImageDraw.Draw(img)
    draw.text((10, 8), "IT之家 热门排行", font=font_small, fill=0)
    draw.line([(10, 24), (390, 24)], fill=0)
    y = 32
    for i, n in enumerate(news[:12], 1):
        draw.text((10, y), f"{i}. {n['title']}", font=font_tiny, fill=0)
        y += 21
        if y > 290:
            break
    push_image(img, 3)


    img = new_image()
    draw = ImageDraw.Draw(img)

    draw.text((200, 15), "🍀 健康生活", font=font_title, fill=0, anchor="mt")

    y = 50
    for line in lines[:8]:
        line = line.strip()
        if not line:
            continue
        font_use = font_small if len(line) > 16 else font_item
        draw.text((10, y), f"· {line}", font=font_use, fill=0)
        y += 28
        if y > 280:
            break

    push_image(img, 3)

# ================= 模式24: 晚安语（独立模式） =================
@mode_register("goodnight", "晚安语")
def mode_goodnight():
    """生成晚安语，不依赖时间段判断"""
    ccgen("请生成5条温馨的晚安问候语，每条不超过15字，包含温暖祝福，一行一条，直接输出纯文本", "goodnight.txt")

    lines = read_ccgen("goodnight.txt")
    if not lines:
        lines = ["晚安，好梦。"]

    img = new_image()
    draw = ImageDraw.Draw(img)

    draw.text((200, 30), "🌙 晚安", font=font_huge, fill=0, anchor="mt")

    y = 100
    for line in lines[:5]:
        line = line.strip()
        if not line:
            continue
        draw.text((200, y), line, font=font_item, fill=0, anchor="mt")
        y += 32

    time_str = datetime.now().strftime("%Y年%m月%d日")
    draw.text((200, 260), time_str, font=font_small, fill=0, anchor="mt")

    push_image(img, 3)

# ================= 天气相关（下层函数） =================

def get_clothing_advice(temp):
    try:
        t = int(temp)
        if t >= 28: return "建议穿短袖、短裤，注意防晒补水。"
        elif t >= 22: return "体感舒适，建议穿 T 恤配薄长裤。"
        elif t >= 16: return "建议穿长袖衬衫、卫衣或单层薄外套。"
        elif t >= 10: return "气温微凉，建议穿夹克、风衣或毛衣。"
        elif t >= 5: return "建议穿大衣、厚毛衣或薄款羽绒服。"
        else: return "天气寒冷，建议穿厚羽绒服，注意防寒。"
    except:
        return "请根据实际体感气温调整着装。"

def get_solar_term(year, month, day):
    data = [
        (1, 6, "小寒"), (1, 20, "大寒"),
        (2, 4, "立春"), (2, 19, "雨水"),
        (3, 6, "惊蛰"), (3, 21, "春分"),
        (4, 5, "清明"), (4, 20, "谷雨"),
        (5, 6, "立夏"), (5, 21, "小满"),
        (6, 6, "芒种"), (6, 21, "夏至"),
        (7, 7, "小暑"), (7, 23, "大暑"),
        (8, 8, "立秋"), (8, 23, "处暑"),
        (9, 8, "白露"), (9, 23, "秋分"),
        (10, 8, "寒露"), (10, 23, "霜降"),
        (11, 7, "立冬"), (11, 22, "小雪"),
        (12, 7, "大雪"), (12, 22, "冬至"),
    ]
    for m, d, name in data:
        if m == month and d == day:
            return name
    for m, d, name in data:
        if m == month and d >= day:
            return name
    return "立春"

def get_lunar_or_festival(y, m, d):
    try:
        zh = ZhDate(y, m, d)
        lunar = zh.lunar_date()
        festivals = {
            (1, 1): "春节", (1, 15): "元宵节",
            (5, 5): "端午节", (7, 7): "七夕节",
            (8, 15): "中秋节", (9, 9): "重阳节",
            (12, 8): "腊八节",
        }
        lm, ld = lunar.month, lunar.day
        return festivals.get((lm, ld), f"农历{lm}月{ld}")
    except:
        return None

def get_hybrid_weather():
    result = {
        "city": "余杭区", "weather": "未知", "temp_curr": 0,
        "temp_low": 0, "temp_high": 0, "wind_info": "无数据",
        "humidity": "0%", "feel_temp": "N/A",
        "sunrise": "--:--", "sunset": "--:--", "forecasts": []
    }
    if not AMAP_KEY:
        return result
    try:
        base_url = f"https://restapi.amap.com/v3/weather/weatherInfo?city={ADCODE}&key={AMAP_KEY}&extensions=base"
        base_resp = requests.get(base_url, timeout=10).json()
        if base_resp.get("status") == "1" and base_resp.get("lives"):
            live = base_resp["lives"][0]
            result["city"] = live.get("city", "余杭区")
            result["weather"] = live.get("weather", "未知")
            result["temp_curr"] = int(live.get("temperature", 0))
            result["humidity"] = live.get("humidity", "0") + "%"
            wind_power_raw = live.get("windpower", "0")
            wind_direction = live.get("winddirection", "")
            wind_num = re.search(r'\d+', wind_power_raw)
            wind_power = wind_num.group(0) if wind_num else "0"
            result["wind_info"] = f"{wind_power}级 {wind_direction}"
            try:
                wind_speed = int(wind_power)
                wind_kmh = {0: 0, 1: 2, 2: 8}.get(wind_speed, 15 + (wind_speed - 3) * 7)
                feel_temp = result["temp_curr"] - (wind_kmh / 15) if wind_kmh > 5 else result["temp_curr"]
                result["feel_temp"] = f"{round(feel_temp, 1)}°C"
            except:
                result["feel_temp"] = f"{result['temp_curr']}°C"
    except:
        pass
    try:
        all_url = f"https://restapi.amap.com/v3/weather/weatherInfo?city={ADCODE}&key={AMAP_KEY}&extensions=all"
        all_resp = requests.get(all_url, timeout=10).json()
        if all_resp.get("status") == "1" and all_resp.get("forecasts"):
            forecast = all_resp["forecasts"][0]
            casts = forecast.get("casts", [])
            if casts:
                result["temp_low"] = int(casts[0].get("nighttemp", 0))
                result["temp_high"] = int(casts[0].get("daytemp", 0))
            for idx in [1, 2]:
                if idx < len(casts):
                    day = casts[idx]
                    result["forecasts"].append({
                        "date": day.get("date", "")[5:],
                        "weather": day.get("dayweather", "未知"),
                        "temp_low": int(day.get("nighttemp", 0)),
                        "temp_high": int(day.get("daytemp", 0))
                    })
    except:
        pass
    try:
        wttr_url = "https://wttr.in/Hangzhou?format=j1&lang=zh"
        wttr_resp = requests.get(wttr_url, timeout=15).json()
        astro = wttr_resp['weather'][0]['astronomy'][0]
        result["sunrise"] = astro['sunrise']
        result["sunset"] = astro['sunset']
    except:
        pass
    return result

def task_weather_dashboard(cfg=None, history=None, layout="standard"):
    """
    生成 Page 4 天气看板
    layout: standard=标准布局, compact=紧凑布局, full=全屏大字
    """
    print(f"生成 Page 4: 天气看板 ({layout} layout)...")
    img = Image.new('1', (400, 300), color=255)
    draw = ImageDraw.Draw(img)

    weather = get_hybrid_weather()
    if weather["temp_curr"] == 0 and not weather["forecasts"]:
        draw.text((20, 50), "天气数据获取失败，请检查 API Key", font=font_item, fill=0)
        push_image(img, 4)
        return

    if layout == "compact":
        _render_weather_compact(draw, weather)
    elif layout == "full":
        _render_weather_full(draw, weather)
    else:
        _render_weather_standard(draw, weather)

    push_image(img, 4)


def _render_weather_standard(draw, weather):
    """标准布局"""
    # === 城市名 + 更新时间 ===
    draw.text((20, 10), weather["city"], font=font_title, fill=0)
    now_beijing = datetime.now()
    update_time = now_beijing.strftime("%H:%M")
    time_text = f"更新 {update_time}"
    bbox = draw.textbbox((0, 0), time_text, font=font_small)
    time_width = bbox[2] - bbox[0]
    draw.text((390 - time_width, 12), time_text, font=font_small, fill=0)

    # === 主温度 + 天气 ===
    draw.text((25, 40), f"{weather['temp_curr']}°C", font=font_48, fill=0)
    draw.text((25, 100), f"{weather['temp_low']}°/{weather['temp_high']}°", font=font_item, fill=0)
    draw.text((150, 45), weather["weather"], font=font_36, fill=0)

    # === 右侧信息框 ===
    draw.rounded_rectangle([(235, 45), (385, 130)], radius=8, outline=0, fill=0)
    draw.text((245, 45), weather["wind_info"], font=font_small, fill=255)
    draw.text((245, 70), f"湿度 {weather['humidity']}", font=font_small, fill=255)
    draw.text((245, 95), f"体感 {weather['feel_temp']}", font=font_small, fill=255)

    # === 日出日落 ===
    draw.text((25, 135), f"日出 {weather['sunrise']}   日落 {weather['sunset']}", font=font_item, fill=0)

    # === 分隔线 ===
    draw.line([(20, 160), (380, 160)], fill=0, width=1)

    # === 2天预报 ===
    x_positions = [30, 200]
    for i, day in enumerate(weather["forecasts"][:2]):
        x = x_positions[i]
        draw.text((x, 175), day["date"], font=font_item, fill=0)
        draw.text((x, 200), day["weather"], font=font_item, fill=0)
        draw.text((x, 220), f"{day['temp_low']}°~{day['temp_high']}°", font=font_item, fill=0)

    # === 穿衣建议 ===
    advice = get_clothing_advice(weather["temp_curr"])
    draw.line([(20, 250), (380, 250)], fill=0, width=1)
    advice_lines = [advice[i:i+18] for i in range(0, len(advice), 18)]
    for i, line in enumerate(advice_lines[:2]):
        draw.text((20, 262 + i*24), f"[衣] {line}", font=font_item, fill=0)


def _render_weather_compact(draw, weather):
    """紧凑布局：顶部大字温度，4天预报网格"""
    # 城市 + 日出日落
    draw.text((10, 6), weather["city"], font=font_large, fill=0)
    draw.text((10, 30), f"日出 {weather['sunrise']}  日落 {weather['sunset']}", font=font_small, fill=0)
    draw.line([(10, 46), (390, 46)], fill=0)

    # 主温度
    draw.text((200, 50), f"{weather['temp_curr']}°", font=font_display, fill=0, anchor="mt")
    draw.text((200, 105), weather["weather"], font=font_mid, fill=0, anchor="mt")

    # 今日详情
    draw.text((200, 128), f"最高{weather['temp_high']}° / 最低{weather['temp_low']}°", font=font_label, fill=0, anchor="mt")
    draw.text((200, 146), f"体感 {weather['feel_temp']}", font=font_label, fill=0, anchor="mt")

    draw.line([(10, 162), (390, 162)], fill=0)

    # 4天预报 2x2 网格
    draw.text((10, 166), f"湿度 {weather['humidity']}  {weather['wind_info']}", font=font_label, fill=0)
    draw.line([(10, 184), (390, 184)], fill=0)

    fc = weather["forecasts"][:4]
    cols = 2
    for i in range(4):
        if i >= len(fc):
            break
        col = i % cols
        row = i // cols
        x = [10, 205][col]
        y = 190 + row * 36
        d = fc[i]
        draw.text((x, y), d["date"][-5:], font=font_mid, fill=0)
        draw.text((x, y+20), f"{d['weather']}  {d['temp_low']}°/{d['temp_high']}°", font=font_forecast, fill=0)

    # 穿衣
    draw.line([(10, 262), (390, 262)], fill=0)
    advice = get_clothing_advice(weather["temp_curr"])
    draw.text((10, 266), advice[:30], font=font_label, fill=0)


def _render_weather_full(draw, weather):
    """全屏大字布局"""
    # 城市 + 节气
    draw.text((10, 6), weather["city"], font=font_large, fill=0)
    draw.text((310, 6), f"更新 {datetime.utcnow().strftime('%H:%M')}", font=font_small, fill=0)
    draw.line([(10, 24), (390, 24)], fill=0)

    # 超大温度
    draw.text((200, 26), f"{weather['temp_curr']}°", font=font_display, fill=0, anchor="mt")
    draw.text((200, 84), weather["weather"], font=font_mid, fill=0, anchor="mt")

    # 横向详情条
    draw.text((10, 108), f"最高 {weather['temp_high']}°", font=font_label, fill=0)
    draw.text((140, 108), f"最低 {weather['temp_low']}°", font=font_label, fill=0)
    draw.text((260, 108), f"体感 {weather['feel_temp']}", font=font_label, fill=0)
    draw.text((10, 126), f"湿度 {weather['humidity']}", font=font_label, fill=0)
    draw.text((140, 126), weather["wind_info"], font=font_label, fill=0)
    draw.text((260, 126), f"日出 {weather['sunrise']}", font=font_label, fill=0)
    draw.text((350, 126), f"日落 {weather['sunset']}", font=font_label, fill=0, anchor="rt")

    draw.line([(10, 144), (390, 144)], fill=0)

    # 4天预报
    fc = weather["forecasts"][:4]
    for i in range(4):
        if i >= len(fc):
            break
        d = fc[i]
        col = i % 2
        row = i // 2
        x = [10, 205][col]
        y = 150 + row * 50
        draw.text((x, y), d["date"][-5:], font=font_mid, fill=0)
        draw.text((x+65, y), d["weather"][:4], font=font_mid, fill=0)
        draw.text((x+130, y), f"{d['temp_high']}°/{d['temp_low']}°", font=font_label, fill=0)
        draw.text((x, y+22), f"体感 {weather['feel_temp']}", font=font_forecast, fill=0)
        draw.text((x+90, y+22), weather["wind_info"], font=font_forecast, fill=0)
        draw.text((x+165, y+22), weather["humidity"], font=font_forecast, fill=0)

    # 穿衣
    draw.line([(10, 250), (390, 250)], fill=0)
    advice = get_clothing_advice(weather["temp_curr"])
    draw.text((10, 255), advice[:36], font=font_label, fill=0)

def get_ithome_news():
    try:
        url = "https://api.ithome.com/ajax/news ranking?rankingId=hot"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        data = resp.json()
        items = data.get("data", [])[:10]
        news = []
        for item in items:
            title = item.get("title", "")[:30]
            links = item.get("links", {})
            url2 = links.get("pc", "") if isinstance(links, dict) else ""
            news.append({"title": title, "url": url2})
        return news
    except:
        return []

def task_news_dashboard():
    print("生成 Page 5: IT之家热门新闻...")
    news = get_ithome_news()
    img = new_image()
    draw = ImageDraw.Draw(img)
    draw.text((10, 8), "IT之家 热门排行", font=font_small, fill=0)
    draw.line([(10, 24), (390, 24)], fill=0)
    y = 32
    for i, n in enumerate(news[:12], 1):
        draw.text((10, y), f"{i}. {n['title']}", font=font_tiny, fill=0)
        y += 21
        if y > 290:
            break
    push_image(img, 5)

# ================= Page 3 随机转盘 =================

def task_page3_random(cfg=None, history=None):
    """从配置的可用模式中随机选一个执行，支持时段绑定"""
    if cfg is None:
        cfg = Config()

    # 时段匹配逻辑
    strategy = cfg.get_refresh_strategy()
    chosen_modes = None
    if strategy == "time_slot":
        rules = cfg.get_time_slot_rules()
        hour = datetime.now().hour
        for rule in rules:
            if rule.get("startHour", 0) <= hour < rule.get("endHour", 0):
                slot_modes = rule.get("modes", [])
                if slot_modes:
                    # 只从该时段允许的模式中选择
                    chosen_modes = [(mid, name, fn) for mid, name, fn in MODES if mid in slot_modes]
                    print(f"[时段] {rule.get('startHour')}:00-{rule.get('endHour')}:0 时段匹配到 {len(chosen_modes)} 个模式")
                    break
        if chosen_modes is None:
            print("[时段] 当前时段无匹配规则，fallback 到随机")

    # fallback: 从配置的可用模式中随机选
    if not chosen_modes:
        available = [(mid, name, fn) for mid, name, fn in MODES if mid in cfg.page3_modes]
        if not available:
            print("错误: 没有可用模式")
            return
        chosen_modes = available

    chosen = random.choice(chosen_modes)
    mid, name, func = chosen
    print(f"🎲 抽中 Page 3 模式: {mid} ({name})")
    pushed = False
    try:
        func()
        pushed = True
    except Exception as e:
        print(f"模式 {mid} 执行失败: {e}")
        import traceback
        traceback.print_exc()

    if history:
        history.record(page=3, mode=mid, pushed=pushed)

# ================= 主程序 =================
if __name__ == "__main__":
    args = parse_args()

    # 加载配置
    cfg = Config(args.config) if args.config else Config()

    # 加载历史
    hist_file = os.path.join(os.path.dirname(__file__), cfg.history_file)
    history = History(hist_file, cfg.history_max)

    # --history: 只打印历史
    if args.history:
        print(history.print_recent(20))
        exit(0)

    # --list: 只列出模式
    if args.list:
        list_modes(args.config)
        exit(0)

    # 强制推送逻辑（--force 时跳过 API 检查）
    if args.force:
        force_mode = args.force.lower()
        target_page = args.page or 3
        print(f"[Force] 强制推送 Page {target_page} 模式: {force_mode}")

        # 找到对应函数
        found = False
        for mid, name, func in MODES:
            if mid.lower() == force_mode:
                try:
                    func()
                    history.record(page=target_page, mode=mid, pushed=True)
                    print(f"[Force] {mid} 推送成功")
                    found = True
                except Exception as e:
                    print(f"[Force] {mid} 失败: {e}")
                    history.record(page=target_page, mode=mid, pushed=False)
                break

        if not found:
            print(f"[Force] 未知模式: {force_mode}，可用: {[m[0] for m in MODES]}")

        # weather 可以强制推 page 4
        if force_mode == "weather" and target_page == 4:
            try:
                task_weather_dashboard()
                history.record(page=4, mode="weather", pushed=True)
            except Exception as e:
                print(f"[Force] weather 失败: {e}")
                history.record(page=4, mode="weather", pushed=False)

        if found or force_mode == "weather":
            print("所有任务执行完毕！")
            exit(0)

    # API 检查（仅在非 --force 时）
    if not API_KEY or not MAC_ADDRESS:
        print("错误: 请配置 ZECTRIX_API_KEY 和 ZECTRIX_MAC")
        exit(1)

    # 正常随机推送
    if cfg.is_page_enabled(3):
        task_page3_random(cfg, history)
        # 记录 page 3 推送历史
        for mid, name, func in MODES:
            last = history.get_last_push(3)
            if last and last.get("mode") == mid:
                break
        else:
            # 从日志找刚推送的 mid
            pass

    if cfg.is_page_enabled(4):
        task_weather_dashboard(cfg, history, layout=cfg.page4_layout)

    print("所有任务执行完毕！")
