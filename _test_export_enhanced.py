"""测试增强版 ReportExporter — 完整数据验证"""
import sys, os; sys.path.insert(0, os.path.dirname(__file__))
import pandas as pd
import numpy as np
from modules.trial_report_analysis import (
    ReportExporter, TrialReportConfig,
    SSRMultipleComparison, StabilityAnalysis,
    CKComparison, BiplotAnalysis, TrialEvaluation,
    format_anova_table,
)
from datetime import datetime

eco_cfg = TrialReportConfig.get_config(4)
print(f"生态区: {eco_cfg['name']}, CK: {eco_cfg['ck']}")

# ── 构建模拟数据集 ──
np.random.seed(42)
genotypes = ['A', 'B', 'C', 'D', 'E', 'F']
environments = ['北京', '石家庄', '郑州', '济南', '沈阳']
n_rep = 3

rows = []
base_yield = {'A': 680, 'B': 650, 'C': 620, 'D': 590, 'E': 560, 'F': 530}
env_effects = {'北京': 20, '石家庄': 10, '郑州': -5, '济南': 0, '沈阳': -15}

for g in genotypes:
    for e in environments:
        base = base_yield[g] + env_effects[e]
        for rep in range(n_rep):
            val = base + np.random.normal(0, 8)
            rows.append({'品种': g, '环境': e, '区组': f'R{rep+1}', '产量': round(val, 1)})

df = pd.DataFrame(rows)
print(f"数据: {len(df)} 行, {df['品种'].nunique()} 品种, {df['环境'].nunique()} 环境")

rsp = '产量'; gt = '品种'; ev = '环境'

# ════════════════════════════════════════════
# 1. 联合方差分析
# ════════════════════════════════════════════
print("\n--- 1. 联合方差分析 ---")
from statsmodels.formula.api import ols as sm_ols
from statsmodels.stats.anova import anova_lm
m = sm_ols(f'Q("{rsp}") ~ C(Q("{gt}")) + C(Q("{ev}"))', data=df).fit()
at = anova_lm(m, typ=2)
anova_table = format_anova_table(at)
print(anova_table.to_string())
grand_mean_val = round(df[rsp].mean(), 2)
res = at.loc[at.index.str.lower() == 'residual']
mse_val = res['sum_sq'].values[0] / res['df'].values[0] if len(res) > 0 else None
dfe_val = int(res['df'].values[0]) if len(res) > 0 else None
cv_val = round((mse_val**0.5) / grand_mean_val * 100, 2) if grand_mean_val and mse_val else None
print(f"总平均: {grand_mean_val}, 误差MSE: {mse_val:.2f}, dfe: {dfe_val}, CV: {cv_val}%")

# ════════════════════════════════════════════
# 2. 各试点单点方差分析 + 产量汇总
# ════════════════════════════════════════════
print("\n--- 2. 各试点产量汇总 ---")
per_env_anova = {}
per_env_yield = {}
all_yv = {}
for en, edf in df.groupby(ev):
    m2 = sm_ols(f'Q("{rsp}") ~ C(Q("{gt}"))', data=edf).fit()
    at2 = anova_lm(m2, typ=2)
    pea = format_anova_table(at2)
    if not pea.empty:
        per_env_anova[en] = pea
    env_means = edf.groupby(gt)[rsp].mean().sort_values(ascending=False)
    rows_t = []
    for idx, (g, v) in enumerate(env_means.items()):
        ck_v = env_means.get('D', 0)
        pct_ck = ((v - ck_v) / ck_v * 100) if ck_v else 0
        rows_t.append({'品种': g, '产量': round(v, 2), '排名': idx + 1,
                       '较CK': round(v - ck_v, 2), '较CK(%)': round(pct_ck, 2)})
    per_env_yield[en] = pd.DataFrame(rows_t)
    all_yv[en] = env_means.to_dict()

overall_means = df.groupby(gt)[rsp].mean().sort_values(ascending=False)
overall_rows = []
for idx, (g, v) in enumerate(overall_means.items()):
    ck_v = overall_means.get('D', 0)
    pct_ck = ((v - ck_v) / ck_v * 100) if ck_v else 0
    overall_rows.append({'品种': g, '产量': round(v, 2), '排名': idx + 1,
                         '较CK': round(v - ck_v, 2), '较CK(%)': round(pct_ck, 2)})
per_env_yield['总平均'] = pd.DataFrame(overall_rows)
print(per_env_yield['总平均'].to_string())

# ════════════════════════════════════════════
# 3. 多重比较
# ════════════════════════════════════════════
print("\n--- 3. 多重比较 ---")
gm_for_mc = df.groupby(gt)[rsp].mean()
yv_mc = gm_for_mc.values
gv_mc = gm_for_mc.index.tolist()
result = SSRMultipleComparison.duncan_test(yv_mc, gv_mc, mse_val=mse_val, df_e=dfe_val, alpha=0.05)
pairs = result['pairs']; n_s = result['names_sorted']; m_s = result['means_sorted']
cld = SSRMultipleComparison.compute_cld_letters(n_s, m_s, pairs, g1_col=pairs.columns[0], g2_col=pairs.columns[1], sig_col='显著')
cld_t = SSRMultipleComparison.generate_cld_table(n_s, m_s, cld)
print(cld_t.to_string())
mc_result = {'method': 'Duncan', 'cld_table': cld_t, 'pairs': pairs, 'mse': mse_val, 'dfe': dfe_val}

# ════════════════════════════════════════════
# 4. 对照比较
# ════════════════════════════════════════════
print("\n--- 4. 对照比较 ---")
ck_name = 'D'
ck_res = CKComparison.compare_with_ck(df, rsp, gt, ck_name=ck_name)
print(ck_res.to_string())
ck_rk = CKComparison.ck_rank_in_group(df, rsp, gt, ck_name=ck_name)
print(f"CK排名: {ck_rk}")
ck_comp_data = {'ck_name': ck_name, 'ck_result': ck_res, 'ck_rank': ck_rk}

# ════════════════════════════════════════════
# 5. 稳定性
# ════════════════════════════════════════════
print("\n--- 5. 稳定性 ---")
stab_data = {}
shk = StabilityAnalysis.shukla_variance(df, rsp, gt, ev)
if shk is not None and not shk.empty:
    stab_data['shukla'] = shk
    print(shk.to_string())
er = StabilityAnalysis.eberhart_russell(df, rsp, gt, ev)
if er:
    stab_data['eberhart_russell'] = er['result']
    print(er['result'].to_string())
cmb = StabilityAnalysis.comprehensive_stability(df, rsp, gt, ev)
if cmb is not None and not cmb.empty:
    stab_data['comprehensive'] = cmb
    print(cmb.to_string())

# ════════════════════════════════════════════
# 6. AMMI
# ════════════════════════════════════════════
print("\n--- 6. AMMI ---")
ammi_data = {}
ar = BiplotAnalysis.ammi_analysis(df, rsp, gt, ev)
if ar:
    ammi_data['ipc_table'] = ar.get('ipc_table', pd.DataFrame())
    ammi_data['anova'] = ar.get('anova', pd.DataFrame())
    cum_var = ar['ipc_table']['累积贡献率(%)'].iloc[1] if len(ar.get('ipc_table', pd.DataFrame())) > 1 else (ar['ipc_table']['累积贡献率(%)'].iloc[0] if len(ar.get('ipc_table', pd.DataFrame())) > 0 else 0)
    ammi_data['cum_var'] = float(cum_var)
    print(f"AMMI累积贡献: {cum_var}%")

# ════════════════════════════════════════════
# 7. 试点评价
# ════════════════════════════════════════════
print("\n--- 7. 试点评价 ---")
trial_eval = {}
trial_eval['env_discriminability'] = TrialEvaluation.env_discriminability(df, rsp, gt, ev)
print(trial_eval['env_discriminability'].to_string())
trial_eval['geno_mean_cv'] = TrialEvaluation.geno_mean_cv(df, rsp, gt, ev)
print(trial_eval['geno_mean_cv'].to_string())

# ════════════════════════════════════════════
# 8. 品种综合评价
# ════════════════════════════════════════════
print("\n--- 8. 品种综合评价 ---")
variety_eval = []
for idx, (g, v) in enumerate(overall_means.items()):
    entry = {'品种': g, '产量': round(v, 2), '排名': idx + 1}
    if ck_res is not None:
        m = ck_res[ck_res.iloc[:, 0] == g]
        if len(m) > 0:
            pct = m.iloc[0].get('增产率(%)', 0)
            entry['比CK增产(%)'] = round(float(pct), 2) if pct != '' else 0
    if 'shukla' in stab_data:
        sm = stab_data['shukla'][stab_data['shukla'].iloc[:, 0] == g]
        if len(sm) > 0:
            entry['Shukla变异数'] = round(float(sm.iloc[0].get('Shukla变异数', 0)), 2)
    variety_eval.append(entry)
for v in variety_eval:
    print(f"  {v['品种']}: 产量={v['产量']}, 排名={v['排名']}, 增产={v.get('比CK增产(%)','')}%")

# ════════════════════════════════════════════
# 9. 品种审定判定
# ════════════════════════════════════════════
print("\n--- 9. 品种审定判定 ---")
gl = sorted(df[gt].unique())
ji = {"genotypes": gl, "yield_values": overall_means.to_dict(),
      "ck_name": ck_name, "per_environment": all_yv}
jr = TrialReportConfig.evaluate_promotion(ji, 4)
for g, v in jr.items():
    if isinstance(v, dict):
        print(f"  {g}: {v['judgment']} (增产{v['diff_percent']:+.2f}%, 达标率{v['win_rate']}%)")

# ════════════════════════════════════════════
# 组装完整 report_data
# ════════════════════════════════════════════
report_data = {
    "overview": {"title": eco_cfg['title'], "year": "2025",
                 "n_genotypes": len(gl), "n_environments": len(per_env_yield) - 1,
                 "n_replicates": n_rep},
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

# ════════════════════════════════════════════
# 生成 Word
# ════════════════════════════════════════════
print("\n--- 正在生成 Word 报告 ---")
path = ReportExporter.export_to_word(report_data, eco_region_id=4)
print(f'SUCCESS: {path}')
print(f"文件大小: {os.path.getsize(path) / 1024:.1f} KB")
