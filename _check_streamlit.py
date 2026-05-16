import streamlit
print('streamlit', streamlit.__version__)

import py_compile
try:
    py_compile.compile('数据管理.py', doraise=True)
    print('数据管理.py syntax OK')
except Exception as e:
    print('语法错误:', e)
