# 数据可视化模块 - 交互式图表生成

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from utils.data_manager import get_data_manager
from utils.styles import get_global_css


def render_visualization():
    st.markdown(get_global_css(), unsafe_allow_html=True)
    st.markdown('<div class="section-header">📊 数据可视化</div>', unsafe_allow_html=True)
    
    # 功能简介下拉菜单
    with st.expander("📖 功能简介", expanded=False):
        st.markdown("""
        **数据可视化**帮助您直观理解数据分布、趋势和关系，是数据分析的重要环节。
        
        | 图表类型 | 用途 | 适用数据 |
        |---------|------|---------|
        | 折线图 | 展示趋势变化 | 时间序列、连续变量 |
        | 柱状图 | 比较各类别数值 | 分类变量+数值变量 |
        | 箱线图 | 显示分布和异常值 | 数值变量（可分组） |
        | 直方图 | 展示数据分布形态 | 单个数值变量 |
        | 散点图 | 展示两个变量关系 | 两个数值变量 |
        | 热力图 | 显示矩阵数据强度 | 相关矩阵、交叉表 |
        | 饼图/环形图 | 展示构成比例 | 分类变量 |
        | 小提琴图 | 展示分布密度 | 数值变量（可分组） |
        | 散点矩阵 | 多变量关系概览 | 多个数值变量 |
        | 面积图 | 展示累积趋势 | 时间序列、多组数据 |
        
        **使用建议**：根据数据类型和分析目的选择合适的图表，多种图表结合使用效果更佳。
        """)
        
        st.markdown("""
        <div class="method-guide">
        <div class="method-guide-title">图表选择速查</div>
        <div class="method-guide-content">
        <b>想看趋势</b> → 折线图、面积图<br>
        <b>想比较大小</b> → 柱状图（分类少）、饼图（类别5个以内）<br>
        <b>想看分布</b> → 直方图、箱线图、小提琴图<br>
        <b>想看关系</b> → 散点图（2个变量）、散点矩阵（多个变量）、热力图（相关系数）<br>
        <b>论文配图推荐</b> → 箱线图+散点叠加、热力图
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
    
    chart_type = st.selectbox(
        "选择图表类型",
        [
            "---",
            "📈 折线图 (Line Chart)",
            "📊 柱状图 (Bar Chart)",
            "📦 箱线图 (Box Plot)",
            "📉 直方图/分布 (Histogram)",
            "🔵 散点图 (Scatter Plot)",
            "🌡️ 热力图 (Heatmap)",
            "🥧 饼图 (Pie Chart)",
            "🎻 小提琴图 (Violin Plot)",
            "🔗 散点矩阵 (Scatter Matrix)",
            "📐 面积图/堆叠面积图"
        ]
    )
    
    st.markdown("---")
    
    if chart_type == "---":
        st.info("👆 请从上方下拉菜单选择图表类型，或查看功能简介了解各图表用途")
        show_viz_gallery(df, numeric_cols, categorical_cols)
        return
    
    elif "折线图" in chart_type:
        line_chart(df, numeric_cols, categorical_cols)
    
    elif "柱状图" in chart_type:
        bar_chart(df, numeric_cols, categorical_cols)
    
    elif "箱线图" in chart_type:
        box_plot(df, numeric_cols, categorical_cols)
    
    elif "直方图" in chart_type:
        histogram(df, numeric_cols, categorical_cols)
    
    elif "散点图" in chart_type and "矩阵" not in chart_type:
        scatter_plot(df, numeric_cols, categorical_cols)
    
    elif "热力图" in chart_type:
        heatmap(df, numeric_cols, categorical_cols)
    
    elif "饼图" in chart_type:
        pie_chart(df, categorical_cols, numeric_cols)
    
    elif "小提琴图" in chart_type:
        violin_plot(df, numeric_cols, categorical_cols)
    
    elif "散点矩阵" in chart_type:
        scatter_matrix(df, numeric_cols)
    
    elif "面积图" in chart_type:
        area_chart(df, numeric_cols, categorical_cols)


def show_viz_gallery(df, num_cols, cat_cols):
    """显示可视化画廊预览"""
    st.markdown("### 🎨 可视化选项概览")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**连续变量**")
        st.write(f"- {len(num_cols)} 个数值列可用")
        if num_cols: st.write(f"  包括：{', '.join(num_cols[:5])}")
    
    with col2:
        st.markdown("**分类变量**")
        st.write(f"- {len(cat_cols)} 个分类列可用")
        if cat_cols: st.write(f"  包括：{', '.join(cat_cols[:5])}")
    
    with col3:
        st.markdown("**数据规模**")
        st.write(f"- {len(df)} 行 × {len(df.columns)} 列")
        missing = df.isnull().sum().sum()
        st.write(f"- 缺失值: {missing} 个")
    
    # 快速预览图（如果数据量不大）
    if len(num_cols) >= 2 and len(df) <= 5000:
        st.markdown("### 🖼️ 数据预览")
        
        fig_preview = px.scatter_matrix(
            df[num_cols[:4]].dropna(),
            dimensions=num_cols[:4],
            opacity=0.6,
            title='数值变量关系预览'
        )
        fig_preview.update_layout(height=500)
        st.plotly_chart(fig_preview, use_container_width=True)


# ========== 图表实现 ==========

def line_chart(df, num_cols, cat_cols):
    """折线图"""
    y_col = st.selectbox("Y轴 (数值)", num_cols, key="line_y")
    x_col = st.selectbox("X轴", ["索引"] + num_cols + cat_cols, key="line_x")
    color_col = st.selectbox("分组/颜色", ["无"] + cat_cols + num_cols, key="line_color")
    
    fig_args = dict(y=y_col, title=f'{y_col} 变化趋势')
    
    if x_col != "索引":
        fig_args['x'] = x_col
    
    if color_col != "无":
        fig_args['color'] = color_col
    
    fig = px.line(df.dropna(subset=[y_col]), **fig_args)
    
    # 添加标记点
    if st.checkbox("显示数据点"):
        fig.update_traces(mode='lines+markers', marker_size=4)
    
    update_fig_layout(fig, f'折线图 - {y_col}')
    st.plotly_chart(fig, use_container_width=True)


def bar_chart(df, num_cols, cat_cols):
    """柱状图"""
    chart_mode = st.radio("柱状图模式", 
                           ["分类统计", "单变量计数", "聚合比较"], horizontal=True,
                           key="bar_mode")
    
    if chart_mode == "分类统计":
        y_col = st.selectbox("Y轴 (数值)", num_cols, key="bar_y")
        x_col = st.selectbox("X轴 (分类)", cat_cols, key="bar_x")
        color_col = st.selectbox("颜色分组", ["无"] + cat_cols, key="bar_color")
        
        agg_func = st.selectbox("聚合函数", ['mean', 'sum', 'count', 'median', 'max', 'min'])
        
        fig = px.bar(df, x=x_col, y=y_col,
                     color=(color_col if color_col!="无" else None),
                     barmode=st.selectbox('柱状图模式', ['stack', 'group', 'overlay']))
        
    elif chart_mode == "单变量计数":
        count_col = st.selectbox("计数变量", cat_cols + num_cols, key="bar_count")
        fig = px.bar(df[count_col].value_counts().reset_index(), 
                    x='index', y=count_col, title=f'{count_col} 分布')
    
    else:  # 聚类比较
        y_col = st.selectbox("Y轴", num_cols, key="bar_agg_y")
        group_col = st.selectbox("分组变量", cat_cols, key="bar_agg_group")
        
        grouped = df.groupby(group_col)[y_col].agg(['mean', 'std']).reset_index()
        fig = go.Figure([
            go.Bar(name='均值', x=grouped[group_col], y=grouped['mean'],
                  error_y=dict(type='data', array=grouped['std'])),
        ])
    
    orientation = st.radio("方向", ["垂直", "水平"], horizontal=True, key="bar_orient")
    if orientation == "水平":
        # 转换为水平
        pass
    
    update_fig_layout(fig, '柱状图', height=450)
    st.plotly_chart(fig, use_container_width=True)


def box_plot(df, num_cols, cat_cols):
    """箱线图"""
    y_col = st.selectbox("Y轴 (数值)", num_cols, key="box_y")
    x_col = st.selectbox("X轴 (分组)", ["无"] + cat_cols, key="box_x")
    color_col = st.selectbox("颜色细分", ["无"] + cat_cols + num_cols, key="box_color")
    
    plot_df = df.dropna(subset=[y_col])
    
    show_points = st.checkbox("显示异常点", value=True)
    show_notched = st.checkbox("显示中位 notch")
    try:
        fig = px.box(plot_df, y=y_col,
                    x=x_col if x_col != "无" else None,
                    color=color_col if color_col != "无" else None,
                    boxpoints='outliers' if show_points else False,
                    notched=show_notched)
    except TypeError:
        fig = px.box(plot_df, y=y_col,
                    x=x_col if x_col != "无" else None,
                    color=color_col if color_col != "无" else None,
                    notched=show_notched)
        if show_points:
            fig.update_traces(boxpoints='all', jitter=0.3)

    update_fig_layout(fig, f'箱线图 - {y_col}')
    st.plotly_chart(fig, use_container_width=True)


def histogram(df, num_cols, cat_cols):
    """直方图与分布图"""
    var_col = st.selectbox("变量", num_cols, key="hist_var")
    bins = st.slider("组数", min_value=10, max_value=100, value=30, key="hist_bins")
    
    tab_hist, tab_dist, tab_cum = st.tabs(["频率直方图", "密度曲线", "累积分布"])
    
    with tab_hist:
        fig = px.histogram(df, x=var_col, nbins=bins, 
                          marginal="box" if st.checkbox("边距图") else None,
                          title=f'{var_col} 分布')
        update_fig_layout(fig, f'{var_col} 分布', height=400)
        st.plotly_chart(fig, use_container_width=True)
    
    with tab_dist:
        # KDE核密度估计
        from scipy import stats as scipy_stats
        
        data = df[var_col].dropna()
        kde_x = np.linspace(data.min(), data.max(), 200)
        kde = scipy_stats.gaussian_kde(data)(kde_x)
        
        fig_kde = go.Figure()
        fig_kde.add_trace(go.Scatter(x=kde_x, y=kde, fill='tozeroy',
                                     name='KDE密度', line_color='#3498db'))
        fig_kde.add_histogram(x=data, histnorm='probability density',
                       name='归一化直方图',
                       marker_color='rgba(55,128,191,0.3)')
        fig_kde.update_layout(title=f'{var_col} 密度分布', height=400)
        st.plotly_chart(fig_kde, use_container_width=True)
    
    with tab_cum:
        sorted_data = np.sort(data)
        cdf = np.arange(1, len(sorted_data)+1) / len(sorted_data)
        
        fig_cdf = go.Figure()
        fig_cdf.add_scatter(x=sorted_data, y=cdf, mode='lines', name='CDF')
        fig_cdf.update_layout(
            title=f'{var_col} 累积分布函数',
            height=350,
            xaxis=dict(title=var_col),
            yaxis=dict(title='累积概率')
        )
        st.plotly_chart(fig_cdf, use_container_width=True)


def scatter_plot(df, num_cols, cat_cols):
    """散点图"""
    y_col = st.selectbox("Y轴", num_cols, key="scat_y")
    x_col = st.selectbox("X轴", [c for c in num_cols if c != y_col], key="scat_x")
    size_col = st.selectbox("大小变量", ["无"] + num_cols, key="scat_size")
    color_col = st.selectbox("颜色变量", ["无"] + cat_cols + num_cols, key="scat_color")
    
    # 回归趋势线
    trend_opt = st.selectbox("趋势线", ["无", "线性(OLS)", "LOWESS"], key="scat_trend")
    
    fig = px.scatter(df, x=x_col, y=y_col,
                     size=size_col if size_col!="无" else None,
                     color=color_col if color_col!="无" else None,
                     hover_data=df.columns.tolist()[:5])
    
    if trend_opt == "线性(OLS)":
        clean = df[[x_col, y_col]].dropna()
        slope, intercept, r, p, se = scipy_stats.linregress(clean[x_col], clean[y_col])  # type: ignore
        fig.add_trace(go.Scatter(x=clean[x_col], y=slope*clean[x_col]+intercept,
                                mode='lines', name=f'趋势线 R²={r**2:.3f}',
                                line=dict(color='red', dash='dash')))
    elif trend_opt == "LOWESS":
        try:
            import statsmodels.nonparametric.smoothers_lowess as lowess
            clean = df[[x_col, y_col]].dropna()
            smoothed = lowess.lowess(clean[y_col], clean[x_col], frac=0.3)
            fig.add_trace(go.Scatter(x=smoothed[:, 0], y=smoothed[:, 1],
                                    mode='lines', name='LOWESS',
                                    line=dict(color='red', width=2)))
        except:
            pass
    
    update_fig_layout(fig, f'{y_col} vs {x_col}', height=500)
    st.plotly_chart(fig, use_container_width=True)
    
    # 相关系数
    corr = df[x_col].corr(df[y_col])
    st.metric("Pearson相关系数", f"{corr:.4f}")


def heatmap(df, num_cols, cat_cols):
    """热力图"""
    heat_type = st.radio("热力图类型",
                         ["相关系数矩阵", "交叉频数表", "透视表聚合"],
                         horizontal=True, key="heat_type")
    
    if heat_type == "相关系数矩阵":
        selected = st.multiselect("选择变量", num_cols, default=num_cols[:min(8, len(num_cols))])
        method = st.selectbox("相关方法", ["pearson", "spearman", "kendall"])
        
        corr_mat = df[selected].corr(method=method)
        
        fig = px.imshow(corr_mat, text_auto='.2f', aspect='auto',
                        color_continuous_scale='RdBu_r',
                        color_continuous_midpoint=0, title='相关系数热力图')
        
    elif heat_type == "交叉频数表":
        row_var = st.selectbox("行变量", cat_cols, key="heat_row")
        col_var = st.selectbox("列变量", [c for c in cat_cols if c != row_var], key="heat_col")
        
        cross_tab = pd.crosstab(df[row_var], df[col_var])
        fig = px.imshow(cross_tab, text_auto=True, aspect='auto',
                        color_continuous_scale='Blues',
                        title=f'{row_var} × {col_var} 交叉频数')
    
    else:  # 透视表
        val_col = st.selectbox("值变量", num_cols, key="heat_val")
        idx_col = st.selectbox("行变量", cat_cols, key="heat_idx")
        col_var = st.selectbox("列变量", [c for c in cat_cols if c != idx_col], key="heat_col2")
        agg_func = st.selectbox("聚合", ['mean', 'sum', 'count'], key="heat_agg")
        
        pivot = df.pivot_table(values=val_col, index=idx_col, columns=col_var, aggfunc=agg_func)
        fig = px.imshow(pivot.fillna(0), text_auto='.1f', aspect='auto',
                        color_continuous_scale='Viridis',
                        title=f'{val_col} 透视表 ({agg_func})')
    
    fig.update_layout(height=500)
    st.plotly_chart(fig, use_container_width=True)


def pie_chart(df, cat_cols, num_cols):
    """饼图/环形图"""
    category_col = st.selectbox("分类变量", cat_cols + num_cols, key="pie_cat")
    values_col = st.selectbox("数值变量 (用于求和)", 
                              ["计数"] + num_cols, key="pie_val")
    
    if values_col == "计数":
        pie_data = df[category_col].value_counts()
        labels = pie_data.index
        values = pie_data.values
    else:
        pie_data = df.groupby(category_col)[values_col].sum()
        labels = pie_data.index
        values = pie_data.values
    
    is_donut = st.checkbox("环形图样式")
    
    fig = go.Figure(data=[go.Pie(labels=labels, values=values,
                                 hole=0.4 if is_donut else 0,
                                 textinfo='label+percent',
                                 textposition='outside')])
    
    fig.update_layout(title=f'{category_col} 分布{" ("+values_col+")" if values_col!="计数" else ""}',
                     height=500)
    st.plotly_chart(fig, use_container_width=True)


def violin_plot(df, num_cols, cat_cols):
    """小提琴图"""
    y_col = st.selectbox("Y轴 (数值)", num_cols, key="vio_y")
    x_col = st.selectbox("X轴 (分组)", ["无"] + cat_cols, key="vio_x")
    color_col = st.selectbox("颜色", ["无"] + cat_cols, key="vio_color")
    
    fig = px.violin(df, y=y_col, 
                    x=x_col if x_col!="无" else None,
                    color=color_col if color_col!="无" else None,
                    box=True,  # 显示内部箱线图
                    points=st.selectbox("数据点", ["outliers", "all", False]),  # type: ignore
                    title=f'{y_col} 小提琴图')
    
    update_fig_layout(fig, f'小提琴图 - {y_col}', height=450)
    st.plotly_chart(fig, use_container_width=True)


def scatter_matrix(df, num_cols):
    """散点矩阵图"""
    selected = st.multiselect("选择变量 (建议2-6个)", 
                             num_cols, default=num_cols[:min(4, len(num_cols))])
    
    if len(selected) < 2:
        return
    
    color_by = st.selectbox("着色变量", ["无"] + df.columns.tolist(), key="sm_color")
    
    max_samples = st.number_input("最大样本数 (大数据集时降采样)", 
                                  min_value=50, max_value=10000, value=2000)
    
    plot_df = df[selected + ([color_by] if color_by!="无" else [])].dropna()
    if len(plot_df) > max_samples:
        plot_df = plot_df.sample(max_samples, random_state=42)
    
    fig = px.scatter_matrix(plot_df, dimensions=selected,
                            color=color_by if color_by!="无" else None,
                            opacity=0.7,
                            title='散点矩阵')
    fig.update_layout(height=600)
    st.plotly_chart(fig, use_container_width=True)


def area_chart(df, num_cols, cat_cols):
    """面积图"""
    y_cols = st.multiselect("Y轴变量 (可多选)", num_cols, default=num_cols[:3], key="area_y")
    x_col = st.selectbox("X轴", ["索引"] + num_cols + cat_cols, key="area_x")
    
    stacked = st.checkbox("堆叠模式")
    
    plot_df = df[y_cols + ([x_col] if x_col != "索引" else [])].copy()
    if x_col == "索引":
        plot_df = plot_df.reset_index(drop=True).reset_index()
        x_col = 'index'
    
    fig = px.area(plot_df, x=x_col, y=y_cols,
                 title='堆叠面积图' if stacked else '面积图',
                 facet_col=None)
    
    update_fig_layout(fig, '面积图', height=450)
    st.plotly_chart(fig, use_container_width=True)


# ========== 辅助函数 ==========
from scipy import stats as scipy_stats


def update_fig_layout(fig, title, height=450):
    """统一更新图表布局"""
    fig.update_layout(
        title=title,
        height=height,
        template='plotly_white',
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )


def selectbar(default, *options):
    """简化选择器"""
    return default  # placeholder for st.selectbar compatibility


if __name__ == "__main__":
    import os
    render_visualization()