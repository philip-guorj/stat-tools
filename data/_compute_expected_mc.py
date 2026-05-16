"""计算示例数据的期望多重比较结果"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from scipy import stats as scipy_stats
import statsmodels.api as sm
from statsmodels.formula.api import ols
from statsmodels.stats.anova import anova_lm

df = pd.read_csv('data/区试试验示例数据.csv')

# 联合ANOVA
formula = 'Q("产量") ~ C(Q("地点"))/C(Q("区组")) + C(Q("品种")) + C(Q("地点")):C(Q("品种"))'
model = ols(formula, data=df).fit()
anova_tbl = anova_lm(model, typ=2)

for idx in anova_tbl.index:
    if 'Residual' in str(idx):
        residual_row = anova_tbl.loc[idx]
        break
else:
    residual_row = anova_tbl.iloc[-1]

mse_val = float(residual_row['sum_sq'] / residual_row['df'])
df_e = int(residual_row['df'])

# 品种均值
emmeans_geno = df.groupby('品种')['产量'].mean()
geno_names_sorted = emmeans_geno.sort_values(ascending=False).index.tolist()
geno_means_sorted = emmeans_geno.sort_values(ascending=False).values
reps_per_geno = df.groupby('品种').size().astype(float)

print(f'MSE = {mse_val:.6f}, df_e = {df_e}')
print(f'品种数 = {len(geno_names_sorted)}')
print(f'品种排序: {geno_names_sorted}')
print(f'品种均值: {geno_means_sorted}')

# === Fisher LSD ===
from scipy.stats import t as t_dist
alpha = 0.05
t_crit = abs(t_dist.ppf(alpha/2, df_e))
lsd_results = []
for i in range(len(geno_names_sorted)):
    for j in range(i + 1, len(geno_names_sorted)):
        g1, g2 = geno_names_sorted[i], geno_names_sorted[j]
        m1, m2 = emmeans_geno[g1], emmeans_geno[g2]
        diff = m1 - m2
        se_diff = np.sqrt(mse_val * (1.0/reps_per_geno[g1] + 1.0/reps_per_geno[g2]))
        t_stat = diff / se_diff if se_diff > 0 else 0
        p_val = 2 * (1 - t_dist.cdf(abs(t_stat), df_e))
        lsd_value = t_crit * se_diff
        is_sig = abs(diff) >= lsd_value
        lsd_results.append({
            '品种1': g1, '品种2': g2,
            '均值差': round(diff, 4),
            '标准误': round(se_diff, 4),
            'LSD': round(lsd_value, 4),
            't值': round(t_stat, 3),
            'p值': round(p_val, 4),
            '显著': 'Y' if is_sig else ''
        })

df_lsd = pd.DataFrame(lsd_results)
print(f'\n=== Fisher LSD 期望结果 ({len(lsd_results)}对) ===')
sig_count = sum(1 for r in lsd_results if r['显著'])
print(f'显著对数: {sum(1 for r in lsd_results if r["显著"] == "Y")}')
print('前三对比对:')
for r in lsd_results[:3]:
    print(f'  {r["品种1"]} vs {r["品种2"]}: diff={r["均值差"]}, LSD={r["LSD"]}, p={r["p值"]}')

# === CLD计算（闭包法）===
string_lib = __import__('string')
n = len(geno_names_sorted)
non_sig = {g: set() for g in geno_names_sorted}
for r in lsd_results:
    if r['显著'] == '':
        non_sig[r['品种1']].add(r['品种2'])
        non_sig[r['品种2']].add(r['品种1'])

assigned_letters = {g: set() for g in geno_names_sorted}
letter_idx = 0
for i, g_seed in enumerate(geno_names_sorted):
    group = {g_seed}
    for j in range(i + 1, len(geno_names_sorted)):
        g_cand = geno_names_sorted[j]
        if all(g_cand in non_sig.get(gm, set()) for gm in group):
            group.add(g_cand)
    cur_letter = string_lib.ascii_uppercase[letter_idx]
    for gm in group:
        assigned_letters[gm].add(cur_letter)
    letter_idx += 1

print('\n=== CLD字母标识（基于LSD）===')
for g in geno_names_sorted:
    letters = ''.join(sorted(assigned_letters.get(g, set())))
    print(f'  {g}: {emmeans_geno[g]:.2f} -> {letters}')

# 保存完整期望结果到json
expected_mc = {
    'mse': round(mse_val, 6),
    'df_e': df_e,
    't_crit_005': round(float(t_crit), 6),
    'geno_ranking': {g: round(float(emmeans_geno[g]), 4) for g in geno_names_sorted},
    'lsd_pairs': lsd_results,
    'cld_letters': {g: ''.join(sorted(assigned_letters.get(g, set()))) for g in geno_names_sorted},
}

with open('data/expected_results_mc.json', 'w', encoding='utf-8') as f:
    json.dump(expected_mc, f, ensure_ascii=False, indent=2)
print('\n=== 已保存期望多重比较结果到 data/expected_results_mc.json ===')
