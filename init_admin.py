# init_admin.py - 初始化管理员账号
"""
首次部署时运行此脚本，创建管理员账号。
用法: python init_admin.py <手机号> <密码>

示例: python init_admin.py 13800138000 admin123
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from billing.database import execute_query, fetch_one


def init_admin(phone: str, password: str):
    """创建管理员账号"""
    import secrets
    import hashlib

    # 检查是否已存在
    existing = fetch_one("SELECT id, role FROM users WHERE phone = ?", (phone,))
    if existing:
        if existing['role'] == 'admin':
            print(f"[OK] 该手机号 {phone} 已是管理员账号")
        else:
            execute_query("UPDATE users SET role = 'admin' WHERE id = ?", (existing['id'],))
            print(f"[OK] 已将 {phone} 升级为管理员")
        return

    # 创建新管理员
    salt = secrets.token_hex(16)
    pw_hash = hashlib.sha256((password + salt).encode()).hexdigest()

    execute_query(
        """INSERT INTO users (phone, password_hash, salt, role, free_quota, paid_quota)
           VALUES (?, ?, ?, 'admin', 9999, 9999)""",
        (phone, pw_hash, salt)
    )
    print(f"[OK] 管理员账号创建成功！")
    print(f"     手机号: {phone}")
    print(f"     密码: {password}")
    print(f"     免费次数: 9999")
    print(f"     付费次数: 9999")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python init_admin.py <手机号> <密码>")
        print("示例: python init_admin.py 13800138000 admin123")
        sys.exit(1)

    init_admin(sys.argv[1], sys.argv[2])
