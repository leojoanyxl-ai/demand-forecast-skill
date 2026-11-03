"""One report for the declared data accounts, calibration and validation scopes."""
import html

LABELS={'domestic_auto':'国内汽车代理','domestic_nev':'国内新能源代理','nev_export':'新能源出口','total_nev':'新能源总销量',
        'auto':'汽车总销量','nev':'新能源总销量','auto_export':'汽车出口'}


def fmt(value,key=''):
    if value is None:return '待补'
    if isinstance(value,float):
        if key in ('wape','total_wape','branch_absolute_error_over_total','cancellation_fraction'):return f'{value:.2%}'
        return f'{value:,.4f}' if abs(value)<10 else f'{value:,.2f}'
    return html.escape(str(value))


def table(rows,cols):
    return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+html.escape(label)+'</th>' for key,label in cols)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+fmt(LABELS.get(r.get(key),r.get(key)) if key in ('market','metric') else r.get(key),key)+'</td>' for key,label in cols)+'</tr>' for r in rows)+'</tbody></table></div>'


def monthly_chart(rows):
    maximum=max(max(r['domestic_nev'],r['nev_export']) for r in rows)*1.1
    parts=['<svg viewBox="0 0 950 260" role="img" aria-label="国内新能源销量代理与新能源出口月度原值">']
    for f in (0,.5,1):
        y=220-f*180
        parts.append(f'<line x1="60" y1="{y}" x2="900" y2="{y}" stroke="#d6e0e9"/><text x="0" y="{y+4}">{maximum*f:.0f}</text>')
    for key,color,name in [('domestic_nev','#136b9f','国内新能源'),('nev_export','#b56837','新能源出口')]:
        points=' '.join(f'{60+i*840/(len(rows)-1):.2f},{220-r[key]/maximum*180:.2f}' for i,r in enumerate(rows))
        parts.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2.5"/>')
        parts.append(f'<text x="{100 if key=="domestic_nev" else 300}" y="20" fill="{color}">{name}</text>')
    for i,r in enumerate(rows):
        if i==0 or r['period'].endswith('-01') or i==len(rows)-1:
            parts.append(f'<text x="{45+i*840/(len(rows)-1):.2f}" y="250" font-size="13">{r["period"]}</text>')
    return ''.join(parts)+'</svg>'


def render(data,c,fit,forecasts,checks,gridrows,companies,context):
    m=context['monthly_rows'];reg=c['parameter_registry']['parameters'];mapped=context['mapping']
    paramrows=[]
    for key,p in reg.items():paramrows.append(dict(parameter=key,central=p['central'],range=str(p['range']),grid=str(sorted(set(p['grid']+[p['central']]+p['range']))),interpretation=p['interpretation']))
    combinations=len(gridrows)//len(forecasts)
    ranges=[]
    for r in forecasts:
        values=[g['total_nev'] for g in gridrows if g['year']==r['year'] and g['scenario']==r['scenario']]
        ranges.append(dict(year=r['year'],scenario=r['scenario'],low=min(values),central=r['total_nev'],high=max(values)))
    h1=next(r for r in context['cancellation'] if r['method']=='需求参照链' and r['h']==1)
    bad=[r for r in context['reconciliation'] if r['status']!='舍入范围内']
    heading=f"{data['history'][0]['year']}—{data['history'][-1]['year']}共{fit['observations']}个年度；月度{m[0]['period']}—{m[-1]['period']}共{len(m)}个月"
    chunks=['''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>需求预测与经营预案 · 统一版</title><style>*{box-sizing:border-box}body{font:16px/1.75 system-ui,"Microsoft YaHei",sans-serif;background:#f3f6fa;color:#19344c;margin:0}main{max-width:1180px;margin:auto;padding:28px 24px}h1{font-size:28px}h2{font-size:23px;margin-top:0}section{background:white;padding:24px;margin:20px 0;border-radius:10px}.notice{padding:16px;background:#fff1d4;border-left:4px solid #b77e24}.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:10px;text-align:left;vertical-align:top;border-bottom:1px solid #dce4ec;min-width:76px}td{overflow-wrap:anywhere}th{background:#edf3f8}a{color:#126b9c}svg{width:100%;height:auto}small{color:#52697a}@media(max-width:600px){main{padding:14px 10px}section{padding:16px}h1{font-size:24px}}@media print{body{background:white}main{max-width:none;padding:0}section{border-radius:0}button{display:none}}</style></head><body><main><h1>2027销售与产能预案及2028需求风险</h1>''',
        f'<p>信息截止：{html.escape(data["as_of"])}｜数量单位：万辆｜{heading}</p>',
        '<div class="notice">公开目标、辅助数据、原始弹性目标、转换系数、条件情景和验证范围分别列示。程序完成不表示完整经济链已验证；没有真实企业数据与业务容忍度时，不宣布业务验收通过。</div>',
        '<section><h2>决策与统计边界</h2><p>使用者为整车企业战略部门，需求主体为家庭、营运企业/车队及海外客户。厂家总销量Q=国内D+出口X；国内是同口径相减的代理，不自动等于含进口的终端消费。出口出货不自动等于海外销售。新能源汽车含乘用及商用，代表乘用车成本推广到全行业仍需验证。</p>',
        table([
            dict(action='分别设置国内、出口预算条件',reason='支付能力、技术替代与海外政策/渠道的传导不同',condition='核验分车型订单、渠道库存及可服务市场',risk='增长不能保证企业份额；战略部门在预算定稿前复核'),
            dict(action='比较班次、外协与产能预留',reason='需求路径与参数不确定，需要比较灵活性成本',condition='取得有效产能、报价、良率与交期约束',risk='质量、交付与增量成本；生产采购部门复核'),
            dict(action='出口报价同时核算数量和收益',reason='退税损失经买方价格或厂商收益吸收',condition='核实商品代码、税基、月份分布与合同币种',risk='示例税基不能当真实利润；财务在新报价前复核'),
            dict(action='新增产线保留条件评审',reason='行业需求尚不能证明企业增量投资回报',condition='可信订单、现金流、建设期及替代方案',risk='需求落空与技术切换；投资审批前复核')],
            [('action','建议'),('reason','理由'),('condition','适用条件'),('risk','风险与复核')]),'</section>',
        '<section><h2>月度需求入口与辅助数据</h2>',
        f'<p>四条月度目标有{len(m)}个月，其中{sum(r["status"]=="derived" for r in m)}个月为累计差分推算；逐行保留来源、发布日期、单位、性质和计算依据。没有用产量或企业全球销量填需求缺口。</p>',monthly_chart(m),
        table(context['auxiliary_roles'],[('metric','辅助指标'),('n','观察数'),('first','起始'),('last','截至'),('modeling_status','实际用途'),('historical_driver_validation','验证限制')]),
        f'<p>公共桩原值计算历史CAGR为{context["infra"]["reference_growth"]:.2%}，最近同比为{context["infra"]["recent_yoy_growth"]:.2%}。未来沿用最近同比仍是条件，不是观测；桩数和便利性不能直接等同。</p>',
        '<p><a href="月度需求序列.csv">月度目标与国内/出口计算</a> · <a href="辅助变量用途.csv">辅助用途</a> · <a href="辅助原始输入.csv">辅助原值与定位</a></p></section>',
        '<section><h2>统一参数与弹性转换</h2><p>中央值、范围与网格只读取统一参数表；模型内部系数经过转换。购价弹性经κ=dln(TCO)/dln(购价)转为成本系数，新能源选择还计入M的响应。补能γ=目标销量弹性/(1-p锚点)，未来隐含弹性=(1-p未来)γ。固定系数不意味着每年的销量弹性相同。</p>',
        table(paramrows,[('parameter','原始目标'),('central','中央值'),('range','范围'),('grid','实际网格'),('interpretation','依据与限制')]),
        table(mapped,[('stage','计算位置'),('parameter','参数'),('raw_target','原始校准目标'),('model_value','模型系数'),('local_implied','局部隐含弹性'),('formula','转换关系')]),
        '<p>转换公式可复算，不等于样本、国家和指标已经可迁移。补能文献含OLS关联；出口Armington量级不自动成为出口需求估计。所有行为系数仍未由本项目本地识别。</p><p><a href="统一参数表.json">本次参数表</a> · <a href="弹性转换与隐含弹性.csv">转换明细</a></p></section>',
        '<section><h2>三情景条件结果</h2><p>国内D=M×p；收入与总成本作用于总市场，相对持有成本与补能作用于技术选择；出口单独处理海外规模、相对价格、退税传递和准入。政策已进入成本时不另扣同一数量冲击。2027购置税按已公告半征，2028接续为条件分支。</p>',
        table(forecasts,[('year','年'),('scenario','情景'),('domestic_auto','国内汽车M'),('domestic_share','新能源份额p（小数）'),('domestic_nev','国内新能源D'),('nev_export','出口X'),('total_nev','D+X')]),
        table([dict(scenario=s['name'],income=str(s['real_income_growth']),nev_price=str(s['nev_real_price_growth']),foreign=str(s['foreign_demand_growth']),infrastructure=str(s['infrastructure_growth'])) for s in c['scenarios']],
              [('scenario','情景'),('income','实际收入增速路径'),('nev_price','新能源实际车价压力路径'),('foreign','海外规模路径'),('infrastructure','补能条件路径')]),
        '<p>未来路径、代表车型成本、出口税基及政策覆盖含规划假设；小汽车CPI只提供共同价格参照数值，不能识别真实分车型相对价格。以上不是官方或概率预测。</p>',
        f'<p>本轮{combinations}组参数组合，形成{len(gridrows)}条年份/情景计算。中央点和所列边界均进入网格；这些是压力组合，不是历史样本或置信区间。</p>',
        table(ranges,[('year','年'),('scenario','情景'),('low','网格最小'),('central','中央组合'),('high','网格最大')]),
        '<p><a href="经济机制细节/经济机制与经营判断.html">渠道分解与交互敏感性</a> · <a href="参数压力网格.csv">全部参数组合</a></p></section>',
        '<section><h2>国内、出口与总量分别验证</h2>',
        f'<p>年度参照链h=1的总量WAPE为{h1["total_wape"]:.2%}；分支绝对误差合计/总量实际为{h1["branch_absolute_error_over_total"]:.2%}，抵消比例为{h1["cancellation_fraction"]:.2%}。只报总量会遮蔽分支误差。</p>',
        table(checks,[('method','年度方法'),('market','分支'),('h','年度h'),('n','记录数'),('mae','MAE'),('wape','WAPE'),('bias','偏差')]),
        table(context['cancellation'],[('method','年度方法'),('h','h'),('n','记录数'),('total_wape','总量WAPE'),('branch_absolute_error_over_total','分支绝对误差/总量'),('cancellation_fraction','抵消比例')]),
        '<p>年度测试只有少量实际年；收入预测与收入参照相同，所以未检验收入弹性。年度参照链不验证价格、2027新政策、2026全年桥接或企业计划。</p><h3>月度目标基准检验</h3>',
        table([r for r in context['monthly_metrics'] if r['market']!='domestic_auto'],[('method','月度方法'),('market','分支'),('h','月度h'),('n','预测数'),('mae','MAE'),('wape','WAPE'),('bias','偏差')]),
        '<p>月度h从最后实际月份起计；信息日按当时所用来源日期检查，实际日历提前期受发布滞后影响。较晚差分资料会跳过不合格起点。不同h不混算，重复目标或相邻窗口不视为独立年度。月度基准尚未验证全套经济驱动与企业业务损失。</p>',
        '<p><a href="月度逐条回测.csv">逐条月度预测</a> · <a href="月度分支抵消诊断.csv">月度抵消诊断</a> · <a href="月度跳过起点.csv">跳过原因</a></p></section>',
        '<section><h2>年度与月度版本差异</h2><p>同为中汽协来源的逐月当月值与独立累计/年报存在差额。没有缩放、插值或增加“其他”将其配平。超过舍入范围的行保留待核状态，年度校准继续使用独立年度值，月度基准使用其声明的发布序列。</p>',
        table(bad,[('period','期间'),('metric','指标'),('monthly_sum','月度和'),('independent_reported','独立报告值'),('difference','差额'),('status','状态')]),
        '<p><a href="年度与月度口径核对.csv">含舍入规则的完整核对</a>。差异原因未取得原始修订说明前，不统一断言为修订导致。</p></section>',
        '<section><h2>企业核算与业务状态</h2>',
        table(companies,[('period','年'),('scenario','情景'),('data_nature','资料性质'),('status','计算状态'),('sales_opportunity','销售机会'),('capacity_gap','能力缺口'),('message','条件或缺项')]),
        '<p>生产需要=计划销量+目标期末库存−期初库存−其他净到货；市场机会不等于确定订单。ok表示给定输入算术可计算，教学输入不等于真实业务通过。缺成本、现金流与约束时不宣布最优库存或扩产批准。</p></section>',
        '<section><h2>复核与版本</h2><p>预测状态：年度参照链及月度目标基准已实际运行；完整经济驱动链仍未完成历史验证。业务状态：未取得真实企业参数和容忍度时，只用于条件讨论。</p><p><a href="运行状态.json">运行状态与指纹</a> · <a href="公开数据与来源.json">公开来源台账</a> · <a href="本轮校准输入.json">完整计算输入</a> · <a href="本次用户设置.json">用户覆盖</a></p><p>原始目标、辅助输入、参数和输出分别保留快照。下一次取得新销量、政策、订单或能力数据时重新核验，不把本例幅度设成通用行动阈值。</p><button onclick="window.print()">打印或另存PDF</button></section></main></body></html>']
    return ''.join(chunks)
