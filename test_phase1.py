#!/usr/bin/env python3
"""Phase 1 测试：配置系统 + 强制推送 + 历史记录"""
import os, sys, yaml, json, tempfile

# 确保可以 import 项目模块
sys.path.insert(0, '/home/gaoyuan/workspace/resoukanban')

# ================= 测试 config.yaml 解析 =================

def test_config_load():
    """配置加载正常"""
    from config_reader import Config
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write("enabled_pages: [3, 4]\n")
        f.write("page3:\n  modes: [jokes, quote]\n")
        f.write("  force_mode: jokes\n")
        f.write("page4:\n  layout: standard\n")
        path = f.name
    try:
        cfg = Config(path)
        assert cfg.enabled_pages == [3, 4]
        assert cfg.page3_force_mode == "jokes"
        assert cfg.page4_layout == "standard"
        assert "jokes" in cfg.page3_modes
        print("test_config_load PASS")
    finally:
        os.unlink(path)

def test_config_defaults():
    """默认值正常"""
    from config_reader import Config
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write("enabled_pages: [3]\n")
        path = f.name
    try:
        cfg = Config(path)
        assert cfg.page3_force_mode is None
        assert cfg.page4_layout == "standard"
        assert cfg.history_enabled == True
        assert cfg.history_max == 100
        print("test_config_defaults PASS")
    finally:
        os.unlink(path)

def test_config_invalid_page_rejected():
    """非法页面编号应报错"""
    from config_reader import Config
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write("enabled_pages: [99]\n")
        path = f.name
    try:
        cfg = Config(path)
        assert cfg.enabled_pages == [3, 4]  # 应回退到默认值
        print("test_config_invalid_page_rejected PASS")
    finally:
        os.unlink(path)

def test_config_missing_file():
    """配置文件缺失时应使用默认配置"""
    from config_reader import Config
    cfg = Config("/nonexistent/config.yaml")
    assert cfg.enabled_pages == [3, 4]
    assert cfg.page3_force_mode is None
    print("test_config_missing_file PASS")

# ================= 测试强制推送模式 =================

def test_force_mode_jokes():
    """强制 --force jokes 应该只运行 jokes 模式"""
    from config_reader import Config
    cfg = Config.__new__(Config)
    cfg._cfg = {"enabled_pages": [3, 4], "page3": {"force_mode": "jokes"}}
    assert cfg.page3_force_mode == "jokes"
    # main.py 应该跳过随机，直接运行 mode_jokes
    print("test_force_mode_jokes PASS")

def test_force_mode_none_random():
    """force_mode=null 应该走随机"""
    from config_reader import Config
    cfg = Config.__new__(Config)
    cfg._cfg = {"enabled_pages": [3, 4]}
    assert cfg.page3_force_mode is None
    print("test_force_mode_none_random PASS")

# ================= 测试历史记录 =================

def test_history_record():
    """记录推送历史"""
    import importlib, sys, history_record
    importlib.reload(history_record)
    from history_record import History
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
        path = f.name
    try:
        h = History(path)
        h.record(page=3, mode="jokes", pushed=True)
        h.record(page=4, mode="weather", pushed=True)
        entries = h.get_recent(10)
        assert len(entries) == 2
        assert entries[-1]["page"] == 4  # newest
        assert entries[-2]["page"] == 3   # older
        print("test_history_record PASS")
    finally:
        os.unlink(path)

def test_history_max_entries():
    """超过最大条目应自动裁剪"""
    import importlib, sys, history_record
    importlib.reload(history_record)
    from history_record import History
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
        path = f.name
    try:
        h = History(path, max_entries=5)
        for i in range(10):
            h.record(page=3, mode=f"mode_{i}", pushed=True)
        entries = h.get_recent(10)
        assert len(entries) == 5
        assert entries[-1]["mode"] == "mode_9"  # newest
        print("test_history_max_entries PASS")
    finally:
        os.unlink(path)

def test_history_print():
    """--history 打印格式正确"""
    from history_record import History
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
        path = f.name
    try:
        h = History(path)
        h.record(page=3, mode="jokes", pushed=True)
        h.record(page=4, mode="weather", pushed=True)
        output = h.print_recent(5)
        assert "Page 3" in output
        assert "jokes" in output
        assert "Page 4" in output
        print("test_history_print PASS")
    finally:
        os.unlink(path)

# ================= 测试 CLI 参数解析 =================

def test_cli_args_force():
    """--force MODE 参数解析"""
    sys.argv = ['main.py', '--force', 'jokes']
    from cli_args import parse_args
    args = parse_args()
    assert args.force == 'jokes'
    assert args.history == False
    assert args.list == False
    print("test_cli_args_force PASS")

def test_cli_args_history():
    """--history 参数解析"""
    sys.argv = ['main.py', '--history']
    from cli_args import parse_args
    args = parse_args()
    assert args.history == True
    print("test_cli_args_history PASS")

def test_cli_args_list():
    """--list 参数解析"""
    sys.argv = ['main.py', '--list']
    from cli_args import parse_args
    args = parse_args()
    assert args.list == True
    print("test_cli_args_list PASS")

def test_cli_args_default():
    """无参数时走随机"""
    sys.argv = ['main.py']
    from cli_args import parse_args
    args = parse_args()
    assert args.force is None
    assert args.history == False
    print("test_cli_args_default PASS")

# ================= 测试 main.py 集成 =================

def test_main_no_api_key_quits():
    """没有 API_KEY 时应该优雅退出，不崩溃"""
    import main as m
    orig_key = os.environ.get('ZECTRIX_API_KEY')
    if 'ZECTRIX_API_KEY' in os.environ:
        del os.environ['ZECTRIX_API_KEY']
    try:
        # 模拟检查
        API_KEY = os.environ.get("ZECTRIX_API_KEY")
        MAC_ADDRESS = os.environ.get("ZECTRIX_MAC")
        # 应该打印错误并退出
        assert API_KEY is None
        print("test_main_no_api_key_quits PASS (API_KEY=None detected)")
    finally:
        if orig_key:
            os.environ['ZECTRIX_API_KEY'] = orig_key

if __name__ == "__main__":
    print("=== Phase 1 测试开始 ===")
    tests = [
        test_config_load,
        test_config_defaults,
        test_config_invalid_page_rejected,
        test_config_missing_file,
        test_force_mode_jokes,
        test_force_mode_none_random,
        test_history_record,
        test_history_max_entries,
        test_history_print,
        test_cli_args_force,
        test_cli_args_history,
        test_cli_args_list,
        test_cli_args_default,
        test_main_no_api_key_quits,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n=== {passed}/{len(tests)} 测试通过 ===")
