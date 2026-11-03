"""ABS-specific monthly baselines, nested rolling validation and conditional planning (stdlib)."""
import csv
import hashlib
import html
import json
import math
from pathlib import Path
import statistics
from datetime import date

ROOT = Path(__file__).resolve().parents[1]
MODELS = ('naive', 'seasonal', 'mean12', 'count_size')
LABELS = {'naive': '最近月延续', 'seasonal': '上年同月延续', 'mean12': '近12月均值',
          'count_size': '季节项目数×近12月加权单均规模', 'adaptive': '训练内选模'}
TARGETS = ('volume', 'projects')


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def advance(period, steps=1):
    year, month = map(int, period.split('-'))
    date(year, month, 1)
    index = year*12+month-1+steps
    return f'{index//12:04d}-{index%12+1:02d}'


def read(path, settings, meta):
    date.fromisoformat(settings['as_of'])
    if meta['latest_list_publication'] > settings['as_of']:
        raise ValueError('最新来源目录发布日期晚于截止日。')
    if meta['columns']['new_volume_100m_cny']['unit'] != '亿元' or meta['columns']['new_projects']['unit'] != '只':
        raise ValueError('ABS规模和数量单位不匹配。')
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    for item in rows:
        period = item['period']
        if advance(period, 0) != period or period > settings['as_of'][:7]:
            raise ValueError('期间无效或越过截止日。')
        for key in item:
            if key != 'period' and item[key] != '':
                item[key] = float(item[key])
                if not math.isfinite(item[key]):
                    raise ValueError('数据必须为有限数。')
        if item['new_volume_100m_cny'] <= 0 or item['new_projects'] <= 0 or not item['new_projects'].is_integer():
            raise ValueError('当前适配器要求规模与项目数为正，项目数为整数；零项目期需单独适配。')
        item['volume'] = item['new_volume_100m_cny']
        item['projects'] = item['new_projects']
        item['average_size'] = item['volume']/item['projects']
    if any(advance(a['period']) != b['period'] for a, b in zip(rows, rows[1:])):
        raise ValueError('月份必须连续、升序且无重复。')
    if len(rows) < settings['outer_min_train']+settings['selection_horizon']:
        raise ValueError('历史长度不足以支持当前验证设计；请降级方法，不填造月份。')
    if rows[-1]['period'] != settings['latest_period']:
        raise ValueError('数据末期与配置不一致。')
    if settings['outer_min_train'] < settings['inner_min_train']+settings['selection_horizon']+5:
        raise ValueError('训练内选模至少保留六个可用起点。')
    if settings['target_years'] != sorted(set(settings['target_years'])) or any(y <= int(rows[-1]['period'][:4]) for y in settings['target_years']):
        raise ValueError('预测年份需升序、唯一且晚于最后观测年度。')
    if len(settings['scenarios']) != 3 or len({s['name'] for s in settings['scenarios']}) != 3:
        raise ValueError('需要三个不同的命名情景。')
    for scenario in settings['scenarios']:
        for key in ('project_growth', 'size_growth'):
            values = scenario[key]
            if len(values) != len(settings['target_years']) or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= -1 for v in values):
                raise ValueError('情景路径长度或增长率无效。')
    return rows


def predict(history, horizon, model):
    if model not in MODELS or horizon < 1 or len(history) < 12:
        raise ValueError('模型、预测长度或历史长度无效。')
    avg = {key: statistics.mean(r[key] for r in history[-12:]) for key in TARGETS}
    size = sum(r['volume'] for r in history[-12:])/sum(r['projects'] for r in history[-12:])
    result = []
    for step in range(horizon):
        seasonal = history[-12+step % 12]
        if model == 'naive':
            values = {key: history[-1][key] for key in TARGETS}
        elif model == 'mean12':
            values = dict(avg)
        elif model == 'seasonal':
            values = {key: seasonal[key] for key in TARGETS}
        else:
            values = {'projects': seasonal['projects'], 'volume': seasonal['projects']*size}
        result.append(dict(period=advance(history[-1]['period'], step+1), **values))
    return result


def select(history, settings):
    horizon = settings['selection_horizon']
    origins = range(settings['inner_min_train'], len(history)-horizon+1)
    scores = []
    for model in MODELS:
        errors = []; actuals = []; monthly_errors = []
        for n in origins:
            actual = sum(r['volume'] for r in history[n:n+horizon])
            path = predict(history[:n], horizon, model)
            forecast = sum(r['volume'] for r in path)
            errors.append(abs(forecast-actual)); actuals.append(actual)
            monthly_errors.append(sum(abs(p['volume']-a['volume']) for p,a in zip(path, history[n:n+horizon])))
        if not errors:
            raise ValueError('训练内验证没有可用起点。')
        scores.append({'model': model, 'wape': sum(errors)/sum(actuals),
                       'monthly_wape': sum(monthly_errors)/sum(actuals), 'origins': len(errors)})
    # Annual sums of seasonal/mean12/count_size are algebraically equal. Resolve ties
    # by training-only monthly error, then declared MODELS order, never outer targets.
    best = min(scores, key=lambda s: (round(s['wape'], 12), s['monthly_wape'], MODELS.index(s['model'])))['model']
    return best, scores


def backtest(rows, settings, horizons=(1, 3, 12, 24)):
    detail = []
    windows = [(h, 0) for h in horizons] + [(12, 3), (12, 15)]
    for n in range(settings['outer_min_train'], len(rows)):
        history = rows[:n]
        selected, _ = select(history, settings)
        for horizon, offset in windows:
            if n+offset+horizon > len(rows):
                continue
            actual = rows[n+offset:n+offset+horizon]
            for method in (*MODELS, 'adaptive'):
                forecasts = predict(history, offset+horizon, selected if method == 'adaptive' else method)[offset:]
                for target in TARGETS:
                    a = sum(r[target] for r in actual); p = sum(r[target] for r in forecasts)
                    detail.append({'origin_period': history[-1]['period'], 'training_months': n,
                                   'start': actual[0]['period'], 'end': actual[-1]['period'],
                                   'horizon': horizon, 'lead_start': offset+1, 'lead_end': offset+horizon,
                                   'method': method, 'selected_model': selected if method == 'adaptive' else method,
                                   'target': target, 'actual': a, 'forecast': p, 'error': p-a,
                                   'abs_monthly_error': sum(abs(x[target]-y[target]) for x, y in zip(forecasts, actual))})
    summary = []
    for horizon, offset in windows:
        for method in (*MODELS, 'adaptive'):
            for target in TARGETS:
                sample = [r for r in detail if r['horizon'] == horizon and r['lead_start'] == offset+1 and r['method'] == method and r['target'] == target]
                if not sample:
                    continue
                denominator = sum(r['actual'] for r in sample)
                summary.append({'horizon': horizon, 'lead_start': offset+1, 'lead_end': offset+horizon,
                                'method': method, 'target': target, 'origins': len(sample),
                                'mae': statistics.mean(abs(r['error']) for r in sample),
                                'wape': sum(abs(r['error']) for r in sample)/denominator,
                                'monthly_wape': sum(r['abs_monthly_error'] for r in sample)/denominator,
                                'bias': statistics.mean(r['error'] for r in sample),
                                'first_origin': sample[0]['origin_period'], 'last_origin': sample[-1]['origin_period'],
                                'nonoverlapping_windows_available': (len(sample)-1)//horizon+1})
    return detail, summary


def scenarios(rows, settings, model):
    last = f"{settings['target_years'][-1]}-12"
    start = advance(rows[-1]['period'])
    def idx(period):
        y, m = map(int, period.split('-')); return y*12+m
    forecast = predict(rows, idx(last)-idx(start)+1, model)
    monthly = []; annual = []
    for scenario in settings['scenarios']:
        factors = {}; count_factor = size_factor = 1.0
        for year, cg, sg in zip(settings['target_years'], scenario['project_growth'], scenario['size_growth']):
            count_factor *= 1+cg; size_factor *= 1+sg
            factors[year] = (count_factor, size_factor)
        for item in forecast:
            year = int(item['period'][:4]); cf, sf = factors.get(year, (1.0, 1.0))
            count = item['projects']*cf
            size = item['volume']/item['projects']*sf
            monthly.append({'scenario': scenario['name'], 'period': item['period'], 'volume': count*size,
                            'projects': count, 'average_size': size, 'project_factor': cf, 'size_factor': sf,
                            'nature': '规划压力条件；项目数为期望量，可有小数，不是确定订单'})
        for year in settings['target_years']:
            subset = [r for r in monthly if r['scenario'] == scenario['name'] and r['period'].startswith(str(year))]
            count = sum(r['projects'] for r in subset); volume = sum(r['volume'] for r in subset)
            annual.append({'scenario': scenario['name'], 'year': year, 'volume': volume, 'projects': count,
                           'average_size': volume/count, 'months': len(subset),
                           'lead_start': idx(subset[0]['period'])-idx(rows[-1]['period']),
                           'lead_end': idx(subset[-1]['period'])-idx(rows[-1]['period']),
                           'conditions': scenario['conditions']})
    return monthly, annual


def company_bridge(annual, company):
    keys = ('volume_share', 'project_share', 'fee_rate', 'hours_per_project', 'annual_available_hours')
    for key in keys:
        value = company.get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0):
            raise ValueError('企业参数需为非负有限数或null。')
    for key in keys[:3]:
        if company.get(key) is not None and company[key] > 1:
            raise ValueError('份额与费率须用0—1小数。')
    result = []
    for row in annual:
        if any(company.get(key) is None for key in keys):
            result.append({'scenario': row['scenario'], 'year': row['year'], 'status': 'needs_input',
                           'nature': company['nature'], 'formula': '规模×规模份额；数量×数量份额；服务费万元=规模亿元×费率×10000；工时=项目数×单项工时'})
        else:
            volume = row['volume']*company['volume_share']; count = row['projects']*company['project_share']
            hours = count*company['hours_per_project']
            result.append({'scenario': row['scenario'], 'year': row['year'], 'status': 'conditional_calculated',
                           'nature': company['nature'], 'opportunity_volume': volume, 'opportunity_projects': count,
                           'fee_revenue_10k_cny': volume*company['fee_rate']*10000,
                           'required_hours': hours, 'hours_gap': max(0, hours-company['annual_available_hours']),
                           'limit': '市场机会和单次费用敏感性，不是已签订单、利润或当年收入确认；未计项目储备、转化、跨期存续费和监管约束'})
    return result


def write_csv(path, rows):
    if not rows:
        return
    keys = list(dict.fromkeys(key for row in rows for key in row))
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=keys); writer.writeheader(); writer.writerows(rows)


def table(rows, columns):
    def cell(value):
        if isinstance(value, float):
            return f'{value:,.2f}'
        return html.escape(str(value))
    return '<div class="table"><table><thead><tr>'+''.join('<th>'+html.escape(label)+'</th>' for key,label in columns)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+cell(row.get(key,''))+'</td>' for key,label in columns)+'</tr>' for row in rows)+'</tbody></table></div>'


def report(settings, rows, meta, monthly, annual, companies, summary, selected, scores):
    esc = html.escape
    metric_rows = [dict(r, method=LABELS[r['method']], wape=f"{r['wape']:.2%}", monthly_wape=f"{r['monthly_wape']:.2%}") for r in summary if r['horizon'] in (12,24)]
    body = f'<p class="eyebrow">行业需求预测与经营计划助手 · ABS 模块</p><h1>融资活动预测与业务预案</h1><p>信息截止 {settings["as_of"]} · {len(rows)}个月 · {rows[0]["period"]}—{rows[-1]["period"]}</p>'
    body += '<div class="notice">计算已完成；验证对象是新增备案活动的统计预测。宏观、利差和政策的因果数量效应尚未估计；企业业务验收尚未完成。</div>'
    body += '<h2>任务与决策摘要</h2><p>'+esc(settings['task']['user'])+'：'+esc(settings['task']['decision'])+'</p><p>'+esc(settings['task']['demand_actors'])+'</p><p>'+esc(settings['task']['boundary'])+'</p>'
    decisions = [
        {'advice':'以基准机会量安排可调整的项目团队，按悲观情景核查固定工时承诺', 'reason':'融资活动同时受原始权益人资产池、替代融资与投资者资金约束', 'condition':'取得企业项目储备、转化率、项目复杂度及可用工时后复算', 'risk':'行业份额假设不能替代已签项目，规模与项目数可能出现相反变化'},
        {'advice':'2028年优先保留弹性人力与业务管线，分阶段审批扩张', 'reason':'当前最长目标提前到第27个月，长周期证据少，制度及资产结构可能改变', 'condition':'每月跟踪新增规模／数量，每季复核单均规模、成本优势和延期情况', 'risk':'季节基线无法预见政策突变、信用事件和投资者退出'},
        {'advice':'融资成本按同评级同期限比较，未取得配套数据前只给条件判断', 'reason':'ABS总成本与贷款／债券的差值影响融资方式替代，名义利率下降不必然扩大ABS相对优势', 'condition':'补发行利率、费用、评级、期限、替代融资报价及成功率', 'risk':'价格与规模共同决定，直接回归可能有反向因果和遗漏变量偏误'}]
    body += table(decisions,[('advice','建议'),('reason','理由'),('condition','适用条件'),('risk','风险')])
    leads = '；'.join(f"{r['year']}年为第{r['lead_start']}—{r['lead_end']}个月" for r in annual if r['scenario']==settings['scenarios'][0]['name'])
    body += '<h2>三情景：规模与项目数同时解释</h2><p>'+esc(settings['scenario_nature'])+'</p><p>每月规模 = 项目数 × 单均规模。项目与单均规模冲击逐年累乘；最后实际月之后、目标年度之前的月份先由基线桥接，未当作实际值。'+leads+'。连续12／24月回测并不完全等同日历年目标验证。</p>'
    chart_data = json.dumps({'history':[{k:r[k] for k in ('period','volume','projects')} for r in rows],
                             'future':monthly}, ensure_ascii=False)
    body += '<p><label>图表指标 <select id="target"><option value="volume">新增备案规模（亿元）</option><option value="projects">新增项目数量（只）</option></select></label>　<label>显示情景 <select id="scenario"><option value="all">全部情景</option><option>悲观</option><option>基准</option><option>乐观</option></select></label></p><div class="table"><svg id="forecast-chart" viewBox="0 0 1080 380" style="min-width:640px;width:100%" role="img" aria-label="ABS历史与条件预测折线图"></svg></div><p>深蓝为历史实际；虚线为条件预测：红色悲观、青色基准、绿色乐观。竖线后2026第四季度是桥接估计，三条线重合。图表呈现全部81个月历史，非置信区间。</p>'
    body += '<script>const chartData='+chart_data+''';
function drawChart(){
const svg=document.getElementById('forecast-chart'),target=document.getElementById('target').value,chosen=document.getElementById('scenario').value;
const names=['悲观','基准','乐观'],colors=['#bb4c50','#067d91','#519640'];
const history=chartData.history,periods=history.map(r=>r.period).concat(chartData.future.filter(r=>r.scenario===names[0]).map(r=>r.period));
const paths=names.map(n=>chartData.future.filter(r=>r.scenario===n));
const top=Math.max(...history.map(r=>r[target]),...paths.flat().map(r=>r[target]))*1.12;
const x=i=>70+i/(periods.length-1)*970,y=v=>325-v/top*275;
let elements='<rect x="'+x(history.length-1)+'" y="30" width="'+(1040-x(history.length-1))+'" height="295" fill="#e8f0f3"/>';
for(let tick=0;tick<=4;tick++){const value=top*tick/4;elements+='<line x1="70" y1="'+y(value)+'" x2="1040" y2="'+y(value)+'" stroke="#d9e2e8"/><text x="60" y="'+(y(value)+5)+'" text-anchor="end" font-size="13">'+Math.round(value).toLocaleString()+'</text>';}
const points=(p,offset)=>p.map((r,i)=>x(i+offset)+','+y(r[target])).join(' ');
elements+='<polyline fill="none" stroke="#213d56" stroke-width="2" points="'+points(history,0)+'"/>';
paths.forEach((path,i)=>{if(chosen==='all'||chosen===names[i])elements+='<polyline fill="none" stroke="'+colors[i]+'" stroke-width="2.5" stroke-dasharray="7 4" points="'+points([history.at(-1),...path],history.length-1)+'"/>';});
[0,Math.floor(history.length/2),history.length-1,periods.length-1].forEach(i=>{elements+='<text x="'+x(i)+'" y="350" font-size="13" text-anchor="middle">'+periods[i]+'</text>';});
elements+='<line x1="'+x(history.length-1)+'" x2="'+x(history.length-1)+'" y1="30" y2="325" stroke="#54738b" stroke-dasharray="4 4"/><text x="75" y="22" font-size="14">'+(target==='volume'?'新增规模（亿元）':'新增项目数（只）')+'</text><text x="1025" y="22" text-anchor="end" font-size="14">条件预测</text>';
svg.innerHTML=elements;svg.dataset.target=target;svg.dataset.scenario=chosen;
}
document.getElementById('target').addEventListener('change',drawChart);document.getElementById('scenario').addEventListener('change',drawChart);drawChart();</script>'''
    body += table(annual,[('scenario','情景'),('year','年度'),('volume','新增备案亿元'),('projects','项目数期望值'),('average_size','单均亿元'),('conditions','成立条件')])
    body += '<h2>经济机制与实际纳入状态</h2>'+table(settings['drivers'],[('name','因素'),('mechanism','传导机制'),('needed','待补数据'),('status','计算状态')])
    body += '<h2>历史验证：年度合计与月度误差并列</h2><p>所有候选方法在相同起点比较。每个外层起点仅用此前数据，在训练内部比较12个月合计WAPE后选模；合计并列时按训练内月度WAPE选择，再按固定方法顺序。季节、近12月均值和数量×规模法的完整12个月合计本来就相同，不能据此声称三种独立模型相互印证。当前选择：<strong>'+esc(LABELS[selected])+'</strong>。下表“训练内选模”是整个选模规则的外层表现，不能用当前胜出方法的全样本排名冒充独立测试。</p>'
    body += '<p>当前版本伪滚动验证，未重建当年发布时间与原始版本；此前已查看过部分基线表现，本轮属于回顾性设计与比较，不是封存的独立前瞻验证。起点按月滚动，预测窗口重叠，不能把起点数当作独立年份。WAPE=绝对合计误差之和／实际合计之和；月度WAPE先对各月误差取绝对值，可显示跨月抵消。</p>'
    matched = [r for r in summary if r['method']=='adaptive' and r['target']=='volume' and r['lead_start']>1]
    body += '<p>相近提前期的回顾验证：'+'；'.join(f"第{r['lead_start']}—{r['lead_end']}月有{r['origins']}个重叠起点" for r in matched)+'。这仍不是按历史实际发布日期历的精确回放，起点数也不是独立年份数。</p>'
    body += table(metric_rows,[('lead_start','提前起始月'),('lead_end','提前末月'),('method','方法'),('target','目标'),('origins','重叠起点数'),('wape','合计WAPE'),('monthly_wape','月度WAPE'),('bias','平均有向误差'),('nonoverlapping_windows_available','最多不重叠窗口')])
    body += '<p>未取得业务误差容忍度、错估损失与真实企业输入，尚不能判定满足经营用途。2027／2028压力情景及企业映射没有因果回测通过证明。</p>'
    body += '<h2>企业条件核算</h2>'+table(companies,[('scenario','情景'),('year','年度'),('status','状态'),('opportunity_volume','机会规模亿元'),('opportunity_projects','机会项目数'),('fee_revenue_10k_cny','费用敏感性万元'),('required_hours','所需工时'),('hours_gap','工时缺口'),('nature','输入性质'),('formula','缺数时公式')])
    body += '<h2>数据边界与复核</h2><p>'+esc(meta['source_provider'])+'；'+esc(meta['verification'])+'</p><p>'+esc(meta['availability'])+'</p><p>存续规模是期末存量；新增备案是流量；深交所成交额是局部二级市场交易。三者不相加，也未把所有列同时纳入回归。</p><p><a href="'+meta['public_source']+'">协会简报目录</a> · <a href="ABS回测汇总.csv">完整回测汇总</a> · <a href="ABS逐条回测.csv">逐条核查</a> · <a href="运行状态.json">运行与验证状态</a> · <a href="本次设置.json">本次唯一情景设置</a></p>'
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ABS融资活动预测与业务预案</title><style>body{font:16px/1.8 "Microsoft YaHei",sans-serif;background:#f3f5f8;color:#20344b;margin:0}main{max-width:1200px;margin:auto;padding:36px 24px 80px}h1{font-size:36px;margin:8px 0}h2{margin-top:38px;border-top:1px solid #cad5df;padding-top:22px}.eyebrow{color:#197c87;font-weight:700}.notice{background:#e0eef0;border-left:5px solid #197c87;padding:16px}.table{overflow:auto;background:white;margin:18px 0}table{border-collapse:collapse;width:100%;min-width:640px}th,td{padding:12px;border-bottom:1px solid #e2e8ef;text-align:left;vertical-align:top}th{background:#213d56;color:white;white-space:nowrap}a{color:#076e86}@media(max-width:600px){main{padding:20px 16px}h1{font-size:27px}}</style><main>'+body+'</main></html>'


def run(output, data_path=None, settings_path=None, company_path=None, source_path=None):
    data_path = Path(data_path or ROOT/'assets'/'abs-monthly.csv')
    settings_path = Path(settings_path or ROOT/'assets'/'abs-settings.json')
    company_path = Path(company_path or ROOT/'assets'/'abs-company.json')
    source_path = Path(source_path or ROOT/'assets'/'abs-source.json')
    settings = load(settings_path); meta = load(source_path); company = load(company_path)
    rows = read(data_path, settings, meta)
    selected, scores = select(rows, settings)
    detail, summary = backtest(rows, settings)
    monthly, annual = scenarios(rows, settings, selected)
    companies = company_bridge(annual, company)
    if output.exists():
        raise ValueError('输出目录已存在；请使用新目录保留运行版本。')
    output.mkdir(parents=True)
    for name, items in [('ABS月度输入.csv', rows), ('ABS月度条件路径.csv', monthly), ('ABS年度三情景.csv', annual),
                        ('ABS逐条回测.csv', detail), ('ABS回测汇总.csv', summary), ('ABS当前训练内选模.csv', scores), ('ABS企业条件核算.csv', companies)]:
        write_csv(output/name, items)
    for name, obj in [('本次设置.json', settings), ('数据来源.json', meta), ('企业输入快照.json', company)]:
        (output/name).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    status = {'pipeline':'completed', 'industry':'abs', 'as_of':settings['as_of'], 'history_months':len(rows),
              'forecast_months_per_scenario':len(monthly)//3, 'selected_model':selected, 'selection_scores':scores,
              'annual_scenarios':len(annual), 'backtest_rows':len(detail),
              'forecast_validation':'当前版本回顾性伪滚动；嵌套选模规则已比较；前瞻经济参数、发布日期实时回放及情景尚未验证',
              'business_acceptance':'尚未验收；缺企业实际管线、工时、份额、费用与风险容忍度',
              'company_states':[r['status'] for r in companies], 'drivers':settings['drivers'],
              'input_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (data_path, settings_path, company_path, source_path)},
              'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (output/'运行状态.json').write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
    (output/'ABS融资活动预测与业务预案.html').write_text(report(settings, rows, meta, monthly, annual, companies, summary, selected, scores), encoding='utf-8')
    return status
