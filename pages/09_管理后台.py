# pages/09_管理后台.py - 管理后台
"""
管理员专用页面：兑换码管理、用户管理、系统设置、数据统计、充值审核。
仅管理员可见（已在入口文件的 st.navigation 中控制）。
"""

import streamlit as st
import pandas as pd

from billing.auth import get_current_user
from billing.admin import (
    get_system_setting, set_system_setting,
    get_all_users, adjust_user_quota, ban_user, unban_user, set_user_role,
    get_stats, get_recent_analyses
)
from billing.redeem import generate_codes, get_all_codes
from billing.recharge import (
    get_all_recharge_requests, approve_recharge_request, reject_recharge_request,
    get_pending_count, get_payment_info, set_payment_info, get_recharge_plans
)

# require_auth 和管理员检查已在入口文件完成，此处双重保险
user = get_current_user()
if not user or user['role'] != 'admin':
    st.error("⛔ 无权访问此页面，仅管理员可用")
    st.stop()

st.markdown('<div class="main-header">⚙️ 管理后台</div>', unsafe_allow_html=True)

with st.expander("📖 功能简介", expanded=False):
    st.markdown("""
管理后台仅供管理员使用，提供以下管理模块：

| 模块 | 说明 |
|------|------|
| 📊 **数据统计** | 平台使用概览：用户数、分析次数、近期活动 |
| 🔑 **兑换码管理** | 批量生成/查看兑换码，支持自定义面额 |
| 👥 **用户管理** | 查看/搜索用户、调整次数、封禁/解封、角色管理 |
| 💳 **充值审核** | 审核用户充值申请（通过/拒绝）、配置收款信息 |
| 🔧 **系统设置** | 新用户赠送次数、默认分析参数等全局配置 |
""")

# Tab 页签（待审核数量提示）
pending_count = get_pending_count()
tab_title = f"💳 充值审核{' (' + str(pending_count) + ')' if pending_count > 0 else ''}"
tab_stats, tab_codes, tab_users, tab_recharge, tab_settings = st.tabs([
    "📊 数据统计", "🔑 兑换码管理", "👥 用户管理", tab_title, "🔧 系统设置"
])

# ============== 数据统计 ==============
with tab_stats:
    stats = get_stats()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("总用户数", stats['total_users'], delta=stats['today_users'], delta_color="normal")
    with col2:
        st.metric("总分析次数", stats['total_analyses'], delta=stats['today_analyses'], delta_color="normal")
    with col3:
        st.metric("已兑换码数", stats['used_codes'], delta=f"未使用: {stats['unused_codes']}")

    st.markdown("---")

    col4, col5 = st.columns(2)
    with col4:
        st.metric("免费分析次数", stats['free_analyses'])
        st.metric("付费分析次数", stats['paid_analyses'])
    with col5:
        st.metric("总充值次数", f"{stats['total_recharged']} 次")
        st.metric("充值金额", f"¥ {stats['total_recharge_amount']:.0f}")

    st.markdown("---")
    st.markdown("### 📋 最近分析记录")

    recent = get_recent_analyses(30)
    if recent:
        df = pd.DataFrame(recent)
        df = df.rename(columns={
            'id': 'ID',
            'phone': '用户',
            'analysis_type': '分析类型',
            'quota_type': '类型',
            'created_at': '时间'
        })
        df['类型'] = df['类型'].map({'free': '免费', 'paid': '付费'})
        st.dataframe(df[['ID', '用户', '分析类型', '类型', '时间']], hide_index=True, use_container_width=True)
    else:
        st.info("暂无分析记录")

# ============== 兑换码管理 ==============
with tab_codes:
    st.markdown("### 生成兑换码")

    with st.form("gen_codes_form"):
        col_count, col_amount = st.columns(2)
        with col_count:
            gen_count = st.number_input("生成数量", min_value=1, max_value=100, value=10)
        with col_amount:
            gen_amount = st.number_input("每次充值次数", min_value=1, max_value=10000, value=10)
        
        submitted = st.form_submit_button("生成兑换码", type="primary", use_container_width=True)
        
        if submitted:
            codes = generate_codes(user['id'], gen_count, gen_amount)
            if codes:
                st.success(f"✅ 成功生成 {len(codes)} 个兑换码（每个 {gen_amount} 次）")
                
                # 展示生成的兑换码
                codes_text = "\n".join(codes)
                st.code(codes_text, language=None)
                
                # 一键复制提示
                st.info("💡 请复制上述兑换码分发给用户。")

    st.markdown("---")
    st.markdown("### 兑换码列表")

    status_filter = st.selectbox("筛选状态", ["all", "unused", "used"], format_func={
        "all": "全部", "unused": "未使用", "used": "已使用"
    }.get)

    codes_list = get_all_codes(status_filter if status_filter != "all" else None, limit=100)
    if codes_list:
        df = pd.DataFrame(codes_list)
        df = df.rename(columns={
            'id': 'ID',
            'code': '兑换码',
            'amount': '次数',
            'status': '状态',
            'used_phone': '使用者',
            'created_at': '生成时间',
            'used_at': '使用时间'
        })
        df['状态'] = df['状态'].map({'unused': '未使用', 'used': '已使用'})
        st.dataframe(
            df[['ID', '兑换码', '次数', '状态', '使用者', '生成时间', '使用时间']],
            hide_index=True, use_container_width=True
        )
    else:
        st.info("暂无兑换码记录")

# ============== 用户管理 ==============
with tab_users:
    st.markdown("### 用户列表")

    users = get_all_users(limit=200)
    if users:
        df = pd.DataFrame(users)
        df = df.rename(columns={
            'id': 'ID',
            'phone': '手机号',
            'nickname': '姓名',
            'organization': '单位',
            'free_quota': '免费次数',
            'paid_quota': '付费次数',
            'role': '角色',
            'status': '状态',
            'created_at': '注册时间',
            'last_login': '最后登录'
        })
        df['角色'] = df['角色'].map({'user': '用户', 'admin': '管理员'})
        df['状态'] = df['状态'].map({'active': '正常', 'banned': '已封禁'})
        st.dataframe(df, hide_index=True, use_container_width=True)

        st.markdown("---")
        st.markdown("### 用户操作")

        # 选择用户
        user_options = {u['phone']: u['id'] for u in users}
        selected_phone = st.selectbox("选择用户", options=list(user_options.keys()))
        selected_uid = user_options[selected_phone]

        # 获取选中用户的当前数据
        from billing.database import fetch_one
        sel_user = fetch_one(
            "SELECT * FROM users WHERE id = ?", (selected_uid,)
        )

        if sel_user:
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**当前状态**：免费 {sel_user['free_quota']} 次 / 付费 {sel_user['paid_quota']} 次 / {sel_user['status']}")

            with col2:
                st.markdown("**操作**")

            # 调整次数
            with st.form("adjust_quota_form"):
                c1, c2, c3 = st.columns(3)
                with c1:
                    adj_free = st.number_input("调整免费次数（正数=增加，负数=减少）", value=0)
                with c2:
                    adj_paid = st.number_input("调整付费次数（正数=增加，负数=减少）", value=0)
                with c3:
                    st.markdown("<br>", unsafe_allow_html=True)
                    adj_btn = st.form_submit_button("执行调整")

                if adj_btn and (adj_free != 0 or adj_paid != 0):
                    adjust_user_quota(selected_uid, adj_free, adj_paid)
                    st.success(f"已调整：免费次数 {adj_free:+d}，付费次数 {adj_paid:+d}")
                    st.rerun()

            # 封禁/解封/角色
            btn_col1, btn_col2, btn_col3 = st.columns(3)
            with btn_col1:
                if st.button("🔓 解封" if sel_user['status'] == 'banned' else "🔒 封禁"):
                    if sel_user['status'] == 'banned':
                        unban_user(selected_uid)
                        st.success("已解封")
                    else:
                        ban_user(selected_uid)
                        st.success("已封禁")
                    st.rerun()

            with btn_col2:
                if st.button(f"设为{'用户' if sel_user['role'] == 'admin' else '管理员'}"):
                    new_role = 'user' if sel_user['role'] == 'admin' else 'admin'
                    set_user_role(selected_uid, new_role)
                    st.success(f"已设为{'管理员' if new_role == 'admin' else '用户'}")
                    st.rerun()
    else:
        st.info("暂无注册用户")

# ============== 充值审核 ==============
with tab_recharge:
    status_filter = st.selectbox("筛选状态", ["all", "pending", "approved", "rejected"], format_func={
        "all": "全部", "pending": "⏳ 待审核", "approved": "✅ 已通过", "rejected": "❌ 已驳回"
    }.get)

    requests = get_all_recharge_requests(status_filter if status_filter != "all" else None, limit=50)

    if requests:
        # 按状态分组显示
        pending_list = [r for r in requests if r['status'] == 'pending']
        processed_list = [r for r in requests if r['status'] != 'pending']

        # ---- 待审核 ----
        if pending_list:
            st.markdown("### ⏳ 待审核")
            for req in pending_list:
                with st.expander(
                    f"**{req['phone']}** | {req['amount']}元 → {req['quota_requested']}次 | {req['created_at']}",
                    expanded=True
                ):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"**用户**：{req['phone']}")
                        st.markdown(f"**金额**：{req['amount']} 元")
                        st.markdown(f"**申请次数**：{req['quota_requested']} 次")
                    with col2:
                        st.markdown(f"**申请时间**：{req['created_at']}")
                        if req.get('remark'):
                            st.markdown(f"**备注**：{req['remark']}")

                    st.markdown("---")

                    # 审核操作
                    with st.form(f"approve_form_{req['id']}"):
                        c1, c2, c3 = st.columns([1, 1, 2])
                        with c1:
                            grant_quota = st.number_input(
                                "发放次数", min_value=1, max_value=100000,
                                value=req['quota_requested'],
                                key=f"grant_{req['id']}"
                            )
                        with c2:
                            admin_note = st.text_input(
                                "管理员备注（选填）",
                                key=f"note_{req['id']}"
                            )
                        with c3:
                            st.markdown("<br>", unsafe_allow_html=True)
                            bc1, bc2 = st.columns(2)
                            with bc1:
                                btn_approve = st.form_submit_button(
                                    "✅ 通过", type="primary", use_container_width=True
                                )
                            with bc2:
                                btn_reject = st.form_submit_button(
                                    "❌ 驳回", type="secondary", use_container_width=True
                                )

                        if btn_approve:
                            ok, msg = approve_recharge_request(
                                req['id'], user['id'], grant_quota, admin_note
                            )
                            if ok:
                                st.success(msg)
                            else:
                                st.error(msg)
                            st.rerun()

                        if btn_reject:
                            if not admin_note:
                                st.error("驳回时请填写原因")
                            else:
                                ok, msg = reject_recharge_request(
                                    req['id'], user['id'], admin_note
                                )
                                if ok:
                                    st.success(msg)
                                else:
                                    st.error(msg)
                                st.rerun()

            st.markdown("---")

        # ---- 已处理 ----
        if processed_list:
            st.markdown("### 📋 已处理")
            df_processed = pd.DataFrame(processed_list)
            status_map = {'approved': '✅ 通过', 'rejected': '❌ 驳回'}
            df_processed['status'] = df_processed['status'].map(status_map)
            df_processed = df_processed.rename(columns={
                'phone': '用户',
                'amount': '金额(元)',
                'quota_requested': '申请次数',
                'status': '状态',
                'admin_note': '处理说明',
                'processed_at': '处理时间',
                'created_at': '申请时间'
            })
            st.dataframe(
                df_processed[['用户', '金额(元)', '申请次数', '状态', '处理说明', '处理时间', '申请时间']],
                hide_index=True, use_container_width=True
            )
    else:
        st.info("暂无充值申请")

# ============== 系统设置 ==============
with tab_settings:
    st.markdown("### 系统配置")

    with st.form("settings_form"):
        # 新用户默认免费次数
        current_free = get_system_setting('new_user_free_quota', '100')
        new_free = st.number_input(
            "新用户注册默认免费次数",
            min_value=0,
            max_value=100000,
            value=int(current_free),
            help="新用户注册时自动赠送的免费分析次数"
        )

        # Token 过期时间
        current_expire = get_system_setting('token_expire_hours', '72')
        new_expire = st.number_input(
            "登录 Token 有效期（小时）",
            min_value=1,
            max_value=720,
            value=int(current_expire),
            help="用户登录后 Token 的有效时长"
        )

        submitted = st.form_submit_button("保存设置", type="primary", use_container_width=True)
        if submitted:
            set_system_setting('new_user_free_quota', str(new_free))
            set_system_setting('token_expire_hours', str(new_expire))
            # 清除 auth 模块的缓存
            from billing.auth import _get_system_setting
            _get_system_setting.cache_clear()
            st.success("✅ 设置已保存")
            st.rerun()

    st.markdown("---")

    # ---- 收款信息配置 ----
    st.markdown("### 💳 收款信息")

    current_payment = get_payment_info()

    with st.form("payment_form"):
        pay_method = st.text_input(
            "收款方式", value=current_payment.get('method', '微信'),
            help="如：微信、支付宝"
        )
        pay_account = st.text_input(
            "收款账号", value=current_payment.get('account', ''),
            help="收款账号或提示信息"
        )

        st.markdown("**收款二维码**（上传图片后会显示在充值页面）")
        uploaded_qr = st.file_uploader(
            "上传收款二维码",
            type=['png', 'jpg', 'jpeg'],
            key="qr_uploader"
        )

        qr_preview = ""
        if uploaded_qr:
            import base64
            qr_bytes = uploaded_qr.read()
            qr_preview = base64.b64encode(qr_bytes).decode()
            st.image(qr_bytes, width=150)

        pay_submitted = st.form_submit_button("保存收款信息", type="primary", use_container_width=True)
        if pay_submitted:
            # 未重新上传二维码时保留旧值
            final_qr = qr_preview if qr_preview else current_payment.get('qr_code', '')
            set_payment_info(pay_method, pay_account, final_qr)
            st.success("✅ 收款信息已保存")
            st.rerun()

    st.markdown("---")

    # ---- 充值方案配置 ----
    st.markdown("### 💰 充值方案")
    st.info("每行一个方案，格式：金额:次数（如 10:50 表示10元50次）")

    current_plans = get_recharge_plans()
    plans_text = "\n".join([f"{a}:{q}" for a, q in current_plans])

    new_plans_text = st.text_area(
        "充值方案",
        value=plans_text,
        height=120,
        help="每行一个，格式 金额:次数"
    )

    if st.button("保存充值方案", type="primary"):
        import json
        try:
            plans = []
            for line in new_plans_text.strip().split("\n"):
                line = line.strip()
                if not line or ':' not in line:
                    continue
                parts = line.split(':')
                amount = float(parts[0].strip())
                quota = int(parts[1].strip())
                if amount > 0 and quota > 0:
                    plans.append([amount, quota])
            if plans:
                set_system_setting('recharge_plans', json.dumps(plans))
                st.success("✅ 充值方案已保存")
                st.rerun()
            else:
                st.error("至少需要一个有效方案")
        except Exception as e:
            st.error(f"格式错误：{str(e)}")
