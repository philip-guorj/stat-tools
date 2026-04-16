# 方差分析模块 - 田间试验设计专用

import os
import sys
import re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
import numpy as np
from scipy import stats
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import warnings
warnings.filterwarnings('ignore')

from utils.data_manager import get_data_manager
from utils.styles import get_global_css


# ========== 延迟导入statsmodels（加快启动速度）==========

_sm_cache = None

def _get_statsmodels():
    """延迟导入statsmodels，按需加载"""
    global _sm_cache
    if _sm_cache is None:
        import statsmodels.api as sm
        from statsmodels.formula.api import ols
        from statsmodels.stats.anova import anova_lm
        from statsmodels.stats.multicomp import pairwise_tukeyhsd
        _sm_cache = (sm, ols, anova_lm, pairwise_tukeyhsd)
    return _sm_cache

# 提供便捷访问
def _get_ols():
    return _get_statsmodels()[1]

def _get_anova_lm():
    return _get_statsmodels()[2]

def _get_tukey():
    return _get_statsmodels()[3]


# ========== 兼容性辅助函数（必须在其他函数之前定义）==========

def _display_tukey_result(tukey_obj):
    """显示Tukey HSD结果（含字母标识），兼容不同版本的statsmodels"""
    df_tukey = None

    try:
        if hasattr(tukey_obj, '_results_table') and tukey_obj._results_table is not None:
            df_tukey = pd.DataFrame(tukey_obj._results_table[1:],
                                    columns=tukey_obj._results_table[0])
    except Exception:
        pass

    if df_tukey is None:
        try:
            summary = tukey_obj.summary()
            if hasattr(summary, 'tables'):
                t = summary.tables[1]
                df_tukey = t.as_data() if hasattr(t, 'as_data') else pd.DataFrame(t)
        except Exception:
            pass

    if df_tukey is None:
        try:
            if hasattr(tukey_obj, "_multicomp") and hasattr(tukey_obj._multicomp, "data"):
                df_tukey = pd.DataFrame(data=tukey_obj._multicomp.data,
                                        columns=['group1','group2','meandiff','p-adj',

                                                 'lower','upper','reject'])
        except Exception:
            pass

    if df_tukey is not None:
        with st.expander("Tukey HSD \u6210\u5bf9\u6bd4\u8f83\u8be6\u60c5", expanded=False):
            st.dataframe(df_tukey)
        _render_cld_letters(tukey_obj, df_tukey)
    else:
        st.info("Tukey HSD \u68c0\u9a8c\u5df2\u5b8c\u6210")


def _render_cld_letters(tukey_obj, df_tukey):
    """显示Tukey HSD的CLD字母标识（闭包法 v3）"""
    import string
    groups = sorted(tukey_obj.groupsunique)
    if not groups:
        return

    # 构建不显著邻接表
    non_sig = {g: set() for g in groups}
    col_names = list(df_tukey.columns)
    reject_col = 'reject' if 'reject' in col_names else col_names[-1]

    for _, row in df_tukey.iterrows():
        g1, g2 = str(row.iloc[0]), str(row.iloc[1])
        try:
            rej_val = row.get(reject_col, True)
            if rej_val == False or str(rej_val) == 'False':
                non_sig[g1].add(g2)
                non_sig[g2].add(g1)
        except Exception:
            pass

    group_means = {g: float(np.mean(tukey_obj.data[tukey_obj.groups == g])) for g in groups}
    sorted_groups = sorted(groups, key=lambda x: group_means[x], reverse=True)

    # ── 闭包法 CLD v3：每个最大不显著团对应一个字母，团内所有成员共享 ──
    assigned_letters = {g: set() for g in sorted_groups}
    letter_idx = 0

    for i, g_seed in enumerate(sorted_groups):
        group = {g_seed}
        for j in range(i + 1, len(sorted_groups)):
            g_candidate = sorted_groups[j]
            if all(g_candidate in non_sig.get(gm, set()) for gm in group):
                group.add(g_candidate)

        # 团中所有成员共享同一个字母（核心修正）
        cur_letter = string.ascii_uppercase[letter_idx]
        for gm in group:
            assigned_letters[gm].add(cur_letter)
        letter_idx += 1

    # 组装输出
    cld_rows = []
    for g in sorted_groups:
        letters = ''.join(sorted(assigned_letters.get(g, set())))
        cld_rows.append({'基因型/处理': g, '均值': round(group_means[g], 2), '字母标识': letters})

    df_cld = pd.DataFrame(cld_rows)

    c1, c2 = st.columns([2, 3])
    with c1:
        st.markdown('**显著性字母标识** (不同字母 -> p<0.05):')
        st.dataframe(df_cld.reset_index(drop=True), use_container_width=True)

    with c2:
        fig_cld = go.Figure()
        means_vals = [group_means[g] for g in sorted_groups]
        letters_display = [''.join(sorted(assigned_letters.get(g, set()))) for g in sorted_groups]
        fig_cld.add_trace(go.Bar(
            x=means_vals, y=sorted_groups, orientation='h',
            text=letters_display, textposition='outside',
            marker_color='#3498db'
        ))
        fig_cld.update_layout(
            title='多重比较字母标识图',
            xaxis_title='均值',
            height=max(300, len(sorted_groups)*40 + 80),
            showlegend=False, yaxis=dict(autorange='reversed')
        )
        st.plotly_chart(fig_cld, use_container_width=True, key='met_cld')


def _render_met_cld(geno_names_sorted, emmeans_geno, compare_results, method_name='LSD'):
    """基于多重比较结果渲染MET基因型CLD字母标识（闭包法 v3）"""
    import string

    n = len(geno_names_sorted)
    if n == 0:
        return

    # Step 1: 构建不显著性邻接表（显著标记为空 = 不显著）
    non_sig = {g: set() for g in geno_names_sorted}
    for r in compare_results:
        sig_mark = r.get('显著', '')
        # 空字符串表示不显著（无论旧格式还是新格式 ✓/✓✓）
        if sig_mark.strip() == '' or sig_mark == '':
            g1, g2 = r['品种1'], r['品种2']
            non_sig[g1].add(g2)
            non_sig[g2].add(g1)

    # Step 2: 闭包法CLD — 每个最大不显著团对应一个字母
    # 按均值从高到低排序后逐个作为种子扩展
    assigned_letters = {g: set() for g in geno_names_sorted}
    letter_idx = 0

    for i, g_seed in enumerate(geno_names_sorted):
        # 从种子开始向后贪心扩展最大不显著团
        group = {g_seed}
        for j in range(i + 1, len(geno_names_sorted)):
            g_cand = geno_names_sorted[j]
            # 候选者必须与团中每一个成员都不显著才能加入
            if all(g_cand in non_sig.get(gm, set()) for gm in group):
                group.add(g_cand)

        # 团中的所有成员共享同一个字母（核心修正）
        cur_letter = string.ascii_uppercase[letter_idx]
        for gm in group:
            assigned_letters[gm].add(cur_letter)
        letter_idx += 1

    # Step 3: assemble output
    cld_rows = []
    for g in geno_names_sorted:
        letters = ''.join(sorted(assigned_letters.get(g, set())))
        cld_rows.append({'基因型': g, '均值': round(emmeans_geno[g], 2), '字母标识': letters})

    df_cld = pd.DataFrame(cld_rows)

    col_t, col_b = st.columns([2, 3])
    with col_t:
        st.markdown(f'**显著性字母标识（{method_name}）** — 不同字母表示 p<0.05 差异显著:')
        st.dataframe(df_cld.reset_index(drop=True), use_container_width=True)
    with col_b:
        fig_m = go.Figure()
        means_v = [emmeans_geno[g] for g in geno_names_sorted]
        let_d = [''.join(sorted(assigned_letters.get(g, set()))) for g in geno_names_sorted]
        fig_m.add_trace(go.Bar(
            x=means_v, y=geno_names_sorted, orientation='h',
            text=let_d, textposition='outside',
            marker_color='#e74c3c' if method_name != 'LSD' else '#3498db'
        ))
        fig_m.update_layout(
            title=f'MET基因型多重比较字母标识图（基于联合模型{method_name}）',
            xaxis_title='调整均值',
            height=max(300, len(geno_names_sorted)*40 + 80),
            showlegend=False, yaxis=dict(autorange='reversed')
        )
        st.plotly_chart(fig_m, use_container_width=True, key=f'met_{method_name.lower()}_cld')



def render_anova():
    st.markdown(get_global_css(), unsafe_allow_html=True)
    st.markdown('<div class="section-header">📊 方差分析 (ANOVA)</div>', unsafe_allow_html=True)
    
    # 功能简介下拉菜单
    with st.expander("📖 功能简介", expanded=False):
        st.markdown("""
        **方差分析 (ANOVA)** 用于比较三个或更多组间的均值差异，是田间试验设计的核心分析方法。
        
        | 试验设计 | 适用场景 | 数据要求 |
        |---------|---------|---------|
        | 完全随机设计 (CRD) | 处理随机分配到试验单元 | 1个处理因子+观测值 |
        | 随机区组设计 (RCBD) | 存在已知干扰因素（如土壤肥力梯度） | 处理+区组+观测值 |
        | 拉丁方设计 | 控制两个方向的干扰因素 | 处理+行区组+列区组+观测值 |
        | 裂区设计 | 主处理需要大面积，副处理在小面积实施 | 主处理+副处理+区组+观测值 |
        | 两因素析因设计 | 研究两个因子的主效应和交互效应 | 因子A+因子B+观测值 |
        | MET多点联合分析 | 多地点多年份的品种试验 | 品种+地点+年份+观测值 |
        
        **使用建议**：根据试验设计选择对应方法，RCBD是最常用的田间试验设计。
        """)
        
        st.markdown("""
        <div class="method-guide">
        <div class="method-guide-title">如何选择方差分析方法？</div>
        <div class="method-guide-content">
        <b>1. 完全随机设计 (CRD)</b>：试验单元之间环境差异不大（如温室、实验室）<br>
        <b>2. 随机区组设计 (RCBD)</b>：存在已知方向的环境梯度（如土壤肥力从一端到另一端逐渐变化）→ 田间试验<b>最常用</b><br>
        <b>3. 拉丁方设计</b>：存在<b>两个方向</b>的环境梯度（如行和列方向都有肥力差异）<br>
        <b>4. 裂区设计</b>：一个因素需要大面积实施（如耕作方式），另一个因素可以小面积实施（如品种）<br>
        <b>5. 两因素析因设计</b>：两个因素处于同等地位，需研究<b>交互效应</b><br>
        <b>6. MET多点联合分析</b>：品种在多个地点、多个年份的联合试验，用于品种审定
        </div>
        </div>
        """, unsafe_allow_html=True)
    
    dm = get_data_manager()
    
    if not dm.is_loaded:
        st.warning("⚠️ 请先上传数据文件")
        return
    
    df = dm.data
    
    # 试验设计类型选择
    design_type = st.selectbox(
        "选择试验设计类型",
        [
            "--- 完全随机设计 (CRD)",
            "随机完全区组设计 (RCBD)",
            "拉丁方设计 (Latin Square)",
            "裂区设计 (Split-Plot)",
            "两因素析因设计",
            "MET 多点联合分析",
            "Alpha/不完全区组设计",
            "增广设计 (对照+测试)",
            "间比法/对比法分析"
        ]
    )
    
    st.markdown("---")
    
    if design_type.startswith("--- CRD"):
        crd_anova(df)
    elif design_type == "随机完全区组设计 (RCBD)":
        rcbd_anova(df)
    elif design_type == "拉丁方设计 (Latin Square)":
        latin_square_anova(df)
    elif design_type == "裂区设计 (Split-Plot)":
        split_plot_anova(df)
    elif design_type == "两因素析因设计":
        factorial_anova(df)
    elif design_type == "MET 多点联合分析":
        met_analysis(df)
    elif design_type == "Alpha/不完全区组设计":
        alpha_lattice_anova(df)
    elif design_type == "增广设计 (对照+测试)":
        augmented_anova(df)
    elif design_type == "间比法/对比法分析":
        interval_contrast_anova(df)


# ========== CRD 完全随机设计 ==========
def crd_anova(df):
    st.markdown("### 🎯 完全随机设计 (CRD)")
    sm, ols, anova_lm, pairwise_tukeyhsd = _get_statsmodels()
    
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    categorical_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
    
    response = st.selectbox("选择响应变量（产量/指标）", numeric_cols, key="crd_y")
    treatment = st.selectbox("选择处理变量", categorical_cols, key="crd_trt")
    
    # 拟合模型
    formula = f'Q("{response}") ~ C(Q("{treatment}"))'
    try:
        model = ols(formula, data=df).fit()
        anova_table = anova_lm(model, typ=2)
        
        display_anova_table(anova_table, "CRD方差分析表")
        
        # 处理均值比较
        treatment_means = df.groupby(treatment)[response].agg(['mean', 'std', 'count']).round(3)
        treatment_means.columns = ['均值', '标准差', '重复数']
        
        st.markdown("#### 处理均值与多重比较")
        tab_mean, tab_tukey = st.tabs(["描述统计", "Tukey HSD"])
        
        with tab_mean:
            st.dataframe(treatment_means.sort_values('均值', ascending=False))
        
        with tab_tukey:
            tukey = pairwise_tukeyhsd(
                endog=df[response].values,
                groups=df[treatment].values,
                alpha=0.05
            )
            # 兼容不同版本的statsmodels
            _display_tukey_result(tukey)
            
            # 显著性分组图
            plot_significance_groups(tukey, treatment_means, response)
    
    except Exception as e:
        st.error(f"分析失败: {e}")


# ========== RCBD 随机完全区组设计 ==========
def rcbd_anova(df):
    st.markdown("### 🎯 随机完全区组设计 (RCBD)")
    sm, ols, anova_lm, pairwise_tukeyhsd = _get_statsmodels()
    
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    categorical_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
    
    col1, col2, col3 = st.columns(3)
    with col1:
        response = st.selectbox("响应变量", numeric_cols, key="rcbd_y")
    with col2:
        treatment = st.selectbox("处理变量", categorical_cols, key="rcbd_trt")
    with col3:
        block = st.selectbox("区组变量", [c for c in categorical_cols if c != treatment], key="rcbd_blk")
    
    try:
        formula = f'Q("{response}") ~ C(Q("{block}")) + C(Q("{treatment}"))'
        model = ols(formula, data=df).fit()
        anova_table = anova_lm(model, typ=2)
        
        display_anova_table(anova_table, "RCBD方差分析表")
        
        # 处理效应可视化
        st.markdown("#### 处理效应分析")
        
        # 调整均值
        adj_means = df.groupby(treatment)[response].mean().sort_values(ascending=False)
        
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        # 均值柱状图
        fig.add_trace(go.Bar(x=adj_means.index, y=adj_means.values,
                             name='处理均值', marker_color='#3498db'))
        
        # 误差线
        sem_values = df.groupby(treatment)[response].apply(stats.sem).reindex(adj_means.index)
        fig.add_trace(go.Scatter(x=adj_means.index, y=adj_means.values,
                                error_y=dict(type='data', array=sem_values.values*1.96,
                                           visible=True, thickness=2),
                                mode='markers', name='95% CI', 
                                marker_size=12))
        
        fig.update_layout(title=f'{response} 处理均值比较 (RCBD)',
                         xaxis_title=treatment, yaxis_title=response, height=450)
        st.plotly_chart(fig, use_container_width=True)
        
        # 区组效应
        block_means = df.groupby(block)[response].mean().sort_values(ascending=False)
        fig_block = px.bar(x=block_means.index, y=block_means.values,
                          labels={'x': block, 'y': response},
                          title='区组效应')
        st.plotly_chart(fig_block, use_container_width=True)
        
        # 多重比较
        tukey_result = pairwise_tukeyhsd(df[response], df[treatment], alpha=0.05)
        with st.expander("查看 Tukey HSD 多重比较"):
            _display_tukey_result(tukey_result)
        
        plot_significance_groups(tukey_result, 
                                 df.groupby(treatment)[response].agg(['mean','std','count']),
                                 response)
    
    except Exception as e:
        st.error(f"分析失败: {e}")
        import traceback; st.code(traceback.format_exc())


# ========== 拉丁方设计 ==========
def latin_square_anova(df):
    st.markdown("### 🎯 拉丁方设计 (Latin Square)")
    sm, ols, anova_lm, pairwise_tukeyhsd = _get_statsmodels()
    
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    categorical_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
    
    if len(categorical_cols) < 3:
        st.warning("拉丁方设计需要至少3个分类变量：行、列、处理")
        return
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        response = st.selectbox("响应变量", numeric_cols, key="ls_y")
    with col2:
        row_var = st.selectbox("行变量", categorical_cols, key="ls_row")
    with col3:
        col_var = st.selectbox("列变量", [c for c in categorical_cols if c != row_var], key="ls_col")
    with col4:
        trt_var = st.selectbox("处理变量", [c for c in categorical_cols if c not in [row_var, col_var]], key="ls_trt")
    
    try:
        formula = f'Q("{response}") ~ C(Q("{row_var}")) + C(Q("{col_var}")) + C(Q("{trt_var}"))'
        model = ols(formula, data=df).fit()
        anova_table = anova_lm(model, typ=2)
        
        display_anova_table(anova_table, "拉丁方设计方差分析表")
        
        # 热力图展示拉丁方布局
        pivot_df = df.pivot_table(values=response, index=row_var, columns=trt_var, aggfunc='mean')
        
        fig = px.imshow(pivot_df, text_auto='.1f', aspect='auto',
                        color_continuous_scale='YlGnBu',
                        title=f'{response} 均值分布 ({row_var} × {trt_var})')
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)
        
    except Exception as e:
        st.error(f"分析失败: {e}")


# ========== 裂区设计 ==========
def split_plot_anova(df):
    st.markdown("### 🎯 裂区设计 (Split-Plot)")
    sm, ols, anova_lm, pairwise_tukeyhsd = _get_statsmodels()
    
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    categorical_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
    
    st.markdown("""
    **裂区设计说明**：
    - **主区因子 (A)**：施加于整个主区的处理
    - **副区因子 (B)**：在主区内细分后施加的处理
    - **区组 (Block)**：重复单位
    """)
    
    col1, col2, col3, col4 = st.columns(4)
    with col1: response = st.selectbox("响应变量", numeric_cols, key="sp_y")
    with col2: main_factor = st.selectbox("主区因子(A)", categorical_cols, key="sp_a")
    with col3: sub_factor = st.selectbox("副区因子(B)", [c for c in categorical_cols if c != main_factor], key="sp_b")
    with col4: block_var = st.selectbox("区组", [c for c in categorical_cols if c not in [main_factor, sub_factor]], key="sp_block")
    
    try:
        # 裂区设计混合模型公式
        formula = f'''Q("{response}") ~ Q("{block_var}") + C(Q("{main_factor}"), Sum) + 
                    Q("{block_var}"):C(Q("{main_factor}"), Sum) + 
                    C(Q("{sub_factor}"), Sum) + C(Q("{main_factor}"), Sum):C(Q("{sub_factor}"), Sum) +
                    Q("{block_var}"):C(Q("{sub_factor}"), Sum) + 
                    C(Q("{main_factor}"), Sum):C(Q("{sub_factor}"), Sum):Q("{block_var}")'''
        
        model = ols(formula.replace('\n', '').replace('  ', ''), data=df).fit()
        anova_table = anova_lm(model, typ=3)
        
        display_anova_table(anova_table, "裂区设计方差分析表")
        
        # 交互作用图
        st.markdown("#### 主区 × 副区交互作用")
        fig = px.line(df.groupby([main_factor, sub_factor])[response].mean().reset_index(),
                     x=sub_factor, y=response, color=main_factor,
                     markers=True, title='主区×副区交互作用图',
                     labels={sub_factor: '副区因子', response: response, main_factor: '主区因子'})
        st.plotly_chart(fig, use_container_width=True)
        
    except Exception as e:
        st.error(f"分析失败: {e}")


# ========== 两因素析因设计 ==========
def factorial_anova(df):
    st.markdown("### 🎯 两因素析因设计")
    sm, ols, anova_lm, pairwise_tukeyhsd = _get_statsmodels()
    
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    categorical_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
    
    col1, col2, col3 = st.columns(3)
    with col1: response = st.selectbox("响应变量", numeric_cols, key="fact_y")
    with col2: factor_a = st.selectbox("因子A", categorical_cols, key="fact_a")
    with col3: factor_b = st.selectbox("因子B", [c for c in categorical_cols if c != factor_a], key="fact_b")
    
    include_interaction = st.checkbox("包含交互作用 A×B", value=True)
    
    try:
        if include_interaction:
            formula = f'Q("{response}") ~ C(Q("{factor_a}")) * C(Q("{factor_b}"))'
        else:
            formula = f'Q("{response}") ~ C(Q("{factor_a}")) + C(Q("{factor_b}"))'
        
        model = ols(formula, data=df).fit()
        anova_table = anova_lm(model, typ=2)
        
        display_anova_table(anova_table, "两因素析因设计方差分析表")
        
        # 交互作用图
        if include_interaction:
            st.markdown("#### 因子交互作用图")
            
            tab_int, tab_profile = st.tabs(["交互作用线图", "剖面图"])
            
            with tab_int:
                fig = px.line(df.groupby([factor_a, factor_b])[response].mean().reset_index(),
                             x=factor_a, y=response, color=factor_b,
                             markers=True, title='因子A×B交互作用',
                             labels={factor_a: '因子A', factor_b: '因子B'})
                st.plotly_chart(fig, use_container_width=True)
            
            with tab_profile:
                fig2 = px.line(df.groupby([factor_a, factor_b])[response].mean().reset_index(),
                              x=factor_b, y=response, color=factor_a,
                              markers=True, title='因子B×A剖面图',
                              labels={factor_b: '因子B', factor_a: '因子A'})
                st.plotly_chart(fig2, use_container_width=True)
        
        # 单元格均值热图
        cell_means = df.pivot_table(values=response, index=factor_a, columns=factor_b, aggfunc='mean')
        fig_heat = px.imshow(cell_means, text_auto='.2f', aspect='auto',
                             color_continuous_scale='RdBu_r',
                             title='单元格均值矩阵')
        fig_heat.update_layout(height=350)
        st.plotly_chart(fig_heat, use_container_width=True)
        
    except Exception as e:
        st.error(f"分析失败: {e}")


# ========== MET 多点联合分析 ==========
def met_analysis(df):
    st.markdown("### 🌍 MET 多点联合分析")
    sm, ols, anova_lm, pairwise_tukeyhsd = _get_statsmodels()

    st.markdown("""
    **MET (Multi-Environment Trial)** 用于评估品种/处理在不同环境（地点×年份）下的表现，
    分析基因型(G)、环境(E)、及G×E互作效应。
    """)

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    categorical_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()

    col1, col2, col3 = st.columns(3)
    with col1: response = st.selectbox("响应变量", numeric_cols, key="met_y")
    with col2: genotype = st.selectbox("基因型/处理", categorical_cols, key="met_g")
    with col3: environment = st.selectbox("环境(地点/年份)", [c for c in categorical_cols if c != genotype], key="met_e")

    try:
        environments = sorted(df[environment].unique())
        genotypes = sorted(df[genotype].unique())
        n_env = len(environments)
        n_gen = len(genotypes)

        # ========== Tab 1: 单点分析 ==========
        st.markdown("---")
        st.markdown("#### 📍 一、单点分析 — 各环境独立方差分析与CV")

        single_point_results = []

        for env in environments:
            df_env = df[df[environment] == env]

            cat_cols_env = df_env.select_dtypes(include=['object', 'category']).columns.tolist()
            potential_block = [c for c in cat_cols_env if c not in [environment, genotype]]

            env_mean = df_env[response].mean()
            env_std = df_env[response].std()
            env_cv = (env_std / env_mean * 100) if env_mean != 0 else 0
            env_n = len(df_env)

            try:
                formula_sp = f'Q("{response}") ~ C(Q("{genotype}"))'
                if len(potential_block) > 0:
                    block_var = potential_block[0]
                    formula_sp = f'Q("{response}") ~ C(Q("{block_var}")) + C(Q("{genotype}"))'

                model_sp = ols(formula_sp, data=df_env).fit()
                anova_sp = anova_lm(model_sp, typ=2)

                geno_row = None
                for idx_name in anova_sp.index:
                    if genotype in str(idx_name):
                        geno_row = anova_sp.loc[idx_name]
                        break

                f_val = geno_row['F'] if geno_row is not None else np.nan
                p_val = geno_row['PR(>F)'] if geno_row is not None else np.nan

                geno_stats = df_env.groupby(genotype)[response].agg(['mean', 'std', 'count'])
                geno_max_mean = geno_stats['mean'].max()
                geno_min_mean = geno_stats['mean'].min()
                geno_range = geno_max_mean - geno_min_mean

            except Exception:
                f_val, p_val, geno_range = np.nan, np.nan, np.nan

            single_point_results.append({
                environment: env,
                '样本数(N)': env_n,
                '均值': round(env_mean, 2),
                '标准差': round(env_std, 2),
                '变异系数(CV%)': round(env_cv, 2),
                '基因型F值': round(f_val, 2) if not np.isnan(f_val) else '-',
                '基因型p值': f'{p_val:.4f}' if not np.isnan(p_val) else '-',
                '极差': round(geno_range, 2) if not np.isnan(geno_range) else '-',
            })

        sp_df = pd.DataFrame(single_point_results)
        sp_df_sorted = sp_df.sort_values('变异系数(CV%)', ascending=False)

        st.dataframe(sp_df_sorted.reset_index(drop=True), use_container_width=True)

        # 单点CV柱状图
        fig_sp_cv = px.bar(
            x=sp_df_sorted[environment], y=sp_df_sorted['变异系数(CV%)'],
            labels={environment: '环境', '变异系数(CV%)': 'CV (%)'},
            title='各试验点变异系数 (CV%) 排序',
            text=sp_df_sorted['变异系数(CV%)'].apply(lambda x: f'{x:.1f}%'),
            color=sp_df_sorted['变异系数(CV%)'],
            color_continuous_scale='RdYlGn_r'
        )
        fig_sp_cv.update_layout(height=400, showlegend=False)
        st.plotly_chart(fig_sp_cv, use_container_width=True, key='met_sp_cv')

        # 展开查看每个环境的详细ANOVA表
        with st.expander("📋 查看每个环境的详细方差分析表"):
            for env in environments:
                df_env = df[df[environment] == env]
                with st.expander(f"环境: {env}"):
                    try:
                        cat_cols_env = df_env.select_dtypes(include=['object', 'category']).columns.tolist()
                        # 检测数值型分类变量（如区组用数字表示）
                        num_cat_env = []
                        for col in df_env.select_dtypes(include=[np.number]).columns:
                            if col == response:
                                continue
                            uv = df_env[col].dropna().unique()
                            nu = len(uv)
                            if 2 <= nu <= 20 and all(float(v).is_integer() for v in uv):
                                num_cat_env.append(col)
                        potential_block = [c for c in (cat_cols_env + num_cat_env) if c not in [environment, genotype] and c != response]

                        if len(potential_block) > 0:
                            bv = potential_block[0]
                            f = f'Q("{response}") ~ C(Q("{bv}")) + C(Q("{genotype}"))'
                            m = ols(f, data=df_env).fit()
                        else:
                            f = f'Q("{response}") ~ C(Q("{genotype}"))'
                            m = ols(f, data=df_env).fit()

                        at = anova_lm(m, typ=2)
                        # 单点ANOVA表重命名
                        at_renamed = _rename_anova_index(at, environment, genotype,
                                                          bv if len(potential_block) > 0 else None,
                                                          is_met=False)
                        display_anova_table(at_renamed, f"{env} — ANOVA")

                        gs = df_env.groupby(genotype)[response].agg(['mean', 'std']).round(2)
                        gs.columns = ['均值', '标准差']
                        gs = gs.sort_values('均值', ascending=False)
                        st.dataframe(gs)
                    except Exception as e2:
                        st.warning(f"{env} 分析异常: {e2}")


        # ========== Tab 2: 联合方差分析 ==========
        st.markdown("---")
        st.markdown("#### 🌐 二、MET联合方差分析")

        # 检测是否有区组列（除环境和基因型外的分类变量，包括数值型分类变量）
        cat_cols_all = df.select_dtypes(include=['object', 'category']).columns.tolist()
        # 同时检测数值型但实际是分类的变量（如区组用 1,2,3 表示）
        numeric_cat_candidates = []
        for col in df.select_dtypes(include=[np.number]).columns:
            if col == response:
                continue
            unique_vals = df[col].dropna().unique()
            n_unique = len(unique_vals)
            # 数值型分类变量特征：唯一值较少(≤20)，且值为整数
            if n_unique >= 2 and n_unique <= 20 and all(float(v).is_integer() for v in unique_vals):
                numeric_cat_candidates.append(col)
        # 合并候选列表
        all_candidate_blocks = [c for c in (cat_cols_all + numeric_cat_candidates)
                                if c not in [environment, genotype] and c != response]

        block_var_met = None
        if len(all_candidate_blocks) > 0:
            block_var_met = all_candidate_blocks[0]
            st.caption(f"📌 检测到区组列: **{block_var_met}** | 模型: 环境 + 区组(嵌套于环境内) + 基因型 + G×E")
            # 含区组的MET模型: 区组嵌套在环境内 (RCBD-MET)
            # C(env)/C(block) 展开为: C(env) + C(env):C(block)
            formula = (f'Q("{response}") ~ C(Q("{environment}"))/C(Q("{block_var_met}")) '
                       f'+ C(Q("{genotype}")) + C(Q("{environment}")):C(Q("{genotype}"))')
        else:
            st.caption(f"⚠️ 未检测到区组列 | 分类变量: {cat_cols_all} | 数值候选: {numeric_cat_candidates}")
            formula = f'Q("{response}") ~ C(Q("{environment}")) * C(Q("{genotype}"))'

        model = ols(formula, data=df).fit()
        anova_table = anova_lm(model, typ=2)

        # 重命名ANOVA表的变异来源为中文
        anova_renamed = _rename_anova_index(anova_table, environment, genotype, block_var_met, is_met=True)
        display_anova_table(anova_renamed, "MET联合方差分析表")

        ss_total = anova_renamed['sum_sq'].sum()
        anova_renamed['SS%'] = (anova_renamed['sum_sq'] / ss_total * 100).round(2)

        fig_pie = go.Figure(data=[go.Pie(
            labels=anova_renamed.index.tolist(),
            values=anova_renamed['sum_sq'].tolist(),
            hole=0.4,
            textinfo='label+percent',
            textposition='outside'
        )])
        fig_pie.update_layout(title='各变异来源占总变异的比例', height=380)
        st.plotly_chart(fig_pie, use_container_width=True, key='met_pie')


        # ========== Tab 3: 基因型多重比较 ==========
        st.markdown("---")
        st.markdown("#### 🔬 三、基因型间多重比较（跨环境合并检验）")

        try:
            # ── 获取联合ANOVA模型的误差项均方(MSE)和自由度(df_e) ──
            anova_idx = list(anova_renamed.index)
            # 误差行可能是 '误差' 或包含 'Residual' 的原始名
            residual_row = None
            for idx_name in anova_renamed.index:
                if str(idx_name) in ('误差', 'Residual', 'residual'):
                    residual_row = anova_renamed.loc[idx_name]
                    break
            if residual_row is None:
                # 兜底：取最后一行作为残差
                residual_row = anova_renamed.iloc[-1]

            mse_val = residual_row.get('sum_sq', np.nan) / residual_row.get('df', 1) \
                if residual_row.get('df', 0) > 0 else np.nan
            df_e = int(residual_row.get('df', np.nan))

            # 基因型调整均值（来自联合模型）
            emmeans_geno = df.groupby(genotype)[response].mean()
            n_geno = len(emmeans_geno)
            geno_names_sorted = emmeans_geno.sort_values(ascending=False).index.tolist()
            geno_means_sorted = emmeans_geno.sort_values(ascending=False).values

            # 重复数：每个基因型的实际总观测数
            if block_var_met is not None:
                n_block = df[block_var_met].nunique()
            else:
                n_block = 1
            n_rep_total = n_env * n_block  # 理论总重复数 = 环境数 × 区组数

            # 每个基因型的实际观测数（用于精确SE计算，每对比较用各自n1,n2）
            obs_per_geno = df.groupby(genotype).size().astype(float)
            reps_per_geno = obs_per_geno

            # ── 方法1: Fisher LSD（基于联合模型MSE）──
            from scipy.stats import t as t_dist
            t_crit_05 = abs(t_dist.ppf(0.025, df_e))   # 双侧 α=0.05
            t_crit_01 = abs(t_dist.ppf(0.005, df_e))   # 双侧 α=0.01

            lsd_results = []
            for i in range(len(geno_names_sorted)):
                for j in range(i + 1, len(geno_names_sorted)):
                    g1, g2 = geno_names_sorted[i], geno_names_sorted[j]
                    m1, m2 = emmeans_geno[g1], emmeans_geno[g2]
                    diff = m1 - m2
                    # 合并标准误：sqrt(MSE * (1/n1 + 1/n2))
                    se_diff = np.sqrt(mse_val * (1.0 / reps_per_geno[g1] + 1.0 / reps_per_geno[g2]))
                    t_stat = diff / se_diff if se_diff > 0 else 0
                    p_val = 2 * (1 - t_dist.cdf(abs(t_stat), df_e))
                    lsd_value = t_crit_05 * se_diff
                    lsd_value_01 = t_crit_01 * se_diff
                    is_sig_05 = abs(diff) >= lsd_value
                    is_sig_01 = abs(diff) >= lsd_value_01
                    sig_mark = '✓✓' if is_sig_01 else ('✓' if is_sig_05 else '')
                    lsd_results.append({
                        '品种1': g1, '品种2': g2,
                        '均值差': round(diff, 4),
                        '标准误': round(se_diff, 4),
                        'LSD₀.₀₅': round(lsd_value, 4),
                        'LSD₀.₀₁': round(lsd_value_01, 4),
                        't值': round(t_stat, 3),
                        'p值': f'{p_val:.4f}',
                        '显著': sig_mark
                    })

            df_lsd = pd.DataFrame(lsd_results)
            sig_count_05 = sum(1 for r in lsd_results if '✓' in r['显著'])
            sig_count_01 = sum(1 for r in lsd_results if r['显著'] == '✓✓')

            with st.expander("📊 Fisher LSD 多重比较（基于联合模型误差项）", expanded=True):
                st.caption(
                    f"**说明**: 使用MET联合ANOVA的误差均方(MSE={mse_val:.4f}, df={df_e})进行多重比较。"
                    f" 每对比较的LSD临界值根据该两个基因型的实际观测数(n₁, n₂)分别计算："
                    f" SE = √(MSE × (1/n₁ + 1/n₂))，LSD = t × SE。"
                    f"\n\n临界t值: t₀.₀₂₅({df_e}) = {t_crit_05:.4f}，t₀.₀₀₅({df_e}) = {t_crit_01:.4f}。"
                    f" 理论重复数 n = 环境数×区组数 = {n_env}×{n_block} = {n_rep_total}。"
                    f"\n\n共 {len(lsd_results)} 对比较，α=0.05显著 {sig_count_05} 对，α=0.01极显著 {sig_count_01} 对。"
                    f" 显著标记：✓ = α=0.05显著，✓✓ = α=0.01极显著。"
                )
                st.dataframe(df_lsd.reset_index(drop=True), use_container_width=True)

            # ── CLD字母标识（基于LSD结果）──
            _render_met_cld(geno_names_sorted, emmeans_geno, lsd_results)

            # ── 方法2: Duncan's New MRT（邓肯新复极差法）──
            from scipy.stats import t as t_dist_fn
            try:
                from scipy.stats import studentized_range as ss_range
                has_sr = True
            except Exception:
                has_sr = False

            n_g = len(geno_names_sorted)
            duncan_results = []
            # Duncan's SSR值表：按范围 r = 2, 3, ..., k 查表
            ssr_table = {}
            alpha_duncan = 0.05
            for r in range(2, n_g + 1):
                if has_sr:
                    try:
                        ssr_val = ss_range.ppf(1 - alpha_duncan, r, df_e)
                        ssr_table[r] = ssr_val
                    except Exception:
                        # 兜底：用近似公式 SSR ≈ sqrt(2) * t_{α/(2r), df_e}
                        t_approx = abs(t_dist_fn.ppf(alpha_duncan / (2 * r), df_e))
                        ssr_table[r] = np.sqrt(2) * t_approx
                else:
                    t_approx = abs(t_dist_fn.ppf(alpha_duncan / (2 * r), df_e))
                    ssr_table[r] = np.sqrt(2) * t_approx

            # 对所有配对进行Duncan检验
            for i in range(n_g):
                for j in range(i + 1, n_g):
                    g1, g2 = geno_names_sorted[i], geno_names_sorted[j]
                    m1, m2 = emmeans_geno[g1], emmeans_geno[g2]
                    diff = m1 - m2

                    # 计算范围r：在排序列表中两处理之间相隔的处理数+1
                    r_val = j - i + 1

                    se = np.sqrt(mse_val / 2.0 * (1.0 / reps_per_geno[g1] + 1.0 / reps_per_geno[g2]))
                    ssr_crit = ssr_table.get(r_val, ssr_table.get(2, 3.912))
                    lsd_duncan = ssr_crit * se
                    is_sig_duncan = abs(diff) >= lsd_duncan

                    duncan_results.append({
                        '品种1': g1, '品种2': g2,
                        '均值差': round(diff, 4),
                        f'范围(r={r_val})': r_val,
                        'SSR临界值': round(ssr_crit, 4),
                        'LSR': round(lsd_duncan, 4),
                        '显著': '✓' if is_sig_duncan else ''
                    })

            df_duncan = pd.DataFrame(duncan_results)
            sig_count_duncan = sum(1 for r in duncan_results if r['显著'] == '✓')

            with st.expander("📊 Duncan's 新复极差法（基于联合模型误差项）", expanded=True):
                st.caption(
                    f"**说明**: Duncan's New MRT (SSR法)，"
                    f"误差均方(MSE={mse_val:.4f}, df={df_e})，"
                    f"保护水平随比较范围r递增(α_r = 1-(1-α)^{{r-1}})。"
                    f" 共 {len(duncan_results)} 对比较，{sig_count_duncan} 对差异显著。"
                    f" {'(使用近似t值)' if not has_sr else '(使用Studentized Range分布)'}"
                )
                st.dataframe(df_duncan.reset_index(drop=True), use_container_width=True)

            # ── Duncan CLD字母标识 ──
            _render_met_cld(geno_names_sorted, emmeans_geno, duncan_results, method_name='Duncan')

            # ── 同时保留Tukey HSD（原始合并数据）供参考对比 ──
            with st.expander("📋 Tukey HSD（原始数据参考 — 忽略环境效应）", expanded=False):
                st.caption(
                    "⚠️ **注意**: 此结果将所有环境原始数据视为单因素CRD处理，"
                    "**未扣除环境效应和G×E互作**，误差项偏大、检验偏保守。"
                    " 与联合ANOVA的F检验结论可能不一致属正常现象。"
                    " **建议以上方Fisher LSD结果为准。**"
                )
                tukey_met = pairwise_tukeyhsd(
                    endog=df[response].values,
                    groups=df[genotype].values,
                    alpha=0.05
                )
                _display_tukey_result(tukey_met)

            geno_all_means = df.groupby(genotype)[response].agg(['mean', 'std', 'count']).round(2)
            geno_all_means.columns = ['总均值', '标准差', '样本数']
            geno_all_means = geno_all_means.sort_values('总均值', ascending=False)

            st.markdown("**基因型综合表现排序**:")
            st.dataframe(geno_all_means)

            fig_geno_bar = px.bar(
                x=geno_all_means.index, y=geno_all_means['总均值'],
                error_y=geno_all_means['标准差'],
                labels={'x': genotype, 'y': response},
                title='基因型综合均值比较（误差线=SD）',
                color=geno_all_means['总均值'],
                color_continuous_scale='Viridis'
            )
            fig_geno_bar.update_layout(height=420, showlegend=False)
            st.plotly_chart(fig_geno_bar, use_container_width=True, key='met_geno_bar')

        except Exception as e_mp:
            import traceback
            st.warning(f"多重比较执行异常: {e_mp}")
            st.code(traceback.format_exc())


        # ========== Tab 4: G×E交互作用分析 ==========
        st.markdown("---")
        st.markdown("#### 🔄 四、G×E 交互作用分析")

        env_means = df.groupby(environment)[response].mean().sort_values(ascending=False)
        geno_means = df.groupby(genotype)[response].mean().sort_values(ascending=False)

        tab_env, tab_geno, tab_ge = st.tabs(["环境表现", "基因型表现", "G×E交互矩阵"])

        with tab_env:
            fig_env = px.bar(x=env_means.index, y=env_means.values,
                           labels={'x': environment, 'y': response},
                           title='各环境平均表现')
            st.plotly_chart(fig_env, use_container_width=True, key='met_ge_env')

            env_cv = df.groupby(environment)[response].apply(
                lambda x: x.std()/x.mean()*100 if x.mean()!=0 else 0)
            cv_df = pd.DataFrame({'均值': env_means.round(2), 'CV%': env_cv.round(2)})
            st.dataframe(cv_df.sort_values('CV%', ascending=False))

        with tab_geno:
            fig_geno = px.bar(x=geno_means.index, y=geno_means.values,
                            labels={'x': genotype, 'y': response},
                            title='基因型平均表现（跨环境）')
            st.plotly_chart(fig_geno, use_container_width=True, key='met_ge_geno')

            rank_data = df.groupby([environment, genotype])[response].mean().groupby(level=genotype).rank(ascending=False)
            avg_rank = rank_data.groupby(genotype).mean().round(2).sort_values()
            fig_rank = px.bar(x=avg_rank.index, y=avg_rank.values,
                             labels={'x': genotype, 'y': '平均排名'},
                             title='基因型平均排名（越低越稳定）')
            st.plotly_chart(fig_rank, use_container_width=True, key='met_ge_rank')

        with tab_ge:
            ge_matrix = df.pivot_table(values=response, index=environment, columns=genotype, aggfunc='mean')
            grand_mean = df[response].mean()
            e_effects = df.groupby(environment)[response].mean() - grand_mean
            g_effects = df.groupby(genotype)[response].mean() - grand_mean

            ge_effects = pd.DataFrame(index=e_effects.index, columns=g_effects.index)
            for env_idx in e_effects.index:
                for gen_idx in g_effects.index:
                    subset = df[(df[environment]==env_idx)&(df[genotype]==gen_idx)][response]
                    if len(subset) > 0:
                        cell_mean = subset.mean()
                        ge_effects.loc[env_idx, gen_idx] = cell_mean - grand_mean - e_effects[env_idx] - g_effects[gen_idx]

            fig_ge = px.imshow(ge_effects.fillna(0), text_auto='.1f', aspect='auto',
                              color_continuous_scale='RdBu_r',
                              color_continuous_midpoint=0,
                              title='G×E 交互效应矩阵')
            fig_ge.update_layout(height=450)
            st.plotly_chart(fig_ge, use_container_width=True, key='met_ge_matrix')

        # ========== Tab 5: 品种稳定性分析 ==========
        st.markdown("---")
        st.markdown("#### ⚖️ 五、品种稳定性分析")

        stability_metrics = _compute_stability_metrics(df, response, genotype, environment)

        if stability_metrics is not None and len(stability_metrics) > 0:
            stab_df = pd.DataFrame(stability_metrics).round(4)
            stab_df = stab_df.sort_values('总均值', ascending=False)
            st.dataframe(stab_df.reset_index(drop=True), use_container_width=True)

            stab_col1, stab_col2 = st.columns(2)
            with stab_col1:
                fig_ms = go.Figure()
                fig_ms.add_trace(go.Scatter(
                    x=stab_df['总均值'], y=stab_df['CV%'],
                    mode='markers+text', text=stab_df[genotype],
                    textposition='top center',
                    marker=dict(size=14, color='#3498db'),
                    name='品种'
                ))
                fig_ms.update_layout(
                    title='均值 vs 变异系数（右下角最优）',
                    xaxis_title=f'{response} 均值', yaxis_title='CV (%)',
                    height=420
                )
                st.plotly_chart(fig_ms, use_container_width=True, key='stab_mean_cv')

            with stab_col2:
                if '排名范围' in stab_df.columns:
                    fig_rr = go.Figure()
                    fig_rr.add_trace(go.Scatter(
                        x=stab_df['平均排名'], y=stab_df['排名范围'].apply(
                            lambda x: float(x.split('~')[1]) if '~' in str(x) and x.split('~')[1] else 0),
                        mode='markers+text', text=stab_df[genotype],
                        textposition='top center',
                        marker=dict(size=14, color='#e74c3c'),
                        name='品种'
                    ))
                    fig_rr.update_layout(
                        title='平均排名 vs 最大排名波动（左下角最优）',
                        xaxis_title='平均排名', yaxis_title='最大排名',
                        height=420
                    )
                    st.plotly_chart(fig_rr, use_container_width=True, key='stab_rank_range')
        else:
            st.info("稳定性指标计算需要至少2个环境和2个重复")


        # ========== Tab 6: Eberhart-Russell 稳定性分析 ==========
        st.markdown("---")
        st.markdown("#### 📈 六、Eberhart-Russell 稳定性分析")

        er_results = _eberhart_russell_analysis(df, response, genotype, environment)

        if er_results is not None:
            er_df, fig_er, env_indices_df = er_results

            st.markdown("""
            **Eberhart-Russell (1966) 模型**：
            - 回归系数 bᵢ 衡量品种对环境变化的响应（b≈1 为平均响应，b>1 更敏感，b<1 更迟钝）
            - 偏差平方和 s²dᵢ 衡量对线性回归的偏离（越小越好，理想为0）
            """)

            st.dataframe(er_df.round(4).reset_index(drop=True), use_container_width=True)

            st.plotly_chart(fig_er, use_container_width=True, key='er_regression')

            if env_indices_df is not None:
                with st.expander("查看环境指数详情"):
                    st.dataframe(env_indices_df.round(4), use_container_width=True)
        else:
            st.info("Eberhart-Russell分析需要足够的环境数和重复数据")


        # ========== Tab 7: GGE双标图 ==========
        st.markdown("---")
        st.markdown("#### 🎯 七、主成分分解（GGE双标图）")

        from sklearn.decomposition import PCA
        from sklearn.preprocessing import StandardScaler

        pivot_for_pca = df.pivot_table(values=response, index=environment, columns=genotype, aggfunc='mean').fillna(0)
        scaler = StandardScaler()
        pca = PCA(n_components=min(2, min(n_gen, n_env)))
        scores = pca.fit_transform(scaler.fit_transform(pivot_for_pca.T))

        fig_biplot = go.Figure()

        fig_biplot.add_trace(go.Scatter(
            x=scores[:, 0], y=scores[:, 1],
            mode='markers+text', text=pivot_for_pca.T.index,
            textposition='top center', name=genotype,
            marker_size=12, marker_color='#3498db'
        ))

        loadings = pca.components_.T * np.sqrt(pca.explained_variance_)
        for i, env_name in enumerate(pivot_for_pca.index):
            fig_biplot.add_trace(go.Scatter(
                x=[0, loadings[i, 0]*2], y=[0, loadings[i, 1]*2],
                mode='lines+text', text=[None, str(env_name)[:4]],
                line=dict(color='#e74c3c', width=2), showlegend=False
            ))

        variance_explained = pca.explained_variance_ratio_ * 100
        fig_biplot.update_layout(
            title=f"GGE双标图 (PC1: {variance_explained[0]:.1f}%, PC2: {variance_explained[1]:.1f}%)",
            xaxis_title=f"PC1 ({variance_explained[0]:.1f}%)",
            yaxis_title=f"PC2 ({variance_explained[1]:.1f}%)",
            height=520, width=750
        )
        st.plotly_chart(fig_biplot, use_container_width=True, key='gge_biplot')

    except Exception as e:
        st.error(f"分析失败: {e}")
        import traceback; st.code(traceback.format_exc())


def _compute_stability_metrics(df, response, genotype, environment):
    """计算品种稳定性综合指标"""

    envs = sorted(df[environment].unique())
    genes = sorted(df[genotype].unique())

    results = []

    for g in genes:
        df_g = df[df[genotype] == g]
        g_mean = df_g[response].mean()
        g_std = df_g[response].std()

        # 1. CV%
        g_cv = (g_std / g_mean * 100) if g_mean != 0 else 0

        # 2. 各环境下的均值与排名
        env_means_list = []
        for e in envs:
            df_ge = df[(df[genotype]==g) & (df[environment]==e)]
            if len(df_ge) > 0:
                em = df_ge[response].mean()
                env_means_list.append(em)
            else:
                env_means_list.append(np.nan)

        # 各环境下排名
        all_env_ranks = []
        for e in envs:
            df_e = df[df[environment]==e]
            e_genos = df_e.groupby(genotype)[response].mean().sort_values(ascending=False)
            if g in e_genos.index:
                all_env_ranks.append(e_genos.index.tolist().index(g) + 1)
            else:
                all_env_ranks.append(np.nan)

        avg_rank = np.nanmean(all_env_ranks) if any(not np.isnan(r) for r in all_env_ranks) else np.nan
        valid_ranks = [r for r in all_env_ranks if not np.isnan(r)]
        rank_range = f'{int(min(valid_ranks))}~{int(max(valid_ranks))}' if len(valid_ranks) >= 2 else ''

        # 3. Shukla变异数（环境间标准差）
        valid_em = [v for v in env_means_list if not np.isnan(v)]
        shukla_var = np.std(valid_em, ddof=1) if len(valid_em) >= 2 else 0

        # 4. 综合评分
        max_mean = df.groupby(genotype)[response].mean().max()
        yield_score = g_mean / max_mean * 50 if max_mean > 0 else 0

        cvs = (df.groupby(genotype)[response].std() / df.groupby(genotype)[response].mean() * 100).replace([np.inf, -np.inf], 0).fillna(0)
        max_cv = cvs.max()
        stability_score = (1 - g_cv/max_cv) * 50 if max_cv > 0 else 25

        total_score = yield_score + stability_score

        results.append({
            genotype: g,
            '总均值': round(g_mean, 2),
            '标准差': round(g_std, 2),
            'CV%': round(g_cv, 2),
            '平均排名': round(avg_rank, 1) if not np.isnan(avg_rank) else '-',
            '排名范围': rank_range,
            'Shukla变异数': round(shukla_var, 4),
            '产量分': round(yield_score, 1),
            '稳定性分': round(stability_score, 1),
            '综合分': round(total_score, 1),
        })

    return results


def _eberhart_russell_analysis(df, response, genotype, environment):
    """
    Eberhart-Russell (1966) 稳定性分析

    模型: Yij = μi + bi*Ij + dij
    其中 Ij = 环境指数 = 所有品种在第j环境的均值 - 总均值
          bi = 第i品种的回归系数
          s2di = 偏离回归的均方（线性偏差）
    """

    envs = sorted(df[environment].unique())
    genes = sorted(df[genotype].unique())

    if len(envs) < 2:
        return None

    env_mean_all = df.groupby(environment)[response].mean()
    grand_mean = df[response].mean()
    environmental_index = env_mean_all - grand_mean

    er_records = []
    regression_lines = []

    for g in genes:
        geno_means_per_env = []
        ei_values = []

        for e in envs:
            df_ge = df[(df[genotype]==g) & (df[environment]==e)]
            if len(df_ge) > 0:
                gm = df_ge[response].mean()
                geno_means_per_env.append(gm)
                ei_values.append(environmental_index[e])

        if len(geno_means_per_env) >= 3:
            y_arr = np.array(geno_means_per_env)
            x_arr = np.array(ei_values)

            slope, intercept, r_value, p_value, std_err = stats.linregress(x_arr, y_arr)

            predicted = intercept + slope * x_arr
            deviations = y_arr - predicted

            n = len(y_arr)
            ss_deviation = np.sum(deviations**2)
            s2_d = ss_deviation / (n - 2) if n > 2 else 0

            geno_overall_mean = np.mean(y_arr)

            er_records.append({
                genotype: g,
                '均值': round(geno_overall_mean, 2),
                '截距(a)': round(intercept, 4),
                '回归系数(b)': round(slope, 4),
                's2d (偏差MS)': round(s2_d, 4),
                'R2': round(r_value**2, 4),
                '判断':
                    '稳定' if abs(slope - 1) <= 0.2 and s2_d < np.var(y_arr)*0.3
                    else ('敏感' if slope > 1.2 else '迟钝'),
                '推荐':
                    '广泛推广' if (abs(slope - 1) <= 0.3 and s2_d < np.var(y_arr)*0.5 and geno_overall_mean >= grand_mean)
                    else ('特定区域' if slope > 1.2 else '一般')
            })

            regression_lines.append({
                'geno': g,
                'x': list(x_arr),
                'y_actual': list(y_arr),
                'y_fit': list(predicted),
                'b': slope,
                'overall_mean': geno_overall_mean
            })

    if len(er_records) == 0:
        return None

    er_df = pd.DataFrame(er_records)

    # 绘制ER回归图
    fig_er = make_subplots(specs=[[{"secondary_y": True}]])

    ei_vals = environmental_index.values
    x_min, x_max = float(ei_vals.min()), float(ei_vals.max())
    x_pad = (x_max - x_min) * 0.15
    x_plot = np.array([x_min - x_pad, x_max + x_pad])

    colors = px.colors.qualitative.Set1 + px.colors.qualitative.Set2 + px.colors.qualitative.Dark24

    for i, rl in enumerate(regression_lines):
        color = colors[i % len(colors)]
        # 只画回归线（去掉散点）
        intercept_i = rl['overall_mean'] - rl['b'] * np.mean(rl['x'])
        y_line = intercept_i + rl['b'] * x_plot
        fig_er.add_trace(go.Scatter(
            x=list(x_plot), y=list(y_line),
            mode='lines', name=f"{rl['geno']} (b={rl['b']:.2f})",
            line=dict(color=color, width=2.5),
            legendgroup=rl['geno']
        ), secondary_y=False)

    y_ref = grand_mean + 1.0 * x_plot
    fig_er.add_trace(go.Scatter(
        x=list(x_plot), y=list(y_ref),
        mode='lines', line=dict(color='gray', width=1.5, dash='dot'),
        name='b=1 (平均响应)', showlegend=True
    ), secondary_y=False)

    fig_er.update_layout(
        title='Eberhart-Russell 稳定性回归分析<br><sup>虚线=回归拟合 | 点线=b=1参考线</sup>',
        xaxis_title='环境指数 (Ij)',
        yaxis_title=f'{response}',
        height=550,
        hovermode='closest',
        legend=dict(font=dict(size=10))
    )

    env_idx_df = pd.DataFrame({
        '环境': envs,
        '环境均值': [env_mean_all[e] for e in envs],
        '环境指数(Ij)': [environmental_index[e] for e in envs],
    }).round(2)

    return (er_df, fig_er, env_idx_df)


# ========== Alpha/不完全区组设计 ==========
def alpha_lattice_anova(df):
    """Alpha Lattice不完全区组设计的方差分析"""
    st.markdown("### 🧬 Alpha/不完全区组设计分析")
    
    st.info("""
    **Alpha设计**使用混合模型，区组效应为随机效应：
    - 完整区组（Rep）：固定效应
    - 不完全区组（IB）：随机效应
    - 处理效应：固定效应
    
    数据需要包含：处理、不完全区组、完整区组、观测值
    """)
    
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    categorical_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
    
    col1, col2, col3 = st.columns(3)
    with col1:
        response = st.selectbox("响应变量", numeric_cols, key="alpha_y")
    with col2:
        treatment = st.selectbox("处理变量", categorical_cols, key="alpha_trt")
    with col3:
        other_cols = [c for c in categorical_cols if c != treatment]
        rep_block = st.selectbox("区组变量", other_cols, key="alpha_rep")
    
    try:
        # Alpha设计的混合模型（不完全区组作为随机效应）
        # 使用Type 3的混合模型分析
        formula = f'Q("{response}") ~ C(Q("{treatment}")) + C(Q("{rep_block}"))'
        model = ols(formula, data=df).fit()
        anova_table = anova_lm(model, typ=3)
        
        display_anova_table(anova_table, "不完全区组设计方差分析表")
        
        # 处理均值
        treatment_means = df.groupby(treatment)[response].agg(['mean', 'std', 'count']).round(3)
        treatment_means.columns = ['均值', '标准差', '重复数']
        st.markdown("#### 处理均值")
        st.dataframe(treatment_means.sort_values('均值', ascending=False))
        
        # 可视化
        fig = px.bar(treatment_means.reset_index().sort_values('均值', ascending=True),
                    x='均值', y=treatment, orientation='h', title=f'{response} 处理均值比较',
                    color='均值', color_continuous_scale='Blues')
        fig.update_layout(height=max(400, len(treatment_means) * 30), yaxis_title=treatment)
        st.plotly_chart(fig, use_container_width=True)
        
        # 多重比较
        tukey = pairwise_tukeyhsd(df[response], df[treatment], alpha=0.05)
        _display_tukey_result(tukey)
        
    except Exception as e:
        st.error(f"分析失败: {e}")


# ========== 增广设计分析 ==========
def augmented_anova(df):
    """增广设计的统计分析（对照有重复，测试无重复）"""
    st.markdown("### ➕ 增广设计分析")
    
    st.info("""
    **增广设计**分析特点：
    - 对照（Check）有重复，用于估计区组效应
    - 测试处理（Test）无重复，无法直接进行方差分析
    - 使用对照校正后的相对产量进行比较
    
    数据需要包含：处理、区组（如有）、类型（对照/测试）、观测值
    """)
    
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    categorical_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
    
    col1, col2 = st.columns(2)
    with col1:
        response = st.selectbox("响应变量", numeric_cols, key="aug_y")
    with col2:
        treatment = st.selectbox("处理变量", categorical_cols, key="aug_trt")
    
    # 检测是否有类型列
    type_col = None
    block_col = None
    for col in categorical_cols:
        if col != treatment:
            unique_vals = df[col].unique()
            if set(unique_vals).issubset({'对照', '测试', 'CK', 'Test', 'Check', '对照(重复)', '测试(无重复)'}):
                type_col = col
                break
    
    if type_col:
        st.success(f"检测到类型列: {type_col}")
    else:
        st.warning("未检测到类型列，请手动指定哪些是对照")
        type_col = st.selectbox("处理类型列（如有）", [None] + categorical_cols, key="aug_type")
    
    # 选择区组列
    block_cols = [c for c in categorical_cols if c not in [treatment, type_col]]
    if block_cols:
        block_col = st.selectbox("区组变量（可选）", [None] + block_cols, key="aug_block")
    
    try:
        # 分离对照和测试处理
        check_data = df[df[type_col].isin(['对照', 'CK', 'Check'])] if type_col else df[df[treatment].str.contains('CK|对照|ck', na=False)]
        test_data = df[df[type_col].isin(['测试', 'Test'])] if type_col else df[~df[treatment].str.contains('CK|对照|ck', na=False)]
        
        if len(check_data) == 0:
            st.error("未找到对照数据，请检查数据格式")
            return
        
        st.markdown(f"**数据概况：** 对照 {len(check_data)} 小区，测试处理 {len(test_data)} 小区")
        
        # 计算对照均值和区组效应
        check_means = check_data.groupby(treatment if type_col is None else treatment)[response].agg(['mean', 'count'])
        
        st.markdown("#### 对照处理统计")
        st.dataframe(check_means.round(3))
        
        # 计算校正后的测试处理产量
        if len(test_data) > 0 and block_col:
            block_means = check_data.groupby(block_col)[response].mean()
            grand_mean = check_data[response].mean()
            
            st.markdown("#### 测试处理校正产量")
            test_results = []
            for _, row in test_data.iterrows():
                block = row[block_col]
                block_effect = block_means.get(block, grand_mean) - grand_mean
                adjusted_yield = row[response] - block_effect
                test_results.append({
                    '处理': row[treatment],
                    '原始产量': row[response],
                    '区组效应': block_effect,
                    '校正产量': adjusted_yield
                })
            
            test_df = pd.DataFrame(test_results).sort_values('校正产量', ascending=False)
            st.dataframe(test_df.round(3))
        
        # 综合比较表
        st.markdown("#### 所有处理综合比较")
        all_means = df.groupby(treatment)[response].agg(['mean', 'std', 'count']).round(3)
        all_means.columns = ['均值', '标准差', '重复数']
        st.dataframe(all_means.sort_values('均值', ascending=False))
        
        # 可视化
        fig = px.box(df, x=treatment, y=response, title=f'{response} 处理分布',
                    color=type_col if type_col else None)
        fig.update_layout(height=400, xaxis_tick_angle=-45)
        st.plotly_chart(fig, use_container_width=True)
        
    except Exception as e:
        st.error(f"分析失败: {e}")


# ========== 间比法/对比法分析 ==========
def interval_contrast_anova(df):
    """间比法和对比法设计的分析 - 使用相对产量百分比法"""
    st.markdown("### 📈 间比法/对比法分析")
    
    st.info("""
    **间比法/对比法**使用相对产量百分比分析：
    
    **对比法**：相对产量 = (处理产量 / 相邻对照产量) × 100%
    
    **间比法**：理论对照 = (左CK + 右CK) / 2
               相对产量 = (处理产量 / 理论对照) × 100%
    
    **判断标准**：相对产量 >110% 可能显著优于对照
    """)
    
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    categorical_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
    
    col1, col2, col3 = st.columns(3)
    with col1:
        response = st.selectbox("响应变量", numeric_cols, key="ic_y")
    with col2:
        treatment = st.selectbox("处理变量", categorical_cols, key="ic_trt")
    with col3:
        position = st.selectbox("位置变量（可选）", [None] + categorical_cols, key="ic_pos")
    
    # 判断设计类型
    ck_treatments = df[df[treatment].isin(['CK', 'ck', '对照', 'CK1', 'CK2'])][treatment].unique()
    has_ck = len(ck_treatments) > 0
    
    if not has_ck:
        st.error("数据中未找到对照（CK），请确保处理列中包含 'CK' 或 '对照'")
        return
    
    # 分析方法选择
    analysis_type = st.radio("分析类型", ["自动检测", "对比法", "间比法"], horizontal=True)
    
    try:
        # 分离对照和处理
        ck_data = df[df[treatment].isin(['CK', 'ck', '对照', 'CK1', 'CK2'])]
        test_data = df[~df[treatment].isin(['CK', 'ck', '对照', 'CK1', 'CK2'])]
        
        st.markdown(f"**数据概况：** 对照 {len(ck_data)} 小区，测试处理 {len(test_data)} 小区")
        
        # 计算相对产量
        if position:
            # 按位置排序
            df_sorted = df.sort_values(position).reset_index(drop=True)
            
            if analysis_type in ["自动检测", "对比法"]:
                # 对比法分析
                results = []
                ck_yields = {}
                
                for idx, row in df_sorted.iterrows():
                    if row[treatment] in ['CK', 'ck', '对照', 'CK1', 'CK2']:
                        ck_yields[idx] = row[response]
                    else:
                        # 找到最近的对照
                        nearby_cks = [ck_yields.get(i) for i in range(max(0, idx-5), idx) 
                                   if i in ck_yields] + [ck_yields.get(i) for i in range(idx+1, min(len(df_sorted), idx+6)) 
                                   if i in ck_yields]
                        if nearby_cks:
                            relative = (row[response] / np.mean(nearby_cks)) * 100
                            results.append({
                                '处理': row[treatment],
                                '产量': row[response],
                                '邻近CK均值': np.mean(nearby_cks),
                                '相对产量(%)': relative,
                                '显著性': '***' if relative > 110 else ('**' if relative > 105 else ('*' if relative > 100 else ''))
                            })
                
                if results:
                    results_df = pd.DataFrame(results).sort_values('相对产量(%)', ascending=False)
                    st.markdown("#### 对比法分析结果")
                    st.dataframe(results_df.round(2))
            
            if analysis_type in ["自动检测", "间比法"]:
                # 间比法分析（需要识别区段）
                results = []
                current_segment = []
                
                for idx, row in df_sorted.iterrows():
                    if row[treatment] in ['CK', 'ck', '对照', 'CK1', 'CK2']:
                        if len(current_segment) > 0:
                            # 段末对照，计算段内测试处理的相对产量
                            left_ck = df_sorted.loc[current_segment[0][0], response]
                            right_ck = row[response]
                            theoretical_ck = (left_ck + right_ck) / 2
                            
                            for t_idx, t_row in current_segment:
                                relative = (t_row[response] / theoretical_ck) * 100
                                results.append({
                                    '处理': t_row[treatment],
                                    '产量': t_row[response],
                                    '理论CK': theoretical_ck,
                                    '相对产量(%)': relative,
                                    '判断': '优' if relative > 110 else ('可' if relative > 100 else '差')
                                })
                            current_segment = []
                    else:
                        current_segment.append((idx, row))
                
                if results:
                    results_df = pd.DataFrame(results).sort_values('相对产量(%)', ascending=False)
                    st.markdown("#### 间比法分析结果")
                    st.dataframe(results_df.round(2))
        
        # 可视化
        if analysis_type != "间比法":
            fig = px.bar(results_df if analysis_type in ["自动检测", "对比法"] else pd.DataFrame(),
                        x='处理', y='相对产量(%)',
                        title=f'{response} 相对产量分析',
                        color='相对产量(%)',
                        color_continuous_scale=['red', 'yellow', 'green'],
                        text='相对产量(%)')
            fig.add_hline(y=100, line_dash="dash", annotation_text="对照基准(100%)")
            fig.add_hline(y=110, line_dash="dot", annotation_text="显著标准(110%)")
            fig.update_layout(height=400, xaxis_tick_angle=-45)
            st.plotly_chart(fig, use_container_width=True)
        
    except Exception as e:
        st.error(f"分析失败: {e}")


# ========== 通用显示函数 ==========
def _rename_anova_index(anova_table, environment, genotype, block_var=None, is_met=False):
    """将ANOVA表的index重命名为中文变异来源名称"""
    rename_map = {}
    env_str = str(environment)
    geno_str = str(genotype)
    block_str = str(block_var) if block_var is not None else None
    block_label = '区组（环境内）' if is_met else '区组'

    for idx in anova_table.index:
        idx_str = str(idx)
        # 1. 交互项（包含冒号）优先匹配 — 必须同时含环境和基因型
        if ':' in idx_str and env_str in idx_str and geno_str in idx_str:
            rename_map[idx] = '基因型×环境'
        # 2. 区组项（在环境之前匹配，避免区组列名含环境名字符时误判）
        elif block_str is not None and block_str in idx_str:
            rename_map[idx] = block_label
        # 3. 环境主效应
        elif env_str in idx_str and 'C(Q(' in idx_str:
            rename_map[idx] = '环境'
        elif env_str == idx_str:
            rename_map[idx] = '环境'
        # 4. 基因型主效应
        elif geno_str in idx_str and 'C(Q(' in idx_str:
            rename_map[idx] = '基因型'
        elif geno_str == idx_str:
            rename_map[idx] = '基因型'
        # 5. 残差/误差
        elif 'Residual' in idx_str:
            rename_map[idx] = '误差'
        else:
            rename_map[idx] = idx

    renamed = anova_table.rename(index=rename_map)
    return renamed


def display_anova_table(anova_table, title):
    """格式化显示ANOVA表格（含均方列）"""

    # 清理表格
    display_table = anova_table.copy()

    # 自动清理 index 中的 C(Q("...")) 格式，只保留变量名
    cleaned_index = {}
    for idx in display_table.index:
        idx_str = str(idx)
        # 匹配 C(Q("var")) 或 C(Q('var')) 模式，提取变量名
        m = re.findall(r'C\(Q\(["\']([^"\']+)["\']\)\)', idx_str)
        if m:
            cleaned_index[idx] = ':'.join(m)
    if cleaned_index:
        display_table = display_table.rename(index=cleaned_index)

    # 添加均方(MS) = SS / df
    if 'sum_sq' in display_table.columns and 'df' in display_table.columns:
        safe_df = display_table['df'].replace(0, np.nan)
        display_table['MS'] = (display_table['sum_sq'] / safe_df).round(4)

    # 添加显著性标记
    def add_sig(p):
        if pd.isna(p): return "-"
        if p < 0.001: return "***"
        elif p < 0.01: return "**"
        elif p < 0.05: return "*"
        else: return "n.s."

    if 'PR(>F)' in display_table.columns or 'p-value' in display_table:
        pcol = 'PR(>F)' if 'PR(>F)' in display_table.columns else 'p-value'  # type: ignore
        display_table['显著性'] = display_table[pcol].apply(add_sig)  # type: ignore
        display_table.rename(columns={pcol: 'p值'}, inplace=True)  # type: ignore

    # 重命名
    rename_map = {
        'sum_sq': '平方和(SS)',
        'df': '自由度(df)',
        'MS': '均方(MS)',
        'F': 'F值'
    }
    display_table.rename(columns=rename_map, inplace=True)  # type: ignore

    st.markdown(f"#### {title}")
    st.dataframe(display_table.round(4), use_container_width=True)


def plot_significance_groups(tukey_result, treatment_means, response_var):
    """绘制显著性字母分组图"""
    
    try:
        summary_df = pd.DataFrame(data=tukey_result._results_table.data[1:], 
                                  columns=tukey_result._results_table.data[0])  # type: ignore
        
        groups = set(summary_df.iloc[:, 0].unique()) | set(summary_df.iloc[:, 1].unique())
        group_order = sorted(groups, key=lambda x: treatment_means.loc[x, 'mean'] if x in treatment_means.index else 0, reverse=True)  # type: ignore
        
        # 构建字母标注
        letter_dict = {}
        letters = list('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
        current_letter_idx = 0
        
        for g in group_order:
            comparisons = summary_df[
                ((summary_df.iloc[:, 0] == g) | (summary_df.iloc[:, 1] == g)) & 
                (summary_df.iloc[:, -1] == True)
            ]
            
            if len(comparisons) > 0:
                letter_dict[g] = letters[current_letter_idx]
                current_letter_idx += 1
            else:
                letter_dict[g] = letters[current_letter_idx]
        
        means_sorted = treatment_means.sort_values('mean', ascending=True)
        fig = go.Figure()
        
        colors = ['#3498db', '#2ecc71', '#e74c3c', '#f39c12', '#9b59b6', '#1abc9c']
        for i, (idx, row) in enumerate(means_sorted.iterrows()):
            letter = letter_dict.get(idx, '')
            fig.add_trace(go.Bar(
                x=[row['mean']],
                name=f"{idx} ({letter})",
                marker_color=colors[i % len(colors)]
            ))
        
        fig.update_layout(
            barmode='group',
            title=f'{response_var} 处理均值比较（字母相同表示差异不显著）',
            showlegend=True,
            height=400
        )
        st.plotly_chart(fig, use_container_width=True)
        
    except Exception as e:
        st.caption(f"字母分组图生成失败: {e}")


if __name__ == "__main__":
    render_anova()