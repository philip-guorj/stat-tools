"""精简版端到端测试：验证新增功能"""
import sys; sys.path.insert(0, '.')
import pandas as pd, numpy as np, os
from modules.trial_report_analysis import (
    TrialReportConfig, ReportExporter, TrialEvaluation
)

print('='*60)
print('StatTools 区试报告 新增功能测试')
print('='*60)

# 1. JSON 扩展字段
print('\n[1] 验证 JSON 扩展字段...')
for eid in [1, 4, 5, 7, 8]:
    cfg = TrialReportConfig.get_config(eid)
    fields = [k for k in ['plant_info','main_title','pip','d_list','lt_pip'] if k in cfg]
    print(f'    id={eid} {cfg["name"]}: {fields}')

# 2. 新图表方法
print('\n[2] 验证新图表方法...')
np.random.seed(42)
df = pd.DataFrame({
    '品种': np.repeat(['A','B','C','D'], 12),
    '地点': np.tile(['L1','L2','L3'], 16),
    '产量': np.random.normal(500, 50, 48)
})
fig1 = TrialEvaluation.plot_variety_mean_heatmap(df, '产量', '品种', '地点')
fig2 = TrialEvaluation.plot_variety_error_bar(df, '产量', '品种', '地点')
fig3 = TrialEvaluation.plot_variety_three_point(df, '产量', '品种', '地点')
print('    品种均值热图: OK')
print('    品种均值误差图: OK')
print('    品种三维评价图: OK')

# 3. Word 导出
print('\n[3] 验证 Word 导出（含生产试验模式）...')
report_data = {
    'overview': {'title': '区域试验', 'year': '2025', 'n_genotypes': 4, 'n_environments': 3, 'n_replicates': 4},
    'judgment': {
        'A': {'judgment': '晋级', 'yield_value': 520, 'diff_percent': 5.2, 'yield_diff': 26, 'win_rate': 75},
        'B': {'judgment': '晋级', 'yield_value': 510, 'diff_percent': 3.1, 'yield_diff': 15, 'win_rate': 62},
        'C': {'judgment': '待定', 'yield_value': 495, 'diff_percent': 0.0, 'yield_diff': 0, 'win_rate': 45},
        '对照': {'judgment': '-', 'yield_value': 495, 'diff_percent': 0, 'yield_diff': 0, 'win_rate': 50},
    }
}
for mode, label in [(False, '区域试验'), (True, '生产试验')]:
    path = ReportExporter.export_to_word(report_data, 5, is_production_trial=mode)
    size = os.path.getsize(path) / 1024
    print(f'    {label}: {path} ({size:.0f}KB)')
    os.remove(path)

# 4. Excel 导出
print('\n[4] 验证 Excel 导出（含生产试验模式）...')
for mode, label in [(False, '区域试验'), (True, '生产试验')]:
    path = ReportExporter.export_to_excel(report_data, 5, is_production_trial=mode)
    size = os.path.getsize(path) / 1024
    print(f'    {label}: {path} ({size:.0f}KB)')
    os.remove(path)

# 5. 生产试验切换测试
print('\n[5] 验证生产试验模式...')
cfg = TrialReportConfig.get_config(5)
print(f'    pip (区域): {cfg.get("pip","")[:40]}...')
print(f'    lt_pip (生产): {cfg.get("lt_pip","")[:40]}...')

print('\n' + '='*60)
print('所有测试通过!')
print('='*60)
