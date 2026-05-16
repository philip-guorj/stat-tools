"""
StatTools v1.5 启动脚本
作者: 老非 | 邮箱: philip.guo@foxmail.com
"""
import sys
import os
import tempfile
import shutil

# 修复 importlib.metadata 问题
import importlib.metadata
_original_version = importlib.metadata.version
def _fixed_version(name):
    try:
        return _original_version(name)
    except importlib.metadata.PackageNotFoundError:
        return "1.0.0"
importlib.metadata.version = _fixed_version

# 确定应用路径
if getattr(sys, 'frozen', False):
    bundle_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
else:
    bundle_dir = os.path.dirname(os.path.abspath(__file__))

# 创建临时目录
temp_dir = tempfile.mkdtemp(prefix="StatTools_")

# 复制必要文件
src = os.path.join(bundle_dir, "数据管理.py")
if os.path.exists(src):
    shutil.copy2(src, temp_dir)

for d in ["pages", "utils", "modules", "data"]:
    src = os.path.join(bundle_dir, d)
    if os.path.exists(src):
        shutil.copytree(src, os.path.join(temp_dir, d), dirs_exist_ok=True)

os.chdir(temp_dir)

print("=" * 50)
print("  StatTools v1.5 - 统计分析工具")
print("  作者: 老非 | 邮箱: philip.guo@foxmail.com")
print("=" * 50)
print(f"\n工作目录: {temp_dir}")
print("\n正在启动 Streamlit 服务...")
print("浏览器将自动打开，请稍候...\n")

# 清理
import atexit
def cleanup():
    try:
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass
atexit.register(cleanup)

# 直接用streamlit CLI
sys.argv = ["streamlit", "run", "数据管理.py", "--server.headless", "false"]
from streamlit.web.cli import main
main()
