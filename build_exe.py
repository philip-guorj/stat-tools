"""
打包构建脚本 - 生成 StatTools1.0.exe
"""
import subprocess, sys, os, shutil, time

# 1. 生成 UTF-8 runtime hook（避免 BOM 和编码问题）
hook_content = """import sys, os
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['PYTHONUTF8'] = '1'
"""

hook_dir = os.path.join(os.path.dirname(__file__), 'build', 'hook_env')
os.makedirs(hook_dir, exist_ok=True)
hook_path = os.path.join(hook_dir, '_pyi_utf8_hook.py')

with open(hook_path, 'w', encoding='utf-8') as f:
    f.write(hook_content)
print(f'[OK] UTF-8 hook 已写入: {hook_path}')

# 2. 写入 spec 文件
spec_content = '''# -*- mode: python ; coding: utf-8 -*-
import sys, os
from PyInstaller.utils.hooks import collect_data_files, collect_all

block_cipher = None

# 收集数据文件
datas = []
for pkg in ['streamlit', 'plotly', 'numpy', 'pandas', 'scipy', 'scikit_learn',
            'matplotlib', 'seaborn', 'statsmodels', 'sklearn', 'PIL', 'pillow',
            'altair', 'vega_datasets', 'tenacity', 'blinker', 'git', 'hydralit',
            'protobuf', 'htmlmin', 'watchdog', 'tzlocal', 'dateutil']:
    try:
        datas += collect_data_files(pkg)
    except Exception:
        pass

# 应用数据文件
app_files = []
for root, dirs, files in os.walk('pages'):
    for file in files:
        if file.endswith(('.py', '.csv', '.json')):
            app_files.append((os.path.join(root, file), 'pages'))
for extra in ['utils', 'modules', 'data', '.streamlit', 'stattools_launcher.py', '数据分析.py']:
    if os.path.isdir(extra):
        for root, dirs, files in os.walk(extra):
            for file in files:
                if file.endswith(('.py', '.csv', '.json', '.toml')):
                    app_files.append((os.path.join(root, file), extra))
    elif os.path.isfile(extra):
        app_files.append((extra, os.path.dirname(extra) or '.'))

a = Analysis(
    ['stattools_launcher.py'],
    pathex=[os.getcwd()],
    binaries=[],
    datas=app_files + datas,
    hiddenimports=[
        'streamlit.web.cli', 'streamlit.runtime.scriptrunner.magic_funcs',
        'streamlit.runtime.legacy_caching.hashing', 'streamlit.elements.lib.dict_utils',
        'sklearn.utils._cython_blas', 'sklearn.neighbors._typedefs', 'sklearn.neighbors._quad_tree',
        'sklearn.tree._utils', 'sklearn.cluster._hierarchical_fast', 'sklearn.cluster._k_means_fast',
        'sklearn.ensemble._gradient_boosting', 'sklearn.tree._criterion', 'sklearn.tree._splitter',
        'sklearn.tree._partitioner', 'sklearn.neighbors._ball_tree', 'sklearn.neighbors._kd_tree',
        'winreg', 'threading', 'concurrent.futures',
    ],
    hookspath=['build/hook_env'],
    runtime_hooks=['build/hook_env/_pyi_utf8_hook.py'],
    excludes=['pytest', 'jedi', 'parso', 'IPython'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
    python=None,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='StatTools1.0',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='StatTools1.0',
)
'''

spec_path = os.path.join(os.path.dirname(__file__), 'stattools.spec')
with open(spec_path, 'w', encoding='utf-8') as f:
    f.write(spec_content)
print(f'[OK] spec 已写入: {spec_path}')

# 3. 运行 pyinstaller
print('\n[开始] 运行 PyInstaller...\n')
t0 = time.time()
    result = subprocess.run(
        [sys.executable, '-m', 'PyInstaller', '--clean', 'stattools.spec'],
    capture_output=False,
    cwd=os.path.dirname(__file__) or '.',
)
print(f'\n[完成] 耗时 {time.time()-t0:.0f}s, 返回码 {result.returncode}')

# 4. 收集输出
dist_dir = os.path.join(os.path.dirname(__file__), 'dist', 'StatTools1.0')
exe_path = os.path.join(dist_dir, 'StatTools1.0.exe')
if os.path.exists(exe_path):
    size_mb = os.path.getsize(exe_path) / 1024 / 1024
    print(f'\n[OK] 打包成功: {exe_path} ({size_mb:.1f} MB)')
else:
    print(f'\n[ERROR] exe 未找到: {exe_path}')
