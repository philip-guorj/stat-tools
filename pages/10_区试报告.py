"""
StatTools - 区试报告 (品种区域试验分析)
8Tab: 多重比较、稳定性、对照比较、报告汇总(含审定标准)、
      AMMI/GGE、试点评价、异常值诊断、报告导出
"""

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from utils.data_manager import get_current_dm
from utils.styles import inject_css
from utils.visitor_logger import log_visit
from billing.billing import require_auth, check_billing, can_download
from utils.imports import get_ols as _get_ols, get_anova_lm as _get_anova_lm

_module_loaded = False


def _import_modules():
    global _module_loaded
    if not _module_loaded:
        try:
            from modules.trial_report_analysis import (
                SSRMultipleComparison, StabilityAnalysis,
                CKComparison, SSRReportGenerator,
                BiplotAnalysis, TrialEvaluation, Diagnostics,
                TrialReportConfig, ReportExporter,
                render_duncan_cld_chart, render_cld_bar_chart,
                rename_anova_index, format_anova_table,
                plot_stability_scatter, plot_er_regression,
            )
            for _n in [
                'SSRMultipleComparison', 'StabilityAnalysis', 'CKComparison',
                'SSRReportGenerator', 'BiplotAnalysis', 'TrialEvaluation',
                'Diagnostics', 'TrialReportConfig', 'ReportExporter',
                'render_duncan_cld_chart', 'render_cld_bar_chart',
                'rename_anova_index', 'format_anova_table',
                'plot_stability_scatter', 'plot_er_regression',
            ]:
                globals()[_n] = eval(_n)
            _module_loaded = True
        except ImportError as e:
            st.error(f"❌ modules/trial_report_analysis.py 导入失败: {e}")
            return False
    return _module_loaded


# ─── 辅助函数 ───
def _safe_index(options, candidates, fallback=0):
    if isinstance(candidates, str):
        candidates = [candidates]
    for c in candidates:
        for i, opt in enumerate(options):
            if c.lower() in str(opt).lower():
                return i
    return fallback


def _display_df(df, key="df"):
    st.dataframe(df.style.format(precision=2, na_rep='-'), use_container_width=True, key=key)


# =============================================================================
# Tab 1: 多重比较
# =============================================================================
def _tab_multiple_comparison(df):
    st.markdown("### 📊 多重比较分析")
    st.caption("对品种均值进行两两比较，使用字母标识法（CLD）分组")
    all_num = [c for c in df.select_dtypes(include=[np.number]).columns]
    all_cat = [c for c in df.columns if c not in all_num]

    with st.expander("⚙️ 参数配置", expanded=True):
        a, b, c, d = st.columns(4)
        with a:
            rsp = st.selectbox("响应变量", all_num, index=_safe_index(all_num, ['产量', 'yield', '值'], 0), key="mc_r")
        with b:
            gt = st.selectbox("品种列", all_cat, index=_safe_index(all_cat, ['品种', '基因型', '处理'], 0), key="mc_g")
        with c:
            env = st.selectbox("环境列(可选)", ['(不区分)'] + all_cat, key="mc_env")
        with d:
            blk = st.selectbox("区组列(可选)", ['(不使用)'] + all_cat, key="mc_block")
        e, f, g = st.columns(3)
        with e:
            method = st.selectbox("方法", ["Duncan SSR（新复极差法）", "SNK q检验", "Tukey HSD", "Fisher LSD"])
        with f:
            alpha = st.selectbox("α", [0.01, 0.05, 0.10], index=1)
        with g:
            chart = st.checkbox("显示CLD柱状图", value=True)
        run = st.button("▶ 运行多重比较", type="primary", key="mc_run")
    if not run:
        return

    dfw = df.copy()
    if env != '(不区分)':
        gm = dfw.groupby(gt)[rsp].agg(['mean', 'count']).reset_index()
        gm.columns = [gt, '均值', '重复数']
        try:
            sm_ols = _get_ols()
            anova_lm = _get_anova_lm()
            formula = f'Q("{rsp}") ~ C(Q("{gt}")) + C(Q("{env}"))'
            m = sm_ols(formula, data=dfw).fit()
            at = anova_lm(m, typ=2)
            res = at.loc[at.index.str.lower() == 'residual']
            mse = res['sum_sq'].values[0] / res['df'].values[0] if len(res) > 0 else None
            dfe = int(res['df'].values[0]) if len(res) > 0 else None
        except Exception:
            mse, dfe = None, None
        if mse is None:
            st.error("无法计算误差项"); return
        yv = gm['均值'].values; gv = gm[gt].values
    else:
        if blk != '(不使用)':
            try:
                sm_ols = _get_ols()
                anova_lm = _get_anova_lm()
                m = sm_ols(f'Q("{rsp}") ~ C(Q("{gt}")) + C(Q("{blk}"))', data=dfw).fit()
                at = anova_lm(m, typ=2)
                res = at.loc[at.index.str.lower() == 'residual']
                mse = res['sum_sq'].values[0] / res['df'].values[0] if len(res) > 0 else None
                dfe = int(res['df'].values[0]) if len(res) > 0 else None
            except Exception:
                mse, dfe = None, None
        else:
            mse, dfe = None, None
        yv = dfw[rsp].values; gv = dfw[gt].values

    func = {"Duncan SSR（新复极差法）": SSRMultipleComparison.duncan_test,
            "SNK q检验": SSRMultipleComparison.snk_test,
            "Tukey HSD": SSRMultipleComparison.tukey_test,
            "Fisher LSD": SSRMultipleComparison.lsd_test}.get(method)
    check_billing(f"多重比较-{method.split('（')[0]}", {"method": method, "genotypes": len(set(gv)), "alpha": alpha})

    with st.spinner(f"运行 {method}..."):
        try:
            result = func(yv, gv, mse_val=mse, df_e=dfe, alpha=alpha)
        except Exception as e:
            st.error(f"出错: {e}"); return
    pairs = result['pairs']; n_s = result['names_sorted']; m_s = result['means_sorted']
    mse_o = result.get('mse', mse); dfe_o = result.get('df_e', dfe)
    if len(pairs) == 0:
        st.info("品种数不足"); return
    sig_col = 'reject' if method == "Tukey HSD" else '显著'
    cld = SSRMultipleComparison.compute_cld_letters(n_s, m_s, pairs, g1_col=pairs.columns[0], g2_col=pairs.columns[1], sig_col=sig_col)
    cld_t = SSRMultipleComparison.generate_cld_table(n_s, m_s, cld)
    st.success(f"✅ {method} 完成 (MSE={mse_o:.2f}, df_e={dfe_o})")
    x, y = st.columns(2)
    with x:
        st.subheader("两两比较"); _display_df(pairs, key="mc_p")
    with y:
        st.subheader("CLD字母"); _display_df(cld_t, key="mc_cld")
    if can_download():
        st.download_button("📥 配对表", pairs.to_csv(index=False).encode('utf-8-sig'), f"多重比较_{method.split('（')[0]}.csv", "text/csv")
        st.download_button("📥 CLD表", cld_t.to_csv(index=False).encode('utf-8-sig'), f"CLD_{method.split('（')[0]}.csv", "text/csv")
    if chart:
        try:
            st.plotly_chart(render_cld_bar_chart(cld_t, '处理', '均值', '字母标识'), use_container_width=True)
        except Exception as e:
            st.warning(f"图表异常: {e}")


# =============================================================================
# Tab 2: 稳定性分析
# =============================================================================
def _tab_stability(df):
    st.markdown("### 🌾 品种稳定性分析")
    st.caption("Shukla方差、Eberhart-Russell回归、综合稳定性评价")
    all_num = [c for c in df.select_dtypes(include=[np.number]).columns]
    all_cat = [c for c in df.columns if c not in all_num]

    with st.expander("⚙️ 参数配置", expanded=True):
        a, b, c = st.columns(3)
        with a:
            rsp = st.selectbox("响应变量", all_num, index=_safe_index(all_num, ['产量', 'yield', '值'], 0), key="sb_y")
        with b:
            gt = st.selectbox("品种列", all_cat, index=_safe_index(all_cat, ['品种', '基因型', '处理'], 0), key="sb_g")
        with c:
            ev = st.selectbox("环境列", [x for x in all_cat if x != gt],
                              index=_safe_index([x for x in all_cat if x != gt], ['地点', '环境', '年份', 'env'], 0), key="sb_e")
        d, e, f = st.columns(3)
        with d:
            s_sh = st.checkbox("Shukla方差", value=True)
        with e:
            s_er = st.checkbox("Eberhart-Russell", value=True)
        with f:
            s_wk = st.checkbox("Wricke生态价", value=False)
        run = st.button("▶ 运行稳定性分析", type="primary")
    if not run:
        return

    check_billing("稳定性分析", {"genotypes": df[gt].nunique(), "environments": df[ev].nunique()})
    res = {}
    with st.spinner("计算稳定性..."):
        if s_sh:
            try:
                res['shukla'] = StabilityAnalysis.shukla_variance(df, rsp, gt, ev)
            except Exception as e:
                st.error(f"Shukla出错: {e}")
        if s_er:
            try:
                er = StabilityAnalysis.eberhart_russell(df, rsp, gt, ev)
                if er:
                    res['er_r'] = er['result']; res['er_i'] = er['env_indices']
                else:
                    st.warning("Eberhart-Russell需≥2个环境")
            except Exception as e:
                st.error(f"ER出错: {e}")
        try:
            res['comb'] = StabilityAnalysis.comprehensive_stability(df, rsp, gt, ev)
        except Exception:
            pass

    for k, title, fname in [('shukla', "Shukla稳定性方差", "Shukla"), ('er_r', "Eberhart-Russell回归", "ER")]:
        if k in res:
            st.subheader(title); _display_df(res[k], key=f"stab_{k}")
            if can_download():
                st.download_button(f"📥 下载{title}", res[k].to_csv(index=False).encode('utf-8-sig'), f"{fname}.csv", "text/csv")
    if 'shukla' in res:
        try:
            fig = plot_stability_scatter(res['shukla'], gt, '总均值', 'Shukla变异数')
            if fig:
                st.plotly_chart(fig.update_layout(height=500), use_container_width=True)
        except Exception:
            pass
    if 'er_r' in res:
        try:
            fig = plot_er_regression(res['er_r'], gt)
            if fig:
                st.plotly_chart(fig.update_layout(height=500), use_container_width=True)
        except Exception:
            pass
    if 'comb' in res:
        st.subheader("综合稳定性评价"); _display_df(res['comb'], key="stab_c")
        if can_download():
            st.download_button("📥 综合评价表", res['comb'].to_csv(index=False).encode('utf-8-sig'), "稳定性综合评价.csv", "text/csv")


# =============================================================================
# Tab 3: 对照比较
# =============================================================================
def _tab_ck_comparison(df):
    st.markdown("### 🎯 对照品种比较")
    st.caption("与CK比较: 增产率/减产率及差异显著性")
    all_num = [c for c in df.select_dtypes(include=[np.number]).columns]
    all_cat = [c for c in df.columns if c not in all_num]

    with st.expander("⚙️ 参数配置", expanded=True):
        a, b, c_ = st.columns(3)
        with a:
            rsp = st.selectbox("响应变量", all_num, index=_safe_index(all_num, ['产量', 'yield', '值'], 0), key="ck_y")
        with b:
            gt = st.selectbox("品种列", all_cat, index=_safe_index(all_cat, ['品种', '基因型', '处理'], 0), key="ck_g")
        with c_:
            all_g = sorted(df[gt].unique())
            ck = st.selectbox("对照品种(CK)", all_g, index=_safe_index(all_g, ['CK', '对照', '郑单958'], 0))
        env_f = st.selectbox("限定环境(可选)", ['(全部)'] + all_cat, key="ck_env")
        run = st.button("▶ 运行对照比较", type="primary")
    if not run:
        return
    dfw = df.copy()
    if env_f != '(全部)':
        dfw = dfw[dfw[env_f] == env_f]
    check_billing("对照比较", {"ck": ck, "genotypes": dfw[gt].nunique()})
    with st.spinner("计算..."):
        try:
            result = CKComparison.compare_with_ck(dfw, rsp, gt, ck_name=ck)
        except (ValueError, Exception) as e:
            st.error(f"❌ {e}"); return
    st.success(f"✅ 完成 (CK={ck})")
    st.subheader(f"与对照 {ck} 比较结果"); _display_df(result, key="ck_res")
    fig = px.bar(result.sort_values('增产率(%)', ascending=True), x='增产率(%)', y='品种',
                 color='增产率(%)', color_continuous_scale=['#ef4444', '#fef3c7', '#22c55e'],
                 text_auto='.1f', title=f"各品种较 {ck} 增产率(%)")
    fig.add_vline(x=0, line_dash="dash", line_color="gray")
    fig.update_layout(height=500, xaxis_title="增产率(%)", yaxis_title="")
    st.plotly_chart(fig, use_container_width=True)
    try:
        rk = CKComparison.ck_rank_in_group(dfw, rsp, gt, ck_name=ck)
        st.info(f"📌 **{ck}** 排名第 **{rk['ck_rank']}** / {rk['total_genotypes']} (百分位: {rk['percentile']}%)")
    except Exception:
        pass
    if can_download():
        st.download_button("📥 下载结果", result.to_csv(index=False).encode('utf-8-sig'), "对照比较.csv", "text/csv")


# =============================================================================
# Tab 4: 报告汇总 (重构，集成审定标准)
# =============================================================================
def _tab_report_summary(df):
    st.markdown("### 📋 区试报告汇总")
    st.caption("综合多重比较/稳定性/对照比较结果，按审定标准判定晋级")
    all_num = [c for c in df.select_dtypes(include=[np.number]).columns]
    all_cat = [c for c in df.columns if c not in all_num]

    with st.expander("⚙️ 参数配置", expanded=True):
        a, b, c, d = st.columns(4)
        with a:
            rsp = st.selectbox("响应变量", all_num, index=_safe_index(all_num, ['产量', 'yield', '值'], 0), key="rpt_y")
        with b:
            gt = st.selectbox("品种列", all_cat, index=_safe_index(all_cat, ['品种', '基因型', '处理'], 0), key="rpt_g")
        with c:
            ev = st.selectbox("环境列(稳定性用)", ['(不分析)'] + all_cat, key="rpt_e")
        with d:
            eco_names = [f"{r['id']}. {r['name']}" for r in TrialReportConfig.ECO_REGIONS]
            eco_ch = st.selectbox("生态区(审定标准)", eco_names, index=3,
                                  help="选择玉米生态区，自动应用审定标准")
            eco_id = int(eco_ch.split('.')[0])
        e, f, g = st.columns(3)
        with e:
            ck_txt = st.text_input("对照品种(留空用默认)", "", placeholder="留空用生态区默认CK", key="rpt_ck")
        with f:
            thr = st.number_input("增产率阈值(%)", 0.0, 100.0, 5.0, 1.0)
        with g:
            stab_thr = st.number_input("稳定性阈(Shukla变异数上限)", 0.0, value=100.0, step=10.0)
        run = st.button("▶ 生成报告", type="primary")
    if not run:
        return

    eco_cfg = TrialReportConfig.get_config(eco_id)
    ck_name = ck_txt.strip() or eco_cfg["ck"]
    check_billing("区试报告汇总", {"genotypes": df[gt].nunique(), "ck": ck_name, "eco": eco_cfg["name"]})

    with st.spinner("生成区试报告..."):
        try:
            ck_res = CKComparison.compare_with_ck(df, rsp, gt, ck_name=ck_name)
        except ValueError:
            ck_res = None
        stab_res = None
        per_env = {}
        if ev != '(不分析)':
            try:
                stab_res = StabilityAnalysis.comprehensive_stability(df, rsp, gt, ev)
            except Exception:
                pass
            for en, edf in df.groupby(ev):
                per_env[en] = edf.groupby(gt)[rsp].mean().to_dict()
        else:
            per_env['全部'] = df.groupby(gt)[rsp].mean().to_dict()

        yv = df.groupby(gt)[rsp].mean().to_dict()
        gl = sorted(df[gt].unique())
        ji = {"genotypes": gl, "yield_values": yv, "ck_name": ck_name, "per_environment": per_env}
        jr = TrialReportConfig.evaluate_promotion(ji, eco_id)
        cfg = {'response': rsp, 'genotype': gt, 'ck_name': ck_name, 'yield_threshold': thr,
               'stability_threshold': stab_thr, 'eco_region': eco_cfg['name'],
               'ck_result': ck_res, 'stability_result': stab_res}
        try:
            report = SSRReportGenerator.generate_summary_report(df, cfg)
        except Exception as e:
            st.error(f"报告生成出错: {e}"); report = {}

    st.success(f"✅ 完成 (生态区:{eco_cfg['name']}, CK:{ck_name})")
    pc = sum(1 for v in jr.values() if isinstance(v, dict) and v.get('judgment') == '晋级')
    pd_ = sum(1 for v in jr.values() if isinstance(v, dict) and v.get('judgment') == '待定')
    pe = sum(1 for v in jr.values() if isinstance(v, dict) and v.get('judgment') == '淘汰')
    oc = st.columns(4)
    oc[0].metric("参试品种", len(gl))
    oc[1].metric("✅ 晋级", pc)
    oc[2].metric("⚠️ 待定", pd_)
    oc[3].metric("❌ 淘汰", pe)

    jrows = []
    for g in gl:
        info = jr.get(g, {})
        if isinstance(info, dict):
            jrows.append({"品种": g, "产量": info.get('yield_value', 0), "较CK(%)": info.get('diff_percent', 0),
                          "达标率(%)": info.get('win_rate', 0), "判定": info.get('judgment', ''),
                          "详情": info.get('detail', '')})
    if jrows:
        jdf = pd.DataFrame(jrows).sort_values('判定').reset_index(drop=True)

        def _cj(v):
            return ('background-color:#dcfce7;color:#166534' if v == '晋级'
                    else 'background-color:#fef9c3;color:#854d0e' if v == '待定'
                    else 'background-color:#fee2e2;color:#991b1b' if v == '淘汰' else '')
        st.dataframe(jdf.style.format(precision=2, na_rep='-').applymap(_cj, subset=['判定']), use_container_width=True)

    if 'report_table' in report:
        st.subheader("品种综合评价表"); _display_df(report['report_table'], key="rpt_t")
        if can_download():
            st.download_button("📥 下载区试报告", report['report_table'].to_csv(index=False).encode('utf-8-sig'), "区试报告.csv", "text/csv")

    for jt, emj in [('晋级', '✅'), ('待定', '⚠️'), ('淘汰', '❌')]:
        items = [(g, v) for g, v in jr.items() if isinstance(v, dict) and v.get('judgment') == jt]
        if items:
            st.subheader(f"{emj} {jt}品种")
            for g, v in items:
                st.markdown(f"- **{g}**: {TrialReportConfig.format_judgment_text(v)}")


# =============================================================================
# Tab 5: AMMI / GGE 双标图
# =============================================================================
def _tab_ammi_gge(df):
    st.markdown("### 📈 AMMI / GGE 双标图分析")
    st.caption("品种-环境互作模式可视化：AMMI1(产量vsPC1)、AMMI2(PC1vsPC2)、GGE双标图")

    all_num = [c for c in df.select_dtypes(include=[np.number]).columns]
    all_cat = [c for c in df.columns if c not in all_num]

    with st.expander("⚙️ 参数配置", expanded=True):
        a, b, c = st.columns(3)
        with a:
            rsp = st.selectbox("响应变量", all_num, index=_safe_index(all_num, ['产量', 'yield', '值'], 0), key="am_y")
        with b:
            gt = st.selectbox("品种列", all_cat, index=_safe_index(all_cat, ['品种', '基因型', '处理'], 0), key="am_g")
        with c:
            ev = st.selectbox("环境列", [x for x in all_cat if x != gt],
                              index=_safe_index([x for x in all_cat if x != gt], ['地点', '环境', '年份', 'env'], 0), key="am_e")
        d, e, f, g_ = st.columns(4)
        with d:
            a1 = st.checkbox("AMMI1", value=True)
        with e:
            a2 = st.checkbox("AMMI2", value=True)
        with f:
            gg = st.checkbox("GGE双标图", value=True)
        with g_:
            gp = st.checkbox("GGE多边形", value=False)
        h, i, j = st.columns(3)
        with h:
            lb = st.checkbox("标签", value=True)
        with i:
            ls = st.slider("标签大小", 6, 16, 10)
        with j:
            ps = st.slider("点大小", 4, 14, 8)
        run = st.button("▶ 运行双标图分析", type="primary", key="ammi_run")
    if not run:
        return

    check_billing("AMMI/GGE双标图", {"genotypes": df[gt].nunique(), "environments": df[ev].nunique()})

    with st.spinner("计算 AMMI/GGE..."):
        ar = BiplotAnalysis.ammi_analysis(df, rsp, gt, ev)
        gr = BiplotAnalysis.gge_analysis(df, rsp, gt, ev)

    st.subheader("AMMI 方差分析")
    ipc_cols = [c for c in ar['ipc_table'].columns if any(k in str(c) for k in ['DF', 'SS', 'MS', 'F', '解释率', '累计'])]
    _display_df(ar['ipc_table'][ipc_cols] if ipc_cols else ar['ipc_table'], key="ammi_ipc")
    st.info(f"📊 前2个IPC累积解释 {ar.get('cum_var', 0):.1f}% 互作变异")

    if a1:
        st.subheader("AMMI1: 产量均值 vs IPC1")
        st.plotly_chart(BiplotAnalysis.plot_ammi1_biplot(ar), use_container_width=True)
    if a2:
        st.subheader("AMMI2: IPC1 vs IPC2")
        st.plotly_chart(BiplotAnalysis.plot_ammi2_biplot(ar), use_container_width=True)
    if gg:
        st.subheader("GGE 双标图")
        st.caption(f"PC1={gr['var_explained'][0]:.1f}%, PC2={gr['var_explained'][1]:.1f}%")
        st.plotly_chart(BiplotAnalysis.plot_gge_biplot(gr), use_container_width=True)
    if gp:
        st.subheader("GGE 多边形图")
        st.plotly_chart(BiplotAnalysis.plot_gge_polygon(gr), use_container_width=True)


# =============================================================================
# Tab 6: 试点评价
# =============================================================================
def _tab_trial_evaluation(df):
    st.markdown("### 🔍 试点与品种评价")
    st.caption("试点鉴别力(CV)、品种均值-CV四象限图、互作效应热力图、品种均值热图/误差图/三维评价")

    all_num = [c for c in df.select_dtypes(include=[np.number]).columns]
    all_cat = [c for c in df.columns if c not in all_num]

    with st.expander("⚙️ 参数配置", expanded=True):
        a, b, c = st.columns(3)
        with a:
            rsp = st.selectbox("响应变量", all_num, index=_safe_index(all_num, ['产量', 'yield', '值'], 0), key="ev_y")
        with b:
            gt = st.selectbox("品种列", all_cat, index=_safe_index(all_cat, ['品种', '基因型', '处理'], 0), key="ev_g")
        with c:
            ev = st.selectbox("环境列", [x for x in all_cat if x != gt],
                              index=_safe_index([x for x in all_cat if x != gt], ['地点', '环境', '年份', 'env'], 0), key="ev_e")
        d, e, f, g_ = st.columns(4)
        with d:
            cv = st.checkbox("试点鉴别力(CV)", value=True)
        with e:
            qd = st.checkbox("均值-CV四象限", value=True)
        with f:
            hm = st.checkbox("互作热力图", value=True)
        with g_:
            top_n = st.number_input("显示前N试点", 3, 50, 20, 1, key="ev_top")
        h, i, j = st.columns(3)
        with h:
            show_hm = st.checkbox("品种均值热图(QYSY)", value=False, key="ev_vmh")
        with i:
            show_eb = st.checkbox("品种均值误差图(QYSY)", value=False, key="ev_eb")
        with j:
            show_3p = st.checkbox("三维评价图(QYSY)", value=True, key="ev_3p")
        run = st.button("▶ 运行评价", type="primary", key="eval_run")
    if not run:
        return

    check_billing("试点评价", {"genotypes": df[gt].nunique(), "environments": df[ev].nunique()})

    with st.spinner("计算试点评价..."):
        env_cv = TrialEvaluation.env_discriminability(df, rsp, gt, ev) if cv else None
        mc = TrialEvaluation.geno_mean_cv(df, rsp, gt, ev) if qd else None
        ie = TrialEvaluation.interaction_effects(df, rsp, gt, ev)

    if env_cv is not None:
        st.subheader("试点鉴别力(CV)")
        _display_df(env_cv.head(top_n), key="eval_cv")
        st.plotly_chart(TrialEvaluation.plot_env_discriminability(env_cv.head(top_n)), use_container_width=True)

    if mc is not None:
        st.subheader("品种丰产性-稳定性分类")
        _display_df(mc, key="eval_mc")
        st.plotly_chart(TrialEvaluation.plot_mean_cv_quadrant(mc, gt), use_container_width=True)

    if hm:
        st.subheader("品种-试点互作效应热力图")
        st.plotly_chart(TrialEvaluation.plot_interaction_heatmap(ie, gt, ev), use_container_width=True)

    # ── QYSY 新增图表 ──
    if show_hm:
        st.subheader("品种均值热图")
        st.caption("品种×试点产量均值矩阵，按均值排序（QYSY AAPZJZRSDTController）")
        st.plotly_chart(TrialEvaluation.plot_variety_mean_heatmap(df, rsp, gt, ev), use_container_width=True)

    if show_eb:
        st.subheader("品种均值误差图")
        st.caption("各品种产量均值 ±95% CI，反映丰产性与稳定性（QYSY AAPZJZSFCTController）")
        st.plotly_chart(TrialEvaluation.plot_variety_error_bar(df, rsp, gt, ev), use_container_width=True)

    if show_3p:
        st.subheader("品种三维评价图")
        st.caption("柱状图=产量均值，折线=排名 和 CV%（QYSY AAPZSDJZTController+AAPZSDHZXYTController）")
        st.plotly_chart(TrialEvaluation.plot_variety_three_point(df, rsp, gt, ev), use_container_width=True)


# =============================================================================
# Tab 7: 异常值诊断
# =============================================================================
def _tab_diagnostics(df):
    st.markdown("### ⚠️ 异常值诊断")
    st.caption("残差分析、正态性检验、Cook距离、杠杆值诊断")

    all_num = [c for c in df.select_dtypes(include=[np.number]).columns]
    all_cat = [c for c in df.columns if c not in all_num]

    with st.expander("⚙️ 参数配置", expanded=True):
        a, b, c, d = st.columns(4)
        with a:
            rsp = st.selectbox("响应变量", all_num, index=_safe_index(all_num, ['产量', 'yield', '值'], 0), key="dg_y")
        with b:
            gt = st.selectbox("品种列", all_cat, index=_safe_index(all_cat, ['品种', '基因型', '处理'], 0), key="dg_g")
        with c:
            ev = st.selectbox("环境列(可选)", ['(不选)'] + all_cat, key="dg_e")
        with d:
            blk = st.selectbox("区组列(可选)", ['(不选)'] + all_cat, key="dg_b")
        run = st.button("▶ 运行诊断", type="primary", key="diag_run")
    if not run:
        return

    pass  # 异常值诊断免费，不扣次数

    with st.spinner("运行诊断..."):
        ev_val = ev if ev != '(不选)' else None
        blk_val = blk if blk != '(不选)' else None
        dc = Diagnostics.residual_analysis(df, rsp, gt, environment=ev_val, block=blk_val)

    # 统计摘要
    st.subheader("诊断统计摘要")
    if 'shapiro_p' in dc:
        sw_p = dc['shapiro_p']
        sw_s = dc['shapiro_stat']
        sw_text = f"✅ 残差服从正态分布 (p={sw_p:.4f})" if sw_p > 0.05 else f"⚠️ 残差不服从正态分布 (p={sw_p:.4f})"
        st.metric("Shapiro-Wilk W", f"{sw_s:.4f}", sw_text, delta_color="off")
    if 'jb_p' in dc:
        jb_p = dc['jb_p']
        jb_s = dc['jb_stat']
        jb_text = f"✅ (p={jb_p:.4f})" if jb_p > 0.05 else f"⚠️ (p={jb_p:.4f})"
        st.metric("Jarque-Bera", f"{jb_s:.4f}", jb_text, delta_color="off")
    if dc.get('outliers_3sigma'):
        st.warning(f"⚠️ 发现 {len(dc['outliers_3sigma'])} 个潜在离群点（3σ规则），详见结果表")

    # 结果表
    if 'result' in dc:
        st.subheader("诊断明细")
        _display_df(dc['result'], key="diag_table")
        if can_download():
            st.download_button("📥 诊断结果CSV", dc['result'].to_csv(index=False).encode('utf-8-sig'), "异常值诊断.csv", "text/csv")

    # 诊断图
    st.subheader("诊断图")
    st.plotly_chart(Diagnostics.plot_residuals(dc), use_container_width=True)


# =============================================================================
# Tab 8: 报告导出 (Word) — 全面增强版
# =============================================================================
def _tab_report_export(df):
    st.markdown("### 📝 报告导出")
    st.caption("生成 Word/Excel 版完整试验报告（区域试验/生产试验），含多重比较/稳定性/CK比较/AMMI/试点评价/审定判定")

    all_num = [c for c in df.select_dtypes(include=[np.number]).columns]
    all_cat = [c for c in df.columns if c not in all_num]

    with st.expander("⚙️ 参数配置", expanded=True):
        a, b, c = st.columns(3)
        with a:
            rsp = st.selectbox("响应变量", all_num, index=_safe_index(all_num, ['产量', 'yield', '值'], 0), key="ex_y")
        with b:
            gt = st.selectbox("品种列", all_cat, index=_safe_index(all_cat, ['品种', '基因型', '处理'], 0), key="ex_g")
        with c:
            ev = st.selectbox("环境列", [x for x in all_cat if x != gt],
                              index=_safe_index([x for x in all_cat if x != gt], ['地点', '环境', '年份', 'env'], 0), key="ex_e")
        d, e, f = st.columns(3)
        with d:
            eco_names = [f"{r['id']}. {r['name']}" for r in TrialReportConfig.ECO_REGIONS]
            eco_ch = st.selectbox("生态区", eco_names, index=3, key="ex_eco")
            eco_id = int(eco_ch.split('.')[0])
        with e:
            ck_txt = st.text_input("对照品种(留空用默认)", "", placeholder="留空用生态区默认CK", key="ex_ck")
        with f:
            mc_method = st.selectbox("多重比较方法",
                ["Duncan SSR（新复极差法）","SNK q检验","Tukey HSD","Fisher LSD"], key="ex_mc")
            mc_alias = mc_method.split("（")[0]
        g, h, i = st.columns(3)
        with g:
            include_stab = st.checkbox("包含稳定性分析", value=True)
        with h:
            include_ammi = st.checkbox("包含AMMI分析", value=True)
        with i:
            is_lt = st.checkbox("生产试验模式(试用LTPIP)", value=False, key="ex_lt")
        run = st.button("📝 生成并下载报告", type="primary", key="export_run")
    if not run:
        return

    eco_cfg = TrialReportConfig.get_config(eco_id)
    ck_name = ck_txt.strip() or eco_cfg["ck"]
    check_billing("报告导出", {"ck": ck_name, "eco_region": eco_cfg["name"]})

    with st.spinner("正在生成 Word 报告（收集全部分析数据）..."):
        gl = sorted(df[gt].unique())
        n_g = len(gl)

        # ── 1. 联合方差分析 ──
        anova_table = pd.DataFrame()
        grand_mean_val = None
        cv_val = None
        try:
            _sm_ols = _get_ols()
            _anova_lm = _get_anova_lm()
            terms_f = [f'C(Q("{t}"))' for t in [gt, ev]]
            formula = f'Q("{rsp}") ~ {" + ".join(terms_f)}'
            m = _sm_ols(formula, data=df).fit()
            at = _anova_lm(m, typ=2)
            anova_table = format_anova_table(at)
            grand_mean_val = round(df[rsp].mean(), 2)
            # CV
            res = at.loc[at.index.str.lower() == 'residual']
            if len(res) > 0:
                mse = res['sum_sq'].values[0] / res['df'].values[0]
                cv_val = round((mse**0.5) / grand_mean_val * 100, 2) if grand_mean_val else None
        except Exception:
            pass

        # ── 2. 各试点单点方差分析 + 产量汇总 ──
        per_env_anova = {}
        per_env_yield = {}
        all_yv = {}
        for en, edf in df.groupby(ev):
            # 单点方差分析
            try:
                sm_ols2 = _get_ols()
                al2 = _get_anova_lm()
                m2 = sm_ols2(f'Q("{rsp}") ~ C(Q("{gt}"))', data=edf).fit()
                at2 = al2(m2, typ=2)
                pea = format_anova_table(at2)
                if not pea.empty:
                    per_env_anova[en] = pea
            except Exception:
                pass
            # 各试点品种均值
            env_means = edf.groupby(gt)[rsp].mean().sort_values(ascending=False)
            rows = []
            for idx, (g, v) in enumerate(env_means.items()):
                pct_ck = ((v - env_means.get(ck_name, v)) / env_means.get(ck_name, v) * 100) if ck_name in env_means.index and env_means[ck_name] != 0 else 0
                diff_ck = v - env_means.get(ck_name, v) if ck_name in env_means.index else 0
                rows.append({'品种': g, '产量': round(v, 2), '排名': idx + 1,
                             '较CK': round(diff_ck, 2), '较CK(%)': round(pct_ck, 2)})
            per_env_yield[en] = pd.DataFrame(rows)
            all_yv[en] = env_means.to_dict()

        # ── 总平均汇总 ──
        overall_means = df.groupby(gt)[rsp].mean().sort_values(ascending=False)
        overall_rows = []
        for idx, (g, v) in enumerate(overall_means.items()):
            pct_ck = ((v - overall_means.get(ck_name, v)) / overall_means.get(ck_name, v) * 100) if ck_name in overall_means.index and overall_means[ck_name] != 0 else 0
            diff_ck = v - overall_means.get(ck_name, v) if ck_name in overall_means.index else 0
            overall_rows.append({'品种': g, '产量': round(v, 2), '排名': idx + 1,
                                 '较CK': round(diff_ck, 2), '较CK(%)': round(pct_ck, 2)})
        per_env_yield['总平均'] = pd.DataFrame(overall_rows)

        # ── 3. 多重比较 ──
        mc_result = {}
        try:
            # 多环境均值多重比较
            gm_for_mc = df.groupby(gt)[rsp].mean()
            yv_mc = gm_for_mc.values
            gv_mc = gm_for_mc.index.tolist()
            # 估算 MSE（使用联合方差分析的 MSE）
            try:
                sm_ols3 = _get_ols()
                al3 = _get_anova_lm()
                m3 = sm_ols3(f'Q("{rsp}") ~ C(Q("{gt}")) + C(Q("{ev}"))', data=df).fit()
                at3 = al3(m3, typ=2)
                res3 = at3.loc[at3.index.str.lower() == 'residual']
                if len(res3) > 0:
                    mse_val = res3['sum_sq'].values[0] / res3['df'].values[0]
                    dfe_val = int(res3['df'].values[0])
                else:
                    mse_val, dfe_val = None, None
            except Exception:
                mse_val, dfe_val = None, None

            func_map = {"Duncan SSR": SSRMultipleComparison.duncan_test,
                        "SNK q检验": SSRMultipleComparison.snk_test,
                        "Tukey HSD": SSRMultipleComparison.tukey_test,
                        "Fisher LSD": SSRMultipleComparison.lsd_test}
            func = func_map.get(mc_alias, SSRMultipleComparison.duncan_test)
            result = func(yv_mc, gv_mc, mse_val=mse_val, df_e=dfe_val, alpha=0.05)
            pairs = result['pairs']; n_s = result['names_sorted']; m_s = result['means_sorted']
            sig_col = 'reject' if mc_alias == 'Tukey HSD' else '显著'
            cld = SSRMultipleComparison.compute_cld_letters(n_s, m_s, pairs,
                g1_col=pairs.columns[0], g2_col=pairs.columns[1], sig_col=sig_col)
            cld_t = SSRMultipleComparison.generate_cld_table(n_s, m_s, cld)
            mc_result = {
                'method': mc_alias, 'cld_table': cld_t, 'pairs': pairs,
                'mse': mse_val, 'dfe': dfe_val,
            }
        except Exception as e:
            st.warning(f"多重比较计算异常（将使用简化CLD）: {e}")
            # 降级：纯排序CLD
            gm_sorted = overall_means.sort_values(ascending=False)
            cld_simple = pd.DataFrame({
                '品种': gm_sorted.index, '均值': gm_sorted.values.round(2),
                '排名': range(1, len(gm_sorted)+1), '字母标识': ['a'] + ['b']*(len(gm_sorted)-1)
            })
            mc_result = {'method': mc_alias, 'cld_table': cld_simple, 'pairs': pd.DataFrame()}

        # ── 4. 对照比较 ──
        ck_res = None
        ck_rank_info = {}
        try:
            ck_res = CKComparison.compare_with_ck(df, rsp, gt, ck_name=ck_name)
        except (ValueError, Exception):
            pass
        try:
            ck_rk = CKComparison.ck_rank_in_group(df, rsp, gt, ck_name=ck_name)
            if ck_rk:
                ck_rank_info = ck_rk
        except Exception:
            pass
        ck_comp_data = {'ck_name': ck_name, 'ck_result': ck_res, 'ck_rank': ck_rank_info}

        # ── 5. 稳定性分析 ──
        stab_data = {}
        if include_stab:
            try:
                shk = StabilityAnalysis.shukla_variance(df, rsp, gt, ev)
                if shk is not None and not shk.empty:
                    stab_data['shukla'] = shk
            except Exception:
                pass
            try:
                er = StabilityAnalysis.eberhart_russell(df, rsp, gt, ev)
                if er:
                    stab_data['eberhart_russell'] = er['result']
            except Exception:
                pass
            try:
                cmb = StabilityAnalysis.comprehensive_stability(df, rsp, gt, ev)
                if cmb is not None and not cmb.empty:
                    stab_data['comprehensive'] = cmb
            except Exception:
                pass

        # ── 6. AMMI 分析 ──
        ammi_data = {}
        if include_ammi:
            try:
                ar = BiplotAnalysis.ammi_analysis(df, rsp, gt, ev)
                if ar:
                    ammi_data['ipc_table'] = ar.get('ipc_table', pd.DataFrame())
                    ammi_data['anova'] = ar.get('anova', pd.DataFrame())
                    ammi_data['cum_var'] = ar['ipc_table']['累积贡献率(%)'].iloc[1] if len(ar.get('ipc_table', pd.DataFrame())) > 1 else (ar['ipc_table']['累积贡献率(%)'].iloc[0] if len(ar.get('ipc_table', pd.DataFrame())) > 0 else 0)
            except Exception:
                pass

        # ── 7. 试点评价 ──
        trial_eval = {}
        try:
            trial_eval['env_discriminability'] = TrialEvaluation.env_discriminability(df, rsp, gt, ev)
        except Exception:
            pass
        try:
            trial_eval['geno_mean_cv'] = TrialEvaluation.geno_mean_cv(df, rsp, gt, ev)
        except Exception:
            pass

        # ── 8. 品种综合评价 ──
        variety_eval = []
        try:
            for idx, (g, v) in enumerate(overall_means.items()):
                entry = {'品种': g, '产量': round(v, 2), '排名': idx + 1}
                if ck_res is not None and not ck_res.empty:
                    m = ck_res[ck_res.iloc[:, 0] == g]
                    if len(m) > 0:
                        entry['比CK增产(%)'] = round(float(m.iloc[0].get('增产率(%)', 0)), 2) if m.iloc[0].get('增产率(%)', '') != '' else 0
                if 'shukla' in stab_data and not stab_data['shukla'].empty:
                    sm = stab_data['shukla'][stab_data['shukla'].iloc[:, 0] == g]
                    if len(sm) > 0:
                        entry['Shukla变异数'] = round(float(sm.iloc[0].get('Shukla变异数', 0)), 2)
                variety_eval.append(entry)
        except Exception:
            pass

        # ── 9. 品种审定判定 ──
        ji = {"genotypes": gl, "yield_values": overall_means.to_dict(),
              "ck_name": ck_name,
              "per_environment": all_yv}
        jr = TrialReportConfig.evaluate_promotion(ji, eco_id)

        # ── 组装完整的 report_data ──
        rpt_title = eco_cfg['title']
        if is_lt and '区域试验' in rpt_title:
            rpt_title = rpt_title.replace('区域试验', '生产试验')
        report_data = {
            "overview": {"title": rpt_title, "year": "2025",
                         "n_genotypes": n_g, "n_environments": len(per_env_yield) - 1,
                         "n_replicates": int(df.groupby([gt, ev]).ngroups / n_g / len(per_env_yield.keys() - {'总平均'})) if n_g > 0 and (len(per_env_yield) - 1) > 0 else 1},
            "anova": {"anova_table": anova_table, "grand_mean": grand_mean_val, "cv": cv_val},
            "per_env_anova": per_env_anova,
            "per_env_yield": per_env_yield,
            "multiple_comparison": mc_result,
            "ck_comparison": ck_comp_data,
            "stability": stab_data,
            "ammi": ammi_data,
            "trial_evaluation": trial_eval,
            "variety_evaluation": variety_eval,
            "judgment": jr,
        }

        # ── 生成并下载 ──
        a, b = st.columns(2)
        with a:
            docx_bytes = None
            try:
                path_w = ReportExporter.export_to_word(report_data, eco_id, is_production_trial=is_lt)
                with open(path_w, "rb") as f:
                    docx_bytes = f.read()
            except ImportError:
                st.error("❌ python-docx 未安装，请执行: pip install python-docx")
            except Exception as e:
                st.error(f"❌ Word 报告生成失败: {e}")
            if docx_bytes:
                rpt_type = "生产试验" if is_lt else "区域试验"
                st.success(f"✅ {rpt_type}报告（含 {len([k for k,v in report_data.items() if v])} 个章节）")
                st.download_button("📥 下载 Word 报告", docx_bytes,
                                   f"{rpt_type}报告_{eco_cfg['name']}.docx",
                                   "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                   use_container_width=True, key="dl_word")
        with b:
            xlsx_bytes = None
            try:
                path_x = ReportExporter.export_to_excel(report_data, eco_id, is_production_trial=is_lt)
                with open(path_x, "rb") as f:
                    xlsx_bytes = f.read()
            except Exception as e:
                st.error(f"❌ Excel 报告生成失败: {e}")
            if xlsx_bytes:
                rpt_type = "生产试验" if is_lt else "区域试验"
                st.success(f"✅ Excel {rpt_type}报告（11 个工作表）")
                st.download_button("📥 下载 Excel 报告", xlsx_bytes,
                                   f"{rpt_type}报告_{eco_cfg['name']}.xlsx",
                                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                   use_container_width=True, key="dl_xlsx")


# =============================================================================
# 主渲染函数
# =============================================================================
def render_trial_report():
    require_auth()
    log_visit("区试报告")
    inject_css()
    st.markdown('<div class="section-header">📋 区试报告</div>', unsafe_allow_html=True)

    with st.expander("📖 使用指南", expanded=False):
        st.markdown("""
        **区试报告** 模块含8个分析Tab：

        | Tab | 功能 | 说明 |
        |:---:|------|------|
        | 📊 多重比较 | Duncan/SNK/Tukey/LSD + CLD | 品种均值两两比较，字母分组 |
        | 🌾 稳定性 | Shukla/Eberhart-Russell/Wricke | 多环境品种稳定性分析 |
        | 🎯 对照比较 | CK增产率/排名 | 与对照品种比较及差异显著性 |
        | 📋 报告汇总 | 审定判定(12生态区) | 综合判定晋级/待定/淘汰 |
        | 📈 AMMI/GGE | 双标图/多边形 | 品种-环境互作模式可视化 |
        | 🔍 试点评价 | CV/四象限/热力图 | 试点鉴别力与品种分类 |
        | ⚠️ 异常值诊断 | 残差/Q-Q/Cook距离 | 数据质控与离群点检测 |
        | 📝 报告导出 | Word格式 | 完整分析报告一键导出 |
        """)

    dm = get_current_dm()
    if not dm.is_loaded:
        st.warning("⚠️ 请先通过首页上传数据文件")
        return
    df = dm.data
    if not _import_modules():
        return

    tabs = st.tabs(["📊 多重比较", "🌾 稳定性", "🎯 对照比较", "📋 报告汇总",
                    "📈 AMMI/GGE", "🔍 试点评价", "⚠️ 异常值诊断", "📝 导出"])
    with tabs[0]:
        _tab_multiple_comparison(df)
    with tabs[1]:
        _tab_stability(df)
    with tabs[2]:
        _tab_ck_comparison(df)
    with tabs[3]:
        _tab_report_summary(df)
    with tabs[4]:
        _tab_ammi_gge(df)
    with tabs[5]:
        _tab_trial_evaluation(df)
    with tabs[6]:
        _tab_diagnostics(df)
    with tabs[7]:
        _tab_report_export(df)


if __name__ == "__main__":
    render_trial_report()
