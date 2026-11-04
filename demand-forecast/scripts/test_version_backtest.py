import copy
import math
from pathlib import Path
import unittest
import version_backtest as app

class VersionComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original=app.load(app.ROOT/'assets'/'v1-frozen.json')
        cls.data=app.load(app.ROOT/'assets'/'nev-evidence.json')
        cls.rows=app.monthly.read(app.ROOT/'assets'/'nev-monthly.csv',cls.data['as_of'])

    def test_frozen_original_reproduces_published_baseline(self):
        last=self.data['history'][-1];a=self.data['recent']['2026_ytd'];b=self.data['recent']['2025_ytd']
        anchor={'year':2026,'auto':last['auto']*a['auto']/b['auto'],'nev':last['nev']*a['nev']/b['nev']}
        self.assertAlmostEqual(app.v1_total(self.original['history'],anchor,1),2179.219705797201)
        self.assertAlmostEqual(app.v1_total(self.original['history'],anchor,2),2480.213264947118)

    def test_2026_is_excluded_from_original_scoring(self):
        legacy,paired=app.annual_compare(self.original,self.data)
        self.assertEqual({r['target'] for r in legacy if r['horizon']==1},set(map(str,range(2021,2026))))
        self.assertTrue(all(int(r['target'])<=2025 for r in legacy+paired))

    def test_common_annual_totals_are_aligned(self):
        _,paired=app.annual_compare(self.original,self.data)
        methods={r['method'] for r in paired}
        keys=[{(r['origin'],r['target'],r['horizon']) for r in paired if r['method']==m and r['market']=='总量'} for m in methods]
        self.assertTrue(all(k==keys[0] for k in keys))
        self.assertEqual({r['target'] for r in paired if r['horizon']==1},{'2023','2024','2025'})

    def test_original_does_not_invent_export_split(self):
        _,paired=app.annual_compare(self.original,self.data)
        self.assertTrue(all(r['market']=='总量' for r in paired if r['method'].startswith('V1')))

    def test_unused_income_parameter_does_not_change_reference(self):
        changed=copy.deepcopy(self.data);changed['external_income_elasticity']['value']=100
        self.assertEqual(app.annual_compare(self.original,self.data),app.annual_compare(self.original,changed))

    def test_future_actual_does_not_change_earlier_predictions(self):
        before=app.monthly_compare(self.rows)[0]
        changed=copy.deepcopy(self.rows)
        for row in changed[48:]:
            for key in ('nev','nev_export','domestic_nev'):row[key]*=.8
        after=app.monthly_compare(changed)[0]
        key=lambda r:(r['origin'],r['target'],r['method'],r['market'],r['horizon'],r['lead_start'])
        old={key(r):r['prediction'] for r in before if r['origin']<self.rows[48]['period']}
        new={key(r):r['prediction'] for r in after if r['origin']<self.rows[48]['period']}
        self.assertEqual(old,new)

    def test_monthly_accounting_and_window_coverage(self):
        rows,_,_=app.monthly_compare(self.rows)
        app.cancellation(rows)
        for r in rows:
            self.assertGreaterEqual(r['monthly_abs_error']+1e-7,abs(r['error']))
            self.assertLess(r['origin'],r['target_start'])
        group=[r for r in rows if r['method']=='V1月度适配' and r['horizon']==12 and r['lead_start']==1]
        self.assertGreater(len(group),12)
        self.assertEqual(len({r['target'][:4] for r in group}),3)

    def test_bridge_uses_only_three_past_actual_years(self):
        rows=app.bridge_test(self.rows,self.data)
        self.assertEqual({r['target'] for r in rows},{'2023','2024','2025'})
        app.cancellation(rows)

    def test_2026_is_forecast_not_actual(self):
        estimates,_=app.estimated_2026(self.rows,self.data)
        self.assertTrue(all('预测' in r['nature'] for r in estimates))
        for r in estimates:self.assertAlmostEqual(r['国内']+r['出口'],r['总量'])

    def test_september_chain_does_not_fit_future_annual_actual(self):
        before=app.september_chain(self.original,self.rows,self.data)
        changed=copy.deepcopy(self.data)
        for r in changed['history']:
            if r['year']>=2024:r['nev']*=.9
        after=app.september_chain(self.original,self.rows,changed)
        self.assertEqual([r['prediction'] for r in before],[r['prediction'] for r in after])
        self.assertEqual({r['target'] for r in before},{'2024','2025'})

if __name__=='__main__':unittest.main()
