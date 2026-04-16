"""StatTools 打包构建脚本 - 简化版"""
import subprocess
import sys
import os
import time
import shutil

def run_build():
    # 切换到脚本所在目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    # 1. 清理旧的 dist 目录
    dist_dir = os.path.join(script_dir, 'dist')
    if os.path.exists(dist_dir):
        print('[清理] 删除旧的 dist 目录...')
        shutil.rmtree(dist_dir)

    build_dir = os.path.join(script_dir, 'build')
    if os.path.exists(build_dir):
        print('[清理] 删除旧的 build 目录...')
        shutil.rmtree(build_dir)

    # 2. 验证关键文件
    required_files = ['stattools_launcher.py', '数据管理.py', 'stattools.spec']
    for f in required_files:
        if not os.path.exists(f):
            print(f'[错误] 缺少必要文件: {f}')
            return False
        print(f'[OK] {f} 存在')

    # 3. 运行 PyInstaller
    print('\n' + '='*50)
    print('[开始] 运行 PyInstaller 打包...')
    print('='*50 + '\n')

    t0 = time.time()
    result = subprocess.run(
        [sys.executable, '-m', 'PyInstaller', '--clean', '--noconfirm', 'stattools.spec'],
        cwd=script_dir,
    )
    elapsed = time.time() - t0

    print('\n' + '='*50)
    print(f'[完成] 耗时 {elapsed:.0f} 秒, 返回码 {result.returncode}')
    print('='*50)

    # 4. 验证结果
    exe_path = os.path.join(script_dir, 'dist', 'StatTools', 'StatTools.exe')
    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / 1024 / 1024
        print(f'\n[成功] 打包完成!')
        print(f'       路径: {exe_path}')
        print(f'       主程序大小: {size_mb:.1f} MB')
        print(f'\n完整输出目录: {os.path.join(script_dir, "dist", "StatTools")}')

        # 计算总大小
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(os.path.join(script_dir, 'dist', 'StatTools')):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                total_size += os.path.getsize(fp)
        print(f'       完整目录大小: {total_size/1024/1024:.1f} MB')
        return True
    else:
        print(f'\n[错误] exe 未生成，请检查上方错误日志')
        return False

if __name__ == '__main__':
    success = run_build()
    if not success:
        input('\n按回车键退出...')
    else:
        input('\n按回车键退出...')
