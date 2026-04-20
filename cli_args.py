"""
cli_args.py — 命令行参数解析
支持：
  python main.py                  # 正常运行（随机模式）
  python main.py --force jokes    # 强制指定模式
  python main.py --history        # 显示推送历史
  python main.py --list           # 列出所有模式
  python main.py --config config.yaml  # 指定配置文件
"""
import argparse, sys, os


def parse_args():
    parser = argparse.ArgumentParser(
        description="墨水屏看板推送系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py                  # 正常运行（随机模式）
  python main.py --force jokes    # 强制 Page3 推送笑话
  python main.py --force weather  # 强制 Page4 推送天气
  python main.py --history        # 查看推送历史
  python main.py --list           # 列出所有可用模式
  python main.py --config my.yaml # 使用自定义配置文件
        """
    )

    parser.add_argument(
        '--force', dest='force', type=str, default=None,
        help='强制指定模式运行（跳过随机），如 --force jokes'
    )

    parser.add_argument(
        '--history', action='store_true',
        help='显示推送历史并退出'
    )

    parser.add_argument(
        '--list', action='store_true',
        help='列出所有可用模式并退出'
    )

    parser.add_argument(
        '--config', dest='config', type=str, default=None,
        help='指定配置文件路径（默认: config.yaml）'
    )

    parser.add_argument(
        '--page', dest='page', type=int, default=None,
        help='指定页面（3/4/5），配合 --force 使用'
    )

    args = parser.parse_args()

    # 验证
    if args.force and args.history:
        print("错误: --force 和 --history 不能同时使用")
        sys.exit(1)

    if args.force and args.page and args.page not in [3, 4, 5]:
        print("错误: --page 必须为 3、4 或 5")
        sys.exit(1)

    return args


def list_modes(config=None):
    """列出所有可用模式"""
    if config:
        from config_reader import Config
        cfg = Config(config)
        modes = cfg.page3_modes
    else:
        modes = [
            "history_photo", "countdown", "year_progress", "greeting",
            "poetry", "jokes", "cold_knowledge", "thisday", "riddle",
            "quote", "word", "wisdom", "health", "recipe", "book",
            "qa", "chat", "art", "horoscope", "news",
            "question", "health_tip", "goodnight"
        ]

    from config_reader import Config
    if config is None:
        cfg_obj = Config()
    else:
        cfg_obj = Config(config)

    print("\n=== 可用模式列表（共 {} 个）===\n".format(len(modes)))
    print(f"{'序号':4s}  {'模式ID':20s}  {'中文名称':20s}  {'状态'}")
    print("-" * 60)
    for i, mid in enumerate(modes, 1):
        name = cfg_obj.get_mode_info(mid)
        print(f"{i:4d}  {mid:20s}  {name:20s}  {'✅'}")


if __name__ == "__main__":
    args = parse_args()
    print(f"force={args.force}, history={args.history}, list={args.list}")
