# 描述统计模块

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from scipy import stats
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.data_manager import get_data_manager
from utils.styles import get_global_css

def render_descriptive_stats():
    st.markdown(get_global_css(), unsafe_allow_html=True)
    st.markdown('<div class="section-header">📈 描述统计分析</div>', unsafe_allow_html=True)
    
    # 功能简介下拉菜单
    with st.expander("📖 功能简介", expanded=False):
        st.markdown("""
        **描述统计**用于总结和描述数据的基本特征，帮助您快速了解数据的分布情况。
        
        | 功能 | 说明 | 适用场景 |
        |------|------|---------|
        | 基础统计量 | 均值、中位数、标准差、变异系数等 | 了解数据集中趋势和离散程度 |
        | 分组统计 | 按分类变量分组计算统计量 | 比较不同组间的差异 |
        | 分布可视化 | 直方图、箱线图、Q-Q图 | 直观查看数据分布形态 |
        | 峰度偏度 | 判断数据是否正态分布 | 为后续检验选择提供依据 |
        
        **使用建议**：分析前先做描述统计，了解数据基本情况。CV%（变异系数）是田间试验最常用的指标之一。
        """)
    
    dm = get_data_manager()
    
    if not dm.is_loaded:
        st.warning("⚠️ 请先上传数据文件")
        return
    
    df = dm.data
    numeric_cols = dm.get_numeric_columns()
    
    if not numeric_cols:
        st.warning("⚠️ 数据中没有数值型列")
        return
    
    # 列选择
    st.markdown("### 参数设置")
    selected_cols = st.multiselect(
        "选择分析变量",
        numeric_cols,
        default=numeric_cols[:3] if len(numeric_cols) >= 3 else numeric_cols
    )
    
    group_col = st.selectbox(
        "选择分组变量（可选）",
        options=["无"] + dm.get_categorical_columns()
    )
    
    if not selected_cols:
        return
    
    # 基础描述统计量
    st.markdown("---")
    st.markdown("### 📊 描述统计量")
    
    desc_df = df[selected_cols].describe().T
    # 添加额外统计量
    extra_stats = []
    for col in selected_cols:
        data = df[col].dropna()
        extra_stats.append({
            '变量': col,
            '偏度': stats.skew(data),
            '峰度': stats.kurtosis(data),
            '变异系数(CV%)': (data.std() / data.mean() * 100) if data.mean() != 0 else np.nan,
            '中位数': data.median(),
            '众数': mode(data),  # type: ignore
            '极差': data.max() - data.min(),
            '四分位距(IQR)': data.quantile(0.75) - data.quantile(0.25),
            '标准误(SE)': stats.sem(data),
            '置信区间(95%下限)': data.mean() - 1.96 * stats.sem(data),
            '置信区间(95%上限)': data.mean() + 1.96 * stats.sem(data),
        })
    
    extra_df = pd.DataFrame(extra_stats).set_index('变量')
    
    tab1, tab2, tab3 = st.tabs(["基础统计", "完整统计量", "详细报告"])
    
    with tab1:
        st.dataframe(desc_df.style.background_gradient(cmap='Blues'), use_container_width=True)
    
    with tab2:
        st.dataframe(extra_df.round(4).style.background_gradient(cmap='Greens'), use_container_width=True)
    
    with tab3:
        for col in selected_cols:
            data = df[col].dropna()
            st.markdown(f"#### {col}")
            
            m1, m2, m3, m4 = st.columns(4)
            with m1: st.metric("均值", f"{data.mean():.4f}")
            with m2: st.metric("标准差", f"{data.std():.4f}")
            with m3: st.metric("中位数", f"{data.median():.4f}")
            with m4: st.metric("CV%", f"{(data.std()/data.mean()*100):.2f}%")
    
    # 分组统计
    if group_col != "无":
        st.markdown("---")
        st.markdown(f"### 📊 按 **{group_col}** 分组统计")
        
        grouped = df.groupby(group_col)[selected_cols].agg(['count', 'mean', 'std', 'min', 'max'])
        st.dataframe(grouped.round(4), use_container_width=True)
        
        # 分组箱线图
        st.markdown("#### 分组箱线图")
        fig_box = px.box(
            df.melt(id_vars=[group_col], value_vars=selected_cols, 
                    var_name='变量', value_name='值'),
            x=group_col, y='值', color='变量',
            title=f'按{group_col}分组的箱线图'
        )
        st.plotly_chart(fig_box, use_container_width=True)
    
    # 可视化
    st.markdown("---")
    st.markdown("### 📈 可视化分析")
    
    viz_cols = st.columns(len(selected_cols))
    for i, col in enumerate(selected_cols):
        with viz_cols[i]:
            chart_type = st.selectbox(
                f"{col} 图表类型",
                ["直方图", "箱线图", "小提琴图", "QQ图"],
                key=f"viz_{col}"
            )
    
    for col in selected_cols:
        data = df[col].dropna()
        chart_type = st.session_state.get(f"viz_{col}", "直方图")  # type: ignore
        
        st.markdown(f"#### {col}")
        
        c_hist, c_qq = st.columns(2)
        
        with c_hist:
            if chart_type in ["直方图", "小提琴图"]:
                fig = px.histogram(df, x=col, nbins=30, marginal="box",
                                   title=f'{col} 分布直方图')
                fig.update_layout(height=400)
                st.plotly_chart(fig, use_container_width=True)
            elif chart_type == "箱线图":
                fig = px.box(df, y=col, title=f'{col} 箱线图',
                            points="outliers")
                fig.update_layout(height=400)
                st.plotly_chart(fig, use_container_width=True)
        
        with c_qq:
            # QQ图（正态性检验可视化）
            qq_data = stats.probplot(data, dist="norm")
            fig_qq = go.Figure()
            fig_qq.add_trace(go.Scatter(
                x=qq_data[0][1], y=qq_data[1],
                mode='markers', name='样本数据'
            ))
            fig_qq.add_trace(go.Scatter(
                x=[min(qq_data[0][1]), max(qq_data[0][1])],
                y=[min(qq_data[1]), max(qq_data[1])],
                mode='lines', name='参考线', line=dict(dash='dash')
            ))
            fig_qq.update_layout(title=f'{col} QQ图 (正态性检验)',
                                height=400, xaxis_title='理论分位数',
                                yaxis_title='样本分位数')
            st.plotly_chart(fig_qq, use_container_width=True)
    
    # 相关性矩阵
    if len(selected_cols) > 1:
        st.markdown("---")
        st.markdown("### 🔗 变量相关性分析")
        
        corr_matrix = df[selected_cols].corr()
        
        fig_corr = px.imshow(
            corr_matrix,
            text_auto='.2f',
            aspect='auto',
            color_continuous_scale='RdBu_r',
            title='相关系数热力图'
        )
        fig_corr.update_layout(height=500)
        st.plotly_chart(fig_corr, use_container_width=True)


def mode(arr):
    """计算众数"""
    try:
        from scipy import stats
        result = stats.mode(arr, keepdims=True)
        return result.mode[0]
    except:
        return arr.mode()[0]


if __name__ == "__main__":
    import os
    render_descriptive_stats()