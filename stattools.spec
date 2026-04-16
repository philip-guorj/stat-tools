# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_all

datas = [('D:\\stat-tools\\数据管理.py', '.'), ('D:\\stat-tools\\pages', 'pages'), ('D:\\stat-tools\\utils', 'utils'), ('D:\\stat-tools\\modules', 'modules'), ('D:\\stat-tools\\data', 'data'), ('D:\\stat-tools\\.streamlit', '.streamlit')]
binaries = []
hiddenimports = ['streamlit.web.cli', 'streamlit.runtime.scriptrunner.magic_funcs', 'streamlit.runtime.legacy_caching.hashing', 'streamlit.elements.lib.dict_utils', 'winreg', 'threading', 'concurrent.futures', 'seaborn']
datas += collect_data_files('PIL')
datas += collect_data_files('altair')
datas += collect_data_files('kaleido')
tmp_ret = collect_all('streamlit')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('plotly')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pandas')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('numpy')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('scipy')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('matplotlib')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('statsmodels')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('sklearn')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['stattools_launcher.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['D:\\stat-tools\\build\\hook_env\\_pyi_utf8_hook.py'],
    excludes=['IPython', 'jupyter', 'notebook', 'pytest', 'tkinter', 'xmlrpc', 'pygments', 'sphinx', 'docutils', 'setuptools', 'pip', 'wheel'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='StatTools',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='StatTools',
)
