# StatTools 访问日志记录器
# 记录页面访问量、访客IP和访问时间到CSV文件

import os
import csv
import threading
import urllib.request
import json
from datetime import datetime

import streamlit as st

_lock = threading.Lock()
_log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")

# IP地区查询结果缓存，避免重复查询同一IP
_region_cache: dict[str, str] = {}


def _get_log_path():
    """获取日志文件路径，按月归档"""
    os.makedirs(_log_dir, exist_ok=True)
    filename = f"visitor_{datetime.now().strftime('%Y%m')}.csv"
    return os.path.join(_log_dir, filename)


def _ensure_header(path):
    """确保CSV文件有表头"""
    if not os.path.exists(path):
        with open(path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(["访问时间", "IP地址", "IP地址所属地区", "页面"])


def _get_ip_region(ip: str) -> str:
    """通过 ip-api.com 查询IP所属地区（免费，无需API Key）

    Args:
        ip: IP地址字符串

    Returns:
        地区字符串，如"中国 北京"；查询失败返回"未知"
    """
    if not ip or ip in ("本地访问", "未知", "localhost", "127.0.0.1"):
        return "本地"

    if ip in _region_cache:
        return _region_cache[ip]

    try:
        url = f"http://ip-api.com/json/{ip}?lang=zh-CN&fields=status,country,regionName,city"
        req = urllib.request.Request(url, headers={"User-Agent": "StatTools/1.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("status") == "success":
            parts = [data.get("country", ""), data.get("regionName", ""), data.get("city", "")]
            region = " ".join(p for p in parts if p)
        else:
            region = "未知"
    except Exception:
        region = "未知"

    _region_cache[ip] = region
    return region


def log_visit(page: str = "首页"):
    """记录一次页面访问
    
    Args:
        page: 访问的页面名称，默认"首页"
    """
    try:
        path = _get_log_path()
        ip = _get_client_ip()
        region = _get_ip_region(ip)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with _lock:
            _ensure_header(path)
            with open(path, 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([timestamp, ip, region, page])
    except Exception:
        # 日志记录失败不应影响主程序
        pass


@st.cache_data(ttl=60)
def get_visitor_stats():
    """获取访问统计摘要（缓存60秒，避免每次rerun重读CSV）
    
    Returns:
        dict: {"总访问量": N, "今日访问": N, "独立IP数": N, "日志文件": path}
    """
    stats = {"总访问量": 0, "今日访问": 0, "独立IP数": 0, "日志文件": ""}
    
    path = _get_log_path()
    if not os.path.exists(path):
        return stats
    
    stats["日志文件"] = path
    today = datetime.now().strftime("%Y-%m-%d")
    ips = set()
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                stats["总访问量"] += 1
                ip = row.get("IP地址", "")
                if ip:
                    ips.add(ip)
                if row.get("访问时间", "").startswith(today):
                    stats["今日访问"] += 1
        stats["独立IP数"] = len(ips)
    except Exception:
        pass
    
    return stats


def _get_client_ip() -> str:
    """获取客户端IP地址
    
    优先级：X-Forwarded-For > X-Real-Ip
    """
    try:
        import streamlit as st
        headers = st.context.headers
        ip = headers.get("X-Forwarded-For", "").split(",")[0].strip()
        if ip:
            return ip
        ip = headers.get("X-Real-Ip", "").strip()
        if ip:
            return ip
        # 回退：尝试直接连接地址
        ip = headers.get("Host", "").split(":")[0]
        if ip and ip not in ("localhost", "127.0.0.1", ""):
            return ip
        return "本地访问"
    except Exception:
        return "未知"


def render_sidebar_stats():
    """在侧边栏底部渲染访问统计（公共组件）"""
    stats = get_visitor_stats()
    if stats["总访问量"] > 0:
        st.sidebar.caption("📊 访问统计")
        st.sidebar.caption(f"总访问: {stats['总访问量']}")
        st.sidebar.caption(f"今日: {stats['今日访问']}")
        st.sidebar.caption(f"访客: {stats['独立IP数']}")
