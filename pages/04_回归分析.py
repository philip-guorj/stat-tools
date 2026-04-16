# 回归分析模块

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
import numpy as np
from scipy import stats
from scipy.optimize import curve_fit
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import warnings
warnings.filterwarnings('ignore')

from utils.data_manager import get_data_manager
from utils.styles import get_global_css

# 全局缓存延迟导入的模块
_sm_cache = None
_vif_cache = None

def _get_sm():
    """延迟导入statsmodels.api（单例）"""
    global _sm_cache
    if _sm_cache is None:
        import statsmodels.api as sm
        _sm_cache = sm
    return _sm_cache

def _get_vif():
    """延迟导入VIF计算（单例）"""
    global _vif_cache
    if _vif_cache is None:
        from statsmodels.stats.outliers_influence import variance_inflation_factor
        _vif_cache = variance_inflation_factor
    return _vif_cache


def render_regression():
    st.markdown(get_global_css(), unsafe_allow_html=True)
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
    
    dm = get_data_manager()
    
    if not dm.is_loaded:
        st.warning("⚠️ 请先上传数据文件")
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
            "逐步回归 (Stepwise)",
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
    
    elif reg_type == "逐步回归 (Stepwise)":
        stepwise_regression(df, numeric_cols)


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
                            showlegend=False, name='95% CI'))
    
    eq_str = f'Y = {slope:.3f}X + {intercept:.3f}, R²={r_squared:.4f}'
    fig.update_layout(title=f'{y_var} vs {x_var}<br><sup>{eq_str}</sup>',
                     xaxis_title=x_var, yaxis_title=y_var, height=500)
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
        
        st.caption("*VIF > 10 表示存在多重共线性")
    
    with tab_ano:
        anova_table = _get_sm().stats.anova_lm(model, typ=2)
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
        '显著性': model.pvalues.apply(lambda p: "***" if p<0.001 else "**" if p<0.01 else "*" if p<0.05 else "")
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
                     xaxis_title=x_var, yaxis_title=y_var, height=500)
    st.plotly_chart(fig, use_container_width=True)


def stepwise_regression(df, numeric_cols):
    st.markdown("### 🔄 逐步回归 (Stepwise Selection)")
    
    y_var = st.selectbox("因变量 (Y)", numeric_cols, key="step_y")
    candidates = [c for c in numeric_cols if c != y_var]
    
    method = st.radio("筛选方向", ["向前选择 (Forward)", "向后消除 (Backward)", "双向逐步"], horizontal=True)
    alpha_enter = st.number_input("进入阈值 (α_entry)", value=0.05, min_value=0.001, max_value=0.5)
    alpha_exit = st.number_input("剔除阈值 (α_exit)", value=0.10, min_value=0.001, max_value=0.5)
    
    if st.button("执行逐步回归"):
        selected, results_history = perform_stepwise(df, y_var, candidates, 
                                                     method, alpha_enter, alpha_exit)
        
        if selected:
            # 最终模型
            final_X = _get_sm().add_constant(df[selected].dropna())
            final_y = df[y_var].loc[final_X.index]
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
            st.warning("没有变量被选中")


# ========== 辅助函数 ==========

def display_anova_ml_table(table):
    """显示ML回归的ANOVA表"""
    disp = table.copy().round(4)
    disp['SS%'] = (disp['sum_sq'] / disp['sum_sq'].sum() * 100).round(1)
    disp.rename(columns={
        'sum_sq': 'SS', 'df': 'df', 'F': 'F值', 'PR(>F)': 'p'
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
    }).sort_values('|Beta|', ascending=False)

from scipy.stats import rankdata


def perform_stepwise(df, y_var, candidates, method, alpha_enter, alpha_exit):
    """
    执行逐步回归算法
    
    Returns:
        selected: 选中的变量列表
        history: 筛选过程记录
    """
    selected = []
    remaining = list(candidates)
    history = []
    
    def fit_and_score(vars_list):
        if not vars_list:
            return None, float('inf'), None
        X = _get_sm().add_constant(df[vars_list].dropna())
        y = df[y_var].loc[X.index]
        model = _get_sm().OLS(y, X).fit()
        return model, model.aic, model.pvars[1:]  # type: ignore
    
    max_iter = min(len(candidates), 20)
    
    for iteration in range(max_iter):
        changed = False
        
        if method in ["向前选择 (Forward)", "双向逐步"]:
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
        
        if method in ["向后消除 (Backward)", "双向逐步"] and len(selected) > 1:
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
    
    return selected, history


if __name__ == "__main__":
    render_regression()


# ========== 兼容性辅助函数 ==========

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
                    'coef': model.params.values,
                    'std err': model.bse.values,
                    't': model.tvalues.values,
                    'P>|t|': model.pvalues.values,
                    '[0.025': model.conf_int()[0].values,
                    '0.975]': model.conf_int()[1].values
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
                    'coef': model.params.values,
                    'std err': getattr(model, 'bse', [np.nan]*len(model.params)).values if hasattr(model.bse, '__iter__') else model.bse,
                    't': model.tvalues.values if hasattr(model, 'tvalues') else [np.nan]*len(model.params),
                    'P>|t|': model.pvalues.values,
                })
                return coef_df.set_index('')
            raise