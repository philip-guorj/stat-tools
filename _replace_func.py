import sys
content = open('pages/03_方差分析.py', encoding='utf-8').read()

old_start = 'def _display_tukey_result(tukey_obj):'
old_end = '        st.warning(f"无法显示Tukey结果详情: {e}")\n'

# Find the old function boundaries
start_idx = content.find(old_start)
if start_idx == -1:
    print('ERROR: cannot find _display_tukey_result')
    sys.exit(1)

end_idx = content.find('\n\ndef render_anova():', start_idx)
if end_idx == -1:
    print('ERROR: cannot find render_anova')
    sys.exit(1)

old_func = content[start_idx:end_idx]

new_func = r'''def _display_tukey_result(tukey_obj):
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
            if hasattr(tukey_obj, '_multicomp') and hasattr(tukey_obj._multicomp', 'data'):
                df_tukey = pd.DataFrame(data=tukey_obj._multicomp.data,
                                        columns=['group1','group2','meandiff','p-adj',
                                                 'lower','upper','reject'])
        except Exception:
            pass

    if df_tukey is not None:
        with st.expander("Tukey HSD \u6210\u5bf9\u6bd4\u8f83\u8be6\u60c5", expanded=False):
            st.dataframe(df_tukey)
        _render_cld_letters(tukey_obj, df_tukey)
    else:
        st.info("Tukey HSD \u68c0\u9a8c\u5df2\u5b8c\u6210")


def _render_cld_letters(tukey_obj, df_tukey):
    import string
    groups = sorted(tukey_obj.groupsunique)

    non_reject_pairs = set()
    col_names = list(df_tukey.columns)
    reject_col = 'reject' if 'reject' in col_names else col_names[-1]

    for _, row in df_tukey.iterrows():
        g1 = str(row.iloc[0])
        g2 = str(row.iloc[1])
        try:
            rej_val = row.get(reject_col, True)
            if rej_val == False or str(rej_val) == 'False':
                non_reject_pairs.add((g1, g2))
                non_reject_pairs.add((g2, g1))
        except Exception:
            pass

    group_means = {g: float(np.mean(tukey_obj.data[tukey_obj.groups == g])) for g in groups}
    sorted_groups = sorted(groups, key=lambda x: group_means[x], reverse=True)

    letter_assignment = {}
    for i, g in enumerate(sorted_groups):
        assigned = set()
        for j in range(i):
            prev_g = sorted_groups[j]
            if (g, prev_g) in non_reject_pairs or (prev_g, g) in non_reject_pairs:
                shared = letter_assignment.get(prev_g, set())
                if shared:
                    assigned.add(min(shared))
        if not assigned:
            n_assigned = len([sg for sg in sorted_groups[:i] if sg in letter_assignment])
            assigned.add(string.ascii_uppercase[n_assigned])
        letter_assignment[g] = assigned

    cld_rows = []
    for g in sorted_groups:
        letters = ''.join(sorted(letter_assignment.get(g, set())))
        cld_rows.append({'基因型/处理': g, '均值': round(group_means[g], 2), '字母标识': letters})

    df_cld = pd.DataFrame(cld_rows)

    c1, c2 = st.columns([2, 3])
    with c1:
        st.markdown('**显著性字母标识** (不同字母 -> p<0.05):')
        st.dataframe(df_cld.reset_index(drop=True), use_container_width=True)

    with c2:
        fig_cld = go.Figure()
        means_vals = [group_means[g] for g in sorted_groups]
        letters_display = [''.join(sorted(letter_assignment.get(g, set()))) for g in sorted_groups]
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


'''

content = content[:start_idx] + new_func + content[end_idx:]
open('pages/03_方差分析.py', 'w', encoding='utf-8').write(content)
print('OK - replaced successfully')
