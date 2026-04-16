import sys, os
is_frozen = getattr(sys, 'frozen', False)
if is_frozen:
    base_dir = sys._MEIPASS
    exe_dir = os.path.dirname(sys.executable)
    print(f"sys._MEIPASS = {base_dir}")
    print(f"sys.executable = {sys.executable}")
    main_script = os.path.join(base_dir, '数据管理.py')
    print(f"main_script = {main_script}")
    print(f"exists = {os.path.exists(main_script)}")
    files = [f for f in os.listdir(base_dir) if f.endswith('.py')]
    print(f".py files: {files}")
    # Also check exe dir
    alt = os.path.join(exe_dir, '数据管理.py')
    print(f"exe_dir path = {alt}, exists = {os.path.exists(alt)}")
else:
    print("NOT frozen - need to run from exe")
