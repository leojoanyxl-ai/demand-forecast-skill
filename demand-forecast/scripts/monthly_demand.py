"""Monthly CAAM-account target validation, baselines and branch-error diagnostics."""
import csv
import math
from datetime import date
from pathlib import Path
import statistics

KEYS=('auto','nev','auto_export','nev_export')
MARKETS=('domestic_auto','domestic_nev','nev_export','total_nev')


def period_index(period):
    y,m=map(int,period.split('-'))
    if not 1<=m<=12:raise ValueError('月份无效')
    return y*12+m-1


def read(path,as_of):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    if not rows:raise ValueError('月度目标数据为空。')
    seen=set();output=[]
    for r in rows:
        period_index(r['period'])
        if r['period'] in seen:raise ValueError('月度目标期间重复。')
        seen.add(r['period'])
        if r['quantity_unit']!='万辆':raise ValueError('月度输入必须明确换算为万辆。')
        if not r.get('published') or date.fromisoformat(r['published'])>date.fromisoformat(as_of):raise ValueError('缺发布日期或晚于截止日。')
        if r['status'] not in ('reported','derived'):raise ValueError('月度目标只能为有来源的报告值或可审计推算，预测不能混入历史。')
        if not r.get('source','').startswith('https://'):raise ValueError('缺月度来源。')
        if r['status']=='derived' and not r.get('derivation'):raise ValueError('推算月度缺计算依据。')
        for k in KEYS:
            try:r[k]=float(r[k])
            except (TypeError,ValueError):raise ValueError('缺月度目标值：'+k)
            if not math.isfinite(r[k]) or r[k]<0:raise ValueError('月度目标必须为非负有限数。')
        if not 0<=r['nev_export']<=r['auto_export']<=r['auto'] or not 0<=r['nev']-r['nev_export']<=r['auto']-r['auto_export']:
            raise ValueError('月度国内/出口或份额边界不成立。')
        r.update(domestic_auto=r['auto']-r['auto_export'],domestic_nev=r['nev']-r['nev_export'],total_nev=r['nev'])
        output.append(r)
    output.sort(key=lambda r:r['period'])
    indexes=[period_index(r['period']) for r in output]
    if indexes!=list(range(indexes[0],indexes[-1]+1)):raise ValueError('月度目标缺月：保留缺口并补源，不将相邻观察当作相邻月份。')
    return output


def backtest(rows,min_train=24,horizons=(1,3,12,24)):
    output=[];skips=[]
    for i in range(min_train-1,len(rows)-1):
        train=rows[:i+1]
        info=max(r['published'] for r in train)
        # A reconstructed month may only be available several months later; do not use that as a forecast origin.
        if period_index(info[:7])>period_index(rows[i]['period'])+1:
            skips.append(dict(origin=rows[i]['period'],reason='推算来源较晚，跳过该实时起点'));continue
        for h in horizons:
            if i+h>=len(rows):continue
            target=rows[i+h]
            if target['published']<=info or period_index(target['period'])<period_index(info[:7]):
                skips.append(dict(origin=rows[i]['period'],reason='目标已在信息期内，不当作未知未来'));continue
            for method in ('朴素不变','季节朴素'):
                reference=train[-1] if method=='朴素不变' else train[-12+(h-1)%12]
                for market in MARKETS:
                    pred=reference[market];actual=target[market]
                    output.append(dict(origin=rows[i]['period'],information_date=info,target=target['period'],h=h,
                        method=method,market=market,prediction=pred,actual=actual,error=pred-actual,
                        n_train=len(train),scope='月度目标基准；未验证经济驱动参数、政策或企业计划'))
    return output,skips


def metrics(rows):
    output=[]
    for method,market,h in sorted(set((r['method'],r['market'],r['h']) for r in rows)):
        g=[r for r in rows if (r['method'],r['market'],r['h'])==(method,market,h)]
        denom=sum(r['actual'] for r in g)
        output.append(dict(method=method,market=market,h=h,n=len(g),independent_actual_periods=len(set(r['target'] for r in g)),
            mae=statistics.mean(abs(r['error']) for r in g),wape=sum(abs(r['error']) for r in g)/denom if denom else None,
            bias=statistics.mean(r['error'] for r in g),status='探索性基准；发布日期已检查，未取得全部历史修订存档'))
    return output


def cancellation(rows):
    groups={}
    for r in rows:
        if r['market'] in ('国内','出口','总量','domestic_nev','nev_export','total_nev'):
            groups.setdefault((r['origin'],r['method'],r['h']),{})[r['market']]=r
    detail=[]
    for (origin,method,h),g in groups.items():
        if '国内' in g:names=('国内','出口','总量')
        else:names=('domestic_nev','nev_export','total_nev')
        if any(k not in g for k in names):continue
        d,x,q=[g[k] for k in names]
        if abs(d['error']+x['error']-q['error'])>1e-7:raise ValueError('分支误差不能回到总量，检查统计账户。')
        gross=abs(d['error'])+abs(x['error']);net=abs(q['error'])
        detail.append(dict(origin=origin,method=method,h=h,target=q['target'],domestic_error=d['error'],export_error=x['error'],
            total_error=q['error'],branch_absolute_error=gross,net_absolute_error=net,
            cancellation_fraction=(gross-net)/gross if gross else 0,total_actual=q['actual']))
    summary=[]
    for method,h in sorted(set((r['method'],r['h']) for r in detail)):
        g=[r for r in detail if (r['method'],r['h'])==(method,h)]
        denom=sum(r['total_actual'] for r in g);gross=sum(r['branch_absolute_error'] for r in g);net=sum(r['net_absolute_error'] for r in g)
        summary.append(dict(method=method,h=h,n=len(g),total_wape=net/denom if denom else None,
            branch_absolute_error_over_total=gross/denom if denom else None,
            cancellation_fraction=(gross-net)/gross if gross else 0,
            interpretation='抵消比例是诊断，不是预测置信度；分支绝对误差不因净额较小而消失'))
    return detail,summary


def reconcile(rows,data):
    output=[]
    references={str(r['year']):r for r in data['history']}
    references.update({k[:4]:v for k,v in data['recent'].items() if k.startswith('2026')})
    for year,ref in references.items():
        group=[r for r in rows if r['period'].startswith(year)]
        if not group:continue
        expected=9 if year=='2026' else 12
        for key in KEYS:
            value=sum(r[key] for r in group) if len(group)==expected else None
            difference=value-ref[key] if value is not None else None
            tolerance=.05*(expected+1)+1e-8
            output.append(dict(period=year+'-01至'+year+f'-{expected:02}',metric=key,months=len(group),monthly_sum=value,
                independent_reported=ref[key],difference=difference,rounding_tolerance=tolerance,
                status='覆盖不足' if value is None else '舍入范围内' if abs(difference)<=tolerance else '差异超舍入：保留来源版本待核',
                rule='不以插值、缩放或其他桶配平；年度校准沿用独立年度值，月度验证使用原始发布序列'))
    return output


def auxiliary(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    groups={}
    for r in rows:
        value=float(r['value'])
        if not math.isfinite(value) or value<0:raise ValueError('辅助数据异常。')
        groups.setdefault(r['metric'],[]).append(r)
    result=[]
    for metric,g in groups.items():
        periods=[r['period'] for r in g]
        if len(set(periods))!=len(periods):raise ValueError('辅助指标期间重复。')
        result.append(dict(metric=metric,n=len(g),first=min(periods),last=max(periods),role=g[0]['role'],
            modeling_status='供需校验，不作需求目标' if metric=='nev_production' else '仅用于前瞻补能条件参照，不声称已估计弹性',
            historical_driver_validation='逐期发布日期未提供，未做实时驱动回测'))
    return rows,result


def infrastructure_growth(rows,start_year=2021,end_year=2025):
    points={r['period']:float(r['value']) for r in rows if r['metric']=='public_chargers_stock'}
    recent=max(points);year,month=map(int,recent.split('-'));previous=f'{year-1}-{month:02}'
    reference=(points[f'{end_year}-12']/points[f'{start_year}-12'])**(1/(end_year-start_year))-1
    return dict(reference_growth=reference,recent_yoy_growth=points[recent]/points[previous]-1,
                reference_period=f'{start_year}-12至{end_year}-12',recent_period=recent,
                future_status='将最近同比延续为未来条件，不是未来观测或补能便利性实证估计')
