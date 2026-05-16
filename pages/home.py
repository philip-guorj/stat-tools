# pages/home.py - 首页
"""
StatTools 首页：数据管理 + 功能概述。
"""

import streamlit as st
from utils.data_manager import render_data_manager_expanded
from utils.visitor_logger import log_visit, render_sidebar_stats

# 页面标题
st.markdown('<div class="main-header">StatTools 田间试验统计分析平台</div>', unsafe_allow_html=True)
st.markdown('<div style="text-align:center;color:#64748b;font-size:0.8rem;margin-top:-0.3rem;margin-bottom:0.5rem;">欢迎试用反馈，philip.guo@foxmail.com</div>', unsafe_allow_html=True)

# 系统功能概述（默认折叠，减少首屏干扰）
with st.expander("📖 系统功能概述与使用指南", expanded=False):
    st.markdown("""
    ### 平台简介
    
    **StatTools** 是专为田间试验设计的统计分析平台，提供从数据管理到高级分析的一站式解决方案。
    
    ### 功能模块
    
    | 模块 | 功能 | 适用场景 |
    |------|------|---------|
    | **描述统计** | 均值、标准差、变异系数等基础统计量 | 快速了解数据特征 |
    | **假设检验** | t检验、卡方检验、正态性检验等 | 验证统计假设 |
    | **方差分析** | 随机区组、裂区设计、多点试验，间比试验 | 田间试验数据分析 |
    | **回归分析** | 线性、多元、多项式、逐步回归 | 建立预测模型 |
    | **多变量分析** | PCA、聚类、相关分析 | 多变量数据探索 |
    | **数据可视化** | 10+种交互式图表 | 直观展示数据 |
    | **试验设计** | CRD/RCBD/拉丁方/裂区等方案生成 | 生成科学试验方案 |
    
    ### 分析方法选择指南
    
    <div class="method-guide">
    <div class="method-guide-title">不知道选哪个分析模块？按以下步骤判断：</div>
    <div class="method-guide-content">
    <b>第一步：明确试验设计类型</b><br>
    - 只有一个处理因素 → 用<b>描述统计</b>或<b>方差分析-CRD/RCBD</b><br>
    - 两个处理因素（如品种×施肥）→ 用<b>方差分析-两因素析因</b><br>
    - 主处理+副处理（如耕作方式×品种）→ 用<b>方差分析-裂区设计</b><br>
    - 多个地点/年份 → 用<b>方差分析-MET多点联合分析</b>
    
    <b>第二步：选择统计检验方法</b><br>
    - 比较两组均值差异 → <b>假设检验-t检验</b><br>
    - 检验数据是否符合正态分布 → <b>假设检验-正态性检验</b><br>
    - 多组方差是否齐次 → <b>假设检验-方差齐性检验</b>

    <b>第三步：深入分析</b><br>
    - 探索变量间关系 → <b>回归分析</b><br>
    - 降维/分类/综合评价 → <b>多变量分析-PCA/聚类</b><br>
    - 生成试验田间排列方案 → <b>试验设计</b>
    </div>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("""
    ### 选择示例数据
    
    1. **上传数据**：在下方数据管理区域上传 CSV/Excel 文件
    2. **选择分析**：从左侧导航选择需要的分析方法
    3. **配置参数**：根据页面提示设置分析参数
    4. **查看结果**：查看统计结果和可视化图表
    
    ### 使用提示
    
    - 每个分析页面都有 **功能简介**，帮助了解各工具用途
    - 支持示例数据，可快速体验各项功能
    - 分析结果可导出为图片或表格
    """)

st.markdown("---")

# 数据管理区域（全局，直接展开）
render_data_manager_expanded()

# 侧边栏访问统计（仅首页显示）
render_sidebar_stats()

# 记录访问
log_visit("首页")
