"""Reproducible evidence -> reference calibration -> conditional scenarios -> validation -> planning."""
import argparse
import copy
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
from datetime import datetime, timezone, timedelta
import webbrowser

import economic_scenarios as econ
import planning_bridge as planning
import monthly_demand as monthly
import parameter_mapping as mapping

ROOT = Path(__file__).resolve().parent.parent


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def validate_evidence(data):
    cutoff = data['as_of']
    if cutoff != '2026-11-03':
        raise ValueError('此案例固定2026-11-03信息边界；更新截止日需重新核验制度与数据，不能仅改日期。')
    hist = data['history']
    years = [r['year'] for r in hist]
    if len(hist) < 3 or years != sorted(set(years)) or any(b-a != 1 for a,b in zip(years,years[1:])):
        raise ValueError('至少需要三个连续且不重复的年度；少样本仍须披露验证限制。')
    for r in hist:
        for field in ('sales_published','income_published'):
            if r[field] > cutoff: raise ValueError('来源晚于信息截止日。')
        for k in ('auto','auto_export','nev','nev_export','real_income_growth'):
            if isinstance(r[k],bool) or not isinstance(r[k],(float,int)) or not math.isfinite(r[k]):
                raise ValueError('历史值必须为有限数值。')
        if not 0 < r['nev']-r['nev_export'] < r['auto']-r['auto_export'] or not 0 < r['nev_export'] < r['auto_export']:
            raise ValueError('历史分支或份额边界错误。')
        if r['real_income_growth'] <= -1: raise ValueError('收入增长率越界。')
        if not all(r[k].startswith('https://') for k in ('sales_source','income_source')):
            raise ValueError('缺原始来源。')
    if years[-1] != 2025: raise ValueError('2026全年不能冒充已观测历史。')
    for r in data['recent'].values():
        if r['published'] > cutoff: raise ValueError('近期来源晚于截止日。')
        if not 0 < r['nev']-r['nev_export'] < r['auto']-r['auto_export']: raise ValueError('近期分支越界。')
    if data['external_income_elasticity']['published'] > cutoff: raise ValueError('外部研究晚于截止日。')
    return hist


def calibrate(hist):
    """Descriptive trend estimates; no identification of price or policy effects."""
    points=[(r['year'],econ.logit((r['nev']-r['nev_export'])/(r['auto']-r['auto_export']))) for r in hist]
    xm=statistics.mean(x for x,y in points);ym=statistics.mean(y for x,y in points)
    slope=sum((x-xm)*(y-ym) for x,y in points)/sum((x-xm)**2 for x,y in points)
    growth=statistics.median(math.log((b['auto']-b['auto_export'])/(a['auto']-a['auto_export'])) for a,b in zip(hist,hist[1:]))
    return {'share_logit_slope':slope,'domestic_reference_growth':math.expm1(growth),
            'income_reference_growth':statistics.median(r['real_income_growth'] for r in hist[-3:]),
            'observations':len(hist),'growth_observations':len(hist)-1}


def prepare(data, template, settings=None, registry=None):
    registry=copy.deepcopy(registry or load(ROOT/'assets'/'economic-parameters.json'))
    hist=validate_evidence(data);fit=calibrate(hist);c=copy.deepcopy(template)
    c['domestic_share_reference_history']=[{k:r[k] for k in ('year','auto','auto_export','nev','nev_export')} for r in hist]
    c['observed']={'2025_full':{k:hist[-1][k] for k in ('auto','auto_export','nev','nev_export')}}
    c['observed'].update({k:{f:v[f] for f in ('auto','auto_export','nev','nev_export')} for k,v in data['recent'].items()})
    # References are transparent continuations, not official future projections.
    income=data['macro']['real_income_growth_ytd'];price=data['macro']['car_price_ytd_growth']
    c['calibration']={'domestic_reference_growth':[fit['domestic_reference_growth']]*2,
                      'income_reference_growth':[income]*2,
                      'meaning':'国内总市场历史增长中位数作为参照；收入与成本只调整偏离参照，非因果分解。'}
    infra=data.get('infrastructure',{})
    if 'reference_growth' not in infra:
        auxiliary_rows,_=monthly.auxiliary(ROOT/'assets'/'auxiliary-monthly.csv')
        derived=monthly.infrastructure_growth(auxiliary_rows,hist[0]['year'],hist[-1]['year'])
        ref_infra=derived['reference_growth'];fwd_infra=derived['recent_yoy_growth']
    else:ref_infra=infra['reference_growth'];fwd_infra=infra['recent_ytd_growth']
    c['reference_path'].update(nev_real_price_growth=[price]*2,ice_real_price_growth=[price]*2,infrastructure_growth=[ref_infra,ref_infra])
    c['parameters']['income_elasticity'].update(value=data['external_income_elasticity']['value'],
        evidence='外部研究参照，非本样本估计：'+data['external_income_elasticity']['source']+'；'+data['external_income_elasticity']['limit'])
    c['parameters']['income_elasticity']['kind']='外部研究参照'
    external=data.get('external_elasticities',{})
    for k,p in c['parameters'].items():
        if k=='income_elasticity':continue
        ref=external.get(k)
        if isinstance(ref,dict) and isinstance(ref.get('value'),(int,float)):
            p.update(value=ref['value'],kind='外部研究参照',
                     evidence=f"{ref.get('title','外部研究')}；取值{ref['value']}，范围{ref.get('range','')}；{ref.get('limit','')}")
        else:
            p.update(kind='压力参数',evidence='未取得适用的本样本识别结果；仅用于显式参数网格与条件测算，不是经验估计。')
    for s in c['scenarios']:
        s.update(inflation_growth=[data['macro']['cpi_september_yoy']]*2,
                 infrastructure_growth=[fwd_infra,fwd_infra],extra_technology_logodds=[0,0],
                 pure_timing_transfer_10k=[0,0],financing_quantity_factor=[1,1])
        if s['name']=='基准':s.update(real_income_growth=[income]*2,nev_real_price_growth=[price]*2,ice_real_price_growth=[price]*2,foreign_demand_growth=[0,0])
        if s['name']=='悲观':s.update(real_income_growth=[max(-.99,income-.02)]*2,nev_real_price_growth=[0,0],ice_real_price_growth=[price]*2,foreign_demand_growth=[-.05,-.05],infrastructure_growth=[0.10,0.10])
        if s['name']=='乐观':s.update(real_income_growth=[income+.02]*2,nev_real_price_growth=[price-.02]*2,ice_real_price_growth=[price]*2,foreign_demand_growth=[.10,.10],infrastructure_growth=[0.22,0.22])
        s['path_evidence']=f'默认收入{income:.2%}和共同车价参照{price:.2%}延续近期值，未来并非观测。收入±2pp、额外降价2pp、海外-5/0/+10%为压力条件；公共桩历史参照{ref_infra:.2%}，基准延续近期{fwd_infra:.2%}，其余路径见本次输入；非概率或官方预测。'
    c['reference_path']['meaning']=f'共同车价参照使用小汽车CPI数值的规划延续，不是分车型实际成交价观测。公共桩历史参照{ref_infra:.2%}、基准未来延续{fwd_infra:.2%}；不证明补能效应已识别。2028半征仅为条件参照。'
    c['model_status']='公开数据锚点＋描述性参照＋外部量级下原始弹性目标经导数转换＋条件网格；非本样本识别，非业务验收通过'
    c['source_notes']=[c['model_status'],data['vintage_limit'],data['macro']['price_limit'],
        f"国内总市场及份额趋势来自{hist[0]['year']}—{hist[-1]['year']}共{len(hist)}个年度，混合历史收入、技术与价格作用，不能解释为独立因果。",
        '出口基准不延续历史翻倍增长，采用2026桥接值作为无增量海外需求参照；海外路径和准入为压力条件。',
        '原型中的车型成本、持有期、残值、出口税基和政策覆盖仍属示例；实际利润与税额须用企业输入。',
        '融资、技术、抢购本轮没有另估数量效应；零增量表示未叠加，不证明真实影响为零。补能历史CAGR与近期同比由辅助CSV原值计算后进入条件偏离。']
    if settings:
        for name,overrides in settings.get('scenario_overrides',{}).items():
            scenario=next((s for s in c['scenarios'] if s['name']==name),None)
            if scenario is None or any(k not in scenario or k=='name' for k in overrides):raise ValueError('未知情景或路径字段。')
            scenario.update(copy.deepcopy(overrides))
        if settings.get('parameter_overrides'):
            raise ValueError('统一版请用economic_parameters覆盖原始弹性目标，不再直接覆盖模型logit系数。')
        for key,entry in settings.get('economic_parameters',{}).items():
            if key not in registry['parameters'] or not isinstance(entry,dict) or not entry.get('interpretation'):
                raise ValueError('弹性设置需已知名称、central和interpretation依据；超范围时同时调整range/grid。')
            registry['parameters'][key].update(entry)
        for section in ('cost_example','export_cost_example'):
            overrides=settings.get(section,{})
            if any(k not in c[section] for k in overrides):raise ValueError('未知成本输入字段。')
            c[section].update(copy.deepcopy(overrides))
        c['source_notes'].append('本轮设置覆盖：'+json.dumps(settings,ensure_ascii=False))
    mapping.apply(c,registry)
    c['source_notes'].append('原始弹性目标、转换后的模型系数与隐含弹性分开；参数表是中央值和网格唯一入口。')
    econ.validate(c)
    return c,fit


def backtest(data):
    hist=data['history'];rows=[]
    for n in range(2,len(hist)):
        train=hist[:n];last=train[-1];fit=calibrate(train)
        # Information time is January after the origin year, after actual annual releases.
        information_date=max(last['sales_published'],last['income_published'])
        if data['external_income_elasticity']['published']>information_date:continue
        m=last['auto']-last['auto_export'];p=(last['nev']-last['nev_export'])/m
        for h in (1,2):
            target=last['year']+h
            actual=next((r for r in hist if r['year']==target),None)
            if actual is None:continue
            # Future income is a training-only median, never realized target income.
            income_forecast=fit['income_reference_growth']
            neutral_reference=fit['income_reference_growth']
            pred_m=m*(1+fit['domestic_reference_growth'])**h*((1+income_forecast)/(1+neutral_reference))**(data['external_income_elasticity']['value']*h)
            pred_d=pred_m*econ.logistic(econ.logit(p)+fit['share_logit_slope']*h)
            estimates={'国内':pred_d,'出口':last['nev_export'],'总量':pred_d+last['nev_export']}
            actuals={'国内':actual['nev']-actual['nev_export'],'出口':actual['nev_export'],'总量':actual['nev']}
            naive={'国内':last['nev']-last['nev_export'],'出口':last['nev_export'],'总量':last['nev']}
            for method,values in (('需求参照链',estimates),('朴素不变',naive)):
                for market in values:
                    rows.append(dict(origin=last['year'],information_date=information_date,target=target,h=h,method=method,market=market,
                                     prediction=values[market],actual=actuals[market],error=values[market]-actuals[market],
                                     income_forecast=income_forecast,n_train=n,
                                     scope='只验证参考趋势与朴素出口，收入偏离为零；不验证价格弹性、2027新政策、2026桥接或企业计划'))
    return rows


def metrics(rows):
    output=[]
    for key in sorted(set((r['method'],r['market'],r['h']) for r in rows)):
        group=[r for r in rows if (r['method'],r['market'],r['h'])==key]
        output.append(dict(method=key[0],market=key[1],h=key[2],n=len(group),
                           independent_actual_years=len(set(r['target'] for r in group)),
                           mae=statistics.mean(abs(r['error']) for r in group),
                           wape=sum(abs(r['error']) for r in group)/sum(r['actual'] for r in group),
                           bias=statistics.mean(r['error'] for r in group),status='探索性；未设业务合格阈值'))
    return output


def grid(config):
    rows=[]
    registry=config['parameter_registry']
    for raw in mapping.grid_points(registry):
        c=copy.deepcopy(config)
        mapping.apply(c,registry,raw)
        for s in c['scenarios']:
            for h in (1,2):
                r=econ.evaluate(c,s,h)
                rows.append(dict(year=r['year'],scenario=r['scenario'],**raw,
                                 domestic_nev=r['domestic_nev'],nev_export=r['nev_export'],total_nev=r['total_nev'],
                                 nature='来自本次统一参数表的校准/压力目标，非概率分布或统计置信界'))
    return rows


def company_rows(forecasts,company_path):
    if company_path:
        with company_path.open(encoding='utf-8-sig',newline='') as f:inputs=list(csv.DictReader(f))
        ids=[(r.get('period'),r.get('scenario')) for r in inputs]
        if len(ids)!=len(set(ids)):raise ValueError('企业输入存在重复期间与情景。')
    else:inputs=[]
    results=[]
    for r in forecasts:
        inp=next((v for v in inputs if str(v.get('period'))==str(r['year']) and v.get('scenario')==r['scenario']),{})
        row=dict(inp,period=str(r['year']),scenario=r['scenario'],quantity_unit='万辆',
                 data_nature=inp.get('data_nature','企业实际参数未提供'),assumption_basis=inp.get('assumption_basis','行业结果为条件测算'),
                 domestic_demand=r['domestic_nev'],exports=r['nev_export'])
        if inp.get('quantity_unit') not in (None,'','万辆'):raise ValueError('企业数量须换算为万辆，不能静默改单位。')
        results.append(planning.calculate(row))
    return results


def write_csv(path,rows):
    if rows:econ.csv_output(path,rows)








def run(data,template,out,company_path=None,settings=None,monthly_path=None,auxiliary_path=None,registry=None):
    data=copy.deepcopy(data)
    monthly_path=monthly_path or ROOT/'assets'/'nev-monthly.csv'
    auxiliary_path=auxiliary_path or ROOT/'assets'/'auxiliary-monthly.csv'
    mrows=monthly.read(monthly_path,data['as_of'])
    aux,roles=monthly.auxiliary(auxiliary_path)
    infra=monthly.infrastructure_growth(aux,data['history'][0]['year'],data['history'][-1]['year'])
    data['infrastructure'].update(reference_growth=infra['reference_growth'],recent_ytd_growth=infra['recent_yoy_growth'],
        reference_evidence='从本次辅助数据原值计算：'+infra['reference_period'],recent_evidence='从本次辅助数据原值计算同比：'+infra['recent_period'])
    c,fit=prepare(data,template,settings,registry)
    if out.exists():raise ValueError('输出目录已存在，请使用新目录保留版本。')
    out.mkdir(parents=True)
    forecasts,_,_=econ.run(c,out/'经济机制细节')
    forecast_rows=[dict(r,nature='外部参照与压力参数下的条件测算，非正式预算') for r in forecasts]
    tests=backtest(data);checks=metrics(tests);gridrows=grid(c);companies=company_rows(forecasts,company_path)
    mtests,skips=monthly.backtest(mrows);mchecks=monthly.metrics(mtests)
    cancel_detail,cancel=monthly.cancellation(tests)
    mcancel_detail,mcancel=monthly.cancellation(mtests)
    reconciliation=monthly.reconcile(mrows,data)
    write_csv(out/'三情景结果.csv',forecast_rows);write_csv(out/'参数压力网格.csv',gridrows)
    write_csv(out/'逐条回测.csv',tests);write_csv(out/'回测汇总.csv',checks);write_csv(out/'企业条件核算.csv',companies)
    ledger=[dict(parameter=k,value=p['value'],kind=p['kind'],meaning=p['meaning'],evidence=p['evidence']) for k,p in c['parameters'].items()]
    ledger.extend([dict(parameter='份额趋势',value=fit['share_logit_slope'],kind='本样本描述性拟合',meaning='年度logit斜率',evidence=f"{data['history'][0]['year']}—{data['history'][-1]['year']}共{fit['observations']}年，非因果；窗口内重估"),
                   dict(parameter='国内总市场参照增长',value=fit['domestic_reference_growth'],kind='本样本描述性统计',meaning='年度log增长中位数还原',evidence=f"{fit['growth_observations']}个增长观察，非周期预测")])
    write_csv(out/'参数依据.csv',ledger)
    (out/'公开数据与来源.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'本轮校准输入.json').write_text(json.dumps(c,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'本次用户设置.json').write_text(json.dumps(settings or {},ensure_ascii=False,indent=2),encoding='utf-8')
    mapping_rows=mapping.ledger(c,forecast_rows)
    write_csv(out/'弹性转换与隐含弹性.csv',mapping_rows)
    write_csv(out/'月度需求序列.csv',mrows);write_csv(out/'月度逐条回测.csv',mtests);write_csv(out/'月度分支误差.csv',mchecks)
    write_csv(out/'月度跳过起点.csv',skips);write_csv(out/'年度分支抵消诊断.csv',cancel);write_csv(out/'年度分支误差明细.csv',cancel_detail)
    write_csv(out/'月度分支抵消诊断.csv',mcancel);write_csv(out/'月度分支误差明细.csv',mcancel_detail)
    write_csv(out/'年度与月度口径核对.csv',reconciliation);write_csv(out/'辅助变量用途.csv',roles)
    context=dict(monthly_rows=mrows,monthly_metrics=mchecks,cancellation=cancel,monthly_cancellation=mcancel,
                 reconciliation=reconciliation,auxiliary_roles=roles,mapping=mapping_rows,infra=infra)
    from unified_report import render as render_unified
    (out/'需求预测与经营预案.html').write_text(render_unified(data,c,fit,forecast_rows,checks,gridrows,companies,context),encoding='utf-8')
    (out/'统一参数表.json').write_text(json.dumps(c['parameter_registry'],ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'月度原始输入.csv').write_bytes(Path(monthly_path).read_bytes())
    (out/'辅助原始输入.csv').write_bytes(Path(auxiliary_path).read_bytes())
    if company_path:(out/'企业输入快照.csv').write_bytes(Path(company_path).read_bytes())
    status={'pipeline':'completed','forecast_validation':'年度参照链与月度目标基准已运行；完整经济情景尚未历史验证','business_acceptance':'计算可完成不代表真实业务通过；须核实企业参数性质和容忍度',
            'company_calculation_states':[r['status'] for r in companies], 'history_rows':len(data['history']),
            'forecast_rows':len(forecasts),'grid_rows':len(gridrows),'backtest_rows':len(tests),
            'fit':fit,'as_of':data['as_of'],'parameters_unfilled':[],
            'parameters_not_locally_identified':list(c['parameters']),
            'monthly_rows':len(mrows),'monthly_derived_rows':sum(r['status']=='derived' for r in mrows),
            'monthly_backtest_rows':len(mtests),'monthly_reconciliation_flags':sum(r['status']!='舍入范围内' for r in reconciliation),
            'auxiliary_observations':len(aux),'monthly_sha256':hashlib.sha256(Path(monthly_path).read_bytes()).hexdigest(),
            'parameter_registry_sha256':hashlib.sha256(json.dumps(c['parameter_registry'],sort_keys=True).encode()).hexdigest(),
            'code_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'scripts').glob('*.py'))},
            'input_sha256':hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest(),
            'template_sha256':hashlib.sha256(json.dumps(template,sort_keys=True).encode()).hexdigest(),
            'company_input_sha256':hashlib.sha256(company_path.read_bytes()).hexdigest() if company_path else None}
    (out/'运行状态.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
    return status


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,default=ROOT/'assets'/'nev-evidence.json')
    parser.add_argument('--config',type=Path,default=ROOT/'assets'/'nev-economic-scenario.example.json')
    parser.add_argument('--company',type=Path)
    parser.add_argument('--monthly',type=Path,default=ROOT/'assets'/'nev-monthly.csv')
    parser.add_argument('--auxiliary',type=Path,default=ROOT/'assets'/'auxiliary-monthly.csv')
    parser.add_argument('--parameters',type=Path,default=ROOT/'assets'/'economic-parameters.json')
    parser.add_argument('--settings',type=Path,default=ROOT/'assets'/'nev-settings.json')
    parser.add_argument('--output-dir',type=Path)
    parser.add_argument('--open',action='store_true')
    args=parser.parse_args()
    out=args.output_dir or ROOT/'运行记录'/datetime.now(timezone(timedelta(hours=8))).strftime('run_%Y%m%d_%H%M%S_%f')
    status=run(load(args.data),load(args.config),out,args.company,load(args.settings),args.monthly,args.auxiliary,load(args.parameters))
    print(json.dumps(status,ensure_ascii=False,indent=2));print('报告：'+str(out/'需求预测与经营预案.html'))
    if args.open:webbrowser.open((out/'需求预测与经营预案.html').resolve().as_uri())


if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    main()
