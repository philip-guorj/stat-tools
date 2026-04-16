"""
StatTools Launcher - 调试版（带错误日志）
"""
import sys
import os
import io
import traceback

# 日志文件
LOG_FILE = os.path.join(os.environ.get('TEMP', '.'), 'stattools_debug.log')

def log(msg):
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(f"[{os.popen('time /t').read().strip()}] {msg}\n")
    print(msg)

try:
    log("=== StatTools Launcher 启动 ===")
    log(f"Python: {sys.version}")
    log(f"Executable: {sys.executable}")
    log(f"Frozen: {getattr(sys, 'frozen', False)}")
    
    is_frozen = getattr(sys, 'frozen', False)
    
    if is_frozen:
        base_dir = sys._MEIPASS
        work_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        work_dir = base_dir
    
    log(f"Base dir: {base_dir}")
    log(f"Work dir: {work_dir}")
    
    # UTF-8 修复
    if sys.stdout is not None and hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    if sys.stderr is not None and hasattr(sys.stderr, 'buffer'):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    os.environ['PYTHONUTF8'] = '1'
    
    script_name = '数据管理.py'
    main_script = os.path.join(base_dir, script_name)
    
    log(f"Main script: {main_script}")
    log(f"Script exists: {os.path.exists(main_script)}")
    
    if not os.path.exists(main_script):
        log(f"[ERROR] {main_script} not found")
        input('按回车退出...')
        sys.exit(1)
    
    # 创建临时配置目录
    tmp_dir = os.environ.get('TEMP', '.')
    st_config_dir = os.path.join(tmp_dir, 'stattools_config')
    os.makedirs(st_config_dir, exist_ok=True)
    os.environ['STREAMLIT_CONFIG_DIR'] = st_config_dir
    os.environ['STREAMLIT_SERVER_HEADLESS'] = 'true'
    os.environ['STREAMLIT_BROWSER_GATHER_USAGE_STATS'] = 'false'
    
    log(f"Config dir: {st_config_dir}")
    
    os.chdir(work_dir)
    sys.path.insert(0, base_dir)
    
    log("开始启动 Streamlit...")
    
    sys.argv = [
        'streamlit', 'run', main_script,
        '--global.developmentMode=false',
        '--server.headless=true',
        '--browser.gatherUsageStats=false',
        '--server.port=8501',
    ]
    
    log(f"sys.argv: {sys.argv}")
    
    import streamlit.web.cli as stcli
    log("调用 stcli.main()...")
    stcli.main()
    
except Exception as e:
    log(f"[FATAL ERROR] {type(e).__name__}: {e}")
    log(traceback.format_exc())
    input('按回车退出...')
