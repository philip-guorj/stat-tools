"""清理 PyInstaller 打包产物中的冗余文件，减小体积。
v2 - 增强版：自动检测打包输出路径，清理更多冗余内容。

⚠️ 重要：只清理 site-packages 目录下的文件，不碰应用源码。
运行后验证 EXE 是否正常运行。
"""
import os
import shutil
from pathlib import Path

# 自动检测打包输出路径
_possible_paths = [
    Path(r"D:\stat-tools\dist\StatTools\_internal"),
    Path(r"D:\stat-tools\StatTools_Package\_internal"),
]
PKG = None
for p in _possible_paths:
    if p.exists():
        PKG = p
        break

if PKG is None:
    print("[错误] 未找到打包输出目录，请确认已完成打包。")
    print(f"  查找路径: {_possible_paths}")
    exit(1)

print(f"[信息] 清理目标: {PKG}")


def rmtree(path: Path, desc=""):
    if path.exists():
        shutil.rmtree(path)
        print(f"  [DEL] {path.relative_to(PKG)}")

def rmfile(path: Path):
    if not path or not isinstance(path, Path):
        return
    if path.exists():
        size_kb = path.stat().st_size // 1024
        path.unlink()
        print(f"  [DEL] {path.relative_to(PKG)} ({size_kb} KB)")

def is_app_source(path: Path) -> bool:
    """判断是否为应用源码（而非第三方库）"""
    rel = str(path.relative_to(PKG))
    parts = Path(rel).parts
    if parts[0] in ("pages", "utils", "modules", "data", ".streamlit"):
        return True
    return True  # 也跳过根目录文件（如 数据管理.py）


def clean():
    print("=== StatTools 打包后清理 v2 ===\n")

    # ── 1. .py 源码（仅 site-packages，保留应用源码）──────────────────
    print("[1] 删除 site-packages 下的 .py 源码文件...")
    count_py = 0
    for f in PKG.rglob("*.py"):
        if "__pycache__" in str(f) or ".pytest_cache" in str(f):
            continue
        rel = str(f.relative_to(PKG))
        # 保留根目录文件（stattools_launcher.py、数据管理.py 等）
        parts = rel.replace("\\", "/").split("/")
        if len(parts) <= 1:
            continue
        # 保留应用源码目录
        if is_app_source(f):
            continue
        rmfile(f)
        count_py += 1
    print(f"  → 删除 {count_py} 个 .py 源码文件\n")

    # ── 2. .cc C++ 源码（已编译进 .pyd/.dll）──────────────────────────
    print("[2] 删除 .cc C++ 源码...")
    count_cc = 0
    for f in PKG.rglob("*.cc"):
        rmfile(f)
        count_cc += 1
    print(f"  → 删除 {count_cc} 个 .cc 文件\n")

    # ── 3. Cython 源文件（.pyx .pxd .pxi）──────────────────────────────
    print("[3] 删除 Cython 源文件...")
    count_cy = 0
    for ext in ("*.pyx", "*.pxd", "*.pxi"):
        for f in PKG.rglob(ext):
            rmfile(f)
            count_cy += 1
    print(f"  → 删除 {count_cy} 个 Cython 源文件\n")

    # ── 4. pyarrow 冗余目录────────────────────────────────────────────
    print("[4] 删除 pyarrow 冗余目录...")
    for sub in ("src", "includes", "tests"):
        rmtree(PKG / "pyarrow" / sub)

    # ── 5. matplotlib 冗余文件──────────────────────────────────────────
    print("[5] 删除 matplotlib 冗余内容...")
    for sub in ("afm", "pdfcorefonts"):
        rmtree(PKG / "matplotlib" / "mpl-data" / "fonts" / sub)
    # matplotlib tests/doc 示例
    rmtree(PKG / "matplotlib" / "tests")
    rmtree(PKG / "matplotlib" / "mpl-data" / "sample_data")

    # ── 6. scipy 冗余模块───────────────────────────────────────────────
    print("[6] 删除 scipy 冗余模块...")
    # 注意：scipy.fftpack 被 statsmodels 依赖，不能删除
    rmtree(PKG / "scipy" / "tests")
    rmtree(PKG / "scipy" / "_lib" / "tests")

    # ── 7. numpy 冗余模块───────────────────────────────────────────────
    print("[7] 删除 numpy 冗余模块...")
    rmtree(PKG / "numpy" / "distutils")
    rmtree(PKG / "numpy" / "f2py")
    rmtree(PKG / "numpy" / "tests")
    rmtree(PKG / "numpy" / "typing" / "tests")
    rmtree(PKG / "numpy" / "core" / "tests")
    rmtree(PKG / "numpy" / "linalg" / "tests")
    rmtree(PKG / "numpy" / "fft" / "tests")
    rmtree(PKG / "numpy" / "lib" / "tests")
    rmtree(PKG / "numpy" / "random" / "tests")
    rmtree(PKG / "numpy" / "polynomial" / "tests")
    rmtree(PKG / "numpy" / "ma" / "tests")

    # ── 8. pandas 冗余文件──────────────────────────────────────────────
    print("[8] 删除 pandas 冗余文件...")
    rmtree(PKG / "pandas" / "tests")
    rmfile(PKG / "pandas" / "conftest.py")

    # ── 9. sklearn 冗余文件─────────────────────────────────────────────
    print("[9] 删除 sklearn 冗余文件...")
    rmtree(PKG / "sklearn" / "tests")
    rmfile(PKG / "sklearn" / "conftest.py")
    rmtree(PKG / "sklearn" / "utils" / "tests")
    # 注意：sklearn/utils/_repr_html 不能删，sklearn 运行时会读取 estimator.css

    # ── 10. statsmodels 冗余文件────────────────────────────────────────
    print("[10] 删除 statsmodels 冗余文件...")
    rmtree(PKG / "statsmodels" / "tests")
    rmfile(PKG / "statsmodels" / "conftest.py")
    rmtree(PKG / "statsmodels" / "docs")

    # ── 11. plotly 冗余文件─────────────────────────────────────────────
    print("[11] 删除 plotly 冗余文件...")
    rmfile(PKG / "plotly" / "conftest.py")
    rmfile(PKG / "plotly" / "package_data" / "template.html" if (PKG / "plotly" / "package_data" / "template.html").exists() else "")

    # ── 12. streamlit 冗余文件──────────────────────────────────────────
    print("[12] 删除 streamlit 冗余文件...")
    rmtree(PKG / "streamlit" / "static" / "static")  # 重复目录
    # 保留 streamlit 静态资源（前端必需），不删除

    # ── 13. __pycache__ 目录────────────────────────────────────────────
    print("[13] 清理 __pycache__ 目录...")
    for d in sorted(PKG.rglob("__pycache__"), key=lambda p: len(str(p)), reverse=True):
        rmtree(d)

    # ── 14. .dist-info 目录 ──────────────────────────────────────────────
    # 注意：多个包（streamlit/plotly/altair等）启动时读取版本元数据
    # dist-info 总共仅几MB，删除收益极低但风险极高，跳过此步骤
    print("[14] 跳过 .dist-info 目录（保留全部，避免运行时元数据缺失）...\n")

    # ── 15. altair 冗余（datasets 示例数据）────────────────────────────
    print("[15] 删除 altair 冗余内容...")
    rmtree(PKG / "altair" / "datasets")

    # ── 统计 ──────────────────────────────────────────────────────────
    total = sum(f.stat().st_size for f in PKG.rglob("*") if f.is_file())
    print(f"\n=== 清理完成 ===")
    print(f"清理后: {total/1024**2:.1f} MB")
    print(f"\n[提示] 请运行 StatTools.exe 验证功能正常")

if __name__ == "__main__":
    clean()
