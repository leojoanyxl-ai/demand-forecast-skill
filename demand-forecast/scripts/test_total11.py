import copy
import unittest
import run_full
import total11_forecast as app

class TotalHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=run_full.load(app.ROOT/'assets'/'nev-evidence.json')
        cls.history=run_full.load(app.ROOT/'assets'/'v1-frozen.json')['history']
        cls.config,_=run_full.prepare(cls.data,run_full.load(app.ROOT/'assets'/'nev-economic-scenario.example.json'))

    def test_all_eleven_years_affect_reference(self):
        rows,fit=app.calculate(self.history,self.data,self.config)
        changed=copy.deepcopy(self.history);changed[0]['nev']*=2
        other,_=app.calculate(changed,self.data,self.config)
        self.assertEqual(fit['observations'],11)
        self.assertNotEqual(rows[0]['total_reference'],other[0]['total_reference'])

    def test_estimated_2026_is_not_added_to_training(self):
        changed=copy.deepcopy(self.history);changed.append({'year':2026,'auto':3250,'nev':1820})
        with self.assertRaises(ValueError):app.calculate(changed,self.data,self.config)

    def test_primary_reference_is_original_eleven_year_reference(self):
        rows,_=app.calculate(self.history,self.data,self.config)
        self.assertAlmostEqual(rows[0]['total_reference'],2179.219705797201)

    def test_condition_factor_and_independent_branches_are_disclosed(self):
        rows,_=app.calculate(self.history,self.data,self.config)
        for r in rows:
            self.assertAlmostEqual(r['domestic_weight']+r['export_weight'],1)
            self.assertAlmostEqual(r['total_conditioned'],r['total_reference']*r['condition_factor'])
            self.assertAlmostEqual(r['independent_domestic']+r['independent_export'],r['independent_branch_total'])
            self.assertAlmostEqual(r['total_conditioned']-r['independent_branch_total'],r['crosscheck_gap'])
        self.assertTrue(any(abs(r['crosscheck_gap'])>1 for r in rows))

if __name__=='__main__':unittest.main()
