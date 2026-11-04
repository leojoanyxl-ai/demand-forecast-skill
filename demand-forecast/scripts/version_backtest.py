"""Frozen-version annual comparison, monthly adaptations, bridge tests, and branch diagnostics."""
import argparse
import csv
from datetime import datetime
import hashlib
import html
import json
import math
from pathlib import Path
import statistics

import monthly_demand as monthly
import run_full as reference
import economic_scenarios as econ

ROOT=Path(__file__).resolve().parents[1]
DOMESTIC=('seasonal','trend_half','trend_full')
EXPORT=('seasonal','trend_half','trend_full')

def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def csvwrite(p,rows):
    if not rows:return
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def slope(points):
    xm=statistics.mean(x for x,y in points);ym=statistics.mean(y for x,y in points)
    den=sum((x-xm)**2 for x,y in points)
    if not den:raise ValueError('趋势训练长度不足')
    return sum((x-xm)*(y-ym) for x,y in points)/den

def v1_total(history,anchor,h,exclude_anchor=True):
    train=[r for r in history if r['year']<anchor['year'] or not exclude_anchor]
    if len(train)<2:raise ValueError('原版趋势至少需要两年')
    b=slope([(r['year'],econ.logit(r['nev']/r['auto'])) for r in train])
    return anchor['auto']*econ.logistic(econ.logit(anchor['nev']/anchor['auto'])+b*h)

def v2_branches(history,anchor,h):
    fit=reference.calibrate(history)
    m=anchor['auto']-anchor['auto_export'];p=(anchor['nev']-anchor['nev_export'])/m
    d=m*(1+fit['domestic_reference_growth'])**h*econ.logistic(econ.logit(p)+fit['share_logit_slope']*h)
    # No future economic regressors are used. Income deviation equals zero exactly.
    return {'国内':d,'出口':anchor['nev_export'],'总量':d+anchor['nev_export']}

def actuals(row):return {'国内':row['nev']-row['nev_export'],'出口':row['nev_export'],'总量':row['nev']}

def annual_compare(original,data):
    legacy=[];paired=[]
    hist=original['history'];branches=data['history']
    for origin in range(2020,2025):
        anchor=next(r for r in hist if r['year']==origin)
        for h in (1,2):
            target=next((r for r in hist if r['year']==origin+h),None)
            if target is None:continue
            predictions={'V1原版总量':v1_total([r for r in hist if r['year']<=origin],anchor,h),
                         '上年总量不变':anchor['nev']}
            for name,pred in predictions.items():
                legacy.append(dict(origin=str(origin),target=str(origin+h),horizon=h,lead_start=1,method=name,market='总量',prediction=pred,actual=target['nev'],error=pred-target['nev'],monthly_abs_error=abs(pred-target['nev']),scope='原版年度公式；多起点；不含全年桥接误差'))
    for n in range(2,len(branches)):
        train=branches[:n];anchor=train[-1];origin=anchor['year']
        for h in (1,2):
            target=next((r for r in branches if r['year']==origin+h),None)
            if target is None:continue
            pool=[r for r in hist if r['year']<=origin]
            predictions={'V1原版总量':{'总量':v1_total(pool,anchor,h)},
                         'V1相同分支年份窗口总量':{'总量':v1_total(train,anchor,h,exclude_anchor=False)},
                         'V2年度参照链':v2_branches(train,anchor,h),
                         '上年分支不变':actuals(anchor)}
            for name,values in predictions.items():
                for market,pred in values.items():
                    a=actuals(target)[market]
                    paired.append(dict(origin=str(origin),target=str(origin+h),horizon=h,lead_start=1,method=name,market=market,prediction=pred,actual=a,error=pred-a,monthly_abs_error=abs(pred-a),scope='同数据池和起点，各方法原定窗口；另列同窗口控制；不验证经济因果参数'))
    return legacy,paired

def metrics(rows):
    output=[]
    for name,market,h,lead in sorted(set((r['method'],r['market'],r['horizon'],r['lead_start']) for r in rows)):
        group=[r for r in rows if (r['method'],r['market'],r['horizon'],r['lead_start'])==(name,market,h,lead)]
        den=sum(r['actual'] for r in group)
        output.append(dict(method=name,market=market,horizon=h,lead_start=lead,n=len(group),distinct_target_years=len(set(r['target'][:4] for r in group)),mae=statistics.mean(abs(r['error']) for r in group),wape=sum(abs(r['error']) for r in group)/den,monthly_wape=sum(r['monthly_abs_error'] for r in group)/den,bias=statistics.mean(r['error'] for r in group)))
    return output

def path(history,horizon,method,branch=None):
    """Monthly adaptations, explicitly separate from frozen annual algorithms."""
    if len(history)<12:raise ValueError('至少12个月')
    def share(r,domestic=False):return r['domestic_nev']/r['domestic_auto'] if domestic else r['nev']/r['auto']
    overall_b=slope([(i,econ.logit(share(r))) for i,r in enumerate(history)])
    domestic_b=slope([(i,econ.logit(share(r,True))) for i,r in enumerate(history)])
    def growth(key):
        if len(history)<24:return 0.0
        return math.log(sum(r[key] for r in history[-12:])/sum(r[key] for r in history[-24:-12]))
    g_m=growth('domestic_auto');g_x=growth('nev_export')
    rows=[]
    for step in range(1,horizon+1):
        ref_index=len(history)-12+(step-1)%12;ref=history[ref_index]
        delta=len(history)-1+step-ref_index
        period=monthly.period_index(history[-1]['period'])+step
        date=f'{period//12:04d}-{period%12+1:02d}'
        if method=='V1月度适配':
            rows.append(dict(period=date,总量=ref['auto']*econ.logistic(econ.logit(share(ref))+overall_b*delta)));continue
        if method=='V2月度适配':
            d=ref['domestic_auto']*math.exp(g_m*delta/12)*econ.logistic(econ.logit(share(ref,True))+domestic_b*delta)
            x=ref['nev_export']
        elif method in DOMESTIC:
            damp={'seasonal':0,'trend_half':.5,'trend_full':1}[method]
            if branch=='国内':
                d=ref['domestic_nev'] if method=='seasonal' else ref['domestic_auto']*math.exp(damp*g_m*delta/12)*econ.logistic(econ.logit(share(ref,True))+damp*domestic_b*delta)
                rows.append(dict(period=date,国内=d));continue
            if branch=='出口':
                rows.append(dict(period=date,出口=ref['nev_export']*math.exp(damp*g_x*delta/12)));continue
            raise ValueError('分支未提供')
        elif method=='分支季节朴素':d=ref['domestic_nev'];x=ref['nev_export']
        else:raise ValueError('未知方法')
        rows.append(dict(period=date,国内=d,出口=x,总量=d+x))
    return rows

def origin_valid(history):
    info=max(r['published'] for r in history)
    return monthly.period_index(info[:7])<=monthly.period_index(history[-1]['period'])+1

def select_branch(history,branch):
    # Six-month inner validation keeps at least seven folds with a 24-month outer train.
    scores=[]
    for method in DOMESTIC:
        errors=[];den=[]
        for n in range(12,len(history)-6+1):
            train=history[:n]
            if not origin_valid(train):continue
            info=max(r['published'] for r in train)
            if history[n]['published']<=info:continue
            forecast=path(train,6,method,branch)
            key='domestic_nev' if branch=='国内' else 'nev_export'
            a=sum(r[key] for r in history[n:n+6]);p=sum(r[branch] for r in forecast)
            errors.append(abs(p-a));den.append(a)
        if not errors:raise ValueError('内部选模样本不足')
        scores.append(dict(method=method,wape=sum(errors)/sum(den),n=len(errors)))
    selected=min(scores,key=lambda s:(round(s['wape'],12),DOMESTIC.index(s['method'])))['method']
    return selected,scores

def adaptive(history,horizon):
    d,ds=select_branch(history,'国内');x,xs=select_branch(history,'出口')
    dp=path(history,horizon,d,'国内');xp=path(history,horizon,x,'出口')
    return [dict(period=a['period'],国内=a['国内'],出口=b['出口'],总量=a['国内']+b['出口']) for a,b in zip(dp,xp)],dict(domestic=d,export=x,domestic_scores=ds,export_scores=xs)

def monthly_compare(rows,min_train=24):
    output=[];choices=[];skips=[]
    windows=[(1,0),(3,0),(12,0),(24,0),(12,3),(12,15)]
    for n in range(min_train,len(rows)):
        history=rows[:n]
        if not origin_valid(history):
            skips.append(dict(origin=history[-1]['period'],reason='来源发布时间过晚'));continue
        adaptive_path,selection=adaptive(history,27)
        choices.append(dict(origin=history[-1]['period'],**selection))
        for horizon,offset in windows:
            if n+horizon+offset>len(rows):continue
            targets=rows[n+offset:n+offset+horizon]
            info=max(r['published'] for r in history)
            if targets[0]['published']<=info:continue
            for method in ('V1月度适配','V2月度适配','V3分支独立选模候选','V3仅更新出口候选','分支季节朴素'):
                if method=='V3分支独立选模候选':forecast=adaptive_path[offset:offset+horizon]
                elif method=='V3仅更新出口候选':
                    domestic=path(history,offset+horizon,'V2月度适配')[offset:]
                    forecast=[dict(period=a['period'],国内=a['国内'],出口=b['出口'],总量=a['国内']+b['出口']) for a,b in zip(domestic,adaptive_path[offset:offset+horizon])]
                else:forecast=path(history,offset+horizon,method)[offset:]
                for market in forecast[0]:
                    if market=='period':continue
                    key={'国内':'domestic_nev','出口':'nev_export','总量':'nev'}[market]
                    a=sum(r[key] for r in targets);p=sum(r[market] for r in forecast)
                    output.append(dict(origin=history[-1]['period'],information_date=info,target=targets[-1]['period'],target_start=targets[0]['period'],horizon=horizon,lead_start=offset+1,method=method,market=market,prediction=p,actual=a,error=p-a,monthly_abs_error=sum(abs(f[market]-r[key]) for f,r in zip(forecast,targets)),scope='月度适配/候选比较，非原年度完整经济模型；当前版本回顾性研究'))
    return output,choices,skips

def cancellation(rows):
    groups={}
    for r in rows:groups.setdefault((r['method'],r['origin'],r['horizon'],r['lead_start'],r['target']),{})[r['market']]=r
    out=[]
    for key,g in groups.items():
        if not all(k in g for k in ('国内','出口','总量')):continue
        d,x,q=(g[k]['error'] for k in ('国内','出口','总量'))
        if not math.isclose(d+x,q,abs_tol=1e-7):raise ValueError('分支错误无法加回总量')
        gross=abs(d)+abs(x)
        out.append(dict(method=key[0],origin=key[1],horizon=key[2],lead_start=key[3],target=key[4],domestic_error=d,export_error=x,total_error=q,branch_abs_error=gross,cancellation_fraction=max(0,1-abs(q)/gross) if gross else 0))
    return out

def bridge_test(rows,data):
    output=[];history={r['year']:r for r in data['history']}
    for year in (2023,2024,2025):
        prev=history[year-1];actual=history[year]
        last=[r for r in rows if r['period'].startswith(str(year-1)) and int(r['period'][-2:])<=9]
        current=[r for r in rows if r['period'].startswith(str(year)) and int(r['period'][-2:])<=9]
        if len(last)!=9 or len(current)!=9:continue
        estimates={}
        for market,key in [('国内','domestic_nev'),('出口','nev_export')]:
            pred=actuals(prev)[market]*sum(r[key] for r in current)/sum(r[key] for r in last)
            estimates[market]=pred
        estimates['总量']=estimates['国内']+estimates['出口']
        for market,p in estimates.items():
            a=actuals(actual)[market]
            output.append(dict(origin=f'{year}-09',target=str(year),horizon=3,lead_start=1,method='三季度分支全年桥接',market=market,prediction=p,actual=a,error=p-a,monthly_abs_error=abs(p-a),scope='独立年度值与当月发布序列并用；年/月修订差异保留；2026不评分'))
    return output

def estimated_2026(rows,data):
    history=rows[:];adaptive_path,selected=adaptive(history,3);output=[]
    ytd=data['recent']['2026_ytd'];past={'国内':ytd['nev']-ytd['nev_export'],'出口':ytd['nev_export'],'总量':ytd['nev']}
    for method in ('分支季节朴素','V2月度适配','V3分支独立选模候选'):
        paths=adaptive_path if method.startswith('V3') else path(history,3,method)
        for r in paths:output.append(dict(method=method,period=r['period'],**{k:r[k] for k in ('国内','出口','总量')},nature='预测，不是实际，不参与回测评分'))
        output.append(dict(method=method,period='2026E全年',**{k:past[k]+sum(r[k] for r in paths) for k in past},nature='1—9月官方累计＋预测Q4，尚无全年实际；仅作规划'))
    return output,selected

def september_chain(original,rows,data):
    """Historical September -> estimated current FY -> next FY, not a full causal-policy backtest."""
    output=[];annual={r['year']:r for r in data['history']}
    for year in (2023,2024,2025):
        old=[r for r in rows if r['period'].startswith(str(year-1)) and int(r['period'][-2:])<=9]
        new=[r for r in rows if r['period'].startswith(str(year)) and int(r['period'][-2:])<=9]
        if len(old)!=9 or len(new)!=9:continue
        prev=annual[year-1]
        sums=lambda rs,k:sum(r[k] for r in rs)
        anchor1={'year':year,'auto':prev['auto']*sums(new,'auto')/sums(old,'auto'),'nev':prev['nev']*sums(new,'nev')/sums(old,'nev')}
        m=(prev['auto']-prev['auto_export'])*sums(new,'domestic_auto')/sums(old,'domestic_auto')
        d=(prev['nev']-prev['nev_export'])*sums(new,'domestic_nev')/sums(old,'domestic_nev')
        x=prev['nev_export']*sums(new,'nev_export')/sums(old,'nev_export')
        ae=prev['auto_export']*sums(new,'auto_export')/sums(old,'auto_export')
        anchor2=dict(year=year,auto=m+ae,auto_export=ae,nev=d+x,nev_export=x)
        hist=[r for r in data['history'] if r['year']<year]
        for h in (1,2):
            actual=annual.get(year+h)
            if actual is None:continue
            predictions={'V1三季度桥接后总量':{'总量':v1_total(original['history'][:year-2015],anchor1,h)},'V2三季度桥接后参照链':v2_branches(hist,anchor2,h)}
            for name,values in predictions.items():
                for market,p in values.items():
                    a=actuals(actual)[market]
                    output.append(dict(origin=f'{year}-09',target=str(year+h),horizon=h,lead_start=1,method=name,market=market,prediction=p,actual=a,error=p-a,monthly_abs_error=abs(p-a),scope='前三季→估计全年→后续年度参照；不含历史政策/价格因果模型；实际年份有限'))
    return output

def table(rows,keys):
    def fmt(x):return f'{x:,.3f}' if isinstance(x,float) else str(x)
    return '<div class="scroll"><table><tr>'+''.join('<th>'+html.escape(label)+'</th>' for k,label in keys)+'</tr>'+''.join('<tr>'+''.join('<td>'+html.escape(fmt(r.get(k,'')))+'</td>' for k,label in keys)+'</tr>' for r in rows)+'</table></div>'

def report(out,original,legacy,annual,mtests,bridges,estimates,chain):
    am=metrics(annual);mm=metrics(mtests);lm=metrics(legacy);bm=metrics(bridges)
    def display(rs):return [dict(r,wape=f"{r['wape']:.2%}",monthly_wape=f"{r['monthly_wape']:.2%}") for r in rs]
    cols=[('method','方法'),('market','市场'),('horizon','跨度'),('lead_start','提前起始'),('n','重叠起点数'),('distinct_target_years','不同目标年份'),('wape','WAPE'),('monthly_wape','逐月WAPE'),('bias','平均偏差/万辆')]
    body='<h1>第一版与改进版：历史验证和误差诊断</h1><p>运行日2026-11-04；信息冻结在2026-11-03。所有2026全年数字均为预测，不参与实际评分。</p>'
    body+='<h2>先回答同学的意见</h2><p>原表已与最初快照指纹核对一致，2015—2025共11年实际；2026E剔除。原版没有独立国内/出口模型，因此不替它编造分支预测。旧版2024→2025参照链：国内高估136.81万辆、出口低估133.10万辆，总量仅高估3.71万辆，约98.63%的分支绝对误差被抵消。“进出口”在这里应称国内与出口。</p>'
    body+='<p>下列比较分层报告，不能跨层挑一个更好的数字。原年度模型、月度适配和新增分支候选都保留失败结果。看过历史后开展的方法研究属于回顾性探索，不是封存的独立前瞻验收。</p>'
    a1=next(r for r in am if r['method']=='V1原版总量' and r['horizon']==1 and r['market']=='总量')
    a2=next(r for r in am if r['method']=='V2年度参照链' and r['horizon']==1 and r['market']=='总量')
    body+=f"<p><strong>当前共同年度样本：V1总量WAPE {a1['wape']:.2%}，V2参照链 {a2['wape']:.2%}，改进版在这个样本的总量成绩更差。不能宣称全局精度提升。</strong></p>"
    body+='<h2>一、原版多年度重跑</h2><p>扩展到2020—2024起点，1/2年提前期分别评分。按原始总量×份额趋势公式，趋势用锚点之前历史，汽车总量延续锚点。该层单独检查原版，不与缺早期分支数据的新版本硬拼。</p>'+table(display(lm),cols)
    body+='<h2>二、相同年度起点横向比较</h2><p>总量统一含出口。V1使用2015起原定历史窗口；V2用当时已有的同口径分支参照，另列V1相同年份窗口控制。年度参照公式不使用未来收入偏离，因此取消只对这项不使用参数的基线无关的“收入论文已发表”筛选，补跑更早起点；没有把论文参数偷放到发表前的实际预测中。这一层仍只有2023—2025三个不同目标年，不能宣布统计上稳定胜出。</p>'+table(display(am),cols)
    body+='<h2>三、月度多起点：同目标、同历史池、同提前期</h2><p>至少24个月训练。V1月度适配沿用总体市场×份额的思想，V2月度适配用国内总车市×国内份额＋季节出口。二者改变了频率和锚定规则，不是原年度完整经济模型重跑。V3是新增研究候选：国内与出口分别在训练内比较季节不变、半幅趋势、全幅趋势，以6个月内层WAPE选模，外层评分时不读取未来实际。内层仅6月，长期用途必须单独看外层表现。“仅更新出口”保留V2国内预测，单独观察出口修正的影响；此消融比较在看过初步结果后增加，仍是探索。</p><p>派生月若来源过晚会跳过相应实时起点；数据仍是当前公开版本，未恢复全部当时修订值。月度窗口高度重叠，起点数不是独立年份。“不同目标年份”按窗口末月计，2026的滚动12月实际窗口不代表已取得2026日历全年。</p>'
    body+=table(display([r for r in mm if (r['horizon'],r['lead_start']) in ((12,1),(24,1),(12,4),(12,16))]),cols)
    body+='<h2>四、模拟只知道前三季度，检查全年桥接</h2><p>对2023、2024、2025各取1—9月，使用上年全年×当年同期/上年同期，分国内和出口估算再加总。评分只用已发布的实际全年，保留年度与月度来源修订差异。这检验桥接自身，不代表已经检验下一两年政策情景。</p>'+table(display(bm),cols)
    body+='<h2>桥接后再预测下一年／两年</h2><p>另重放“只知前三季度→估计当前全年→预测后续年度”的参照链。可评分的后续实际仅2024和2025，不能把此有限链路检验写成完整政策模型验证。</p>'+table(display(metrics(chain)),cols)
    body+='<h2>五、2026可以补预测，但不能补成“实际”</h2>'+table([r for r in estimates if r['period']=='2026E全年'],[('method','方法'),('国内','国内/万辆'),('出口','出口/万辆'),('总量','总量/万辆'),('nature','性质')])
    body+='<h2>六、国内与出口的证据和待补资料</h2><p>已有四条同体系月度序列及年度官方参照。2026年前三季国内新能源846.6万辆，较2025同期947.0万辆少100.4；出口400.6万辆较175.8万辆多224.8；总量只净增124.4。这是算术分解，不是因果贡献。旧参照链出口固定不变，会漏掉快速增长期，不能继续靠总量误差掩盖这一问题。</p><p>新增出口研究候选让增长可以由历史趋势进入，但不能取代目的地需求、相对到岸价、汇率传递、关税/准入、海外库存和海外生产的结构分析。IEA说明2024出口增速放缓、2025增长加快及市场分化；欧盟2024措施针对中国来源BEV，不可直接加到全部PHEV、全车型或全部目的地。</p><p><a href="https://www.iea.org/reports/global-ev-outlook-2025/trends-in-the-electric-car-industry-3">IEA2025行业贸易分析</a>；<a href="https://www.iea.org/reports/global-ev-outlook-2026/manufacturing-and-trade">IEA2026制造与贸易</a>；<a href="https://ec.europa.eu/commission/presscorner/api/files/document/print/en/ip_24_5589/IP_24_5589_EN.pdf">欧委会2024正式措施</a>。这些来源补强机制和适用范围，未混入全国CAAM销量拟合。</p>'
    body+='<p>进一步核到：<a href="https://www.mofcom.gov.cn/cms_files/filemanager/policySummary/viewcore_c5f01aa2e1b24970a82098a26a3a55a8.html">商务部2025-09-26政策专题</a>说明指定纯电动载人车辆2026-01-01起实行出口许可证管理，属于需核执行覆盖的准入机制，不能直接填成数量损失系数。<a href="https://www.cada.cn/xinche/info_118_8923.html">汽车流通协会2021贸易分析</a>列2020新能源出口22.3万辆、2021年58.8万辆，明显不同于2021厂家口径31万辆；因此没有将其拼到CAAM分支历史。这也说明有权威来源还不够，必须对口径。</p><p>还需按目的地×BEV/PHEV取得出口量、价格、库存、终端登记和适用政策，并将海关贸易与厂家出货对齐；本轮未取得完整可比面板，不按总出口比例倒造分层实际，不把海外建厂销量当中国出口，也不把国内厂家销量称终端消费。</p>'
    body+='<h2>怎样用于汇报</h2><p>可以说：我们增加了原版对照、多年度/多月起点、桥接检查和分支失配诊断，并对出口提供新的可比较候选。是否提高准确性，要看相同表格内各分支、各提前期的实际结果；不能先写“提升”再挑样本。新增候选尚未成为默认经营预算，完整宏观、相对成本、政策链和真实业务用途仍需进一步验证。</p><p>逐条预测、共同起点汇总、抵消明细、2026预测及输入快照均在本目录，可用Excel打开CSV复算WAPE。没有给虚构的概率或业务容忍度。</p>'
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>版本横向回测与分支诊断</title><style>body{font:16px/1.8 Microsoft YaHei,sans-serif;background:#f3f6f8;color:#20384d;margin:0}main{max-width:1240px;margin:auto;padding:30px 20px 80px}h2{border-top:1px solid #cedce5;padding-top:22px;margin-top:32px}.scroll{overflow:auto;background:white}table{border-collapse:collapse;min-width:900px;width:100%}th,td{text-align:left;padding:10px;border-bottom:1px solid #dbe5eb;vertical-align:top}th{background:#203e55;color:white}a{color:#087c8a}</style><main>'+body+'</main></html>'

def run(out):
    if out.exists():raise ValueError('请使用新的输出目录')
    original=load(ROOT/'assets'/'v1-frozen.json');data=load(ROOT/'assets'/'nev-evidence.json')
    mrows=monthly.read(ROOT/'assets'/'nev-monthly.csv',data['as_of'])
    legacy,annual=annual_compare(original,data)
    mtests,choices,skips=monthly_compare(mrows)
    bridges=bridge_test(mrows,data);estimates,selected=estimated_2026(mrows,data)
    chain=september_chain(original,mrows,data)
    # Reproduction of the original published 2027/2028 central forecast.
    y25=data['history'][-1];a=data['recent']['2026_ytd'];b=data['recent']['2025_ytd']
    anchor={'year':2026,'auto':y25['auto']*a['auto']/b['auto'],'nev':y25['nev']*a['nev']/b['nev']}
    reproduced=[dict(year=2026+h,total=v1_total(original['history'],anchor,h)) for h in (1,2)]
    out.mkdir(parents=True)
    csvwrite(out/'三季度桥接再预测后续年度逐条.csv',chain)
    csvwrite(out/'三季度桥接再预测后续年度汇总.csv',metrics(chain))
    for name,rs in [('原版扩大年度逐条.csv',legacy),('原版扩大年度汇总.csv',metrics(legacy)),('同起点年度逐条.csv',annual),('同起点年度汇总.csv',metrics(annual)),('月度适配逐条.csv',mtests),('月度适配汇总.csv',metrics(mtests)),('月度选模记录.csv',choices),('月度跳过起点.csv',skips),('年度抵消诊断.csv',cancellation(annual)),('月度抵消诊断.csv',cancellation(mtests)),('前三季度全年桥接逐条.csv',bridges),('前三季度全年桥接汇总.csv',metrics(bridges)),('2026全年估计及Q4路径.csv',estimates),('原始2027_2028基准复现.csv',reproduced)]:csvwrite(out/name,rs)
    for name,path_in in [('原版输入快照.json',ROOT/'assets'/'v1-frozen.json'),('年度输入快照.json',ROOT/'assets'/'nev-evidence.json'),('月度输入快照.csv',ROOT/'assets'/'nev-monthly.csv')]:
        (out/name).write_bytes(path_in.read_bytes())
    status={'pipeline':'completed','as_of':data['as_of'],'annual_original_years':len(original['history']),'annual_paired_rows':len(annual),'monthly_rows':len(mrows),'monthly_prediction_records':len(mtests),'original_reproduced':reproduced,'candidate_2026_selection':selected,'actual_2026_available':False,'validation_status':'当前版本回顾性比较；原年度与月度适配分层，经济驱动因果与业务验收未完成','code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (out/'运行状态.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'版本横向回测与分支诊断.html').write_text(report(out,original,legacy,annual,mtests,bridges,estimates,chain),encoding='utf-8')
    return status

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',type=Path)
    args=parser.parse_args();out=args.output_dir or ROOT/'运行记录'/('validation_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    print(json.dumps(run(out),ensure_ascii=False,indent=2))
