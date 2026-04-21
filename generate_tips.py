#!/usr/bin/env python3
"""
每天凌晨生成100条鼓励语，存入文件
每小时推送从文件随机读取，不再调用LLM
"""
import subprocess, os
from datetime import datetime

TIP_FILE = "/tmp/kanban_tips.txt"
TODAY_FILE = "/tmp/kanban_tips_date.txt"

def generate_tips():
    """调用 Claude Code 生成100条鼓励语（每条≤15字）"""
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"[{today}] 开始生成100条鼓励语...")

    prompt = (
        "请生成100条温暖鼓励的话，每条不超过15个中文字，内容多样化，"
        "包括：阳光积极、健身健康、工作努力、生活美好、情感温暖等不同主题。 "
        "格式：每行一条，不要编号，不要加引号，直接输出100行文本。"
    )

    try:
        result = subprocess.run(
            ["claude", "--print", "-p", prompt],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, timeout=60
        )
        if result.returncode == 0 and result.stdout:
            lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
            # 取前100条
            tips = lines[:100]
            # 保存到文件
            with open(TIP_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(tips))
            with open(TODAY_FILE, "w") as f:
                f.write(today)
            print(f"✅ 生成成功：{len(tips)} 条 → {TIP_FILE}")
            return tips
        else:
            print(f"❌ 生成失败: returncode={result.returncode}")
            return None
    except Exception as e:
        print(f"❌ 异常: {e}")
        return None

def main():
    today = datetime.now().strftime("%Y-%m-%d")
    # 检查今日是否已生成
    try:
        with open(TODAY_FILE) as f:
            if f.read().strip() == today and os.path.getsize(TIP_FILE) > 100:
                print(f"[{today}] 今日鼓励语已存在，跳过生成")
                return
    except FileNotFoundError:
        pass

    tips = generate_tips()
    if tips:
        print(f"示例前5条:")
        for t in tips[:5]:
            print(f"  - {t}")

if __name__ == "__main__":
    main()
