# billing/recharge.py - 充值申请模块
"""
充值申请的创建、查询、审核（管理员通过/驳回）。
用户提交充值申请 → 管理员审核通过 → 自动发放兑换码并通知用户。
"""

from billing.database import execute_query, fetch_one, fetch_all


# ---- 充值方案配置 ----

# (金额元, 对应次数) 的固定方案，可在 system_settings 中覆盖
DEFAULT_PLANS = [
    (10, 50),    # 10元 = 50次
    (20, 120),   # 20元 = 120次
    (50, 350),   # 50元 = 350次
    (100, 800),  # 100元 = 800次
]


def get_recharge_plans() -> list[tuple[int, int]]:
    """获取充值方案列表 [(金额, 次数), ...]"""
    from billing.admin import get_system_setting
    plans_str = get_system_setting('recharge_plans', '')
    if plans_str:
        try:
            import json
            return json.loads(plans_str)
        except (json.JSONDecodeError, TypeError):
            pass
    return DEFAULT_PLANS


# ---- 收款信息 ----

def get_payment_info() -> dict:
    """
    获取收款信息（从系统设置读取）。
    返回: {'method': '微信/支付宝', 'account': '...', 'qr_code': 'base64...'}
    """
    from billing.admin import get_system_setting
    return {
        'method': get_system_setting('payment_method', '微信'),
        'account': get_system_setting('payment_account', ''),
        'qr_code': get_system_setting('payment_qr_code', ''),
    }


def set_payment_info(method: str, account: str, qr_code: str = ''):
    """保存收款信息到系统设置"""
    from billing.admin import set_system_setting
    set_system_setting('payment_method', method)
    set_system_setting('payment_account', account)
    if qr_code:
        set_system_setting('payment_qr_code', qr_code)


# ---- 充值申请 ----

def create_recharge_request(user_id: int, amount: float, quota_requested: int, remark: str = '') -> tuple[bool, str]:
    """
    创建充值申请。
    返回 (成功?, 消息)
    """
    if amount <= 0 or quota_requested <= 0:
        return False, "金额或次数无效"

    # 检查是否有未处理的申请（防止重复提交）
    pending = fetch_one(
        """SELECT id FROM recharge_requests
           WHERE user_id = ? AND status = 'pending'
           ORDER BY created_at DESC LIMIT 1""",
        (user_id,)
    )
    if pending:
        return False, "您已有待处理的充值申请，请耐心等待管理员审核"

    try:
        execute_query(
            """INSERT INTO recharge_requests (user_id, amount, quota_requested, status, remark)
               VALUES (?, ?, ?, 'pending', ?)""",
            (user_id, amount, quota_requested, remark)
        )
        return True, "充值申请已提交，请等待管理员审核"
    except Exception as e:
        return False, f"提交失败：{str(e)}"


def approve_recharge_request(request_id: int, admin_id: int, quota_granted: int, admin_note: str = '') -> tuple[bool, str]:
    """
    管理员通过充值申请：发放兑换码给用户。
    返回 (成功?, 消息)
    """
    request = fetch_one(
        "SELECT * FROM recharge_requests WHERE id = ? AND status = 'pending'",
        (request_id,)
    )
    if not request:
        return False, "申请不存在或已处理"

    try:
        # 生成兑换码并直接核销（发放到用户 paid_quota）
        from billing.redeem import _generate_unique_code

        code = _generate_unique_code()

        # 创建并立即使用兑换码
        execute_query(
            """INSERT INTO redeem_codes (code, amount, status, created_by, batch_id)
               VALUES (?, ?, 'used', ?, ?)""",
            (code, quota_granted, admin_id, f'recharge_{request_id}')
        )
        execute_query(
            """UPDATE redeem_codes
               SET used_by = ?, used_at = datetime('now','localtime')
               WHERE code = ?""",
            (request['user_id'], code)
        )
        # 增加用户付费次数
        execute_query(
            "UPDATE users SET paid_quota = paid_quota + ? WHERE id = ?",
            (quota_granted, request['user_id'])
        )

        # 更新申请状态
        execute_query(
            """UPDATE recharge_requests
               SET status = 'approved', admin_note = ?, processed_by = ?,
                   processed_at = datetime('now','localtime')
               WHERE id = ?""",
            (f'已发放 {quota_granted} 次（兑换码: {code}）。{admin_note}'.strip(), admin_id, request_id)
        )

        return True, f"已通过，发放 {quota_granted} 次给用户（兑换码: {code}）"
    except Exception as e:
        return False, f"操作失败：{str(e)}"


def reject_recharge_request(request_id: int, admin_id: int, admin_note: str) -> tuple[bool, str]:
    """
    管理员驳回充值申请。
    返回 (成功?, 消息)
    """
    request = fetch_one(
        "SELECT * FROM recharge_requests WHERE id = ? AND status = 'pending'",
        (request_id,)
    )
    if not request:
        return False, "申请不存在或已处理"

    execute_query(
        """UPDATE recharge_requests
           SET status = 'rejected', admin_note = ?, processed_by = ?,
               processed_at = datetime('now','localtime')
           WHERE id = ?""",
        (admin_note, admin_id, request_id)
    )
    return True, "已驳回"


# ---- 查询 ----

def get_user_recharge_requests(user_id: int, limit: int = 20) -> list[dict]:
    """获取用户的充值申请记录"""
    rows = fetch_all(
        """SELECT * FROM recharge_requests
           WHERE user_id = ?
           ORDER BY created_at DESC LIMIT ?""",
        (user_id, limit)
    )
    return [dict(r) for r in rows]


def get_all_recharge_requests(status_filter: str = None, limit: int = 50) -> list[dict]:
    """
    获取所有充值申请（管理员用）。
    status_filter: None=全部, 'pending'=待审核, 'approved'=已通过, 'rejected'=已驳回
    """
    if status_filter and status_filter != 'all':
        rows = fetch_all(
            """SELECT rr.*, u.phone, u.nickname
               FROM recharge_requests rr
               JOIN users u ON rr.user_id = u.id
               WHERE rr.status = ?
               ORDER BY rr.created_at DESC LIMIT ?""",
            (status_filter, limit)
        )
    else:
        rows = fetch_all(
            """SELECT rr.*, u.phone, u.nickname
               FROM recharge_requests rr
               JOIN users u ON rr.user_id = u.id
               ORDER BY rr.created_at DESC LIMIT ?""",
            (limit,)
        )
    return [dict(r) for r in rows]


def get_pending_count() -> int:
    """获取待审核的充值申请数量"""
    row = fetch_one("SELECT COUNT(*) as cnt FROM recharge_requests WHERE status = 'pending'")
    return row['cnt'] if row else 0
