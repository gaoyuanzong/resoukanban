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
from PIL import Image, ImageDraw, ImageFont, ImageOps, ExifTags
from datetime import datetime, timedelta
from zhdate import ZhDate

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

def ccgen(prompt, filename):
    """调用 Claude Code 生成文本内容到文件"""
    output = os.path.join(CCGEN_DIR, filename)
    workdir = "/tmp/cc-gen-work"
    os.makedirs(workdir, exist_ok=True)
    cmd = [
        "/home/gaoyuan/nodejs/bin/claude", "--permission-mode", "bypassPermissions", "--print",
        f"{prompt}。直接输出纯文本，不要markdown代码块，不要任何前缀说明，直接把内容写入文件：{output}"
    ]
    try:
        result = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            return output
    except Exception as e:
        print(f"ccgen 失败: {e}")
    return None

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
    """从 NAS 照片中挑选'历史上的今天'拍摄的照片"""
    today = datetime.now()

    def is_real_photo(path):
        try:
            img = Image.open(path)
            exif = img._getexif()
            if not exif:
                return False
            for tag_id, val in exif.items():
                tag = ExifTags.TAGS.get(tag_id, tag_id)
                if tag in ('Make', 'Model'):
                    return True
            return False
        except:
            return False

    def get_shoot_date(path):
        try:
            img = Image.open(path)
            exif = img._getexif()
            if exif:
                for tag_id, val in exif.items():
                    tag = ExifTags.TAGS.get(tag_id, tag_id)
                    if tag in ('DateTimeOriginal', 'DateTime') and isinstance(val, str) and len(val) >= 10:
                        return datetime.strptime(val[:10], "%Y:%m:%d")
        except:
            pass
        return None

    def get_day_diff(m1, d1, m2, d2):
        try:
            d1_d = datetime(2004, m1, d1)
            d2_d = datetime(2004, m2, d2)
            diff = abs((d1_d - d2_d).days)
            return min(diff, 366 - diff)
        except:
            return 999

    records_by_year = {}
    all_records = []

    for root, dirs, files in os.walk(NAS_PHOTO_ROOT):
        if '@eaDir' in dirs:
            dirs.remove('@eaDir')
        for file in files:
            if not file.lower().endswith(('.jpg', '.jpeg')):
                continue
            full_path = os.path.join(root, file)
            if not is_real_photo(full_path):
                continue
            shoot_date = get_shoot_date(full_path)
            if shoot_date is None:
                continue
            if shoot_date.year == today.year:
                continue
            rec = {'year': shoot_date.year, 'path': full_path}
            all_records.append(rec)
            diff = get_day_diff(today.month, today.day, shoot_date.month, shoot_date.day)
            if diff <= 10:
                yr = shoot_date.year
                if yr not in records_by_year:
                    records_by_year[yr] = []
                records_by_year[yr].append(rec)

    chosen_record = None
    if records_by_year:
        chosen_year = random.choice(list(records_by_year.keys()))
        chosen_record = random.choice(records_by_year[chosen_year])
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
@mode_register("weather", "天气看板")
def mode_weather():
    """渲染天气到 page 3"""
    data = get_hybrid_weather()
    t = data["temp_curr"]
    w = data["weather"]
    advice = get_clothing_advice(t)
    solar = get_solar_term(datetime.now().year, datetime.now().month, datetime.now().day)
    img = new_image()
    draw = ImageDraw.Draw(img)
    draw.text((10, 8), f"{data['city']} | 杭州", font=font_small, fill=0)
    draw.text((300, 8), solar, font=font_small, fill=0)
    draw.text((200, 32), f"{t}°C  {w}", font=font_title, fill=0, anchor="mt")
    draw.text((200, 62), f"{data['temp_high']}° / {data['temp_low']}°  体感 {data['feel_temp']}", font=font_small, fill=0, anchor="mt")
    draw.text((10, 86), f"湿度 {data['humidity']}  {data['wind_info']}", font=font_tiny, fill=0)
    draw.text((10, 100), f"日出 {data['sunrise']} | 日落 {data['sunset']}", font=font_tiny, fill=0)
    draw.line([(10, 116), (390, 116)], fill=0)
    draw.text((10, 120), advice, font=font_tiny, fill=0)
    draw.line([(10, 138), (390, 138)], fill=0)
    y = 148
    for fc in data["forecasts"]:
        md = fc["date"][-5:]  # e.g. "04-21"
        draw.text((10, y), md, font=font_tiny, fill=0)
        draw.text((80, y), fc["weather"], font=font_tiny, fill=0)
        draw.text((170, y), f"{fc['temp_high']}°/{fc['temp_low']}°", font=font_tiny, fill=0)
        y += 16
    draw.text((200, 285), "天气 · 24模式随机", font=font_tiny, fill=0, anchor="mt")
    push_image(img, 3)

# ================= 模式21: 新闻看板（复用已有） =================
@mode_register("news", "IT之家新闻")
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

def task_weather_dashboard():
    print("生成 Page 4: 天气看板...")
    data = get_hybrid_weather()
    w = data["weather"]
    t = data["temp_curr"]
    advice = get_clothing_advice(t)
    solar = get_solar_term(datetime.now().year, datetime.now().month, datetime.now().day)
    lunar = get_lunar_or_festival(datetime.now().year, datetime.now().month, datetime.now().day)
    img = new_image()
    draw = ImageDraw.Draw(img)

    # === 顶行：城市 + 节气 + 日出日落 ===
    draw.text((10, 6), f"{data['city']}", font=font_large, fill=0)
    draw.text((310, 6), solar, font=font_label, fill=0)
    draw.text((10, 28), f"日出 {data['sunrise']}  日落 {data['sunset']}", font=font_small, fill=0)

    draw.line([(10, 46), (390, 46)], fill=0)

    # === 主温度（大字居中）===
    draw.text((200, 50), f"{t}°", font=font_display, fill=0, anchor="mt")
    draw.text((200, 106), w, font=font_mid, fill=0, anchor="mt")

    # === 今日详情行 ===
    draw.text((200, 128), f"最高{data['temp_high']}° / 最低{data['temp_low']}°", font=font_label, fill=0, anchor="mt")
    draw.text((200, 146), f"体感 {data['feel_temp']}   湿度 {data['humidity']}   {data['wind_info']}", font=font_label, fill=0, anchor="mt")

    draw.line([(10, 162), (390, 162)], fill=0)

    # === 穿衣建议 ===
    draw.text((10, 166), advice, font=font_small, fill=0)

    draw.line([(10, 184), (390, 184)], fill=0)

    # === 未来天气：2×2 网格 ===
    # 列宽=190，左列x=10，右列x=205
    # 每格高36px，行1 y=188，行2 y=228
    forecasts = data["forecasts"][:4]
    col_x = [10, 205]
    row_y = [188, 228]

    for i, fc in enumerate(forecasts):
        col = i % 2
        row = i // 2
        x = col_x[col]
        y = row_y[row]

        # 第1行：日期 + 天气
        draw.text((x, y), fc["date"][-5:], font=font_mid, fill=0)       # "04-21"
        draw.text((x+68, y), fc["weather"][:4], font=font_mid, fill=0)  # "小雨"
        draw.text((x+118, y), f"{fc['temp_high']}°/{fc['temp_low']}°", font=font_label, fill=0)  # "18°/13°"

        # 第2行：体感 + 风 + 湿度
        draw.text((x, y+20), f"体感{data['feel_temp']}", font=font_forecast, fill=0)
        draw.text((x+90, y+20), data['wind_info'], font=font_forecast, fill=0)
        draw.text((x+165, y+20), data['humidity'], font=font_forecast, fill=0)

    # === 底部农历 ===
    y_bottom = row_y[1] + 40
    if lunar:
        draw.line([(10, y_bottom), (390, y_bottom)], fill=0)
        draw.text((10, y_bottom+4), f"农历 {lunar}", font=font_label, fill=0)

    draw.text((200, 294), "天气 · 每小时更新", font=font_forecast, fill=0, anchor="mt")
    push_image(img, 4)

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

def task_page3_random():
    """从24个模式中随机选一个执行"""
    if not MODES:
        print("错误: 没有注册任何模式")
        return
    chosen = random.choice(MODES)
    mid, name, func = chosen
    print(f"🎲 抽中 Page 3 模式: {mid} ({name})")
    try:
        func()
    except Exception as e:
        print(f"模式 {mid} 执行失败: {e}")
        import traceback
        traceback.print_exc()

# ================= 主程序 =================
if __name__ == "__main__":
    if not API_KEY or not MAC_ADDRESS:
        print("错误: 请配置 ZECTRIX_API_KEY 和 ZECTRIX_MAC")
        exit(1)
    task_page3_random()
    task_weather_dashboard()
    # task_news_dashboard()  # Page 5 已禁用
    print("所有任务执行完毕！")
