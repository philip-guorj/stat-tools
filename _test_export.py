"""测试 ReportExporter 基本功能"""
import sys, os; sys.path.insert(0, os.path.dirname(__file__))
import pandas as pd
from modules.trial_report_analysis import ReportExporter, TrialReportConfig

eco_cfg = TrialReportConfig.get_config(4)
report_data = {
    'overview': {'title': eco_cfg['title'], 'year': '2025',
                 'n_genotypes': 8, 'n_environments': 5, 'n_replicates': 3},
    'anova': {'anova_table': pd.DataFrame({
        '来源': ['品种', '环境', 'G×E', '误差', '总计'],
        'DF': [7, 4, 28, 80, 119],
        'SS': [1256.3, 892.1, 456.2, 324.5, 2929.1],
        'MS': [179.47, 223.03, 16.29, 4.06, ''],
        'F': [44.23, 54.96, 4.02, '', ''],
    })},
    'multiple_comparison': {'method': 'Duncan', 'cld_table': pd.DataFrame({
        '处理': ['A', 'B', 'C', 'D'],
        '均值': [680, 650, 620, 590],
        '字母标识': ['a', 'ab', 'bc', 'cd'],
    })},
    'stability': {'shukla': pd.DataFrame({
        '品种': ['A', 'B', 'C', 'D'],
        '总均值': [680, 650, 620, 590],
        'Shukla变异数': [120, 95, 150, 80],
    })},
    'ammi': {'ipc_table': pd.DataFrame({
        'IPC': ['IPC1', 'IPC2'],
        '奇异值': [12.5, 8.3],
        '方差贡献率(%)': [55.3, 24.7],
        '累积贡献率(%)': [55.3, 80.0],
    }), 'cum_var': 80.0},
    'judgment': {g: {
        'yield_value': v,
        'diff_percent': (v - 620) / 620 * 100,
        'win_rate': 60,
        'judgment': '晋级' if (v - 620) / 620 * 100 >= 3 else ('待定' if v >= 620 else '淘汰'),
        'detail': f'较郑单958增产{(v-620)/620*100:+.1f}%'
    } for g, v in [('A', 680), ('B', 650), ('C', 620), ('D', 590)]},
}
path = ReportExporter.export_to_word(report_data, eco_region_id=4)
print(f'SUCCESS: {path}')
