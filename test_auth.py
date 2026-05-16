# 最小测试：验证 session_state 在页面切换时是否保留
import streamlit as st

st.set_page_config(page_title="Auth Test", page_icon="🔐")

if "test_counter" not in st.session_state:
    st.session_state.test_counter = 0

st.session_state.test_counter += 1

st.write(f"## session_state 测试")
st.write(f"**当前 counter**: {st.session_state.test_counter}")
st.write(f"**URL query_params**: {dict(st.query_params)}")

if "current_user" in st.session_state:
    st.success(f"✅ 用户已登录: {st.session_state['current_user']}")
else:
    st.warning("❌ 未登录")

token = st.query_params.get("token")
st.write(f"**URL 中的 token**: {token[:20] + '...' if token and len(token) > 20 else token}")

if st.button("模拟写入 session_state"):
    st.session_state['current_user'] = "测试用户"
    st.rerun()

if st.button("模拟写入 query_params"):
    st.query_params['token'] = "test_token_abc123"
    st.rerun()

if st.button("模拟登录（同时写入两个）"):
    st.session_state['current_user'] = "测试用户"
    st.query_params['token'] = "test_token_abc123"
    st.rerun()

if st.button("清除所有"):
    if "current_user" in st.session_state:
        del st.session_state["current_user"]
    if "token" in st.query_params:
        del st.query_params["token"]
    st.rerun()
