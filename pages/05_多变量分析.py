# 多变量分析模块 - PCA、聚类、相关分析

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

from utils.data_manager import get_current_dm
from utils.styles import inject_css
from utils.visitor_logger import log_visit
from billing.billing import require_auth, can_download


# ========== 延迟导入重量级计算库 ==========
_sklearn_cache = {}
_scipy_hier_cache = None

def _get_pca():
    if 'pca' not in _sklearn_cache:
        from sklearn.decomposition import PCA
        from sklearn.preprocessing import StandardScaler
        _sklearn_cache['pca'] = PCA
        _sklearn_cache['scaler'] = StandardScaler
    return _sklearn_cache['pca'], _sklearn_cache['scaler']

def _get_kmeans():
    if 'kmeans' not in _sklearn_cache:
        from sklearn.cluster import KMeans
        from sklearn.metrics import silhouette_score, calinski_harabasz_score, davies_bouldin_score
        _sklearn_cache['kmeans'] = KMeans
        _sklearn_cache['silhouette'] = silhouette_score
        _sklearn_cache['calinski'] = calinski_harabasz_score
        _sklearn_cache['davies'] = davies_bouldin_score
    return (_sklearn_cache['kmeans'], _sklearn_cache['silhouette'],
            _sklearn_cache['calinski'], _sklearn_cache['davies'])

def _get_hierarchy():
    global _scipy_hier_cache
    if _scipy_hier_cache is None:
        from scipy.cluster.hierarchy import dendrogram, linkage
        _scipy_hier_cache = (dendrogram, linkage)
    return _scipy_hier_cache

def _get_stats():
    from scipy import stats
    return stats

def _get_px():
    import plotly.express as px
    return px

def _get_go():
    import plotly.graph_objects as go
    return go

def _get_subplots():
    from plotly.subplots import make_subplots
    return make_subplots




def render_multivariate():
    require_auth()
    log_visit("多变量分析")
    inject_css()
    st.markdown('<div class="section-header">🎯 多变量分析</div>', unsafe_allow_html=True)

    
    # 功能简介下拉菜单
    with st.expander("📖 功能简介", expanded=False):
        st.markdown("""
        **多变量分析**用于同时处理多个变量，发现数据中的潜在结构和模式。
        
        | 分析方法 | 用途 | 适用场景 |
        |---------|------|---------|
        | 主成分分析 (PCA) | 降维、提取主要信息 | 变量多且存在相关性 |
        | K-Means聚类 | 将样本分成K个群组 | 客户分群、品种分类 |
        | 层次聚类 | 构建层次化的分类树 | 探索性分类分析 |
        | 相关性矩阵 | 查看变量间相关程度 | 变量关系探索 |
        | 因子分析 | 寻找潜在公共因子 | 问卷分析、性状提取 |
        
        **使用建议**：多变量分析前建议先标准化数据，消除量纲影响。
        """)
        
        st.markdown("""
        <div class="method-guide">
        <div class="method-guide-title">分析方法选择指南</div>
        <div class="method-guide-content">
        <b>1. 想降维/综合评价</b> → <b>主成分分析(PCA)</b>：将多个指标综合为少数几个主成分<br>
        <b>2. 想分类/分组</b> → <b>K-Means聚类</b>：已知要分几类；<b>层次聚类</b>：不确定分几类<br>
        <b>3. 想看变量关系</b> → <b>相关性矩阵</b>：一目了然查看变量间相关程度<br>
        <b>4. 有很多性状指标</b> → <b>因子分析</b>：提取潜在公共因子，减少变量数量
        </div>
        </div>
        """, unsafe_allow_html=True)
    
    dm = get_current_dm()
    
    if not dm.is_loaded:
        st.warning("⚠️ 请从首页上传数据")
        return
    
    df = dm.data
    
    analysis_type = st.selectbox(
        "选择分析方法",
        [
            "---",
            "主成分分析 (PCA)",
            "K-Means 聚类分析",
            "层次聚类分析",
            "相关性矩阵与热力图",
            "因子分析探索"
        ]
    )
    
    st.markdown("---")
    
    if analysis_type == "---":
        st.info("👆 请从上方下拉菜单选择分析方法，或查看功能简介了解各方法用途")
        return
    
    elif analysis_type == "主成分分析 (PCA)":
        pca_analysis(df)
    
    elif analysis_type == "K-Means 聚类分析":
        kmeans_analysis(df)
    
    elif analysis_type == "层次聚类分析":
        hierarchical_analysis(df)
    
    elif analysis_type == "相关性矩阵与热力图":
        correlation_analysis(df)


def show_multivariate_overview():
    st.markdown("""
    ### 📋 多变量分析方法概览
    
    | 方法 | 用途 | 输出 |
    |------|------|------|
    主成分分析(PCA) | 降维、数据压缩、识别主要变异来源 | 主成分得分、载荷图、方差贡献率 |
    K-Means聚类 | 将样本分为K个相似组 | 聚类标签、中心点、轮廓系数 |
    层次聚类 | 构建样本/变量的层级关系 | 树状图、聚类谱系 |
    相关性分析 | 探索变量间线性关系 | 相关系数矩阵、显著性检验 |
    """)


# ========== 主成分分析 ==========
def pca_analysis(df):
    st.markdown("### 📊 主成分分析 (Principal Component Analysis)")
    
    st.info("""
    **主成分分析 (PCA)** 是一种降维技术，将多个相关变量综合为少数几个不相关的综合指标。
    
    **适用场景**：变量多且存在相关性，需要降维或综合评价时（如多性状品种评价）。
    
    **数据要求**：≥2个数值变量，建议标准化消除量纲影响。
    
    **关键概念**：
    - **特征值 > 1**：对应主成分的方差贡献大于单个原始变量
    - **累计方差 > 70%~80%**：前几个主成分能解释大部分信息
    - **载荷(Loading)**：原始变量与主成分的相关系数，绝对值越大关系越密切
    - **KMO > 0.6**：数据适合做PCA（取样适切性良好）
    
    **输出**：特征值表、碎石图、得分图(2D/3D)、变量载荷图。
    """)
    
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    
    selected_vars = st.multiselect(
        "选择参与分析的变量（建议选数值型）",
        numeric_cols,
        default=numeric_cols[:min(5, len(numeric_cols))]
    )
    
    n_components = st.slider(
        "主成分数量", min_value=2, max_value=min(len(selected_vars), 10),
        value=min(len(selected_vars), 3)
    )
    
    standardize = st.checkbox("标准化（Z-score）", value=True,
                              help="当变量量纲差异大时建议标准化")
    
    if not selected_vars or len(selected_vars) < 2:
        st.warning("请至少选择2个变量")
        return
    
    # 准备数据
    clean_df = df[selected_vars].dropna()
    
    if len(clean_df) < 5:
        st.warning("有效样本数不足")
        return
    
    if standardize:
        _, ScalerCls = _get_pca()
        scaler = ScalerCls()
        X_scaled = scaler.fit_transform(clean_df)
    else:
        X_scaled = clean_df.values
    
    # PCA拟合
    PCA_cls, _ = _get_pca()
    pca = PCA_cls(n_components=n_components)
    scores = pca.fit_transform(X_scaled)
    loadings = pca.components_.T * np.sqrt(pca.explained_variance_)
    
    # 结果展示
    variance_ratio = pca.explained_variance_ratio_
    cumulative_var = np.cumsum(variance_ratio)
    
    col1, col2, col3 = st.columns(3)
    with col1: 
        st.metric("累计解释方差", f"{cumulative_var[-1]*100:.1f}%")
    with col2:
        st.metric(f"前2主成分", f"{cumulative_var[1]*100:.1f}%")
    with col3:
        st.metric("KMO适用性" if len(selected_vars)>=3 else "", 
                  calculate_kmo(X_scaled) if len(selected_vars)>=3 else "-")
    
    # 方差解释表
    var_table = pd.DataFrame({
        '主成分': [f'PC{i+1}' for i in range(n_components)],
        '特征值': pca.explained_variance_.round(4),
        '方差比例%': (variance_ratio*100).round(2),
        '累积方差%': (cumulative_var*100).round(2)
    })
    st.markdown("#### 特征值与方差贡献")
    st.dataframe(var_table.set_index('主成分'))
    
    # 碎石图
    fig_scree = _get_subplots()(specs=[[{"secondary_y": True}]])
    go = _get_go()
    fig_scree.add_trace(go.Bar(
        x=[f'PC{i+1}' for i in range(n_components)],
        y=pca.explained_variance_,
        name='特征值',
        marker_color='#3498db'
    ))
    fig_scree.add_trace(go.Scatter(
        x=[f'PC{i+1}' for i in range(n_components)],
        y=cumulative_var * 100,
        mode='lines+markers',
        name='累积%',
        line=dict(color='red', width=2)
    ), secondary_y=True)
    fig_scree.update_layout(
        title='碎石图',
        xaxis_title='主成分', yaxis_title='特征值',
        yaxis2_title='累积方差%', height=400
    )
    st.plotly_chart(fig_scree, width="stretch")
    
    # 得分图
    tab_2d, tab_3d, tab_load = st.tabs(["PC1×PC2得分图", "三维得分图", "载荷图"])
    
    with tab_2d:
        score_df = pd.DataFrame({
            'PC1': scores[:, 0], 'PC2': scores[:, 1],
            **{col: clean_df[col].values for col in selected_vars}
        })
        
        color_by = st.selectbox("着色变量", ["无"] + selected_vars, key="pca_color")
        
        fig_2d = go.Figure()
        if color_by != "无":
            for group in score_df[color_by].unique():
                mask = score_df[color_by] == group
                fig_2d.add_trace(go.Scatter(
                    x=score_df.loc[mask, 'PC1'],
                    y=score_df.loc[mask, 'PC2'],
                    mode='markers', name=str(group),
                    text=clean_df.index[mask],
                    opacity=0.7
                ))
        else:
            fig_2d.add_trace(go.Scatter(
                x=scores[:, 0], y=scores[:, 1],
                mode='markers+text', text=clean_df.index,
                textposition="top center", opacity=0.6
            ))
        
        fig_2d.update_layout(
            title=f'PC1 ({variance_ratio[0]*100:.1f}%) × PC2 ({variance_ratio[1]*100:.1f}%)',
            xaxis_title='PC1', yaxis_title='PC2', height=500,
            legend_title_text=None
        )
        st.plotly_chart(fig_2d, width="stretch")
    
    with tab_3d:
        if n_components >= 3:
            fig_3d = go.Figure()
            fig_3d.add_trace(go.Scatter3d(
                x=scores[:, 0], y=scores[:, 1], z=scores[:, 2],
                mode='markers+text' if len(clean_df)<50 else 'markers',
                marker=dict(size=8, opacity=0.7),
                text=list(clean_df.index)[:30] if len(clean_df)>30 else list(clean_df.index)
            ))
            fig_3d.update_layout(
                title='三维主成分空间',
                scene=dict(xaxis_title='PC1', yaxis_title='PC2', zaxis_title='PC3'),
                height=550
            )
            st.plotly_chart(fig_3d, width="stretch")
        else:
            st.info("需要选择≥3个主成分才能显示3D图")
    
    with tab_load:
        # 载荷图（变量在主成分上的投影）
        fig_load = go.Figure()
        
        for i, var in enumerate(selected_vars):
            fig_load.add_trace(go.Scatter(
                x=[0, loadings[i, 0]], y=[0, loadings[i, 1]],
                mode='lines+markers+text',
                line=dict(width=2, color=['red','green','blue','orange','purple'][i % 5]),
                marker_size=12, text=["", var], textposition='top center'
            ))
        
        # 参考圆
        theta = np.linspace(0, 2*np.pi, 100)
        max_load = np.max(np.abs(loadings[:, :2])) * 1.1
        fig_load.add_shape(type="circle", xref="x", yref="y",
                          x0=-max_load, y0=-max_load, x1=max_load, y1=max_load,
                          line=dict(dash='dash', color='gray'))
        
        fig_load.update_layout(
            title='变量载荷图',
            xaxis_title=f'PC1 ({variance_ratio[0]*100:.1f}%)',
            yaxis_title=f'PC2 ({variance_ratio[1]*100:.1f}%)',
            height=500, width=600, legend_title_text=None
        )
        fig_load.update_xaxes(range=[-max_load, max_load])
        fig_load.update_yaxes(range=[-max_load, max_load])
        st.plotly_chart(fig_load, width="stretch")
        
        # 载荷表
        loadings_df = pd.DataFrame(
            loadings[:, :n_components],
            index=selected_vars,
            columns=[f'PC{i+1}' for i in range(n_components)]
        ).round(3)
        st.dataframe(loadings_df.style.background_gradient(cmap='RdBu_r', axis=None))
    
    # 主成分得分导出
    st.markdown("#### 导出主成分得分")
    score_export = pd.DataFrame(scores, columns=[f'PC{i+1}' for i in range(n_components)],
                                 index=clean_df.index)
    
    if st.button("下载得分矩阵"):
        csv = score_export.to_csv(index=True).encode('utf-8')
        if can_download():
            st.download_button("保存CSV", data=csv, file_name="pca_scores.csv", mime="text/csv")
        else:
            st.warning("分析次数已用完，充值后可下载结果。请前往侧边栏充值中心。")


# ========== K-Means 聚类 ==========
def kmeans_analysis(df):
    st.markdown("### 🔵 K-Means 聚类分析")
    
    st.info("""
    **K-Means 聚类**将样本划分为 K 个群组，使组内尽可能相似、组间尽可能不同。
    
    **适用场景**：已知要分几类（如品种分为3个等级、样本分成不同群体）。
    
    **数据要求**：≥2个数值变量，建议标准化。
    
    **参数选择**：
    - **K值**：可通过"肘部法则"确定，拐点处为较优K值
    - **标准化**：变量量纲不同时必须勾选
    
    **评估指标**：
    - **轮廓系数**：-1~1，越接近1越好
    - **CH指数**：越大越好（组间分离度）
    - **DB指数**：越小越好（组内紧凑度）
    
    **输出**：聚类评估、各簇统计、散点图/雷达图、肘部法则图。
    """)
    
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    
    selected_vars = st.multiselect("选择聚类变量", numeric_cols, default=numeric_cols[:4])
    n_clusters = st.slider("聚类数 (K)", min_value=2, max_value=10, value=3)
    standardize = st.checkbox("标准化", value=True)
    
    if not selected_vars:
        return
    
    clean_df = df[selected_vars].dropna()
    
    KMeans, silhouette_score, calinski_harabasz_score, davies_bouldin_score = _get_kmeans()
    go = _get_go()
    
    if standardize:
        _, ScalerCls = _get_pca()
        scaler = ScalerCls()
        X = scaler.fit_transform(clean_df)
    else:
        X = clean_df.values
    
    # 执行KMeans
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10, init='k-means++')
    labels = kmeans.fit_predict(X)
    centers = kmeans.cluster_centers_
    
    # 评估指标
    sil = silhouette_score(X, labels)
    ch = calinski_harabasz_score(X, labels)
    db = davies_bouldin_score(X, labels)
    
    st.markdown("#### 聚类评估指标")
    m1, m2, m3 = st.columns(3)
    with m1: st.metric("轮廓系数 (Silhouette)", f"{sil:.4f}", help="-1~1，越接近1越好")
    with m2: st.metric("CH指数", f"{ch:.1f}", help="越大越好，簇间分离度")
    with m3: st.metric("DB指数", f"{db:.4f}", help="越小越好，簇内紧凑度")
    
    # 各簇统计
    result_df = clean_df.copy()
    result_df['聚类'] = labels
    
    cluster_summary = result_df.groupby('聚类')[selected_vars].mean().round(3)
    cluster_summary['样本数'] = result_df.groupby('聚类').size()
    cluster_summary['占比%'] = (cluster_summary['样本数'] / len(result_df) * 100).round(1)
    
    tab_stats, tab_viz, tab_elbow = st.tabs(["各簇统计", "可视化", "肘部法则"])
    
    with tab_stats:
        st.markdown("##### 各聚类中心的特征均值")
        st.dataframe(cluster_summary.round(3), width="stretch")
        
        # 各组原始数据预览
        st.markdown("##### 各组样本详情")
        for c in range(n_clusters):
            with st.expander(f"聚类 {c} ({len(labels[labels==c])} 个样本)"):
                st.dataframe(result_df[labels==c][selected_vars + ['聚类']].head(20))
    
    with tab_viz:
        viz_type = st.radio("可视化类型", ["散点图(2D降维)", "雷达图"], horizontal=True, key="km_viz")
        
        if viz_type == "散点图(2D降维)":
            # 用PCA降到2维显示
            PCA_cls, _ = _get_pca()
            pca_vis = PCA_cls(n_components=2)
            X_2d = pca_vis.fit_transform(X)
            
            fig_km = go.Figure()
            colors = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6',
                     '#1abc9c', '#e67e22', '#34495e', '#16a085', '#c0392b']
            
            for c in range(n_clusters):
                mask = labels == c
                fig_km.add_trace(go.Scatter(
                    x=X_2d[mask, 0], y=X_2d[mask, 1],
                    mode='markers', name=f'聚类 {c}',
                    marker_color=colors[c % len(colors)],
                    text=result_df.index[result_df['聚类']==c],
                    opacity=0.7
                ))
            
            # 中心点
            centers_2d = pca_vis.transform(centers)
            fig_km.add_trace(go.Scatter(
                x=centers_2d[:, 0], y=centers_2d[:, 1],
                mode='markers', name='中心点',
                marker_symbol='x', marker_size=15,
                marker_color='black', marker_line_width=3
            ))
            
            fig_km.update_layout(title='K-Means 聚类结果（PCA降维）',
                               height=500, showlegend=True, legend_title_text=None)
            st.plotly_chart(fig_km, width="stretch")
        
        else:
            # 雷达图
            fig_radar = go.Figure()
            
            for c in range(n_clusters):
                center_scaled = centers[c] if not standardize else centers[c]
                
                fig_radar.add_trace(go.Scatterpolar(
                    r=center_scaled.tolist() + [center_scaled[0]],
                    theta=selected_vars + [selected_vars[0]],
                    fill='toskeleton', name=f'聚类 {c}',
                    opacity=0.6
                ))
            
            fig_radar.update_layout(
                polar=dict(radialaxis_visible=True, type='linear'),
                title='各聚类中心雷达图', height=450
            )
            st.plotly_chart(fig_radar, width="stretch")
    
    with tab_elbow:
        # 肘部法则
        inertias = []
        sil_scores = []
        K_range = range(2, min(11, len(X)))
        
        for k in K_range:
            km_temp = KMeans(n_clusters=k, random_state=42, n_init=10).fit(X)
            inertias.append(km_temp.inertia_)
            sil_scores.append(silhouette_score(X, km_temp.labels_))
        
        make_subplots = _get_subplots()
        fig_elbow = make_subplots(specs=[[{"secondary_y": True}]])
        fig_elbow.add_trace(go.Scatter(x=list(K_range), y=inertias,
                                       mode='lines+markers', name='惯性(SSE)',
                                       marker_color='blue'))
        fig_elbow.add_trace(go.Scatter(x=list(K_range), y=sil_scores,
                                       mode='lines+markers', name='轮廓系数',
                                       line=dict(color='red'), yaxis='y2'))
        fig_elbow.update_layout(title='肘部法则 & 轮廓系数', xaxis_title='K值',
                               yaxis_title='组内平方和(SSE)', yaxis2_title='轮廓系数', height=400)
        st.plotly_chart(fig_elbow, width="stretch")


# ========== 层次聚类 ==========
def hierarchical_analysis(df):
    st.markdown("### 🌳 层次聚类分析")
    
    st.info("""
    **层次聚类**通过逐步合并（或分裂）构建样本间的层次关系树。
    
    **适用场景**：不确定分几类，想探索数据的层次结构（如品种亲缘关系）。
    
    **数据要求**：≥2个数值变量，会自动标准化。
    
    **参数说明**：
    - **链接方法**：
      - Ward（离差平方和）：最常用，倾向产生大小相近的簇
      - Complete（最长距离）：产生紧凑的簇
      - Average（平均距离）：折中方案
    - **距离度量**：欧氏距离（最常用）、相关系数距离、曼哈顿距离
    
    **输出**：谱系图（树状图）、截取指定聚类数后的各组描述统计。
    """)
    
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    selected_vars = st.multiselect("选择变量", numeric_cols, default=numeric_cols[:4])
    
    method = st.selectbox("链接方法", ["ward", "complete", "average", "single"],
                          format_func=lambda x: {"ward":"离差平方和","complete":"最长距离","average":"平均距离","single":"最短距离"}[x])
    metric = st.selectbox("距离度量", ["euclidean", "correlation", "cityblock"],
                          format_func=lambda x: {"euclidean":"欧氏距离","correlation":"相关系数","cityblock":"曼哈顿距离"}[x])
    
    if not selected_vars:
        return
    
    clean_df = df[selected_vars].dropna()
    _, ScalerCls = _get_pca()
    scaler = ScalerCls()
    X = scaler.fit_transform(clean_df)
    
    # 计算距离矩阵并执行层次聚类
    _, linkage = _get_hierarchy()
    linked = linkage(X, method=method, metric=metric)
    
    # 树状图
    go = _get_go()
    fig_dendro = go.Figure()
    
    scipy_dendrogram, _ = _get_hierarchy()
    
    # Plotly树状图需要特殊处理
    st.markdown("#### 谱系图 (Dendrogram)")
    
    # 使用matplotlib生成后转换或使用plotly自定义
    import io
    import matplotlib.pyplot as plt
    
    buf = io.BytesIO()
    plt.figure(figsize=(12, max(6, len(clean_df)*0.25)))
    scipy_dendrogram(linked, labels=clean_df.index.tolist(),
                    orientation='top', leaf_font_size=10,
                    color_threshold=0.7*max(linked[:,2]))
    plt.title(f"层次聚类树状图 ({method}方法)")
    plt.tight_layout()
    plt.savefig(buf, format='png', dpi=150)
    plt.close()
    buf.seek(0)
    
    st.image(buf, width="stretch")
    
    # 截取指定数量的簇
    cut_n = st.slider("截取聚类数", min_value=2, max_value=10, value=3)
    from scipy.cluster.hierarchy import fcluster
    cluster_labels = fcluster(linked, t=cut_n, criterion='maxclust')
    
    # 各簇描述
    result_hier = clean_df.copy()
    result_hier['聚类'] = cluster_labels
    st.markdown(f"#### {cut_n}个聚类的描述统计")
    st.dataframe(result_hier.groupby('聚类')[selected_vars].agg(['mean', 'std', 'count']).round(3))


# ========== 相关性分析 ==========
def correlation_analysis(df):
    st.markdown("### 🔗 相关性分析")
    
    st.info("""
    **相关性分析**用于量化变量之间的线性（或单调）关系强度和方向。
    
    **数据要求**：≥2个数值变量。
    
    **三种相关系数**：
    - **Pearson**：度量线性相关（最常用，要求数值型、近似正态）
    - **Spearman**：度量单调相关（基于秩次，不要求数值型/正态）
    - **Kendall**：度量有序相关（小样本、有大量相同秩次时更稳健）
    
    **结果解读**：
    - r > 0：正相关；r < 0：负相关
    - |r| < 0.3：弱相关；0.3~0.7：中等；> 0.7：强相关
    
    **输出**：热力图、相关系数表、显著性检验（标注 * / ** / ***）。
    """)
    
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    selected_vars = st.multiselect("选择变量", numeric_cols, default=numeric_cols)
    
    corr_method = st.selectbox("相关系数类型", ["pearson", "spearman", "kendall"])
    sig_level = st.select_slider("显著性水平", options=[0.01, 0.05, 0.10], value=0.05)
    
    if len(selected_vars) < 2:
        return
    
    _stats = _get_stats()
    
    # 相关系数矩阵
    corr_matrix = df[selected_vars].corr(method=corr_method)
    
    # p值计算
    n = len(df)
    pval_matrix = pd.DataFrame(np.zeros((len(selected_vars), len(selected_vars))),
                               index=selected_vars, columns=selected_vars)
    
    for i, v1 in enumerate(selected_vars):
        for j, v2 in enumerate(selected_vars):
            if i != j:
                if corr_method == "pearson":
                    _, p = _stats.pearsonr(df[v1].dropna(), df[v2].dropna())
                elif corr_method == "spearman":
                    _, p = _stats.spearmanr(df[v1].dropna(), df[v2].dropna())
                else:
                    _, p = _stats.kendalltau(df[v1].dropna(), df[v2].dropna())
                pval_matrix.loc[v1, v2] = p
                pval_matrix.loc[v2, v1] = p
    
    # 可视化
    tab_heatmap, tab_table, tab_sig = st.tabs(["热力图", "相关系数表", "显著性检验"])
    
    with tab_heatmap:
        # 创建带注释的热力图
        annotations = []
        for i, v1 in enumerate(selected_vars):
            for j, v2 in enumerate(selected_vars):
                r = corr_matrix.loc[v1, v2]
                p = pval_matrix.loc[v1, v2]
                sig_mark = "***" if p<0.001 else "**" if p<0.01 else "*" if p<sig_level else ""
                annotations.append(dict(
                    x=v2, y=v1, text=f"{r:.2f}{sig_mark}",
                    font=dict(color="white" if abs(r)>0.5 else "black", size=11),
                    showarrow=False
                ))
        
        go = _get_go()
        fig_corr = go.Figure(data=go.Heatmap(
            z=corr_matrix.values, x=selected_vars, y=selected_vars,
            colorscale='RdBu_r', zmid=0,
            text=[[f"{corr_matrix.iloc[i,j]:.2f}" for j in range(len(selected_vars))] 
                   for i in range(len(selected_vars))],
            texttemplate="%{text}",
            hoverinfo='text+z'
        ))
        fig_corr.update(layout_annotations=annotations)  # type: ignore
        fig_corr.update_layout(title=f'{corr_method.capitalize()} 相关系数矩阵', height=500)
        st.plotly_chart(fig_corr, width="stretch")
    
    with tab_table:
        display_corr = corr_matrix.round(4)
        st.dataframe(display_corr, width="stretch")
    
    with tab_sig:
        sig_display = pval_matrix.copy()
        def format_p(p):
            if p < 0.001: return "<0.001***"
            elif p < 0.01: return f"{p:.4f}**"
            elif p < 0.05: return f"{p:.4f}*"
            else: return f"{p:.4f}"
        
        sig_display = sig_display.applymap(format_p)
        st.dataframe(sig_display, width="stretch")
        st.caption("*p<0.05, **p<0.01, ***p<0.001")


# ========== 辅助函数 ==========
def calculate_kmo(data_array):
    """计算KMO取样适切性量数"""
    try:
        from factor_analyzer.factor_analyzer import calculate_kmo
        kmo_per, kmo_total = calculate_kmo(data_array)
        return round(kmo_total, 3)
    except ImportError:
        # 简化版计算
        from numpy.linalg import inv
        R = np.corrcoef(data_array.T)
        try:
            R_inv = inv(R)
            D = np.diag(1/np.sqrt(np.diag(R_inv)))
            anti_R = -D @ R_inv @ D
            np.fill_diagonal(anti_R, 0)
            anti_sum = np.sum(anti_R**2)
            total_sum = anti_sum + np.sum(R**2) - len(R)
            kmo_val = anti_sum / total_sum if total_sum > 0 else 0
            return round(kmo_val, 3)
        except Exception:
            return "需安装factor_analyzer"


if __name__ == "__main__":
    render_multivariate()