# 方差分析模块 - 田间试验设计专用

import os
import sys
import re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
import numpy as np
from scipy import stats
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import warnings
warnings.filterwarnings('ignore')

from utils.data_manager import get_current_dm
from utils.styles import inject_css
from utils.visitor_logger import log_visit
from billing.billing import require_auth, check_billing, can_download

# 导入重构后的公共算法模块
try:
    from modules.ssr_analysis import SSRMultipleComparison as _SSRMC
    _HAS_SSR_MODULE = True
except ImportError:
    _HAS_SSR_MODULE = False


# ========== 统一延迟导入（自 utils.imports）==========
from utils.imports import (
    get_statsmodels as _get_statsmodels,
    get_ols as _get_ols,
    get_anova_lm as _get_anova_lm,
    get_tukey as _get_tukey,
)


# ========== 兼容性辅助函数（必须在其他函数之前定义）==========

@st.cache_data
def _detect_numeric_categorical(df, numeric_cols=None, exclude_cols=None):
    """检测数字型分类变量（如区组用 1,2,3 表示）

    判定标准：
    - 所有值都是整数
    - 唯一值数量 >= 2
    - 不在 exclude_cols 中

    注意：使用 tuple(exclude_cols) 作为缓存键，确保 list 参数可 hash。
    """
    if numeric_cols is None:
        numeric_cols = tuple(df.select_dtypes(include=[np.number]).columns.tolist())
    else:
        numeric_cols = tuple(numeric_cols)
    if exclude_cols is None:
        exclude_cols = ()
    else:
        exclude_cols = tuple(exclude_cols)
    result = []
    for col in numeric_cols:
        if col in exclude_cols:
            continue
        uv = df[col].dropna().unique()
        if len(uv) >= 2 and all(float(v).is_integer() for v in uv):
            result.append(col)
    return result


def _auto_detect_design(df, design_options):
    """根据数据结构自动推断最可能的试验设计类型，返回 design_options 中的 index。

    推断策略（基于数据结构特征，优先级从高到低）：
    1. 间比法/对比法：无区组/重复列，有位置/小区号列，CK按规律出现
    2. 增广设计：有区组列，类型列含对照+测试；对照有重复、处理无重复
    3. Alpha/不完全区组：同时有"不完全区组"和"完整区组"列
    4. MET多点联合分析：有环境/地点列 + 重复/区组 + 品种/处理列
    5. 裂区设计：有"主处理"+"副处理"列
    6. 拉丁方设计：行区组+列区组，且处理数=行数=列数
    7. 两因素析因设计：有重复/区组，另有至少两个独立的分组变量
    8. 随机区组(RCBD)：有区组/重复列，只有一个处理列
    9. 完全随机(CRD)：无区组/重复列，仅有处理+数值列
    """
    cols = [c.strip() for c in df.columns.tolist()]

    # 分类列检测
    _nc_cat = _detect_numeric_categorical(df, df.select_dtypes(include=[np.number]).columns.tolist())
    cat_cols = df.select_dtypes(include=['object', 'category']).columns.tolist() + _nc_cat

    # --- 辅助函数 ---
    def has_exact(pattern):
        """精确匹配列名"""
        return pattern in cols

    def has_keyword(kw):
        """列名包含关键词"""
        return any(kw in c for c in cols)

    def col_vals(col_name):
        """获取某列的去重值集合"""
        if col_name not in df.columns:
            return set()
        return set(df[col_name].dropna().astype(str).str.strip().unique())

    def find_block_col():
        """找区组/重复列（排除完整区组/不完全区组）"""
        for c in cols:
            if ('区组' in c or '重复' in c) and '不完全' not in c and '完整' not in c:
                return c
        return None

    def find(pattern):
        return next((i for i, o in enumerate(design_options) if pattern in o), None)

    # --- 预计算特征 ---
    _block_col = find_block_col()
    _has_block = _block_col is not None
    _has_ib = has_exact('不完全区组')
    _has_full_rep = has_exact('完整区组')
    _has_rep_exact = has_exact('重复')
    _has_position = has_exact('位置') or has_exact('小区号')

    # 类型列：值含"对照"/"处理"/"测试"/"CK"等
    type_cols = [c for c in cat_cols if col_vals(c) & {'对照', '处理', '测试', 'CK', 'Test', 'Check'}]
    _has_type = len(type_cols) > 0

    # 处理列（精确匹配）
    _trt_col = None
    for c in cat_cols:
        if c in ('处理', '品种', '名称'):
            _trt_col = c
            break

    _has_ck = any(any('CK' in v for v in col_vals(c)) for c in cat_cols)

    # === 1. 间比法/对比法 ===
    # 无区组/重复列，有位置/小区号列，CK出现
    if _has_position and not _has_block and not _has_ib and not _has_full_rep:
        if _has_type or _has_ck:
            i = find('间比')
            if i is not None:
                return i

    # === 2. 增广设计 ===
    # 有区组列，类型列含对照+测试
    for tc in type_cols:
        if col_vals(tc) >= {'对照', '测试'} and _has_block:
            i = find('增广')
            if i is not None:
                return i

    # === 3. Alpha/不完全区组 ===
    # 同时有"不完全区组"和"完整区组"列
    if _has_ib and _has_full_rep:
        i = find('Alpha')
        if i is None:
            i = find('不完全')
        if i is not None:
            return i

    # === 4. MET多点联合分析 ===
    # 有环境/地点列 + 区组/重复 + 品种列
    has_env = has_keyword('环境') or has_keyword('地点')
    if has_env and _has_block and (_trt_col is not None or has_exact('品种')):
        i = find('MET')
        if i is not None:
            return i

    # === 5. 裂区设计 ===
    # 精确匹配"主处理"+"副处理"列
    if has_exact('主处理') and has_exact('副处理'):
        i = find('裂区')
        if i is None:
            i = find('Split')
        if i is not None:
            return i

    # === 6. 拉丁方设计 ===
    # 有"行区组"+"列区组"，处理数=行数=列数
    if has_exact('行区组') and has_exact('列区组') and _trt_col:
        trt_n = df[_trt_col].nunique()
        row_n = df['行区组'].nunique()
        col_n = df['列区组'].nunique()
        if trt_n == row_n == col_n and trt_n >= 3:
            i = find('拉丁')
            if i is None:
                i = find('Latin')
            if i is not None:
                return i

    # === 7. 两因素析因设计 ===
    # 有区组/重复，另有至少两个独立分组变量（排除类型列和区组列）
    non_factor_cols = set(type_cols)
    if _block_col:
        non_factor_cols.add(_block_col)
    factor_only = [c for c in cat_cols if c not in non_factor_cols]
    if _has_block and len(factor_only) >= 2:
        i = find('析因')
        if i is not None:
            return i

    # === 8. 随机完全区组(RCBD) ===
    # 有区组列，只有一个处理列，无更复杂特征
    if _has_block and not has_exact('主处理') and not has_exact('行区组') and not has_exact('列区组'):
        if not _has_ib and not _has_full_rep:
            i = find('RCBD')
            if i is not None:
                return i

    # === 9. 完全随机设计(CRD) ===
    # 无区组/重复列，有处理列
    if not _has_block and not _has_ib and not _has_full_rep and not _has_rep_exact:
        if _trt_col is not None or has_exact('处理'):
            i = find('CRD')
            if i is not None:
                return i

    return -1  # 无法判断，回退到默认(index=1, RCBD)


def _auto_match(df, all_categorical, match_rules, exclude=None):
    """通用列名自动匹配：按优先级规则从 all_categorical 中找到第一个匹配项。

    Args:
        df: DataFrame（用于值域检测）
        all_categorical: 全部分类变量候选列表
        match_rules: 匹配规则列表，每条规则为 (精确匹配列表, 模糊关键字列表, 值域匹配函数(可选))
            例: (['处理', '品种', '名称'], ['处理', '品种'], None)
        exclude: 需要排除的列名列表

    Returns:
        匹配到的列名，或 None
    """
    if exclude is None:
        exclude = []
    pool = [c for c in all_categorical if c not in exclude]

    for exact_list, fuzzy_list, val_check in match_rules:
        for col in pool:
            if val_check:
                vals = set(df[col].dropna().astype(str).str.strip().unique())
                if val_check(vals):
                    return col
            if col in exact_list:
                return col
            for kw in fuzzy_list:
                if kw in col:
                    return col
    return None


def _safe_index(options, target):
    """安全获取 target 在 options 中的 index，找不到返回 0"""
    if target and target in options:
        return options.index(target)
    return 0


# 处理变量的匹配规则（复用于多种设计）
_TRT_RULES = [
    (['处理', '品种', '名称'], ['处理', '品种'], None),
]

# 区组/重复变量的匹配规则
_BLOCK_RULES = [
    (['区组', '重复'], ['区组', '重复'], None),
]

# 环境变量的匹配规则
_ENV_RULES = [
    (['环境', '地点', '年份', '地点×年份', '年份×地点'], ['环境', '地点', '年份'], None),
]

# 完整区组的匹配规则
_REP_RULES = [
    (['完整区组', '区组'], ['完整区组'], None),
]

# 不完全区组的匹配规则
_IB_RULES = [
    (['不完全区组', '子区组'], ['不完全区组', '子区组'], None),
]

# 类型列的匹配规则
_TYPE_RULES = [
    (['类型'], ['类型'],
     lambda vals: bool(vals & {'对照', '处理', 'CK', 'Check'})),
]

# 行区组的匹配规则
_ROW_RULES = [
    (['行区组', '行'], ['行区组'], None),
]

# 列区组的匹配规则
_COL_RULES = [
    (['列区组', '列'], ['列区组'], None),
]



def _display_tukey_result(tukey_obj, alpha=0.05):
    """显示Tukey HSD结果（含字母标识），兼容不同版本的statsmodels"""
    df_tukey = None

    try:
        if hasattr(tukey_obj, '_results_table') and tukey_obj._results_table is not None:
            df_tukey = pd.DataFrame(tukey_obj._results_table[1:],
                                    columns=tukey_obj._results_table[0])
    except Exception:
        pass

    if df_tukey is None:
        try:
            summary = tukey_obj.summary()
            if hasattr(summary, 'tables'):
                t = summary.tables[1]
                df_tukey = t.as_data() if hasattr(t, 'as_data') else pd.DataFrame(t)
        except Exception:
            pass

    if df_tukey is None:
        try:
            if hasattr(tukey_obj, "_multicomp") and hasattr(tukey_obj._multicomp, "data"):
                df_tukey = pd.DataFrame(data=tukey_obj._multicomp.data,
                                        columns=['group1','group2','meandiff','p-adj',

                                                 'lower','upper','reject'])
        except Exception:
            pass

    if df_tukey is not None:
        with st.expander("Tukey HSD \u6210\u5bf9\u6bd4\u8f83\u8be6\u60c5", expanded=False):
            st.dataframe(df_tukey)
        _render_cld_letters(tukey_obj, df_tukey, alpha)
    else:
        st.info("Tukey HSD \u68c0\u9a8c\u5df2\u5b8c\u6210")


def _render_cld_letters(tukey_obj, df_tukey, alpha=0.05):
    """显示Tukey HSD的CLD字母标识（闭包法 v3）"""
    import string
    groups = sorted(tukey_obj.groupsunique)
    if not groups:
        return

    # 构建不显著邻接表
    non_sig = {g: set() for g in groups}
    col_names = list(df_tukey.columns)
    reject_col = 'reject' if 'reject' in col_names else col_names[-1]

    for _, row in df_tukey.iterrows():
        g1, g2 = str(row.iloc[0]), str(row.iloc[1])
        try:
            rej_val = row.get(reject_col, True)
            if rej_val == False or str(rej_val) == 'False':
                non_sig[g1].add(g2)
                non_sig[g2].add(g1)
        except Exception:
            pass

    group_means = {g: float(np.mean(tukey_obj.data[tukey_obj.groups == g])) for g in groups}
    sorted_groups = sorted(groups, key=lambda x: group_means[x], reverse=True)

    # ── 闭包法 CLD v3：每个最大不显著团对应一个字母，团内所有成员共享 ──
    assigned_letters = {g: set() for g in sorted_groups}
    letter_idx = 0

    for i, g_seed in enumerate(sorted_groups):
        group = {g_seed}
        for j in range(i + 1, len(sorted_groups)):
            g_candidate = sorted_groups[j]
            if all(g_candidate in non_sig.get(gm, set()) for gm in group):
                group.add(g_candidate)

        # 团中所有成员共享同一个字母（核心修正）
        cur_letter = string.ascii_uppercase[letter_idx]
        for gm in group:
            assigned_letters[gm].add(cur_letter)
        letter_idx += 1

    # 组装输出
    cld_rows = []
    for g in sorted_groups:
        letters = ''.join(sorted(assigned_letters.get(g, set())))
        cld_rows.append({'基因型/处理': g, '均值': round(group_means[g], 2), '字母标识': letters})

    df_cld = pd.DataFrame(cld_rows)

    c1, c2 = st.columns([2, 3])
    with c1:
        st.markdown(f'**显著性字母标识** (不同字母 -> p<{alpha}):')
        st.dataframe(df_cld.reset_index(drop=True), use_container_width=True)

    with c2:
        fig_cld = go.Figure()
        means_vals = [group_means[g] for g in sorted_groups]
        letters_display = [''.join(sorted(assigned_letters.get(g, set()))) for g in sorted_groups]
        fig_cld.add_trace(go.Bar(
            x=means_vals, y=sorted_groups, orientation='h',
            text=letters_display, textposition='outside',
            marker_color='#3498db'
        ))
        fig_cld.update_layout(
            title='多重比较字母标识图',
            xaxis_title='均值',
            height=max(300, len(sorted_groups)*40 + 80),
            showlegend=False, yaxis=dict(autorange='reversed')
        )
        st.plotly_chart(fig_cld, use_container_width=True, key='met_cld')


def _get_alpha():
    """获取当前多重比较的显著性水平"""
    return st.session_state.get("_anova_alpha", 0.05)


def _alpha_selector():
    """在多重比较部分之前显示显著性水平选择器（醒目样式）"""
    alpha_level = st.selectbox(
        "🔬 多重比较显著性水平",
        [0.05, 0.01],
        format_func=lambda x: f"p < {x:.2f}",
        key="anova_alpha_level",
        help="选择多重比较的显著性水平，字母标识文字将与此一致"
    )
    st.session_state["_anova_alpha"] = alpha_level


def _duncan_multiple_comparison(response_data, group_data, mse_val=None, df_e=None, alpha=None):
    """
    通用 Duncan's 新复极差法多重比较（委托 modules/ssr_analysis.py）

    参数见旧函数，保持完全向后兼容。
    返回: (df_result, mse_val, df_e, means_sorted, group_names_sorted, reps)
    """
    if alpha is None:
        alpha = _get_alpha()
    if not _HAS_SSR_MODULE:
        return _duncan_fallback(response_data, group_data, mse_val, df_e, alpha)

    from modules.ssr_analysis import SSRMultipleComparison as _SSRMC_2
    result = _SSRMC_2.duncan_test(response_data, group_data, mse_val=mse_val, df_e=df_e, alpha=alpha)

    df_result = result['pairs'].copy()
    # 转换显著标记: 模块用 'Y', 旧代码用 '✓'
    if '显著' in df_result.columns:
        df_result['显著'] = df_result['显著'].replace({'Y': '✓', '': ''})
    return df_result, result['mse'], result['df_e'], result['means_sorted'], result['names_sorted'], result['reps']


def _duncan_fallback(response_data, group_data, mse_val=None, df_e=None, alpha=0.05):
    """备用实现（不使用 modules 时）"""
    st.warning("⚠️ modules/ssr_analysis.py 不可用，使用内置算法")
    from scipy.stats import t as t_dist_fn
    try:
        from scipy.stats import studentized_range as ss_range
        has_sr = True
    except Exception:
        has_sr = False
    df_input = pd.DataFrame({'y': response_data, 'g': group_data})
    means = df_input.groupby('g')['y'].mean()
    reps = df_input.groupby('g')['y'].count()
    names_sorted = means.sort_values(ascending=False).index.tolist()
    means_sorted = means.sort_values(ascending=False).values
    n_g = len(names_sorted)
    if mse_val is None or df_e is None:
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
            df_e = len(response_data) - n_g
    if mse_val is None or np.isnan(mse_val) or df_e is None or df_e <= 0:
        st.warning("⚠️ 无法估计误差均方或误差自由度，跳过 Duncan 多重比较。")
        return None, mse_val, df_e, means_sorted, names_sorted, reps
    ssr_table = {}
    for r in range(2, n_g + 1):
        if has_sr:
            try:
                ssr_table[r] = ss_range.ppf(1 - alpha, r, df_e)
            except Exception:
                t_approx = abs(t_dist_fn.ppf(alpha / (2 * r), df_e))
                ssr_table[r] = np.sqrt(2) * t_approx
        else:
            t_approx = abs(t_dist_fn.ppf(alpha / (2 * r), df_e))
            ssr_table[r] = np.sqrt(2) * t_approx
    results = []
    for i in range(n_g):
        for j in range(i + 1, n_g):
            g1, g2 = names_sorted[i], names_sorted[j]
            m1, m2 = means_sorted[i], means_sorted[j]
            diff = m1 - m2
            r_val = j - i + 1
            se = np.sqrt(mse_val / 2.0 * (1.0 / reps[g1] + 1.0 / reps[g2]))
            ssr_crit = ssr_table.get(r_val, ssr_table.get(2, 3.912))
            lsr_val = ssr_crit * se
            is_sig = abs(diff) >= lsr_val
            results.append({'处理1': g1, '处理2': g2, '均值差': round(diff, 4),
                            '范围(r)': r_val, 'SSR临界值': round(ssr_crit, 4),
                            'LSR': round(lsr_val, 4), '显著': '✓' if is_sig else ''})
    return pd.DataFrame(results), mse_val, df_e, means_sorted, names_sorted, reps


def _render_duncan_cld(names_sorted, means_sorted, duncan_results, title="Duncan CLD"):
    """基于 Duncan 比较结果渲染 CLD 字母标识图（委托 modules/ssr_analysis.py）"""
    n_g = len(names_sorted)
    if n_g == 0 or duncan_results is None or len(duncan_results) == 0:
        return

    if _HAS_SSR_MODULE:
        from modules.ssr_analysis import SSRMultipleComparison as _SSRMC_2
        # 判断显著列: 旧代码用 '✓', 模块用 'Y'
        has_check = (duncan_results['显著'] == '✓').any()
        if has_check:
            sig_col_for_mod = duncan_results['显著'].replace({'✓': 'Y', '': ''}).values
            pairs_mod = duncan_results.copy()
            pairs_mod['显著'] = sig_col_for_mod
        else:
            pairs_mod = duncan_results
        cld_dict = _SSRMC_2.compute_cld_letters(
            names_sorted, means_sorted, pairs_mod,
            g1_col='处理1', g2_col='处理2', sig_col='显著'
        )
    else:
        # fallback: 直接用本地算法
        import string
        non_sig = {g: set() for g in names_sorted}
        for _, row in duncan_results.iterrows():
            g1, g2 = str(row['处理1']), str(row['处理2'])
            if row['显著'] != '✓' and row['显著'] != 'Y':
                non_sig[g1].add(g2)
                non_sig[g2].add(g1)
        assigned_letters = {g: set() for g in names_sorted}
        letters_list = list(string.ascii_uppercase)
        letter_idx = 0
        for i in range(n_g):
            g = names_sorted[i]
            if not assigned_letters[g]:
                clique = [g]
                for j in range(i + 1, n_g):
                    candidate = names_sorted[j]
                    if all(candidate in non_sig[m] for m in clique):
                        clique.append(candidate)
                new_letter = letters_list[letter_idx] if letter_idx < len(letters_list) else str(letter_idx)
                letter_idx += 1
                for member in clique:
                    assigned_letters[member].add(new_letter)
        cld_dict = {g: ''.join(sorted(assigned_letters.get(g, set()))) for g in names_sorted}

    display_data = []
    for i in range(n_g):
        g = names_sorted[i]
        letter_str = cld_dict.get(g, '')
        display_data.append({'处理': g, '均值': round(means_sorted[i], 4), '分组': letter_str})

    fig = go.Figure(data=[go.Table(
        header=dict(values=['处理', '均值', '分组'],
                    fill_color='#4472C4', font=dict(color='white', size=13), align='center'),
        cells=dict(values=[[d['处理'] for d in display_data],
                           [d['均值'] for d in display_data],
                           [d['分组'] for d in display_data]],
                   fill_color=[['#f0f4ff' if i % 2 == 0 else 'white' for i in range(n_g)] * 3],
                   align='center', font=dict(size=12))
    )])
    fig.update_layout(title=title, height=max(250, n_g * 35 + 60), margin=dict(t=40, b=20))
    st.plotly_chart(fig, use_container_width=True)


def _display_duncan_result(df_result, mse_val, df_e, names_sorted, means_sorted, reps, title_prefix=""):
    """显示 Duncan 多重比较完整结果（表格+CLD）"""
    if df_result is None:
        return
    sig_count = sum(1 for r in df_result['显著'] if r == '✓')
    st.markdown(f"#### {title_prefix}Duncan's 新复极差法")
    st.caption(
        f"**说明**: Duncan's New MRT (SSR法)，"
        f"误差均方(MSE={mse_val:.4f}, df={df_e})，"
        f"保护水平随比较范围r递增(α_r = 1-(1-0.05)^(r-1))。"
        f" 共 {len(df_result)} 对比较，{sig_count} 对差异显著。"
    )
    st.dataframe(df_result.reset_index(drop=True), use_container_width=True)
    _render_duncan_cld(names_sorted, means_sorted, df_result, title=f"{title_prefix}Duncan CLD")


def _render_met_cld(geno_names_sorted, emmeans_geno, compare_results, method_name='LSD', alpha=0.05):
    """基于多重比较结果渲染MET基因型CLD字母标识（委托 modules/ssr_analysis.py）"""
    n = len(geno_names_sorted)
    if n == 0:
        return

    if _HAS_SSR_MODULE:
        # 将 compare_results (list of dict) 转为 DataFrame
        pairs_df = pd.DataFrame(compare_results)
        from modules.ssr_analysis import SSRMultipleComparison as _SSRMC_2
        if len(pairs_df) > 0 and '品种1' in pairs_df.columns and '品种2' in pairs_df.columns:
            cld_dict = _SSRMC_2.compute_cld_letters(
                geno_names_sorted,
                np.array([emmeans_geno[g] for g in geno_names_sorted]),
                pairs_df,
                g1_col='品种1', g2_col='品种2', sig_col='显著'
            )
        else:
            cld_dict = {g: '' for g in geno_names_sorted}
    else:
        # fallback: 闭包法 v3
        import string
        non_sig = {g: set() for g in geno_names_sorted}
        for r in compare_results:
            sig_mark = r.get('显著', '')
            if sig_mark.strip() == '':
                g1, g2 = r['品种1'], r['品种2']
                non_sig[g1].add(g2)
                non_sig[g2].add(g1)
        assigned_letters = {g: set() for g in geno_names_sorted}
        letter_idx = 0
        for i, g_seed in enumerate(geno_names_sorted):
            group = {g_seed}
            for j in range(i + 1, len(geno_names_sorted)):
                g_cand = geno_names_sorted[j]
                if all(g_cand in non_sig.get(gm, set()) for gm in group):
                    group.add(g_cand)
            cur_letter = string.ascii_uppercase[letter_idx]
            for gm in group:
                assigned_letters[gm].add(cur_letter)
            letter_idx += 1
        cld_dict = {g: ''.join(sorted(assigned_letters.get(g, set()))) for g in geno_names_sorted}

    # Step 3: assemble output
    cld_rows = []
    for g in geno_names_sorted:
        letters = cld_dict.get(g, '')
        cld_rows.append({'基因型': g, '均值': round(emmeans_geno[g], 2), '字母标识': letters})

    df_cld = pd.DataFrame(cld_rows)

    col_t, col_b = st.columns([2, 3])
    with col_t:
        st.markdown(f'**显著性字母标识（{method_name}）** — 不同字母表示 p<{alpha} 差异显著:')
        st.dataframe(df_cld.reset_index(drop=True), use_container_width=True)
    with col_b:
        fig_m = go.Figure()
        means_v = [emmeans_geno[g] for g in geno_names_sorted]
        let_d = [cld_dict.get(g, '') for g in geno_names_sorted]
        fig_m.add_trace(go.Bar(
            x=means_v, y=geno_names_sorted, orientation='h',
            text=let_d, textposition='outside',
            marker_color='#e74c3c' if method_name != 'LSD' else '#3498db'
        ))
        fig_m.update_layout(
            title=f'MET基因型多重比较字母标识图（基于联合模型{method_name}）',
            xaxis_title='调整均值',
            height=max(300, len(geno_names_sorted)*40 + 80),
            showlegend=False, yaxis=dict(autorange='reversed')
        )
        st.plotly_chart(fig_m, use_container_width=True, key=f'met_{method_name.lower()}_cld')



def render_anova():
    require_auth()
    log_visit("方差分析")
    inject_css()
    st.markdown('<div class="section-header">📊 方差分析 (ANOVA)</div>', unsafe_allow_html=True)

    
    # 功能简介下拉菜单
    with st.expander("📖 功能简介与使用指南", expanded=False):
        st.markdown("""
        **方差分析 (ANOVA)** 用于比较三个或更多组间的均值差异，是田间试验设计的核心分析方法。
        
        本系统支持以下 9 种试验设计的方差分析：

        | 序号 | 试验设计 | 适用场景 | 数据列要求 |
        |:---:|---------|---------|---------|
        | 1 | 完全随机设计 (CRD) | 试验单元间环境差异不大（温室、实验室、培养箱） | 处理因子 + 观测值 |
        | 2 | 随机区组设计 (RCBD) | 存在单一方向环境梯度（如土壤肥力渐变） | 处理 + 区组 + 观测值 |
        | 3 | 拉丁方设计 | 存在两个方向的环境梯度（行、列均有差异） | 处理 + 行区组 + 列区组 + 观测值 |
        | 4 | 裂区设计 | 主处理需大面积实施，副处理在小面积实施 | 主处理 + 副处理 + 区组 + 观测值 |
        | 5 | 两因素析因设计 | 两个因子地位平等，需研究交互效应 | 因子A + 因子B + 观测值 |
        | 6 | MET多点联合分析 | 多地点、多年份的品种区域试验 | 品种 + 环境 + 重复 + 观测值 |
        | 7 | Alpha/不完全区组设计 | 品种数多无法容纳在一个完全区组中 | 处理 + 不完全区组 + 完整区组 + 观测值 |
        | 8 | 增广设计 | 对照有重复、测试材料无重复的早期筛选试验 | 处理 + 区组(可选) + 类型(对照/测试) + 观测值 |
        | 9 | 间比法/对比法分析 | 育种早期阶段，对照间隔插入，用相对产量比较 | 处理 + 位置(必填) + 类型(推荐) + 观测值（需含 CK1） |
        """)
        
        st.markdown("""
        <div class="method-guide">
        <div class="method-guide-title">如何选择方差分析方法？</div>
        <div class="method-guide-content">
        <b>1. 完全随机设计 (CRD)</b>：试验单元之间环境差异不大（如温室、实验室、培养箱）<br>
        <b>2. 随机区组设计 (RCBD)</b>：存在已知方向的环境梯度（如土壤肥力从一端到另一端逐渐变化）→ 田间试验<b>最常用</b><br>
        <b>3. 拉丁方设计</b>：存在<b>两个方向</b>的环境梯度（如行和列方向都有肥力差异），处理数 = 行数 = 列数<br>
        <b>4. 裂区设计</b>：一个因素需要大面积实施（如耕作方式、灌溉），另一个因素可以小面积实施（如品种、施肥量）<br>
        <b>5. 两因素析因设计</b>：两个因素处于同等地位，需研究<b>交互效应</b>（如品种×氮肥互作）<br>
        <b>6. MET多点联合分析</b>：品种在多个地点、多个年份的联合试验，用于品种审定和稳定性评价<br>
        <b>7. Alpha/不完全区组设计</b>：品种数过多（如 >20），无法在一个完全区组中容纳，需将区组拆分为不完全区组。采用混合模型，区组效应为随机效应<br>
        <b>8. 增广设计</b>：育种早期筛选阶段，对照品种有重复用于估计误差，测试材料无重复。通过对照校正后比较测试材料<br>
        <b>9. 间比法/对比法分析</b>：育种初期品系鉴定，对照（CK1）间隔插入试验材料中。允许存在多个对照（如CK1、CK2），但<b>仅用CK1对照做对比计算</b>。需要<b>位置列</b>（田间排列顺序）和<b>类型列</b>（区分"对照"和"处理"）。对比法与间比法均使用<b>左右CK1均值作为理论对照</b>：理论对照 = (左CK1 + 右CK1) / 2，相对产量 = (处理产量 / 理论对照) × 100%。相对产量 >110% 可能优于对照
        </div>
        </div>
        """, unsafe_allow_html=True)
    
    dm = get_current_dm()
    
    if not dm.is_loaded:
        st.warning("⚠️ 请从首页上传数据")
        return
    
    df = dm.data
    
    # ── 自动推断试验设计类型 ──
    _design_options = [
        "完全随机设计 (CRD)",
        "随机完全区组设计 (RCBD)",
        "拉丁方设计 (Latin Square)",
        "裂区设计 (Split-Plot)",
        "两因素析因设计",
        "MET 多点联合分析",
        "Alpha/不完全区组设计",
        "增广设计 (对照+测试)",
        "间比法/对比法分析"
    ]
    _detected_index = _auto_detect_design(df, _design_options)
    _detected_name = _design_options[_detected_index] if _detected_index >= 0 else None
    
    if _detected_name:
        st.success(f"🧠 智能识别：根据数据结构，推荐使用 **{_detected_name}**")
    
    # 试验设计类型选择
    design_type = st.selectbox(
        "选择试验设计类型",
        _design_options,
        index=_detected_index if _detected_index >= 0 else 1
    )

    st.markdown("---")
    
    # 计费守卫：选择分析类型后检查并扣减次数
    if design_type not in ("---", "请先上传数据"):
        check_billing("方差分析-" + design_type, {"design_type": design_type, "rows": len(df)})
    
    if "CRD" in design_type and "随机" in design_type:
        crd_anova(df)
    elif design_type == "随机完全区组设计 (RCBD)":
        rcbd_anova(df)
    elif design_type == "拉丁方设计 (Latin Square)":
        latin_square_anova(df)
    elif design_type == "裂区设计 (Split-Plot)":
        split_plot_anova(df)
    elif design_type == "两因素析因设计":
        factorial_anova(df)
    elif design_type == "MET 多点联合分析":
        met_analysis(df)
    elif design_type == "Alpha/不完全区组设计":
        alpha_lattice_anova(df)
    elif design_type == "增广设计 (对照+测试)":
        augmented_anova(df)
    elif design_type == "间比法/对比法分析":
        interval_contrast_anova(df)


# ========== CRD 完全随机设计 ==========
def crd_anova(df):
    st.markdown("### 🎯 完全随机设计 (CRD)")
    sm, ols, anova_lm, pairwise_tukeyhsd = _get_statsmodels()

    st.info("""
    **完全随机设计 (CRD)** 是最简单的方差分析设计。

    **适用场景**：试验单元间环境差异不大（温室、培养箱、实验室）。

    **数据要求**：
    - **处理变量**（分类）：如品种、施肥方案等
    - **响应变量**（数值）：如产量、株高、穗长等
    - 不需要区组列

    **模型**：Y = μ + τᵢ + εᵢⱼ（总均值 + 处理效应 + 随机误差）

    **输出**：方差分析表、处理均值比较、Tukey HSD多重比较
    """)
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    # 检测数字型分类变量
    _nc_cat = _detect_numeric_categorical(df, numeric_cols)
    all_categorical = df.select_dtypes(include=['object', 'category']).columns.tolist() + _nc_cat
    pure_numeric = [c for c in numeric_cols if c not in _nc_cat]
    
    _trt_match = _auto_match(df, all_categorical, _TRT_RULES)
    
    response = st.selectbox("选择响应变量（产量/指标）", pure_numeric, key="crd_y")
    treatment = st.selectbox("选择处理变量", all_categorical, index=_safe_index(all_categorical, _trt_match), key="crd_trt")
    
    # 拟合模型
    formula = f'Q("{response}") ~ C(Q("{treatment}"))'
    try:
        model = ols(formula, data=df).fit()
        anova_table = anova_lm(model, typ=2)
        
        # ── 一、方差分析 ──
        st.markdown("---")
        st.markdown("#### 📊 一、方差分析")
        display_anova_table(anova_table, "CRD方差分析表")
        
        # ── 二、处理均值与多重比较 ──
        st.markdown("---")
        st.markdown("#### 🔬 二、处理均值与多重比较")
        _alpha_selector()
        treatment_means = df.groupby(treatment)[response].agg(['mean', 'std', 'count']).round(3)
        treatment_means.columns = ['均值', '标准差', '重复数']
        tab_mean, tab_tukey, tab_duncan = st.tabs(["描述统计", "Tukey HSD", "Duncan's SSR"])
        
        with tab_mean:
            st.dataframe(treatment_means.sort_values('均值', ascending=False))
        
        with tab_tukey:
            tukey = pairwise_tukeyhsd(
                endog=df[response].values,
                groups=df[treatment].values,
                alpha=_get_alpha()
            )
            # 兼容不同版本的statsmodels
            _display_tukey_result(tukey, _get_alpha())
            
            # 显著性分组图
            plot_significance_groups(tukey, treatment_means, response)
        
        with tab_duncan:
            df_dun, mse_v, df_v, ms_sorted, ns_sorted, reps = _duncan_multiple_comparison(
                df[response], df[treatment])
            if df_dun is not None:
                _display_duncan_result(df_dun, mse_v, df_v, ns_sorted, ms_sorted, reps)
    
    except Exception as e:
        st.error(f"分析失败: {e}")


# ========== RCBD 随机完全区组设计 ==========
def rcbd_anova(df):
    st.markdown("### 🎯 随机完全区组设计 (RCBD)")
    sm, ols, anova_lm, pairwise_tukeyhsd = _get_statsmodels()

    st.info("""
    **随机完全区组设计 (RCBD)** 是田间试验**最常用**的设计。

    **适用场景**：存在已知方向的环境梯度（如土壤肥力从一端到另一端变化）。

    **数据要求**：
    - **处理变量**（分类）：如品种
    - **区组变量**（分类）：如重复、区组I/II/III
    - **响应变量**（数值）：如产量

    **模型**：Y = μ + τᵢ + βⱼ + εᵢⱼ（处理效应 + 区组效应 + 误差）

    **特点**：通过区组控制环境变异，提高处理比较精度。每个区组内包含所有处理。
    """)
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    _nc_cat = _detect_numeric_categorical(df, numeric_cols)
    all_categorical = df.select_dtypes(include=['object', 'category']).columns.tolist() + _nc_cat
    pure_numeric = [c for c in numeric_cols if c not in _nc_cat]
    
    _trt_match = _auto_match(df, all_categorical, _TRT_RULES)
    _blk_match = _auto_match(df, all_categorical, _BLOCK_RULES)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        response = st.selectbox("响应变量", pure_numeric, key="rcbd_y")
    with col2:
        treatment = st.selectbox("处理变量", all_categorical, index=_safe_index(all_categorical, _trt_match), key="rcbd_trt")
    with col3:
        block = st.selectbox("区组变量", [c for c in all_categorical if c != treatment], index=_safe_index([c for c in all_categorical if c != treatment], _blk_match), key="rcbd_blk")
    
    try:
        formula = f'Q("{response}") ~ C(Q("{block}")) + C(Q("{treatment}"))'
        model = ols(formula, data=df).fit()
        anova_table = anova_lm(model, typ=2)
        
        # ── 一、方差分析 ──
        st.markdown("---")
        st.markdown("#### 📊 一、方差分析")
        display_anova_table(anova_table, "RCBD方差分析表")
        
        # ── 二、处理效应分析 ──
        st.markdown("---")
        st.markdown("#### 📈 二、处理效应分析")
        
        # 调整均值
        adj_means = df.groupby(treatment)[response].mean().sort_values(ascending=False)
        
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        # 均值柱状图
        fig.add_trace(go.Bar(x=adj_means.index, y=adj_means.values,
                             name='处理均值', marker_color='#3498db'))
        
        # 误差线
        sem_values = df.groupby(treatment)[response].apply(stats.sem).reindex(adj_means.index)
        fig.add_trace(go.Scatter(x=adj_means.index, y=adj_means.values,
                                error_y=dict(type='data', array=sem_values.values*1.96,
                                           visible=True, thickness=2),
                                mode='markers', name='95% CI', 
                                marker_size=12))
        
        fig.update_layout(title=f'{response} 处理均值比较 (RCBD)',
                         xaxis_title=treatment, yaxis_title=response, height=450)
        st.plotly_chart(fig, use_container_width=True)
        
        # 区组效应
        block_means = df.groupby(block)[response].mean().sort_values(ascending=False)
        fig_block = px.bar(x=block_means.index, y=block_means.values,
                          labels={'x': block, 'y': response},
                          title='区组效应')
        st.plotly_chart(fig_block, use_container_width=True)
        
        # ── 三、多重比较 ──
        st.markdown("---")
        st.markdown("#### 🔬 三、多重比较")
        _alpha_selector()
        tukey_result = pairwise_tukeyhsd(df[response], df[treatment], alpha=_get_alpha())
        tab_tukey_rcbd, tab_duncan_rcbd = st.tabs(["Tukey HSD", "Duncan's SSR"])
        with tab_tukey_rcbd:
            _display_tukey_result(tukey_result, _get_alpha())
            plot_significance_groups(tukey_result,
                                     df.groupby(treatment)[response].agg(['mean','std','count']),
                                     response)
        with tab_duncan_rcbd:
            # 从模型残差提取 MSE 和 df_e
            mse_rcbd = model.mse_resid if hasattr(model, 'mse_resid') else np.nan
            df_e_rcbd = model.df_resid if hasattr(model, 'df_resid') else None
            df_dun_r, mse_r, df_r, ms_r, ns_r, reps_r = _duncan_multiple_comparison(
                df[response], df[treatment], mse_val=mse_rcbd, df_e=df_e_rcbd)
            if df_dun_r is not None:
                _display_duncan_result(df_dun_r, mse_r, df_r, ns_r, ms_r, reps_r)
    
    except Exception as e:
        st.error(f"分析失败: {e}")
        import traceback; st.code(traceback.format_exc())


# ========== 拉丁方设计 ==========
def latin_square_anova(df):
    st.markdown("### 🎯 拉丁方设计 (Latin Square)")
    sm, ols, anova_lm, pairwise_tukeyhsd = _get_statsmodels()

    st.info("""
    **拉丁方设计**可同时控制两个方向的环境变异。

    **适用场景**：行和列两个方向都存在环境梯度（如田间行向和列向肥力差异）。

    **数据要求**：
    - **行区组变量**（分类）
    - **列区组变量**（分类）
    - **处理变量**（分类）：处理数 = 行数 = 列数
    - **响应变量**（数值）

    **模型**：Y = μ + τᵢ + ρⱼ + γₖ + εᵢⱼₖ（处理 + 行 + 列 + 误差）

    **注意**：需要至少3个分类变量（行、列、处理），且处理数等于行数和列数。
    """)
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    _nc_cat = _detect_numeric_categorical(df, numeric_cols)
    all_categorical = df.select_dtypes(include=['object', 'category']).columns.tolist() + _nc_cat
    pure_numeric = [c for c in numeric_cols if c not in _nc_cat]
    
    if len(all_categorical) < 3:
        st.warning("拉丁方设计需要至少3个分类变量：行、列、处理")
        return
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        response = st.selectbox("响应变量", pure_numeric, key="ls_y")
    with col2:
        row_var = st.selectbox("行变量", all_categorical, index=_safe_index(all_categorical, _auto_match(df, all_categorical, _ROW_RULES)), key="ls_row")
    with col3:
        col_var = st.selectbox("列变量", [c for c in all_categorical if c != row_var], index=_safe_index([c for c in all_categorical if c != row_var], _auto_match(df, all_categorical, _COL_RULES)), key="ls_col")
    with col4:
        trt_var = st.selectbox("处理变量", [c for c in all_categorical if c not in [row_var, col_var]], index=_safe_index([c for c in all_categorical if c not in [row_var, col_var]], _auto_match(df, all_categorical, _TRT_RULES)), key="ls_trt")
    
    try:
        formula = f'Q("{response}") ~ C(Q("{row_var}")) + C(Q("{col_var}")) + C(Q("{trt_var}"))'
        model = ols(formula, data=df).fit()
        anova_table = anova_lm(model, typ=2)
        
        # ── 一、方差分析 ──
        st.markdown("---")
        st.markdown("#### 📊 一、方差分析")
        display_anova_table(anova_table, "拉丁方设计方差分析表")
        
        # ── 二、处理均值分布 ──
        st.markdown("---")
        st.markdown("#### 📈 二、处理均值分布")
        
        # 热力图展示拉丁方布局
        pivot_df = df.pivot_table(values=response, index=row_var, columns=trt_var, aggfunc='mean')
        
        fig = px.imshow(pivot_df, text_auto='.1f', aspect='auto',
                        color_continuous_scale='YlGnBu',
                        title=f'{response} 均值分布 ({row_var} × {trt_var})')
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)
        
        # ── 三、处理间多重比较 ──
        st.markdown("---")
        st.markdown("#### 🔬 三、处理间多重比较")
        _alpha_selector()
        tukey_ls = pairwise_tukeyhsd(df[response], df[trt_var], alpha=_get_alpha())
        tab_tukey_ls, tab_duncan_ls = st.tabs(["Tukey HSD", "Duncan's SSR"])
        with tab_tukey_ls:
            _display_tukey_result(tukey_ls, _get_alpha())
        with tab_duncan_ls:
            mse_ls = model.mse_resid if hasattr(model, 'mse_resid') else np.nan
            df_e_ls = model.df_resid if hasattr(model, 'df_resid') else None
            df_dun_ls, mse_l, df_l, ms_l, ns_l, reps_l = _duncan_multiple_comparison(
                df[response], df[trt_var], mse_val=mse_ls, df_e=df_e_ls)
            if df_dun_ls is not None:
                _display_duncan_result(df_dun_ls, mse_l, df_l, ns_l, ms_l, reps_l)
        
    except Exception as e:
        st.error(f"分析失败: {e}")


# ========== 裂区设计 ==========
def split_plot_anova(df):
    st.markdown("### 🎯 裂区设计 (Split-Plot)")
    sm, ols, anova_lm, pairwise_tukeyhsd = _get_statsmodels()

    st.info("""
    **裂区设计**用于一个因素需要大面积实施、另一个因素小面积实施的情况。

    **适用场景**：如耕作方式（主区）× 品种（副区）、灌溉方式（主区）× 施肥量（副区）。

    **数据要求**：
    - **主区因子 A**（分类）：需大面积实施的处理
    - **副区因子 B**（分类）：在主区内细分的处理
    - **区组**（分类）：重复单位
    - **响应变量**（数值）

    **模型**：Y = μ + αᵢ + βⱼ + (αβ)ᵢⱼ + γₖ + (αγ)ᵢₖ + εᵢⱼₖ

    **特点**：主区和副区的误差项不同，副区比较精度通常高于主区。
    """)
    
    # 裂区设计复用外部 all_categorical，先做自动匹配
    _sp_trt_a = _auto_match(df, all_categorical, _TRT_RULES)
    _sp_blk = _auto_match(df, all_categorical, _BLOCK_RULES)
    # 副区因子：排除处理和区组后的第一个分类变量
    _sp_trt_b_pool = [c for c in all_categorical if c not in [_sp_trt_a, _sp_blk] and _sp_trt_a and _sp_blk]
    _sp_trt_b = _sp_trt_b_pool[0] if _sp_trt_b_pool else None
    
    col1, col2, col3, col4 = st.columns(4)
    with col1: response = st.selectbox("响应变量", pure_numeric, key="sp_y")
    with col2: main_factor = st.selectbox("主区因子(A)", all_categorical, index=_safe_index(all_categorical, _sp_trt_a), key="sp_a")
    with col3: sub_factor = st.selectbox("副区因子(B)", [c for c in all_categorical if c != main_factor], index=_safe_index([c for c in all_categorical if c != main_factor], _sp_trt_b), key="sp_b")
    with col4: block_var = st.selectbox("区组", [c for c in all_categorical if c not in [main_factor, sub_factor]], index=_safe_index([c for c in all_categorical if c not in [main_factor, sub_factor]], _sp_blk), key="sp_block")
    
    # ── 数据校验 ──
    n_blocks = df[block_var].nunique()
    n_main = df[main_factor].nunique()
    n_sub = df[sub_factor].nunique()
    n_obs = len(df)
    expected_obs = n_blocks * n_main * n_sub
    
    if n_obs != expected_obs:
        st.warning(f"⚠️ 数据不平衡：实际 {n_obs} 行，期望 {expected_obs} 行 "
                   f"({n_blocks}区组 × {n_main}主处理 × {n_sub}副处理)。"
                   f"裂区设计要求完全平衡数据。")
    
    if n_blocks < 3:
        st.warning(f"⚠️ 区组数仅 {n_blocks}，建议至少 3 个区组以获得足够的误差自由度。")
    
    # 检查自由度是否足够（主区误差 df = (r-1)(a-1)，至少需要 1）
    if (n_blocks - 1) * (n_main - 1) < 1:
        st.error(f"❌ 主区误差自由度为 0 (需要 (区组数-1)×(主处理数-1) ≥ 1，"
                 f"当前 ({n_blocks}-1)×({n_main}-1) = {(n_blocks-1)*(n_main-1)})。"
                 f"请增加区组数或主处理数。")
        return
    
    try:
        # ── 标准裂区设计 ANOVA ──
        # 模型拟合到 A×B 交互，不包含三阶交互 A:B:Block
        # Block:A 充当主区误差 Ea
        # 残差（Block:B + A:B:Block）充当副区误差 Eb
        formula = (f'Q("{response}") ~ Q("{block_var}") + '
                   f'C(Q("{main_factor}"), Sum) + '
                   f'Q("{block_var}"):C(Q("{main_factor}"), Sum) + '
                   f'C(Q("{sub_factor}"), Sum) + '
                   f'C(Q("{main_factor}"), Sum):C(Q("{sub_factor}"), Sum)')
        
        model = ols(formula, data=df).fit()
        raw_anova = anova_lm(model, typ=2)
        
        # ── 构建标准裂区 ANOVA 表 ──
        # 找到各效应对应的行
        def _match_row(index, keywords):
            """在 ANOVA 表 index 中匹配含所有关键词的行"""
            for idx in index:
                idx_str = str(idx)
                if all(kw.lower() in idx_str.lower() for kw in keywords):
                    return idx
            return None
        
        block_row = _match_row(raw_anova.index, [block_var])
        main_row = _match_row(raw_anova.index, [main_factor]) and not _match_row(raw_anova.index, [main_factor, sub_factor])
        # 主处理行：含 main_factor 但不含 sub_factor 且不含 block_var
        for idx in raw_anova.index:
            idx_str = str(idx)
            if main_factor in idx_str and sub_factor not in idx_str and block_var not in idx_str:
                main_row = idx
                break
        
        # 主区误差 = Block:A 交互
        ea_row = _match_row(raw_anova.index, [block_var, main_factor])
        
        # 副处理行：含 sub_factor 但不含 main_factor
        for idx in raw_anova.index:
            idx_str = str(idx)
            if sub_factor in idx_str and main_factor not in idx_str and block_var not in idx_str:
                sub_row = idx
                break
        else:
            sub_row = None
        
        # A×B 交互行
        ab_row = _match_row(raw_anova.index, [main_factor, sub_factor])
        
        # 残差行 = Block:B + A:B:Block（作为副区误差 Eb）
        residual_row = _match_row(raw_anova.index, ['Residual'])
        
        # ── 构建标准 6 行裂区 ANOVA 表 ──
        results = []
        
        # 变异来源名称
        def _clean_name(idx):
            s = str(idx)
            m = re.findall(r'C\(Q\(["\']([^"\']+)["\']\)\)', s)
            if m:
                return ':'.join(m)
            if 'Residual' in s:
                return '残差'
            return s
        
        # 1. 区组
        if block_row and block_row in raw_anova.index:
            r = raw_anova.loc[block_row]
            results.append({'变异来源': '区组', '自由度': int(r['df']), '平方和': r['sum_sq'],
                           '均方': r['sum_sq'] / r['df'] if r['df'] > 0 else np.nan})
        
        # 2. 主处理(A)
        if main_row and main_row in raw_anova.index:
            r = raw_anova.loc[main_row]
            results.append({'变异来源': f'主处理({main_factor})', '自由度': int(r['df']), '平方和': r['sum_sq'],
                           '均方': r['sum_sq'] / r['df'] if r['df'] > 0 else np.nan})
        
        # 3. 主区误差 Ea = Block:A
        if ea_row and ea_row in raw_anova.index:
            r = raw_anova.loc[ea_row]
            ms_ea = r['sum_sq'] / r['df'] if r['df'] > 0 else np.nan
            results.append({'变异来源': '主区误差(Ea)', '自由度': int(r['df']), '平方和': r['sum_sq'], '均方': ms_ea})
            # 用 Ea 检验主处理
            if ms_ea and ms_ea > 0 and len(results) >= 2:
                ms_main = results[1]['均方']
                if ms_main and ms_main > 0:
                    f_main = ms_main / ms_ea
                    df_main = results[1]['自由度']
                    df_ea = int(r['df'])
                    p_main = 1 - stats.f.cdf(f_main, df_main, df_ea) if df_ea > 0 else np.nan
                    results[1]['F值'] = round(f_main, 4)
                    results[1]['p值'] = round(p_main, 4)
                    results[1]['显著性'] = '***' if p_main < 0.001 else ('**' if p_main < 0.01 else ('*' if p_main < 0.05 else 'n.s.'))
        
        # 4. 副处理(B)
        if sub_row and sub_row in raw_anova.index:
            r = raw_anova.loc[sub_row]
            results.append({'变异来源': f'副处理({sub_factor})', '自由度': int(r['df']), '平方和': r['sum_sq'],
                           '均方': r['sum_sq'] / r['df'] if r['df'] > 0 else np.nan})
        
        # 5. A×B 交互
        if ab_row and ab_row in raw_anova.index:
            r = raw_anova.loc[ab_row]
            results.append({'变异来源': f'{main_factor}×{sub_factor}', '自由度': int(r['df']), '平方和': r['sum_sq'],
                           '均方': r['sum_sq'] / r['df'] if r['df'] > 0 else np.nan})
        
        # 6. 副区误差 Eb = 残差 (Block:B + A:B:Block)
        ms_eb_val, df_eb_val = np.nan, None  # 保存供 Duncan 使用
        if residual_row and residual_row in raw_anova.index:
            r = raw_anova.loc[residual_row]
            ms_eb = r['sum_sq'] / r['df'] if r['df'] > 0 else np.nan
            ms_eb_val, df_eb_val = ms_eb, int(r['df'])
            results.append({'变异来源': '副区误差(Eb)', '自由度': int(r['df']), '平方和': r['sum_sq'], '均方': ms_eb})
            
            # 用 Eb 检验副处理和 A×B 交互
            if ms_eb and ms_eb > 0:
                # 副处理
                for item in results:
                    if item['变异来源'].startswith('副处理') and 'F值' not in item:
                        ms_trt = item['均方']
                        if ms_trt and ms_trt > 0:
                            f_val = ms_trt / ms_eb
                            df_trt = item['自由度']
                            df_eb = int(r['df'])
                            p_val = 1 - stats.f.cdf(f_val, df_trt, df_eb) if df_eb > 0 else np.nan
                            item['F值'] = round(f_val, 4)
                            item['p值'] = round(p_val, 4)
                            item['显著性'] = '***' if p_val < 0.001 else ('**' if p_val < 0.01 else ('*' if p_val < 0.05 else 'n.s.'))
                    # A×B 交互
                    if item['变异来源'].startswith(main_factor) and '×' in item['变异来源'] and 'F值' not in item:
                        ms_int = item['均方']
                        if ms_int and ms_int > 0:
                            f_val = ms_int / ms_eb
                            df_int = item['自由度']
                            df_eb = int(r['df'])
                            p_val = 1 - stats.f.cdf(f_val, df_int, df_eb) if df_eb > 0 else np.nan
                            item['F值'] = round(f_val, 4)
                            item['p值'] = round(p_val, 4)
                            item['显著性'] = '***' if p_val < 0.001 else ('**' if p_val < 0.01 else ('*' if p_val < 0.05 else 'n.s.'))
        
        # 填充缺失字段
        for item in results:
            item.setdefault('F值', np.nan)
            item.setdefault('p值', np.nan)
            item.setdefault('显著性', '-')
        
        # 计算总变异
        ss_total = sum(item['平方和'] for item in results)
        df_total = sum(item['自由度'] for item in results)
        results.append({'变异来源': '总计', '自由度': df_total, '平方和': ss_total, '均方': np.nan, 'F值': np.nan, 'p值': np.nan, '显著性': '-'})
        
        # 构建显示表格（全中文表头）
        df_anova = pd.DataFrame(results)
        df_anova = df_anova.set_index('变异来源')
        df_anova = df_anova[['自由度', '平方和', '均方', 'F值', 'p值', '显著性']]
        df_anova = df_anova.round(4)
        
        # ── 一、方差分析 ──
        st.markdown("---")
        st.markdown("#### 📊 一、方差分析")
        st.markdown("#### 裂区设计方差分析表")
        st.markdown("*注：主处理用 Ea 检验，副处理和 A×B 交互用 Eb 检验*")
        st.dataframe(df_anova, use_container_width=True)
        
        # CV 计算
        grand_mean = df[response].mean()
        eb_row_data = next((item for item in results if 'Eb' in str(item.get('变异来源', ''))), None)
        if eb_row_data and eb_row_data.get('均方') and eb_row_data['均方'] > 0:
            cv = (np.sqrt(eb_row_data['均方']) / grand_mean * 100) if grand_mean != 0 else np.nan
            if not np.isnan(cv):
                st.metric("变异系数 (CV%)", f"{cv:.2f}%")
        
        # ── 二、交互作用分析 ──
        st.markdown("---")
        st.markdown("#### 📈 二、主区 × 副区交互作用")
        fig = px.line(df.groupby([main_factor, sub_factor])[response].mean().reset_index(),
                     x=sub_factor, y=response, color=main_factor,
                     markers=True, title='主区×副区交互作用图',
                     labels={sub_factor: '副区因子', response: response, main_factor: '主区因子'})
        st.plotly_chart(fig, use_container_width=True)
        
        # ── 三、多重比较 ──
        st.markdown("---")
        st.markdown("#### 🔬 三、多重比较")
        _alpha_selector()
        for factor_col, factor_label in [(main_factor, f'主处理({main_factor})'), (sub_factor, f'副处理({sub_factor})')]:
            try:
                tab_t_sp, tab_d_sp = st.tabs(["Tukey HSD", "Duncan's SSR"])
                with tab_t_sp:
                    tukey = pairwise_tukeyhsd(df[response], df[factor_col], alpha=_get_alpha())
                    st.markdown(f"##### {factor_label} — Tukey HSD")
                    _display_tukey_result(tukey, _get_alpha())
                with tab_d_sp:
                    df_dun_sp, mse_sp, df_sp, ms_sp, ns_sp, reps_sp = _duncan_multiple_comparison(
                        df[response], df[factor_col], mse_val=ms_eb_val, df_e=df_eb_val)
                    if df_dun_sp is not None:
                        _display_duncan_result(df_dun_sp, mse_sp, df_sp, ns_sp, ms_sp, reps_sp,
                                              title_prefix=f"{factor_label} — ")
            except Exception:
                pass
        
    except Exception as e:
        st.error(f"分析失败: {e}")


# ========== 两因素析因设计 ==========
def factorial_anova(df):
    st.markdown("### 🎯 两因素析因设计")
    sm, ols, anova_lm, pairwise_tukeyhsd = _get_statsmodels()

    st.info("""
    **两因素析因设计**用于研究两个因素的主效应和交互效应。

    **适用场景**：两个因素处于同等地位，需研究交互作用（如品种×氮肥互作）。

    **数据要求**：
    - **因子A**（分类）：第一个因素
    - **因子B**（分类）：第二个因素
    - **响应变量**（数值）：观测值

    **模型**：Y = μ + αᵢ + βⱼ + (αβ)ᵢⱼ + εᵢⱼ

    **交互效应解读**：
    - 交互显著 → 两因素联合效应不等于各自效应之和，需做简单效应分析
    - 交互不显著 → 可分别考察各因素主效应
    """)
    
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    _nc_cat = _detect_numeric_categorical(df, numeric_cols)
    all_categorical = df.select_dtypes(include=['object', 'category']).columns.tolist() + _nc_cat
    pure_numeric = [c for c in numeric_cols if c not in _nc_cat]
    
    _fact_a = _auto_match(df, all_categorical, _TRT_RULES)
    _fact_b_pool = [c for c in all_categorical if c != _fact_a] if _fact_a else all_categorical[1:]
    _fact_b = _fact_b_pool[0] if _fact_b_pool else None
    
    col1, col2, col3 = st.columns(3)
    with col1: response = st.selectbox("响应变量", pure_numeric, key="fact_y")
    with col2: factor_a = st.selectbox("因子A", all_categorical, index=_safe_index(all_categorical, _fact_a), key="fact_a")
    with col3: factor_b = st.selectbox("因子B", [c for c in all_categorical if c != factor_a], index=_safe_index([c for c in all_categorical if c != factor_a], _fact_b), key="fact_b")
    
    include_interaction = st.checkbox("包含交互作用 A×B", value=True)
    
    try:
        if include_interaction:
            formula = f'Q("{response}") ~ C(Q("{factor_a}")) * C(Q("{factor_b}"))'
        else:
            formula = f'Q("{response}") ~ C(Q("{factor_a}")) + C(Q("{factor_b}"))'
        
        model = ols(formula, data=df).fit()
        anova_table = anova_lm(model, typ=2)
        
        # ── 一、方差分析 ──
        st.markdown("---")
        st.markdown("#### 📊 一、方差分析")
        display_anova_table(anova_table, "两因素析因设计方差分析表")
        
        # ── 二、交互作用分析 ──
        st.markdown("---")
        st.markdown("#### 📈 二、交互作用分析")
        if include_interaction:
            st.markdown("#### 因子交互作用图")
            
            tab_int, tab_profile = st.tabs(["交互作用线图", "剖面图"])
            
            with tab_int:
                fig = px.line(df.groupby([factor_a, factor_b])[response].mean().reset_index(),
                             x=factor_a, y=response, color=factor_b,
                             markers=True, title='因子A×B交互作用',
                             labels={factor_a: '因子A', factor_b: '因子B'})
                st.plotly_chart(fig, use_container_width=True)
            
            with tab_profile:
                fig2 = px.line(df.groupby([factor_a, factor_b])[response].mean().reset_index(),
                              x=factor_b, y=response, color=factor_a,
                              markers=True, title='因子B×A剖面图',
                              labels={factor_b: '因子B', factor_a: '因子A'})
                st.plotly_chart(fig2, use_container_width=True)
        
        # ── 三、多重比较 ──
        st.markdown("---")
        st.markdown("#### 🔬 三、多重比较")
        _alpha_selector()
        for factor_col, factor_label in [(factor_a, f'因子A({factor_a})'), (factor_b, f'因子B({factor_b})')]:
            try:
                tab_t_fact, tab_d_fact = st.tabs(["Tukey HSD", "Duncan's SSR"])
                with tab_t_fact:
                    tukey = pairwise_tukeyhsd(df[response], df[factor_col], alpha=_get_alpha())
                    st.markdown(f"##### {factor_label} — Tukey HSD")
                    _display_tukey_result(tukey, _get_alpha())
                with tab_d_fact:
                    mse_fact = model.mse_resid if hasattr(model, 'mse_resid') else np.nan
                    df_e_fact = model.df_resid if hasattr(model, 'df_resid') else None
                    df_dun_f, mse_f, df_f, ms_f, ns_f, reps_f = _duncan_multiple_comparison(
                        df[response], df[factor_col], mse_val=mse_fact, df_e=df_e_fact)
                    if df_dun_f is not None:
                        _display_duncan_result(df_dun_f, mse_f, df_f, ns_f, ms_f, reps_f,
                                              title_prefix=f"{factor_label} — ")
            except Exception:
                pass

        # 单元格均值热图
        cell_means = df.pivot_table(values=response, index=factor_a, columns=factor_b, aggfunc='mean')
        fig_heat = px.imshow(cell_means, text_auto='.2f', aspect='auto',
                             color_continuous_scale='RdBu_r',
                             title='单元格均值矩阵')
        fig_heat.update_layout(height=350)
        st.plotly_chart(fig_heat, use_container_width=True)
        
    except Exception as e:
        st.error(f"分析失败: {e}")


# ========== MET 多点联合分析 ==========
def met_analysis(df):
    st.markdown("### 🌍 MET 多点联合分析")
    sm, ols, anova_lm, pairwise_tukeyhsd = _get_statsmodels()

    st.info("""
    **MET (Multi-Environment Trial)** 用于评估品种/处理在多环境下的表现。

    **适用场景**：品种区域试验，需要在多个地点/年份同时比较品种表现。

    **数据要求**：
    - **基因型/品种**（分类）
    - **环境**（分类）：地点×年份组合，或单独地点列
    - **重复/区组**（分类）：可选，选择后将使用区组嵌套模型（RCBD-MET）
    - **响应变量**（数值）：产量等性状

    **分析内容**：
    - 联合方差分析：基因型(G)、环境(E)、G×E互作
    - 稳定性分析：Shukla's 方差、Eberhart-Russell 回归
    - 品种排名和推荐
    """)

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    _nc_cat = _detect_numeric_categorical(df, numeric_cols)
    all_categorical = df.select_dtypes(include=['object', 'category']).columns.tolist() + _nc_cat
    pure_numeric = [c for c in numeric_cols if c not in _nc_cat]

    _met_geno = _auto_match(df, all_categorical, _TRT_RULES)
    _met_env = _auto_match(df, all_categorical, _ENV_RULES, exclude=[_met_geno])
    _met_blk = _auto_match(df, all_categorical, _BLOCK_RULES, exclude=[_met_geno, _met_env])

    col1, col2, col3, col4 = st.columns(4)
    with col1: response = st.selectbox("响应变量", pure_numeric, key="met_y")
    with col2: genotype = st.selectbox("基因型/处理", all_categorical, index=_safe_index(all_categorical, _met_geno), key="met_g")
    with col3: environment = st.selectbox("环境(地点/年份)", [c for c in all_categorical if c != genotype], index=_safe_index([c for c in all_categorical if c != genotype], _met_env), key="met_e")
    remaining_for_block = [c for c in all_categorical if c not in [genotype, environment]]
    with col4: block_var_met = st.selectbox("重复/区组", ["无"] + remaining_for_block, index=_safe_index(["无"] + remaining_for_block, _met_blk), key="met_block")
    if block_var_met == "无":
        block_var_met = None

    try:
        environments = sorted(df[environment].unique())
        genotypes = sorted(df[genotype].unique())
        n_env = len(environments)
        n_gen = len(genotypes)

        # ========== Tab 1: 单点分析 ==========
        st.markdown("---")
        st.markdown("#### 📍 一、单点分析 — 各环境独立方差分析与CV")

        single_point_results = []

        for env in environments:
            df_env = df[df[environment] == env]

            if block_var_met is not None:
                formula_sp = f'Q("{response}") ~ C(Q("{block_var_met}")) + C(Q("{genotype}"))'
            else:
                formula_sp = f'Q("{response}") ~ C(Q("{genotype}"))'

            env_mean = df_env[response].mean()
            env_std = df_env[response].std()
            env_cv = (env_std / env_mean * 100) if env_mean != 0 else 0
            env_n = len(df_env)

            try:
                model_sp = ols(formula_sp, data=df_env).fit()
                anova_sp = anova_lm(model_sp, typ=2)

                geno_row = None
                for idx_name in anova_sp.index:
                    if genotype in str(idx_name):
                        geno_row = anova_sp.loc[idx_name]
                        break

                f_val = geno_row['F'] if geno_row is not None else np.nan
                p_val = geno_row['PR(>F)'] if geno_row is not None else np.nan

                geno_stats = df_env.groupby(genotype)[response].agg(['mean', 'std', 'count'])
                geno_max_mean = geno_stats['mean'].max()
                geno_min_mean = geno_stats['mean'].min()
                geno_range = geno_max_mean - geno_min_mean

            except Exception:
                f_val, p_val, geno_range = np.nan, np.nan, np.nan

            single_point_results.append({
                environment: env,
                '样本数(N)': env_n,
                '均值': round(env_mean, 2),
                '标准差': round(env_std, 2),
                '变异系数(CV%)': round(env_cv, 2),
                '基因型F值': round(f_val, 2) if not np.isnan(f_val) else '-',
                '基因型p值': f'{p_val:.4f}' if not np.isnan(p_val) else '-',
                '极差': round(geno_range, 2) if not np.isnan(geno_range) else '-',
            })

        sp_df = pd.DataFrame(single_point_results)
        sp_df_sorted = sp_df.sort_values('变异系数(CV%)', ascending=False)

        st.dataframe(sp_df_sorted.reset_index(drop=True), use_container_width=True)

        # 单点CV柱状图
        fig_sp_cv = px.bar(
            x=sp_df_sorted[environment], y=sp_df_sorted['变异系数(CV%)'],
            labels={environment: '环境', '变异系数(CV%)': 'CV (%)'},
            title='各试验点变异系数 (CV%) 排序',
            text=sp_df_sorted['变异系数(CV%)'].apply(lambda x: f'{x:.1f}%'),
            color=sp_df_sorted['变异系数(CV%)'],
            color_continuous_scale='RdYlGn_r'
        )
        fig_sp_cv.update_layout(height=400, showlegend=False)
        st.plotly_chart(fig_sp_cv, use_container_width=True, key='met_sp_cv')

        # 展开查看每个环境的详细ANOVA表
        with st.expander("📋 查看每个环境的详细方差分析表"):
            for env in environments:
                df_env = df[df[environment] == env]
                with st.expander(f"环境: {env}"):
                    try:
                        cat_cols_env = df_env.select_dtypes(include=['object', 'category']).columns.tolist()
                        # 检测数值型分类变量（如区组用数字表示）
                        num_cat_env = []
                        for col in df_env.select_dtypes(include=[np.number]).columns:
                            if col == response:
                                continue
                            uv = df_env[col].dropna().unique()
                            nu = len(uv)
                            if 2 <= nu <= 20 and all(float(v).is_integer() for v in uv):
                                num_cat_env.append(col)
                        potential_block = [c for c in (cat_cols_env + num_cat_env) if c not in [environment, genotype] and c != response]

                        if len(potential_block) > 0:
                            bv = potential_block[0]
                            f = f'Q("{response}") ~ C(Q("{bv}")) + C(Q("{genotype}"))'
                            m = ols(f, data=df_env).fit()
                        else:
                            f = f'Q("{response}") ~ C(Q("{genotype}"))'
                            m = ols(f, data=df_env).fit()

                        at = anova_lm(m, typ=2)
                        # 单点ANOVA表重命名
                        at_renamed = _rename_anova_index(at, environment, genotype,
                                                          bv if len(potential_block) > 0 else None,
                                                          is_met=False)
                        display_anova_table(at_renamed, f"{env} — ANOVA")

                        gs = df_env.groupby(genotype)[response].agg(['mean', 'std']).round(2)
                        gs.columns = ['均值', '标准差']
                        gs = gs.sort_values('均值', ascending=False)
                        st.dataframe(gs)
                    except Exception as e2:
                        st.warning(f"{env} 分析异常: {e2}")


        # ========== Tab 2: 联合方差分析 ==========
        st.markdown("---")
        st.markdown("#### 🌐 二、MET联合方差分析")

        if block_var_met is not None:
            st.caption(f"📌 区组列: **{block_var_met}** | 模型: 环境 + 区组(嵌套于环境内) + 基因型 + G×E")
            # 含区组的MET模型: 区组嵌套在环境内 (RCBD-MET)
            # C(env)/C(block) 展开为: C(env) + C(env):C(block)
            formula = (f'Q("{response}") ~ C(Q("{environment}"))/C(Q("{block_var_met}")) '
                       f'+ C(Q("{genotype}")) + C(Q("{environment}")):C(Q("{genotype}"))')
        else:
            st.caption("📌 无区组列 | 模型: 环境 + 基因型 + G×E（CRD-MET）")
            formula = f'Q("{response}") ~ C(Q("{environment}")) * C(Q("{genotype}"))'

        model = ols(formula, data=df).fit()
        anova_table = anova_lm(model, typ=2)

        # 重命名ANOVA表的变异来源为中文
        anova_renamed = _rename_anova_index(anova_table, environment, genotype, block_var_met, is_met=True)
        display_anova_table(anova_renamed, "MET联合方差分析表")


        # ========== Tab 3: 多重比较 ==========
        st.markdown("---")
        st.markdown("#### 🔬 三、多重比较")
        _alpha_selector()

        try:
            # ── 获取联合ANOVA模型的误差项均方(MSE)和自由度(df_e) ──
            anova_idx = list(anova_renamed.index)
            # 误差行可能是 '误差' 或包含 'Residual' 的原始名
            residual_row = None
            for idx_name in anova_renamed.index:
                if str(idx_name) in ('误差', 'Residual', 'residual'):
                    residual_row = anova_renamed.loc[idx_name]
                    break
            if residual_row is None:
                # 兜底：取最后一行作为残差
                residual_row = anova_renamed.iloc[-1]

            mse_val = residual_row.get('sum_sq', np.nan) / residual_row.get('df', 1) \
                if residual_row.get('df', 0) > 0 else np.nan
            df_e = int(residual_row.get('df', np.nan))

            # 基因型调整均值（来自联合模型）
            emmeans_geno = df.groupby(genotype)[response].mean()
            n_geno = len(emmeans_geno)
            geno_names_sorted = emmeans_geno.sort_values(ascending=False).index.tolist()
            geno_means_sorted = emmeans_geno.sort_values(ascending=False).values

            # 重复数：每个基因型的实际总观测数
            if block_var_met is not None:
                n_block = df[block_var_met].nunique()
            else:
                n_block = 1
            n_rep_total = n_env * n_block  # 理论总重复数 = 环境数 × 区组数

            # 每个基因型的实际观测数（用于精确SE计算，每对比较用各自n1,n2）
            obs_per_geno = df.groupby(genotype).size().astype(float)
            reps_per_geno = obs_per_geno

            # ── 方法1: Fisher LSD（基于联合模型MSE）──
            from scipy.stats import t as t_dist
            t_crit_05 = abs(t_dist.ppf(0.025, df_e))   # 双侧 α=0.05
            t_crit_01 = abs(t_dist.ppf(0.005, df_e))   # 双侧 α=0.01

            lsd_results = []
            for i in range(len(geno_names_sorted)):
                for j in range(i + 1, len(geno_names_sorted)):
                    g1, g2 = geno_names_sorted[i], geno_names_sorted[j]
                    m1, m2 = emmeans_geno[g1], emmeans_geno[g2]
                    diff = m1 - m2
                    # 合并标准误：sqrt(MSE * (1/n1 + 1/n2))
                    se_diff = np.sqrt(mse_val * (1.0 / reps_per_geno[g1] + 1.0 / reps_per_geno[g2]))
                    t_stat = diff / se_diff if se_diff > 0 else 0
                    p_val = 2 * (1 - t_dist.cdf(abs(t_stat), df_e))
                    lsd_value = t_crit_05 * se_diff
                    lsd_value_01 = t_crit_01 * se_diff
                    is_sig_05 = abs(diff) >= lsd_value
                    is_sig_01 = abs(diff) >= lsd_value_01
                    sig_mark = '✓✓' if is_sig_01 else ('✓' if is_sig_05 else '')
                    lsd_results.append({
                        '品种1': g1, '品种2': g2,
                        '均值差': round(diff, 4),
                        '标准误': round(se_diff, 4),
                        'LSD₀.₀₅': round(lsd_value, 4),
                        'LSD₀.₀₁': round(lsd_value_01, 4),
                        't值': round(t_stat, 3),
                        'p值': f'{p_val:.4f}',
                        '显著': sig_mark
                    })

            df_lsd = pd.DataFrame(lsd_results)
            sig_count_05 = sum(1 for r in lsd_results if '✓' in r['显著'])
            sig_count_01 = sum(1 for r in lsd_results if r['显著'] == '✓✓')

            with st.expander("📊 Fisher LSD 多重比较（基于联合模型误差项）", expanded=True):
                st.caption(
                    f"**说明**: 使用MET联合ANOVA的误差均方(MSE={mse_val:.4f}, df={df_e})进行多重比较。"
                    f" 每对比较的LSD临界值根据该两个基因型的实际观测数(n₁, n₂)分别计算："
                    f" SE = √(MSE × (1/n₁ + 1/n₂))，LSD = t × SE。"
                    f"\n\n临界t值: t₀.₀₂₅({df_e}) = {t_crit_05:.4f}，t₀.₀₀₅({df_e}) = {t_crit_01:.4f}。"
                    f" 理论重复数 n = 环境数×区组数 = {n_env}×{n_block} = {n_rep_total}。"
                    f"\n\n共 {len(lsd_results)} 对比较，α=0.05显著 {sig_count_05} 对，α=0.01极显著 {sig_count_01} 对。"
                    f" 显著标记：✓ = α=0.05显著，✓✓ = α=0.01极显著。"
                )
                st.dataframe(df_lsd.reset_index(drop=True), use_container_width=True)

            # ── CLD字母标识（基于LSD结果）──
            _render_met_cld(geno_names_sorted, emmeans_geno, lsd_results, alpha=_get_alpha())

            # ── 方法2: Duncan's New MRT（邓肯新复极差法）──
            from scipy.stats import t as t_dist_fn
            try:
                from scipy.stats import studentized_range as ss_range
                has_sr = True
            except Exception:
                has_sr = False

            n_g = len(geno_names_sorted)
            duncan_results = []
            # Duncan's SSR值表：按范围 r = 2, 3, ..., k 查表
            ssr_table = {}
            alpha_duncan = _get_alpha()
            for r in range(2, n_g + 1):
                if has_sr:
                    try:
                        ssr_val = ss_range.ppf(1 - alpha_duncan, r, df_e)
                        ssr_table[r] = ssr_val
                    except Exception:
                        # 兜底：用近似公式 SSR ≈ sqrt(2) * t_{α/(2r), df_e}
                        t_approx = abs(t_dist_fn.ppf(alpha_duncan / (2 * r), df_e))
                        ssr_table[r] = np.sqrt(2) * t_approx
                else:
                    t_approx = abs(t_dist_fn.ppf(alpha_duncan / (2 * r), df_e))
                    ssr_table[r] = np.sqrt(2) * t_approx

            # 对所有配对进行Duncan检验
            for i in range(n_g):
                for j in range(i + 1, n_g):
                    g1, g2 = geno_names_sorted[i], geno_names_sorted[j]
                    m1, m2 = emmeans_geno[g1], emmeans_geno[g2]
                    diff = m1 - m2

                    # 计算范围r：在排序列表中两处理之间相隔的处理数+1
                    r_val = j - i + 1

                    se = np.sqrt(mse_val / 2.0 * (1.0 / reps_per_geno[g1] + 1.0 / reps_per_geno[g2]))
                    ssr_crit = ssr_table.get(r_val, ssr_table.get(2, 3.912))
                    lsd_duncan = ssr_crit * se
                    is_sig_duncan = abs(diff) >= lsd_duncan

                    duncan_results.append({
                        '品种1': g1, '品种2': g2,
                        '均值差': round(diff, 4),
                        f'范围(r={r_val})': r_val,
                        'SSR临界值': round(ssr_crit, 4),
                        'LSR': round(lsd_duncan, 4),
                        '显著': '✓' if is_sig_duncan else ''
                    })

            df_duncan = pd.DataFrame(duncan_results)
            sig_count_duncan = sum(1 for r in duncan_results if r['显著'] == '✓')

            with st.expander("📊 Duncan's 新复极差法（基于联合模型误差项）", expanded=True):
                st.caption(
                    f"**说明**: Duncan's New MRT (SSR法)，"
                    f"误差均方(MSE={mse_val:.4f}, df={df_e})，"
                    f"保护水平随比较范围r递增(α_r = 1-(1-α)^{{r-1}})。"
                    f" 共 {len(duncan_results)} 对比较，{sig_count_duncan} 对差异显著。"
                    f" {'(使用近似t值)' if not has_sr else '(使用Studentized Range分布)'}"
                )
                st.dataframe(df_duncan.reset_index(drop=True), use_container_width=True)

            # ── Duncan CLD字母标识 ──
            _render_met_cld(geno_names_sorted, emmeans_geno, duncan_results, method_name='Duncan', alpha=_get_alpha())

            # ── 同时保留Tukey HSD（原始合并数据）供参考对比 ──
            with st.expander("📋 Tukey HSD（原始数据参考 — 忽略环境效应）", expanded=False):
                st.caption(
                    "⚠️ **注意**: 此结果将所有环境原始数据视为单因素CRD处理，"
                    "**未扣除环境效应和G×E互作**，误差项偏大、检验偏保守。"
                    " 与联合ANOVA的F检验结论可能不一致属正常现象。"
                    " **建议以上方Fisher LSD结果为准。**"
                )
                tukey_met = pairwise_tukeyhsd(
                    endog=df[response].values,
                    groups=df[genotype].values,
                    alpha=_get_alpha()
                )
                _display_tukey_result(tukey_met, _get_alpha())

            geno_all_means = df.groupby(genotype)[response].agg(['mean', 'std', 'count']).round(2)
            geno_all_means.columns = ['总均值', '标准差', '样本数']
            geno_all_means = geno_all_means.sort_values('总均值', ascending=False)

            st.markdown("**基因型综合表现排序**:")
            st.dataframe(geno_all_means)

            fig_geno_bar = px.bar(
                x=geno_all_means.index, y=geno_all_means['总均值'],
                error_y=geno_all_means['标准差'],
                labels={'x': genotype, 'y': response},
                title='基因型综合均值比较（误差线=SD）',
                color=geno_all_means['总均值'],
                color_continuous_scale='Viridis'
            )
            fig_geno_bar.update_layout(height=420, showlegend=False)
            st.plotly_chart(fig_geno_bar, use_container_width=True, key='met_geno_bar')

        except Exception as e_mp:
            import traceback
            st.warning(f"多重比较执行异常: {e_mp}")
            st.code(traceback.format_exc())


        # ========== Tab 4: G×E交互作用分析 ==========
        st.markdown("---")
        st.markdown("#### 🔄 四、G×E 交互作用分析")

        env_means = df.groupby(environment)[response].mean().sort_values(ascending=False)
        geno_means = df.groupby(genotype)[response].mean().sort_values(ascending=False)

        tab_env, tab_geno, tab_ge = st.tabs(["环境表现", "基因型表现", "G×E交互矩阵"])

        with tab_env:
            fig_env = px.bar(x=env_means.index, y=env_means.values,
                           labels={'x': environment, 'y': response},
                           title='各环境平均表现')
            st.plotly_chart(fig_env, use_container_width=True, key='met_ge_env')

            env_cv = df.groupby(environment)[response].apply(
                lambda x: x.std()/x.mean()*100 if x.mean()!=0 else 0)
            cv_df = pd.DataFrame({'均值': env_means.round(2), 'CV%': env_cv.round(2)})
            st.dataframe(cv_df.sort_values('CV%', ascending=False))

        with tab_geno:
            fig_geno = px.bar(x=geno_means.index, y=geno_means.values,
                            labels={'x': genotype, 'y': response},
                            title='基因型平均表现（跨环境）')
            st.plotly_chart(fig_geno, use_container_width=True, key='met_ge_geno')

            rank_data = df.groupby([environment, genotype])[response].mean().groupby(level=genotype).rank(ascending=False)
            avg_rank = rank_data.groupby(genotype).mean().round(2).sort_values()
            fig_rank = px.bar(x=avg_rank.index, y=avg_rank.values,
                             labels={'x': genotype, 'y': '平均排名'},
                             title='基因型平均排名（越低越稳定）')
            st.plotly_chart(fig_rank, use_container_width=True, key='met_ge_rank')

        with tab_ge:
            ge_matrix = df.pivot_table(values=response, index=environment, columns=genotype, aggfunc='mean')
            grand_mean = df[response].mean()
            e_effects = df.groupby(environment)[response].mean() - grand_mean
            g_effects = df.groupby(genotype)[response].mean() - grand_mean

            ge_effects = pd.DataFrame(index=e_effects.index, columns=g_effects.index)
            for env_idx in e_effects.index:
                for gen_idx in g_effects.index:
                    subset = df[(df[environment]==env_idx)&(df[genotype]==gen_idx)][response]
                    if len(subset) > 0:
                        cell_mean = subset.mean()
                        ge_effects.loc[env_idx, gen_idx] = cell_mean - grand_mean - e_effects[env_idx] - g_effects[gen_idx]

            fig_ge = px.imshow(ge_effects.fillna(0), text_auto='.1f', aspect='auto',
                              color_continuous_scale='RdBu_r',
                              color_continuous_midpoint=0,
                              title='G×E 交互效应矩阵')
            fig_ge.update_layout(height=450)
            st.plotly_chart(fig_ge, use_container_width=True, key='met_ge_matrix')

        # ========== Tab 5: 品种稳定性分析 ==========
        st.markdown("---")
        st.markdown("#### ⚖️ 五、品种稳定性分析")

        stability_metrics = _compute_stability_metrics(df, response, genotype, environment)

        if stability_metrics is not None and len(stability_metrics) > 0:
            stab_df = pd.DataFrame(stability_metrics).round(4)
            stab_df = stab_df.sort_values('总均值', ascending=False)
            st.dataframe(stab_df.reset_index(drop=True), use_container_width=True)

            stab_col1, stab_col2 = st.columns(2)
            with stab_col1:
                fig_ms = go.Figure()
                fig_ms.add_trace(go.Scatter(
                    x=stab_df['总均值'], y=stab_df['CV%'],
                    mode='markers+text', text=stab_df[genotype],
                    textposition='top center',
                    marker=dict(size=14, color='#3498db'),
                    name='品种'
                ))
                fig_ms.update_layout(
                    title='均值 vs 变异系数（右下角最优）',
                    xaxis_title=f'{response} 均值', yaxis_title='CV (%)',
                    height=420
                )
                st.plotly_chart(fig_ms, use_container_width=True, key='stab_mean_cv')

            with stab_col2:
                if '排名范围' in stab_df.columns:
                    fig_rr = go.Figure()
                    fig_rr.add_trace(go.Scatter(
                        x=stab_df['平均排名'], y=stab_df['排名范围'].apply(
                            lambda x: float(x.split('~')[1]) if '~' in str(x) and x.split('~')[1] else 0),
                        mode='markers+text', text=stab_df[genotype],
                        textposition='top center',
                        marker=dict(size=14, color='#e74c3c'),
                        name='品种'
                    ))
                    fig_rr.update_layout(
                        title='平均排名 vs 最大排名波动（左下角最优）',
                        xaxis_title='平均排名', yaxis_title='最大排名',
                        height=420
                    )
                    st.plotly_chart(fig_rr, use_container_width=True, key='stab_rank_range')
        else:
            st.info("稳定性指标计算需要至少2个环境和2个重复")


        # ========== Tab 6: Eberhart-Russell 稳定性分析 ==========
        st.markdown("---")
        st.markdown("#### 📈 六、Eberhart-Russell 稳定性分析")

        er_results = _eberhart_russell_analysis(df, response, genotype, environment)

        if er_results is not None:
            er_df, fig_er, env_indices_df = er_results

            st.markdown("""
            **Eberhart-Russell (1966) 模型**：
            - 回归系数 bᵢ 衡量品种对环境变化的响应（b≈1 为平均响应，b>1 更敏感，b<1 更迟钝）
            - 偏差平方和 s²dᵢ 衡量对线性回归的偏离（越小越好，理想为0）
            """)

            st.dataframe(er_df.round(4).reset_index(drop=True), use_container_width=True)

            st.plotly_chart(fig_er, use_container_width=True, key='er_regression')

            if env_indices_df is not None:
                with st.expander("查看环境指数详情"):
                    st.dataframe(env_indices_df.round(4), use_container_width=True)
        else:
            st.info("Eberhart-Russell分析需要足够的环境数和重复数据")


        # ========== Tab 7: GGE双标图 ==========
        st.markdown("---")
        st.markdown("#### 🎯 七、主成分分解（GGE双标图）")

        from sklearn.decomposition import PCA
        from sklearn.preprocessing import StandardScaler

        pivot_for_pca = df.pivot_table(values=response, index=environment, columns=genotype, aggfunc='mean').fillna(0)
        scaler = StandardScaler()
        pca = PCA(n_components=min(2, min(n_gen, n_env)))
        scores = pca.fit_transform(scaler.fit_transform(pivot_for_pca.T))

        fig_biplot = go.Figure()

        fig_biplot.add_trace(go.Scatter(
            x=scores[:, 0], y=scores[:, 1],
            mode='markers+text', text=pivot_for_pca.T.index,
            textposition='top center', name=genotype,
            marker_size=12, marker_color='#3498db'
        ))

        loadings = pca.components_.T * np.sqrt(pca.explained_variance_)
        for i, env_name in enumerate(pivot_for_pca.index):
            fig_biplot.add_trace(go.Scatter(
                x=[0, loadings[i, 0]*2], y=[0, loadings[i, 1]*2],
                mode='lines+text', text=[None, str(env_name)[:4]],
                line=dict(color='#e74c3c', width=2), showlegend=False
            ))

        variance_explained = pca.explained_variance_ratio_ * 100
        fig_biplot.update_layout(
            title=f"GGE双标图 (PC1: {variance_explained[0]:.1f}%, PC2: {variance_explained[1]:.1f}%)",
            xaxis_title=f"PC1 ({variance_explained[0]:.1f}%)",
            yaxis_title=f"PC2 ({variance_explained[1]:.1f}%)",
            height=520, width=750
        )
        st.plotly_chart(fig_biplot, use_container_width=True, key='gge_biplot')

    except Exception as e:
        st.error(f"分析失败: {e}")
        import traceback; st.code(traceback.format_exc())


@st.cache_data
def _compute_stability_metrics(df, response, genotype, environment):
    """计算品种稳定性综合指标（缓存：数据不变时跳过重复计算）"""

    envs = sorted(df[environment].unique())
    genes = sorted(df[genotype].unique())

    results = []

    for g in genes:
        df_g = df[df[genotype] == g]
        g_mean = df_g[response].mean()
        g_std = df_g[response].std()

        # 1. CV%
        g_cv = (g_std / g_mean * 100) if g_mean != 0 else 0

        # 2. 各环境下的均值与排名
        env_means_list = []
        for e in envs:
            df_ge = df[(df[genotype]==g) & (df[environment]==e)]
            if len(df_ge) > 0:
                em = df_ge[response].mean()
                env_means_list.append(em)
            else:
                env_means_list.append(np.nan)

        # 各环境下排名
        all_env_ranks = []
        for e in envs:
            df_e = df[df[environment]==e]
            e_genos = df_e.groupby(genotype)[response].mean().sort_values(ascending=False)
            if g in e_genos.index:
                all_env_ranks.append(e_genos.index.tolist().index(g) + 1)
            else:
                all_env_ranks.append(np.nan)

        avg_rank = np.nanmean(all_env_ranks) if any(not np.isnan(r) for r in all_env_ranks) else np.nan
        valid_ranks = [r for r in all_env_ranks if not np.isnan(r)]
        rank_range = f'{int(min(valid_ranks))}~{int(max(valid_ranks))}' if len(valid_ranks) >= 2 else ''

        # 3. Shukla变异数（环境间标准差）
        valid_em = [v for v in env_means_list if not np.isnan(v)]
        shukla_var = np.std(valid_em, ddof=1) if len(valid_em) >= 2 else 0

        # 4. 综合评分
        max_mean = df.groupby(genotype)[response].mean().max()
        yield_score = g_mean / max_mean * 50 if max_mean > 0 else 0

        cvs = (df.groupby(genotype)[response].std() / df.groupby(genotype)[response].mean() * 100).replace([np.inf, -np.inf], 0).fillna(0)
        max_cv = cvs.max()
        stability_score = (1 - g_cv/max_cv) * 50 if max_cv > 0 else 25

        total_score = yield_score + stability_score

        results.append({
            genotype: g,
            '总均值': round(g_mean, 2),
            '标准差': round(g_std, 2),
            'CV%': round(g_cv, 2),
            '平均排名': round(avg_rank, 1) if not np.isnan(avg_rank) else '-',
            '排名范围': rank_range,
            'Shukla变异数': round(shukla_var, 4),
            '产量分': round(yield_score, 1),
            '稳定性分': round(stability_score, 1),
            '综合分': round(total_score, 1),
        })

    return results


def _eberhart_russell_analysis(df, response, genotype, environment):
    """
    Eberhart-Russell (1966) 稳定性分析

    模型: Yij = μi + bi*Ij + dij
    其中 Ij = 环境指数 = 所有品种在第j环境的均值 - 总均值
          bi = 第i品种的回归系数
          s2di = 偏离回归的均方（线性偏差）
    """

    envs = sorted(df[environment].unique())
    genes = sorted(df[genotype].unique())

    if len(envs) < 2:
        return None

    env_mean_all = df.groupby(environment)[response].mean()
    grand_mean = df[response].mean()
    environmental_index = env_mean_all - grand_mean

    er_records = []
    regression_lines = []

    for g in genes:
        geno_means_per_env = []
        ei_values = []

        for e in envs:
            df_ge = df[(df[genotype]==g) & (df[environment]==e)]
            if len(df_ge) > 0:
                gm = df_ge[response].mean()
                geno_means_per_env.append(gm)
                ei_values.append(environmental_index[e])

        if len(geno_means_per_env) >= 3:
            y_arr = np.array(geno_means_per_env)
            x_arr = np.array(ei_values)

            slope, intercept, r_value, p_value, std_err = stats.linregress(x_arr, y_arr)

            predicted = intercept + slope * x_arr
            deviations = y_arr - predicted

            n = len(y_arr)
            ss_deviation = np.sum(deviations**2)
            s2_d = ss_deviation / (n - 2) if n > 2 else 0

            geno_overall_mean = np.mean(y_arr)

            er_records.append({
                genotype: g,
                '均值': round(geno_overall_mean, 2),
                '截距(a)': round(intercept, 4),
                '回归系数(b)': round(slope, 4),
                's2d (偏差MS)': round(s2_d, 4),
                'R2': round(r_value**2, 4),
                '判断':
                    '稳定' if abs(slope - 1) <= 0.2 and s2_d < np.var(y_arr)*0.3
                    else ('敏感' if slope > 1.2 else '迟钝'),
                '推荐':
                    '广泛推广' if (abs(slope - 1) <= 0.3 and s2_d < np.var(y_arr)*0.5 and geno_overall_mean >= grand_mean)
                    else ('特定区域' if slope > 1.2 else '一般')
            })

            regression_lines.append({
                'geno': g,
                'x': list(x_arr),
                'y_actual': list(y_arr),
                'y_fit': list(predicted),
                'b': slope,
                'overall_mean': geno_overall_mean
            })

    if len(er_records) == 0:
        return None

    er_df = pd.DataFrame(er_records)

    # 绘制ER回归图
    fig_er = make_subplots(specs=[[{"secondary_y": True}]])

    ei_vals = environmental_index.values
    x_min, x_max = float(ei_vals.min()), float(ei_vals.max())
    x_pad = (x_max - x_min) * 0.15
    x_plot = np.array([x_min - x_pad, x_max + x_pad])

    colors = px.colors.qualitative.Set1 + px.colors.qualitative.Set2 + px.colors.qualitative.Dark24

    for i, rl in enumerate(regression_lines):
        color = colors[i % len(colors)]
        # 只画回归线（去掉散点）
        intercept_i = rl['overall_mean'] - rl['b'] * np.mean(rl['x'])
        y_line = intercept_i + rl['b'] * x_plot
        fig_er.add_trace(go.Scatter(
            x=list(x_plot), y=list(y_line),
            mode='lines', name=f"{rl['geno']} (b={rl['b']:.2f})",
            line=dict(color=color, width=2.5),
            legendgroup=rl['geno']
        ), secondary_y=False)

    y_ref = grand_mean + 1.0 * x_plot
    fig_er.add_trace(go.Scatter(
        x=list(x_plot), y=list(y_ref),
        mode='lines', line=dict(color='gray', width=1.5, dash='dot'),
        name='b=1 (平均响应)', showlegend=True
    ), secondary_y=False)

    fig_er.update_layout(
        title='Eberhart-Russell 稳定性回归分析<br><sup>虚线=回归拟合 | 点线=b=1参考线</sup>',
        xaxis_title='环境指数 (Ij)',
        yaxis_title=f'{response}',
        height=550,
        hovermode='closest',
        legend=dict(font=dict(size=10))
    )

    env_idx_df = pd.DataFrame({
        '环境': envs,
        '环境均值': [env_mean_all[e] for e in envs],
        '环境指数(Ij)': [environmental_index[e] for e in envs],
    }).round(2)

    return (er_df, fig_er, env_idx_df)


# ========== Alpha/不完全区组设计 ==========
def alpha_lattice_anova(df):
    """Alpha Lattice不完全区组设计的方差分析"""
    st.markdown("### 🧬 Alpha/不完全区组设计分析")
    sm, ols, anova_lm, pairwise_tukeyhsd = _get_statsmodels()
    
    st.info("""
    **Alpha设计**使用混合模型，区组效应为随机效应：
    - 完整区组（Rep）：固定效应
    - 不完全区组（IB）：随机效应
    - 处理效应：固定效应
    
    数据需要包含：处理、不完全区组、完整区组、观测值
    """)
    
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    _nc_cat = _detect_numeric_categorical(df, numeric_cols)
    all_categorical = df.select_dtypes(include=['object', 'category']).columns.tolist() + _nc_cat
    pure_numeric = [c for c in numeric_cols if c not in _nc_cat]
    
    _alpha_trt = _auto_match(df, all_categorical, _TRT_RULES)
    _alpha_rep = _auto_match(df, all_categorical, _REP_RULES, exclude=[_alpha_trt])
    _alpha_ib = _auto_match(df, all_categorical, _IB_RULES, exclude=[_alpha_trt, _alpha_rep])
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        response = st.selectbox("响应变量", pure_numeric, key="alpha_y")
    with col2:
        treatment = st.selectbox("处理变量", all_categorical, index=_safe_index(all_categorical, _alpha_trt), key="alpha_trt")
    with col3:
        other_cols = [c for c in all_categorical if c != treatment]
        rep_col = st.selectbox("完整区组", other_cols, index=_safe_index(other_cols, _alpha_rep), key="alpha_rep",
                               help="包含所有处理的完整区组（如 区组I、区组II、区组III）")
    with col4:
        ib_cols = [c for c in other_cols if c != rep_col]
        ib_col = st.selectbox("不完全区组", ib_cols, index=_safe_index(ib_cols, _alpha_ib), key="alpha_ib",
                              help="完整区组内的不完全子区组（如 IB1、IB2、IB3）")
    
    try:
        # Alpha设计的模型：处理（固定）+ 完整区组（固定）+ 不完全区组嵌套在完整区组中（随机）
        formula = f'Q("{response}") ~ C(Q("{treatment}")) + C(Q("{rep_col}")) + C(Q("{rep_col}")):C(Q("{ib_col}"))'
        model = ols(formula, data=df).fit()
        anova_table = anova_lm(model, typ=2)
        
        # ── 一、方差分析 ──
        st.markdown("---")
        st.markdown("#### 📊 一、方差分析")
        display_anova_table(anova_table, "Alpha不完全区组设计方差分析表")
        
        # 计算处理均值
        treatment_means = df.groupby(treatment)[response].agg(['mean', 'std', 'count']).round(3)
        treatment_means.columns = ['均值', '标准差', '重复数']
        
        # ── 二、处理效应分析 ──
        st.markdown("---")
        st.markdown("#### 📈 二、处理效应分析")
        st.dataframe(treatment_means.sort_values('均值', ascending=False))
        
        # 可视化
        fig = px.bar(treatment_means.reset_index().sort_values('均值', ascending=True),
                    x='均值', y=treatment, orientation='h', title=f'{response} 处理均值比较',
                    color='均值', color_continuous_scale='Blues')
        fig.update_layout(height=max(400, len(treatment_means) * 30), yaxis_title=treatment)
        st.plotly_chart(fig, use_container_width=True)
        
        # ── 三、多重比较 ──
        st.markdown("---")
        st.markdown("#### 🔬 三、多重比较")
        _alpha_selector()
        tab_t_alpha, tab_d_alpha = st.tabs(["Tukey HSD", "Duncan's SSR"])
        with tab_t_alpha:
            tukey = pairwise_tukeyhsd(df[response], df[treatment], alpha=_get_alpha())
            _display_tukey_result(tukey, _get_alpha())
        with tab_d_alpha:
            mse_alpha = model.mse_resid if hasattr(model, 'mse_resid') else np.nan
            df_e_alpha = model.df_resid if hasattr(model, 'df_resid') else None
            df_dun_a, mse_a, df_a, ms_a, ns_a, reps_a = _duncan_multiple_comparison(
                df[response], df[treatment], mse_val=mse_alpha, df_e=df_e_alpha)
            if df_dun_a is not None:
                _display_duncan_result(df_dun_a, mse_a, df_a, ns_a, ms_a, reps_a)
        
    except Exception as e:
        st.error(f"分析失败: {e}")


# ========== 增广设计分析 ==========
def augmented_anova(df):
    """增广设计的统计分析（对照有重复，测试无重复）"""
    st.markdown("### ➕ 增广设计分析")
    
    st.info("""
    **增广设计**分析特点：
    - 对照（Check）有重复，用于估计区组效应
    - 测试处理（Test）无重复，无法直接进行方差分析
    - 使用对照校正后的相对产量进行比较
    
    数据需要包含：处理、区组（如有）、类型（对照/测试）、观测值
    """)
    
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    _nc_cat = _detect_numeric_categorical(df, numeric_cols)
    all_categorical = df.select_dtypes(include=['object', 'category']).columns.tolist() + _nc_cat
    pure_numeric = [c for c in numeric_cols if c not in _nc_cat]
    
    _aug_trt = _auto_match(df, all_categorical, _TRT_RULES)
    _aug_type = _auto_match(df, all_categorical, _TYPE_RULES, exclude=[_aug_trt])
    _aug_blk = _auto_match(df, all_categorical, _BLOCK_RULES, exclude=[_aug_trt, _aug_type])
    
    col1, col2 = st.columns(2)
    with col1:
        response = st.selectbox("响应变量", pure_numeric, key="aug_y")
    with col2:
        treatment = st.selectbox("处理变量", all_categorical, index=_safe_index(all_categorical, _aug_trt), key="aug_trt")
    
    # 检测是否有类型列
    type_col = _aug_type
    
    if type_col:
        st.success(f"检测到类型列: {type_col}")
    else:
        st.warning("未检测到类型列，请手动指定哪些是对照")
        type_col = st.selectbox("处理类型列（如有）", [None] + all_categorical, key="aug_type")
    
    # 选择区组列
    block_cols = [c for c in all_categorical if c not in [treatment, type_col]]
    if block_cols:
        block_col = st.selectbox("区组变量（可选）", [None] + block_cols, index=_safe_index([None] + block_cols, _aug_blk), key="aug_block")
    
    try:
        # 分离对照和测试处理
        check_data = df[df[type_col].isin(['对照', 'CK', 'Check'])] if type_col else df[df[treatment].str.contains('CK|对照|ck', na=False)]
        test_data = df[df[type_col].isin(['测试', 'Test'])] if type_col else df[~df[treatment].str.contains('CK|对照|ck', na=False)]
        
        if len(check_data) == 0:
            st.error("未找到对照数据，请检查数据格式")
            return
        
        st.markdown(f"**数据概况：** 对照 {len(check_data)} 小区，测试处理 {len(test_data)} 小区")
        
        # 计算对照均值和区组效应
        check_means = check_data.groupby(treatment if type_col is None else treatment)[response].agg(['mean', 'count'])
        
        st.markdown("#### 对照处理统计")
        st.dataframe(check_means.round(3))
        
        # 计算校正后的测试处理产量
        if len(test_data) > 0 and block_col:
            block_means = check_data.groupby(block_col)[response].mean()
            grand_mean = check_data[response].mean()
            
            st.markdown("#### 测试处理校正产量")
            test_results = []
            for _, row in test_data.iterrows():
                block = row[block_col]
                block_effect = block_means.get(block, grand_mean) - grand_mean
                adjusted_yield = row[response] - block_effect
                test_results.append({
                    '处理': row[treatment],
                    '原始产量': row[response],
                    '区组效应': block_effect,
                    '校正产量': adjusted_yield
                })
            
            test_df = pd.DataFrame(test_results).sort_values('校正产量', ascending=False)
            st.dataframe(test_df.round(3))
        
        # 综合比较表
        st.markdown("#### 所有处理综合比较")
        all_means = df.groupby(treatment)[response].agg(['mean', 'std', 'count']).round(3)
        all_means.columns = ['均值', '标准差', '重复数']
        st.dataframe(all_means.sort_values('均值', ascending=False))
        
        # 可视化
        fig = px.box(df, x=treatment, y=response, title=f'{response} 处理分布',
                    color=type_col if type_col else None)
        fig.update_layout(height=400, xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"分析失败: {e}")


# ========== 间比法/对比法分析 ==========
def _is_ck(value, type_value=None):
    """判断一个处理值是否为 CK1 对照。
    
    只有名称中包含 CK1 文字的处理才被认定为CK1对照，参与间比法/对比法计算。
    其他对照（CK2、CK3等）不参与计算。
    """
    if type_value is not None:
        # 有类型列时：类型为"对照"且名称含CK1
        if str(type_value).strip() != '对照':
            return False
    # 无论是否有类型列，最终都必须名称含CK1
    s = str(value).strip().upper()
    return 'CK1' in s


def interval_contrast_anova(df):
    """间比法和对比法设计的分析 - 使用相对产量百分比法
    
    数据要求：
    - 位置列（必填）：表示小区在田间排列的顺序
    - 类型列（推荐）：值为"对照"或"处理"，用于区分对照和测试材料
    - 处理列：品种/处理名称，允许包含多个对照（如CK1、CK2等）
    
    对比算法只使用含 CK1 文字的对照进行对比计算。
    """
    st.markdown("### 📈 间比法/对比法分析")
    
    st.info("""
    **间比法/对比法**使用相对产量百分比分析：
    
    **对比法**：理论对照 = (左CK1 + 右CK1) / 2
               相对产量 = (处理产量 / 理论对照) × 100%
    
    **间比法**：理论对照 = (左CK1 + 右CK1) / 2
               相对产量 = (处理产量 / 理论对照) × 100%
    
    **说明**：只使用含 **CK1** 文字的对照进行对比计算。其他对照（如CK2、CK3）不参与计算。
    
    **判断标准**：相对产量 >110% 可能显著优于对照
    """)
    
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    categorical_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
    
    # ── 检测数字型但实际是分类的变量 ──
    numeric_cat_candidates = _detect_numeric_categorical(df, numeric_cols)
    
    # 分类变量候选 = 文本型 + 数字型分类变量
    all_categorical = categorical_cols + numeric_cat_candidates
    
    # 响应变量 = 纯数值列（排除数字型分类变量）
    pure_numeric = [c for c in numeric_cols if c not in numeric_cat_candidates]
    
    # ── 检测类型列 ──
    type_col = None
    for col in all_categorical:
        unique_vals = set(str(v).strip() for v in df[col].dropna().unique())
        if unique_vals.issubset({'对照', '处理', 'CK', 'Test', 'Check', '1', '0', '1.0', '0.0'}):
            # 进一步确认：如果有"对照"/"处理"文字就直接认定；如果是0/1编码则跳过（歧义太大）
            if unique_vals & {'对照', '处理', 'CK', 'Check'}:
                type_col = col
                break
    
    # ── 检测位置列（自动匹配） ──
    position_col = None
    for c in all_categorical:
        if c in ('位置', '小区号'):
            position_col = c
            break
    if position_col is None:
        # 模糊匹配：列名包含"位置"或"小区"
        for c in all_categorical:
            if '位置' in c or '小区' in c:
                position_col = c
                break

    # ── 变量选择 ──
    _ic_trt = _auto_match(df, all_categorical, _TRT_RULES)
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        response = st.selectbox("响应变量", pure_numeric if pure_numeric else numeric_cols, key="ic_y")
    with col2:
        treatment = st.selectbox("处理变量", all_categorical, index=_safe_index(all_categorical, _ic_trt), key="ic_trt")
    with col3:
        default_pos_idx = all_categorical.index(position_col) if position_col and position_col in all_categorical else 0
        position = st.selectbox("位置变量（必填）", all_categorical, index=default_pos_idx, key="ic_pos")
    with col4:
        type_options = [None] + all_categorical
        default_type_idx = type_options.index(type_col) if type_col in type_options else 0
        type_col = st.selectbox("类型列（对照/处理）", type_options, 
                                index=default_type_idx, key="ic_type")
    
    if not position:
        st.error("⚠️ 位置变量为必填项，请选择位置列（表示田间排列顺序）")
        return
    
    # ── 识别对照 ──
    def _mark_ck(row):
        """标记行是否为CK1对照"""
        if type_col and type_col != 'None':
            return _is_ck(row[treatment], row.get(type_col))
        return _is_ck(row[treatment])
    
    df_work = df.copy()
    df_work['_is_ck'] = df_work.apply(_mark_ck, axis=1)
    
    n_ck = df_work['_is_ck'].sum()
    n_test = len(df_work) - n_ck
    
    if n_ck == 0:
        st.error("数据中未找到含 CK1 文字的对照。请确保处理列中有含 'CK1' 的品种，或类型列中包含 '对照'。")
        return
    
    # 显示检测到的对照信息
    ck_names = df_work[df_work['_is_ck'] == True][treatment].unique()
    st.markdown(f"**数据概况：** 检测到 CK1 对照 {n_ck} 小区（{', '.join(ck_names)}），测试处理 {n_test} 小区")
    if type_col and type_col != 'None':
        st.success(f"使用类型列 '{type_col}' 区分对照和处理")
    
    try:
        # 按位置排序
        df_sorted = df_work.sort_values(position).reset_index(drop=True)
        
        # ── 统一分析：用左右两侧CK1均值作为理论对照，计算相对产量 ──
        ck_indices = [(idx, row[response]) for idx, row in df_sorted.iterrows() if row['_is_ck']]
        results = []
        
        if len(ck_indices) < 1:
            st.warning("需要至少1个CK1对照。")
        else:
            for idx, row in df_sorted.iterrows():
                if row['_is_ck']:
                    continue
                
                # 找前后最近的CK1
                left_ck_val = None
                right_ck_val = None
                
                # 向前找CK1
                for i in range(idx - 1, -1, -1):
                    if df_sorted.loc[i, '_is_ck']:
                        left_ck_val = df_sorted.loc[i, response]
                        left_ck_pos = df_sorted.loc[i, position]
                        break
                # 向后找CK1
                for i in range(idx + 1, len(df_sorted)):
                    if df_sorted.loc[i, '_is_ck']:
                        right_ck_val = df_sorted.loc[i, response]
                        right_ck_pos = df_sorted.loc[i, position]
                        break
                
                ck_vals = [v for v in [left_ck_val, right_ck_val] if v is not None]
                if not ck_vals:
                    continue
                
                ck_mean = np.mean(ck_vals)
                relative = (row[response] / ck_mean) * 100
                
                results.append({
                    '处理': row[treatment],
                    '位置': row[position],
                    response: row[response],
                    '相对值(%)': round(relative, 2),
                    '理论CK值': round(ck_mean, 2),
                    '左CK1值': left_ck_val if left_ck_val is not None else '-',
                    '右CK1值': right_ck_val if right_ck_val is not None else '-',
                    '左CK1位置': left_ck_pos if left_ck_val is not None else '-',
                    '右CK1位置': right_ck_pos if right_ck_val is not None else '-',
                })
        
        if results:
            results_df = pd.DataFrame(results).sort_values('位置')
            st.markdown("#### 分析结果")
            st.dataframe(results_df.reset_index(drop=True), use_container_width=True)
            
            # 下载按钮
            csv_bytes = results_df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
            if can_download():
                st.download_button(label="📥 下载分析结果（CSV）", data=csv_bytes,
                                   file_name="分析结果.csv", mime="text/csv")
            else:
                st.warning("⚠️ 分析次数已用完，充值后可下载结果。请前往侧边栏「💎 充值中心」。")
            
            # 可视化：按处理均值，从高到低
            trt_mean = results_df.groupby('处理')['相对值(%)'].mean().round(2).sort_values(ascending=False)
            chart_df = trt_mean.reset_index()
            chart_df.columns = ['处理', '相对值(%)']
            
            fig = px.bar(chart_df,
                        x='处理', y='相对值(%)',
                        title=f'{response} — 各处理相对产量均值（从高到低）',
                        color='相对值(%)',
                        color_continuous_scale=['#e74c3c', '#f1c40f', '#27ae60'],
                        text=chart_df['相对值(%)'].apply(lambda x: f'{x:.1f}%'),
                        color_continuous_midpoint=100)
            fig.add_hline(y=100, line_dash="dash", line_color="gray", annotation_text="对照基准(100%)")
            fig.add_hline(y=110, line_dash="dot", line_color="red", annotation_text="显著标准(110%)")
            # Y轴起始值：取最小值向下取整到最近的10，留出底部空间
            y_min = chart_df['相对值(%)'].min()
            y_start = max(0, (y_min // 10) * 10 - 5)
            fig.update_layout(height=max(400, len(chart_df) * 25 + 100), 
                              xaxis_tickangle=-45, showlegend=False,
                              yaxis_range=[y_start, None])
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("未找到有效的分析结果。请检查数据中CK1对照是否按位置排列。")
        
    except Exception as e:
        st.error(f"分析失败: {e}")
        import traceback
        st.code(traceback.format_exc())


# ========== 通用显示函数 ==========
def _rename_anova_index(anova_table, environment, genotype, block_var=None, is_met=False):
    """将ANOVA表的index重命名为中文变异来源名称"""
    rename_map = {}
    env_str = str(environment)
    geno_str = str(genotype)
    block_str = str(block_var) if block_var is not None else None
    block_label = '区组（环境内）' if is_met else '区组'

    for idx in anova_table.index:
        idx_str = str(idx)
        # 1. 交互项（包含冒号）优先匹配 — 必须同时含环境和基因型
        if ':' in idx_str and env_str in idx_str and geno_str in idx_str:
            rename_map[idx] = '基因型×环境'
        # 2. 区组项（在环境之前匹配，避免区组列名含环境名字符时误判）
        elif block_str is not None and block_str in idx_str:
            rename_map[idx] = block_label
        # 3. 环境主效应
        elif env_str in idx_str and 'C(Q(' in idx_str:
            rename_map[idx] = '环境'
        elif env_str == idx_str:
            rename_map[idx] = '环境'
        # 4. 基因型主效应
        elif geno_str in idx_str and 'C(Q(' in idx_str:
            rename_map[idx] = '基因型'
        elif geno_str == idx_str:
            rename_map[idx] = '基因型'
        # 5. 残差/误差
        elif 'Residual' in idx_str:
            rename_map[idx] = '误差'
        else:
            rename_map[idx] = idx

    renamed = anova_table.rename(index=rename_map)
    return renamed


def display_anova_table(anova_table, title):
    """格式化显示ANOVA表格（含均方列）"""

    # 清理表格
    display_table = anova_table.copy()

    # 自动清理 index 中的 C(Q("...")) 格式，只保留变量名
    cleaned_index = {}
    for idx in display_table.index:
        idx_str = str(idx)
        # 匹配 C(Q("var")) 或 C(Q('var')) 模式，提取变量名
        m = re.findall(r'C\(Q\(["\']([^"\']+)["\']\)\)', idx_str)
        if m:
            cleaned_index[idx] = ':'.join(m)
    if cleaned_index:
        display_table = display_table.rename(index=cleaned_index)

    # 翻译 Residual 为中文
    residual_rename = {idx: '残差' for idx in display_table.index if str(idx).lower() == 'residual'}
    if residual_rename:
        display_table = display_table.rename(index=residual_rename)

    # 翻译 Intercept 为中文
    intercept_rename = {idx: '截距' for idx in display_table.index if str(idx) == 'Intercept'}
    if intercept_rename:
        display_table = display_table.rename(index=intercept_rename)

    # 添加均方(MS) = SS / df
    if 'sum_sq' in display_table.columns and 'df' in display_table.columns:
        safe_df = display_table['df'].replace(0, np.nan)
        display_table['MS'] = (display_table['sum_sq'] / safe_df).round(4)

    # 添加显著性标记
    def add_sig(p):
        if pd.isna(p): return "-"
        if p < 0.001: return "***"
        elif p < 0.01: return "**"
        elif p < 0.05: return "*"
        else: return "n.s."

    if 'PR(>F)' in display_table.columns or 'p-value' in display_table:
        pcol = 'PR(>F)' if 'PR(>F)' in display_table.columns else 'p-value'  # type: ignore
        display_table['显著性'] = display_table[pcol].apply(add_sig)  # type: ignore
        display_table.rename(columns={pcol: 'p值'}, inplace=True)  # type: ignore

    # 重命名列（全中文）
    rename_map = {
        'sum_sq': '平方和',
        'df': '自由度',
        'MS': '均方',
        'F': 'F值'
    }
    display_table.rename(columns=rename_map, inplace=True)  # type: ignore

    # 统一列顺序：自由度, 平方和, 均方, F值, p值, 显著性
    col_order = [c for c in ['自由度', '平方和', '均方', 'F值', 'p值', '显著性'] if c in display_table.columns]
    display_table = display_table[col_order]

    st.markdown(f"#### {title}")
    st.dataframe(display_table.round(4), use_container_width=True)


def plot_significance_groups(tukey_result, treatment_means, response_var):
    """绘制显著性字母分组图"""
    
    try:
        summary_df = pd.DataFrame(data=tukey_result._results_table.data[1:], 
                                  columns=tukey_result._results_table.data[0])  # type: ignore
        
        groups = set(summary_df.iloc[:, 0].unique()) | set(summary_df.iloc[:, 1].unique())
        group_order = sorted(groups, key=lambda x: treatment_means.loc[x, 'mean'] if x in treatment_means.index else 0, reverse=True)  # type: ignore
        
        # 构建字母标注
        letter_dict = {}
        letters = list('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
        current_letter_idx = 0
        
        for g in group_order:
            comparisons = summary_df[
                ((summary_df.iloc[:, 0] == g) | (summary_df.iloc[:, 1] == g)) & 
                (summary_df.iloc[:, -1] == True)
            ]
            
            if len(comparisons) > 0:
                letter_dict[g] = letters[current_letter_idx]
                current_letter_idx += 1
            else:
                letter_dict[g] = letters[current_letter_idx]
        
        means_sorted = treatment_means.sort_values('mean', ascending=True)
        fig = go.Figure()
        
        colors = ['#3498db', '#2ecc71', '#e74c3c', '#f39c12', '#9b59b6', '#1abc9c']
        for i, (idx, row) in enumerate(means_sorted.iterrows()):
            letter = letter_dict.get(idx, '')
            fig.add_trace(go.Bar(
                x=[row['mean']],
                name=f"{idx} ({letter})",
                marker_color=colors[i % len(colors)]
            ))
        
        fig.update_layout(
            barmode='group',
            title=f'{response_var} 处理均值比较（字母相同表示差异不显著）',
            showlegend=True,
            height=400
        )
        st.plotly_chart(fig, use_container_width=True)
        
    except Exception as e:
        st.caption(f"字母分组图生成失败: {e}")


if __name__ == "__main__":
    render_anova()