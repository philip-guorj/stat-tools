# billing/redeem.py - 兑换码模块
"""
兑换码的生成、核销、批量生成。
"""

import secrets
from datetime import datetime

from billing.database import execute_query, fetch_one, fetch_all


def generate_codes(admin_id: int, count: int, amount: int) -> list[str]:
    """
    批量生成兑换码。
    
    参数：
    - admin_id: 管理员用户 ID
    - count: 生成数量
    - amount: 每个兑换码对应的次数（非金额）
    
    返回：生成的兑换码列表
    """
    batch_id = secrets.token_hex(8)
    codes = []

    for _ in range(count):
        code = _generate_unique_code()
        execute_query(
            """INSERT INTO redeem_codes (code, amount, status, created_by, batch_id)
               VALUES (?, ?, 'unused', ?, ?)""",
            (code, amount, admin_id, batch_id)
        )
        codes.append(code)

    return codes


def _generate_unique_code() -> str:
    """生成唯一的兑换码（8位大写字母+数字，易读）"""
    import string
    # 去掉容易混淆的字符
    chars = string.ascii_uppercase.replace('O', '').replace('I', '') + string.digits.replace('0', '').replace('1', '')
    
    for _ in range(100):  # 最多重试100次
        code = ''.join(secrets.choice(chars) for _ in range(8))
        # 检查唯一性
        existing = fetch_one("SELECT id FROM redeem_codes WHERE code = ?", (code,))
        if not existing:
            return code
    
    # 极端情况：用长随机串
    return secrets.token_hex(4).upper()


def redeem_code(user_id: int, code: str) -> tuple[bool, str]:
    """
    核销兑换码，成功时增加用户 paid_quota。
    
    返回：(成功?, 消息)
    """
    code = code.strip().upper()

    if not code:
        return False, "请输入兑换码"

    row = fetch_one(
        "SELECT * FROM redeem_codes WHERE code = ?",
        (code,)
    )

    if not row:
        return False, "兑换码不存在"

    if row['status'] == 'used':
        return False, "该兑换码已被使用"

    amount = row['amount']

    try:
        # 核销兑换码
        execute_query(
            """UPDATE redeem_codes
               SET status = 'used', used_by = ?, used_at = datetime('now','localtime')
               WHERE id = ?""",
            (user_id, row['id'])
        )

        # 增加用户付费次数
        execute_query(
            "UPDATE users SET paid_quota = paid_quota + ? WHERE id = ?",
            (amount, user_id)
        )

        # 更新 session_state
        import streamlit as st
        if 'current_user' in st.session_state:
            st.session_state['current_user']['paid_quota'] = (
                st.session_state['current_user'].get('paid_quota', 0) + amount
            )

        return True, f"充值成功！已增加 {amount} 次分析次数。"
    except Exception as e:
        return False, f"充值失败：{str(e)}"


def get_codes_by_batch(batch_id: str) -> list[dict]:
    """获取某批次的兑换码列表"""
    rows = fetch_all(
        "SELECT * FROM redeem_codes WHERE batch_id = ? ORDER BY id",
        (batch_id,)
    )
    return [dict(r) for r in rows]


def get_all_codes(status_filter: str = None, limit: int = 100) -> list[dict]:
    """
    获取兑换码列表。
    status_filter: None=全部, 'unused'=未使用, 'used'=已使用
    """
    if status_filter and status_filter != 'all':
        rows = fetch_all(
            """SELECT rc.*, u.phone as used_phone
               FROM redeem_codes rc
               LEFT JOIN users u ON rc.used_by = u.id
               WHERE rc.status = ?
               ORDER BY rc.created_at DESC
               LIMIT ?""",
            (status_filter, limit)
        )
    else:
        rows = fetch_all(
            """SELECT rc.*, u.phone as used_phone
               FROM redeem_codes rc
               LEFT JOIN users u ON rc.used_by = u.id
               ORDER BY rc.created_at DESC
               LIMIT ?""",
            (limit,)
        )
    return [dict(r) for r in rows]
