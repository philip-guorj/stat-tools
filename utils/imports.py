"""
StatTools - 统一的延迟导入模块

集中管理各页面所需的重量级库的延迟加载，
使用 st.cache_resource 确保跨页面共享同一实例。
"""

import streamlit as st

# ─── statsmodels ───────────────────────────────────────────────

@st.cache_resource
def get_statsmodels():
    """延迟导入 statsmodels，返回 (sm, ols, anova_lm, pairwise_tukeyhsd)"""
    import statsmodels.api as _sm
    from statsmodels.formula.api import ols as _ols
    from statsmodels.stats.anova import anova_lm as _anova_lm
    from statsmodels.stats.multicomp import pairwise_tukeyhsd as _tukey
    return _sm, _ols, _anova_lm, _tukey


@st.cache_resource
def get_sm():
    """仅获取 statsmodels.api"""
    import statsmodels.api as _sm
    return _sm


@st.cache_resource
def get_ols():
    """仅获取 ols"""
    return get_statsmodels()[1]


@st.cache_resource
def get_anova_lm():
    """仅获取 anova_lm"""
    return get_statsmodels()[2]


@st.cache_resource
def get_tukey():
    """仅获取 pairwise_tukeyhsd"""
    return get_statsmodels()[3]


# ─── scipy ─────────────────────────────────────────────────────

@st.cache_resource
def get_scipy_stats():
    """延迟导入 scipy.stats"""
    from scipy import stats as _stats
    return _stats


# ─── plotly ────────────────────────────────────────────────────

@st.cache_resource
def get_plotly_express():
    """延迟导入 plotly.express"""
    import plotly.express as _px
    return _px


@st.cache_resource
def get_plotly_go():
    """延迟导入 plotly.graph_objects"""
    import plotly.graph_objects as _go
    return _go


@st.cache_resource
def get_plotly_subplots():
    """延迟导入 plotly.subplots"""
    from plotly.subplots import make_subplots as _ms
    return _ms


# ─── sklearn / stats 子模块 ───────────────────────────────────

@st.cache_resource
def get_vif():
    """延迟导入 variance_inflation_factor"""
    from statsmodels.stats.outliers_influence import variance_inflation_factor as _vif
    return _vif
