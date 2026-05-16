# 回归分析模块

import os
import sys
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

from utils.data_manager import get_current_dm
from utils.styles import inject_css
from utils.visitor_logger import log_visit
from billing.billing import require_auth

# ========== 统一延迟导入（自 utils.imports）==========
from utils.imports import get_sm as _get_sm, get_vif as _get_vif


def _get_summary_table(model, table_idx=1):
    """获取模型summary表格，兼容不同版本的statsmodels
    
    Args:
        model: 拟合的statsmodels模型
        table_idx: 表格索引 (0=整体信息, 1=系数表)
        
    Returns:
        DataFrame 或 SimpleTable对象
    """
    try:
        # 新版 statsmodels (0.14+): 使用 summary_df 或 summary().tables
        # 尝试直接从模型获取DataFrame
        if hasattr(model, 'summary_frame') and table_idx == 1:
            return model.summary_frame()
        
        # 尝试 pvalues 和 params 构建系数表
        if table_idx == 1:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                coef_df = pd.DataFrame({
                    '': model.params.index,
                    '系数': model.params.values,
                    '标准误': model.bse.values,
                    't值': model.tvalues.values,
                    'P>|t|': model.pvalues.values,
                    '95%CI下': model.conf_int()[0].values,
                    '95%CI上': model.conf_int()[1].values
                }).set_index('')
                return coef_df
        
        return model.summary().tables[table_idx]
        
    except Exception:
        # 回退到旧版方式
        try:
            return model.summary().tables[table_idx]
        except (AttributeError, IndexError):
            # 最后回退：手动构建
            if table_idx == 1:
                coef_df = pd.DataFrame({
                    '': model.params.index.tolist(),
                    '系数': model.params.values,
                    '标准误': getattr(model, 'bse', [np.nan]*len(model.params)).values if hasattr(model.bse, '__iter__') else model.bse,
                    't值': model.tvalues.values if hasattr(model, 'tvalues') else [np.nan]*len(model.params),
                    'P>|t|': model.pvalues.values,
                })
                return coef_df.set_index('')
            raise


def render_regression():
    require_auth()
    log_visit("回归分析")
    inject_css()
    st.markdown('<div class="section-header">📉 回归分析</div>', unsafe_allow_html=True)

    
    # 功能简介下拉菜单
    with st.expander("📖 功能简介", expanded=False):
        st.markdown("""
        **回归分析**用于研究变量间的定量关系，建立预测模型或探索影响因素。
        
        | 回归方法 | 用途 | 适用场景 |
        |---------|------|---------|
        | 简单线性回归 | 研究两个变量的线性关系 | 1个自变量+1个因变量 |
        | 多元线性回归 | 多个自变量对因变量的影响 | 多个自变量+1个连续因变量 |
        | 多项式回归 | 处理非线性关系 | 变量间存在曲线关系 |
        | 逐步回归 | 自动筛选重要变量 | 自变量较多时简化模型 |
        | Logistic回归 | 二分类结果的预测 | 因变量为二分类（是/否） |
        
        **使用建议**：先做散点图观察变量关系，再选择合适的回归方法。
        """)
        
        st.markdown("""
        <div class="method-guide">
        <div class="method-guide-title">回归方法选择指南</div>
        <div class="method-guide-content">
        <b>1. 确定因变量类型</b>：连续（产量、株高等）→ 线性回归；二分类（发病/不发病）→ Logistic回归<br>
        <b>2. 确定自变量数量</b>：1个 → 简单线性回归；多个 → 多元线性回归<br>
        <b>3. 检查线性关系</b>：散点图呈曲线趋势 → 多项式回归<br>
        <b>4. 变量较多时</b>：不确定哪些变量重要 → 逐步回归自动筛选
        </div>
        </div>
        """, unsafe_allow_html=True)
    
    dm = get_current_dm()
    
    if not dm.is_loaded:
        st.warning("⚠️ 请从首页上传数据")
        return
    
    df = dm.data
    numeric_cols = dm.get_numeric_columns()
    
    reg_type = st.selectbox(
        "选择回归分析方法",
        [
            "---",
            "简单线性回归",
            "多元线性回归",
            "多项式回归",
            "逐步回归",
            "Logistic回归"
        ]
    )
    
    st.markdown("---")
    
    if reg_type == "---":
        st.info("👆 请从上方下拉菜单选择回归方法，或查看功能简介了解各方法用途")
        return
    
    elif reg_type == "简单线性回归":
        simple_linear_regression(df, numeric_cols)
    
    elif reg_type == "多元线性回归":
        multiple_regression(df, numeric_cols)
    
    elif reg_type == "多项式回归":
        polynomial_regression(df, numeric_cols)
    
    elif reg_type == "逐步回归":
        stepwise_regression(df, numeric_cols)
    
    elif reg_type == "Logistic回归":
        logistic_regression(df, numeric_cols)


def show_regression_overview():
    st.markdown("""
    ### 📋 回归分析方法概览
    
    | 方法 | 用途 | 自变量数 |
    |------|------|---------|
    简单线性回归 | Y = aX + b，单一自变量预测 | 1 |
    多元线性回归 | Y = β₀ + β₁X₁ + ... + βₙXₙ，多因素影响分析 | ≥2 |
    多项式回归 | 非线性关系拟合（二次、三次等） | 1(扩展) |
    逐步回归 | 自动筛选重要变量 | 多个 |
    Logistic回归 | 分类问题（0/1） | 多个 |
    """)


def simple_linear_regression(df, numeric_cols):
    st.markdown("### 📈 简单线性回归: Y = aX + b")
    
    st.info("""
    **简单线性回归**用于研究两个连续变量之间的线性关系。
    
    **数据要求**：1个因变量(Y) + 1个自变量(X)，均为数值型。
    
    **模型**：Y = aX + b（截距 + 斜率×自变量）。
    
    **关键指标**：
    - **R²**：模型解释的变异比例，越接近1拟合越好
    - **p值**：回归方程整体显著性
    - **标准误(SE)**：回归系数的估计精度
    
    **前提条件**：线性关系、残差正态、残差方差齐、独立性。
    
    **输出**：回归方程、ANOVA表、散点图+回归线+置信带、残差诊断图。
    """)
    
    col1, col2 = st.columns(2)
    with col1:
        y_var = st.selectbox("因变量 (Y)", numeric_cols, key="slr_y")
    with col2:
        x_var = st.selectbox("自变量 (X)", [c for c in numeric_cols if c != y_var], key="slr_x")
    
    x_data = df[x_var].dropna()
    y_data = df[y_var].dropna()
    
    # 对齐数据
    common_idx = x_data.index.intersection(y_data.index)
    x = x_data.loc[common_idx].values
    y = y_data.loc[common_idx].values
    
    # 拟合模型
    slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
    y_pred = slope * x + intercept
    
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r_squared = 1 - ss_res / ss_tot
    
    # 结果展示
    st.markdown("#### 回归方程与统计量")
    
    eq_col1, eq_col2 = st.columns([1, 2])
    with eq_col1:
        st.markdown("**回归方程:**")
        st.code(f"Y = {slope:.4f} × X + ({intercept:.4f})", language=None)
    
    with eq_col2:
        m1, m2, m3, m4 = st.columns(4)
        with m1: st.metric("R²", f"{r_squared:.4f}")
        with m2: st.metric("R", f"{np.sqrt(r_squared):.4f}")
        with m3: st.metric("p值", f"{p_value:.2e}")
        with m4: st.metric("标准误(SE)", f"{std_err:.4f}")
    
    # ANOVA表格
    n = len(y)
    k = 1  # 单一自变量
    ms_reg = ss_res / k
    ms_res = ss_res / (n - k - 1)
    f_stat = ms_reg / ms_res
    f_p = 1 - stats.f.cdf(f_stat, k, n-k-1)
    
    anova_data = {
        '变异来源': ['回归', '残差', '总计'],
        '平方和': [ss_tot - ss_res, ss_res, ss_tot],
        '自由度': [k, n-k-1, n-1],
        '均方': [ms_reg, ms_res, '-'],
        'F值': [f_stat, '-', '-'],
        'p值': [f_p, '-', '-']
    }
    st.dataframe(pd.DataFrame(anova_data).set_index('变异来源').round(4))
    
    # 散点图+回归线
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    fig.add_trace(go.Scatter(x=x, y=y, mode='markers', name='观测值',
                             marker_color='rgba(55,128,191,0.6)', 
                             marker_size=8,
                             hovertemplate=f'{x_var}: %{{x}}<br>{y_var}: %{{y}}'))
    
    x_line = np.linspace(np.min(x), np.max(x), 100)
    fig.add_trace(go.Scatter(x=x_line, y=slope*x_line + intercept, 
                            mode='lines', name='回归线',
                            line=dict(color='red', width=3)))
    
    # 置信区间
    se_pred = std_err * np.sqrt(1/n + (x_line - np.mean(x))**2/np.sum((x-np.mean(x))**2))
    ci_upper = slope * x_line + intercept + 1.96 * se_pred
    ci_lower = slope * x_line + intercept - 1.96 * se_pred
    
    fig.add_trace(go.Scatter(x=np.concatenate([x_line, x_line[::-1]]),
                            y=np.concatenate([ci_lower, ci_upper[::-1]]),
                            fill='toself', fillcolor='rgba(255,0,0,0.15)',
                            line=dict(color='rgba(255,255,255,0)'),
                            showlegend=False, name='95% 置信区间'))
    
    eq_str = f'Y = {slope:.3f}X + {intercept:.3f}, R²={r_squared:.4f}'
    fig.update_layout(title=f'{y_var} vs {x_var}<br><sup>{eq_str}</sup>',
                     xaxis_title=x_var, yaxis_title=y_var, height=500,
                     legend_title_text=None)
    st.plotly_chart(fig, use_container_width=True)
    
    # 残差诊断图
    residuals = y - y_pred
    standardized_residuals = residuals / np.std(residuals)
    
    diag_col1, diag_col2 = st.columns(2)
    
    with diag_col1:
        fig_resid = go.Figure()
        fig_resid.add_trace(go.Scatter(x=y_pred, y=residuals, mode='markers',
                                       marker_color='blue', opacity=0.6))
        fig_resid.add_hline(y=0, line_dash='dash', line_color='red')
        fig_resid.update_layout(title='残差 vs 拟合值', 
                               xaxis_title='拟合值', yaxis_title='残差', height=350)
        st.plotly_chart(fig_resid, use_container_width=True)
    
    with diag_col2:
        # Q-Q图
        from scipy.stats import probplot
        qq_data = probplot(residuals, dist="norm")
        
        fig_qq = go.Figure()
        fig_qq.add_trace(go.Scatter(x=qq_data[0][1], y=qq_data[1],
                                    mode='markers', name='残差'))
        qq_x = np.array([min(qq_data[0][1]), max(qq_data[0][1])])
        fig_qq.add_trace(go.Scatter(x=qq_x, y=qq_x, mode='lines',
                                    line_dash='dash', name='参考线'))
        fig_qq.update_layout(title='残差Q-Q正态检验', height=350)
        st.plotly_chart(fig_qq, use_container_width=True)


def multiple_regression(df, numeric_cols):
    st.markdown("### 📊 多元线性回归")
    
    st.info("""
    **多元线性回归**用于研究多个自变量对因变量的联合影响。
    
    **数据要求**：1个因变量(Y) + ≥2个自变量(X₁...Xₙ)，均为数值型。
    
    **模型**：Y = β₀ + β₁X₁ + β₂X₂ + ... + βₙXₙ。
    
    **关键指标**：
    - **R² / 调整R²**：模型解释力（调整R²对变量数做了惩罚，更可靠）
    - **VIF**：方差膨胀因子，VIF>10提示多重共线性
    - **标准化系数(Beta)**：比较各自变量相对重要性
    
    **输出**：回归方程、系数表(含VIF)、ANOVA表、残差诊断图、标准化系数。
    """)
    
    y_var = st.selectbox("因变量 (Y)", numeric_cols, key="mlr_y")
    x_vars = st.multiselect(
        "选择自变量 (X₁...Xₙ)", 
        [c for c in numeric_cols if c != y_var],
        default=[c for c in numeric_cols if c != y_var][:3]
    )
    
    if len(x_vars) < 1:
        st.warning("请至少选择一个自变量")
        return
    
    # 准备数据
    clean_df = df[[y_var] + x_vars].dropna()
    y = clean_df[y_var]
    X = clean_df[x_vars]
    X_const = _get_sm().add_constant(X)
    
    # OLS拟合
    model = _get_sm().OLS(y, X_const).fit()
    
    # 结果展示
    st.markdown("#### 模型摘要")
    
    sum_col1, sum_col2, sum_col3, sum_col4 = st.columns(4)
    with sum_col1: st.metric("R²", f"{model.rsquared:.4f}")
    with sum_col2: st.metric("调整R²", f"{model.rsquared_adj:.4f}")
    with sum_col3: st.metric("F统计量", f"{model.fvalue:.4f}")
    with sum_col4: st.metric("p值(F)", f"{model.f_pvalue:.2e}")
    
    # 方程显示
    coef = model.params
    equation = f"{y_var} = {coef['const']:.4f}"
    for var in x_vars:
        sign = "+" if coef[var] >= 0 else "-"
        equation += f" {sign} {abs(coef[var]):.4f}×{var}"
    
    st.code(equation, language=None)
    
    tab_coef, tab_ano, tab_diag = st.tabs(["系数表", "方差分析", "诊断"])
    
    with tab_coef:
        # VIF计算
        vif_func = _get_vif()
        vif_data = pd.DataFrame()
        vif_data["变量"] = x_vars
        vif_data["VIF"] = [vif_func(X_const.values, i+1) for i in range(len(x_vars))]
        
        coef_summary = _get_summary_table(model, table_idx=1)
        if isinstance(coef_summary, pd.DataFrame):
            coef_df = coef_summary
        else:
            coef_df = pd.DataFrame(coef_summary.data[1:], columns=coef_summary.data[0]).set_index('')
        vif_df = vif_data.set_index('变量')
        combined = coef_df.join(vif_df, how='left')
        st.dataframe(combined.round(4), use_container_width=True)
        
        st.caption("*VIF > 10 表示存在多重共线性")  # VIF为通用统计缩写，保留
    
    with tab_ano:
        # sm.OLS矩阵模式下anova_lm需要design_info（仅formula API提供），
        # 新版statsmodels会抛AttributeError，因此手动构建type II ANOVA表
        try:
            anova_table = _get_sm().stats.anova_lm(model, typ=2)
        except (AttributeError, ValueError):
            # 手动构建ANOVA表
            n = int(model.nobs)
            k = int(model.df_model)
            ss_model = float(model.ess)
            ss_resid = float(model.ssr)
            ss_total = ss_model + ss_resid
            ms_model = ss_model / k if k > 0 else 0
            ms_resid = ss_resid / model.df_resid if model.df_resid > 0 else 0
            f_val = float(model.fvalue) if hasattr(model, 'fvalue') else (ms_model / ms_resid if ms_resid > 0 else 0)
            p_val = float(model.f_pvalue) if hasattr(model, 'f_pvalue') else 0
            anova_table = pd.DataFrame({
                'df': [k, model.df_resid, n - 1],
                'sum_sq': [ss_model, ss_resid, ss_total],
                'mean_sq': [ms_model, ms_resid, ''],
                'F': [f_val, '', ''],
                'PR(>F)': [p_val, '', '']
            }, index=['回归', '残差', '总计'])
        display_anova_ml_table(anova_table)
    
    with tab_diag:
        residuals = model.resid
        fitted = model.fittedvalues
        
        d1, d2 = st.columns(2)
        with d1:
            fig1 = go.Figure()
            fig1.add_trace(go.Scatter(x=fitted, y=residuals, mode='markers', opacity=0.6))
            fig1.add_hline(y=0, line_dash='dash')
            fig1.update_layout(title='残差 vs 拟合值', height=300)
            st.plotly_chart(fig1, use_container_width=True)
        
        with d2:
            from scipy.stats import probplot
            qq_d = probplot(residuals)
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(x=qq_d[0][1], y=qq_d[1], mode='markers'))
            fig2.add_scatter(x=[min(qq_d[0][1]), max(qq_d[0][1])],
                            y=[min(qq_d[0][1]), max(qq_d[0][1])],
                            mode='lines', line_dash='dash')
            fig2.update_layout(title='Q-Q图', height=300)
            st.plotly_chart(fig2, use_container_width=True)
    
    # 标准化系数（Beta）
    st.markdown("#### 标准化回归系数 (Beta)")
    beta_df = calculate_standardized_coefficients(model, x_vars)
    st.dataframe(beta_df.round(4), use_container_width=True)


def polynomial_regression(df, numeric_cols):
    st.markdown("### 📐 多项式回归")
    
    st.info("""
    **多项式回归**用于拟合变量间的非线性（曲线）关系。
    
    **数据要求**：1个因变量(Y) + 1个自变量(X)，均为数值型。
    
    **模型**：Y = β₀ + β₁X + β₂X² + ... + βₙXⁿ。
    
    **阶数选择**：
    - 2阶（二次）：抛物线关系，如施肥量-产量的报酬递减
    - 3阶（三次）：S形曲线关系
    - 过高阶数（>4）容易过拟合，需谨慎
    
    **注意**：阶数越高模型越灵活，但也越容易过拟合。以调整R²和实际意义为参考。
    """)
    
    col1, col2, col3 = st.columns(3)
    with col1: y_var = st.selectbox("因变量", numeric_cols, key="poly_y")
    with col2: x_var = st.selectbox("自变量", [c for c in numeric_cols if c != y_var], key="poly_x")
    with col3: degree = st.slider("多项式阶数", min_value=2, max_value=6, value=2, key="poly_deg")
    
    clean_df = df[[y_var, x_var]].dropna()
    y = clean_df[y_var].values
    x = clean_df[x_var].values
    
    # 构建多项式特征
    poly_features = np.vstack([x**i for i in range(degree+1)]).T
    model = _get_sm().OLS(y, poly_features).fit()
    
    y_pred = model.predict(poly_features)
    
    # 结果
    r_sq = model.rsquared
    adj_rsq = model.rsquared_adj
    
    st.markdown(f"#### {degree}阶多项式拟合结果")
    m1, m2 = st.columns(2)
    with m1: st.metric("R²", f"{r_sq:.4f}")
    with m2: st.metric("调整R²", f"{adj_rsq:.4f}")
    
    # 方程
    coefs = model.params
    eq = f"{y_var} = "
    terms = []
    for i, c in enumerate(coefs):
        if abs(c) > 1e-6:
            if i == 0:
                terms.append(f"{c:.4f}")
            else:
                sign = "+" if c >= 0 else "-"
                power = f"^{i}" if i > 1 else ""
                terms.append(f"{sign} {abs(c):.4f}{x_var}{power}")
    st.code(eq + " ".join(terms), language=None)
    
    # 系数表
    coef_tab = pd.DataFrame({
        '项': ['常数项'] + [f"{x_var}^{i}" if i > 0 else "" for i in range(1, degree+1)],
        '系数': model.params,
        '标准误': model.bse,
        't值': model.tvalues,
        'p值': model.pvalues,
        '显著性': pd.Series(model.pvalues).apply(lambda p: "***" if p<0.001 else "**" if p<0.01 else "*" if p<0.05 else "")
    })
    st.dataframe(coef_tab.set_index('项').round(4))
    
    # 可视化
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=y, mode='markers', name='观测值',
                             marker_color='rgba(55,128,191,0.5)', opacity=0.7))
    
    x_smooth = np.linspace(min(x), max(x), 200)
    x_poly_smooth = np.vstack([x_smooth**i for i in range(degree+1)]).T
    y_smooth = model.predict(x_poly_smooth)
    
    fig.add_trace(go.Scatter(x=x_smooth, y=y_smooth, mode='lines',
                            name=f'{degree}阶拟合', line=dict(color='red', width=3)))
    
    fig.update_layout(title=f'{y_var} vs {x_var} - {degree}阶多项式回归 (R²={r_sq:.4f})',
                     xaxis_title=x_var, yaxis_title=y_var, height=500,
                     legend_title_text=None)
    st.plotly_chart(fig, use_container_width=True)



def logistic_regression(df, numeric_cols):
    """Logistic 二分类回归"""
    st.markdown("### 📊 Logistic回归（二分类）")
    
    st.info("""
    **Logistic回归**用于因变量为二分类时的建模和预测。
    
    **数据要求**：因变量为二分类（0/1、是/否、发病/不发病等） + ≥1个自变量。
    
    **模型**：log(p/(1-p)) = β₀ + β₁X₁ + ... + βₙXₙ（对数 odds 模型）。
    
    **关键指标**：
    - **伪R² (McFadden)**：模型拟合优度（低于线性回归的R²）
    - **OR (odds ratio)**：发生比，OR>1风险增加，OR<1风险降低
    - **AUC**：模型判别能力，0.5=随机，1=完美
    
    **输出**：系数表(含OR值)、混淆矩阵、灵敏度/特异度、ROC曲线。
    """)
    
    y_var = st.selectbox("因变量 (Y，二分类)", numeric_cols, key="logit_y")
    x_vars = st.multiselect(
        "选择自变量 (X)",
        [c for c in numeric_cols if c != y_var],
        key="logit_x"
    )
    
    if len(x_vars) < 1:
        st.warning("请至少选择一个自变量")
        return
    
    # 准备数据
    clean = df[[y_var] + x_vars].dropna()
    unique_y = sorted(clean[y_var].unique())
    
    # 检查因变量是否为二分类
    if len(unique_y) != 2:
        st.warning(f"因变量「{y_var}」有 {len(unique_y)} 个唯一值：{unique_y}，Logistic回归需要恰好 2 个类别")
        return
    
    # 将因变量映射为 0/1
    y_map = {unique_y[0]: 0, unique_y[1]: 1}
    y = clean[y_var].map(y_map).astype(float)
    X = _get_sm().add_constant(clean[x_vars])
    
    # 拟合模型
    try:
        model = _get_sm().Logit(y, X).fit(disp=0, maxiter=100)
    except Exception as e:
        st.error(f"模型拟合失败: {e}")
        return
    
    # 模型摘要
    st.markdown("#### 模型摘要")
    
    m1, m2, m3 = st.columns(3)
    with m1: st.metric("伪R² (McFadden)", f"{model.prsquared:.4f}")
    with m2: st.metric("对数似然", f"{model.llf:.2f}")
    with m3: st.metric("AIC", f"{model.aic:.2f}")
    
    st.markdown(f"*因变量映射: {unique_y[0]} → 0, {unique_y[1]} → 1*")
    
    # 系数表
    tab_coef, tab_pred = st.tabs(["系数表", "预测与评估"])
    
    with tab_coef:
        coef_df = pd.DataFrame({
            '系数': model.params,
            '标准误': model.bse,
            'z值': model.tvalues,
            'p值': model.pvalues,
            'OR (exp(β))': np.exp(model.params),
            'OR 95%CI下': np.exp(model.conf_int()[0]),
            'OR 95%CI上': np.exp(model.conf_int()[1]),
            '显著性': pd.Series(model.pvalues).apply(
                lambda p: "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else ""
            )
        })
        st.dataframe(coef_df.round(4), use_container_width=True)
        st.caption("OR > 1 表示正相关风险增加，OR < 1 表示负相关风险降低")
    
    with tab_pred:
        # 预测概率
        y_pred_prob = model.predict(X)
        y_pred = (y_pred_prob >= 0.5).astype(int)
        
        # 混淆矩阵
        from sklearn.metrics import confusion_matrix, classification_report, roc_auc_score
        cm = confusion_matrix(y, y_pred)
        
        st.markdown("**混淆矩阵**")
        cm_df = pd.DataFrame(
            cm,
            index=[f"实际{unique_y[0]}", f"实际{unique_y[1]}"],
            columns=[f"预测{unique_y[0]}", f"预测{unique_y[1]}"]
        )
        st.dataframe(cm_df, use_container_width=True)
        
        # 准确率等指标
        tn, fp, fn, tp = cm.ravel()
        acc = (tp + tn) / (tp + tn + fp + fn) if (tp + tn + fp + fn) > 0 else 0
        sens = tp / (tp + fn) if (tp + fn) > 0 else 0  # 灵敏度/召回率
        spec = tn / (tn + fp) if (tn + fp) > 0 else 0  # 特异度
        
        i1, i2, i3, i4 = st.columns(4)
        with i1: st.metric("准确率", f"{acc:.2%}")
        with i2: st.metric("灵敏度", f"{sens:.2%}")
        with i3: st.metric("特异度", f"{spec:.2%}")
        with i4:
            try:
                auc = roc_auc_score(y, y_pred_prob)
                st.metric("AUC", f"{auc:.4f}")
            except Exception:
                st.metric("AUC", "N/A")
        
        # ROC 曲线
        try:
            fpr, tpr, _ = stats.roc_curve(y, y_pred_prob)
            fig_roc = go.Figure()
            fig_roc.add_trace(go.Scatter(x=fpr, y=tpr, mode='lines', name='ROC曲线',
                                         line=dict(color='blue', width=2)))
            fig_roc.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode='lines',
                                         line_dash='dash', name='随机基线',
                                         line=dict(color='gray')))
            auc_val = roc_auc_score(y, y_pred_prob)
            fig_roc.update_layout(
                title=f"ROC曲线 (AUC = {auc_val:.4f})",
                xaxis_title="假阳性率 (1-特异度)",
                yaxis_title="灵敏度",
                height=400,
                xaxis=dict(scaleanchor="y", scaleratio=1)
            )
            st.plotly_chart(fig_roc, use_container_width=True)
        except Exception:
            pass


def stepwise_regression(df, numeric_cols):
    st.markdown("### 🔄 逐步回归")
    
    st.info("""
    **逐步回归**通过自动筛选过程，从多个候选变量中选出最优变量子集。
    
    **数据要求**：1个因变量(Y) + 多个候选自变量(X)。
    
    **三种筛选方向**：
    - **向前选择**：从无变量开始，逐步加入显著的变量
    - **向后消除**：从全部变量开始，逐步剔除不显著的变量
    - **双向逐步**（推荐）：每步既可加入也可剔除，综合前两种优点
    
    **参数说明**：
    - **进入阈值(α)**：变量被选入的标准，默认0.05
    - **剔除阈值(α)**：变量被移出的标准，默认0.10
    
    **输出**：入选变量列表、筛选过程历史、最终模型系数表。
    """)
    
    y_var = st.selectbox("因变量 (Y)", numeric_cols, key="step_y")
    candidates = st.multiselect(
        "候选自变量 (X)", 
        [c for c in numeric_cols if c != y_var],
        default=[c for c in numeric_cols if c != y_var]
    )
    
    method = st.radio("筛选方向", ["向前选择", "向后消除", "双向逐步"], horizontal=True)
    alpha_enter = st.number_input("进入阈值 (α)", value=0.05, min_value=0.001, max_value=0.5)
    alpha_exit = st.number_input("剔除阈值 (α)", value=0.10, min_value=0.001, max_value=0.5)
    
    if len(candidates) < 1:
        st.warning("请至少选择一个候选自变量")
        return
    
    if st.button("执行逐步回归"):
        selected, results_history, best_var, best_p = perform_stepwise(df, y_var, tuple(candidates), 
                                                     method, alpha_enter, alpha_exit)
        
        if selected:
            # 最终模型
            clean = df[[y_var] + selected].dropna()
            final_X = _get_sm().add_constant(clean[selected])
            final_y = clean[y_var]
            final_model = _get_sm().OLS(final_y, final_X).fit()
            
            st.markdown("#### 最终模型结果")
            
            m1, m2, m3 = st.columns(3)
            with m1: st.metric("入选变量数", str(len(selected)))
            with m2: st.metric("R²", f"{final_model.rsquared:.4f}")
            with m3: st.metric("AIC", f"{final_model.aic:.2f}")
            
            st.code(f"入选变量: {', '.join(selected)}", language=None)
            
            # 变量进入顺序历史
            if results_history:
                hist_df = pd.DataFrame(results_history)
                st.markdown("#### 变量筛选过程")
                st.dataframe(hist_df, use_container_width=True)
            
            # 系数表
            coef_df_final = _get_summary_table(final_model, table_idx=1)
            if isinstance(coef_df_final, pd.DataFrame):
                st.dataframe(coef_df_final, use_container_width=True)
            else:
                st.dataframe(coef_df_final, use_container_width=True)
        else:
            if best_var:
                st.warning(f"没有变量被选中（最佳候选：{best_var}，p={best_p:.4f} > α={alpha_enter}）。可尝试：\n- 降低进入阈值 α\n- 检查自变量与因变量的线性关系\n- 增加样本量")
            else:
                st.warning("无法完成逐步回归，请检查数据是否存在缺失值过多等问题")


# ========== 辅助函数 ==========

def display_anova_ml_table(table):
    """显示ML回归的ANOVA表"""
    disp = table.copy().round(4)
    disp['SS%'] = (disp['sum_sq'] / disp['sum_sq'].sum() * 100).round(1)
    disp.rename(columns={
        'sum_sq': '平方和', 'df': '自由度', 'F': 'F值', 'PR(>F)': 'p值'
    }, inplace=True)
    st.dataframe(disp, use_container_width=True)


def calculate_standardized_coefficients(model, x_vars):
    """计算标准化回归系数(Beta)"""
    coefs = model.params[1:]  # 排除截距
    sy = np.std(model.model.endog)
    sx = [np.std(model.model.exog[:, i+1]) for i in range(len(x_vars))]
    
    betas = [coefs[i] * sx[i] / sy for i in range(len(x_vars))]
    
    return pd.DataFrame({
        '变量': x_vars,
        '原始系数': coefs.values,
        '标准化系数(Beta)': betas,
        '绝对|Beta|排序': rankdata([-abs(b) for b in betas], method='ordinal')  # type: ignore
    }).sort_values('标准化系数(Beta)', key=lambda c: c.abs(), ascending=False)

from scipy.stats import rankdata


@st.cache_data
def perform_stepwise(df, y_var, candidates, method, alpha_enter, alpha_exit):
    """
    执行逐步回归算法（缓存：相同输入参数命中缓存）

    Args:
        candidates: 必须为 tuple，确保可 hash
        selected: 选中的变量列表
        history: 筛选过程记录
    """
    selected = []
    remaining = list(candidates)
    history = []
    best_overall_p = 1.0
    best_overall_var = None
    
    def fit_and_score(vars_list):
        if not vars_list:
            return None, float('inf'), None
        clean = df[[y_var] + list(vars_list)].dropna()
        if len(clean) <= len(vars_list) + 1:
            return None, float('inf'), None
        y = clean[y_var]
        X = _get_sm().add_constant(clean[vars_list])
        model = _get_sm().OLS(y, X).fit()
        return model, model.aic, model.pvalues[1:]
    
    max_iter = min(len(candidates), 20)
    
    for iteration in range(max_iter):
        changed = False
        
        if method in ["向前选择", "双向逐步"]:
            # 尝试加入新变量
            best_p_enter = 1.0
            best_var_enter = None
            
            for var in remaining:
                test_vars = selected + [var]
                model, _, pvals = fit_and_score(test_vars)
                if pvals is not None and var in pvals.index:
                    p_val = pvals[var]
                    if p_val < best_p_enter:
                        best_p_enter = p_val
                        best_var_enter = var
            
            if best_var_enter and best_p_enter < best_overall_p:
                best_overall_p = best_p_enter
                best_overall_var = best_var_enter
            
            if best_var_enter and best_p_enter < alpha_enter:
                selected.append(best_var_enter)
                remaining.remove(best_var_enter)
                history.append({
                    '步骤': iteration+1,
                    '操作': f"+ 加入 {best_var_enter}",
                    '当前变量': ", ".join(selected),
                    'p值': round(best_p_enter, 6),
                    'AIC': round(fit_and_score(selected)[1], 2) if selected else None
                })
                changed = True
        
        if method in ["向后消除", "双向逐步"] and len(selected) > 1:
            # 尝试移除变量
            model, _, pvals = fit_and_score(selected)
            worst_p = -1
            worst_var = None
            
            if pvals is not None:
                for var in selected:
                    p_val = pvals.get(var, 1.0)
                    if p_val > worst_p:
                        worst_p = p_val
                        worst_var = var
                
                if worst_var and worst_p > alpha_exit:
                    selected.remove(worst_var)
                    remaining.append(worst_var)
                    history.append({
                        '步骤': iteration+1,
                        '操作': f"- 移除 {worst_var}",
                        '当前变量': ", ".join(selected),
                        'p值': round(worst_p, 6),
                        'AIC': round(fit_and_score(selected)[1], 2) if selected else None
                    })
                    changed = True
        
        if not changed:
            break
    
    return selected, history, best_overall_var, best_overall_p


if __name__ == "__main__":
    render_regression()
