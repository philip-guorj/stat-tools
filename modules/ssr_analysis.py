"""
StatTools - 区试报告分析模块（SSR Module）

包含多重比较、品种稳定性、对照比较、区试报告生成四大功能。
从 pages/03_方差分析.py 提取并重构，保持向后兼容。

接口契约版本: v1.0 (2026-05-04)
"""

import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats
from typing import Optional

# =============================================================================
# 延迟导入（自 utils.imports）
# =============================================================================
from utils.imports import get_statsmodels as _get_statsmodels


# =============================================================================
# 内部辅助函数
# =============================================================================

def _resolve_error_term(df_input, mse_val, df_e, n_g):
    """计算或验证误差均方和自由度"""
    if mse_val is not None and df_e is not None:
        return mse_val, df_e
    try:
        from statsmodels.formula.api import ols as _ols
        from statsmodels.stats.anova import anova_lm as _anova_lm
        df_tmp = df_input.copy()
        df_tmp.columns = ['y', 'group_col']
        formula = 'Q("y") ~ C(Q("group_col"))'
        model = _ols(formula, data=df_tmp).fit()
        at = _anova_lm(model, typ=2)
        res_row = at.loc[at.index.str.lower() == 'residual'] if len(at) > 1 else at.iloc[-1]
        if mse_val is None:
            mse_val = res_row['sum_sq'] / res_row['df'] if res_row['df'] > 0 else np.nan
        if df_e is None:
            df_e = int(res_row['df'])
    except Exception:
        pooled_var = df_input.groupby('g')['y'].var().mean()
        mse_val = pooled_var if not np.isnan(pooled_var) else np.nan
        df_e = len(df_input) - n_g
    return mse_val, df_e


def _build_ssr_table(n_g, df_e, alpha, method='duncan'):
    """构建 SSR/q 临界值表"""
    from scipy.stats import t as t_dist_fn
    try:
        from scipy.stats import studentized_range as ss_range
        has_sr = True
    except Exception:
        has_sr = False

    table = {}
    for r in range(2, n_g + 1):
        if has_sr:
            try:
                if method == 'snk':
                    val = ss_range.ppf(1 - alpha, r, df_e)
                else:
                    val = ss_range.ppf(1 - alpha, r, df_e)
                table[r] = val
            except Exception:
                t_approx = abs(t_dist_fn.ppf(alpha / (2 * r), df_e))
                table[r] = np.sqrt(2) * t_approx
        else:
            t_approx = abs(t_dist_fn.ppf(alpha / (2 * r), df_e))
            table[r] = np.sqrt(2) * t_approx
    return table


# =============================================================================
# SSRMultipleComparison — 多重比较分析
# =============================================================================

class SSRMultipleComparison:
    """多重比较核心类：Duncan SSR / SNK q / Tukey HSD / Fisher LSD + CLD"""

    @staticmethod
    def duncan_test(response_data, group_data, mse_val=None, df_e=None, alpha=0.05):
        """Duncan's 新复极差法多重比较"""
        df_input = pd.DataFrame({'y': response_data, 'g': group_data})
        means = df_input.groupby('g')['y'].mean()
        reps = df_input.groupby('g')['y'].count()
        names_sorted = means.sort_values(ascending=False).index.tolist()
        means_sorted = means.sort_values(ascending=False).values
        n_g = len(names_sorted)
        mse_val, df_e = _resolve_error_term(df_input, mse_val, df_e, n_g)
        if mse_val is None or np.isnan(mse_val) or df_e is None or df_e <= 0:
            return dict(pairs=pd.DataFrame(), mse=np.nan, df_e=0,
                        means_sorted=means_sorted, names_sorted=names_sorted, reps=reps)
        ssr_table = _build_ssr_table(n_g, df_e, alpha, method='duncan')
        results = []
        for i in range(n_g):
            for j in range(i + 1, n_g):
                g1, g2 = names_sorted[i], names_sorted[j]
                m1, m2 = means_sorted[i], means_sorted[j]
                diff = m1 - m2
                r_val = j - i + 1
                se = np.sqrt(mse_val / 2.0 * (1.0 / reps[g1] + 1.0 / reps[g2]))
                ssr_crit = ssr_table.get(r_val, ssr_table.get(2, 3.912))
                is_sig = abs(diff) >= ssr_crit * se
                results.append(dict(处理1=g1, 处理2=g2, 均值差=round(diff, 4),
                                    范围r=r_val, SSR临界值=round(ssr_crit, 4),
                                    LSR=round(ssr_crit * se, 4), 显著='Y' if is_sig else ''))
        return dict(pairs=pd.DataFrame(results), mse=float(mse_val), df_e=int(df_e),
                    means_sorted=means_sorted, names_sorted=names_sorted, reps=reps)

    @staticmethod
    def snk_test(response_data, group_data, mse_val=None, df_e=None, alpha=0.05):
        """SNK (Student-Newman-Keuls) q 检验"""
        df_input = pd.DataFrame({'y': response_data, 'g': group_data})
        means = df_input.groupby('g')['y'].mean()
        reps = df_input.groupby('g')['y'].count()
        names_sorted = means.sort_values(ascending=False).index.tolist()
        means_sorted = means.sort_values(ascending=False).values
        n_g = len(names_sorted)
        mse_val, df_e = _resolve_error_term(df_input, mse_val, df_e, n_g)
        if mse_val is None or np.isnan(mse_val) or df_e is None or df_e <= 0:
            return dict(pairs=pd.DataFrame(), mse=np.nan, df_e=0,
                        means_sorted=means_sorted, names_sorted=names_sorted, reps=reps)
        q_table = _build_ssr_table(n_g, df_e, alpha, method='snk')
        results = []
        for i in range(n_g):
            for j in range(i + 1, n_g):
                g1, g2 = names_sorted[i], names_sorted[j]
                m1, m2 = means_sorted[i], means_sorted[j]
                diff = m1 - m2
                p = j - i + 1
                se = np.sqrt(mse_val / 2.0 * (1.0 / reps[g1] + 1.0 / reps[g2]))
                q_crit = q_table.get(p, q_table.get(2, 3.912))
                is_sig = abs(diff) >= q_crit * se
                results.append(dict(处理1=g1, 处理2=g2, 均值差=round(diff, 4),
                                    范围p=p, q临界值=round(q_crit, 4),
                                    W=round(q_crit * se, 4), 显著='Y' if is_sig else ''))
        return dict(pairs=pd.DataFrame(results), mse=float(mse_val), df_e=int(df_e),
                    means_sorted=means_sorted, names_sorted=names_sorted, reps=reps)

    @staticmethod
    def tukey_test(data, groups, alpha=0.05):
        """Tukey HSD 包装 statsmodels"""
        sm, ols_fn, anova_lm_fn, pairwise_tukeyhsd = _get_statsmodels()
        tukey_obj = pairwise_tukeyhsd(endog=np.asarray(data), groups=np.asarray(groups), alpha=alpha)
        df_pairs = None
        try:
            if hasattr(tukey_obj, '_results_table') and tukey_obj._results_table is not None:
                df_pairs = pd.DataFrame(tukey_obj._results_table[1:], columns=tukey_obj._results_table[0])
        except Exception:
            pass
        if df_pairs is None:
            try:
                summary = tukey_obj.summary()
                if hasattr(summary, 'tables'):
                    t = summary.tables[1]
                    df_pairs = t.as_data() if hasattr(t, 'as_data') else pd.DataFrame(t)
            except Exception:
                pass
        if df_pairs is None:
            try:
                if hasattr(tukey_obj, '_multicomp') and hasattr(tukey_obj._multicomp, 'data'):
                    df_pairs = pd.DataFrame(data=tukey_obj._multicomp.data,
                                            columns=['group1', 'group2', 'meandiff', 'p-adj',
                                                     'lower', 'upper', 'reject'])
            except Exception:
                pass
        if df_pairs is None:
            df_pairs = pd.DataFrame()
        groups_unique = sorted(set(groups), key=lambda g: -np.mean(data[np.array(groups) == g]))
        means = {g: float(np.mean(data[np.array(groups) == g])) for g in groups_unique}
        return dict(pairs=df_pairs, groups_unique=groups_unique, means=means, tukey_obj=tukey_obj)

    @staticmethod
    def lsd_test(response_data, group_data, mse_val=None, df_e=None, alpha=0.05):
        """Fisher LSD 多重比较"""
        from scipy.stats import t as t_dist
        df_input = pd.DataFrame({'y': response_data, 'g': group_data})
        means = df_input.groupby('g')['y'].mean()
        reps = df_input.groupby('g')['y'].count()
        names_sorted = means.sort_values(ascending=False).index.tolist()
        means_sorted = means.sort_values(ascending=False).values
        n_g = len(names_sorted)
        mse_val, df_e = _resolve_error_term(df_input, mse_val, df_e, n_g)
        if mse_val is None or np.isnan(mse_val) or df_e is None or df_e <= 0:
            return dict(pairs=pd.DataFrame(), mse=np.nan, df_e=0,
                        means_sorted=means_sorted, names_sorted=names_sorted, reps=reps)
        t_crit = abs(t_dist.ppf(alpha / 2, df_e))
        results = []
        for i in range(n_g):
            for j in range(i + 1, n_g):
                g1, g2 = names_sorted[i], names_sorted[j]
                m1, m2 = means_sorted[i], means_sorted[j]
                diff = m1 - m2
                se = np.sqrt(mse_val * (1.0 / reps[g1] + 1.0 / reps[g2]))
                t_stat = diff / se if se > 0 else 0
                p_val = 2 * (1 - t_dist.cdf(abs(t_stat), df_e))
                lsd_val = t_crit * se
                is_sig = abs(diff) >= lsd_val
                results.append(dict(处理1=g1, 处理2=g2, 均值差=round(diff, 4),
                                    标准误=round(se, 4), LSD=round(lsd_val, 4),
                                    t值=round(t_stat, 3), p值=round(p_val, 4),
                                    显著='Y' if is_sig else ''))
        return dict(pairs=pd.DataFrame(results), mse=float(mse_val), df_e=int(df_e),
                    means_sorted=means_sorted, names_sorted=names_sorted, reps=reps)

    @staticmethod
    def compute_cld_letters(names_sorted, means_sorted, pair_results,
                            g1_col='处理1', g2_col='处理2', sig_col='显著'):
        """闭包法 CLD 字母标识计算"""
        import string as string_lib
        n = len(names_sorted)
        if n == 0:
            return {}
        non_sig = {g: set() for g in names_sorted}
        for _, row in pair_results.iterrows():
            g1, g2 = str(row[g1_col]), str(row[g2_col])
            sig_val = str(row.get(sig_col, '')).strip()
            # 统一识别多种显著标记：SSR模块产出'Y'，MET LSD产出'✓'/'✓✓'
            is_sig = sig_val in ('Y', '✓', '✓✓')
            if not is_sig:
                if g1 in non_sig:
                    non_sig[g1].add(g2)
                if g2 in non_sig:
                    non_sig[g2].add(g1)
        assigned = {g: set() for g in names_sorted}
        li = 0
        for i, gs in enumerate(names_sorted):
            grp = {gs}
            for j in range(i + 1, n):
                gc = names_sorted[j]
                if all(gc in non_sig.get(gm, set()) for gm in grp):
                    grp.add(gc)
            letter = string_lib.ascii_uppercase[li]
            for gm in grp:
                assigned[gm].add(letter)
            li += 1
        return {g: ''.join(sorted(assigned.get(g, set()))) for g in names_sorted}

    @staticmethod
    def generate_cld_table(names_sorted, means_sorted, cld_dict):
        """生成 CLD 汇总表格"""
        rows = []
        for i, g in enumerate(names_sorted):
            rows.append(dict(处理=g, 均值=round(float(means_sorted[i]), 4),
                             字母标识=cld_dict.get(g, '')))
        return pd.DataFrame(rows)


# =============================================================================
# StabilityAnalysis — 品种稳定性分析
# =============================================================================

class StabilityAnalysis:
    """品种稳定性分析（MET 多点环境数据）"""

    @staticmethod
    def shukla_variance(df, response, genotype, environment):
        """Shukla 稳定性方差 — 环境间标准差"""
        envs = sorted(df[environment].unique())
        genes = sorted(df[genotype].unique())
        results = []
        for g in genes:
            df_g = df[df[genotype] == g]
            g_mean = df_g[response].mean()
            g_std = df_g[response].std()
            g_cv = (g_std / g_mean * 100) if g_mean != 0 else 0
            env_means = []
            for e in envs:
                sub = df[(df[genotype]==g) & (df[environment]==e)]
                env_means.append(sub[response].mean() if len(sub) > 0 else np.nan)
            all_ranks = []
            for e in envs:
                sub = df[df[environment]==e]
                eg = sub.groupby(genotype)[response].mean().sort_values(ascending=False)
                if g in eg.index:
                    all_ranks.append(eg.index.tolist().index(g) + 1)
                else:
                    all_ranks.append(np.nan)
            avg_rank = np.nanmean(all_ranks) if any(not np.isnan(r) for r in all_ranks) else np.nan
            vr = [r for r in all_ranks if not np.isnan(r)]
            rng = f'{int(min(vr))}~{int(max(vr))}' if len(vr) >= 2 else ''
            ve = [v for v in env_means if not np.isnan(v)]
            sh_var = np.std(ve, ddof=1) if len(ve) >= 2 else 0
            mm = df.groupby(genotype)[response].mean().max()
            ys = g_mean / mm * 50 if mm > 0 else 0
            cvs = (df.groupby(genotype)[response].std() / df.groupby(genotype)[response].mean() * 100)
            cvs = cvs.replace([np.inf, -np.inf], 0).fillna(0)
            mc = cvs.max()
            ss = (1 - g_cv / mc) * 50 if mc > 0 else 25
            results.append({genotype: g, '总均值': round(g_mean, 2), '标准差': round(g_std, 2),
                            'CV%': round(g_cv, 2), '平均排名': round(avg_rank, 1) if not np.isnan(avg_rank) else '-',
                            '排名范围': rng, 'Shukla变异数': round(sh_var, 4),
                            '产量分': round(ys, 1), '稳定性分': round(ss, 1), '综合分': round(ys+ss, 1)})
        return pd.DataFrame(results)

    @staticmethod
    def eberhart_russell(df, response, genotype, environment):
        """Eberhart-Russell (1966) 回归稳定性"""
        envs = sorted(df[environment].unique())
        genes = sorted(df[genotype].unique())
        if len(envs) < 2:
            return None
        env_mean_all = df.groupby(environment)[response].mean()
        grand_mean = df[response].mean()
        env_idx = env_mean_all - grand_mean
        records = []
        for g in genes:
            y_arr, x_arr = [], []
            for e in envs:
                sub = df[(df[genotype]==g) & (df[environment]==e)]
                if len(sub) > 0:
                    y_arr.append(sub[response].mean())
                    x_arr.append(env_idx[e])
            if len(y_arr) >= 3:
                slope, intercept, rv, pv, se = scipy_stats.linregress(x_arr, y_arr)
                pred = intercept + slope * np.array(x_arr)
                dev = np.array(y_arr) - pred
                n = len(y_arr)
                s2d = np.sum(dev**2) / (n - 2) if n > 2 else 0
                gm = np.mean(y_arr)
                is_stable = abs(slope - 1) <= 0.2 and s2d < np.var(y_arr) * 0.3
                records.append({genotype: g, '均值': round(gm, 2),
                                '截距(a)': round(intercept, 4), '回归系数(b)': round(slope, 4),
                                's2d (偏差MS)': round(s2d, 4), 'R2': round(rv**2, 4),
                                '判断': '稳定' if is_stable else ('敏感' if slope > 1.2 else '迟钝'),
                                '推荐': ''})
        return dict(result=pd.DataFrame(records),
                    env_indices=pd.DataFrame({environment: env_idx.index,
                                               '环境均值': env_mean_all.values,
                                               '环境指数(Ij)': env_idx.values,
                                               '总均值': grand_mean}).reset_index(drop=True))

    @staticmethod
    def wricke_ecovalence(df, response, genotype, environment):
        """Wricke (1962) 生态价: W²ᵢ = Σⱼ(Yᵢⱼ - Ȳᵢ. - Ȳ.ⱼ + Ȳ..)²"""
        g_mean = df.groupby(genotype)[response].mean()
        e_mean = df.groupby(environment)[response].mean()
        t_mean = df[response].mean()
        results = []
        for g in sorted(df[genotype].unique()):
            w2 = 0.0
            for e in sorted(df[environment].unique()):
                sub = df[(df[genotype]==g) & (df[environment]==e)]
                if len(sub) > 0:
                    eff = sub[response].mean() - g_mean[g] - e_mean[e] + t_mean
                    w2 += eff**2
            results.append({genotype: g, '生态价(W²)': round(w2, 4), '均值': round(float(g_mean[g]), 2)})
        wdf = pd.DataFrame(results)
        tw = wdf['生态价(W²)'].sum()
        wdf['贡献率(%)'] = (wdf['生态价(W²)'] / tw * 100).round(2) if tw > 0 else 0
        return wdf.sort_values('生态价(W²)', ascending=True).reset_index(drop=True)

    @staticmethod
    def comprehensive_stability(df, response, genotype, environment, yield_weight=0.5):
        """综合稳定性评价"""
        sdf = StabilityAnalysis.shukla_variance(df, response, genotype, environment)
        er = StabilityAnalysis.eberhart_russell(df, response, genotype, environment)
        if er is not None:
            edf = er['result'][[genotype, '回归系数(b)', 's2d (偏差MS)']]
            return sdf.merge(edf, on=genotype, how='left')
        sdf['回归系数(b)'] = np.nan
        sdf['s2d (偏差MS)'] = np.nan
        return sdf


# =============================================================================
# CKComparison — 对照品种比较
# =============================================================================

class CKComparison:
    """对照品种(CK)比较分析"""

    @staticmethod
    def compare_with_ck(df, response, genotype, ck_name, environment=None):
        """与对照品种比较"""
        ck_data = df[df[genotype] == ck_name]
        if len(ck_data) == 0:
            raise ValueError(f'对照品种 "{ck_name}" 未在数据中找到')
        ck_mean = ck_data[response].mean()
        from scipy.stats import ttest_ind
        results = []
        for g in sorted(df[genotype].unique()):
            gd = df[df[genotype] == g][response]
            gm = gd.mean()
            diff = gm - ck_mean
            pct = (diff / ck_mean * 100) if ck_mean != 0 else 0
            sig = ''
            if g != ck_name and len(gd) > 1 and len(ck_data) > 1:
                try:
                    _, p = ttest_ind(gd, ck_data, equal_var=False)
                    sig = '**' if p < 0.01 else ('*' if p < 0.05 else '')
                except Exception:
                    pass
            results.append({genotype: g, '均值': round(gm, 2), 'CK均值': round(ck_mean, 2),
                            '差值': round(diff, 2), '增产率(%)': round(pct, 2),
                            '差异显著性': sig})
        return pd.DataFrame(results)

    @staticmethod
    def ck_rank_in_group(df, response, genotype, ck_name):
        """CK 排名位置"""
        gm = df.groupby(genotype)[response].mean().sort_values(ascending=False)
        if ck_name not in gm.index:
            raise ValueError(f'对照品种 "{ck_name}" 未找到')
        rank = gm.reset_index()[gm.reset_index()[genotype] == ck_name].index[0] + 1
        return dict(ck_rank=int(rank), total_genotypes=len(gm),
                    percentile=round((len(gm)-rank+1)/len(gm)*100, 1),
                    above_ck=gm[gm > gm[ck_name]].index.tolist())


# =============================================================================
# SSRReportGenerator — 区试报告生成
# =============================================================================

class SSRReportGenerator:
    """品种区域试验总结报告生成"""

    @staticmethod
    def generate_summary_report(df, config):
        """
        生成区试报告摘要。

        参数:
            df: 原始数据 DataFrame
            config: dict，需包含:
                - response, genotype, ck_name, yield_threshold, stability_threshold
                - ck_result: CKComparison.compare_with_ck() 的结果
                - stability_result: StabilityAnalysis 结果（可选）

        返回 dict:
            total_genotypes, promotion_candidates, pending_candidates,
            elimination_candidates (计数),
            report_table (完整评价表),
            promotion, elimination, pending (各候选列表 DataFrame)
        """
        response = config.get('response', '产量')
        genotype = config.get('genotype', '品种')
        ck_name = config.get('ck_name', '')
        yield_th = config.get('yield_threshold', 5.0)
        stab_th = config.get('stability_threshold', 100.0)
        ck_result = config.get('ck_result')
        stability_result = config.get('stability_result')

        # 品种均值排名
        if df is not None and not df.empty:
            geno_means = df.groupby(genotype)[response].mean().sort_values(ascending=False)
            all_genos = list(geno_means.index)
            n_total = len(all_genos)
            grand_mean = df[response].mean()
        else:
            geno_means = pd.Series(dtype=float)
            all_genos = []
            n_total = 0
            grand_mean = 0

        # 合并 CK 比较结果
        report_rows = []
        promo_list = []
        elim_list = []
        pending_list = []

        for i, g in enumerate(all_genos):
            row_data = {
                '品种': g,
                '均值': round(geno_means[g], 2),
                '排名': i + 1,
                '比CK增产(%)': '',
                '判定': '',
                '理由': '',
            }
            # CK 比较
            if ck_result is not None and not ck_result.empty:
                match = ck_result[ck_result.iloc[:, 0] == g]
                if len(match) > 0:
                    pct = match.iloc[0].get('增产率(%)', '')
                    row_data['比CK增产(%)'] = pct
                    if g != ck_name:
                        if pct != '' and float(pct) >= yield_th:
                            row_data['判定'] = '晋级'
                            row_data['理由'] = f'比对照增产 {float(pct):.1f}%'
                            promo_list.append(pd.DataFrame([row_data]))
                        elif pct != '' and float(pct) >= 0:
                            row_data['判定'] = '待定'
                            row_data['理由'] = f'增产 {float(pct):.1f}%，未达阈值'
                            pending_list.append(pd.DataFrame([row_data]))
                        else:
                            row_data['判定'] = '淘汰'
                            row_data['理由'] = f'比对照减产 {abs(float(pct)):.1f}%'
                            elim_list.append(pd.DataFrame([row_data]))
            # 稳定性
            if stability_result is not None and not stability_result.empty:
                smatch = stability_result[stability_result.iloc[:, 0] == g]
                if len(smatch) > 0:
                    if 'Shukla变异数' in smatch.columns:
                        row_data['Shukla变异数'] = smatch.iloc[0]['Shukla变异数']
                    if '回归系数(b)' in smatch.columns:
                        row_data['回归系数(b)'] = smatch.iloc[0]['回归系数(b)']
                    if '稳定性' in smatch.columns:
                        row_data['稳定性'] = smatch.iloc[0]['稳定性']

            report_rows.append(row_data)

        report_table = pd.DataFrame(report_rows) if report_rows else pd.DataFrame()

        # 组装计数字段
        n_promo = len(promo_list)
        n_pending = len(pending_list)
        n_elim = len(elim_list)

        promo_df = pd.concat(promo_list, ignore_index=True) if promo_list else pd.DataFrame()
        elim_df = pd.concat(elim_list, ignore_index=True) if elim_list else pd.DataFrame()
        pending_df = pd.concat(pending_list, ignore_index=True) if pending_list else pd.DataFrame()

        return dict(
            total_genotypes=n_total,
            promotion_candidates=n_promo,
            pending_candidates=n_pending,
            elimination_candidates=n_elim,
            report_table=report_table,
            promotion=promo_df,
            elimination=elim_df,
            pending=pending_df,
        )

    @staticmethod
    def judge_promotion(genotype_ranking, ck_name, threshold_percent=5.0):
        """晋级判定"""
        results = []
        if genotype_ranking is None or genotype_ranking.empty:
            return results
        col = genotype_ranking.columns[0]
        for _, row in genotype_ranking.iterrows():
            nm = row[col]
            if nm == ck_name:
                continue
            pct = row.get('增产率(%)', 0) if '增产率(%)' in genotype_ranking.columns else 0
            if pd.isna(pct):
                continue
            pct = float(pct)
            if pct >= threshold_percent:
                results.append(dict(品种=nm, 增产率=pct, 判定='晋级', 理由=f'增产 {pct:.1f}%'))
            else:
                results.append(dict(品种=nm, 增产率=pct, 判定='待定', 理由=f'增产 {pct:.1f}% 未达阈值'))
        return results


# =============================================================================
# 可视化渲染函数（供 pages/ 调用）
# =============================================================================

def render_cld_bar_chart(cld_df, name_col='处理', mean_col='均值', letter_col='字母标识'):
    """CLD 柱状图：按均值排序，柱顶标注字母"""
    import plotly.graph_objects as go
    import plotly.express as px
    df = cld_df.copy()
    # 确保按均值降序排列
    df = df.sort_values(mean_col, ascending=True)
    colors = px.colors.qualitative.Set2[:len(df)] + px.colors.qualitative.Set3 * 10
    colors = colors[:len(df)]

    fig = go.Figure()
    for i, (_, row) in enumerate(df.iterrows()):
        fig.add_trace(go.Bar(
            name=row[name_col],
            x=[row[mean_col]],
            y=[row[name_col]],
            orientation='h',
            marker_color=colors[i],
            text=f"{row[mean_col]:.1f}  {row.get(letter_col, '')}",
            textposition='outside',
            hovertemplate=f"<b>{row[name_col]}</b><br>均值: {row[mean_col]:.2f}<br>分组: {row.get(letter_col, '')}<extra></extra>",
        ))
    fig.update_layout(
        xaxis_title="均值",
        yaxis_title="",
        height=350 + 30 * len(df),
        showlegend=False,
        margin=dict(l=10, r=30, t=10, b=30),
    )
    return fig


def plot_stability_scatter(stability_df, genotype_col='品种', mean_col='总均值', var_col='Shukla变异数'):
    """稳定性散点图：X=产量均值, Y=Shukla变异数, 标注品种名"""
    import plotly.graph_objects as go
    df = stability_df.copy()
    if df.empty or var_col not in df.columns:
        return None
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df[mean_col], y=df[var_col],
        mode='markers+text',
        text=df[genotype_col],
        textposition="top center",
        marker=dict(size=10, color=df[var_col], colorscale='Viridis', showscale=True,
                    colorbar=dict(title=var_col)),
        hovertemplate=f"<b>%{{text}}</b><br>{mean_col}: %{{x:.2f}}<br>{var_col}: %{{y:.4f}}<extra></extra>",
    ))
    # 参考线：均值附近
    mean_x = df[mean_col].mean()
    fig.add_vline(x=mean_x, line_dash="dash", line_color="gray", opacity=0.5)
    fig.update_layout(
        xaxis_title=mean_col, yaxis_title=var_col,
        height=500,
        hovermode='closest',
    )
    return fig


def plot_er_regression(er_result_df, genotype_col='品种'):
    """Eberhart-Russell 回归系数柱状图"""
    import plotly.graph_objects as go
    df = er_result_df.copy()
    if df.empty or '回归系数(b)' not in df.columns:
        return None
    df = df.sort_values('回归系数(b)', ascending=True)
    fig = go.Figure()
    colors = ['#22c55e' if abs(v - 1) <= 0.2 else '#f59e0b' if v > 1.2 else '#ef4444'
              for v in df['回归系数(b)']]
    fig.add_trace(go.Bar(
        x=df['回归系数(b)'], y=df[genotype_col],
        orientation='h',
        marker_color=colors,
        text=df['回归系数(b)'].round(4),
        textposition='outside',
        hovertemplate=f"<b>%{{y}}</b><br>b = %{{x:.4f}}<br>R² = %{{customdata:.4f}}<extra></extra>",
        customdata=df['R2'].values,
    ))
    fig.add_vline(x=1, line_dash="dash", line_color="gray", line_width=1.5)
    fig.update_layout(
        xaxis_title="回归系数 (b)",
        yaxis_title="",
        height=350 + 30 * len(df),
        margin=dict(l=10, r=30, t=10, b=30),
    )
    return fig


def render_duncan_cld_chart(result_dict):
    """向后兼容：从 dict 结果渲染 CLD 图"""
    if not isinstance(result_dict, dict):
        return None
    pairs = result_dict.get('pairs')
    names_sorted = result_dict.get('names_sorted', [])
    means_sorted = result_dict.get('means_sorted', [])
    if pairs is None or len(names_sorted) == 0:
        return None
    cld = SSRMultipleComparison.compute_cld_letters(
        names_sorted, means_sorted, pairs
    )
    cld_df = SSRMultipleComparison.generate_cld_table(
        names_sorted, means_sorted, cld
    )
    return render_cld_bar_chart(cld_df)


def rename_anova_index(at):
    """格式化 ANOVA 表索引为中文"""
    rename_map = {
        'C(Q("genotype"))': '品种(基因型)', 'C(Q("group_col"))': '处理',
        'C(Q("environment"))': '环境', 'C(Q("block"))': '区组',
        'C(Q("rep"))': '重复', 'C(Q("col"))': '列',
        'C(Q("row"))': '行', 'C(Q("treatment"))': '处理',
        'C(Q("cultivar"))': '品种', 'C(Q("location"))': '地点',
        'Residual': '残差(误差)', 'residual': '残差(误差)',
    }
    new_idx = []
    for idx in at.index:
        found = False
        for k, v in rename_map.items():
            if k in str(idx):
                new_idx.append(v)
                found = True
                break
        if not found:
            new_idx.append(str(idx))
    at = at.copy()
    at.index = new_idx
    return at


def format_anova_table(at):
    """格式化 ANOVA 表为可读样式"""
    at = rename_anova_index(at)
    # 根据列数动态命名：statsmodels 可能返回 3~5 列
    col_map = {3: ['自由度(DF)', '平方和(SS)', '均方(MS)'],
               4: ['自由度(DF)', '平方和(SS)', '均方(MS)', 'F值'],
               5: ['自由度(DF)', '平方和(SS)', '均方(MS)', 'F值', 'P值']}
    n_cols = len(at.columns)
    if n_cols in col_map:
        at.columns = col_map[n_cols]
    # 兼容旧版：按位置重命名
    col_renames = {'df': '自由度(DF)', 'sum_sq': '平方和(SS)', 'mean_sq': '均方(MS)',
                   'F': 'F值', 'PR(>F)': 'P值'}
    at.rename(columns={c: col_renames.get(c.lower(), c) for c in at.columns if c.lower() in col_renames}, inplace=True)
    if 'P值' in at.columns:
        at['P值'] = at['P值'].apply(lambda x: f"{x:.6f}" if pd.notna(x) else '-')
        at['显著'] = at['P值'].apply(
            lambda x: '**' if x != '-' and float(x) < 0.01 else ('*' if x != '-' and float(x) < 0.05 else 'ns')
        )
    return at


