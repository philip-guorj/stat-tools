"""Integration verification for trial report module"""
from modules.trial_report_analysis import *

# Verify all 9 classes
cls = ['SSRMultipleComparison','StabilityAnalysis','CKComparison','SSRReportGenerator',
       'BiplotAnalysis','TrialEvaluation','Diagnostics','TrialReportConfig','ReportExporter']
for c in cls:
    obj = eval(c)
    assert isinstance(obj, type), f'{c} not a class'
print('All 9 classes verified')

# Verify ECO_REGIONS
assert len(TrialReportConfig.ECO_REGIONS) == 12
print('12 eco regions OK')

# Evaluate promotion test
td = {'genotypes':['A','B','C'],'yield_values':{'A':700,'B':680,'C':650},
      'ck_index':1,'per_environment':{'E1':{'A':710,'B':690,'C':660},'E2':{'A':690,'B':670,'C':640}}}
jr = TrialReportConfig.evaluate_promotion(td, 5)
for g in ['A','B','C']:
    print(g, jr[g]['judgment'])

# Example CSV  
import pandas as pd
df = pd.read_csv('data/\u533a\u8bd5\u8bd5\u9a8c\u793a\u4f8b\u6570\u636e.csv', encoding='utf-8-sig')
print('Example data: %d rows, %d genotypes, %d sites' % (len(df), df['品种'].nunique(), df['地点'].nunique()))
print('ALL VERIFICATIONS PASSED')
