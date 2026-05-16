# billing/billing.py - 计费守卫模块
"""
核心接口：
- require_auth()      认证守卫
- check_billing()     计费守卫（扣次数）
- can_download()      下载守卫
- render_balance_widget()  侧边栏信息展示

认证方案：数据库会话 + query_params 持久化
- login_user() 在数据库创建会话，token 写入 st.query_params
- 页面切换/刷新时，get_current_user() 从 query_params 读取 token 查库验证
- session_state 仅做加速缓存，丢失不影响功能
"""

import hashlib
import json
from datetime import datetime, timedelta

import streamlit as st

from billing.database import execute_query, fetch_one, fetch_all


# ---- 参数哈希（防重复扣费） ----

def _calc_params_hash(analysis_type: str, params: dict, data_row_count: int = 0) -> str:
    """计算分析请求的唯一哈希"""
    raw = f"{analysis_type}|{data_row_count}|{json.dumps(params, sort_keys=True, default=str)}"
    return hashlib.md5(raw.encode()).hexdigest()


def _is_duplicate_hash(user_id: int, params_hash: str, window_minutes: int = 5) -> bool:
    """检查最近 N 分钟内是否有相同的分析请求"""
    cutoff = (datetime.now() - timedelta(minutes=window_minutes)).strftime('%Y-%m-%d %H:%M:%S')
    row = fetch_one(
        """SELECT id FROM billing_logs
           WHERE user_id = ? AND params_hash = ? AND created_at > ?
           LIMIT 1""",
        (user_id, params_hash, cutoff)
    )
    return row is not None


# ---- 核心守卫函数 ----

def require_auth(admin_only: bool = False):
    """
    认证守卫：未登录 → 显示登录表单 → st.stop()
    已登录 → 正常放行

    认证来源：query_params 中的 token → 数据库 user_sessions 验证
    """
    from billing.auth import get_current_user, render_captcha_image, verify_captcha, register_user, login_user, refresh_captcha

    user = get_current_user()
    if user:
        # 管理员权限检查
        if admin_only and user['role'] != 'admin':
            st.error("⛔ 无权访问此页面，仅管理员可用")
            st.stop()
        return  # 已登录，放行

    # 未登录，显示登录/注册表单
    st.markdown("""
<div style="text-align:center;margin-bottom:0.5rem;">
    <span style="font-size:1.8rem;font-weight:800;color:#1e40af;">StatTools</span>
    <span style="font-size:1.5rem;font-weight:600;color:#334155;margin-left:0.5rem;">田间试验统计分析平台</span>
</div>
""", unsafe_allow_html=True)
    st.markdown("""
<div style="text-align:center;color:#64748b;font-size:0.9rem;line-height:1.6;
            margin-bottom:1rem;">
    描述统计 · 方差分析 · 回归分析 · 多变量分析 · 试验设计
</div>
""", unsafe_allow_html=True)
    c_reg, _ = st.columns([0.25, 0.75])
    with c_reg:
        if st.button("📝 新用户注册即赠 100次 免费分析", key="top_goto_register"):
            st.session_state['auth_view'] = 'register'
            st.rerun()
    st.markdown("---")
    st.markdown("### 🔐 登录 / 注册")

    # 用 session_state 控制显示"登录"还是"注册"视图（st.tabs 不支持编程式切换）
    if 'auth_view' not in st.session_state:
        st.session_state['auth_view'] = 'login'

    # ---- 登录视图 ----
    if st.session_state['auth_view'] == 'login':
        st.markdown("#### 🔐 登录")
        with st.form("login_form"):
            phone = st.text_input("手机号", key="login_phone", placeholder="请输入手机号")
            password = st.text_input("密码", type="password", key="login_password", placeholder="请输入密码")
            submitted = st.form_submit_button("登录", use_container_width=True, type="primary")
            if submitted:
                if not phone or not password:
                    st.error("请输入手机号和密码")
                else:
                    ok, msg, token = login_user(phone, password)
                    if ok:
                        st.success(msg)
                        st.rerun()  # token 已在 login_user 中写入 query_params，直接 rerun 即可
                    else:
                        st.error(msg)

        st.markdown("---")
        st.caption("🔑 **忘记密码？** 请联系管理员重置密码。发送邮件至 718854143@qq.com，注明手机号和注册信息。")
        if st.button("还没有账号？去注册 →", use_container_width=True, key="goto_register"):
            st.session_state['auth_view'] = 'register'
            st.rerun()

    # ---- 注册视图 ----
    else:
        st.markdown("#### 📝 注册")
        with st.form("register_form"):
            # 第一行：手机号
            reg_phone = st.text_input("手机号 *", key="reg_phone", placeholder="请输入手机号（必填）", label_visibility="visible")

            # 第二行：姓名 + 单位 并排
            c1, c2 = st.columns(2)
            with c1:
                reg_name = st.text_input("姓名", key="reg_name", placeholder="请输入姓名", label_visibility="visible")
            with c2:
                reg_org = st.text_input("单位", key="reg_org", placeholder="请输入工作单位", label_visibility="visible")

            # 第三行：密码 + 确认密码 并排
            c3, c4 = st.columns(2)
            with c3:
                reg_password = st.text_input("密码 *", type="password", key="reg_password", placeholder="至少6位密码", label_visibility="visible")
            with c4:
                reg_password2 = st.text_input("确认密码 *", type="password", key="reg_password2", placeholder="再次输入密码", label_visibility="visible")

            # 第四行：验证码图片 + 输入框 并排
            st.markdown("**📝 图形验证码**")
            c_img, c_input, c_btn = st.columns([2, 2, 1])
            with c_img:
                render_captcha_image()
            with c_input:
                captcha_input = st.text_input("请输入验证码", key="captcha_input", placeholder="不区分大小写", label_visibility="visible")
            with c_btn:
                st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)
                if st.form_submit_button("🔄 换一张", key="captcha_refresh_btn"):
                    refresh_captcha()
                    st.rerun()

            # 第五行：注册按钮
            submitted = st.form_submit_button("注册", use_container_width=True, type="primary")
            if submitted:
                if not reg_phone:
                    st.error("请填写手机号")
                elif reg_password != reg_password2:
                    st.error("两次密码输入不一致")
                elif not captcha_input.strip():
                    st.error("请输入验证码")
                elif not verify_captcha(captcha_input):
                    st.error("验证码错误，请重新输入")
                    refresh_captcha()
                    st.rerun()
                else:
                    ok, msg = register_user(reg_phone, reg_password,
                                            nickname=reg_name, organization=reg_org)
                    if ok:
                        st.success(msg)
                        # 注册后自动登录
                        login_user(reg_phone, reg_password)
                        st.rerun()  # token 已写入 query_params
                    else:
                        if "已注册" in msg:
                            st.error(msg)
                            placeholder = st.empty()
                            placeholder.info("即将跳转到登录页面...")
                            import time
                            time.sleep(1.5)
                            placeholder.empty()
                            st.session_state['auth_view'] = 'login'
                            st.rerun()
                        else:
                            st.error(msg)

        if st.button("← 已有账号，去登录", use_container_width=True, key="goto_login"):
            st.session_state['auth_view'] = 'login'
            st.rerun()

    st.stop()


def check_billing(analysis_type: str, params: dict, data_row_count: int = 0) -> bool:
    """
    计费守卫：检查并扣减分析次数。

    返回值：
    - True  → 有剩余次数（已扣费），可以继续分析
    - False → 次数不足

    注意：无论返回 True 还是 False，分析结果都会正常展示。
    返回 False 仅影响下载功能（通过 can_download() 判断）。
    """
    from billing.auth import get_current_user

    user = get_current_user()
    if not user:
        return False

    user_id = user['id']

    params_hash = _calc_params_hash(analysis_type, params, data_row_count)
    if _is_duplicate_hash(user_id, params_hash):
        return True  # 5分钟内重复请求，跳过扣费

    row = fetch_one(
        "SELECT free_quota, paid_quota FROM users WHERE id = ?", (user_id,)
    )
    if not row:
        return False

    free_quota = row['free_quota']
    paid_quota = row['paid_quota']

    if free_quota > 0:
        execute_query(
            """UPDATE users SET free_quota = free_quota - 1 WHERE id = ?""",
            (user_id,)
        )
        quota_type = 'free'
    elif paid_quota > 0:
        execute_query(
            """UPDATE users SET paid_quota = paid_quota - 1 WHERE id = ?""",
            (user_id,)
        )
        quota_type = 'paid'
    else:
        return False

    execute_query(
        """INSERT INTO billing_logs (user_id, analysis_type, params_hash, quota_type)
           VALUES (?, ?, ?, ?)""",
        (user_id, analysis_type, params_hash, quota_type)
    )

    # 更新 session_state 缓存
    user['free_quota'] = max(0, free_quota - (1 if quota_type == 'free' else 0))
    user['paid_quota'] = max(0, paid_quota - (1 if quota_type == 'paid' else 0))
    st.session_state['current_user'] = user

    return True


def can_download() -> bool:
    """
    下载守卫：检查用户是否还有剩余次数。
    """
    from billing.auth import get_current_user

    user = get_current_user()
    if not user:
        return False

    total_quota = user.get('free_quota', 0) + user.get('paid_quota', 0)
    return total_quota > 0


def get_user_quota() -> dict:
    """获取当前用户的剩余次数（实时从数据库查询）"""
    from billing.auth import get_current_user

    user = get_current_user()
    if not user:
        return {'free': 0, 'paid': 0, 'total': 0}

    row = fetch_one(
        "SELECT free_quota, paid_quota FROM users WHERE id = ?",
        (user['id'],)
    )
    if not row:
        return {'free': 0, 'paid': 0, 'total': 0}

    free = row['free_quota']
    paid = row['paid_quota']
    return {'free': free, 'paid': paid, 'total': free + paid}


def render_balance_widget():
    """
    在侧边栏渲染用户信息和入口。
    调用位置：数据管理.py 的侧边栏区域。
    """
    from billing.auth import get_current_user

    user = get_current_user()
    if not user:
        return

    quota = get_user_quota()

    with st.sidebar:
        st.markdown("---")
        st.markdown("#### 👤 用户信息")

        phone = user['phone']
        if len(phone) >= 7:
            masked_phone = phone[:3] + "****" + phone[-4:]
        else:
            masked_phone = phone
        st.markdown(f"📱 {masked_phone}")

        col_free, col_paid = st.columns(2)
        with col_free:
            st.metric("免费次数", quota['free'])
        with col_paid:
            st.metric("付费次数", quota['paid'])

        if user['role'] == 'admin':
            st.markdown("🛡️ **管理员**")

        # 用户中心入口（所有用户可见）
        if st.button("👤 用户中心", use_container_width=True):
            st.switch_page("pages/08_用户中心.py")

        # 管理后台入口（仅管理员可见）
        if user['role'] == 'admin':
            if st.button("⚙️ 管理后台", use_container_width=True):
                st.switch_page("pages/09_管理后台.py")

        if quota['total'] == 0:
            st.warning("⚠️ 分析次数已用完，充值后可下载结果")
