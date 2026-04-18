# StatTools 全局CSS样式模块
# 所有页面统一引用，确保样式一致性

import streamlit as st


@st.cache_resource
def _get_css_cached() -> str:
    """返回全局CSS样式字符串（缓存，仅生成一次）"""
    return """
<style>
/* ========== 基础布局 ========== */
.stApp {
    max-width: 1440px;
    margin: 0 auto;
    background-color: #f8fafc;
}

/* ========== 页面标题 ========== */
.main-header {
    font-size: 2rem;
    font-weight: 800;
    background: linear-gradient(135deg, #1e40af 0%, #3b82f6 50%, #06b6d4 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    text-align: center;
    padding: 1rem 0 0.4rem 0;
    letter-spacing: 0.5px;
}

/* ========== 章节标题 ========== */
.section-header {
    font-size: 1.35rem;
    font-weight: 700;
    color: #1e293b;
    border-left: 4px solid #3b82f6;
    padding: 0.3rem 0 0.3rem 0.75rem;
    margin-top: 1.2rem;
    margin-bottom: 0.8rem;
    background: linear-gradient(90deg, rgba(59,130,246,0.06) 0%, transparent 100%);
    border-radius: 0 6px 6px 0;
}

/* ========== 子标题 ========== */
.sub-header {
    font-size: 1.05rem;
    font-weight: 600;
    color: #334155;
    margin-top: 1rem;
    margin-bottom: 0.5rem;
    border-bottom: 2px solid #e2e8f0;
    padding-bottom: 0.3rem;
}

/* ========== Expander 美化 ========== */
[data-testid="stExpander"] {
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    background-color: #ffffff;
    box-shadow: 0 1px 4px rgba(0,0,0,0.04);
    margin-bottom: 0.5rem;
}

[data-testid="stExpander"] summary {
    font-weight: 600;
    color: #1e40af;
    border-radius: 10px;
}

[data-testid="stExpander"] summary:hover {
    background-color: #eff6ff;
}

/* ========== 数据表格美化 ========== */
[data-testid="stDataFrame"] {
    border-radius: 10px;
    overflow: hidden;
    box-shadow: 0 2px 8px rgba(0,0,0,0.07);
    border: 1px solid #e2e8f0;
}

/* ========== 指标卡片 ========== */
[data-testid="stMetric"] {
    background: #ffffff;
    border-radius: 10px;
    padding: 12px 16px;
    border: 1px solid #e2e8f0;
    border-left: 3px solid #3b82f6;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05);
    transition: box-shadow 0.2s;
}

[data-testid="stMetric"]:hover {
    box-shadow: 0 4px 12px rgba(59,130,246,0.12);
}

/* ========== 按钮美化 ========== */
.stButton > button {
    border-radius: 8px;
    font-weight: 500;
    transition: all 0.2s;
}

.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);
    border: none;
    font-weight: 600;
    padding: 0.5rem 1.5rem;
    box-shadow: 0 2px 6px rgba(59,130,246,0.25);
}

.stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%);
    box-shadow: 0 4px 14px rgba(37,99,235,0.35);
    transform: translateY(-1px);
}

/* ========== 侧边栏美化 ========== */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
    border-right: 1px solid #e2e8f0;
}

[data-testid="stSidebar"] [data-testid="stSidebarNav"] a {
    border-radius: 8px;
    margin: 2px 4px;
    transition: background 0.15s;
}

[data-testid="stSidebar"] [data-testid="stSidebarNav"] a:hover {
    background-color: #dbeafe;
}

/* ========== Tab 美化 ========== */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    background-color: #f1f5f9;
    border-radius: 10px;
    padding: 4px;
}

.stTabs [data-baseweb="tab"] {
    border-radius: 8px;
    font-weight: 500;
    padding: 6px 14px;
    transition: all 0.15s;
}

.stTabs [aria-selected="true"] {
    background-color: #ffffff;
    color: #1e40af;
    box-shadow: 0 1px 4px rgba(0,0,0,0.10);
}

/* ========== 提示框美化 ========== */
[data-testid="stAlert"] {
    border-radius: 10px;
}

/* ========== 选择框、输入框美化 ========== */
.stSelectbox > div > div,
.stMultiSelect > div > div,
.stTextInput > div > div {
    border-radius: 8px;
}

/* ========== 分隔线 ========== */
hr {
    margin: 1.2rem 0;
    border: none;
    border-top: 1px solid #e2e8f0;
}

/* ========== 方法选择指南样式 ========== */
.method-guide {
    background: linear-gradient(135deg, #eff6ff 0%, #f0fdf4 100%);
    border-left: 4px solid #6366f1;
    border-radius: 0 10px 10px 0;
    padding: 1rem 1.2rem;
    margin: 0.6rem 0;
}

.method-guide-title {
    font-size: 0.95rem;
    font-weight: 700;
    color: #312e81;
    margin-bottom: 0.5rem;
}

.method-guide-content {
    font-size: 0.88rem;
    color: #374151;
    line-height: 1.7;
}

/* ========== 代码块美化 ========== */
.stCodeBlock {
    border-radius: 8px;
    font-size: 0.84rem;
}

/* ========== 文件上传区域 ========== */
[data-testid="stFileUploaderDropzone"] {
    border-radius: 10px;
    border: 2px dashed #93c5fd;
    background: #eff6ff;
}

[data-testid="stFileUploaderDropzone"]:hover {
    border-color: #3b82f6;
    background: #dbeafe;
}

/* ========== 图表容器 ========== */
[data-testid="stPlotlyChart"] {
    border-radius: 10px;
    overflow: hidden;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

/* ========== 数据卡片容器（自定义） ========== */
.stat-card {
    background: #ffffff;
    border-radius: 10px;
    padding: 1rem 1.2rem;
    border: 1px solid #e2e8f0;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05);
    margin-bottom: 0.5rem;
}

/* ========== spinner / 加载状态 ========== */
[data-testid="stSpinner"] {
    color: #3b82f6;
}
</style>
"""


def get_global_css() -> str:
    """返回全局CSS样式字符串（兼容旧接口，内部走缓存）"""
    return _get_css_cached()


def inject_css():
    """在当前页面注入全局CSS（推荐使用此函数，自动走缓存）"""
    st.markdown(_get_css_cached(), unsafe_allow_html=True)
