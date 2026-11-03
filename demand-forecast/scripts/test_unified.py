"""Behavior checks for the unified data/parameter/report workflow (stdlib except no XLSX needed)."""
import copy
import csv
import math
from pathlib import Path
import tempfile
import unittest

import run_full as app
import monthly_demand as monthly
import parameter_mapping as mapping
import economic_scenarios as econ

ASSETS=app.ROOT/'assets'


class UnifiedTests(unittest.TestCase):
    def setUp(self):
        self.data=app.load(ASSETS/'nev-evidence.json');self.template=app.load(ASSETS/'nev-economic-scenario.example.json')
        self.registry=app.load(ASSETS/'economic-parameters.json');self.config,self.fit=app.prepare(self.data,self.template,registry=self.registry)
        self.rows=monthly.read(ASSETS/'nev-monthly.csv',self.data['as_of'])

    def altered_monthly(self,edit):
        with tempfile.TemporaryDirectory() as d:
            with (ASSETS/'nev-monthly.csv').open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
            edit(rows)
            p=Path(d)/'input.csv'
            with p.open('w',encoding='utf-8',newline='') as f:
                w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
            return monthly.read(p,self.data['as_of'])

    def test_duplicate_period_rejected(self):
        with self.assertRaises(ValueError):self.altered_monthly(lambda rows:rows.append(rows[0].copy()))

    def test_missing_month_rejected(self):
        with self.assertRaises(ValueError):self.altered_monthly(lambda rows:rows.pop(2))

    def test_future_release_rejected(self):
        with self.assertRaises(ValueError):self.altered_monthly(lambda rows:rows[-1].update(published='2027-01-01'))

    def test_unit_mismatch_not_silently_accepted(self):
        with self.assertRaises(ValueError):self.altered_monthly(lambda rows:rows[0].update(quantity_unit='辆'))

    def test_zero_not_missing(self):
        rows=self.altered_monthly(lambda rows:rows[0].update(nev='0',nev_export='0'))
        self.assertEqual(rows[0]['domestic_nev'],0)

    def test_negative_quantity_rejected(self):
        with self.assertRaises(ValueError):self.altered_monthly(lambda rows:rows[0].update(nev='-1'))

    def test_derived_value_requires_formula(self):
        with self.assertRaises(ValueError):self.altered_monthly(lambda rows:rows[0].update(status='derived',derivation=''))

    def test_monthly_accounts_reconcile(self):
        for r in self.rows:self.assertAlmostEqual(r['domestic_nev']+r['nev_export'],r['total_nev'])

    def test_future_actual_cannot_change_backtest_forecast(self):
        before,_=monthly.backtest(self.rows)
        changed=copy.deepcopy(self.rows);changed[-1]['total_nev']*=1.1;changed[-1]['domestic_nev']+=changed[-1]['total_nev']*.1
        after,_=monthly.backtest(changed)
        self.assertEqual([r['prediction'] for r in before],[r['prediction'] for r in after])

    def test_late_reconstructed_origin_skipped(self):
        forecasts,skips=monthly.backtest(self.rows)
        self.assertFalse(any(r['origin']=='2024-07' for r in forecasts))
        self.assertTrue(any(r['origin']=='2024-07' for r in skips))

    def test_methods_compared_on_same_target_sets(self):
        forecasts,_=monthly.backtest(self.rows)
        sets={name:{(r['origin'],r['target'],r['market'],r['h']) for r in forecasts if r['method']==name} for name in ('朴素不变','季节朴素')}
        self.assertEqual(sets['朴素不变'],sets['季节朴素'])

    def test_cancellation_cannot_look_like_small_branch_errors(self):
        rows=[dict(origin=2023,target=2024,method='sample',h=1,market=k,error=v,actual=a) for k,v,a in [('国内',10,60),('出口',-10,40),('总量',0,100)]]
        detail,summary=monthly.cancellation(rows)
        self.assertEqual(summary[0]['total_wape'],0)
        self.assertEqual(summary[0]['branch_absolute_error_over_total'],.2)
        self.assertEqual(summary[0]['cancellation_fraction'],1)

    def test_invalid_error_account_rejected(self):
        rows=[dict(origin=2023,target=2024,method='x',h=1,market=k,error=v,actual=100) for k,v in [('国内',10),('出口',-10),('总量',3)]]
        with self.assertRaises(ValueError):monthly.cancellation(rows)

    def test_annual_mismatch_is_preserved(self):
        original=copy.deepcopy(self.rows);audit=monthly.reconcile(self.rows,self.data)
        self.assertEqual(self.rows,original)
        self.assertTrue(any(r['status'].startswith('差异超舍入') for r in audit))

    def local_demand(self,log_nev_price=0,log_ice_price=0,log_infra=0):
        c=self.config;a=econ.anchors(c);p=a['share'];params=c['parameters']
        n=econ.vehicle_cost(c,'nev',math.exp(log_nev_price),.5,1)[0]
        ice=econ.vehicle_cost(c,'ice',math.exp(log_ice_price),0,1)[0]
        n0=econ.vehicle_cost(c,'nev',1,.5,1)[0];i0=econ.vehicle_cost(c,'ice',1,0,1)[0]
        market=a['domestic_auto']*((n/n0)**p*(ice/i0)**(1-p))**params['total_auto_cost_elasticity']['value']
        share=econ.logistic(econ.logit(p)+params['relative_cost_odds_coefficient']['value']*math.log((ice/n)/(i0/n0))+params['infrastructure_odds_coefficient']['value']*log_infra)
        return market,market*share

    def test_infrastructure_conversion_matches_sales_elasticity(self):
        d=1e-5
        actual=math.log(self.local_demand(log_infra=d)[1]/self.local_demand(log_infra=-d)[1])/(2*d)
        self.assertAlmostEqual(actual,self.registry['parameters']['infrastructure_sales_elasticity']['central'],places=6)

    def test_nev_purchase_elasticity_includes_tco_and_total_market(self):
        d=1e-5
        actual=math.log(self.local_demand(log_nev_price=d)[1]/self.local_demand(log_nev_price=-d)[1])/(2*d)
        self.assertAlmostEqual(actual,self.registry['parameters']['nev_purchase_price_elasticity']['central'],places=6)

    def test_market_purchase_elasticity_converts_to_tco(self):
        d=1e-5
        actual=math.log(self.local_demand(d,d)[0]/self.local_demand(-d,-d)[0])/(2*d)
        self.assertAlmostEqual(actual,self.registry['parameters']['market_purchase_price_elasticity']['central'],places=6)

    def test_changing_costs_recomputes_mapping(self):
        old=self.config['parameters']['relative_cost_odds_coefficient']['value']
        c=copy.deepcopy(self.config);c['cost_example']['nev_annual_use_real']=12000
        mapping.apply(c,self.registry)
        self.assertNotEqual(old,c['parameters']['relative_cost_odds_coefficient']['value'])

    def test_grid_includes_central_and_declared_edges(self):
        grid=list(mapping.grid_points(self.registry))
        for key,p in self.registry['parameters'].items():
            actual={r[key] for r in grid}
            for value in [p['central']]+p['range']:self.assertIn(value,actual)
        self.assertTrue(any(r['export_price_elasticity']==-5 for r in grid))

    def test_invalid_parameter_range_rejected(self):
        reg=copy.deepcopy(self.registry);reg['parameters']['export_price_elasticity']['central']=-10
        with self.assertRaises(ValueError):mapping.apply(self.config,reg)

    def test_model_coefficient_override_not_mistaken_for_target(self):
        with self.assertRaises(ValueError):app.prepare(self.data,self.template,{'parameter_overrides':{'infrastructure_odds_coefficient':{'value':.3}}})

    def test_override_changes_grid_and_mapping(self):
        c,_=app.prepare(self.data,self.template,{'economic_parameters':{'infrastructure_sales_elasticity':{'central':.4,'interpretation':'用户压力目标'}}})
        self.assertIn(.4,{r['infrastructure_sales_elasticity'] for r in mapping.grid_points(c['parameter_registry'])})

    def test_missing_company_inputs_do_not_become_zero(self):
        base=next(s for s in self.config['scenarios'] if s['name']=='基准')
        results=app.company_rows([econ.evaluate(self.config,base,1)],None)
        self.assertEqual(results[0]['status'],'needs_input');self.assertIsNone(results[0]['capacity_gap'])

    def test_known_tax_schedule_preserved(self):
        c=copy.deepcopy(self.config);c['scenarios'][0]['nev_tax_relief'][0]=0
        with self.assertRaises(ValueError):econ.validate(c)

    def test_full_pipeline_and_input_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'run';state=app.run(self.data,self.template,out)
            self.assertEqual(state['monthly_rows'],len(self.rows))
            self.assertEqual(state['grid_rows'],len(list(mapping.grid_points(self.registry)))*state['forecast_rows'])
            self.assertGreater(state['monthly_backtest_rows'],state['backtest_rows'])
            self.assertEqual((out/'月度原始输入.csv').read_bytes(),(ASSETS/'nev-monthly.csv').read_bytes())
            self.assertTrue(state['parameters_not_locally_identified'])
            with self.assertRaises(ValueError):app.run(self.data,self.template,out)


if __name__=='__main__':unittest.main(verbosity=2)
