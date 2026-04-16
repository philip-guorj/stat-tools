# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['stattools_launcher_debug.py'],
    pathex=[],
    binaries=[],
    datas=[('数据管理.py', '.'), ('pages', 'pages'), ('utils', 'utils'), ('modules', 'modules'), ('data', 'data')],
    hiddenimports=['streamlit.web.cli', 'streamlit.runtime.scriptrunner.magic_funcs'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='StatTools_Debug',
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
    name='StatTools_Debug',
)
