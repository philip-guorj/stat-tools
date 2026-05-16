"""
生成配合力分析示例数据 (NCII + Diallel)
"""
import numpy as np
import pandas as pd

np.random.seed(202605)

# =============================================================================
# NCII 设计数据
# =============================================================================
# 3母本 × 4父本 × 2区组 = 24条
females = ['母A', '母B', '母C']
males = ['父D', '父E', '父F', '父G']
# GCA 效应
gca_f = {'母A': 3.0, '母B': -1.5, '母C': 1.0}
gca_m = {'父D': 2.0, '父E': -1.0, '父F': 0.5, '父G': -1.5}
# SCA 效应 (部分交互)
sca = {
    ('母A', '父D'): 1.2, ('母A', '父E'): -2.0, ('母A', '父F'): 0.8, ('母A', '父G'): -0.5,
    ('母B', '父D'): -1.5, ('母B', '父E'): 2.5, ('母B', '父F'): -1.0, ('母B', '父G'): 0.3,
    ('母C', '父D'): 0.5, ('母C', '父E'): -0.8, ('母C', '父F'): 0.2, ('母C', '父G'): 1.0,
}
grand_mean = 50.0
block_effect = {'1': 1.0, '2': -1.0}

rows = []
for f in females:
    for m in males:
        for b_key, b_eff in block_effect.items():
            y = (grand_mean + gca_f[f] + gca_m[m] +
                 sca.get((f, m), 0) + b_eff +
                 np.random.normal(0, 2.0))
            rows.append({'母本': f, '父本': m, '区组': b_key, '产量': round(y, 2)})

df_ncii = pd.DataFrame(rows)
df_ncii.to_csv('data/NCII设计示例数据.csv', index=False, encoding='utf-8-sig')
print(f"NCII 数据: {len(df_ncii)} 条")

# =============================================================================
# Diallel 数据 (Griffing 方法4: F1无反交)
# =============================================================================
parents = ['P1', 'P2', 'P3', 'P4', 'P5']
# GCA 效应
gca_diallel = {'P1': 2.0, 'P2': 1.0, 'P3': -0.5, 'P4': -1.5, 'P5': 0.0}
# SCA 效应矩阵
sca_diallel = {
    ('P1', 'P2'): 1.0, ('P1', 'P3'): -0.5, ('P1', 'P4'): 0.8, ('P1', 'P5'): -1.2,
    ('P2', 'P3'): 1.5, ('P2', 'P4'): -1.0, ('P2', 'P5'): 0.3,
    ('P3', 'P4'): 0.5, ('P3', 'P5'): -0.8,
    ('P4', 'P5'): 1.2,
}
grand_mean_d = 45.0

rows_d = []
for i in range(len(parents)):
    for j in range(i + 1, len(parents)):
        p1, p2 = parents[i], parents[j]
        for b_key in ['1', '2']:
            y = (grand_mean_d + gca_diallel[p1] + gca_diallel[p2] +
                 sca_diallel.get((p1, p2), 0) + block_effect[b_key] +
                 np.random.normal(0, 1.5))
            rows_d.append({'亲本1': p1, '亲本2': p2, '区组': b_key, '产量': round(y, 2)})

df_diallel = pd.DataFrame(rows_d)
df_diallel.to_csv('data/Diallel设计示例数据.csv', index=False, encoding='utf-8-sig')
print(f"Diallel 数据: {len(df_diallel)} 条")

# 打印基本统计
print("\nNCII 品种均值:")
print(df_ncii.groupby('母本')['产量'].mean())
print(df_ncii.groupby('父本')['产量'].mean())

print("\nDiallel 组合均值:")
print(df_diallel.groupby(['亲本1', '亲本2'])['产量'].mean())
