import os
import random
import requests
import calendar
import re
from PIL import Image, ImageDraw, ImageFont, ImageOps, ExifTags
from datetime import datetime, timedelta
from zhdate import ZhDate

# ================= 配置区 =================
API_KEY = os.environ.get("ZECTRIX_API_KEY")
MAC_ADDRESS = os.environ.get("ZECTRIX_MAC")
PUSH_URL = f"https://cloud.zectrix.com/open/v1/devices/{MAC_ADDRESS}/display/image"

# 高德配置（津南区）
AMAP_KEY = os.environ.get("AMAP_WEATHER_KEY")
ADCODE = "330110"  # 津南区


# NAS 照片路径
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
except:
    print("错误: 找不到 font.ttf")
    exit(1)

HEADERS = {'User-Agent': 'Mozilla/5.0'}

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

# ================= 节气与农历 =================
def get_solar_term(year, month, day):
    term_table = {
        (2024,2,4):"立春", (2024,2,19):"雨水", (2024,3,5):"惊蛰", (2024,3,20):"春分",
        (2024,4,4):"清明", (2024,4,19):"谷雨", (2024,5,5):"立夏", (2024,5,20):"小满",
        (2024,6,5):"芒种", (2024,6,21):"夏至", (2024,7,6):"小暑", (2024,7,22):"大暑",
        (2024,8,7):"立秋", (2024,8,22):"处暑", (2024,9,7):"白露", (2024,9,22):"秋分",
        (2024,10,8):"寒露", (2024,10,23):"霜降", (2024,11,7):"立冬", (2024,11,22):"小雪",
        (2024,12,6):"大雪", (2024,12,21):"冬至",
        (2025,1,5):"小寒", (2025,1,20):"大寒", (2025,2,3):"立春", (2025,2,18):"雨水",
        (2025,3,5):"惊蛰", (2025,3,20):"春分", (2025,4,4):"清明", (2025,4,20):"谷雨",
        (2025,5,5):"立夏", (2025,5,21):"小满", (2025,6,5):"芒种", (2025,6,21):"夏至",
        (2025,7,7):"小暑", (2025,7,22):"大暑", (2025,8,7):"立秋", (2025,8,23):"处暑",
        (2025,9,7):"白露", (2025,9,22):"秋分", (2025,10,8):"寒露", (2025,10,23):"霜降",
        (2025,11,7):"立冬", (2025,11,22):"小雪", (2025,12,7):"大雪", (2025,12,21):"冬至",
        (2026,1,5):"小寒", (2026,1,20):"大寒", (2026,2,4):"立春", (2026,2,18):"雨水",
        (2026,3,5):"惊蛰", (2026,3,20):"春分", (2026,4,5):"清明", (2026,4,20):"谷雨",
        (2026,5,5):"立夏", (2026,5,21):"小满", (2026,6,6):"芒种", (2026,6,21):"夏至",
        (2026,7,7):"小暑", (2026,7,23):"大暑", (2026,8,7):"立秋", (2026,8,23):"处暑",
        (2026,9,7):"白露", (2026,9,23):"秋分", (2026,10,8):"寒露", (2026,10,23):"霜降",
        (2026,11,7):"立冬", (2026,11,22):"小雪", (2026,12,7):"大雪", (2026,12,21):"冬至",
        (2027,1,5):"小寒", (2027,1,20):"大寒", (2027,2,4):"立春", (2027,2,19):"雨水",
        (2027,3,6):"惊蛰", (2027,3,21):"春分", (2027,4,5):"清明", (2027,4,20):"谷雨",
    }
    return term_table.get((year, month, day), None)

def get_lunar_or_festival(y, m, d):
    term = get_solar_term(y, m, d)
    if term:
        return term
    solar_fests = {
        (1,1):"元旦", (2,14):"情人节", (3,8):"妇女节", (4,1):"愚人节",
        (5,1):"劳动节", (6,1):"儿童节", (7,1):"建党节", (8,1):"建军节",
        (9,10):"教师节", (10,1):"国庆节", (12,25):"圣诞节"
    }
    if (m, d) in solar_fests:
        return solar_fests[(m, d)]
    try:
        lunar = ZhDate.from_datetime(datetime(y, m, d))
        lm, ld = lunar.lunar_month, lunar.lunar_day
        lunar_fests = {
            (1,1):"春节", (1,15):"元宵节", (5,5):"端午节",
            (7,7):"七夕节", (8,15):"中秋节", (9,9):"重阳节", (12,30):"除夕"
        }
        if (lm, ld) in lunar_fests:
            return lunar_fests[(lm, ld)]
        days = ["初一","初二","初三","初四","初五","初六","初七","初八","初九","初十",
                "十一","十二","十三","十四","十五","十六","十七","十八","十九","二十",
                "廿一","廿二","廿三","廿四","廿五","廿六","廿七","廿八","廿九","三十"]
        months = ["正月","二月","三月","四月","五月","六月","七月","八月","九月","十月","冬月","腊月"]
        if ld == 1:
            return months[lm-1]
        return days[ld-1]
    except:
        return ""

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

# ================= 历史今日照片 =================
def task_history_photo():
    """从 NAS 照片目录中查找“历史上的今天”的照片"""
    print("生成 Page 3: 历史今日...")
    
    today = datetime.now()
    
    candidates = []
    processed = 0
    
    for root, dirs, files in os.walk(NAS_PHOTO_ROOT):
        if '@eaDir' in dirs:
            dirs.remove('@eaDir')
        
        for file in files:
            if not file.lower().endswith(('.jpg', '.jpeg')):
                continue
            processed += 1
            
            name = file[:8]
            for sep in ('', '-', '/'):
                for fmt in ('%Y%m%d', '%Y-%m-%d', '%Y/%m/%d'):
                    try:
                        file_date = datetime.strptime(name, fmt)
                        if file_date.month == today.month and file_date.day == today.day:
                            candidates.append(os.path.join(root, file))
                            break
                    except ValueError:
                        continue
                    name = name.replace(sep, '/', 2) if sep else name
    
    if not candidates:
        print("✨ 今日无历史照片，提示上次发回消")
        return
    
    chosen = random.choice(candidates)
    basename = os.path.basename(chosen)
    year = basename[:4]
    print(f"✨ 历史今日: {year}年 {today.month}月{today.day}日 → {basename}")
    
    img = Image.open(chosen)
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

def get_hybrid_weather():
    """高德实时(base) + 高德预报(all) + wttr.in 日出日落"""
    result = {
        "city": "津南区",
        "weather": "未知",
        "temp_curr": 0,
        "temp_low": 0,
        "temp_high": 0,
        "wind_info": "无数据",
        "humidity": "0%",
        "feel_temp": "N/A",
        "sunrise": "--:--",
        "sunset": "--:--",
        "forecasts": []
    }
    
    if not AMAP_KEY:
        print("⚠️ 未设置 AMAP_WEATHER_KEY，无法获取高德数据")
        return result

    # ---------- 1. 高德实时数据 (extensions=base) ----------
    try:
        base_url = f"https://restapi.amap.com/v3/weather/weatherInfo?city={ADCODE}&key={AMAP_KEY}&extensions=base"
        print(f"请求高德实时 API: {base_url}")
        base_resp = requests.get(base_url, timeout=10).json()
        if base_resp.get("status") == "1" and base_resp.get("lives"):
            live = base_resp["lives"][0]
            result["city"] = live.get("city", "津南区")
            result["weather"] = live.get("weather", "未知")
            result["temp_curr"] = int(live.get("temperature", 0))
            result["humidity"] = live.get("humidity", "0") + "%"
            wind_power_raw = live.get("windpower", "0")
            wind_direction = live.get("winddirection", "")
            wind_num = re.search(r'\d+', wind_power_raw)
            wind_power = wind_num.group(0) if wind_num else "0"
            result["wind_info"] = f"{wind_power}级 {wind_direction}"
            # 计算体感温度
            try:
                wind_speed = int(wind_power)
                if wind_speed <= 1:
                    wind_kmh = 2
                elif wind_speed == 2:
                    wind_kmh = 8
                else:
                    wind_kmh = 15 + (wind_speed - 3) * 7
                feel_temp = result["temp_curr"] - (wind_kmh / 15) if wind_kmh > 5 else result["temp_curr"]
                humidity_val = int(live.get("humidity", 50))
                if humidity_val > 70:
                    feel_temp -= 1
                result["feel_temp"] = f"{round(feel_temp, 1)}°C"
            except:
                result["feel_temp"] = f"{result['temp_curr']}°C"
            print("✅ 高德实时数据获取成功")
        else:
            print(f"⚠️ 高德实时 API 返回异常: {base_resp.get('status')}")
    except Exception as e:
        print(f"❌ 高德实时请求异常: {e}")

    # ---------- 2. 高德预报数据 (extensions=all) ----------
    try:
        all_url = f"https://restapi.amap.com/v3/weather/weatherInfo?city={ADCODE}&key={AMAP_KEY}&extensions=all"
        print(f"请求高德预报 API: {all_url}")
        all_resp = requests.get(all_url, timeout=10).json()
        if all_resp.get("status") == "1" and all_resp.get("forecasts"):
            forecast = all_resp["forecasts"][0]
            casts = forecast.get("casts", [])
            if len(casts) >= 1:
                today_cast = casts[0]
                result["temp_low"] = int(today_cast.get("nighttemp", 0))
                result["temp_high"] = int(today_cast.get("daytemp", 0))
            # 未来两天预报（索引1=明天，索引2=后天）
            for idx in [1, 2]:
                if idx < len(casts):
                    day = casts[idx]
                    # 天气描述使用白天天气
                    weather_desc = day.get("dayweather", "未知")
                    result["forecasts"].append({
                        "date": day.get("date", "")[5:],
                        "weather": weather_desc,
                        "temp_low": int(day.get("nighttemp", 0)),
                        "temp_high": int(day.get("daytemp", 0))
                    })
            print("✅ 高德预报数据获取成功")
        else:
            print(f"⚠️ 高德预报 API 返回异常: {all_resp.get('status')}")
    except Exception as e:
        print(f"❌ 高德预报请求异常: {e}")

    # ---------- 3. wttr.in 日出日落 ----------
    try:
        wttr_url = "https://wttr.in/Jinnan,Tianjin?format=j1&lang=zh"
        print(f"请求 wttr.in 天文数据: {wttr_url}")
        wttr_resp = requests.get(wttr_url, timeout=15).json()
        astro = wttr_resp['weather'][0]['astronomy'][0]
        result["sunrise"] = astro['sunrise']
        result["sunset"] = astro['sunset']
        print("✅ wttr.in 日出日落获取成功")
    except Exception as e:
        print(f"❌ wttr.in 请求异常: {e}")

    return result

# ================= 天气看板 =================
def task_weather_dashboard():
    print("生成 Page 4: 混合天气看板（高德+高德+wttr.in日出日落）...")
    img = Image.new('1', (400, 300), color=255)
    draw = ImageDraw.Draw(img)

    weather = get_hybrid_weather()
    if weather["temp_curr"] == 0 and not weather["forecasts"]:
        draw.text((20, 50), "天气数据获取失败，请检查API Key或网络", font=font_item, fill=0)
        push_image(img, 4)
        return

    city_name = weather["city"]
    weather_text = weather["weather"]
    curr_temp = weather["temp_curr"]
    today_low = weather["temp_low"]
    today_high = weather["temp_high"]
    wind_info = weather["wind_info"]
    humidity = weather["humidity"]
    feel_temp = weather["feel_temp"]
    sunrise = weather["sunrise"]
    sunset = weather["sunset"]
    forecasts = weather["forecasts"]

    now_beijing = datetime.utcnow() + timedelta(hours=8)
    update_time = now_beijing.strftime("%H:%M")

    draw.text((20, 10), f"{city_name} | 菜鸟智谷", font=font_title, fill=0)
    time_text = f"更新: {update_time}"
    try:
        bbox = draw.textbbox((0, 0), time_text, font=font_small)
        time_width = bbox[2] - bbox[0]
    except:
        time_width = len(time_text) * 8
    draw.text((390 - time_width, 12), time_text, font=font_small, fill=0)

    draw.text((25, 40), f"{curr_temp}°C", font=font_48, fill=0)
    draw.text((25, 100), f"{today_low}°/{today_high}°", font=font_item, fill=0)
    draw.text((150, 45), f"{weather_text}", font=font_36, fill=0)

    draw.rounded_rectangle([(235, 45), (385, 130)], radius=8, outline=0, fill=0)
    draw.text((245, 45), f"{wind_info}", font=font_small, fill=255)
    draw.text((245, 70), f"湿度 {humidity}", font=font_small, fill=255)
    draw.text((245, 95), f"体感 {feel_temp}", font=font_small, fill=255)

    draw.text((25, 135), f"日出 {sunrise}   日落 {sunset}", font=font_item, fill=0)

    draw.line([(20, 160), (380, 160)], fill=0, width=1)
    x_positions = [30, 200]
    for i, day in enumerate(forecasts[:2]):
        x = x_positions[i]
        draw.text((x, 175), day["date"], font=font_item, fill=0)
        draw.text((x, 200), day["weather"], font=font_item, fill=0)
        draw.text((x, 220), f"{day['temp_low']}°~{day['temp_high']}°", font=font_item, fill=0)

    advice = get_clothing_advice(curr_temp)
    draw.line([(20, 250), (380, 250)], fill=0, width=1)
    advice_lines = [advice[i:i+18] for i in range(0, len(advice), 18)]
    for i, line in enumerate(advice_lines[:2]):
        draw.text((20, 262 + i*24), f"[衣] {line}", font=font_item, fill=0)

    push_image(img, 4)

# ================= IT之家 热门新闻 =================
def get_ithome_news():
    """抓取 IT之家 热门新闻标题"""
    result = []
    try:
        resp = requests.get("https://www.ithome.com/", headers=HEADERS, timeout=10)
        resp.encoding = 'utf-8'
        # 匹配热门新闻列表中的标题
        pattern = re.compile(r'<a[^>]+href="https://www\.ithome\.com/[^"]*"[^>]*>([^<]+)</a>')
        titles = pattern.findall(resp.text)
        # 去重并过滤
        seen = set()
        for t in titles:
            t = t.strip()
            if len(t) > 5 and t not in seen and not t.startswith('http'):
                seen.add(t)
                result.append(t)
                if len(result) >= 10:
                    break
        print(f"✅ IT之家新闻获取成功: {len(result)} 条")
    except Exception as e:
        print(f"❌ IT之家请求异常: {e}")
    return result

# ================= 新闻看板 =================
def task_news_dashboard():
    print("生成 Page 4: IT之家热门新闻...")
    img = Image.new('1', (400, 300), color=255)
    draw = ImageDraw.Draw(img)

    news = get_ithome_news()
    if not news:
        draw.text((20, 50), "新闻数据获取失败，请检查网络", font=font_item, fill=0)
        push_image(img, 5)
        return

    draw.text((20, 10), "IT之家 | 热门资讯", font=font_title, fill=0)
    draw.line([(20, 40), (380, 40)], fill=0, width=2)

    y = 55
    for i, title in enumerate(news[:8]):
        # 截断超长标题
        if len(title) > 22:
            title = title[:21] + "…"
        draw.text((25, y), f"{i+1}. {title}", font=font_item, fill=0)
        y += 30

    push_image(img, 5)

# ================= 主程序 =================
if __name__ == "__main__":
    if not API_KEY or not MAC_ADDRESS:
        print("错误: 请配置 ZECTRIX_API_KEY 和 ZECTRIX_MAC")
        exit(1)
    task_history_photo()
    task_weather_dashboard()
    task_news_dashboard()
    print("所有任务执行完毕！")
