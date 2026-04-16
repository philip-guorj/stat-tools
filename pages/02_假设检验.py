# 假设检验模块

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
import numpy as np
from scipy import stats
import plotly.graph_objects as go
import plotly.express as px

from utils.data_manager import get_data_manager
from utils.styles import get_global_css

def render_hypothesis_test():
    st.markdown(get_global_css(), unsafe_allow_html=True)
    st.markdown('<div class="section-header">🔬 假设检验</div>', unsafe_allow_html=True)
    
    # 功能简介下拉菜单
    with st.expander("📖 功能简介", expanded=False):
        st.markdown("""
        **假设检验**用于判断样本数据是否支持某个统计假设，是科学推断的重要工具。
        
        | 检验方法 | 用途 | 数据要求 |
        |---------|------|---------|
        | 单样本t检验 | 检验样本均值是否等于某值 | 1个数值变量 |
        | 独立双样本t检验 | 两组独立样本均值比较 | 1个数值变量+1个分组变量 |
        | 配对样本t检验 | 配对数据前后比较 | 2个数值变量 |
        | 卡方独立性检验 | 分类变量关联检验 | 2个分类变量 |
        | 正态性检验 | 检验数据是否正态分布 | 1个或多个数值变量 |
        | 方差齐性检验 | 多组方差是否相等 | 1个数值变量+分组变量 |
        | 单因素ANOVA | 多组均值比较 | 1个数值变量+1个分组变量 |
        | 非参数检验 | 不满足正态假设时的替代检验 | 数值/有序变量 |
        
        **使用建议**：先进行正态性检验，根据结果选择参数或非参数检验。
        """)
        
        st.markdown("""
        <div class="method-guide">
        <div class="method-guide-title">检验方法选择流程</div>
        <div class="method-guide-content">
        <b>1. 先判断数据分布</b>：用<b>正态性检验</b> → p>0.05 为正态分布<br>
        <b>2. 两组比较</b>：<br>
        &nbsp;&nbsp;- 正态 → <b>独立双样本t检验</b><br>
        &nbsp;&nbsp;- 非正态 → <b>非参数检验(Mann-Whitney U)</b><br>
        <b>3. 多组比较</b>：<br>
        &nbsp;&nbsp;- 正态+方差齐 → <b>单因素ANOVA</b><br>
        &nbsp;&nbsp;- 正态+方差不齐 → <b>非参数检验(Kruskal-Wallis)</b><br>
        <b>4. 分类数据</b>：用<b>卡方独立性检验</b>
        </div>
        </div>
        """, unsafe_allow_html=True)
    
    dm = get_data_manager()
    
    if not dm.is_loaded:
        st.warning("⚠️ 请先上传数据文件")
        return
    
    df = dm.data
    numeric_cols = dm.get_numeric_columns()
    categorical_cols = dm.get_categorical_columns()
    
    # 检验类型选择
    test_type = st.selectbox(
        "选择检验方法",
        [
            "---",
            "单样本t检验",
            "独立双样本t检验",
            "配对样本t检验",
            "卡方独立性检验",
            "正态性检验 (Shapiro-Wilk)",
            "方差齐性检验 (Levene)",
            "单因素方差分析 (One-way ANOVA)",
            "非参数检验 (Mann-Whitney U / Kruskal-Wallis)"
        ]
    )
    
    st.markdown("---")
    
    if test_type == "---":
        st.info("👆 请从上方下拉菜单选择检验方法，或查看功能简介了解各方法用途")
        return
    
    elif test_type == "单样本t检验":
        one_sample_t_test(df, numeric_cols)
    
    elif test_type == "独立双样本t检验":
        independent_t_test(df, numeric_cols, categorical_cols)
    
    elif test_type == "配对样本t检验":
        paired_t_test(df, numeric_cols)
    
    elif test_type == "卡方独立性检验":
        chi_square_test(df, categorical_cols)
    
    elif test_type == "正态性检验 (Shapiro-Wilk)":
        normality_test(df, numeric_cols)
    
    elif test_type == "方差齐性检验 (Levene)":
        levene_test(df, numeric_cols, categorical_cols)
    
    elif test_type == "单因素方差分析 (One-way ANOVA)":
        oneway_anova(df, numeric_cols, categorical_cols)
    
    elif test_type == "非参数检验 (Mann-Whitney U / Kruskal-Wallis)":
        nonparametric_test(df, numeric_cols, categorical_cols)


def show_test_summary():
    """显示检验方法概览"""
    st.markdown("""
    ### 📋 假设检验方法概览
    
    | 检验方法 | 用途 | 数据要求 |
    |---------|------|---------|
    | 单样本t检验 | 检验样本均值是否等于某值 | 1个数值变量 |
    | 独立双样本t检验 | 两组独立样本均值比较 | 1个数值变量+1个分组变量 |
    | 配对样本t检验 | 配对数据前后比较 | 2个数值变量 |
    | 卡方独立性检验 | 分类变量关联检验 | 2个分类变量 |
    | 正态性检验 | 检验数据是否正态分布 | 1个或多个数值变量 |
    | 方差齐性检验 | 多组方差是否相等 | 1个数值变量+分组变量 |
    | 单因素ANOVA | 多组均值比较 | 1个数值变量+1个分组变量 |
    | 非参数检验 | 不满足正态假设时的替代检验 | 数值/有序变量 |
    """)


def interpret_pvalue(p, alpha=0.05):
    """p值解释"""
    if p < 0.001:
        return f"p < 0.001 ***（极显著）"
    elif p < 0.01:
        return f"p = {p:.4f} **（极显著）" + ("**" if p >= 0.001 else "***")
    elif p < 0.05:
        return f"p = {p:.4f} *（显著）*"
    else:
        return f"p = {p:.4f} （不显著）"


def result_box(statistic, p_value, df=None, test_name=""):
    """显示检验结果框"""
    with st.container():
        col_sig, col_stat = st.columns(2)
        
        # 判断显著性
        sig_level = "***" if p_value < 0.001 else "**" if p_value < 0.01 else "*" if p_value < 0.05 else "n.s."
        
        with col_sig:
            st.metric("显著性水平", sig_level)
        
        with col_stat:
            if df is not None:
                st.metric(f"{test_name}", f"F({df[0]},{df[1]}) = {statistic:.4f}")
            else:
                st.metric(f"{test_name}", f"t = {statistic:.4f}" if abs(statistic) < 100 else f"W = {statistic:.4f}")
        
        st.markdown(f"**p值**: {interpret_pvalue(p_value)}")
        st.markdown(f"*H₀拒绝*: {'是' if p_value < 0.05 else '否'} (α = 0.05)")


def one_sample_t_test(df, numeric_cols):
    st.markdown("### 📌 单样本t检验")
    
    col_select = st.selectbox("选择检验变量", numeric_cols)
    hypothesized_mean = st.number_input("原假设均值 (μ₀)", value=0.0)
    
    data = df[col_select].dropna()
    
    t_stat, p_value = stats.ttest_1samp(data, hypothesized_mean)
    ci = stats.t.interval(0.95, len(data)-1, loc=data.mean(), scale=stats.sem(data))
    
    st.markdown("#### 检验结果")
    result_box(t_stat, p_value, test_name="t统计量")
    
    m1, m2, m3 = st.columns(3)
    with m1: st.metric("样本均值", f"{data.mean():.4f}")
    with m2: st.metric("标准误", f"{stats.sem(data):.4f}")
    with m3: st.metric("95%置信区间", f"[{ci[0]:.3f}, {ci[1]:.3f}]")
    
    # 可视化
    fig = go.Figure()
    x_range = np.linspace(data.mean()-4*data.std(), data.mean()+4*data.std(), 200)
    fig.add_trace(go.Scatter(x=x_range, y=stats.t.pdf(x_range, len(data)-1, data.mean(), data.std()/np.sqrt(len(data))),
                             mode='lines', name='t分布', line=dict(color='blue')))
    fig.add_vline(x=data.mean(), line_dash="dash", line_color="red", 
                  annotation_text=f"样本均值={data.mean():.2f}")
    fig.add_vline(x=hypothesized_mean, line_dash="dot", line_color="green",
                  annotation_text=f"假设均值={hypothesized_mean}")
    fig.update_layout(title='单样本t检验可视化', xaxis_title='值', height=400)
    st.plotly_chart(fig, use_container_width=True)


def independent_t_test(df, numeric_cols, categorical_cols):
    st.markdown("### 📌 独立双样本t检验")
    
    var_col = st.selectbox("选择检验变量", numeric_cols, key="ind_t_var")
    group_col = st.selectbox("选择分组变量", categorical_cols, key="ind_t_group")
    equal_var = st.checkbox("假设方差相等 (Welch's t-test)", value=False)
    
    groups = df[group_col].dropna().unique()
    if len(groups) != 2:
        st.warning(f"分组变量 '{group_col}' 需要恰好2个类别，当前有 {len(groups)} 个类别")
        return
    
    g1_data = df[df[group_col]==groups[0]][var_col].dropna()
    g2_data = df[df[group_col]==groups[1]][var_col].dropna()
    
    t_stat, p_value = stats.ttest_ind(g1_data, g2_data, equal_var=equal_var)
    
    result_box(t_stat, p_value, test_name="t统计量")
    
    c1, c2, c3 = st.columns(3)
    with c1: 
        st.metric(f"{groups[0]} 均值", f"{g1_data.mean():.4f} (n={len(g1_data)})")
    with c2: 
        st.metric(f"{groups[1]} 均值", f"{g2_data.mean():.4f} (n={len(g2_data)})")
    with c3: 
        st.metric("均值差异", f"{abs(g1_data.mean() - g2_data.mean()):.4f}")
    
    fig = px.box(df, x=group_col, y=var_col, color=group_col,
                 title=f'{var_col} 按{group_col}分组的分布')
    st.plotly_chart(fig, use_container_width=True)


def paired_t_test(df, numeric_cols):
    st.markdown("### 📌 配对样本t检验")
    
    col1 = st.selectbox("选择第一组变量", numeric_cols, key="pair_1")
    col2 = st.selectbox("选择第二组变量", [c for c in numeric_cols if c != col1], key="pair_2")
    
    d1 = df[col1].dropna()
    d2 = df[col2].dropna()
    
    min_len = min(len(d1), len(d2))
    t_stat, p_value = stats.ttest_rel(d1.iloc[:min_len], d2.iloc[:min_len])
    
    result_box(t_stat, p_value, test_name="t统计量")
    
    fig = go.Figure()
    idx = range(min_len)
    fig.add_trace(go.Scatter(x=list(idx), y=(d1.values-d2.values)[:min_len],
                              mode='lines+markers', name='差值'))
    fig.add_hline(y=0, line_dash="dash", line_color="red")
    fig.update_layout(title='配对差异图', xaxis_title='样本序号', yaxis_title='差值', height=350)
    st.plotly_chart(fig, use_container_width=True)


def chi_square_test(df, categorical_cols):
    st.markdown("### 📌 卡方独立性检验")
    
    if len(categorical_cols) < 2:
        st.warning("需要至少2个分类变量")
        return
    
    var1 = st.selectbox("选择行变量", categorical_cols, key="chi_row")
    var2 = st.selectbox("选择列变量", [c for c in categorical_cols if c != var1], key="chi_col")
    
    contingency = pd.crosstab(df[var1], df[var2])
    chi2, p_value, dof, expected = stats.chi2_contingency(contingency)
    
    result_box(chi2, p_value, test_name="χ²统计量")
    st.metric("自由度", str(dof))
    
    tab_obs, tab_exp = st.tabs(["观测频数", "期望频数"])
    with tab_obs: st.dataframe(contingency)
    with tab_exp: st.dataframe(pd.DataFrame(expected.round(2),
                                           index=contingency.index,
                                           columns=contingency.columns))


def normality_test(df, numeric_cols):
    st.markdown("### 📌 正态性检验 (Shapiro-Wilk)")
    
    selected = st.multiselect("选择变量", numeric_cols, default=numeric_cols[:5])
    
    results = []
    for col in selected:
        data = df[col].dropna()
        # Shapiro-Wilk限制样本量5000
        sample = data.sample(min(len(data), 5000), random_state=42)
        stat, p = stats.shapiro(sample)
        results.append({
            '变量': col,
            'W统计量': round(stat, 4),
            'p值': round(p, 6),
            '样本量': len(sample),
            '结论': '正态' if p > 0.05 else '非正态'
        })
    
    result_df = pd.DataFrame(results).set_index('变量')
    st.dataframe(result_df.style.apply(lambda x: ['background-color:#d4edda' if v=='正态' else 'background-color:#f8d7da' 
                                                  for v in x], subset=['结论']), use_container_width=True)


def levene_test(df, numeric_cols, categorical_cols):
    st.markdown("### 📌 方差齐性检验 (Levene)")
    
    var_col = st.selectbox("选择变量", numeric_cols, key="lev_var")
    group_col = st.selectbox("选择分组变量", categorical_cols, key="lev_group")
    
    groups = [g[var_col].dropna().values for _, g in df.groupby(group_col)]
    stat, p = stats.levene(*groups)
    
    result_box(stat, p, test_name="Levene W")
    st.write(f"H₀: 各组方差相等 → {'不拒绝H₀（方差齐）' if p > 0.05 else '拒绝H〇（方差不齐）'}")


def oneway_anova(df, numeric_cols, categorical_cols):
    st.markdown("### 📌 单因素方差分析 (One-way ANOVA)")
    
    var_col = st.selectbox("选择因变量", numeric_cols, key="anova_var")
    group_col = st.selectbox("选择自变量（分组）", categorical_cols, key="anova_group")
    
    groups = [g[var_col].dropna() for _, g in df.groupby(group_col)]
    f_stat, p = stats.f_oneway(*groups)
    
    # 计算效应量 eta-squared
    all_data = np.concatenate(groups)
    ss_between = sum(len(g)*(g.mean()-all_data.mean())**2 for g in groups)
    ss_total = np.sum((all_data-all_data.mean())**2)
    eta_sq = ss_between/ss_total if ss_total > 0 else 0
    
    k = len(groups)
    n_total = len(all_data)
    
    result_box(f_stat, p, df=[k-1, n_total-k], test_name="F统计量")
    
    c1, c2 = st.columns(2)
    with c1: st.metric("η² (效应量)", f"{eta_sq:.4f}")
    with c2: st.metric(f"组数", f"k = {k}")
    
    # 组间比较表
    st.markdown("#### 各组描述统计")
    group_stats = []
    for name, g in df.groupby(group_col):
        group_stats.append({
            '组别': name,
            'n': len(g[var_col]),
            '均值': round(g[var_col].mean(), 3),
            '标准差': round(g[var_col].std(), 3),
            '标准误': round(stats.sem(g[var_col].dropna()), 3),
            '95%CI下限': round(g[var_col].mean() - 1.96*stats.sem(g[var_col].dropna()), 3),
            '95%CI上限': round(g[var_col].mean() + 1.96*stats.sem(g[var_col].dropna()), 3),
        })
    st.dataframe(pd.DataFrame(group_stats))
    
    fig = px.box(df, x=group_col, y=var_col, color=group_col,
                 title=f'{var_col} 的组间差异')
    st.plotly_chart(fig, use_container_width=True)


def nonparametric_test(df, numeric_cols, categorical_cols):
    st.markdown("### 📌 非参数检验")
    
    test_method = st.radio("选择检验方法", ["Mann-Whitney U (两组)", "Kruskal-Wallis (多组)"], horizontal=True)
    
    var_col = st.selectbox("选择变量", numeric_cols, key="np_var")
    group_col = st.selectbox("选择分组变量", categorical_cols, key="np_group") if categorical_cols else None
    
    if not group_col:
        st.warning("需要分组变量")
        return
    
    groups = list(df[group_col].unique())
    
    if test_method == "Mann-Whitney U (两组)":
        if len(groups) < 2:
            st.warning("需要至少2组")
            return
        
        g1 = df[df[group_col]==groups[0]][var_col].dropna()
        g2 = df[df[group_col]==groups[1]][var_col].dropna()
        u_stat, p = stats.mannwhitneyu(g1, g2, alternative='two-sided')
        result_box(u_stat, p, test_name="U统计量")
        
    else:
        group_data = [g[var_col].dropna().values for _, g in df.groupby(group_col)]
        h_stat, p = stats.kruskal(*group_data)
        result_box(h_stat, p, test_name="H统计量")


if __name__ == "__main__":
    render_hypothesis_test()