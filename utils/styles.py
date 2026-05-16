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

/* 主内容区宽度稳定 */
[data-testid="stMainBlockContainer"] {
    max-width: 1360px;
    padding: 0 2rem;
}

/* 侧边栏后内容区自适应 */
section[data-testid="stMain"] {
    max-width: 1360px;
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

/* ========== 方法子标题（### 🎯 等） ========== */
.streamlit-expanderHeader,
h3 {
    margin-top: 1.5rem;
    margin-bottom: 0.3rem;
}

/* ========== Info 帮助提示框 - 统一视觉 ========== */
[data-testid="stAlert"][data-testid*="info"] {
    background-color: #f0f9ff !important;
    border: 1px solid #bae6fd;
    border-left: 4px solid #0ea5e9;
    border-radius: 8px;
    padding: 0.8rem 1rem;
    margin-bottom: 0.8rem;
}

/* info 提示框内文字优化 */
[data-testid="stAlert"]:has([data-testid="stAlertContentInfo"]) p {
    font-size: 0.9rem;
    line-height: 1.65;
    color: #1e3a5f;
}

/* info 提示框加粗文字 */
[data-testid="stAlert"]:has([data-testid="stAlertContentInfo"]) strong,
[data-testid="stAlert"]:has([data-testid="stAlertContentInfo"]) b {
    color: #0c4a6e;
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

/* ========== 提示框统一美化 ========== */
[data-testid="stAlert"] {
    border-radius: 10px;
}

/* Warning 提示框 */
[data-testid="stAlert"][data-testid*="warning"] {
    background-color: #fffbeb !important;
    border: 1px solid #fde68a;
    border-left: 4px solid #f59e0b;
}

/* Error 提示框 */
[data-testid="stAlert"][data-testid*="error"] {
    background-color: #fef2f2 !important;
    border: 1px solid #fecaca;
    border-left: 4px solid #ef4444;
}

/* Success 提示框 */
[data-testid="stAlert"][data-testid*="success"] {
    background-color: #f0fdf4 !important;
    border: 1px solid #bbf7d0;
    border-left: 4px solid #22c55e;
}

/* ========== 选择框、输入框美化 ========== */
.stSelectbox > div > div,
.stMultiSelect > div > div,
.stTextInput > div > div,
.stSlider > div > div {
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

/* file_uploader label 不强制换行 */
[data-testid="stFileUploader"] > label > p,
[data-testid="stFileUploader"] label > p {
    white-space: nowrap;
}

/* ========== 图表容器 ========== */
[data-testid="stPlotlyChart"] {
    border-radius: 10px;
    overflow: hidden;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    min-height: 350px;
}

/* plotly 内部统一画布 */
.js-plotly-plot .plotly .modebar {
    top: 4px !important;
    right: 4px !important;
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

/* ========== 区块间距优化 ========== */
.streamlit-container > div > div > div > div {
    gap: 0.3rem;
}

/* 方法说明区块(st.info)与表单控件间增加间距 */
[data-testid="stAlert"] + [data-testid="stSelectbox"],
[data-testid="stAlert"] + [data-testid="stMultiSelect"],
[data-testid="stAlert"] + [data-testid="stNumberInput"],
[data-testid="stAlert"] + [data-testid="stCheckbox"] {
    margin-top: 0.5rem;
}

/* ========== spinner / 加载状态 ========== */
[data-testid="stSpinner"] {
    color: #3b82f6;
}

/* ========== 整体区块容器 - 增加卡片区隔 ========== */
[data-testid="stVerticalBlock"] > div {
    padding: 0.3rem 0;
}
</style>
"""


def get_global_css() -> str:
    """返回全局CSS样式字符串（兼容旧接口，内部走缓存）"""
    return _get_css_cached()


def inject_css():
    """在当前页面注入全局CSS（推荐使用此函数，自动走缓存）"""
    st.markdown(_get_css_cached(), unsafe_allow_html=True)


def inject_upload_i18n():
    """将 file_uploader 内置英文提示替换为中文"""
    import streamlit.components.v1 as components
    js = """
<script>
(function(){
  var doc = window.parent.document;
  var replaced = new WeakSet();
  function walk(el) {
    if (el.nodeType !== 1 || replaced.has(el)) return;
    // 检查元素内是否包含英文提示文本
    var text = el.innerText || '';
    if (text.indexOf('Drag and drop') !== -1 || text.indexOf('Browse files') !== -1 ||
        text.indexOf('drag and drop') !== -1 || text.indexOf('browse files') !== -1 ||
        (text.indexOf('Limit') !== -1 && text.indexOf('per file') !== -1) ||
        text.indexOf('file here') !== -1) {
      // 检查子元素——只处理没有子元素（叶节点）或纯文本容器
      var hasBlockChild = false;
      for (var i = 0; i < el.children.length; i++) {
        if (el.children[i].children.length > 0) { hasBlockChild = true; break; }
      }
      if (!hasBlockChild && el.children.length <= 2) {
        var t = (el.innerText || '').trim();
        if (t.indexOf('Limit') !== -1 && t.indexOf('per file') !== -1) {
          el.innerText = '单文件上限 200MB · CSV、XLSX、XLS';
          replaced.add(el);
        } else if (t.indexOf('drag') !== -1 || t.indexOf('Drag') !== -1 || t.indexOf('Browse') !== -1 || t.indexOf('file here') !== -1) {
          el.innerText = '拖拽文件到此处，或点击选择文件';
          replaced.add(el);
        }
      }
    }
    // 递归子元素
    for (var j = 0; j < el.children.length; j++) {
      walk(el.children[j]);
    }
  }
  function replaceAll() {
    var dzs = doc.querySelectorAll('[data-testid="stFileUploaderDropzone"]');
    for (var d = 0; d < dzs.length; d++) { walk(dzs[d]); }
    return dzs.length > 0;
  }
  replaceAll();
  var iv = setInterval(replaceAll, 300);
  setTimeout(function() { clearInterval(iv); }, 5000);
})();
</script>
"""
    components.html(js, height=0)


def inject_nav_separator():
    """在侧边栏导航的「用户中心」前插入一条分割线（仅一次，MutationObserver 稳定）"""
    import streamlit.components.v1 as components
    js = """
<script>
(function(){
  var doc = window.parent.document;
  function insertSeparator() {
    var links = doc.querySelectorAll('[data-testid="stSidebarNav"] a');
    if (links.length === 0) return;
    // 找「用户中心」
    var target = null;
    for (var i = links.length - 1; i >= 0; i--) {
      if ((links[i].innerText || '').indexOf('用户中心') !== -1) { target = links[i]; break; }
    }
    if (!target) return;
    var li = target.parentElement;
    if (!li) return;
    // 已在上方插入过则跳过
    if (li.previousElementSibling && li.previousElementSibling.dataset && li.previousElementSibling.dataset.stSep) return;
    // 创建分割线 <li>
    var sep = doc.createElement('li');
    sep.dataset.stSep = '1';
    sep.style.cssText = 'height:0;border-bottom:1px solid #cbd5e1;margin:8px 12px;list-style:none;';
    li.parentElement.insertBefore(sep, li);
  }
  // 用 MutationObserver 替代 setInterval，更稳定
  var doc = window.parent.document;
  if (doc.readyState === 'complete') { insertSeparator(); }
  else { window.parent.addEventListener('load', insertSeparator); }
  var obs = new MutationObserver(function() { insertSeparator(); });
  obs.observe(doc.body || doc.documentElement, {childList:true, subtree:true});
  setTimeout(function(){ obs.disconnect(); }, 8000);
})();
</script>
"""
    components.html(js, height=0)




