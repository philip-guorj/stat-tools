"""测试 modules/combining.py — NCII 设计与 Diallel 双列杂交分析"""

import sys, os
import pytest
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

df_ncii = pd.read_csv('data/NCII设计示例数据.csv', encoding='utf-8-sig')
df_diallel = pd.read_csv('data/Diallel设计示例数据.csv', encoding='utf-8-sig')


# =============================================================================
# 数据加载验证
# =============================================================================
class TestDataLoading:
    def test_ncii_shape(self):
        assert len(df_ncii) == 24
        assert set(df_ncii.columns) == {'母本', '父本', '区组', '产量'}
        assert df_ncii['母本'].nunique() == 3
        assert df_ncii['父本'].nunique() == 4
        assert df_ncii['区组'].nunique() == 2

    def test_diallel_shape(self):
        assert len(df_diallel) == 20
        assert set(df_diallel.columns) == {'亲本1', '亲本2', '区组', '产量'}
        assert df_diallel['亲本1'].nunique() == 5
        assert df_diallel['亲本1'].nunique() == df_diallel['亲本2'].nunique()


# =============================================================================
# NCII 分析测试
# =============================================================================
class TestNCIIAnalysis:
    @classmethod
    def setup_class(cls):
        try:
            from modules.combining import NCIIAnalysis
            cls.NCII = NCIIAnalysis
            cls.available = True
        except ImportError:
            cls.available = False

    def test_module_available(self):
        assert self.available, 'modules.combining 未导入'

    def test_ncii_anova_returns_dict(self):
        result = self.NCII.ncii_anova(df_ncii, '母本', '父本', '区组', '产量')
        assert isinstance(result, dict)
        assert 'anova' in result
        assert 'gca_female' in result
        assert 'gca_male' in result
        assert 'sca' in result
        assert 'variance_components' in result

    def test_ncii_anova_has_correct_columns(self):
        result = self.NCII.ncii_anova(df_ncii, '母本', '父本', '区组', '产量')
        # GCA 母本
        assert 'GCA效应' in result['gca_female'].columns
        assert '类型' in result['gca_female'].columns
        assert len(result['gca_female']) == 3
        # GCA 父本
        assert 'GCA效应' in result['gca_male'].columns
        assert len(result['gca_male']) == 4
        # SCA
        assert 'SCA效应' in result['sca'].columns
        assert len(result['sca']) == 12  # 3×4

    def test_gca_female_sign(self):
        """母A GCA 应为正（已知真值 3.0）"""
        result = self.NCII.ncii_anova(df_ncii, '母本', '父本', '区组', '产量')
        gca_a = result['gca_female'][result['gca_female']['母本'] == '母A']['GCA效应'].values[0]
        assert gca_a > 0, f'母A GCA 应为正, 实际 {gca_a}'

    def test_gca_male_sign(self):
        """父D GCA 应为正（已知真值 2.0）"""
        result = self.NCII.ncii_anova(df_ncii, '母本', '父本', '区组', '产量')
        gca_d = result['gca_male'][result['gca_male']['父本'] == '父D']['GCA效应'].values[0]
        assert gca_d > 0, f'父D GCA 应为正, 实际 {gca_d}'

    def test_variance_components_key(self):
        """方差分量包含关键字段"""
        result = self.NCII.ncii_anova(df_ncii, '母本', '父本', '区组', '产量')
        vc = result['variance_components']
        for key in ['σ²_F (母本GCA)', 'σ²_M (父本GCA)', 'σ²_SCA (F×M)', 'GCA/SCA 比值']:
            assert key in vc, f'缺少 {key}'

    def test_ncii_gca_effects_merged(self):
        """合并的 GCA 效应表"""
        merged = self.NCII.ncii_gca_effects(df_ncii, '母本', '父本', '产量')
        assert '亲本' in merged.columns
        assert 'GCA效应' in merged.columns
        assert len(merged) == 7  # 3+4

    def test_ncii_sca_effects(self):
        """SCA 效应矩阵"""
        sca = self.NCII.ncii_sca_effects(df_ncii, '母本', '父本', '产量')
        assert 'SCA效应' in sca.columns
        assert len(sca) == 12

    def test_ncii_no_block(self):
        """无区组列时也能运行"""
        result = self.NCII.ncii_anova(df_ncii, '母本', '父本', response='产量')
        assert 'gca_female' in result


# =============================================================================
# Diallel 分析测试
# =============================================================================
class TestDiallelAnalysis:
    @classmethod
    def setup_class(cls):
        try:
            from modules.combining import DiallelAnalysis
            cls.DA = DiallelAnalysis
            cls.available = True
        except ImportError:
            cls.available = False

    def test_module_available(self):
        assert self.available, 'modules.combining 未导入'

    def test_griffing4_returns_dict(self):
        result = self.DA.griffing4(df_diallel, '亲本1', '亲本2', '产量', '区组')
        assert isinstance(result, dict)
        assert result['method'] == 'Griffing 方法4'
        assert 'gca' in result
        assert 'sca' in result
        assert result['n_parents'] == 5

    def test_griffing4_gca_count(self):
        """GCA 应有5个亲本"""
        result = self.DA.griffing4(df_diallel, '亲本1', '亲本2', '产量', '区组')
        assert len(result['gca']) == 5

    def test_griffing4_sca_count(self):
        """SCA 应有10个组合 (C(5,2)=10)"""
        result = self.DA.griffing4(df_diallel, '亲本1', '亲本2', '产量', '区组')
        assert len(result['sca']) == 10

    def test_griffing4_gca_sign(self):
        """P1 GCA 应为正 (已知真值 2.0)"""
        result = self.DA.griffing4(df_diallel, '亲本1', '亲本2', '产量', '区组')
        gca_p1 = result['gca'][result['gca']['亲本'] == 'P1']['GCA效应'].values[0]
        assert gca_p1 > 0, f'P1 GCA 应为正, 实际 {gca_p1}'

    def test_griffing2_available(self):
        """Griffing 方法2 可用"""
        result = self.DA.griffing2(df_diallel, '亲本1', '亲本2', '产量', '区组')
        assert result['method'] == 'Griffing 方法2'

    def test_diallel_anova(self):
        """通用双列杂交方差分析"""
        result = self.DA.diallel_anova(df_diallel, '亲本1', '亲本2', '产量', '区组')
        assert 'anova' in result
        assert result['n_parents'] == 5


# =============================================================================
# 边缘情况测试
# =============================================================================
class TestEdgeCases:
    @classmethod
    def setup_class(cls):
        try:
            from modules.combining import NCIIAnalysis, DiallelAnalysis
            cls.NCII = NCIIAnalysis
            cls.DA = DiallelAnalysis
            cls.available = True
        except ImportError:
            cls.available = False

    def test_ncii_single_female(self):
        """单母本 — 至少不崩溃"""
        small = df_ncii[df_ncii['母本'] == '母A']
        result = self.NCII.ncii_anova(small, '母本', '父本', '区组', '产量')
        assert 'gca_female' in result

    def test_diallel_no_block(self):
        """Diallel 无区组时可用"""
        result = self.DA.griffing4(df_diallel, '亲本1', '亲本2', '产量')
        assert result['n_parents'] == 5

    def test_diallel_gca_sum_zero(self):
        """GCA 效应之和应接近0"""
        result = self.DA.griffing4(df_diallel, '亲本1', '亲本2', '产量', '区组')
        gca_sum = sum(result['gca']['GCA效应'])
        assert abs(gca_sum) < 0.5, f'GCA 效应之和应接近0, 实际 {gca_sum}'
