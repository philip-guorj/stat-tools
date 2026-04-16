# StatTools 全局CSS样式模块
# 所有页面统一引用，确保样式一致性

def get_global_css():
    """返回全局CSS样式字符串，在每个页面顶部调用 st.markdown(css, unsafe_allow_html=True)"""
    return """
<style>
/* ========== 基础布局 ========== */
.stApp {
    max-width: 1400px;
    margin: 0 auto;
}

/* ========== 页面标题 ========== */
.main-header {
    font-size: 2.2rem;
    font-weight: 800;
    color: #1a56db;
    text-align: center;
    padding: 0.8rem 0 0.3rem 0;
    letter-spacing: 1px;
    text-shadow: 0 1px 2px rgba(0,0,0,0.05);
}

/* ========== 章节标题（每个页面使用） ========== */
.section-header {
    font-size: 1.4rem;
    font-weight: 700;
    color: #1e3a5f;
    border-left: 4px solid #3b82f6;
    padding-left: 0.75rem;
    margin-top: 1.2rem;
    margin-bottom: 0.8rem;
}

/* ========== 子标题 ========== */
.sub-header {
    font-size: 1.1rem;
    font-weight: 600;
    color: #374151;
    margin-top: 1rem;
    margin-bottom: 0.5rem;
    border-bottom: 1px solid #e5e7eb;
    padding-bottom: 0.3rem;
}

/* ========== 功能简介卡片 ========== */
[data-testid="stExpander"] {
    border: 1px solid #e0e7ff;
    border-radius: 8px;
    background-color: #f0f4ff;
}

[data-testid="stExpander"] summary {
    font-weight: 600;
    color: #3730a3;
}

/* ========== 数据表格美化 ========== */
[data-testid="stDataFrame"] {
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}

/* ========== 指标卡片 ========== */
[data-testid="stMetric"] {
    background-color: #f9fafb;
    border-radius: 8px;
    padding: 12px 16px;
    border-left: 3px solid #3b82f6;
}

/* ========== 按钮美化 ========== */
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);
    border: none;
    border-radius: 8px;
    font-weight: 600;
    padding: 0.5rem 1.5rem;
    transition: all 0.2s;
}

.stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%);
    box-shadow: 0 4px 12px rgba(37,99,235,0.3);
}

/* ========== 侧边栏美化 ========== */
[data-testid="stSidebar"] {
    background-color: #f8fafc;
}

[data-testid="stSidebar"] [data-testid="stSidebarNav"] {
    gap: 2px;
}

/* ========== Tab 美化 ========== */
.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
}

.stTabs [data-baseweb="tab"] {
    border-radius: 8px 8px 0 0;
    font-weight: 500;
    padding: 8px 16px;
}

.stTabs [aria-selected="true"] {
    background-color: #e0e7ff;
    color: #1e40af;
}

/* ========== 提示框美化 ========== */
[data-testid="stAlert"] {
    border-radius: 8px;
}

/* ========== 选择框美化 ========== */
.stSelectbox > div > div {
    border-radius: 6px;
}

/* ========== 分隔线 ========== */
hr {
    margin: 1rem 0;
    border: none;
    border-top: 1px solid #e5e7eb;
}

/* ========== 方法选择指南样式 ========== */
.method-guide {
    background: linear-gradient(135deg, #eff6ff 0%, #f0f4ff 100%);
    border-left: 4px solid #6366f1;
    border-radius: 0 8px 8px 0;
    padding: 1rem 1.2rem;
    margin: 0.5rem 0;
}

.method-guide-title {
    font-size: 1rem;
    font-weight: 700;
    color: #312e81;
    margin-bottom: 0.5rem;
}

.method-guide-content {
    font-size: 0.9rem;
    color: #374151;
    line-height: 1.6;
}

/* ========== 代码块美化 ========== */
.stCodeBlock {
    border-radius: 6px;
    font-size: 0.85rem;
}
</style>
"""


def inject_css():
    """便捷函数：在页面顶部调用即可注入全局CSS"""
    import streamlit as st
    st.markdown(get_global_css(), unsafe_allow_html=True)
