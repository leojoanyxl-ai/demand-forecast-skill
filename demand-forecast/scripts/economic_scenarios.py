"""Forward economic scenario prototype; declared planning parameters are not causal estimates."""
import argparse
import copy
import csv
import html
import json
import math
from pathlib import Path
import sys
from datetime import datetime,timezone,timedelta
import webbrowser

HERE=Path(__file__).resolve().parent
CHANNELS=[('income','实际购买力'),('financing','融资可得性'),('total_cost','汽车总体实际成本'),
          ('relative_cost','新能源相对购置使用成本'),('infrastructure','补能便利偏离参照'),
          ('technology','新增非价格技术条件'),('foreign_demand','海外需求'),
          ('export_price','出口到岸相对价格'),('export_rebate','出口退税价格传递'),
          ('access','非价格市场准入'),('timing','跨期购买转移')]


def cumulative(rates,h):
    value=1.0
    for rate in rates[:h]:
        if not math.isfinite(rate) or rate<=-1:raise ValueError('增长率必须有限且大于-100%。')
        value*=1+rate
    return value


def logistic(z):
    return 1/(1+math.exp(-z)) if z>=0 else math.exp(z)/(1+math.exp(z))


def logit(p):
    if not 0<p<1:raise ValueError('份额必须在0与1之间。')
    return math.log(p/(1-p))


def anchors(config):
    a=config['observed'];fy=a['2025_full'];old=a['2025_ytd'];new=a['2026_ytd']
    m0=(fy['auto']-fy['auto_export'])*(new['auto']-new['auto_export'])/(old['auto']-old['auto_export'])
    d0=(fy['nev']-fy['nev_export'])*(new['nev']-new['nev_export'])/(old['nev']-old['nev_export'])
    x0=fy['nev_export']*new['nev_export']/old['nev_export']
    points=[]
    for row in config['domestic_share_reference_history']:
        p=(row['nev']-row['nev_export'])/(row['auto']-row['auto_export'])
        points.append((row['year'],logit(p)))
    xm=sum(p[0] for p in points)/len(points);ym=sum(p[1] for p in points)/len(points)
    b=sum((x-xm)*(y-ym) for x,y in points)/sum((x-xm)**2 for x,y in points)
    return dict(domestic_auto=m0,domestic_nev=d0,nev_export=x0,share=d0/m0,
                share_reference_logit_slope=b,nature='2026全年桥接估算；沿用2025年年内分布；非全年实际')


def vehicle_cost(config,vehicle,price_factor,relief,deflator):
    a=config['cost_example'];price=a[vehicle+'_price_real']*price_factor
    nominal_price=price*deflator
    full_tax=nominal_price/(1+a['vat_rate'])*a['purchase_tax_rate']
    deduction=min(full_tax*relief,a['nev_relief_cap_nominal']) if vehicle=='nev' else 0
    tax_real=(full_tax-deduction)/deflator
    pv=sum(a[vehicle+'_annual_use_real']/(1+a['real_discount_rate'])**t for t in range(1,a['holding_years']+1))
    residual=a[vehicle+'_residual_real']/(1+a['real_discount_rate'])**a['holding_years']
    total=price+tax_real+pv-residual
    if total<=0:raise ValueError('广义成本非正，检查成本输入。')
    return total,tax_real


def evaluate(config,scenario,h,enabled=None):
    enabled=set(k for k,n in CHANNELS) if enabled is None else set(enabled)
    a=anchors(config);p=config['parameters'];ref=config['reference_path'];i=h-1
    parameter=lambda name:p[name]['value']
    income=cumulative(scenario['real_income_growth'],h)
    deflator=cumulative(scenario['inflation_growth'],h)
    nev_cost,tax=vehicle_cost(config,'nev',cumulative(scenario['nev_real_price_growth'],h),scenario['nev_tax_relief'][i],deflator)
    ice_cost,_=vehicle_cost(config,'ice',cumulative(scenario['ice_real_price_growth'],h),0,deflator)
    ref_nev,_=vehicle_cost(config,'nev',cumulative(ref['nev_real_price_growth'],h),ref['nev_tax_relief'][i],deflator)
    ref_ice,_=vehicle_cost(config,'ice',cumulative(ref['ice_real_price_growth'],h),0,deflator)
    anchor_nev,_=vehicle_cost(config,'nev',1,.5,1);anchor_ice,_=vehicle_cost(config,'ice',1,0,1)
    # Aggregate market costs and substitution odds have different coefficients.
    cost_index=(nev_cost/anchor_nev)**a['share']*(ice_cost/anchor_ice)**(1-a['share'])
    m=a['domestic_auto']
    # Optional empirical reference: historical demand growth already mixes past income/cost effects.
    # Apply only deviations from its declared future reference to avoid adding these effects twice.
    calibration=config.get('calibration',{})
    if calibration:
        m*=cumulative(calibration['domestic_reference_growth'],h)
        income_reference=cumulative(calibration['income_reference_growth'],h)
        ref_cost_index=(ref_nev/anchor_nev)**a['share']*(ref_ice/anchor_ice)**(1-a['share'])
        cost_index/=ref_cost_index
    else:income_reference=1
    if 'income' in enabled:m*=(income/income_reference)**parameter('income_elasticity')
    if 'financing' in enabled:m*=scenario['financing_quantity_factor'][i]
    if 'total_cost' in enabled:m*=cost_index**parameter('total_auto_cost_elasticity')
    z=logit(a['share'])+a['share_reference_logit_slope']*h
    relative_advantage=(ice_cost/nev_cost)/(ref_ice/ref_nev)
    if 'relative_cost' in enabled:z+=parameter('relative_cost_odds_coefficient')*math.log(relative_advantage)
    infra=cumulative(scenario['infrastructure_growth'],h)/cumulative(ref['infrastructure_growth'],h)
    if 'infrastructure' in enabled:z+=parameter('infrastructure_odds_coefficient')*math.log(infra)
    if 'technology' in enabled:z+=scenario['extra_technology_logodds'][i]
    structural_share=logistic(z);d=m*structural_share
    timing=scenario['pure_timing_transfer_10k'][i] if 'timing' in enabled else 0
    m+=timing;d+=timing
    if not 0<d<m:raise ValueError('跨期调整后国内销量或份额越界，不能事后截断。')
    foreign=cumulative(scenario['foreign_demand_growth'],h)
    quote=cumulative(scenario['export_quote_real_growth_before_rebate'],h)
    fx=cumulative(scenario['fx_foreign_per_rmb_growth'],h)
    competitor=cumulative(scenario['foreign_competitor_price_growth'],h)
    raw_price=quote*fx/competitor
    policy=config['export_rebate_policy'];coverage=scenario['rebate_eligible_fraction']
    weight=policy['affected_export_weight_2027'] if h==1 else 1
    rebate=policy['old_rate']-(policy['old_rate']-policy['new_rate'])*weight
    e=config['export_cost_example']
    lost_credit=e['eligible_tax_base_real']*(policy['old_rate']-rebate)
    full_period_lost_credit=e['eligible_tax_base_real']*(policy['old_rate']-policy['new_rate'])
    # Add a fixed tax-credit loss to the future quote, then convert once to relative foreign price.
    active_quote=quote if 'export_price' in enabled else 1
    future_quote=e['landed_price_real_before_change']*active_quote
    tax_price_factor=1+coverage*scenario['export_price_pass_through']*lost_credit/future_quote
    affected_price_factor=1+scenario['export_price_pass_through']*full_period_lost_credit/future_quote
    rebate_volume_factor=1-coverage*weight+coverage*weight*affected_price_factor**parameter('export_price_elasticity')
    x=a['nev_export']
    if 'foreign_demand' in enabled:x*=foreign**parameter('foreign_demand_elasticity')
    if 'export_price' in enabled:x*=raw_price**parameter('export_price_elasticity')
    if 'export_rebate' in enabled:x*=rebate_volume_factor
    if 'access' in enabled:x*=scenario['nonprice_export_access_factor'][i]
    return dict(year=2026+h,scenario=scenario['name'],domestic_auto=m,domestic_share=d/m,domestic_nev=d,
                nev_export=x,total_nev=d+x,real_income_index=income,overall_auto_cost_index=cost_index,
                nev_cost_real=nev_cost,ice_cost_real=ice_cost,nev_purchase_tax_real=tax,
                relative_cost_advantage_vs_reference=relative_advantage,infrastructure_vs_reference=infra,
                foreign_demand_index=foreign,export_price_before_rebate_index=raw_price,
                export_quote_before_policy_real=e['landed_price_real_before_change']*quote,
                fx_foreign_per_rmb_index=fx,foreign_competitor_price_index=competitor,
                annual_rebate_rate=rebate,eligible_fraction=coverage,price_pass_through=scenario['export_price_pass_through'],
                rebate_lost_credit_per_eligible_unit_real=lost_credit,
                average_rebate_price_factor=tax_price_factor,
                rebate_volume_factor=rebate_volume_factor,
                policy_cost_retained_per_average_unit_real=coverage*(1-scenario['export_price_pass_through'])*lost_credit,
                nature='经济驱动条件演示；价格、未来路径及行为系数含规划假设；非实证因果预测')


def validate(config):
    if config.get('calibration'):
        for key in ('domestic_reference_growth','income_reference_growth'):
            values=config['calibration'].get(key,[])
            if len(values)!=2 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<=-1 for v in values):
                raise ValueError('校准参照必须含两年有限且大于-100%的增长率：'+key)
    for name,p in config['parameters'].items():
        if not isinstance(p.get('value'),(int,float)) or not math.isfinite(p['value']) or not p.get('evidence'):
            raise ValueError('系数须有有限数值和证据状态：'+name)
    if not 0<=config['export_rebate_policy']['affected_export_weight_2027']<=1:raise ValueError('出口月份权重越界。')
    for s in config['scenarios']:
        paths=['real_income_growth','inflation_growth','nev_real_price_growth','ice_real_price_growth',
               'infrastructure_growth','foreign_demand_growth','export_quote_real_growth_before_rebate',
               'fx_foreign_per_rmb_growth','foreign_competitor_price_growth',
               'nev_tax_relief','financing_quantity_factor','nonprice_export_access_factor',
               'extra_technology_logodds','pure_timing_transfer_10k']
        for key in paths:
            if len(s[key])!=2 or any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in s[key]):
                raise ValueError(key+'须有2027与2028两个有限数值。')
        if any(not 0<=v<=1 for v in s['nev_tax_relief']):raise ValueError('购置税减免比例越界。')
        if s['nev_tax_relief'][0]!=.5:raise ValueError('2027实际政策路线必须保留已公布的减半安排；政策反事实须另设模式。')
        for k in ['rebate_eligible_fraction','export_price_pass_through']:
            if not 0<=s[k]<=1:raise ValueError(k+'需在0与1之间。')
        if abs(sum(s['pure_timing_transfer_10k']))>1e-8:raise ValueError('纯跨期购买转移在完整两年窗口内须净额为0。')
        for k in ['financing_quantity_factor','nonprice_export_access_factor']:
            if any(not math.isfinite(v) or v<=0 for v in s[k]):raise ValueError(k+'必须为正。')


def csv_output(path,rows):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def run(config,out):
    validate(config);out.mkdir(parents=True,exist_ok=True)
    rows=[evaluate(config,s,h) for s in config['scenarios'] for h in (1,2)]
    contributions=[]
    for s in config['scenarios']:
        for h in (1,2):
            active=set();previous=evaluate(config,s,h,active)['total_nev'];start=previous
            for channel,label in CHANNELS:
                active.add(channel);current=evaluate(config,s,h,active)['total_nev']
                contributions.append(dict(scenario=s['name'],year=2026+h,channel=channel,label=label,
                                          incremental_10k=current-previous,cumulative_total=current,
                                          reference_total=start,interpretation='固定顺序条件分解，含交互；不是唯一因果贡献'))
                previous=current
    base=next(s for s in config['scenarios'] if s['name']=='基准')
    variants=[]
    for label,edit in [
        ('实际收入年增速提高2个百分点',lambda s:s.update(real_income_growth=[v+.02 for v in s['real_income_growth']])),
        ('新能源实际车价每年再降2个百分点',lambda s:s.update(nev_real_price_growth=[v-.02 for v in s['nev_real_price_growth']])),
        ('假设2028不续购置税优惠',lambda s:s.update(nev_tax_relief=[.5,0])),
        ('出口退税变化全部由厂商吸收',lambda s:s.update(export_price_pass_through=0)),
        ('出口非价格准入收紧10%',lambda s:s.update(nonprice_export_access_factor=[.9,.9])),
        ('补能便利指标年增仅5%',lambda s:s.update(infrastructure_growth=[.05,.05]))]:
        changed=copy.deepcopy(base);edit(changed)
        for h in (1,2):
            r=evaluate(config,changed,h);original=evaluate(config,base,h)
            variants.append(dict(experiment=label,year=2026+h,domestic_nev=r['domestic_nev'],
                                 nev_export=r['nev_export'],total_nev=r['total_nev'],
                                 difference_from_base=r['total_nev']-original['total_nev']))
    csv_output(out/'经济情景结果.csv',rows);csv_output(out/'固定顺序贡献分解.csv',contributions);csv_output(out/'单因素敏感性.csv',variants)
    (out/'输入与锚点.json').write_text(json.dumps(dict(config=config,anchor=anchors(config)),ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'本次情景输入.json').write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
    candidates=[HERE/'已核验驱动事实与缺口.md',HERE.parent/'assets'/'nev-verified-facts.md']
    source=next((p for p in candidates if p.exists()),None)
    (out/'已核验驱动事实.md').write_text(source.read_text(encoding='utf-8') if source else '本次没有随附事实核查文件，请按输入来源重新核实。',encoding='utf-8')
    from render_economic_report import render
    (out/'经济机制与经营判断.html').write_text(render(config,anchors(config),rows,contributions,variants),encoding='utf-8')
    return rows,contributions,variants


def main():
    default_config=HERE/'经济情景输入.json'
    if not default_config.exists():default_config=HERE.parent/'assets'/'nev-economic-scenario.example.json'
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',type=Path,default=default_config);parser.add_argument('--output-dir',type=Path);parser.add_argument('--open',action='store_true')
    args=parser.parse_args();config=json.loads(args.config.read_text(encoding='utf-8-sig'))
    if any('value' not in p for p in config.get('parameters',{}).values()):
        parser.error('此文件是模型结构。请运行run_full.py；重放已有结果时用--config指定本轮校准输入.json。')
    out=args.output_dir or HERE/'运行记录'/('run_'+datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d_%H%M%S_%f'))
    rows,_,_=run(config,out)
    for r in rows:print(r['year'],r['scenario'],round(r['domestic_nev'],2),round(r['nev_export'],2),round(r['total_nev'],2))
    print('结果：'+str(out/'经济机制与经营判断.html'))
    if args.open:webbrowser.open((out/'经济机制与经营判断.html').resolve().as_uri())


if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    main()
