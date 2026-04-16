"""
StatTools Launcher - 带浏览器自动打开 + 错误日志
"""
import sys
import os
import threading
import time
import traceback
import io
import logging

ERROR_LOG = os.path.join(os.environ.get('TEMP', '.'), 'stattools_error.log')


def log(msg):
    try:
        with open(ERROR_LOG, 'a', encoding='utf-8') as f:
            f.write(f'[{time.strftime("%H:%M:%S")}] {msg}\n')
    except Exception:
        pass


def print_banner():
    """打印启动信息（必须在 suppress_noise 之前调用）"""
    sys.stdout.write('\n')
    sys.stdout.write('  ╔══════════════════════════════════════════════╗\n')
    sys.stdout.write('  ║          StatTools  农业试验统计工具          ║\n')
    sys.stdout.write('  ╠══════════════════════════════════════════════╣\n')
    sys.stdout.write('  ║                                              ║\n')
    sys.stdout.write('  ║   浏览器将自动打开，如未打开请手动访问：       ║\n')
    sys.stdout.write('  ║                                              ║\n')
    sys.stdout.write('  ║       http://localhost:8501                  ║\n')
    sys.stdout.write('  ║                                              ║\n')
    sys.stdout.write('  ║   关闭此窗口将停止程序运行                    ║\n')
    sys.stdout.write('  ║                                              ║\n')
    sys.stdout.write('  ╠══════════════════════════════════════════════╣\n')
    sys.stdout.write('  ║   欢迎试用并提出改进意见                       ║\n')
    sys.stdout.write('  ║   开发者：老非                                ║\n')
    sys.stdout.write('  ║   意见反馈：philip.guo@foxmail.com             ║\n')
    sys.stdout.write('  ╚══════════════════════════════════════════════╝\n')
    sys.stdout.write('\n')
    sys.stdout.write('  正在启动，请稍候...\n')
    sys.stdout.write('\n')
    sys.stdout.flush()


def suppress_noise():
    """抑制 streamlit/click 等库的噪音输出。

    策略：monkey-patch click.echo/click.secho 来过滤控制台输出，
    同时将 stderr 重定向到安全的 devnull。
    不直接替换 sys.stdout/sys.__stdout__，因为 click 和 PyInstaller
    底层会通过 __stdout__ 做检测，替换会导致 "I/O operation on closed file"。
    """
    # 1. 降低 logging 到 ERROR
    logging.basicConfig(level=logging.ERROR)
    try:
        for name in list(logging.root.manager.loggerDict.keys()):
            logging.getLogger(name).setLevel(logging.ERROR)
    except Exception:
        pass

    # 2. stderr 重定向到 devnull（安全的空设备，不会触发 closed file 错误）
    sys.stderr = io.StringIO()

    # 3. monkey-patch click.echo / click.secho 过滤噪音
    try:
        import click

        _BLOCK_KEYWORDS = [
            'You can now view',
            'Local URL',
            'Network URL',
            'External URL',
            '  URL:',
            'To stop',
            'Usage stats',
        ]

        _original_echo = click.echo
        _original_secho = click.secho

        def _safe_echo(message=None, **kwargs):
            if message and any(kw in str(message) for kw in _BLOCK_KEYWORDS):
                return  # 丢弃噪音消息
            try:
                _original_echo(message, **kwargs)
            except (ValueError, OSError):
                pass  # 避免 closed file 错误

        def _safe_secho(message=None, **kwargs):
            if message and any(kw in str(message) for kw in _BLOCK_KEYWORDS):
                return
            try:
                _original_secho(message, **kwargs)
            except (ValueError, OSError):
                pass

        click.echo = _safe_echo
        click.secho = _safe_secho
    except ImportError:
        pass


def open_browser_when_ready(port=8501, delay=3):
    """等待服务器启动后打开浏览器"""
    time.sleep(delay)
    url = f'http://localhost:{port}'
    try:
        import urllib.request
        for _ in range(30):
            try:
                urllib.request.urlopen(url, timeout=1)
                break
            except:
                time.sleep(1)
    except Exception:
        pass
    try:
        os.startfile(url)
    except Exception:
        try:
            import subprocess
            subprocess.Popen(['cmd', '/c', 'start', '', url], shell=False,
                           creationflags=0x08000000)
        except Exception:
            pass


def main():
    print_banner()
    log('Launcher starting...')

    # banner 打完后才抑制噪音
    suppress_noise()

    is_frozen = getattr(sys, 'frozen', False)

    if is_frozen:
        base_dir = sys._MEIPASS
        exe_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        exe_dir = base_dir

    log(f'is_frozen={is_frozen}, _MEIPASS={base_dir}, exe_dir={exe_dir}')

    # UTF-8 环境变量
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    os.environ['PYTHONUTF8'] = '1'

    script_name = '数据管理.py'
    # COLLECT/ONEDIR 模式：datas 在 _MEIPASS/_internal/
    main_script = os.path.join(base_dir, script_name)
    if not os.path.exists(main_script):
        main_script = os.path.join(exe_dir, script_name)
    if not os.path.exists(main_script):
        main_script = os.path.join(exe_dir, '_internal', script_name)

    log(f'main_script = {main_script}, exists = {os.path.exists(main_script)}')

    if not os.path.exists(main_script):
        log(f'FATAL: 找不到 {script_name}')
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, f'找不到主程序文件:\n{main_script}', 'StatTools', 0x10)
        except Exception:
            pass
        sys.exit(1)

    # 配置目录
    tmp_dir = os.environ.get('TEMP', os.path.expanduser('~'))
    st_config_dir = os.path.join(tmp_dir, 'stattools_config')
    os.makedirs(st_config_dir, exist_ok=True)
    os.environ['STREAMLIT_CONFIG_DIR'] = st_config_dir
    os.environ['STREAMLIT_SERVER_HEADLESS'] = 'true'
    os.environ['STREAMLIT_BROWSER_GATHER_USAGE_STATS'] = 'false'

    os.chdir(exe_dir)
    if base_dir not in sys.path:
        sys.path.insert(0, base_dir)

    log('Launching streamlit...')
    t = threading.Thread(target=open_browser_when_ready, args=(8501, 3), daemon=True)
    t.start()

    sys.argv = [
        'streamlit', 'run', main_script,
        '--global.developmentMode=false',
        '--server.headless=true',
        '--browser.gatherUsageStats=false',
        '--server.port=8501',
    ]

    try:
        import streamlit.web.cli as stcli
        log('streamlit.web.cli imported OK')
        stcli.main()
    except SystemExit:
        raise
    except Exception as e:
        log(f'FATAL ERROR: {type(e).__name__}: {e}')
        log(traceback.format_exc())
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, f'{type(e).__name__}: {e}\n\n详见 {ERROR_LOG}', 'StatTools 错误', 0x10)
        except Exception:
            pass
        sys.exit(1)

if __name__ == '__main__':
    main()
