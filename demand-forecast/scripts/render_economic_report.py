import html
import json


def _render_prototype(config,anchor,rows,contributions,variants):
    e=html.escape
    parameters=''.join(f'<tr><td>{e(v["meaning"])}</td><td>{v["value"]}</td><td>{e(v["evidence"])}</td></tr>' for v in config['parameters'].values())
    tables=''.join(f'<tr><td>{r["year"]}</td><td>{e(r["scenario"])}</td><td>{r["domestic_auto"]:,.1f}</td><td>{r["domestic_share"]:.1%}</td><td>{r["domestic_nev"]:,.1f}</td><td>{r["nev_export"]:,.1f}</td><td>{r["total_nev"]:,.1f}</td></tr>' for r in rows)
    source_notes=''.join('<li>'+e(s)+'</li>' for s in config['source_notes'])
    payload=json.dumps(dict(rows=rows,contributions=contributions,variants=variants,scenarios=config['scenarios']),ensure_ascii=False).replace('</',r'<\/')
    return '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>行业需求的经济机制与前瞻情景</title><style>
*{box-sizing:border-box}body{margin:0;background:#f4f6f8;color:#193047;font:16px/1.75 "Microsoft YaHei",sans-serif}main{max-width:1160px;background:white;margin:30px auto;padding:34px 42px}h1{font-size:29px;margin:6px 0 14px}h2{font-size:22px;margin:30px 0 10px}h3{font-size:18px}.lead{color:#326290;font-size:14px}.notice{background:#fff4dc;border-left:4px solid #ba7a00;padding:12px 18px}.fact{background:#eef5fb;padding:14px 18px}.scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:14px}td,th{border-bottom:1px solid #dce4ed;padding:10px 12px;text-align:left}th{background:#eef2f7}td.num{text-align:right;font-variant-numeric:tabular-nums}select,button{font:inherit;padding:7px 11px;margin:4px 10px 4px 0}p{margin:10px 0}a{color:#2161a0}.small{font-size:14px;color:#52697b}.controls{display:flex;flex-wrap:wrap;gap:12px;align-items:center}.calc{border-left:3px solid #2764a0;padding-left:16px}details{margin:24px 0}summary{cursor:pointer;font-weight:600}@media(max-width:650px){main{margin:0;padding:22px 16px}h1{font-size:25px}}@media print{main{margin:0;padding:0}.controls,button{display:none}body{background:white}}
</style></head><body><main><div class="lead">业务负责人 / 战略部门 · 全国厂家新能源销量 · 2027—2028</div><h1>未来需求为什么会变，经营安排如何跟着变</h1>
<p class="notice">这是已运行的经济驱动条件原型。已知销量、收入和制度安排有官方依据；未来收入、车价、海外需求、代表车型成本和行为系数含明确的规划假设。下列数量用于检验传导与情景，不是官方预测或已经识别的政策因果效应。</p>
<h2>1. 当前市场需要同时解释的三件事</h2><div class="fact"><p>2026年前三季度，同口径国内新能源厂家销量同比约下降10.6%，但其在国内汽车中的份额由48.8%升至56.2%；新能源出口同比约增长127.9%。国内总市场收缩、技术替代加强和出口扩张同时发生。</p><p>同期居民实际收入增长4.4%；9月小汽车价格同比下降1.7%，交通工具能源价格同比上涨14.9%。收入增长、车价变化并不能单独解释销量，还须核对融资、存量更新、政策时点、相对油电成本和出口渠道。</p></div><p><a href="已核验驱动事实.md">查看官方事实、发布日期和用途限制</a>。小汽车CPI不是新能源/燃油车各自的成交价格，能源大类也不是油电成本差。</p>
<h2>2. 经济机制怎样进入计算</h2><div class="scroll"><table><thead><tr><th>渠道</th><th>实际输入</th><th>进入位置与经营含义</th></tr></thead><tbody>
<tr><td>宏观购买力</td><td>未来实际收入路径、收入弹性；另列授信约束</td><td>改变国内汽车总市场M；影响销售预算的总盘子</td></tr>
<tr><td>总体购车成本</td><td>实际成交价、税费、使用费用、残值及持有期</td><td>改变汽车总体成本指数；不把成本下降全部等同利润或销量</td></tr>
<tr><td>新能源与燃油车替代</td><td>两类车广义成本之比，相对明确参照路径的新变化</td><td>改变国内新能源份额p；D=M×p</td></tr>
<tr><td>补能与新技术</td><td>未在成本中货币化的便利性，以及额外非价格技术条件</td><td>只叠加偏离参照的新变化，不把既有替代趋势完整再加一遍</td></tr>
<tr><td>海外市场与价格</td><td>海外需求、相对到岸价、汇率/竞品价和非价格准入</td><td>单独计算出口X；不把国内优惠施加给出口</td></tr>
<tr><td>已公告出口退税变化</td><td>13%降至9%，2027年4月生效；适用比例、月内权重和价格传递率另设</td><td>先算退税收入损失，分别影响价格和厂商留存成本，再改变X</td></tr>
<tr><td>购置税与跨期购买</td><td>2027仍按减半；2028接续作为条件分支；纯跨期转移另列</td><td>税费进入成本；有依据的购买转移同时调整国内总市场和新能源销量</td></tr>
</tbody></table></div>
<h2>3. 切换情景，检查每个因子</h2><div class="controls"><label>情景 <select id="scenario"><option>悲观</option><option selected>基准</option><option>乐观</option></select></label><label>年份 <select id="year"><option>2027</option><option>2028</option></select></label></div><div id="active" class="calc" aria-live="polite"></div><div class="scroll"><table><thead><tr><th>变化条件</th><th>本情景路径</th><th>性质</th></tr></thead><tbody id="drivers"></tbody></table></div>
<h2>4. 从国内市场与出口得到行业需求</h2><div class="scroll"><table><thead><tr><th>年份</th><th>情景</th><th>国内汽车M</th><th>国内新能源份额p</th><th>国内新能源D</th><th>新能源出口X</th><th>合计D+X</th></tr></thead><tbody>'''+tables+'''</tbody></table></div><p class="small">数量单位为万辆；成本是代表乘用车示例，正式全行业应用前须校准车型结构及代表性。2026锚点分别桥接国内汽车、国内新能源和新能源出口，沿用2025年年内分布；不是2026全年实际。__HISTORY_NOTE__</p>
<h2>5. 一个因素改变，结果是否真的改变</h2><label>只改基准中的一项 <select id="experiment"></select></label><div id="sensitivity" aria-live="polite"></div><p class="small">敏感性固定其他输入。退税全部由厂商吸收时，价格渠道的销量压力减小，但利润或现金回收压力更大；销量结果改善不等于企业收益改善。</p>
<details><summary>查看本情景的固定顺序贡献分解</summary><div class="scroll"><table><thead><tr><th>依次纳入的渠道</th><th>数量增量（万辆）</th><th>加入后的行业量</th></tr></thead><tbody id="contributions"></tbody></table></div><p class="small">从参照份额趋势与市场锚点开始，按固定顺序依次打开渠道。该差额包含交互和假设影响，不是唯一因果贡献；换顺序可能改变分项归属。</p></details>
<h2>6. 面向负责人和战略部门的行动</h2><div class="scroll"><table><thead><tr><th>建议</th><th>理由</th><th>适用条件</th><th>风险与复核</th></tr></thead><tbody>
<tr><td>国内销量预算分别检查汽车总盘子与新能源替代</td><td>份额升和销量降可以同时发生，不能仅按渗透趋势加码</td><td>以真实订单、目标客群和企业份额验证</td><td>持续看国内零售/上险、融资和渠道库存；厂家批发不等于终端</td></tr>
<tr><td>出口预算同时评估量、价格和单车利润</td><td>退税变化可以被利润吸收或转嫁给买家，数量反应不同</td><td>取得适用HS比例、合同报价、毛利及传递能力</td><td>政策实施前后核实目的地、汇率和交期；不要把退税少4个百分点当销量少4%</td></tr>
<tr><td>把2028政策接续作为预算分支</td><td>已核公告覆盖到2027年底，后续未核实；不同接续改变持有成本</td><td>待正式政策、车型资格和补贴条件明确后更新</td><td>留意提前购买和后续回落；没有依据时不填抢购数量</td></tr>
<tr><td>采用可调整排产并对加班/外协询价</td><td>宏观、成本与出口条件会改变需求，年度点值不保证峰值交付</td><td>补企业份额、库存、有效产能、毛利和成本</td><td>固定扩产还须项目现金流、建设期和不可逆性检验</td></tr>
</tbody></table></div>
<details><summary>参数证据与参照路径</summary><p>__PARAMETER_NOTE__成本使用代表乘用车示例，不是已观测行业均价；全行业应用前需验证车型结构与代表性。</p><div class="scroll"><table><thead><tr><th>参数含义</th><th>值</th><th>证据状态</th></tr></thead><tbody>'''+parameters+'''</tbody></table></div><ul>'''+source_notes+'''</ul></details>
<p><a href="本次情景输入.json">查看本次输入与参数</a> · <a href="经济情景结果.csv">完整结果</a> · <a href="单因素敏感性.csv">敏感性明细</a> · <a href="输入与锚点.json">本次输入与锚点</a></p><p class="small">此页面展示前瞻机制与条件计算。历史回测作为方法检查，不能代替收入、价格、政策和经营条件的分析；现有旧模型回测结果也不代表这个新增模型已经回测。</p><button type="button" onclick="window.print()">打印或另存PDF</button>
<script>const DATA='''+payload+''';const $=s=>document.getElementById(s);const n=v=>Number(v).toLocaleString('zh-CN',{maximumFractionDigits:1});const pct=v=>(100*v).toFixed(1)+'%';
function show(){const name=$('scenario').value,year=Number($('year').value),i=year-2027;const r=DATA.rows.find(x=>x.scenario===name&&x.year===year),s=DATA.scenarios.find(x=>x.name===name);
$('active').textContent=`国内汽车 ${n(r.domestic_auto)} 万辆 × 新能源份额 ${pct(r.domestic_share)}，得到国内新能源 ${n(r.domestic_nev)} 万辆；加出口 ${n(r.nev_export)} 万辆，合计 ${n(r.total_nev)} 万辆。`;
const d=[['实际收入当年增速',pct(s.real_income_growth[i]),'未来规划路径，不是官方预测'],['新能源实际车价当年变化',pct(s.nev_real_price_growth[i]),'代表车型/成本指数假设'],['燃油车实际车价当年变化',pct(s.ice_real_price_growth[i]),'替代品条件假设'],['新能源广义成本',n(r.nev_cost_real)+'元','含价格、购置税、使用费用及残值的示例'],['新能源购置税减免比例',pct(s.nev_tax_relief[i]),year===2027?'已公告减半，示例车型符合资格':'接续或退出条件，未核实实际2028政策'],['补能便利指标当年增长',pct(s.infrastructure_growth[i]),'未来路径；仅算未货币化便利偏离参照'],['海外需求当年增长',pct(s.foreign_demand_growth[i]),'未来规划路径'],['出口同币值报价当年变化',pct(s.export_quote_real_growth_before_rebate[i]),'报价路径；先加固定退税损失再换算相对价'],['每人民币可换外币当年变化',pct(s.fx_foreign_per_rmb_growth[i]),'正值表示人民币升值；0是本情景不变假设'],['海外竞品价格当年变化',pct(s.foreign_competitor_price_growth[i]),'同一海外货币和产品比较；0是不变假设'],['政策前相对到岸价格指数',r.export_price_before_rebate_index.toFixed(4),'报价×汇率÷海外竞品价；不在其他位置重复加汇率冲击'],['退税加权年税率',pct(r.annual_rebate_rate),'制度13%→9%；2027受影响权重9/12是均匀月份假设'],['退税适用出口比例',pct(r.eligible_fraction),'待按HS/产品结构核实'],['出口价格传递率',pct(r.price_pass_through),'规划假设，余下由厂商吸收'],['退税变化后的平均价格倍数',r.average_rebate_price_factor.toFixed(4),'不是税率直接转换成销量'],['按基准权重的平均单台留存成本',n(r.policy_cost_retained_per_average_unit_real)+'元','政策前覆盖/月份权重下的示例增量；非实际单车或总利润估计'],['纯跨期购买转移',n(s.pure_timing_transfer_10k[i])+'万辆','本例未估计，默认输出未包含该转移']];
$('drivers').innerHTML=d.map(a=>'<tr>'+a.map(v=>'<td>'+v+'</td>').join('')+'</tr>').join('');
$('contributions').innerHTML=DATA.contributions.filter(x=>x.scenario===name&&x.year===year).map(x=>`<tr><td>${x.label}</td><td class="num">${x.incremental_10k>=0?'+':''}${n(x.incremental_10k)}</td><td class="num">${n(x.cumulative_total)}</td></tr>`).join('');sensitivity();}
function sensitivity(){const year=Number($('year').value),x=DATA.variants.find(x=>x.experiment===$('experiment').value&&x.year===year);if(x)$('sensitivity').textContent=`${year}年：国内新能源 ${n(x.domestic_nev)} 万辆，出口 ${n(x.nev_export)} 万辆，合计 ${n(x.total_nev)} 万辆；比基准${x.difference_from_base>=0?'增加':'减少'} ${n(Math.abs(x.difference_from_base))} 万辆。`;}
[...new Set(DATA.variants.map(x=>x.experiment))].forEach(v=>{const o=document.createElement('option');o.value=v;o.textContent=v;$('experiment').appendChild(o);});$('scenario').addEventListener('change',show);$('year').addEventListener('change',show);$('experiment').addEventListener('change',sensitivity);show();</script></main></body></html>'''



def render(config,anchor,rows,contributions,variants):
    page=_render_prototype(config,anchor,rows,contributions,variants)
    history=config['domestic_share_reference_history']
    note=f"份额参照来自{history[0]['year']}—{history[-1]['year']}共{len(history)}个年度国内份额；描述性趋势不能视为稳定长期规律。"
    page=page.replace('__HISTORY_NOTE__',html.escape(note))
    page=page.replace('__PARAMETER_NOTE__','本项目未从连续样本识别行为系数；原始弹性目标与转换后模型系数逐项区分，见主报告的弹性映射。')
    return page
