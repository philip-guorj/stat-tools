"""StatTools 打包构建脚本 v2 - 优化版"""
import subprocess, sys, os, time, shutil

script_dir = os.path.dirname(os.path.abspath(__file__))

# 1. 写入 UTF-8 runtime hook
hook_dir = os.path.join(script_dir, 'build', 'hook_env')
os.makedirs(hook_dir, exist_ok=True)
hook_content = (
    "import sys,os,io\n"
    "if sys.stdout is not None and hasattr(sys.stdout,'buffer'):\n"
    "    sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')\n"
    "if sys.stderr is not None and hasattr(sys.stderr,'buffer'):\n"
    "    sys.stderr=io.TextIOWrapper(sys.stderr.buffer,encoding='utf-8',errors='replace')\n"
    "os.environ['PYTHONIOENCODING']='utf-8'\n"
    "os.environ['PYTHONUTF8']='1'\n"
    "_meipass=getattr(sys,'_MEIPASS',None)\n"
    "if _meipass and _meipass not in sys.path:\n"
    "    sys.path.insert(0,_meipass)\n"
)
hook_path = os.path.join(hook_dir, '_pyi_utf8_hook.py')
with open(hook_path, 'w', encoding='utf-8') as f:
    f.write(hook_content)
print(f'[OK] UTF-8 hook: {hook_path}')

# 2. 清理旧的 dist
dist_dir = os.path.join(script_dir, 'dist')
if os.path.exists(dist_dir):
    shutil.rmtree(dist_dir)
print('[清理] dist 目录已删除')

# 3. 构建 PyInstaller 命令
cmd = [
    sys.executable, '-m', 'PyInstaller',
    '--clean',
    '--noconfirm',
    '--onedir',
    '--console',
    '--name', 'StatTools',
    # 入口脚本
    'stattools_launcher.py',
    # 应用数据文件
    '--add-data', f'{script_dir}\\数据管理.py;.',
    '--add-data', f'{script_dir}\\pages;pages',
    '--add-data', f'{script_dir}\\utils;utils',
    '--add-data', f'{script_dir}\\modules;modules',
    '--add-data', f'{script_dir}\\data;data',
    '--add-data', f'{script_dir}\\.streamlit;.streamlit',
    # 强制收集全部文件和元数据（核心依赖）
    '--collect-all', 'streamlit',
    '--collect-all', 'plotly',
    '--collect-all', 'pandas',
    '--collect-all', 'numpy',
    '--collect-all', 'scipy',
    '--collect-all', 'matplotlib',
    '--collect-all', 'statsmodels',
    '--collect-all', 'sklearn',
    # 不需要 collect-all 的依赖，仅收集数据文件即可
    '--collect-data', 'PIL',
    '--collect-data', 'altair',
    '--collect-data', 'kaleido',
    # hidden imports
    '--hidden-import', 'streamlit.web.cli',
    '--hidden-import', 'streamlit.runtime.scriptrunner.magic_funcs',
    '--hidden-import', 'streamlit.runtime.legacy_caching.hashing',
    '--hidden-import', 'streamlit.elements.lib.dict_utils',
    '--hidden-import', 'winreg',
    '--hidden-import', 'threading',
    '--hidden-import', 'concurrent.futures',
    '--hidden-import', 'seaborn',
    # 排除不需要的大型包
    '--exclude-module', 'IPython',
    '--exclude-module', 'jupyter',
    '--exclude-module', 'notebook',
    '--exclude-module', 'pytest',

    '--exclude-module', 'tkinter',
    '--exclude-module', 'xmlrpc',
    '--exclude-module', 'pygments',
    '--exclude-module', 'sphinx',
    '--exclude-module', 'docutils',
    '--exclude-module', 'setuptools',
    '--exclude-module', 'pip',
    '--exclude-module', 'wheel',
    '--runtime-hook', hook_path,
]

# 4. 运行 PyInstaller
print('\n[开始] PyInstaller 打包（优化版）...\n')
t0 = time.time()
result = subprocess.run(cmd, cwd=script_dir)
elapsed = time.time() - t0
print(f'\n[完成] 耗时 {elapsed:.0f}s, 返回码 {result.returncode}')

# 5. 验证
exe_path = os.path.join(script_dir, 'dist', 'StatTools', 'StatTools.exe')
if os.path.exists(exe_path):
    size_mb = os.path.getsize(exe_path) / 1024 / 1024
    total = sum(os.path.getsize(os.path.join(dp, f)) for dp, dn, fn in os.walk(os.path.join(script_dir, 'dist', 'StatTools')) for f in fn)
    print(f'\n[OK] 打包成功: {exe_path}')
    print(f'     EXE 大小: {size_mb:.1f} MB')
    print(f'     目录总大小: {total/1024/1024:.1f} MB')
    print(f'\n[提示] 可运行 python _clean_package.py 进一步减小体积')
else:
    print(f'\n[ERROR] exe 未找到，请检查上方日志')
