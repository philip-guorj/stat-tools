# pages/08_用户中心.py - 用户中心
"""
用户中心：个人信息、充值、改密码、退出、注销。
"""

import streamlit as st
import pandas as pd

from billing.auth import get_current_user, logout_user, change_password, delete_account, update_user_profile
from billing.billing import get_user_quota
from billing.redeem import redeem_code
from billing.recharge import create_recharge_request, get_recharge_plans, get_payment_info, get_user_recharge_requests

# require_auth 已在入口文件调用，此处直接获取用户
user = get_current_user()
if not user:
    st.stop()

# require_auth 放行后，用户已登录
user = get_current_user()

st.markdown('<div class="main-header">👤 用户中心</div>', unsafe_allow_html=True)

with st.expander("📖 功能简介", expanded=False):
    st.markdown("""
用户中心提供以下功能模块：

| 模块 | 说明 |
|------|------|
| 📊 **个人信息** | 查看账号信息、登录历史 |
| 💎 **充值中心** | 选择充值方案、扫码支付、兑换码充值、查看充值记录 |
| 🔐 **修改密码** | 更新登录密码 |
| ⚙️ **账号管理** | 退出登录、注销账号（不可逆） |

> 💡 新用户注册即赠送 **100次** 免费分析次数。充值次数永不过期，用完即止。
""")

# ---- Tab 页签 ----
tab_info, tab_recharge, tab_password, tab_account = st.tabs([
    "📊 个人信息", "💎 充值中心", "🔐 修改密码", "⚙️ 账号管理"
])

# ============== 个人信息 ==============
with tab_info:
    quota = get_user_quota()

    # 用户基本信息
    phone = user['phone']
    if len(phone) >= 7:
        masked_phone = phone[:3] + "****" + phone[-4:]
    else:
        masked_phone = phone

    # 自动保存回调
    def _on_name_change():
        from billing.database import execute_query
        val = st.session_state.get('edit_nickname', '')
        execute_query("UPDATE users SET nickname = ? WHERE id = ?", (val.strip(), user['id']))
        st.session_state['current_user']['nickname'] = val.strip()

    def _on_org_change():
        from billing.database import execute_query
        val = st.session_state.get('edit_org', '')
        execute_query("UPDATE users SET organization = ? WHERE id = ?", (val.strip(), user['id']))
        st.session_state['current_user']['organization'] = val.strip()

    col1, col2 = st.columns(2)
    with col1:
        st.text_input("👤 姓名", value=user.get('nickname') or '', key='edit_nickname',
                      placeholder="点击输入姓名", on_change=_on_name_change, label_visibility="visible")
    with col2:
        st.text_input("🏫 单位", value=user.get('organization') or '', key='edit_org',
                      placeholder="点击输入单位", on_change=_on_org_change, label_visibility="visible")

    col1, col2 = st.columns(2)
    with col1:
        st.metric("📱 手机号", masked_phone)
    with col2:
        st.metric("📅 注册时间", user['created_at'][:10] if user.get('created_at') else "-")

    if user['role'] == 'admin':
        st.markdown("🛡️ **管理员账号**")

    st.markdown("---")

    # 剩余次数展示
    st.markdown("### 📊 我的分析次数")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("免费次数", quota['free'], delta=None)
    with col2:
        st.metric("付费次数", quota['paid'], delta=None)
    with col3:
        st.metric("剩余总计", quota['total'], delta=None)

    if quota['total'] == 0:
        st.warning("⚠️ 分析次数已用完，请前往充值中心充值。")

# ============== 充值中心 ==============
with tab_recharge:
    sub_tab_apply, sub_tab_code, sub_tab_history = st.tabs([
        "💰 在线充值", "🔑 兑换码充值", "📋 充值记录"
    ])

    # ---- 在线充值 ----
    with sub_tab_apply:
        plans = get_recharge_plans()
        payment = get_payment_info()

        st.markdown("### 💰 选择充值方案")
        st.markdown("扫码支付后，提交充值申请，管理员审核通过后将自动发放分析次数。\n\n若需紧急充值，请在完成支付后发送支付截图到邮箱：718854143@qq.com")

        # 充值方案选择
        selected_idx = 0
        plan_cols = st.columns(len(plans))
        for i, (amount, quota) in enumerate(plans):
            with plan_cols[i]:
                unit_price = amount / quota if quota > 0 else 0
                is_selected = st.checkbox(
                    f"**{amount}元**\n{quota}次\n≈{unit_price:.2f}元/次",
                    key=f"plan_{i}",
                    value=(i == 0)
                )
                if is_selected:
                    selected_idx = i

        selected_amount, selected_quota = plans[selected_idx]

        # 收款信息展示
        st.markdown("---")
        st.markdown(f"### 📱 扫码支付（{payment['method']}）")

        if payment.get('qr_code'):
            # qr_code 可能是 base64 字符串或文件路径，统一处理为 bytes
            qr_data = payment['qr_code']
            try:
                import base64
                # 处理带 data URI 前缀的 base64 (data:image/png;base64,xxxx)
                if qr_data.startswith('data:'):
                    header, qr_data = qr_data.split(',', 1)
                img_bytes = base64.b64decode(qr_data)
                st.image(img_bytes, width=200, caption=f"{payment['method']}收款码")
            except Exception:
                # 兜底：尝试作为文件路径
                import os
                if os.path.isfile(qr_data):
                    st.image(qr_data, width=200, caption=f"{payment['method']}收款码")
        if payment.get('account'):
            st.info(f"💰 收款账号：`{payment['account']}`")

        st.warning(f"请支付 **{selected_amount} 元** 后再提交申请")

        # 提交申请
        with st.form("recharge_request_form"):
            remark = st.text_input(
                "备注（选填）",
                placeholder="如支付时间、支付截图说明等",
                label_visibility="visible"
            )

            submitted = st.form_submit_button(
                f"✅ 提交充值申请（{selected_amount}元 / {selected_quota}次）",
                use_container_width=True, type="primary"
            )

            if submitted:
                ok, msg = create_recharge_request(user['id'], selected_amount, selected_quota, remark)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

    # ---- 兑换码充值 ----
    with sub_tab_code:
        st.markdown("### 🔑 兑换码充值")

        with st.form("redeem_form"):
            st.markdown("如果已有兑换码，请在此输入直接充值。")

            code_input = st.text_input(
                "兑换码",
                placeholder="请输入8位兑换码",
                label_visibility="collapsed",
                max_chars=8
            )

            submitted = st.form_submit_button("立即充值", type="primary")

            if submitted:
                if not code_input:
                    st.error("请输入兑换码")
                else:
                    ok, msg = redeem_code(user['id'], code_input)
                    if ok:
                        st.success(msg)
                        st.balloons()
                        st.rerun()
                    else:
                        st.error(msg)

    # ---- 充值记录 ----
    with sub_tab_history:
        st.markdown("### 📋 充值记录")

        # 在线充值申请记录
        requests = get_user_recharge_requests(user['id'], limit=20)
        if requests:
            st.markdown("#### 在线充值申请")
            df_req = pd.DataFrame(requests)
            status_map = {'pending': '⏳ 待审核', 'approved': '✅ 已通过', 'rejected': '❌ 已驳回'}
            df_req['status'] = df_req['status'].map(status_map)
            df_req = df_req.rename(columns={
                'amount': '金额(元)',
                'quota_requested': '申请次数',
                'status': '状态',
                'admin_note': '处理说明',
                'created_at': '申请时间'
            })
            st.dataframe(
                df_req[['金额(元)', '申请次数', '状态', '处理说明', '申请时间']],
                hide_index=True, use_container_width=True
            )
        else:
            st.info("暂无在线充值记录")

        st.markdown("---")

        # 兑换码充值记录
        from billing.database import fetch_all

        records = fetch_all(
            """SELECT rc.code, rc.amount, rc.created_at, rc.used_at
               FROM redeem_codes rc
               WHERE rc.used_by = ? AND rc.status = 'used'
               ORDER BY rc.used_at DESC
               LIMIT 10""",
            (user['id'],)
        )

        st.markdown("#### 兑换码充值记录")
        if records:
            df = pd.DataFrame([dict(r) for r in records])
            df['amount'] = df['amount'].apply(lambda x: f"+{x} 次")
            df = df.rename(columns={
                'code': '兑换码',
                'amount': '充值次数',
                'created_at': '生成时间',
                'used_at': '使用时间'
            })
            st.dataframe(df, hide_index=True, use_container_width=True)
        else:
            st.info("暂无兑换码充值记录")

# ============== 修改密码 ==============
with tab_password:
    st.markdown("### 🔐 修改密码")
    st.info("修改密码后需要重新登录。")

    with st.form("change_password_form"):
        old_pw = st.text_input("原密码", type="password", key="old_pw", placeholder="请输入原密码")
        new_pw = st.text_input("新密码", type="password", key="new_pw", placeholder="至少6位新密码")
        new_pw2 = st.text_input("确认新密码", type="password", key="new_pw2", placeholder="再次输入新密码")

        submitted = st.form_submit_button("修改密码", type="primary")

        if submitted:
            if not old_pw or not new_pw:
                st.error("请输入原密码和新密码")
            elif new_pw != new_pw2:
                st.error("两次密码输入不一致")
            elif len(new_pw) < 6:
                st.error("新密码长度不能少于6位")
            else:
                ok, msg = change_password(user['id'], old_pw, new_pw)
                if ok:
                    st.success(msg)
                    # 密码改完后需要退出登录
                    import time
                    time.sleep(1)
                    logout_user()
                    st.rerun()
                else:
                    st.error(msg)

# ============== 账号管理 ==============
with tab_account:
    st.markdown("### ⚙️ 账号管理")

    # 退出登录（带确认弹窗）
    with st.popover("🚪 退出登录", use_container_width=True):
        st.markdown("**确认退出登录？**")
        clear_cache = st.checkbox("🗑️ 同时清除已上传的数据和分析缓存", value=True,
                                   help="勾选后，退出时将清除您上传的数据文件和分析参数缓存。下次登录需重新上传数据。")
        if st.button("确认退出", type="primary"):
            logout_user(clear_data_cache=clear_cache)
            st.rerun()

    st.markdown("---")

    # 注销账号
    st.markdown("### ⚠️ 注销账号")
    st.warning("""
    **注销账号后数据不可恢复！**  
    注销将删除您的所有数据，包括：
    - 账号信息
    - 分析记录
    - 充值记录
    - 剩余次数
    """)

    confirm_text = st.text_input(
        '请输入 "确认注销" 以继续',
        key="delete_confirm",
        placeholder="确认注销"
    )

    if st.button("🗑️ 注销账号", type="secondary"):
        if confirm_text != "确认注销":
            st.error('请输入 "确认注销" 以确认操作')
        else:
            ok, msg = delete_account(user['id'])
            if ok:
                st.success(msg)
                import time
                time.sleep(1)
                logout_user()
                st.rerun()
            else:
                st.error(msg)
