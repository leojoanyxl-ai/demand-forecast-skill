"""Behavioral and accounting checks for the portable ABS adapter."""
import copy
import csv
from pathlib import Path
import tempfile
import unittest

import abs_forecast as app


class AbsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = app.load(app.ROOT/'assets'/'abs-settings.json')
        cls.meta = app.load(app.ROOT/'assets'/'abs-source.json')
        cls.rows = app.read(app.ROOT/'assets'/'abs-monthly.csv', cls.settings, cls.meta)

    def test_source_count_and_identities(self):
        self.assertEqual(len(self.rows), 81)
        for row in self.rows:
            self.assertAlmostEqual(row['volume'], row['projects']*row['average_size'])

    def changed_input(self, edit):
        with (app.ROOT/'assets'/'abs-monthly.csv').open(encoding='utf-8-sig', newline='') as f:
            rows = list(csv.DictReader(f))
        edit(rows)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'input.csv'
            app.write_csv(path, rows)
            return app.read(path, self.settings, self.meta)

    def test_missing_month_rejected(self):
        with self.assertRaises(ValueError): self.changed_input(lambda rows: rows.pop(12))

    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError): self.changed_input(lambda rows: rows.append(rows[-1]))

    def test_future_observation_rejected(self):
        with self.assertRaises(ValueError): self.changed_input(lambda rows: rows[-1].update(period='2027-01'))

    def test_wrong_units_rejected(self):
        meta = copy.deepcopy(self.meta); meta['columns']['new_volume_100m_cny']['unit'] = '元'
        with self.assertRaises(ValueError): app.read(app.ROOT/'assets'/'abs-monthly.csv', self.settings, meta)

    def test_forecasts_independent_of_auxiliary_stock(self):
        changed = copy.deepcopy(self.rows)
        for row in changed: row['szse_market_value_cny'] *= 100
        for model in app.MODELS:
            self.assertEqual(app.predict(self.rows, 27, model), app.predict(changed, 27, model))

    def test_selection_has_no_outer_future_data(self):
        changed = copy.deepcopy(self.rows)
        for row in changed[60:]: row['volume'] *= 20
        self.assertEqual(app.select(self.rows[:60], self.settings), app.select(changed[:60], self.settings))

    def test_annual_equivalence_not_false_ensemble_evidence(self):
        totals = [sum(r['volume'] for r in app.predict(self.rows, 12, method)) for method in ('seasonal','mean12','count_size')]
        for value in totals: self.assertAlmostEqual(value, totals[0])

    def test_expected_calendar_and_pressure_compounding(self):
        monthly, annual = app.scenarios(self.rows, self.settings, 'seasonal')
        self.assertEqual(len(monthly), 81)
        self.assertEqual(len(annual), 6)
        for row in annual:
            self.assertEqual(row['months'], 12)
            self.assertEqual((row['lead_start'],row['lead_end']), (4,15) if row['year']==2027 else (16,27))
            self.assertAlmostEqual(row['volume'], row['projects']*row['average_size'])
        base = next(r['volume'] for r in annual if r['scenario']=='基准' and r['year']==2028)
        bad = next(r['volume'] for r in annual if r['scenario']=='悲观' and r['year']==2028)
        self.assertAlmostEqual(bad/base, .9*.92*.95*.95)

    def test_missing_private_inputs_and_demo_units(self):
        _, annual = app.scenarios(self.rows, self.settings, 'seasonal')
        blank = app.company_bridge(annual, app.load(app.ROOT/'assets'/'abs-company.json'))
        self.assertTrue(all(r['status']=='needs_input' for r in blank))
        demo = app.company_bridge(annual, app.load(app.ROOT/'assets'/'abs-company.example.json'))
        self.assertAlmostEqual(demo[0]['fee_revenue_10k_cny'], annual[0]['volume']*.02*.002*10000)
        self.assertGreaterEqual(demo[0]['hours_gap'],0)

    def test_invalid_share_not_silently_used(self):
        company = app.load(app.ROOT/'assets'/'abs-company.example.json'); company['project_share']=2
        with self.assertRaises(ValueError): app.company_bridge([], company)

    def test_aligned_backtest_windows_and_absolute_monthly_errors(self):
        detail, summary = app.backtest(self.rows, self.settings)
        self.assertEqual(len(detail), 1220)
        for item in summary:
            self.assertGreaterEqual(item['monthly_wape']+1e-12, item['wape'])
            if item['lead_start']==4: self.assertEqual(item['origins'],19)
            if item['lead_start']==16: self.assertEqual(item['origins'],7)
        for item in detail:
            self.assertLess(item['origin_period'], item['start'])


if __name__ == '__main__':
    unittest.main()
