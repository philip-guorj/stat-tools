"""计算示例数据的期望分析结果"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import statsmodels.api as sm
from statsmodels.formula.api import ols
from statsmodels.stats.anova import anova_lm

df = pd.read_csv('data/区试试验示例数据.csv')
print('=== 数据概览 ===')
print(f'记录数: {len(df)}')
print(f'品种数: {df["品种"].nunique()}')
print(f'环境数: {df["地点"].nunique()}')
print(f'区组数: {df["区组"].nunique()}')

# 品种均值
geno_means = df.groupby('品种')['产量'].mean().sort_values(ascending=False)
print('\n=== 品种均值（降序，用于CLD验证） ===')
for g, m in geno_means.items():
    print(f'  {g}: {m:.2f}')

# 联合ANOVA
formula = 'Q("产量") ~ C(Q("地点"))/C(Q("区组")) + C(Q("品种")) + C(Q("地点")):C(Q("品种"))'
model = ols(formula, data=df).fit()
anova_tbl = anova_lm(model, typ=2)
print('\n=== 联合ANOVA表 ===')
print(anova_tbl.to_string())

# 误差项
for idx in anova_tbl.index:
    if 'Residual' in str(idx):
        residual_row = anova_tbl.loc[idx]
        break
else:
    residual_row = anova_tbl.iloc[-1]

mse_val = residual_row['sum_sq'] / residual_row['df']
df_e = int(residual_row['df'])
print(f'\nMSE = {mse_val:.4f}, df_e = {df_e}')

# 保存期望结果
expected = {
    'geno_means': {g: round(float(m), 4) for g, m in geno_means.items()},
    'n_geno': int(df['品种'].nunique()),
    'n_env': int(df['地点'].nunique()),
    'n_block': int(df['区组'].nunique()),
    'n_total': len(df),
    'mse': round(float(mse_val), 4),
    'df_e': df_e,
}
with open('data/expected_results.json', 'w', encoding='utf-8') as f:
    json.dump(expected, f, ensure_ascii=False, indent=2)
print('\n=== 已保存期望结果到 data/expected_results.json ===')
