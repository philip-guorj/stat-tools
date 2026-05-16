# 生成桌面启动脚本（.bat 格式，含 ngrok 外部访问）
import os
import locale

lines = [
    '@echo off',
    'cd /d D:\\stat-tools',
    'title StatTools Launcher',
    '',
    'echo ========================================',
    'echo   StatTools 农业试验统计工具',
    'echo ========================================',
    'echo.',
    '',
    'rem 清理残留进程',
    'taskkill /F /IM python.exe > nul 2>&1',
    'taskkill /F /IM ngrok.exe > nul 2>&1',
    'timeout /t 1 /nobreak > nul',
    '',
    'rem 启动 Streamlit（新窗口）',
    'start "Streamlit" cmd /k "chcp 65001 > nul && cd /d D:\\stat-tools && python -m streamlit run 数据管理.py --server.port=8501"',
    '',
    'rem 等待端口 8501 就绪',
    'echo 等待 Streamlit 启动...',
    'set /a COUNT=0',
    '',
    ':WAIT_PORT',
    'netstat -ano 2>nul | findstr ":8501 " >nul 2>&1',
    'if %ERRORLEVEL%==0 goto PORT_READY',
    'set /a COUNT+=1',
    'if %COUNT% gtr 30 goto WAIT_TIMEOUT',
    'timeout /t 1 /nobreak > nul',
    'goto WAIT_PORT',
    '',
    ':WAIT_TIMEOUT',
    'echo [失败] Streamlit 启动超时！',
    'echo 请检查 Streamlit 窗口中是否有错误信息',
    'pause',
    'exit 1',
    '',
    ':PORT_READY',
    'echo [OK] Streamlit 已启动 (http://localhost:8501)',
    'echo.',
    '',
    'rem 启动 ngrok 隧道（新窗口）',
    'if not exist "C:\\Users\\phili\\ngrok.exe" goto NO_NGROK',
    'start "ngrok" cmd /k "chcp 65001 > nul && cd /d D:\\stat-tools && C:\\Users\\phili\\ngrok.exe http 8501"',
    'echo [OK] ngrok 已启动，外部访问地址请查看 ngrok 窗口',
    'goto END',
    '',
    ':NO_NGROK',
    'echo [提示] 未找到 ngrok.exe',
    'echo 当前仅本地访问可用',
    'goto END',
    '',
    ':END',
    'echo.',
    'echo 关闭以上窗口即可停止服务',
    'echo.',
    'pause',
]

target = r'C:\Users\phili\Desktop\StatTools启动.bat'
# 用系统默认编码（GBK）写入，cmd 原生支持，无 BOM 问题
enc = locale.getpreferredencoding()
with open(target, 'w', encoding=enc) as f:
    f.write('\n'.join(lines))

print(f'Written to {target} ({enc})')
