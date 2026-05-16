# StatTools - 田间试验统计分析平台
# 主应用入口（路由器）

import streamlit as st

# ---- 全局配置（必须在所有 st 函数之前） ----
st.set_page_config(
    page_title="StatTools - 田间试验统计分析",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

from utils.styles import inject_css, inject_upload_i18n, inject_nav_separator
from billing.billing import get_user_quota
from billing.auth import get_current_user

# ---- 启动时确保存在管理员账号（HF Spaces 首次部署自动初始化） ----
def _ensure_admin():
    """若没有任何管理员账号，自动创建一个（凭据优先读 st.secrets，否则用默认值）"""
    try:
        from billing.database import fetch_one, execute_query
        import secrets, hashlib

        admin = fetch_one("SELECT id FROM users WHERE role = 'admin'")
        if admin is not None:
            return

        # 从 st.secrets 读取凭据，或用默认值
        try:
            phone = st.secrets["admin"]["phone"]
            password = st.secrets["admin"]["password"]
        except Exception:
            phone = "13800138000"
            password = "admin123"

        salt = secrets.token_hex(16)
        pw_hash = hashlib.sha256((password + salt).encode()).hexdigest()
        execute_query(
            "INSERT INTO users (phone, password_hash, salt, role, free_quota, paid_quota) "
            "VALUES (?, ?, ?, 'admin', 9999, 9999)",
            (phone, pw_hash, salt)
        )
        print(f"[INIT] 已自动创建管理员账号：手机号={phone} 密码={password}")
    except Exception as e:
        print(f"[INIT] 管理员自动初始化失败：{e}")

_ensure_admin()


# ---- 登录页面函数（未登录时显示） ----
def _login_page():
    """登录/注册表单，包装为 page 函数"""
    from billing.billing import require_auth
    require_auth()


# ---- 辅助函数 ----
def _current_data_filename(user_id: int) -> str:
    """获取用户当前数据文件名"""
    try:
        from utils.data_manager import get_data_manager
        dm = get_data_manager(user_id)
        return dm.filename if (dm.is_loaded and dm.filename) else '未上传'
    except Exception:
        return '未上传'


# ---- 退出快速退出页面函数（导航菜单项） ----
def _logout_page():
    """侧边栏快速退出：不清除数据缓存，直接退出登录"""
    from billing.auth import logout_user
    logout_user(clear_data_cache=False)
    st.rerun()


# ---- 注入全局CSS ----
inject_css()
inject_upload_i18n()
inject_nav_separator()

# ---- 获取当前用户（不触发 require_auth，避免 st.stop） ----
user = get_current_user()

if user:
    # ======== 已登录 ========

    # ---- 页面顶部用户信息栏 ----
    quota = get_user_quota()
    phone = user['phone']
    nickname = user.get('nickname') or ''
    display_name = nickname if nickname else (phone[:3] + "****" + phone[-4:] if len(phone) >= 7 else phone)
    if user['role'] == 'admin':
        display_name += " 🛡️"
    last_login = user.get('last_login', '')
    if not last_login:
        from billing.database import fetch_one
        row = fetch_one("SELECT last_login FROM users WHERE id = ?", (user['id'],))
        last_login = row['last_login'] if row else ''

    st.markdown(f"""
    <div class="topbar-infobar" style="display:flex;align-items:center;justify-content:space-between;
                padding:6px 16px;background:#f8fafc;border-bottom:1px solid #e2e8f0;
                border-radius:6px;margin-bottom:8px;font-size:0.85rem;">
        <span><b>👤 {display_name}</b></span>
        <span>📊 免费次数: <b>{quota['free']}</b> &nbsp;|&nbsp; 付费次数: <b>{quota['paid']}</b></span>
        <span>🕐 上次登录: {last_login[:16] if last_login else '首次登录'}</span>
        <span>📂 <b>当前数据</b>：{_current_data_filename(user['id'])}</span>
    </div>
    """, unsafe_allow_html=True)

    # ---- 动态构建页面列表（扁平，分割线由 inject_nav_separator 插入） ----
    pages = [
        st.Page("pages/home.py", title="首页", icon="📊"),
        st.Page("pages/01_描述统计.py", title="描述统计", icon="📋"),
        st.Page("pages/02_假设检验.py", title="假设检验", icon="🔬"),
        st.Page("pages/03_方差分析.py", title="方差分析", icon="📐"),
        st.Page("pages/04_回归分析.py", title="回归分析", icon="📈"),
        st.Page("pages/05_多变量分析.py", title="多变量分析", icon="🧬"),
        st.Page("pages/06_数据可视化.py", title="数据可视化", icon="🎨"),
        st.Page("pages/07_试验设计.py", title="试验设计", icon="🎯"),
        st.Page("pages/10_区试报告.py", title="区试报告", icon="📋"),
        st.Page("pages/08_用户中心.py", title="用户中心", icon="👤"),
        st.Page(_logout_page, title="快速退出", icon="🚪"),
    ]

    # 管理后台仅管理员可见
    if user['role'] == 'admin':
        pages.insert(-1, st.Page("pages/09_管理后台.py", title="管理后台", icon="⚙️"))

    pg = st.navigation(pages)
    pg.run()

else:
    # ======== 未登录：只显示登录页 ========
    pg = st.navigation([st.Page(_login_page, title="登录", icon="🔐")])
    pg.run()
