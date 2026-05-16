# billing/auth.py - 用户认证模块
"""
手机号+密码的注册/登录机制。

认证方案（数据库会话 + 双存储）：
- 登录时在数据库 user_sessions 表创建会话记录
- session_token 写入 st.query_params（URL 持久化，刷新不丢失）
- session_state 作为可选缓存（加速读取，丢失不影响功能）

get_current_user() 恢复策略：
1. session_state['current_user']（缓存命中，直接用）
2. st.query_params['token'] → 查数据库 user_sessions → 有效则恢复用户信息
3. 无有效会话 → None
"""

import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta
from functools import lru_cache

import streamlit as st

from billing.database import fetch_one, execute_query, fetch_all, get_connection


# ---- HMAC 签名密钥（从数据库读取，首次运行自动生成） ----

def _get_hmac_secret() -> bytes:
    """获取或生成 HMAC 签名密钥"""
    row = fetch_one("SELECT value FROM system_settings WHERE key = 'hmac_secret'")
    if row:
        return row['value'].encode()
    secret = secrets.token_hex(32)
    execute_query(
        "INSERT OR REPLACE INTO system_settings (key, value) VALUES ('hmac_secret', ?)",
        (secret,)
    )
    return secret.encode()


# ---- 密码哈希 ----

def _hash_password(password: str, salt: str) -> str:
    """SHA-256 + 盐值 哈希密码"""
    return hashlib.sha256((password + salt).encode()).hexdigest()


def _verify_password(password: str, password_hash: str, salt: str) -> bool:
    """验证密码"""
    return _hash_password(password, salt) == password_hash


# ---- 数据库会话管理（核心） ----

def _create_session(user_id: int) -> str:
    """
    在数据库创建登录会话，返回 session_token。
    同时清理该用户的旧会话（单设备登录）。
    """
    expire_hours = int(_get_system_setting('session_expire_hours', '72'))
    expires_at = (datetime.now() + timedelta(hours=expire_hours)).strftime('%Y-%m-%d %H:%M:%S')
    token = secrets.token_urlsafe(32)

    # 删除该用户的旧会话（保持单设备登录）
    execute_query("DELETE FROM user_sessions WHERE user_id = ?", (user_id,))

    # 创建新会话
    execute_query(
        """INSERT INTO user_sessions (user_id, session_token, expires_at, last_active_at)
           VALUES (?, ?, ?, datetime('now','localtime'))""",
        (user_id, token, expires_at)
    )
    return token


def _validate_session(token: str) -> dict | None:
    """
    验证 session_token，返回用户信息 dict 或 None。
    流程：查 user_sessions → 检查过期 → 更新最后活跃时间 → 查用户信息
    """
    if not token:
        return None

    session = fetch_one(
        """SELECT * FROM user_sessions
           WHERE session_token = ? AND expires_at > datetime('now','localtime')""",
        (token,)
    )
    if not session:
        return None

    user_id = session['user_id']

    # 更新最后活跃时间
    execute_query(
        "UPDATE user_sessions SET last_active_at = datetime('now','localtime') WHERE id = ?",
        (session['id'],)
    )

    # 查用户信息
    user = fetch_one(
        "SELECT id, phone, nickname, organization, free_quota, paid_quota, role, status, created_at FROM users WHERE id = ?",
        (user_id,)
    )
    if user and user['status'] != 'banned':
        return dict(user)
    return None


def _destroy_session(token: str):
    """删除数据库中的会话记录"""
    if token:
        execute_query("DELETE FROM user_sessions WHERE session_token = ?", (token,))


def _cleanup_expired_sessions():
    """清理过期会话（低频调用）"""
    execute_query(
        "DELETE FROM user_sessions WHERE expires_at < datetime('now','localtime')"
    )


# ---- 用户操作 ----

def register_user(phone: str, password: str, nickname: str = '', organization: str = '') -> tuple[bool, str]:
    """
    注册新用户。
    返回 (成功?, 消息)。
    注册成功自动赠送免费次数（从 system_settings 读取默认值）。
    """
    phone = phone.strip()
    if not phone or len(phone) < 7:
        return False, "手机号格式不正确"
    if not password or len(password) < 6:
        return False, "密码长度不能少于6位"

    existing = fetch_one("SELECT id FROM users WHERE phone = ?", (phone,))
    if existing:
        return False, "该手机号已注册"

    salt = secrets.token_hex(16)
    pw_hash = _hash_password(password, salt)
    default_quota = int(_get_system_setting('new_user_free_quota', '100'))

    try:
        execute_query(
            """INSERT INTO users (phone, password_hash, salt, nickname, organization, free_quota)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (phone, pw_hash, salt, nickname.strip(), organization.strip(), default_quota)
        )
        return True, f"注册成功！已赠送 {default_quota} 次免费分析。"
    except Exception as e:
        return False, f"注册失败：{str(e)}"


def login_user(phone: str, password: str) -> tuple[bool, str, str | None]:
    """
    用户登录。
    返回 (成功?, 消息, session_token)。
    成功时：创建数据库会话 + 写入 session_state + 写入 query_params。
    """
    phone = phone.strip()
    user = fetch_one("SELECT * FROM users WHERE phone = ?", (phone,))
    if not user:
        return False, "手机号或密码错误", None
    if user['status'] == 'banned':
        return False, "账号已被封禁，请联系管理员", None

    if not _verify_password(password, user['password_hash'], user['salt']):
        return False, "手机号或密码错误", None

    if user['role'] != 'admin':
        if user['status'] != 'active':
            return False, "账号状态异常，请联系管理员", None

    # 查最新用户信息
    user_info = fetch_one(
        "SELECT id, phone, nickname, organization, free_quota, paid_quota, role, status, created_at FROM users WHERE id = ?",
        (user['id'],)
    )
    if not user_info:
        return False, "用户信息异常", None

    # 创建数据库会话
    token = _create_session(user_info['id'])

    # 写入 session_state（缓存，不可靠但快）
    st.session_state['current_user'] = dict(user_info)
    st.session_state['auth_token'] = token

    # 写入 query_params（URL 持久化，最可靠）
    st.query_params['token'] = token

    # 通过 JS 写入 localStorage（防 query_params 被清除的兜底）
    _save_token_to_localstorage(token)

    # 更新最后登录时间
    execute_query(
        "UPDATE users SET last_login = datetime('now','localtime') WHERE id = ?",
        (user['id'],)
    )

    return True, "登录成功", token


def logout_user(clear_data_cache: bool = False):
    """退出登录：清除数据库会话 + session_state + query_params + localStorage
    clear_data_cache: 是否同时清除该用户的数据缓存（内存+磁盘）
    """
    # 先获取 user_id（清除 session_state 之前）
    user = st.session_state.get('current_user')
    user_id = user['id'] if user else None

    # 清除数据库会话
    token = st.session_state.get('auth_token') or st.query_params.get('token')
    _destroy_session(token)

    # 可选：清除该用户的数据缓存文件
    if clear_data_cache and user_id is not None:
        try:
            from utils.data_manager import get_data_manager
            dm = get_data_manager(user_id)
            dm.clear_data()
            dm.clear_cache_files()
        except Exception:
            pass  # 退出时不要因为缓存清理失败而阻塞

    # 清除 session_state
    for key in ['current_user', 'auth_token']:
        if key in st.session_state:
            del st.session_state[key]

    # 清除 URL 中的 token
    if 'token' in st.query_params:
        del st.query_params['token']

    # 清除 localStorage 中的 token
    clear_token_localstorage()


def change_password(user_id: int, old_password: str, new_password: str) -> tuple[bool, str]:
    """
    修改密码。
    返回 (成功?, 消息)。
    """
    if not new_password or len(new_password) < 6:
        return False, "新密码长度不能少于6位"

    user = fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))
    if not user:
        return False, "用户不存在"

    if not _verify_password(old_password, user['password_hash'], user['salt']):
        return False, "原密码错误"

    new_hash = _hash_password(new_password, user['salt'])
    execute_query("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user_id))

    # 修改密码后销毁所有会话（强制重新登录）
    execute_query("DELETE FROM user_sessions WHERE user_id = ?", (user_id,))

    return True, "密码修改成功，请重新登录"


def update_user_profile(user_id: int, nickname: str = '', organization: str = '') -> tuple[bool, str]:
    """
    更新用户姓名和单位。
    返回 (成功?, 消息)。
    """
    execute_query(
        "UPDATE users SET nickname = ?, organization = ? WHERE id = ?",
        (nickname.strip(), organization.strip(), user_id)
    )
    # 同步更新 session_state 缓存
    if 'current_user' in st.session_state and st.session_state['current_user'].get('id') == user_id:
        st.session_state['current_user']['nickname'] = nickname.strip()
        st.session_state['current_user']['organization'] = organization.strip()
    return True, "个人信息已更新"


def delete_account(user_id: int) -> tuple[bool, str]:
    """
    注销账号：删除用户及相关数据。
    返回 (成功?, 消息)。
    注意：这是不可逆操作。
    """
    # 先删除相关数据
    execute_query("DELETE FROM billing_logs WHERE user_id = ?", (user_id,))
    execute_query("DELETE FROM redeem_codes WHERE used_by = ?", (user_id,))
    execute_query("DELETE FROM user_sessions WHERE user_id = ?", (user_id,))
    execute_query("DELETE FROM users WHERE id = ?", (user_id,))

    return True, "账号已注销"


def get_current_user() -> dict | None:
    """
    获取当前用户信息。
    数据库会话为唯一可信源，session_state 只做缓存。

    恢复策略：
    1. session_state 缓存（最快，但不可靠）
    2. query_params token → 数据库验证（可靠，刷新后仍可用）
    3. JS 回写机制（通过 st.html 注入 JS，从 localStorage 恢复 token 到 URL）
    """
    # 第1层：session_state 缓存
    if 'current_user' in st.session_state and st.session_state['current_user'] is not None:
        return st.session_state['current_user']

    # 第2层：从 query_params 获取 token，查数据库会话
    token = st.query_params.get('token')
    if token:
        user = _validate_session(token)
        if user:
            # 恢复到 session_state 缓存
            st.session_state['current_user'] = user
            st.session_state['auth_token'] = token
            return user

    # 第3层：尝试从数据库获取最近的活跃会话（兜底）
    # 仅限最近 30 分钟内有活动的会话（安全性考虑，防止跨设备/跨用户误用）
    # 当 session_state 丢失且 query_params 被 switch_page 清除时的最后防线
    if '_session_restored' not in st.session_state:
        st.session_state['_session_restored'] = True
        latest_session = fetch_one(
            """SELECT s.*, u.id as uid, u.phone, u.nickname, u.organization, u.free_quota, 
                      u.paid_quota, u.role, u.status, u.created_at
               FROM user_sessions s
               JOIN users u ON s.user_id = u.id
               WHERE s.expires_at > datetime('now','localtime')
                 AND s.last_active_at > datetime('now','localtime','-30 minutes')
               ORDER BY s.last_active_at DESC LIMIT 1"""
        )
        if latest_session and latest_session['status'] != 'banned':
            user_info = {k: latest_session[k] for k in 
                        ['uid', 'phone', 'nickname', 'organization', 'free_quota', 'paid_quota', 'role', 'status', 'created_at']}
            user_info['id'] = user_info.pop('uid')
            token_to_use = latest_session['session_token']
            st.session_state['current_user'] = user_info
            st.session_state['auth_token'] = token_to_use
            st.query_params['token'] = token_to_use
            return user_info

    return None


# ---- 图形验证码 ----

def _generate_captcha_image() -> tuple[str, bytes]:
    """
    生成验证码图片，返回 (code, image_bytes)。
    """
    import random
    import string
    from captcha.image import ImageCaptcha

    chars = string.digits + string.ascii_uppercase
    chars = chars.replace('O', '').replace('0', '').replace('I', '').replace('1', '').replace('l', '')
    code = ''.join(random.choices(chars, k=4))

    image = ImageCaptcha(width=160, height=60)
    data = image.generate(code)
    img_bytes = data.read()

    return code.lower(), img_bytes


def render_captcha_image() -> bytes | None:
    """
    渲染验证码图片（用 st.image，避免 base64 HTML 被截断）。
    返回 None，图片直接显示在页面上。
    """
    try:
        # 检查是否需要刷新验证码
        if st.session_state.get('_captcha_needs_refresh'):
            del st.session_state['_captcha_needs_refresh']
            code, img_bytes = _generate_captcha_image()
            st.session_state['_captcha_code'] = code
            st.session_state['_captcha_img_bytes'] = img_bytes

        # 首次生成验证码
        elif '_captcha_code' not in st.session_state:
            code, img_bytes = _generate_captcha_image()
            st.session_state['_captcha_code'] = code
            st.session_state['_captcha_img_bytes'] = img_bytes

        # 用 st.image 直接渲染（不会被截断）
        st.image(st.session_state['_captcha_img_bytes'], width=160)
        return st.session_state['_captcha_img_bytes']

    except ImportError:
        st.warning("验证码模块未安装，请运行: pip install captcha")
        return None


def render_captcha_input(label: str = "请输入验证码") -> str:
    """
    渲染验证码输入框（放在 st.form 内部使用）。
    返回用户输入的验证码字符串。
    """
    user_input = st.text_input(label, key="captcha_input", label_visibility="visible")
    if user_input:
        return user_input.strip().lower()
    return ""




def verify_captcha(user_input: str) -> bool:
    """验证用户输入的验证码"""
    if not user_input:
        return False
    stored = st.session_state.get('_captcha_code', '')
    return user_input.strip().lower() == stored


def refresh_captcha():
    """标记需要刷新验证码"""
    st.session_state['_captcha_needs_refresh'] = True


# ---- 系统设置读取 ----

@lru_cache(maxsize=32)
def _get_system_setting(key: str, default: str = None) -> str:
    """获取系统设置（带缓存）"""
    row = fetch_one("SELECT value FROM system_settings WHERE key = ?", (key,))
    if row:
        return row['value']
    return default or ''


# ---- JS localStorage 辅助（Token 持久化的终极兜底） ----

def _save_token_to_localstorage(token: str):
    """通过 JS 将 token 保存到浏览器 localStorage"""
    import streamlit.components.v1 as components
    js_code = f'''
    <script>
    try {{
        localStorage.setItem('stattls_auth_token', '{token}');
    }} catch(e) {{ console.error('localStorage error:', e); }}
    </script>
    '''
    components.html(js_code, height=0, width=0)


def clear_token_localstorage():
    """通过 JS 清除 localStorage 中的 token"""
    import streamlit.components.v1 as components
    js_code = '''
    <script>
    try {
        localStorage.removeItem('stattls_auth_token');
    } catch(e) { console.error('localStorage error:', e); }
    </script>
    '''
    components.html(js_code, height=0, width=0)


def inject_token_from_localstorage():
    """
    注入 JS：从 localStorage 读取 token，如果没有就在 URL 的 query_params 中。
    如果 URL 中也没有 token 但 localStorage 有，就重定向到带 token 的 URL。
    返回 True 表示需要等待 JS 执行（页面会被重定向）。
    """
    import streamlit.components.v1 as components
    js_code = '''
    <script>
    (function() {
        var token = localStorage.getItem('stattls_auth_token');
        if (token) {
            var params = new URLSearchParams(window.location.search);
            if (!params.get('token')) {
                params.set('token', token);
                window.location.href = window.location.pathname + '?' + params.toString();
                return;
            }
        }
    })();
    </script>
    '''
    components.html(js_code, height=0, width=0)
