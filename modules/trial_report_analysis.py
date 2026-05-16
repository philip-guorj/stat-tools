"""
StatTools - 区试报告分析模块 v2.0
基于艾格偌系统真实功能重构。覆盖多重比较、稳定性、CK比较、
AMMI/GGE双标图、试点评价、异常值诊断、审定标准、报告导出。
向后兼容：重导出 modules.ssr_analysis 所有接口。
"""

import warnings; warnings.filterwarnings('ignore')
import numpy as np
import pandas as pd
from scipy import stats as scipy_stats
from scipy.linalg import svd
from typing import Optional, Dict, List, Tuple, Union
import json, os, io

# ── 1. 从 ssr_analysis.py 重导出（向后兼容） ──
from modules.ssr_analysis import (
    SSRMultipleComparison as SSRMultipleComparison,
    StabilityAnalysis as StabilityAnalysis,
    CKComparison as CKComparison,
    SSRReportGenerator as SSRReportGenerator,
    render_cld_bar_chart, plot_stability_scatter, plot_er_regression,
    render_duncan_cld_chart, rename_anova_index, format_anova_table,
)

# ── 2. 延迟导入（自 utils.imports） ──
from utils.imports import get_statsmodels as _get_statsmodels

def _find_block_col(df, candidates=None):
    if candidates is None:
        candidates = ['区组','重复','block','rep','Block','Rep','区组编号']
    for c in candidates:
        if c in df.columns: return c
    return None

# ── 3. BiplotAnalysis — AMMI + GGE ──
class BiplotAnalysis:
    """AMMI 和 GGE 双标图分析（Gauch 2006, Yan & Kang 2003）"""

    @staticmethod
    def ammi_analysis(df, response, genotype, environment, n_ipc=2):
        """AMMI 分析：方差分解 + SVD。返回 anova/ipc_table/genotype_scores/env_scores/ge_matrix"""
        mt = df.pivot_table(index=genotype, columns=environment, values=response, aggfunc='mean')
        genes, envs = mt.index.tolist(), mt.columns.tolist()
        Y = mt.values
        gm, g_mean, e_mean = np.mean(Y), np.mean(Y, axis=1), np.mean(Y, axis=0)
        GE = Y - g_mean.reshape(-1,1) - e_mean.reshape(1,-1) + gm

        n_g, n_e = len(genes), len(envs)
        ss_g = np.sum((g_mean-gm)**2) * n_e; ss_e = np.sum((e_mean-gm)**2) * n_g
        ss_ge = np.sum(GE**2); ss_t = np.sum((Y-gm)**2)

        ss_err, df_err = 0, 0
        if len(df) / (n_g*n_e) > 1:
            try:
                sm, ols_fn, anova_lm_fn, _ = _get_statsmodels()
                bc = _find_block_col(df)
                fml = f'Q("{response}")~C(Q("{genotype}"))+C(Q("{environment}"))+C(Q("{genotype}")):C(Q("{environment}"))'
                if bc: fml += f'+C(Q("{bc}"))'
                at = anova_lm_fn(ols_fn(fml, data=df).fit(), typ=2)
                e = at.loc[at.index.str.lower()=='residual'] if len(at)>0 else at.iloc[-1:]
                ss_err = float(e['sum_sq'].values[0]) if len(e)>0 else 0
                df_err = int(e['df'].values[0]) if len(e)>0 else 0
            except Exception: pass

        dg = n_g-1; de = n_e-1; dge = dg*de
        anova = pd.DataFrame([
            {'来源':'品种(G)','DF':dg,'SS':round(ss_g,2),'MS':round(ss_g/dg,4) if dg else 0,
             'F':round(ss_g/dg/(ss_err/df_err),4) if ss_err and df_err else '-'},
            {'来源':'环境(E)','DF':de,'SS':round(ss_e,2),'MS':round(ss_e/de,4) if de else 0,
             'F':round(ss_e/de/(ss_err/df_err),4) if ss_err and df_err else '-'},
            {'来源':'G×E','DF':dge,'SS':round(ss_ge,2),'MS':round(ss_ge/dge,4) if dge else 0,
             'F':round(ss_ge/dge/(ss_err/df_err),4) if ss_err and df_err else '-'}])
        if ss_err:
            anova = pd.concat([anova, pd.DataFrame([
                {'来源':'误差','DF':df_err,'SS':round(ss_err,2),'MS':round(ss_err/df_err,4),'F':''}])])
        anova = pd.concat([anova, pd.DataFrame([
            {'来源':'总计','DF':dg+de+dge+df_err,'SS':round(ss_t,2),'MS':'','F':''}])])

        U, s, Vt = svd(GE, full_matrices=False)
        tv = np.sum(s**2); nk = min(n_ipc, len(s)); cum=0
        ipc = []
        for i in range(nk):
            pct = s[i]**2/tv*100 if tv else 0; cum+=pct
            ipc.append({'IPC':f'IPC{i+1}','奇异值':round(s[i],4),
                        '方差贡献率(%)':round(pct,2),'累积贡献率(%)':round(cum,2)})

        gsc = U[:,:nk] * s[:nk]; esc = Vt.T[:,:nk] * s[:nk]
        gcols = {genotype:genes,'均值':g_mean}; ecols = {environment:envs,'均值':e_mean}
        for i in range(nk):
            gcols[f'IPC{i+1}'] = gsc[:,i]; ecols[f'IPC{i+1}'] = esc[:,i]

        return {'anova':anova,'ipc_table':pd.DataFrame(ipc),
                'genotype_scores':pd.DataFrame(gcols),'env_scores':pd.DataFrame(ecols),
                'ge_matrix':GE,'mean_table':mt,'grand_mean':gm}

    @staticmethod
    def gge_analysis(df, response, genotype, environment, n_components=2):
        """GGE 双标图：对 G+GE 矩阵 SVD"""
        mt = df.pivot_table(index=genotype, columns=environment, values=response, aggfunc='mean')
        genes, envs = mt.index.tolist(), mt.columns.tolist(); Y = mt.values
        e_mean = np.mean(Y, axis=0)
        GGE = Y - e_mean.reshape(1,-1)
        U, s, Vt = svd(GGE, full_matrices=False)
        nk = min(n_components, len(s)); tv = np.sum(s**2)
        ve = [s[i]**2/tv*100 if tv else 0 for i in range(nk)]

        gcols = {genotype:genes,'均值':np.mean(Y,axis=1)}
        ecols = {environment:envs,'均值':e_mean}
        for i in range(nk):
            gcols[f'PC{i+1}'] = U[:,i]*s[i]; ecols[f'PC{i+1}'] = Vt.T[:,i]*s[i]
        ev = Vt.T[:,:nk]*s[:nk]; ecols['向量长度'] = np.sqrt(np.sum(ev**2, axis=1))
        return {'genotype_scores':pd.DataFrame(gcols),'env_scores':pd.DataFrame(ecols),
                'var_explained':ve,'eigenvalues':s[:nk],'gge_matrix':GGE,
                'mean_table':mt,'grand_mean':np.mean(Y)}

    @staticmethod
    def _detect_label_col(df, exclude={'均值','IPC1','IPC2','IPC3','PC1','PC2','向量长度'}):
        """自动检测 DataFrame 中叶签列名"""
        for c in df.columns:
            if c not in exclude:
                return c
        return df.columns[0]

    @staticmethod
    def plot_ammi1_biplot(r, genotype=None, environment=None):
        """AMMI1：产量均值 vs IPC1"""
        if genotype is None: genotype=BiplotAnalysis._detect_label_col(r['genotype_scores'])
        if environment is None: environment=BiplotAnalysis._detect_label_col(r['env_scores'])
        import plotly.graph_objects as go
        p = r['ipc_table'].iloc[0]['方差贡献率(%)'] if len(r['ipc_table'])>0 else 0
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=r['genotype_scores']['均值'],y=r['genotype_scores']['IPC1'],
            mode='markers+text',text=r['genotype_scores'][genotype],textposition='top center',
            marker=dict(size=10,color='#3b82f6',symbol='circle'),name='品种'))
        fig.add_trace(go.Scatter(x=r['env_scores']['均值'],y=r['env_scores']['IPC1'],
            mode='markers+text',text=r['env_scores'][environment],textposition='bottom center',
            marker=dict(size=10,color='#ef4444',symbol='diamond'),name='环境'))
        fig.add_hline(y=0,line_dash='dash',line_color='gray',opacity=0.3)
        fig.update_layout(title=f'AMMI1 (IPC1={p:.1f}%)',xaxis_title='产量均值',yaxis_title='IPC1',height=550)
        return fig

    @staticmethod
    def plot_ammi2_biplot(r, genotype=None, environment=None):
        """AMMI2：IPC1 vs IPC2"""
        if genotype is None: genotype=BiplotAnalysis._detect_label_col(r['genotype_scores'])
        if environment is None: environment=BiplotAnalysis._detect_label_col(r['env_scores'])
        import plotly.graph_objects as go
        it=r['ipc_table']; p1=it.iloc[0]['方差贡献率(%)'] if len(it)>0 else 0
        p2=it.iloc[1]['方差贡献率(%)'] if len(it)>1 else 0
        gs,es=r['genotype_scores'],r['env_scores']
        h2='IPC2' in gs.columns
        fig=go.Figure()
        fig.add_trace(go.Scatter(x=gs['IPC1'],y=gs['IPC2'] if h2 else [0]*len(gs),
            mode='markers+text',text=gs[genotype],textposition='top center',
            marker=dict(size=10,color='#3b82f6',symbol='circle'),name='品种'))
        fig.add_trace(go.Scatter(x=es['IPC1'],y=es['IPC2'] if h2 else [0]*len(es),
            mode='markers+text',text=es[environment],textposition='bottom center',
            marker=dict(size=10,color='#ef4444',symbol='diamond'),name='环境'))
        fig.add_hline(y=0,line_dash='dash',line_color='gray',opacity=0.3)
        fig.add_vline(x=0,line_dash='dash',line_color='gray',opacity=0.3)
        fig.update_layout(title=f'AMMI2 (IPC1={p1:.1f}%, IPC2={p2:.1f}%)',
                          xaxis_title='IPC1',yaxis_title='IPC2',height=550)
        return fig

    @staticmethod
    def plot_gge_biplot(r, genotype=None, environment=None):
        """GGE 双标图：PC1 vs PC2 + 环境向量"""
        if genotype is None: genotype=BiplotAnalysis._detect_label_col(r['genotype_scores'])
        if environment is None: environment=BiplotAnalysis._detect_label_col(r['env_scores'])
        import plotly.graph_objects as go
        gs,es=r['genotype_scores'],r['env_scores']; ve=r['var_explained']
        p1=ve[0] if ve else 0; p2=ve[1] if len(ve)>1 else 0
        h2='PC2' in gs.columns
        fig=go.Figure()
        fig.add_trace(go.Scatter(x=gs['PC1'],y=gs['PC2'] if h2 else [0]*len(gs),
            mode='markers+text',text=gs[genotype],textposition='top center',
            marker=dict(size=10,color='#3b82f6',symbol='circle'),name='品种'))
        for _,rw in es.iterrows():
            x,y=rw['PC1'],rw['PC2'] if h2 else 0
            fig.add_trace(go.Scatter(x=[0,x],y=[0,y],mode='lines+text',
                text=[None,rw[environment]],textposition='top center',
                line=dict(color='rgba(239,68,68,0.5)',width=1.5),
                marker=dict(size=[0,8],color='#ef4444',symbol='diamond'),showlegend=False))
        fig.add_hline(y=0,line_dash='dash',line_color='gray',opacity=0.3)
        fig.add_vline(x=0,line_dash='dash',line_color='gray',opacity=0.3)
        mx=max(abs(gs['PC1']).max(),abs(gs['PC2']).max() if h2 else 1,
               abs(es['PC1']).max(),abs(es['PC2']).max() if h2 else 1)*1.2
        fig.update_layout(title=f'GGE (PC1={p1:.1f}%, PC2={p2:.1f}%)',
            xaxis_title=f'PC1 ({p1:.1f}%)',yaxis_title=f'PC2 ({p2:.1f}%)',
            height=600,width=700,xaxis=dict(range=[-mx,mx],scaleanchor='y',scaleratio=1),
            yaxis=dict(range=[-mx,mx]))
        return fig

    @staticmethod
    def plot_gge_polygon(r, genotype=None, environment=None):
        """GGE 多边形图（convex hull）"""
        if genotype is None: genotype=BiplotAnalysis._detect_label_col(r['genotype_scores'])
        if environment is None: environment=BiplotAnalysis._detect_label_col(r['env_scores'])
        import plotly.graph_objects as go
        from scipy.spatial import ConvexHull
        gs,es=r['genotype_scores'],r['env_scores']; ve=r['var_explained']
        p1=ve[0] if ve else 0; p2=ve[1] if len(ve)>1 else 0
        h2='PC2' in gs.columns
        fig=go.Figure()
        fig.add_trace(go.Scatter(x=gs['PC1'],y=gs['PC2'] if h2 else [0]*len(gs),
            mode='markers+text',text=gs[genotype],textposition='top center',
            marker=dict(size=8,color='#94a3b8',opacity=0.6),showlegend=False))
        if h2:
            pts=np.column_stack([gs['PC1'].values,gs['PC2'].values])
            try:
                hull=ConvexHull(pts); hp=np.vstack([pts[hull.vertices],pts[hull.vertices[0]]])
                fig.add_trace(go.Scatter(x=hp[:,0],y=hp[:,1],mode='lines',
                    line=dict(color='#3b82f6',width=2),name='凸包'))
                hdf=gs.iloc[hull.vertices]
                fig.add_trace(go.Scatter(x=hdf['PC1'],y=hdf['PC2'],
                    mode='markers+text',text=hdf[genotype],textposition='top center',
                    marker=dict(size=14,color='#f59e0b',symbol='star',
                                line=dict(width=2,color='#d97706')),name='顶点品种'))
            except Exception: pass
        for _,rw in es.iterrows():
            fig.add_trace(go.Scatter(x=[0,rw['PC1']],y=[0,rw['PC2']],mode='lines+text',
                text=[None,rw[environment]],textposition='top center',
                line=dict(color='rgba(239,68,68,0.5)',width=1.5),
                marker=dict(size=[0,8],color='#ef4444',symbol='diamond'),showlegend=False))
        fig.add_hline(y=0,line_dash='dash',line_color='gray',opacity=0.2)
        fig.add_vline(x=0,line_dash='dash',line_color='gray',opacity=0.2)
        mx=max(abs(gs['PC1']).max(),abs(gs['PC2']).max() if h2 else 1,
               abs(es['PC1']).max(),abs(es['PC2']).max())*1.3
        fig.update_layout(title=f'GGE多边形 (PC1={p1:.1f}%, PC2={p2:.1f}%)',
            xaxis_title=f'PC1 ({p1:.1f}%)',yaxis_title=f'PC2 ({p2:.1f}%)',
            height=600,width=700,xaxis=dict(range=[-mx,mx],scaleanchor='y',scaleratio=1),
            yaxis=dict(range=[-mx,mx]),
            legend=dict(orientation='h',yanchor='bottom',y=1.02,xanchor='right',x=1))
        return fig


# =============================================================================
# 4. TrialEvaluation — 试点评价
# =============================================================================

class TrialEvaluation:
    """试点鉴别力、品种均值-CV、互作效应"""

    @staticmethod
    def env_discriminability(df, response, genotype, environment):
        """试点鉴别力：各环境品种间CV，反映区分能力"""
        rows=[]
        for e in sorted(df[environment].unique()):
            sub=df[df[environment]==e]
            gm=sub.groupby(genotype)[response].mean()
            em=sub[response].mean(); es=sub[response].std()
            gc=(gm.std()/gm.mean()*100) if gm.mean()!=0 else 0
            rows.append({environment:e,'环境均值':round(em,2),
                         '环境CV(%)':round(es/em*100 if em else 0,2),
                         '品种间变异CV(%)':round(gc,2),
                         '品种数':int(sub[genotype].nunique()),'观测数':len(sub)})
        r=pd.DataFrame(rows).sort_values('品种间变异CV(%)',ascending=False)
        r['鉴别力排名']=range(1,len(r)+1)
        return r

    @staticmethod
    def plot_env_discriminability(edf, environment=None):
        """试点鉴别力柱状图"""
        import plotly.graph_objects as go
        d=edf.sort_values('品种间变异CV(%)',ascending=True)
        # 自动检测环境列名：第一个不是 CV/排名 的字符串列
        if environment is None:
            for c in d.columns:
                if c not in ['环境均值','环境CV(%)','品种间变异CV(%)','品种数','观测数','鉴别力排名']:
                    environment=c; break
            if environment is None:
                environment=d.columns[0]
        fig=go.Figure()
        fig.add_trace(go.Bar(x=d['品种间变异CV(%)'],y=d[environment],orientation='h',
            marker_color=d['品种间变异CV(%)'],marker_colorscale='Viridis',
            text=d['品种间变异CV(%)'].round(2),textposition='outside',
            customdata=d['环境均值'],
            hovertemplate='<b>%{y}</b><br>品种间CV: %{x:.2f}%<br>环境均值: %{customdata:.2f}<extra></extra>'))
        fig.update_layout(title='试点鉴别力比较（品种间CV越大→鉴别力越强）',
            xaxis_title='品种间变异 CV(%)',yaxis_title='',
            height=350+30*len(d),margin=dict(l=10,r=30,t=40,b=30))
        return fig

    @staticmethod
    def geno_mean_cv(df, response, genotype, environment):
        """品种均值-CV：丰产性 vs 稳定性"""
        rows=[]
        for g in sorted(df[genotype].unique()):
            sub=df[df[genotype]==g]
            gm=sub[response].mean()
            em=sub.groupby(environment)[response].mean()
            gc=(em.std()/em.mean()*100) if len(em)>=2 and em.mean()!=0 else 0
            rl=[]
            for env,esub in sub.groupby(environment):
                am=df[df[environment]==env].groupby(genotype)[response].mean()
                rl.append(am.sort_values(ascending=False).index.tolist().index(g)+1)
            rows.append({genotype:g,'丰产性(均值)':round(gm,2),
                         '环境间CV(%)':round(gc,2),
                         '排名波动(SD)':round(np.std(rl),1) if len(rl)>=2 else 0,
                         '平均排名':round(np.mean(rl),1) if rl else 0})
        return pd.DataFrame(rows)

    @staticmethod
    def plot_mean_cv_quadrant(mdf, genotype='品种'):
        """四象限散点图：丰产性 vs 环境间CV"""
        import plotly.graph_objects as go
        d=mdf.copy(); mx=d['丰产性(均值)'].mean(); my=d['环境间CV(%)'].mean()
        cols=[]
        for _,r in d.iterrows():
            if r['丰产性(均值)']>=mx and r['环境间CV(%)']<=my: cols.append('#22c55e')
            elif r['丰产性(均值)']>=mx and r['环境间CV(%)']>my: cols.append('#f59e0b')
            elif r['丰产性(均值)']<mx and r['环境间CV(%)']<=my: cols.append('#94a3b8')
            else: cols.append('#ef4444')
        fig=go.Figure()
        fig.add_trace(go.Scatter(x=d['丰产性(均值)'],y=d['环境间CV(%)'],mode='markers+text',
            text=d[genotype],textposition='top center',
            marker=dict(size=12,color=cols,line=dict(width=1,color='#1e293b')),
            hovertemplate='<b>%{text}</b><br>丰产性: %{x:.2f}<br>CV: %{y:.2f}%<extra></extra>'))
        fig.add_hline(y=my,line_dash='dash',line_color='gray',opacity=0.5)
        fig.add_vline(x=mx,line_dash='dash',line_color='gray',opacity=0.5)
        ymax=d['环境间CV(%)'].max()*1.1; ymin=d['环境间CV(%)'].min()*0.9
        fig.update_layout(title='品种丰产性与稳定性四象限图',
            xaxis_title='丰产性（均值）',yaxis_title='不稳定性（环境间CV%）',height=500,
            annotations=[
                dict(x=mx,y=ymax,text='高产敏感↗',showarrow=False,font=dict(size=11,color='#f59e0b')),
                dict(x=mx,y=ymin,text='高产稳定↗',showarrow=False,font=dict(size=11,color='#22c55e')),
                dict(x=mx*0.95,y=ymax,text='低产敏感',showarrow=False,font=dict(size=11,color='#ef4444')),
                dict(x=mx*0.95,y=ymin,text='低产稳定',showarrow=False,font=dict(size=11,color='#94a3b8'))])
        return fig

    @staticmethod
    def interaction_effects(df, response, genotype, environment):
        """品种-试点互作效应矩阵"""
        mt=df.pivot_table(index=genotype,columns=environment,values=response,aggfunc='mean')
        gm=np.mean(mt.values); gm_g=np.mean(mt.values,axis=1); gm_e=np.mean(mt.values,axis=0)
        rows=[]
        for i,g in enumerate(mt.index):
            for j,e in enumerate(mt.columns):
                eff=mt.values[i,j]-gm_g[i]-gm_e[j]+gm
                rows.append({genotype:g,environment:e,'互作效应':round(eff,4),'观测均值':round(mt.values[i,j],2)})
        return pd.DataFrame(rows)

    @staticmethod
    def plot_interaction_heatmap(idf, genotype='品种', environment='环境'):
        """互作效应热力图"""
        import plotly.graph_objects as go
        pt=idf.pivot_table(index=genotype,columns=environment,values='互作效应',aggfunc='mean')
        fig=go.Figure(data=go.Heatmap(z=pt.values,x=list(pt.columns),y=list(pt.index),
            colorscale='RdBu_r',zmid=0,text=np.round(pt.values,2),texttemplate='%{text}',
            hovertemplate='品种: %{y}<br>环境: %{x}<br>效应: %{z:.4f}<extra></extra>'))
        fig.update_layout(title='品种×试点互作效应',xaxis_title=environment,
            yaxis_title=genotype,height=400+20*len(pt.index))
        return fig

    # ── 以下为 QYSY 系列可视化增强 ──

    @staticmethod
    def plot_variety_mean_heatmap(df, response, genotype, environment):
        """品种均值热图（QYSY AAPZJZRSDTController → 品种均值热散点图）

        以品种×地点矩阵形式展示各品种在各试点的产量均值，快速识别
        品种在各地点的表现强弱模式。
        """
        import plotly.graph_objects as go
        mt = df.pivot_table(index=genotype, columns=environment,
                            values=response, aggfunc='mean')
        # 按品种总体均值排序
        row_order = mt.mean(axis=1).sort_values(ascending=False).index
        mt = mt.loc[row_order]
        # 按地点均值排序
        col_order = mt.mean(axis=0).sort_values(ascending=False).index
        mt = mt[col_order]

        fig = go.Figure(data=go.Heatmap(
            z=mt.values, x=list(mt.columns), y=list(mt.index),
            colorscale='YlGnBu', text=np.round(mt.values, 1),
            texttemplate='%{text}', textfont=dict(size=9),
            hovertemplate='品种: %{y}<br>试点: %{x}<br>产量均值: %{z:.1f}<extra></extra>'))
        fig.update_layout(
            title='品种×试点产量均值热图（按均值排序）',
            xaxis_title='试点', yaxis_title='品种',
            xaxis=dict(tickangle=-30),
            height=350 + 25 * len(mt.index),
            margin=dict(l=10, r=30, t=50, b=30))
        return fig

    @staticmethod
    def plot_variety_error_bar(df, response, genotype, environment):
        """品种均值误差图（QYSY AAPZJZSFCTController → 品种均值示方差图）

        每个品种显示其产量均值及跨试点的标准差（误差线），
        直观对比品种的丰产性和稳定性。
        """
        import plotly.graph_objects as go
        g_stats = df.groupby(genotype)[response].agg(['mean', 'std', 'count'])
        g_stats = g_stats.sort_values('mean', ascending=False)
        g_stats['se'] = g_stats['std'] / np.sqrt(g_stats['count'])
        g_stats['ci'] = g_stats['se'] * 1.96  # 95% CI

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=g_stats.index, y=g_stats['mean'].round(1),
            error_y=dict(type='data', array=g_stats['ci'].round(1),
                         visible=True, color='#333'),
            marker_color='#2E86AB', marker_line=dict(width=0.5, color='#1a5276'),
            text=g_stats['mean'].round(1), textposition='outside',
            hovertemplate='<b>%{x}</b><br>均值: %{y:.1f}<br>SD: %{customdata:.1f}<br>n=%{text}',
            customdata=g_stats['std'].round(1)))
        fig.update_layout(
            title='品种产量均值与误差（95% CI）',
            xaxis_title='品种', yaxis_title='产量均值',
            xaxis=dict(tickangle=-45),
            height=450,
            margin=dict(l=10, r=30, t=50, b=80))
        return fig

    @staticmethod
    def plot_variety_three_point(df, response, genotype, environment):
        """三点柱状-折线组合图（QYSY AAPZSDJZTController + AAPZSDHZXYTController）

        柱状图展示各品种产量均值（主纵轴），折线叠加品种排名和CV%（次纵轴），
        一次图表展示丰产性、稳定性、排名三个维度。
        """
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        g_stats = df.groupby(genotype)[response].agg(['mean', 'std'])
        overall_mean = df[response].mean()
        g_stats['cv'] = (g_stats['std'] / g_stats['mean'] * 100).round(1)
        g_stats = g_stats.sort_values('mean', ascending=False)
        g_stats['rank'] = range(1, len(g_stats) + 1)

        fig = make_subplots(specs=[[{'secondary_y': True}]])

        # 柱状图 - 产量均值
        fig.add_trace(go.Bar(
            x=g_stats.index, y=g_stats['mean'].round(1),
            name='产量均值', marker_color='#2E86AB',
            hovertemplate='<b>%{x}</b><br>产量: %{y:.1f}<extra></extra>'),
            secondary_y=False)

        # 折线 - 排名（逆序：排名1在顶部）
        fig.add_trace(go.Scatter(
            x=g_stats.index, y=g_stats['rank'],
            name='排名', mode='lines+markers',
            line=dict(color='#E74C3C', width=2),
            marker=dict(size=8, color='#E74C3C'),
            hovertemplate='<b>%{x}</b><br>排名: %{y}<extra></extra>'),
            secondary_y=True)

        # 折线 - CV%
        fig.add_trace(go.Scatter(
            x=g_stats.index, y=g_stats['cv'],
            name='CV%', mode='lines+markers',
            line=dict(color='#27AE60', width=2, dash='dot'),
            marker=dict(size=8, color='#27AE60'),
            hovertemplate='<b>%{x}</b><br>CV: %{y:.1f}%<extra></extra>'),
            secondary_y=True)

        # 总体均值参考线
        fig.add_hline(y=overall_mean, line_dash='dash',
                      line_color='gray', opacity=0.4,
                      annotation_text='总平均',
                      secondary_y=False)

        fig.update_layout(
            title='品种三维评价：产量均值 · 排名 · CV%',
            xaxis_title='品种',
            xaxis=dict(tickangle=-45),
            height=480,
            legend=dict(orientation='h', y=1.08),
            margin=dict(l=10, r=30, t=60, b=80))
        fig.update_yaxes(title_text='产量均值', secondary_y=False)
        fig.update_yaxes(title_text='排名 / CV%', secondary_y=True,
                         tickmode='array',
                         tickvals=list(range(1, len(g_stats) + 1)))
        return fig


# =============================================================================
# 5. Diagnostics — 异常值诊断
# =============================================================================

class Diagnostics:
    """残差分析、正态性检验、Cook距离、杠杆值"""

    @staticmethod
    def residual_analysis(df, response, genotype, environment=None, block=None):
        """ANOVA 残差分析"""
        try:
            sm, ols_fn, anova_lm_fn, _ = _get_statsmodels()
            fml = f'Q("{response}")~C(Q("{genotype}"))'
            if environment: fml += f'+C(Q("{environment}"))'
            if block: fml += f'+C(Q("{block}"))'
            model = ols_fn(fml, data=df).fit()
            res = model.resid; fitted = model.fittedvalues
            n = len(res); std_res = res/np.std(res) if np.std(res)>0 else res
            try:
                inf = model.get_influence()
                cook = inf.cooks_distance[0]; hat = inf.hat_matrix_diag
            except Exception:
                cook = np.zeros(n); hat = np.zeros(n)
            out3 = int((abs(std_res)>3).sum())
            cook_thresh = 4/n; hc = int((cook>cook_thresh).sum())

            rdf = pd.DataFrame({'残差':res,'标准化残差':std_res,'拟合值':fitted,
                '杠杆值':hat,'Cook距离':cook,
                '异常标记':['🚨' if abs(s)>3 else '⚠️' if c>cook_thresh else ''
                           for s,c in zip(std_res,cook)]})

            sw_s, sw_p = scipy_stats.shapiro(res[:min(5000,len(res))])
            jb_s, jb_p = scipy_stats.jarque_bera(res)
            return {'result':rdf,'shapiro_stat':sw_s,'shapiro_p':sw_p,
                    'jb_stat':jb_s,'jb_p':jb_p,'r2':model.rsquared,
                    'n_outliers_3sigma':out3,'n_high_cook':hc,
                    'residuals':res,'fitted':fitted}
        except Exception as e:
            return {'error':str(e)}

    @staticmethod
    def plot_residuals(diag_result):
        """残差分布图（4面板：残差vs拟合值、QQ图、直方图、Cook距离）"""
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
        if 'error' in diag_result:
            fig = go.Figure()
            fig.add_annotation(text=f"诊断失败: {diag_result['error']}",showarrow=False,
                              xref='paper',yref='paper',x=0.5,y=0.5)
            return fig
        res=diag_result['residuals']; fit=diag_result['fitted']; cook=diag_result.get('result',pd.DataFrame())['Cook距离'].values if 'result' in diag_result else np.zeros(len(res))
        fig=make_subplots(rows=2,cols=2,subplot_titles=['残差 vs 拟合值','Q-Q 图','残差直方图','Cook 距离'])

        fig.add_trace(go.Scatter(x=fit,y=res,mode='markers',
            marker=dict(size=6,color='#3b82f6'),name=''),row=1,col=1)
        fig.add_hline(y=0,line_dash='dash',line_color='gray',opacity=0.3)

        # Q-Q
        osm,osr=scipy_stats.probplot(res,dist='norm',plot=None)
        fig.add_trace(go.Scatter(x=osm[0],y=osm[1],mode='markers',
            marker=dict(size=6,color='#3b82f6'),name=''),row=1,col=2)
        # 参考线
        min_x,max_x=min(osm[0]),max(osm[0])
        slope,intercept=np.polyfit(osm[0],osm[1],1)
        fig.add_trace(go.Scatter(x=[min_x,max_x],y=[slope*min_x+intercept,slope*max_x+intercept],
            mode='lines',line=dict(color='red',dash='dash'),name=''),row=1,col=2)

        fig.add_trace(go.Histogram(x=res,marker_color='#3b82f6',nbinsx=20,
            name=''),row=2,col=1)
        fig.add_trace(go.Scatter(x=list(range(len(cook))),y=cook,mode='markers',
            marker=dict(size=6,color='#ef4444'),name=''),row=2,col=2)
        fig.add_hline(y=4/len(cook) if len(cook)>0 else 0,line_dash='dash',line_color='red',opacity=0.5)

        fig.update_layout(height=600,showlegend=False,
            title_text='异常值诊断图')
        return fig


# ──────────────────────────────────────────────
# 第三部分：TrialReportConfig — 审定标准配置
# ──────────────────────────────────────────────

class TrialReportConfig:
    """参照艾格偌 REPORT_AREAS 表的玉米生态区审定标准配置"""

    _json_cache = None

    @staticmethod
    def _load_json_config():
        """从 data/区试报告_审定标准.json 加载扩展字段（plant_info/pip/d_list/all_pip/lt_pip等）"""
        if TrialReportConfig._json_cache is not None:
            return TrialReportConfig._json_cache
        json_path = os.path.join(os.path.dirname(__file__), '..', 'data', '区试报告_审定标准.json')
        json_path = os.path.normpath(json_path)
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                TrialReportConfig._json_cache = json.load(f)
        else:
            TrialReportConfig._json_cache = []
        return TrialReportConfig._json_cache

    ECO_REGIONS = [
        {"id": 1,  "name": "北方极早熟春玉米组",     "ck": "德美亚1号",   "yield_threshold": 5.0, "percent_sites": 60, "title": "北方极早熟春玉米品种区域试验报告"},
        {"id": 2,  "name": "北方早熟春玉米组",       "ck": "德美亚3号",   "yield_threshold": 5.0, "percent_sites": 60, "title": "北方早熟春玉米品种区域试验报告"},
        {"id": 3,  "name": "东华北中熟春玉米组",     "ck": "先玉335",     "yield_threshold": 3.0, "percent_sites": 60, "title": "东华北中熟春玉米品种区域试验报告"},
        {"id": 4,  "name": "东华北中晚熟春玉米组",   "ck": "郑单958",     "yield_threshold": 3.0, "percent_sites": 60, "title": "东华北中晚熟春玉米品种区域试验报告"},
        {"id": 5,  "name": "黄淮海夏玉米组",         "ck": "郑单958",     "yield_threshold": 3.0, "percent_sites": 60, "title": "黄淮海夏玉米品种区域试验报告"},
        {"id": 6,  "name": "西北春玉米组",           "ck": "先玉335",     "yield_threshold": 3.0, "percent_sites": 55, "title": "西北春玉米品种区域试验报告"},
        {"id": 7,  "name": "西南春玉米组",           "ck": "渝单8号",     "yield_threshold": 5.0, "percent_sites": 50, "title": "西南春玉米品种区域试验报告"},
        {"id": 8,  "name": "热带亚热带春玉米组",     "ck": "正大808",     "yield_threshold": 5.0, "percent_sites": 50, "title": "热带亚热带春玉米品种区域试验报告"},
        {"id": 9,  "name": "东南春玉米组",           "ck": "苏玉29",      "yield_threshold": 5.0, "percent_sites": 50, "title": "东南春玉米品种区域试验报告"},
        {"id": 10, "name": "鲜食甜玉米组",           "ck": "粤甜16号",    "yield_threshold": 3.0, "percent_sites": 50, "title": "鲜食甜玉米品种区域试验报告"},
        {"id": 11, "name": "鲜食糯玉米组",           "ck": "京科糯2000",  "yield_threshold": 3.0, "percent_sites": 50, "title": "鲜食糯玉米品种区域试验报告"},
        {"id": 12, "name": "北方极早熟鲜食甜玉米组", "ck": "金甜678",     "yield_threshold": 5.0, "percent_sites": 55, "title": "北方极早熟鲜食甜玉米品种区域试验报告"},
    ]

    @staticmethod
    def get_config(eco_region_id: int) -> dict:
        """根据生态区ID获取审定标准配置（含 JSON 扩展字段）"""
        base = None
        for r in TrialReportConfig.ECO_REGIONS:
            if r["id"] == eco_region_id:
                base = dict(r)
                break
        if base is None:
            base = dict(TrialReportConfig.ECO_REGIONS[0])

        # 从 JSON 补充扩展字段（按 name 前缀匹配）
        json_data = TrialReportConfig._load_json_config()
        name_short = base["name"]
        name_core = name_short.rstrip("组").strip()
        for j in json_data:
            jn = j.get("name", "")
            jn_core = jn.rstrip("组").strip()
            if jn == name_short or jn_core.startswith(name_core) or name_core.startswith(jn_core):
                for k in ("plant_info", "main_title", "pip", "d_list",
                          "all_pip", "lt_pip", "top_d_list", "jf_type"):
                    if k in j:
                        base[k] = j[k]
                break
        return base

    @staticmethod
    def evaluate_promotion(report_data: dict, eco_region_id: int = 1) -> dict:
        """基于审定标准对品种进行晋级/待定/淘汰判定

        Parameters
        ----------
        report_data : dict
            必须包含以下键：
            - 'genotypes' : List[str] 品种列表
            - 'yield_values' : Dict[str, float] 各品种产量均值（kg/亩）
            - 'per_environment' : Dict[str, Dict[str, float]]
              各品种在每个环境（试点）的产量值 {env: {genotype: value}}
            - 'ck_name' : str (可选) 对照品种名，默认使用生态区标准CK
        eco_region_id : int 生态区ID

        Returns
        -------
        dict : {genotype: {yield_diff, diff_percent, judgment, detail}}
        """
        cfg = TrialReportConfig.get_config(eco_region_id)
        ck_name = report_data.get("ck_name", cfg["ck"])
        genotypes = report_data.get("genotypes", [])
        yields = report_data.get("yield_values", {})
        per_env = report_data.get("per_environment", {})

        # 查找CK对应的产量
        ck_yield = yields.get(ck_name, None)
        if ck_yield is None or ck_yield == 0:
            # 在genotypes中找索引
            for i, g in enumerate(genotypes):
                if g == ck_name:
                    break
            else:
                # CK不在列表中，取产量第1的作为虚拟CK
                if yields:
                    ck_name = max(yields, key=lambda k: yields.get(k, 0) or 0)
                    ck_yield = yields.get(ck_name, 0)

        threshold = cfg["yield_threshold"]
        percent_sites = cfg["percent_sites"]

        results = {}
        for g in genotypes:
            gy = yields.get(g, 0)
            if gy is None:
                gy = 0
            if ck_yield and ck_yield > 0:
                diff = gy - ck_yield
                diff_pct = round((diff / ck_yield) * 100, 2)
            else:
                diff = 0
                diff_pct = 0

            # 判断CK达标率（比CK增产的试点比例）
            env_win = 0
            env_total = len(per_env)
            if env_total > 0 and ck_name in yields:
                for env_name, env_data in per_env.items():
                    if not isinstance(env_data, dict):
                        continue
                    gv = env_data.get(g, 0)
                    cv = env_data.get(ck_name, yields.get(ck_name, 0))
                    if gv and cv and gv > cv:
                        env_win += 1

            win_rate = round(env_win / env_total * 100, 1) if env_total > 0 else 0

            # 晋级判定
            if diff_pct >= threshold and win_rate >= percent_sites:
                judgment = "晋级"
            elif diff_pct >= 0 and win_rate >= 50:
                judgment = "待定"
            else:
                judgment = "淘汰"

            detail = f"较{ck_name}增产{diff_pct:+.2f}%, {env_win}/{env_total}试点达标({win_rate:.1f}%)"
            results[g] = {
                "yield_value": gy,
                "yield_diff": round(diff, 2),
                "diff_percent": diff_pct,
                "win_rate": win_rate,
                "judgment": judgment,
                "detail": detail,
            }

        return results

    @staticmethod
    def format_judgment_text(result: dict) -> str:
        """格式化单个品种的判定文本"""
        parts = [
            f"产量: {result.get('yield_value', 0):.1f} kg/亩",
            f"较CK: {result.get('diff_percent', 0):+.2f}%",
            f"达标率: {result.get('win_rate', 0):.1f}%",
            f"判定: {result.get('judgment', '未知')}",
            result.get("detail", ""),
        ]
        return " | ".join(parts)


# ──────────────────────────────────────────────
# 第四部分：ReportExporter — Word 报告导出引擎
# ──────────────────────────────────────────────

class ReportExporter:
    """使用 python-docx 生成专业 Word 格式的区试分析报告
    完整数据架构见 export_to_word 的 report_data 参数文档
    """

    @staticmethod
    def export_to_word(report_data: dict, eco_region_id: int = 1,
                       output_path: str = None,
                       is_production_trial: bool = False) -> str:
        """生成 Word 区试报告

        Parameters
        ----------
        report_data : dict
            包含所有分析结果的结构化字典，支持字段：
            overview, anova, per_env_anova, per_env_yield,
            multiple_comparison, ck_comparison, stability,
            ammi, trial_evaluation, variety_evaluation, judgment
        eco_region_id : int
            生态区ID
        output_path : str
            输出路径，默认自动生成
        is_production_trial : bool
            是否为生产试验报告（True时使用 LTPIP 模板）

        Returns
        -------
        str : 输出文件路径
        """
        from docx import Document
        from docx.shared import Inches, Pt, Cm, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
        from docx.enum.table import WD_TABLE_ALIGNMENT
        from docx.oxml.ns import qn, nsdecls
        from docx.oxml import parse_xml
        import os
        from datetime import datetime

        cfg = TrialReportConfig.get_config(eco_region_id)
        doc = Document()

        # ── 全局样式 ──
        style = doc.styles['Normal']
        style.font.name = '宋体'
        style.font.size = Pt(11)
        style.element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
        pf = style.paragraph_format
        pf.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
        pf.space_after = Pt(3)

        _TABLE_NUM = [0]

        def _sc(cell, color):
            cell._tc.get_or_add_tcPr().append(
                parse_xml(f'<w:shd {nsdecls("w")} w:fill="{color}"/>'))

        def _st(cell, text, bold=False, align=WD_ALIGN_PARAGRAPH.CENTER, size=Pt(10)):
            cell.text = str(text) if text is not None else '-'
            for p in cell.paragraphs:
                p.alignment = align
                for r in p.runs:
                    r.bold = bold; r.font.size = size; r.font.name = '宋体'
                    r.element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')

        def _fv(v, d=2):
            if v is None or v == '' or v == '-': return '-'
            try:
                fv = float(v)
                if fv == int(fv): return str(int(fv))
                return f'{fv:.{d}f}'
            except Exception: return str(v)

        def _add_heading(text, level=1):
            h = doc.add_heading(text, level=level)
            for r in h.runs:
                r.font.color.rgb = RGBColor(0, 51, 102)
                r.font.name = '黑体'
                r.element.rPr.rFonts.set(qn('w:eastAsia'), '黑体')
            h.paragraph_format.space_before = Pt(12)
            h.paragraph_format.space_after = Pt(6)
            return h

        def _add_body(text):
            p = doc.add_paragraph(text)
            for r in p.runs:
                r.font.name = '宋体'; r.font.size = Pt(11)
                r.element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
            p.paragraph_format.first_line_indent = Cm(0.74)
            return p

        def _add_cap(text):
            p = doc.add_paragraph(text)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for r in p.runs:
                r.bold = True; r.font.size = Pt(11); r.font.name = '宋体'
                r.element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
            p.paragraph_format.space_before = Pt(6)
            p.paragraph_format.space_after = Pt(3)

        def _add_table(df, cap='表'):
            if df is None or (hasattr(df, 'empty') and df.empty): return
            if isinstance(df, list):
                if not df: return
                df = pd.DataFrame(df)
                if df.empty: return
            _TABLE_NUM[0] += 1; tn = _TABLE_NUM[0]
            headers = [str(c) for c in df.columns]
            rows_data = df.values.tolist()
            _add_cap(f'表{tn} {cap}')
            table = doc.add_table(rows=1+len(rows_data), cols=len(headers))
            table.style = 'Table Grid'
            table.alignment = WD_TABLE_ALIGNMENT.CENTER
            table.autofit = True
            for ci, h in enumerate(headers):
                cell = table.rows[0].cells[ci]
                _st(cell, h, bold=True)
                _sc(cell, '1F4E79')
                for p in cell.paragraphs:
                    for r in p.runs:
                        r.font.color.rgb = RGBColor(255,255,255)
            for ri, row in enumerate(rows_data):
                for ci, val in enumerate(row):
                    _st(table.rows[ri+1].cells[ci], _fv(val))
                if ri % 2 == 1:
                    for ci in range(len(headers)):
                        _sc(table.rows[ri+1].cells[ci], 'F2F7FB')
            doc.add_paragraph('')

        # =====================================================================
        # 封面
        # =====================================================================
        for _ in range(6): doc.add_paragraph('')
        tp = doc.add_paragraph()
        tp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        title_text = cfg.get("lt_title", cfg["title"])
        if is_production_trial and "区域试验" in title_text:
            title_text = title_text.replace("区域试验", "生产试验")
        r = tp.add_run(title_text)
        r.font.size = Pt(22); r.bold = True
        r.font.color.rgb = RGBColor(0, 51, 102)
        r.font.name = '黑体'; r.element.rPr.rFonts.set(qn('w:eastAsia'), '黑体')
        doc.add_paragraph('')
        sp = doc.add_paragraph()
        sp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = sp.add_run(f"生态区: {cfg['name']}")
        r.font.size = Pt(14); r.font.color.rgb = RGBColor(80,80,80)
        doc.add_paragraph('')
        ip = doc.add_paragraph()
        ip.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = ip.add_run(f"对照品种: {cfg['ck']}  |  增产阈值: ≥{cfg['yield_threshold']}%  |  达标试点: ≥{cfg['percent_sites']}%")
        r.font.size = Pt(12); r.font.color.rgb = RGBColor(100,100,100)
        doc.add_paragraph('')
        dp = doc.add_paragraph()
        dp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = dp.add_run(f"生成日期: {datetime.now().strftime('%Y年%m月%d日')}")
        r.font.size = Pt(12); r.font.color.rgb = RGBColor(100,100,100)
        doc.add_page_break()

        # =====================================================================
        # 第1章：试验概况
        # =====================================================================
        _add_heading("一、试验概况", level=1)
        ov = report_data.get("overview", {})
        _add_body(f"试验名称：{ov.get('title','区域试验')}")
        _add_body(f"试验年度：{ov.get('year',datetime.now().year)}年")
        _add_body(f"参试品种（系）数：{ov.get('n_genotypes',0)}个")
        _add_body(f"试点数：{ov.get('n_environments',0)}个")
        _add_body(f"重复数：{ov.get('n_replicates',0)}次")
        _add_body(f"对照品种：{cfg['ck']}")
        _add_body(f"增产判定阈值：较CK增产≥{cfg['yield_threshold']}%，达标试点比例≥{cfg['percent_sites']}%")

        # ── 试验目的（来自 REPORT_AREAS main_title） ──
        if cfg.get("main_title"):
            mt = cfg["main_title"].replace("YYYY年", f"{ov.get('year',datetime.now().year)}年")
            _add_body(mt)

        # ── 试验方案（来自 REPORT_AREAS plant_info） ──
        if cfg.get("plant_info"):
            pi = cfg["plant_info"].format(cfg.get("border_rows", 4))
            pi = pi.replace("CKNAME", cfg['ck'])
            _add_body(pi)

        # =====================================================================
        # 第2章：联合方差分析
        # =====================================================================
        anova = report_data.get("anova", {})
        if anova:
            _add_heading("二、联合方差分析", level=1)
            anova_df = anova.get("anova_table", pd.DataFrame())
            if not anova_df.empty:
                _add_table(anova_df, cap='联合方差分析表')
            gm = anova.get("grand_mean")
            cv = anova.get("cv")
            if gm is not None: _add_body(f"总平均：{_fv(gm)}")
            if cv is not None: _add_body(f"变异系数 (CV)：{_fv(cv)}%")

        # ── 各试点单点方差分析 ──
        pe_an = report_data.get("per_env_anova", {})
        ch_num = 2
        if pe_an:
            ch_num += 1
            _add_heading("三、各试点方差分析", level=1)
            for en, edf in pe_an.items():
                if isinstance(edf, pd.DataFrame) and not edf.empty:
                    _add_table(edf, cap=f'{en} 方差分析表')

        # =====================================================================
        # 各试点产量汇总
        # =====================================================================
        pe_y = report_data.get("per_env_yield", {})
        if pe_y:
            ch_num += 1
            ch_map = {3:'三',4:'四',5:'五',6:'六',7:'七',8:'八',9:'九',10:'十'}
            _add_heading(f"{ch_map.get(ch_num,str(ch_num))}、各试点产量汇总", level=1)
            for en in sorted(pe_y.keys()):
                edf = pe_y[en]
                if isinstance(edf, pd.DataFrame) and not edf.empty:
                    _add_table(edf, cap=f'{en} 产量与排名')

        # =====================================================================
        # 多重比较
        # =====================================================================
        mc = report_data.get("multiple_comparison", {})
        if mc:
            ch_num += 1
            ch_map = {3:'三',4:'四',5:'五',6:'六',7:'七',8:'八',9:'九',10:'十',11:'十一'}
            _add_heading(f"{ch_map.get(ch_num,str(ch_num))}、品种多重比较", level=1)
            _add_body(f"多重比较方法：{mc.get('method','Duncan')}")
            mse = mc.get("mse"); dfe = mc.get("dfe")
            if mse: _add_body(f"误差均方 (MSE)：{_fv(mse)}  误差自由度 (dfe)：{dfe}")
            cld_df = mc.get("cld_table", pd.DataFrame())
            if not cld_df.empty:
                _add_table(cld_df, cap='多重比较结果及字母标记（CLD）')
            pairs_df = mc.get("pairs", pd.DataFrame())
            if not pairs_df.empty:
                _add_table(pairs_df, cap='品种两两比较详情')

        # =====================================================================
        # 对照品种比较
        # =====================================================================
        ck = report_data.get("ck_comparison", {})
        if ck:
            ch_num += 1
            ch_map = {3:'三',4:'四',5:'五',6:'六',7:'七',8:'八',9:'九',10:'十',11:'十一',12:'十二'}
            _add_heading(f"{ch_map.get(ch_num,str(ch_num))}、对照品种比较", level=1)
            ck_name = ck.get("ck_name", cfg['ck'])
            _add_body(f"对照品种：{ck_name}")
            ck_rk = ck.get("ck_rank", {})
            if ck_rk and isinstance(ck_rk, dict):
                _add_body(f"对照排名：第 {ck_rk.get('ck_rank','?')} / {ck_rk.get('total_genotypes','?')} 位"
                          f"（百分位：{_fv(ck_rk.get('percentile',0))}%）")
            ck_res = ck.get("ck_result", pd.DataFrame())
            if not ck_res.empty:
                _add_table(ck_res, cap='与对照品种比较结果')

        # =====================================================================
        # 品种稳定性分析
        # =====================================================================
        stab = report_data.get("stability", {})
        if stab:
            ch_num += 1
            ch_map = {3:'三',4:'四',5:'五',6:'六',7:'七',8:'八',9:'九',10:'十',11:'十一',12:'十二',13:'十三'}
            _add_heading(f"{ch_map.get(ch_num,str(ch_num))}、品种稳定性分析", level=1)
            shk = stab.get("shukla", pd.DataFrame())
            if not shk.empty:
                _add_table(shk, cap='Shukla 稳定性方差（值越大越不稳定）')
            er = stab.get("eberhart_russell", pd.DataFrame())
            if not er.empty:
                _add_table(er, cap='Eberhart-Russell 回归（b≈1且离回归方差小→稳定）')
            cmb = stab.get("comprehensive", pd.DataFrame())
            if not cmb.empty:
                _add_table(cmb, cap='品种综合稳定性评价')

        # =====================================================================
        # AMMI 分析
        # =====================================================================
        ammi = report_data.get("ammi", {})
        if ammi:
            ch_num += 1
            ch_map = {3:'三',4:'四',5:'五',6:'六',7:'七',8:'八',9:'九',10:'十',11:'十一',12:'十二',13:'十三',14:'十四'}
            _add_heading(f"{ch_map.get(ch_num,str(ch_num))}、品种-环境互作（AMMI）分析", level=1)
            ipc = ammi.get("ipc_table", pd.DataFrame())
            if not ipc.empty:
                _add_table(ipc, cap='AMMI 主成分分析（IPC）')
            _add_body(f"前2个IPC累积解释互作变异：{_fv(ammi.get('cum_var',0))}%")
            aa = ammi.get("anova", pd.DataFrame())
            if not aa.empty:
                _add_table(aa, cap='AMMI 方差分析')

        # =====================================================================
        # 试点评价
        # =====================================================================
        te = report_data.get("trial_evaluation", {})
        if te:
            ch_num += 1
            ch_map = {3:'三',4:'四',5:'五',6:'六',7:'七',8:'八',9:'九',10:'十',11:'十一',12:'十二',13:'十三',14:'十四',15:'十五'}
            _add_heading(f"{ch_map.get(ch_num,str(ch_num))}、试点与品种评价", level=1)
            env_df = te.get("env_discriminability", pd.DataFrame())
            if not env_df.empty:
                _add_table(env_df, cap='试点鉴别力（品种间CV越大→鉴别力越强）')
            gn_df = te.get("geno_mean_cv", pd.DataFrame())
            if not gn_df.empty:
                _add_table(gn_df, cap='品种丰产性与稳定性指标')

        # =====================================================================
        # 品种综合评价
        # =====================================================================
        ve = report_data.get("variety_evaluation", [])
        if ve:
            ch_num += 1
            ch_map = {3:'三',4:'四',5:'五',6:'六',7:'七',8:'八',9:'九',10:'十',11:'十一',12:'十二',13:'十三',14:'十四',15:'十五',16:'十六'}
            _add_heading(f"{ch_map.get(ch_num,str(ch_num))}、品种综合评价", level=1)
            if isinstance(ve, list) and ve:
                vdf = pd.DataFrame(ve)
                if not vdf.empty:
                    _add_table(vdf, cap='品种综合评价排序')

        # =====================================================================
        # 品种审定判定
        # =====================================================================
        jg = report_data.get("judgment", {})
        if jg:
            ch_num += 1
            ch_map = {3:'三',4:'四',5:'五',6:'六',7:'七',8:'八',9:'九',10:'十',11:'十一',12:'十二',13:'十三',14:'十四',15:'十五',16:'十六',17:'十七'}
            _add_heading(f"{ch_map.get(ch_num,str(ch_num))}、品种审定判定", level=1)
            _add_body(f"审定标准：较对照（{cfg['ck']}）增产≥{cfg['yield_threshold']}%，"
                      f"且达标试点比例≥{cfg['percent_sites']}%")

            # ── 审定标准全文（区域试验用 pip，生产试验用 lt_pip） ──
            if is_production_trial and cfg.get("lt_pip"):
                _add_body(f"处理意见：{cfg['lt_pip']}")
            elif cfg.get("pip"):
                _add_body(f"判定依据：{cfg['pip']}")
            elif cfg.get("all_pip"):
                _add_body(f"判定依据：{cfg['all_pip']}")
            jrows = []
            for g, info in jg.items():
                if isinstance(info, dict):
                    jrows.append({'品种':g,'产量(kg/亩)':info.get('yield_value',0),
                                  '较CK增产(%)':info.get('diff_percent',0),
                                  '增产(kg/亩)':info.get('yield_diff',0),
                                  '达标率(%)':info.get('win_rate',0),
                                  '判定':info.get('judgment','')})
            if jrows:
                _add_table(pd.DataFrame(jrows), cap='品种审定判定结果')
                promoted = [g for g,v in jg.items() if isinstance(v,dict) and v.get('judgment')=='晋级']
                pending = [g for g,v in jg.items() if isinstance(v,dict) and v.get('judgment')=='待定']
                eliminated = [g for g,v in jg.items() if isinstance(v,dict) and v.get('judgment')=='淘汰']
                _add_body(f"推荐晋级：{len(promoted)}个 — {'、'.join(promoted) if promoted else '无'}")
                _add_body(f"待定：{len(pending)}个 — {'、'.join(pending) if pending else '无'}")
                _add_body(f"淘汰：{len(eliminated)}个 — {'、'.join(eliminated) if eliminated else '无'}")

        # =====================================================================
        # 生产试验处理意见（仅生产试验报告时输出）
        # =====================================================================
        if is_production_trial and jg:
            ch_num += 1
            ch_map = {3:'三',4:'四',5:'五',6:'六',7:'七',8:'八',9:'九',10:'十',11:'十一',12:'十二',13:'十三',14:'十四',15:'十五',16:'十六',17:'十七',18:'十八'}
            _add_heading(f"{ch_map.get(ch_num,str(ch_num))}、生产试验处理意见", level=1)
            if cfg.get("lt_pip"):
                _add_body(cfg["lt_pip"])
            promoted = [g for g,v in jg.items() if isinstance(v,dict) and v.get('judgment')=='晋级']
            pending = [g for g,v in jg.items() if isinstance(v,dict) and v.get('judgment')=='待定']
            eliminated = [g for g,v in jg.items() if isinstance(v,dict) and v.get('judgment')=='淘汰']
            _add_body(f"推荐晋级：{len(promoted)}个 — {'、'.join(promoted) if promoted else '无'}")
            _add_body(f"继续试验（待定）：{len(pending)}个 — {'、'.join(pending) if pending else '无'}")
            if eliminated:
                _add_body(f"建议终止试验：{len(eliminated)}个 — {'、'.join(eliminated)}")
            else:
                _add_body("本次参试品种均达到生产试验阶段标准，建议按程序报审。")

        # =====================================================================
        # 结论
        # =====================================================================
        if jg:
            ch_num += 1
            ch_map = {3:'三',4:'四',5:'五',6:'六',7:'七',8:'八',9:'九',10:'十',11:'十一',12:'十二',13:'十三',14:'十四',15:'十五',16:'十六',17:'十七',18:'十八'}
            _add_heading(f"{ch_map.get(ch_num,str(ch_num))}、结论", level=1)
            n_g = ov.get('n_genotypes',0); n_e = ov.get('n_environments',0); n_r = ov.get('n_replicates',0)
            _add_body(f"本年度区域试验参试品种共{n_g}个，试点{n_e}个，重复{n_r}次。"
                      f"根据国家品种审定标准，综合产量表现、稳定性及各试点结果，做出如下判定：")
            promoted = [g for g,v in jg.items() if isinstance(v,dict) and v.get('judgment')=='晋级']
            pending = [g for g,v in jg.items() if isinstance(v,dict) and v.get('judgment')=='待定']
            eliminated = [g for g,v in jg.items() if isinstance(v,dict) and v.get('judgment')=='淘汰']
            if promoted: _add_body(f"推荐晋级品种（{len(promoted)}个）：{'、'.join(promoted)}")
            if pending: _add_body(f"待定品种（{len(pending)}个）：{'、'.join(pending)}")
            if eliminated: _add_body(f"淘汰品种（{len(eliminated)}个）：{'、'.join(eliminated)}")
            if promoted:
                _add_body("建议上述晋级品种按程序提交品种审定委员会审定。")
            if pending:
                _add_body("待定品种建议下一年度继续试验，进一步观察其表现。")

        # 保存
        if output_path is None:
            import tempfile
            prefix = "生产试验报告" if is_production_trial else "区试报告"
            fname = f"{prefix}_{cfg['name']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
            output_path = os.path.join(tempfile.gettempdir(), fname)
        doc.save(output_path)
        return output_path

    @staticmethod
    def export_to_excel(report_data: dict, eco_region_id: int = 1,
                        output_path: str = None,
                        is_production_trial: bool = False) -> str:
        """生成 Excel 版区试报告，与 export_to_word 共用同一份 report_data 结构。

        Parameters
        ----------
        report_data, eco_region_id : 同 export_to_word
        output_path : 输出路径，默认自动生成
        is_production_trial : 是否为生产试验报告

        Returns
        -------
        str : 输出文件路径
        """
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, numbers
        from openpyxl.utils import get_column_letter
        import os, json
        from datetime import datetime

        cfg = TrialReportConfig.get_config(eco_region_id)
        wb = Workbook()

        # ── 样式常量 ──
        TITLE_FONT = Font(name='Arial', size=18, bold=True, color='003366')
        SUB_FONT = Font(name='Arial', size=12, bold=True, color='333333')
        BODY_FONT = Font(name='Arial', size=10, color='000000')
        HEADER_FONT = Font(name='Arial', size=10, bold=True, color='FFFFFF')
        HEADER_FILL = PatternFill('solid', fgColor='1F4E79')
        ALT_FILL = PatternFill('solid', fgColor='F2F7FB')
        THIN_BORDER = Border(
            left=Side(style='thin'), right=Side(style='thin'),
            top=Side(style='thin'), bottom=Side(style='thin'))
        CENTER = Alignment(horizontal='center', vertical='center', wrap_text=True)
        LEFT_WRAP = Alignment(horizontal='left', vertical='top', wrap_text=True)

        def _sht(name):
            """创建或获取sheet，设置默认列宽"""
            if name in wb.sheetnames:
                ws = wb[name]
            else:
                ws = wb.create_sheet(name)
            ws.column_dimensions['A'].width = 5
            ws.column_dimensions['B'].width = 22
            ws.column_dimensions['C'].width = 16
            ws.column_dimensions['D'].width = 16
            ws.column_dimensions['E'].width = 16
            ws.column_dimensions['F'].width = 16
            ws.column_dimensions['G'].width = 16
            ws.column_dimensions['H'].width = 16
            return ws

        def _fw(ws, row, col, val, font=BODY_FONT, fill=None, align=CENTER, border=THIN_BORDER, num_fmt=None):
            c = ws.cell(row=row, column=col, value=_fmt(val))
            c.font = font; c.alignment = align; c.border = border
            if fill: c.fill = fill
            if num_fmt: c.number_format = num_fmt

        def _fmt(v):
            if v is None or v == '' or v == '-': return '-'
            try:
                fv = float(v)
                if fv == int(fv) and abs(fv) < 1e10: return int(fv)
                return round(fv, 2)
            except Exception: return v

        def _fill_table(ws, start_row, df, cap=''):
            """写入DataFrame到工作表，返回写入后的行号"""
            if df is None or (hasattr(df, 'empty') and df.empty):
                return start_row
            if isinstance(df, list):
                if not df: return start_row
                df = pd.DataFrame(df)
                if df.empty: return start_row
            headers = [str(c) for c in df.columns]
            rows_data = df.values.tolist()
            # 表头
            for ci, h in enumerate(headers):
                _fw(ws, start_row, ci + 1, h, font=HEADER_FONT, fill=HEADER_FILL)
            # 数据行
            for ri, row in enumerate(rows_data):
                fill = ALT_FILL if ri % 2 == 1 else None
                for ci, val in enumerate(row):
                    _fw(ws, start_row + 1 + ri, ci + 1, val, fill=fill)
            # 自动调整列宽
            for ci in range(len(headers)):
                col_letter = get_column_letter(ci + 1)
                max_len = len(headers[ci])
                for ri in range(len(rows_data)):
                    cell_val = str(rows_data[ri][ci]) if rows_data[ri][ci] is not None else ''
                    # 中文字符按2倍宽度算
                    slen = sum(2 if ord(c) > 127 else 1 for c in cell_val)
                    if slen > max_len: max_len = slen
                ws.column_dimensions[col_letter].width = min(max(max_len + 2, 10), 40)
            return start_row + 1 + len(rows_data)

        # =====================================================================
        # Sheet 1: 封面
        # =====================================================================
        ws_cover = wb.active
        ws_cover.title = '封面'
        for _ in range(3):
            ws_cover.merge_cells(start_row=1, start_column=1, end_row=1, end_column=6)
        title_text = cfg.get('title', '区域试验报告')
        if is_production_trial and '区域试验' in title_text:
            title_text = title_text.replace('区域试验', '生产试验')
        ws_cover['A1'] = title_text
        ws_cover['A1'].font = TITLE_FONT
        ws_cover['A1'].alignment = CENTER

        row = 3
        infos = [
            ('生态区', cfg['name']), ('对照品种', cfg['ck']),
            ('增产阈值', f"≥{cfg['yield_threshold']}%"),
            ('达标试点比例', f"≥{cfg['percent_sites']}%"),
            ('生成日期', datetime.now().strftime('%Y年%m月%d日')),
        ]
        for label, val in infos:
            ws_cover.cell(row=row, column=2, value=label).font = SUB_FONT
            ws_cover.cell(row=row, column=4, value=val).font = BODY_FONT
            row += 1

        ov = report_data.get("overview", {})
        row += 1
        ov_infos = [
            ('试验名称', ov.get('title', '区域试验')),
            ('试验年度', f"{ov.get('year', datetime.now().year)}年"),
            ('参试品种数', str(ov.get('n_genotypes', 0))),
            ('试点数', str(ov.get('n_environments', 0))),
            ('重复数', str(ov.get('n_replicates', 0))),
        ]
        for label, val in ov_infos:
            ws_cover.cell(row=row, column=2, value=label).font = SUB_FONT
            ws_cover.cell(row=row, column=4, value=val).font = BODY_FONT
            row += 1

        # ── 试验目的（来自 REPORT_AREAS main_title） ──
        if cfg.get("main_title"):
            row += 1
            ws_cover.cell(row=row, column=2, value='试验目的').font = SUB_FONT
            mt = cfg["main_title"].replace("YYYY年", f"{ov.get('year',datetime.now().year)}年")
            ws_cover.cell(row=row, column=4, value=mt).font = BODY_FONT

        # ── 试验方案（来自 REPORT_AREAS plant_info） ──
        if cfg.get("plant_info"):
            row += 1
            ws_cover.cell(row=row, column=2, value='试验方案').font = SUB_FONT
            pi = cfg["plant_info"].format(cfg.get("border_rows", 4))
            pi = pi.replace("CKNAME", cfg['ck'])
            ws_cover.cell(row=row, column=4, value=pi).font = BODY_FONT

        # =====================================================================
        # Sheet 2: 联合方差分析
        # =====================================================================
        anova = report_data.get("anova", {})
        if anova:
            ws = _sht('联合方差分析')
            r = 1
            anova_df = anova.get("anova_table", pd.DataFrame())
            r = _fill_table(ws, r, anova_df, '联合方差分析表')
            gm = anova.get("grand_mean")
            cv = anova.get("cv")
            if gm is not None: ws.cell(row=r+1, column=1, value=f'总平均: {_fmt(gm)}').font = BODY_FONT
            if cv is not None: ws.cell(row=r+2, column=1, value=f'变异系数(CV): {_fmt(cv)}%').font = BODY_FONT

        # =====================================================================
        # Sheet 3: 各试点方差分析
        # =====================================================================
        pe_an = report_data.get("per_env_anova", {})
        if pe_an:
            ws = _sht('各试点方差分析')
            r = 1
            for en, edf in pe_an.items():
                if isinstance(edf, pd.DataFrame) and not edf.empty:
                    ws.cell(row=r, column=1, value=f'— {en} —').font = SUB_FONT; r += 1
                    r = _fill_table(ws, r, edf)
                    r += 1

        # =====================================================================
        # Sheet 4: 各试点产量汇总
        # =====================================================================
        pe_y = report_data.get("per_env_yield", {})
        if pe_y:
            ws = _sht('各试点产量汇总')
            r = 1
            for en in sorted(pe_y.keys()):
                edf = pe_y[en]
                if isinstance(edf, pd.DataFrame) and not edf.empty:
                    ws.cell(row=r, column=1, value=f'— {en} —').font = SUB_FONT; r += 1
                    r = _fill_table(ws, r, edf)
                    r += 1

        # =====================================================================
        # Sheet 5: 多重比较
        # =====================================================================
        mc = report_data.get("multiple_comparison", {})
        if mc:
            ws = _sht('多重比较')
            ws.cell(row=1, column=1, value=f"方法: {mc.get('method','Duncan')}").font = SUB_FONT
            mse_v = mc.get('mse'); dfe_v = mc.get('dfe')
            if mse_v: ws.cell(row=2, column=1, value=f'MSE: {_fmt(mse_v)}  df_e: {dfe_v}').font = BODY_FONT
            r = 3
            cld_df = mc.get("cld_table", pd.DataFrame())
            r = _fill_table(ws, r, cld_df)
            r += 1
            pairs_df = mc.get("pairs", pd.DataFrame())
            _fill_table(ws, r, pairs_df)

        # =====================================================================
        # Sheet 6: 对照比较
        # =====================================================================
        ck = report_data.get("ck_comparison", {})
        if ck:
            ws = _sht('对照比较')
            ck_name = ck.get("ck_name", cfg['ck'])
            ws.cell(row=1, column=1, value=f'对照品种: {ck_name}').font = SUB_FONT
            r = 2
            ck_rk = ck.get("ck_rank", {})
            if ck_rk and isinstance(ck_rk, dict):
                ws.cell(row=r, column=1, value=f"对照排名: 第{ck_rk.get('ck_rank','?')} / {ck_rk.get('total_genotypes','?')} 位 (百分位: {_fmt(ck_rk.get('percentile',0))}%)").font = BODY_FONT
                r += 2
            ck_res = ck.get("ck_result", pd.DataFrame())
            _fill_table(ws, r, ck_res)

        # =====================================================================
        # Sheet 7: 稳定性
        # =====================================================================
        stab = report_data.get("stability", {})
        if stab:
            ws = _sht('稳定性分析')
            r = 1
            shk = stab.get("shukla", pd.DataFrame())
            r = _fill_table(ws, r, shk) + 1
            er = stab.get("eberhart_russell", pd.DataFrame())
            r = _fill_table(ws, r, er) + 1
            cmb = stab.get("comprehensive", pd.DataFrame())
            _fill_table(ws, r, cmb)

        # =====================================================================
        # Sheet 8: AMMI
        # =====================================================================
        ammi = report_data.get("ammi", {})
        if ammi:
            ws = _sht('AMMI分析')
            r = 1
            ipc = ammi.get("ipc_table", pd.DataFrame())
            r = _fill_table(ws, r, ipc) + 1
            ws.cell(row=r, column=1, value=f"IPC1+IPC2累积贡献: {_fmt(ammi.get('cum_var',0))}%").font = BODY_FONT
            r += 2
            aa = ammi.get("anova", pd.DataFrame())
            _fill_table(ws, r, aa)

        # =====================================================================
        # Sheet 9: 试点评价
        # =====================================================================
        te = report_data.get("trial_evaluation", {})
        if te:
            ws = _sht('试点评价')
            r = 1
            env_df = te.get("env_discriminability", pd.DataFrame())
            r = _fill_table(ws, r, env_df) + 1
            gn_df = te.get("geno_mean_cv", pd.DataFrame())
            _fill_table(ws, r, gn_df)

        # =====================================================================
        # Sheet 10: 品种评价
        # =====================================================================
        ve = report_data.get("variety_evaluation", [])
        if ve:
            ws = _sht('品种评价')
            if isinstance(ve, list) and ve:
                vdf = pd.DataFrame(ve)
                _fill_table(ws, 1, vdf)

        # =====================================================================
        # Sheet 11: 审定判定
        # =====================================================================
        jg = report_data.get("judgment", {})
        if jg:
            ws = _sht('审定判定')
            ws.cell(row=1, column=1, value=f"审定标准: 较CK({cfg['ck']})增产≥{cfg['yield_threshold']}%, 达标试点≥{cfg['percent_sites']}%").font = SUB_FONT
            if is_production_trial and cfg.get("lt_pip"):
                ws.cell(row=2, column=1, value=f"处理意见: {cfg['lt_pip']}").font = BODY_FONT
            elif cfg.get("pip"):
                ws.cell(row=2, column=1, value=f"判定依据: {cfg['pip']}").font = BODY_FONT
            jrows = []
            for g, info in jg.items():
                if isinstance(info, dict):
                    jrows.append({'品种': g, '产量(kg/亩)': info.get('yield_value', 0),
                                  '较CK增产(%)': info.get('diff_percent', 0),
                                  '增产(kg/亩)': info.get('yield_diff', 0),
                                  '达标率(%)': info.get('win_rate', 0),
                                  '判定': info.get('judgment', '')})
            if jrows:
                _fill_table(ws, 3, pd.DataFrame(jrows))
                r = 4 + len(jrows)
                promoted = [g for g, v in jg.items() if isinstance(v, dict) and v.get('judgment') == '晋级']
                pending = [g for g, v in jg.items() if isinstance(v, dict) and v.get('judgment') == '待定']
                eliminated = [g for g, v in jg.items() if isinstance(v, dict) and v.get('judgment') == '淘汰']
                ws.cell(row=r+1, column=1, value=f"推荐晋级: {len(promoted)}个 — {'、'.join(promoted) if promoted else '无'}").font = BODY_FONT
                ws.cell(row=r+2, column=1, value=f"待定: {len(pending)}个 — {'、'.join(pending) if pending else '无'}").font = BODY_FONT
                ws.cell(row=r+3, column=1, value=f"淘汰: {len(eliminated)}个 — {'、'.join(eliminated) if eliminated else '无'}").font = BODY_FONT

        # 删除默认的空Sheet（openpyxl默认创建了'Sheet'）
        if 'Sheet' in wb.sheetnames:
            del wb['Sheet']

        if output_path is None:
            import tempfile
            prefix = "生产试验报告" if is_production_trial else "区试报告"
            fname = f"{prefix}_{cfg['name']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            output_path = os.path.join(tempfile.gettempdir(), fname)
        wb.save(output_path)
        return output_path


# ──────────────────────────────────────────────
# 第五部分：ReportManager — 报告持久化管理
# ──────────────────────────────────────────────

class ReportManager:
    """报告配置持久化与历史管理
    
    存储路径: {StatTools数据目录}/reports/
    每个报告保存: 配置JSON + 生成的Word文件路径
    """

    @staticmethod
    def _get_reports_dir() -> str:
        """获取报告存储目录"""
        import json
        rd = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "reports")
        os.makedirs(rd, exist_ok=True)
        return rd

    @staticmethod
    def _get_index_path() -> str:
        return os.path.join(ReportManager._get_reports_dir(), "index.json")

    @staticmethod
    def save_report(eco_region_id: int, ck_name: str, docx_path: str,
                    config: dict = None) -> dict:
        """保存一条报告记录
        
        Returns
        -------
        dict : 保存的记录
        """
        import json
        from datetime import datetime

        idx_path = ReportManager._get_index_path()
        records = []
        if os.path.exists(idx_path):
            try:
                with open(idx_path, 'r', encoding='utf-8') as f:
                    records = json.load(f)
            except Exception:
                records = []

        eco_cfg = TrialReportConfig.get_config(eco_region_id)
        record = {
            "id": len(records) + 1,
            "eco_region_id": eco_region_id,
            "eco_region_name": eco_cfg["name"],
            "ck_name": ck_name,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "docx_path": docx_path,
            "docx_name": os.path.basename(docx_path) if docx_path else "",
            "config": config or {},
        }
        records.append(record)
        with open(idx_path, 'w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        return record

    @staticmethod
    def list_reports(limit: int = 20) -> list:
        """获取报告历史列表（新→旧）"""
        import json
        idx_path = ReportManager._get_index_path()
        if not os.path.exists(idx_path):
            return []
        try:
            with open(idx_path, 'r', encoding='utf-8') as f:
                records = json.load(f)
            return list(reversed(records))[:limit]
        except Exception:
            return []

    @staticmethod
    def delete_report(report_id: int) -> bool:
        """删除报告记录"""
        import json
        idx_path = ReportManager._get_index_path()
        if not os.path.exists(idx_path):
            return False
        try:
            with open(idx_path, 'r', encoding='utf-8') as f:
                records = json.load(f)
            new_records = [r for r in records if r.get("id") != report_id]
            if len(new_records) == len(records):
                return False
            with open(idx_path, 'w', encoding='utf-8') as f:
                json.dump(new_records, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    @staticmethod
    def clear_history() -> bool:
        """清空报告历史"""
        import json
        idx_path = ReportManager._get_index_path()
        with open(idx_path, 'w', encoding='utf-8') as f:
            json.dump([], f)
        return True


# ──────────────────────────────────────────────
# 公开导出接口
# ──────────────────────────────────────────────

__all__ = [
    # 向后兼容（从 ssr_analysis 重导出）
    "SSRMultipleComparison",
    "StabilityAnalysis",
    "CKComparison",
    "SSRReportGenerator",
    "render_cld_bar_chart",
    "plot_stability_scatter",
    "plot_er_regression",
    "render_duncan_cld_chart",
    "rename_anova_index",
    "format_anova_table",

    # 新增
    "BiplotAnalysis",
    "TrialEvaluation",
    "Diagnostics",
    "TrialReportConfig",
    "ReportExporter",
    "ReportManager",
]
