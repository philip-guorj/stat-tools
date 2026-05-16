# billing/admin.py - 管理后台逻辑
"""
用户管理、兑换码管理、系统设置、数据统计。
"""

from billing.database import execute_query, fetch_one, fetch_all


# ---- 系统设置 ----

def get_system_setting(key: str, default: str = '') -> str:
    """获取系统设置"""
    row = fetch_one("SELECT value FROM system_settings WHERE key = ?", (key,))
    return row['value'] if row else default


def set_system_setting(key: str, value: str):
    """修改系统设置"""
    execute_query(
        """INSERT INTO system_settings (key, value, updated_at)
           VALUES (?, ?, datetime('now','localtime'))
           ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = datetime('now','localtime')""",
        (key, value, value)
    )


# ---- 用户管理 ----

def get_all_users(limit: int = 100) -> list[dict]:
    """获取用户列表"""
    rows = fetch_all(
        """SELECT id, phone, nickname, organization, free_quota, paid_quota, role, status,
                  created_at, last_login
           FROM users ORDER BY created_at DESC LIMIT ?""",
        (limit,)
    )
    return [dict(r) for r in rows]


def adjust_user_quota(user_id: int, free_delta: int = 0, paid_delta: int = 0):
    """
    管理员调整用户次数（可增可减）。
    delta > 0 增加次数，delta < 0 减少次数。
    """
    if free_delta != 0:
        execute_query(
            "UPDATE users SET free_quota = MAX(0, free_quota + ?) WHERE id = ?",
            (free_delta, user_id)
        )
    if paid_delta != 0:
        execute_query(
            "UPDATE users SET paid_quota = MAX(0, paid_quota + ?) WHERE id = ?",
            (paid_delta, user_id)
        )


def ban_user(user_id: int):
    """封禁用户"""
    execute_query(
        "UPDATE users SET status = 'banned' WHERE id = ?",
        (user_id,)
    )


def unban_user(user_id: int):
    """解封用户"""
    execute_query(
        "UPDATE users SET status = 'active' WHERE id = ?",
        (user_id,)
    )


def set_user_role(user_id: int, role: str):
    """设置用户角色（user / admin）"""
    execute_query(
        "UPDATE users SET role = ? WHERE id = ?",
        (role, user_id)
    )


# ---- 数据统计 ----

def get_stats() -> dict:
    """获取统计面板数据"""
    stats = {}

    # 总用户数
    row = fetch_one("SELECT COUNT(*) as cnt FROM users")
    stats['total_users'] = row['cnt'] if row else 0

    # 今日注册用户
    row = fetch_one(
        "SELECT COUNT(*) as cnt FROM users WHERE date(created_at) = date('now','localtime')"
    )
    stats['today_users'] = row['cnt'] if row else 0

    # 总分析次数
    row = fetch_one("SELECT COUNT(*) as cnt FROM billing_logs")
    stats['total_analyses'] = row['cnt'] if row else 0

    # 今日分析次数
    row = fetch_one(
        "SELECT COUNT(*) as cnt FROM billing_logs WHERE date(created_at) = date('now','localtime')"
    )
    stats['today_analyses'] = row['cnt'] if row else 0

    # 免费分析次数
    row = fetch_one("SELECT COUNT(*) as cnt FROM billing_logs WHERE quota_type = 'free'")
    stats['free_analyses'] = row['cnt'] if row else 0

    # 付费分析次数
    row = fetch_one("SELECT COUNT(*) as cnt FROM billing_logs WHERE quota_type = 'paid'")
    stats['paid_analyses'] = row['cnt'] if row else 0

    # 已使用兑换码数
    row = fetch_one("SELECT COUNT(*) as cnt FROM redeem_codes WHERE status = 'used'")
    stats['used_codes'] = row['cnt'] if row else 0

    # 未使用兑换码数
    row = fetch_one("SELECT COUNT(*) as cnt FROM redeem_codes WHERE status = 'unused'")
    stats['unused_codes'] = row['cnt'] if row else 0

    # 总充值次数
    row = fetch_one("SELECT COALESCE(SUM(amount), 0) as total FROM redeem_codes WHERE status = 'used'")
    stats['total_recharged'] = row['total'] if row else 0

    # 充值金额（已通过的充值申请）
    row = fetch_one("SELECT COALESCE(SUM(amount), 0) as total FROM recharge_requests WHERE status = 'approved'")
    stats['total_recharge_amount'] = row['total'] if row else 0

    return stats


def get_recent_analyses(limit: int = 50) -> list[dict]:
    """获取最近的分析记录"""
    rows = fetch_all(
        """SELECT bl.*, u.phone
           FROM billing_logs bl
           LEFT JOIN users u ON bl.user_id = u.id
           ORDER BY bl.created_at DESC
           LIMIT ?""",
        (limit,)
    )
    return [dict(r) for r in rows]
