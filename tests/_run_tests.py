"""独立测试运行器，避免 PowerShell CLIXML 的问题"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from tests.test_ssr_analysis import *

if __name__ == '__main__':
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # 按顺序加载测试
    suite.addTests(loader.loadTestsFromTestCase(TestDataLoading))
    suite.addTests(loader.loadTestsFromTestCase(TestSSRMultipleComparisonRefactored))
    suite.addTests(loader.loadTestsFromTestCase(TestEdgeCases))
    suite.addTests(loader.loadTestsFromTestCase(TestStabilityAnalysis))
    suite.addTests(loader.loadTestsFromTestCase(TestCKComparison))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
