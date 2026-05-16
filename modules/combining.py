"""
StatTools - 配合力分析模块（Combining Ability Analysis）

接口契约 v1.0 (2026-05-04)

包含两大类分析：
  1. NCII 设计 (North Carolina Design II) — 析因交配设计
  2. Diallel 双列杂交 (Griffing 方法1-4)

所有公共函数均返回 dict，统一数据结构。
"""

import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats
from typing import Optional, Union, Dict, Tuple


# =============================================================================
# 内部辅助
# =============================================================================

def _get_statsmodels():
    """延迟导入 statsmodels（自 utils.imports）"""
    from utils.imports import get_statsmodels
    return get_statsmodels()[:3]  # 只取前3项: sm, ols, anova_lm


def _anova_table(model, typ=2):
    """统一 ANOVA 表格式"""
    sm, ols_fn, anova_lm = _get_statsmodels()
    at = anova_lm(model, typ=typ)
    return at


# =============================================================================
# NCII 设计分析
# =============================================================================

class NCIIAnalysis:
    """
    North Carolina Design II (析因交配设计)

    原理：
        Y_ijk = μ + F_i + M_j + (F×M)_ij + B_k + ε_ijk
    GCA (一般配合力): F_i 和 M_j 的主效应
    SCA (特殊配合力): (F×M)_ij 的交互效应

    输入数据格式 (DataFrame)：
        female_col: 母本名称列
        male_col:   父本名称列
        response:   观测值/产量列
        block_col:  区组列（可选，不传则视为无区组）

    返回 dict 统一结构：
        {
            'anova': DataFrame,          # ANOVA 表
            'gca_female': DataFrame,     # 母本 GCA 效应
            'gca_male': DataFrame,       # 父本 GCA 效应
            'sca': DataFrame,            # SCA 效应矩阵
            'variance_components': dict, # 方差分量
            'gca_sca_ratio': float,      # GCA/SCA 方差比
        }
    """

    @staticmethod
    def ncii_anova(
        data: pd.DataFrame,
        female_col: str = '母本',
        male_col: str = '父本',
        block_col: Optional[str] = None,
        response: str = '产量'
    ) -> Dict:
        """NCII 方差分析 + GCA/SCA 效应 + 方差分量"""
        sm, ols_fn, anova_lm = _get_statsmodels()
        df = data.copy()

        # 确保因子类型
        df[female_col] = df[female_col].astype(str)
        df[male_col] = df[male_col].astype(str)
        if block_col:
            df[block_col] = df[block_col].astype(str)

        # 构建公式
        if block_col:
            formula = (f'Q("{response}") ~ C(Q("{female_col}")) + C(Q("{male_col}")) + '
                       f'C(Q("{female_col}")):C(Q("{male_col}")) + C(Q("{block_col}"))')
        else:
            formula = (f'Q("{response}") ~ C(Q("{female_col}")) + C(Q("{male_col}")) + '
                       f'C(Q("{female_col}")):C(Q("{male_col}"))')

        model = ols_fn(formula, data=df).fit()
        at = _anova_table(model, typ=2)

        # 提取各效应
        f_label = f'C(Q("{female_col}"))'
        m_label = f'C(Q("{male_col}"))'
        fm_label = f'C(Q("{female_col}")):C(Q("{male_col}"))'
        block_label = f'C(Q("{block_col}"))' if block_col else None

        # 提取均方
        def _ms(label):
            if label in at.index:
                return at.loc[label, 'mean_sq']
            return np.nan

        ms_f = _ms(f_label)
        ms_m = _ms(m_label)
        ms_fm = _ms(fm_label)

        # 残差均方
        res_row = at.loc[at.index.str.lower() == 'residual'] if len(at) > 1 else at.iloc[-1]
        ms_e = res_row['mean_sq'] if 'mean_sq' in res_row else res_row.iloc[-2]

        n_f = df[female_col].nunique()
        n_m = df[male_col].nunique()
        n_b = df[block_col].nunique() if block_col else 1
        n_r = len(df) / (n_f * n_m * n_b) if block_col else len(df) / (n_f * n_m)
        n_r = int(round(n_r))

        # 方差分量
        # σ²_e = MSE
        var_e = ms_e
        # σ²_FM = (MS_FM - MSE) / n_r
        var_fm = max(0, (ms_fm - ms_e) / n_r) if not np.isnan(ms_fm) else 0
        # σ²_M = (MS_M - MS_FM) / (n_f * n_r)
        var_m = max(0, (ms_m - ms_fm) / (n_f * n_r)) if not np.isnan(ms_m) else 0
        # σ²_F = (MS_F - MS_FM) / (n_m * n_r)
        var_f = max(0, (ms_f - ms_fm) / (n_m * n_r)) if not np.isnan(ms_f) else 0

        # GCA 方差 = σ²_F + σ²_M
        var_gca = var_f + var_m
        var_sca = var_fm
        gca_sca_ratio = var_gca / var_sca if var_sca > 0 else np.inf

        variance_components = {
            'σ²_F (母本GCA)': round(var_f, 4),
            'σ²_M (父本GCA)': round(var_m, 4),
            'σ²_GCA': round(var_gca, 4),
            'σ²_SCA (F×M)': round(var_sca, 4),
            'σ²_e (误差)': round(var_e, 4),
            'GCA/SCA 比值': round(gca_sca_ratio, 4),
        }

        # GCA 效应计算
        grand_mean = df[response].mean()
        female_means = df.groupby(female_col)[response].mean()
        male_means = df.groupby(male_col)[response].mean()

        gca_f = (female_means - grand_mean).reset_index()
        gca_f.columns = [female_col, 'GCA效应']
        gca_f['类型'] = '母本'

        gca_m = (male_means - grand_mean).reset_index()
        gca_m.columns = [male_col, 'GCA效应']
        gca_m['类型'] = '父本'

        # SCA 效应 = 组合均值 - 总均值 - 母本GCA - 父本GCA
        cross_means = df.groupby([female_col, male_col])[response].mean().reset_index()
        sca_results = []
        for _, row in cross_means.iterrows():
            f_name = row[female_col]
            m_name = row[male_col]
            cross_mean = row[response]
            fem_gca = female_means[f_name] - grand_mean
            male_gca = male_means[m_name] - grand_mean
            sca_effect = cross_mean - grand_mean - fem_gca - male_gca
            sca_results.append({
                female_col: f_name, male_col: m_name,
                '组合均值': round(cross_mean, 2),
                'SCA效应': round(sca_effect, 4),
            })
        sca_df = pd.DataFrame(sca_results)

        return {
            'anova': at,
            'gca_female': gca_f,
            'gca_male': gca_m,
            'sca': sca_df,
            'variance_components': variance_components,
            'gca_sca_ratio': gca_sca_ratio,
        }

    @staticmethod
    def ncii_gca_effects(
        data: pd.DataFrame,
        female_col: str = '母本',
        male_col: str = '父本',
        response: str = '产量'
    ) -> pd.DataFrame:
        """仅计算 GCA 效应（合并母本和父本）"""
        result = NCIIAnalysis.ncii_anova(data, female_col, male_col, response=response)
        gca_f = result['gca_female'].rename(columns={female_col: '亲本'})
        gca_m = result['gca_male'].rename(columns={male_col: '亲本'})
        combined = pd.concat([gca_f, gca_m], ignore_index=True)
        return combined.sort_values('GCA效应', ascending=False).reset_index(drop=True)

    @staticmethod
    def ncii_sca_effects(
        data: pd.DataFrame,
        female_col: str = '母本',
        male_col: str = '父本',
        response: str = '产量'
    ) -> pd.DataFrame:
        """仅计算 SCA 效应矩阵"""
        result = NCIIAnalysis.ncii_anova(data, female_col, male_col, response=response)
        return result['sca']


# =============================================================================
# Diallel 双列杂交分析 (Griffing 方法)
# =============================================================================

class DiallelAnalysis:
    """
    Griffing 双列杂交分析方法 (1956)

    四种方法：
        方法1: 亲本 + F1 + 反交
        方法2: 亲本 + F1 (无反交)
        方法3: F1 + 反交 (无亲本)
        方法4: F1 (无反交，无亲本) — 最常用

    两种模型：
        model='fixed':  固定效应模型 (模型I) — 推断仅限于亲本群体
        model='random': 随机效应模型 (模型II) — 推断扩展到亲本群体

    输入数据格式 (DataFrame):
        parent1_col: 亲本1名称列
        parent2_col: 亲本2名称列
        response:    观测值列
        block_col:   区组列（可选）
        reciprocal_col: 正反交标记列（可选，用于方法1/3）

    返回 dict 统一结构:
        {
            'anova': DataFrame,           # ANOVA 表
            'gca': DataFrame,             # GCA 效应
            'sca': DataFrame,             # SCA 效应矩阵
            'reciprocal': DataFrame,      # 反交效应（仅方法1/3）
            'variance_components': dict,  # 方差分量
        }
    """

    @staticmethod
    def _validate_diallel_data(data, parent1_col, parent2_col, method):
        """验证双列杂交数据的完整性"""
        df = data.copy()
        p1 = df[parent1_col].astype(str)
        p2 = df[parent2_col].astype(str)
        all_parents = sorted(set(p1.tolist() + p2.tolist()))
        n = len(all_parents)

        if method in (3, 4) and p1.eq(p2).any():
            raise ValueError(f"Griffing 方法{method} 不应包含自交组合 (亲本自身)")

        expected_pairs = n * (n - 1) // 2 if method in (2, 4) else n * (n - 1)
        actual_pairs = len(df.drop_duplicates(subset=[parent1_col, parent2_col]))
        if actual_pairs < expected_pairs:
            raise ValueError(f"数据不完整: 期望 {expected_pairs} 个组合，实际 {actual_pairs} 个")

        return df, all_parents, n

    @staticmethod
    def griffing1(
        data: pd.DataFrame,
        parent1_col: str = '亲本1',
        parent2_col: str = '亲本2',
        response: str = '产量',
        block_col: Optional[str] = None,
        model: str = 'fixed'
    ) -> Dict:
        """
        Griffing 方法1 — 亲本 + F1 + 反交

        包括亲本自交(n)、F1(n(n-1)/2)、反交(n(n-1)/2)，共 n² 个组合
        """
        return DiallelAnalysis._griffing_base(
            data, parent1_col, parent2_col, response, block_col, model, method=1
        )

    @staticmethod
    def griffing2(
        data: pd.DataFrame,
        parent1_col: str = '亲本1',
        parent2_col: str = '亲本2',
        response: str = '产量',
        block_col: Optional[str] = None,
        model: str = 'fixed'
    ) -> Dict:
        """
        Griffing 方法2 — 亲本 + F1 (无反交)

        包括亲本自交(n) + F1(n(n-1)/2)，共 n(n+1)/2 个组合
        """
        return DiallelAnalysis._griffing_base(
            data, parent1_col, parent2_col, response, block_col, model, method=2
        )

    @staticmethod
    def griffing3(
        data: pd.DataFrame,
        parent1_col: str = '亲本1',
        parent2_col: str = '亲本2',
        response: str = '产量',
        block_col: Optional[str] = None,
        model: str = 'fixed'
    ) -> Dict:
        """
        Griffing 方法3 — F1 + 反交 (无亲本)

        包括 F1(n(n-1)/2) + 反交(n(n-1)/2)，共 n(n-1) 个组合
        """
        return DiallelAnalysis._griffing_base(
            data, parent1_col, parent2_col, response, block_col, model, method=3
        )

    @staticmethod
    def griffing4(
        data: pd.DataFrame,
        parent1_col: str = '亲本1',
        parent2_col: str = '亲本2',
        response: str = '产量',
        block_col: Optional[str] = None,
        model: str = 'fixed'
    ) -> Dict:
        """
        Griffing 方法4 — F1 (无反交，无亲本) — 最常用

        仅包括 F1(n(n-1)/2) 个组合
        """
        return DiallelAnalysis._griffing_base(
            data, parent1_col, parent2_col, response, block_col, model, method=4
        )

    @classmethod
    def _griffing_base(
        cls, data, parent1_col, parent2_col, response, block_col, model, method
    ) -> Dict:
        """Griffing 分析通用实现"""
        df, all_parents, n = cls._validate_diallel_data(
            data, parent1_col, parent2_col, method
        )
        sm, ols_fn, anova_lm = _get_statsmodels()

        df[parent1_col] = df[parent1_col].astype(str)
        df[parent2_col] = df[parent2_col].astype(str)

        # 总均值
        grand_mean = df[response].mean()

        # 基于 Griffing(1956) 方法的 GCA/SCA 计算
        # 使用简化方法：GCA = 亲本行均值效应
        # 对于方法4，标准做法是：
        # GCA_i = (1/(n-2)) * Σⱼ(X_ij) - (2/(n*(n-2))) * Σⱼₖ(X_jk)
        # 其中 X_ij 是 i×j 组合的均值

        # 构建组合均值表
        if method in (1, 3):
            # 区分正反交时，组合是有序的 (i,j)
            cross_means = df.groupby([parent1_col, parent2_col])[response].mean().reset_index()
            # 只要 parent1 != parent2 的组合
            cross_f1 = cross_means[cross_means[parent1_col] != cross_means[parent2_col]]
        else:
            # 方法2/4 无反交，组合是无序的 (i,j) 且 i<j
            # 先取均值，再确保每个组合只出现一次
            def _make_pair(row):
                a, b = str(row[parent1_col]), str(row[parent2_col])
                return tuple(sorted([a, b]))
            df['_pair'] = df.apply(_make_pair, axis=1)
            cross_means = df.groupby('_pair')[response].mean().reset_index()
            cross_means[[parent1_col, parent2_col]] = pd.DataFrame(
                cross_means['_pair'].tolist(), index=cross_means.index
            )
            cross_f1 = cross_means

        # 计算 GCA 效应
        gca_results = {}
        for p in all_parents:
            if method in (1, 3):
                # 有方向：p 作为 parent1 的行均值
                row_sum = cross_f1.loc[cross_f1[parent1_col] == p, response].sum()
                row_count = len(cross_f1.loc[cross_f1[parent1_col] == p])
                # p 作为 parent2 的列均值
                col_sum = cross_f1.loc[cross_f1[parent2_col] == p, response].sum()
                col_count = len(cross_f1.loc[cross_f1[parent2_col] == p])
                total_sum = row_sum + col_sum
                total_count = row_count + col_count
                gca_effect = total_sum / total_count - grand_mean if total_count > 0 else 0
            else:
                method_label = {
                    2: (n + 2) / (n - 2),  # X_i. 系数
                    4: 1 / (n - 2),         # X_i. 系数
                }
                if method == 2:
                    row_sum = cross_f1.loc[
                        (cross_f1[parent1_col] == p) | (cross_f1[parent2_col] == p),
                        response
                    ].sum()
                    row_count = len(cross_f1.loc[
                        (cross_f1[parent1_col] == p) | (cross_f1[parent2_col] == p)
                    ])
                    total_sum = cross_f1[response].sum()
                    total_count = len(cross_f1)
                    if row_count > 0 and total_count > 0:
                        xi = row_sum / row_count
                        x_all = total_sum / total_count
                        # Griffing 方法2: GCA_i = (n+2)/(n-2) * (xi - x_all)
                        coeff = (n + 2) / (n - 2) if n > 2 else 1
                        gca_effect = coeff * (xi - x_all)
                    else:
                        gca_effect = 0
                else:  # method 4
                    row_sum = cross_f1.loc[
                        (cross_f1[parent1_col] == p) | (cross_f1[parent2_col] == p),
                        response
                    ].sum()
                    row_count = len(cross_f1.loc[
                        (cross_f1[parent1_col] == p) | (cross_f1[parent2_col] == p)
                    ])
                    total_sum = cross_f1[response].sum()
                    total_count = len(cross_f1)
                    if row_count > 0 and total_count > 0:
                        xi = row_sum / row_count
                        x_all = total_sum / total_count
                        # Griffing 方法4: GCA_i = 1/(n-2) * (xi - x_all)
                        coeff = 1 / (n - 2) if n > 2 else 1
                        gca_effect = coeff * (xi - x_all)
                    else:
                        gca_effect = 0
            gca_results[p] = round(gca_effect, 4)

        # SCA 效应 = 组合均值 - 总均值 - GCA_i - GCA_j
        sca_results = []
        for _, row in cross_f1.iterrows():
            p1 = row[parent1_col]
            p2 = row[parent2_col]
            cross_mean = row[response]
            gca_i = gca_results.get(p1, 0)
            gca_j = gca_results.get(p2, 0)
            sca = cross_mean - grand_mean - gca_i - gca_j
            sca_results.append({
                parent1_col: p1, parent2_col: p2,
                '组合均值': round(cross_mean, 2),
                'SCA效应': round(sca, 4),
            })
        sca_df = pd.DataFrame(sca_results)

        # 组装输出
        gca_df = pd.DataFrame({
            '亲本': list(gca_results.keys()),
            'GCA效应': list(gca_results.values()),
        }).sort_values('GCA效应', ascending=False).reset_index(drop=True)

        return {
            'method': f'Griffing 方法{method}',
            'model': model,
            'n_parents': n,
            'grand_mean': grand_mean,
            'gca': gca_df,
            'sca': sca_df,
            'variance_components': {},
        }

    @staticmethod
    def diallel_anova(
        data: pd.DataFrame,
        parent1_col: str = '亲本1',
        parent2_col: str = '亲本2',
        response: str = '产量',
        block_col: Optional[str] = None,
        reciprocal: bool = False,
    ) -> Dict:
        """
        双列杂交方差分析（通用）

        reciprocal=True: 区分正反交, reciprocal=False: 合并正反交
        """
        sm, ols_fn, anova_lm = _get_statsmodels()
        df = data.copy()
        df[parent1_col] = df[parent1_col].astype(str)
        df[parent2_col] = df[parent2_col].astype(str)

        if reciprocal:
            formula = (f'Q("{response}") ~ C(Q("{parent1_col}")) + C(Q("{parent2_col}")) + '
                       f'C(Q("{parent1_col}")):C(Q("{parent2_col}"))')
        else:
            def _cross_id(r):
                a, b = sorted([str(r[parent1_col]), str(r[parent2_col])])
                return f'{a}×{b}'
            df['_cross'] = df.apply(_cross_id, axis=1)
            formula = (f'Q("{response}") ~ C(Q("_cross"))')

        if block_col:
            df[block_col] = df[block_col].astype(str)
            formula += f' + C(Q("{block_col}"))'

        model = ols_fn(formula, data=df).fit()
        at = _anova_table(model, typ=2)

        return {
            'anova': at,
            'n_parents': len(set(df[parent1_col].tolist() + df[parent2_col].tolist())),
            'reciprocal': reciprocal,
        }
