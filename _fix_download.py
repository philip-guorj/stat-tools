import re

with open('pages/07_试验设计.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
guard_count = 0

for line in lines:
    stripped = line.rstrip('\r\n')
    
    # 8-space indent: '        st.download_button('
    if stripped.startswith('        st.download_button('):
        indent = '        '
        guard_count += 1
        new_lines.append(indent + 'if can_download():\n')
        new_lines.append(indent + '    ' + stripped.strip() + '\n')
        new_lines.append(indent + 'else:\n')
        new_lines.append(indent + '    st.warning("分析次数已用完，充值后可下载结果。请前往侧边栏充值中心。")\n')
        new_lines.append('\n')
    # 12-space indent: '            st.download_button('
    elif stripped.startswith('            st.download_button('):
        indent = '            '
        guard_count += 1
        new_lines.append(indent + 'if can_download():\n')
        new_lines.append(indent + '    ' + stripped.strip() + '\n')
        new_lines.append(indent + 'else:\n')
        new_lines.append(indent + '    st.warning("分析次数已用完，充值后可下载结果。请前往侧边栏充值中心。")\n')
        new_lines.append('\n')
    else:
        new_lines.append(line)

with open('pages/07_试验设计.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f"Done. Added {guard_count} can_download() guards")
