"""Build reporting material and portable ZIPs from the actual shipped outputs."""
import csv
import hashlib
import html
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def inline(text):
    value = html.escape(text)
    value = re.sub(r'`([^`]+)`', r'<code>\1</code>', value)
    value = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', value)
    value = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', value)
    return value


def render_markdown(text):
    result = []; table = []; code = []; in_code = False
    def flush_table():
        if not table: return
        cells = [line.strip().strip('|').split('|') for line in table]
        header = cells[0]; rows = cells[2:]
        result.append('<div class="table"><table><thead><tr>'+''.join('<th>'+inline(c.strip())+'</th>' for c in header)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+inline(c.strip())+'</td>' for c in row)+'</tr>' for row in rows)+'</tbody></table></div>')
        table.clear()
    for line in text.splitlines():
        if line.startswith('```'):
            if in_code:
                result.append('<pre><code>'+html.escape('\n'.join(code))+'</code></pre>'); code=[]
            in_code = not in_code; continue
        if in_code: code.append(line); continue
        if line.startswith('|'): table.append(line); continue
        flush_table()
        if not line.strip(): continue
        if line.startswith('### '): result.append('<h3>'+inline(line[4:])+'</h3>')
        elif line.startswith('## '): result.append('<h2>'+inline(line[3:])+'</h2>')
        elif line.startswith('# '): result.append('<h1>'+inline(line[2:])+'</h1>')
        elif line.startswith('- '): result.append('<p class="bullet">• '+inline(line[2:])+'</p>')
        else: result.append('<p>'+inline(line)+'</p>')
    flush_table()
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>行业需求预测Skill汇报说明</title><style>body{margin:0;background:#f4f6f8;color:#21364c;font:16px/1.85 "Microsoft YaHei",sans-serif}main{max-width:1080px;margin:auto;padding:40px 24px 80px}h1{font-size:34px}h2{margin-top:40px;border-top:1px solid #cbd7e2;padding-top:20px}h3{color:#067780}.table{overflow:auto;background:#fff}table{border-collapse:collapse;width:100%;min-width:580px}td,th{padding:12px;border-bottom:1px solid #dae3ea;text-align:left;vertical-align:top}th{background:#24425c;color:white}code{font:14px/1.6 Consolas,monospace;background:#e8eef2;padding:2px 4px}pre{overflow:auto;background:#e8eef2;padding:16px}a{color:#067780}.bullet{margin:8px 0}@media(max-width:600px){main{padding:20px 16px}h1{font-size:26px}}</style><main>'+''.join(result)+'</main></html>'


def generate_docs():
    docs = ROOT/'docs'; docs.mkdir(exist_ok=True)
    nev = ROOT/'运行结果'/'新能源汽车'; abs_dir = ROOT/'运行结果'/'ABS'
    ns = json.loads((nev/'运行状态.json').read_text(encoding='utf-8'))
    ass = json.loads((abs_dir/'运行状态.json').read_text(encoding='utf-8'))
    checks = read_csv(abs_dir/'ABS回测汇总.csv')
    forecast = read_csv(abs_dir/'ABS年度三情景.csv')
    nchecks = read_csv(nev/'回测汇总.csv')
    methods = [r for r in checks if r['method']=='adaptive' and (r['lead_start']!='1' or r['horizon'] in ('12','24'))]
    abs_metrics = '\n'.join('|'+ '|'.join([r['lead_start']+'—'+r['lead_end'], '规模' if r['target']=='volume' else '项目数', r['origins'], f"{float(r['wape']):.2%}",f"{float(r['monthly_wape']):.2%}", f"{float(r['bias']):,.2f}"])+'|' for r in methods)
    abs_forecasts = '\n'.join(f"|{r['scenario']}|{r['year']}|{float(r['volume']):,.2f}|{float(r['projects']):,.2f}|" for r in forecast)
    branch = [r for r in nchecks if r['method']=='需求参照链' and r['h']=='1']
    branch_metrics = '\n'.join(f"|{r['market']}|{float(r['wape']):.2%}|{float(r['bias']):+.2f}|{r['n']}|" for r in branch)
    text = f'''# 行业需求预测与经营计划助手：汇报说明

这是一个由任务规则、行业适配器、来源数据、参数设置、计算程序和验证输出组成的Skill。最终交付已实现新能源汽车与ABS两条可运行路径，信息截止2026年11月3日。它支持经营判断，尚未获得真实企业的业务验收。

## 1. 谁在何时做什么决策

|模块|使用Skill的人|形成交易需求的主体|实际决策|目标口径|
|---|---|---|---|---|
|新能源汽车|整车企业战略部门、业务负责人|家庭、企业、车队等购车与付款主体|2026-11-03制定2027销售、库存和产能预案，评估2028风险|厂家口径国内新能源销量＋同口径出口，万辆|
|ABS|管理人战略部门、ABS业务负责人|原始权益人融资、投资者认购、管理人提供服务|制定2027项目承接、人员工时和费用预案，评估2028风险|协会口径新增专项计划备案规模亿元及项目数量只|

使用Skill的战略部门不是购车主体，也不是所有ABS融资者。汽车厂家销量不是终端零售；ABS实际备案活动不是无约束潜在融资需求。行业预测影响的是预算与资源预留，不能直接当作企业确定订单。

## 2. Skill怎样运作

任务卡 → 口径与分层数据核验 → 经济机制与证据表 → 简单基线与历史验证 → 有依据或明确假设的未来路径 → 三情景 → 企业条件核算 → 建议、理由、适用条件与风险。

`SKILL.md`告诉AI何时用哪个模块、缺数怎样降级及哪些结论不能声称；`references`放经济机制和方法；`assets`放运行输入；`scripts`确定性计算与验证。AI负责整理证据、选择适用流程和解释；人负责业务目标、实际企业参数、风险容忍度和最终决策。程序本身不依赖模型接口，AI阅读Skill后可调用程序。

统一入口 `run_skill.py --industry nev` 或 `--industry abs`。两个模块共享任务与证据要求，保留自己的需求定义、模型、参数和经营映射。把汽车参数换成ABS表头不构成行业迁移。

## 3. 新能源汽车怎样计算

同口径国内总车市 `M=汽车总销量−汽车出口`，国内新能源 `D=新能源总销量−新能源出口`，国内份额 `p=D/M`，新能源总销量 `Q=D+X`。出口已在总销量内，不得重复相加。产量和充电桩分别用于校验与机制辅助，不作为汽车需求量相加。

年度参照使用2021—2025年五年，份额以logit趋势描述；国内总市场增长使用历史对数增长中位数。只有五年观察及四个增长观察，这些是混合历史作用的描述性参照，不能解释为独立因果估计。2026全年用相应分支的2025全年×2026年前三季／2025年前三季桥接，不是假装已知2026全年。

国内市场按真实收入、总体购车使用成本与融资条件相对参照的偏离调整；新能源选择按相对TCO、补能和技术条件调整：`D=M×logistic(z)`。TCO包括购价、适用税费、持有期内折现使用成本和残值。固定的代表车型参数只是成本算例，不是全市场实测均价。收入增长既影响预算约束，也可能影响耐用品购买，实际政策、价格和技术作用不能重复叠加到趋势和增量中。

出口分支单列境外需求、相对外币价格、汇率、竞争者价格、退税传递及非价格准入。相对外币报价由人民币报价×每人民币可兑换外币／竞争品价格得到；退税变化先改变可抵税利益，再按覆盖比例、年度生效权重与向价格传递比例影响成本和数量。保留成本不等于实际利润损失。2027已知政策与2028延续条件分开，未核实条件不得称为已宣布政策。

### 为什么补弹性转换

弹性是局部比例响应，logit系数改变的是份额对数胜算，两者不同。补能B只影响选择份额时，`dln(D)/dln(B)=(1−p)γ`。所以销量弹性目标η应转为 `γ=η/(1−p₀)`；固定γ后，在未来更高份额处的隐含销量弹性会下降。原先直接填0.3时，未来基准份额约0.680处实际销量弹性只有约0.096，不能说仍为0.3。

购价弹性还需经过TCO。令 `κN=dln(TCO_N)/dln(购价_N)`、`κI=dln(TCO_I)/dln(购价_I)`，按桥接锚点权重w₀计算总体成本导数κM。市场TCO弹性 `εC=ε市场购价/κM`；选择系数 `β=(εC×w₀−ε新能源购价/κN)/(1−p₀)`。当前γ约0.724、β约2.478，但它们是转换后的模型系数，不能重新当作销量弹性。数值导数使用同一税费与残值设置。

外部文献需核对研究指标、样本、时期、识别方法和迁移范围；OLS相关性、文献量级与压力假设不等于本地因果参数。Armington替代弹性也不能直接当作中国新能源汽车出口需求弹性。原始目标、转换系数及每期隐含弹性已分别导出。

### 数据与验证证据

目前月度目标为{ns['monthly_rows']}个月、四条同口径序列，{ns['monthly_derived_rows']}个月由累计差分得到；另有{ns['auxiliary_observations']}条辅助观察。月度发布值与独立年度口径有{ns['monthly_reconciliation_flags']}项差异超过舍入范围，保留差异，没有强制缩放对齐。数据列很多不等于可用需求样本很多；短序列、存量、产量与公司销量不能全部塞入需求回归。

一年期年度参照链的分支结果如下（单位误差为万辆）：

|分支|WAPE|平均有向误差|起点数|
|---|---|---|---|
{branch_metrics}

总量小误差来自国内高估与出口低估部分抵消，不能据此宣布两个业务分支可靠。该年度验证只有两个不同实际年份；月度基线{ns['monthly_backtest_rows']}条和年度{ns['backtest_rows']}条记录都不是相同数量的独立样本。{ns['grid_rows']}条网格是参数压力计算，不是历史测试或置信区间。当前完整宏观／成本／政策情景链尚未历史验证。

## 4. ABS新增了什么，怎样计算

从用户iFinD工作簿J/K列读取2020-01—2026-09共{ass['history_months']}个月，新增备案规模与项目数共同定义融资活动。存续数量、基础资产存续规模及深交所成交数据作为辅助，不与新增量相加。

这里“项目数”严格取新增备案专项计划数（只），不是分层证券数量、原始权益人数或企业独立承揽项目数；单项工时需按每只计划校准，企业台账还应调整同项目多期发行、工作复用和存续管理负荷。

每月 `规模V=项目数N×单均规模A`，年度单均规模必须用全年规模／全年项目数，不能简单平均各月比值。增长关系为 `(1+gV)=(1+gN)(1+gA)`。

融资选择看ABS发行收益率、增信、服务和结构费用的全成本，与同评级同期限贷款／债券成本比较；资产池、投资者承接和规则决定能否实施。宏观下行既可能增加融资需要，也会降低资产质量、合格资产和认购意愿，净作用不能预设。当前缺可比利差、发行失败／延期、合格资产池、评级期限和企业管线数据，未声称已估计其数量弹性。

基线比较最近月、上年同月、近12月均值和季节项目数×加权单均规模。后三者完整12个月总量代数相同，因此不能把它们称为相互独立的准确性证明。每个外层起点至少48个月，训练内部从24个月开始滚动预测12个月；合计WAPE相同再看训练内月度WAPE。每个起点的选模和预测只读此前数据。

以下是整个训练内选模规则的外层结果，规模误差单位为亿元、数量误差单位为只：

|预测第几个月|目标|重叠起点|合计WAPE|月度WAPE|平均有向误差|
|---|---|---|---|---|---|
{abs_metrics}

与未来1—12个月匹配的简单最近月基线规模WAPE约21.08%，所选规则约11.57%；这只是同一当前数据版本和起点下的回顾比较。第4—15个月匹配2027年提前期、第16—27个月匹配2028年，分别只有19与7个重叠起点，最多可取2与1个不重叠窗口。窗口重叠、原始发布时间未重建、此前已见基线表现，均限制证据力度。不能把它说成19年或7年独立验证。

从2026-09后预测27个月，2026第四季度为桥接估计。2027、2028三情景在基线项目数与单均规模上分别施加明确的规划压力并逐年累乘。利率、宏观和政策未量化时，背景解释不能冒充进入了回归。下表是条件测算，不是官方预测和概率区间：

|情景|年度|新增备案亿元|项目数期望值|
|---|---|---|---|
{abs_forecasts}

企业机会规模=行业规模×企业规模份额，机会项目数=行业数量×数量份额。费用敏感性万元=机会规模亿元×费率×10000，工时=机会项目数×单项工时，缺口=max(所需−可用工时,0)。真实企业输入缺失时给公式；教学模式可演示完整核算，但不是订单、已确认收入、利润或最优编制。

## 5. 理论怎样真正用到判断

|理论或原则|本项目中的用途|证据和边界|
|---|---|---|
|需求与需求量、供需均衡|购价变化、收入变化和交易约束分别解释；ABS备案不是潜在融资意愿|实际交易受供给、资产合格和实现条件约束，不能仅凭销量识别需求曲线|
|收入／价格弹性|用比例响应构建条件偏离，正确转换购价、TCO与份额系数|外部研究迁移和规划目标不是本地识别|
|替代与互补效应|新能源与燃油车相对成本、补能互补；ABS与贷款／债券融资替代|补能内生，融资成本与规模共同决定，需专门识别|
|宏观传导与预算约束|收入和融资影响耐用品购买；经济活动影响应收、资产池和信用风险|净方向、时滞及幅度需数据，不从GDP一个变量机械推出需求|
|跨期选择与政策时点|税费政策可能提前／延后购车，ABS规则可能改变实施时点|时间转移不是全部新增长期需求；2028未知政策保留条件|
|存量流量与派生需求|库存／产能核算与项目／工时核算采用不同边界|ABS存续规模与新增备案、二级成交不能混加|
|边际决策与不可逆投资|分阶段预留产能、人力或投资，设置触发条件|未取得成本、现金流、约束和损失函数时不声称最优方案|

## 6. 从最初版到现在

原始小组已有数据、预测CSV、快照和提示词。随后先增加可操作运行和扩大回测，再规范任务卡与企业条件核算；接着把国内与出口拆开，引入前瞻收入、相对成本、补能、政策及海外机制。对照同学版本后强化需求主体、分层输入和证据时间。用户又升级数据与参数，我们复核后增加月度入口、弹性转换、分支抵消诊断和唯一参数源。最后将ABS从可行性论证落到实际适配器、验证、工时核算与统一项目维护。详细变化见[迭代记录](../CHANGELOG.md)。

这不是从一开始就有的完整因果模型。没有事后伪造普通AI初版、真实同学试用、人工贡献比例或早期Git提交。今后的修改可用真实Git提交和验证记录追踪。

## 7. 对照老师评分表怎样展示

|评分维度|展示证据|课堂操作|
|---|---|---|
|问题定义与决策价值|两个任务卡、使用者与需求主体、可改变的安排|先说谁在2026-11-03决定什么|
|经济学分析逻辑|D=M×p、Q=D+X、弹性转换、ABS成本替代与数量×规模|讲清一条传导链与其缺失数据|
|数据设计与完整性|来源、单位、期间、公开／内部、实际／估计／假设、缺口降级|展示CSV和来源JSON，不把列数当样本量|
|AI流程与人机分工|统一入口、离线重跑、测试、企业缺数模式|现场跑ABS或改一个教学情景再运行；实际同学试用仍待做|
|结果与决策可用性|建议＋理由＋适用条件＋风险，预测验证与业务状态分列|用一个触发条件解释为何改变产能或人员预留|

## 8. 尚有哪些不足，下一步补什么

- 新能源月度57个月仍不算长，4个月为差分，年／月差异尚未逐项取得修订说明；年度参照只有5年。优先补同口径更长月度原始值和每月发布时间，而非添加更多不相干指标。
- 新能源收入、价格、补能和出口参数含外部迁移与压力设定，未来驱动路径也有假设。价格、补能具有内生性；需要目的地、车型、地区和原始发布版本，再尝试受约束动态回归或有识别设计的估计，不直接堆VAR。
- ABS样本覆盖81个月，但真实首次发布版本、具体政策变化、资产分层、成本／利差、合格资产池和投资者资料不完整。新增备案同时受供需约束，不是纯需求曲线；宏观与利差尚未量化。
- 两模块都缺真实企业份额、订单／管线、库存／工时、成本和错估损失，尚未业务验收。教学模式数值齐全不代表取得这些企业事实。
- 没有给无依据情景概率、最优安全库存、最优产能和扩张投资回报。需要提前期、预测误差分布、产能约束和增量现金流后再做经营优化。
- 其他行业尚需独立适配：乳制品补销量与渠道库存并处理1—2月合并；粮食补食用／饲用／工业用途、贸易与库存；原油补炼厂投入、下游耗用、贸易与库存。需求定义、单位、基准和验证必须一起改变。

## 9. 你亲自怎样做回测

先保留当前数据和输出。打开菜单选择行业或按README命令运行一个新输出目录；查看逐条回测的起点、当时训练长度、预测期间、实际值和误差。用几条样本手算 `误差=预测−实际`、`WAPE=Σ绝对误差／Σ实际`。ABS同时看规模与项目数、合计与月度；新能源同时看国内与出口。不要把看过结果再挑出的最好方法称独立验证。

接着在副本中调整未来情景并重跑。未来路径变化应改变未来条件预测，但不应把历史实际值改成更贴合模型。真实后续月份发布后保存当时预测快照再评分，逐步积累真正前瞻证据。课堂演示有完整运行记录，但实际同学用新数据独立试用需另行记录。

数据依据：[中国证券投资基金业协会简报目录](https://www.amac.org.cn/sjtj/tjbg/zczqh/)；本项目[ABS源记录](../demand-forecast/assets/abs-source.json)、[新能源汽车证据](../demand-forecast/assets/nev-evidence.json)与[弹性唯一输入](../demand-forecast/assets/economic-parameters.json)。协会目录核实了简报发布日期，未替代用户工作簿全部数值核验。
'''
    (docs/'汇报说明.md').write_text(text, encoding='utf-8')
    (docs/'汇报说明.html').write_text(render_markdown(text), encoding='utf-8')
    lecture = '''# 课堂讲稿与答辩准备

建议8—10分钟，下面是可直接调整的讲述顺序；数值以本次自动生成的汇报说明和报告为准。

## 第1分钟：任务与业务价值

我们的使用者是业务负责人和战略部门。新能源汽车案例在2026年11月3日制定2027年的销售与产能预案，并评估2028年需求风险。战略部门是工具使用者，家庭、企业和车队才是购车主体。预测会改变销售预算、可调整产能和库存安排，行业总销量不能直接当成某家企业订单。

## 第2—3分钟：经济机制

我们先把国内需求和出口分开。国内新能源销量是国内总市场乘新能源选择份额；出口受海外需求、外币相对价格、政策和准入影响，再加总。国内的收入与预算、购置及使用成本、补能条件会影响总市场和选择，不能把所有背景因素都写成已量化。

关键修正是弹性转换：logit系数改变份额的对数胜算，销量弹性还要乘一减份额。因此补能销量弹性不能直接填为同数值的logit系数，购价还需要通过TCO导数转换。我们保留外部文献、迁移限制和压力假设，未把教学参数说成实证估计。

## 第4分钟：数据与验证

我们有五年年度参照、57个月月度目标及辅助数据，但序列性质各不相同。产量不是需求，充电桩不是销量。四个月是累计差分，有12项年／月汇总差异，保留了来源和未解决的问题。

年度总量回测WAPE约1.32%，国内约7.07%，出口约36.21%，这是高估与低估抵消的例子，所以总量成绩不能代表两个业务分支可靠。网格的几千条记录是参数压力计算，不是几千个历史样本。

## 第5—6分钟：ABS迁移与验证

迁移到ABS以后，我们改变了需求定义：新增备案融资规模是融资活动代理。原始权益人融资、投资者认购、管理人提供服务，三者不同。规模等于项目数乘平均项目规模，企业计划对应项目承接、费用和工时，不再套汽车库存和产能公式。

经济机制比较ABS与贷款、债券的同期限全成本，还要看合格资产池与投资者承接。宏观下行可能增加融资需要，也会恶化资产质量和认购，不能机械认为一定增加ABS。由于缺少配套利差与资产池数据，我们没有虚构这些因素的弹性。

已接入81个月的规模和数量，并在每个预测起点只用此前数据，在训练内部选模。12个月规模合计误差约11.57%，最近月基线约21.08%，但月度误差仍超过20%。又按未来第4—15月、第16—27月检查与2027、2028相近的提前期；远期只有7个重叠起点，证据有限。这些是当前版本的回顾验证，不是完全按当年可得版本的实时回放。

## 第7分钟：现场演示

打开主目录README，双击行业菜单，选择ABS。默认真实企业输入为空时仍正常给出行业分析，并为企业核算提供待补公式。再运行教学模式，展示假设份额、收费与工时怎样改变资源缺口。所有教学值都有标记，不能说成某公司的真实经营数据。

可在副本中把ABS悲观项目增速从负10%改为负15%，保留设置后跑到新输出目录；解释变化是更严的规划压力，而非新估计的政策效应。示例路径与报告来自同一设置，避免手改文字与计算不一致。

## 第8—9分钟：改进与不足

最初有提示词、预测和数据；后来增加可运行流程与扩大回测，再规范任务与口径，拆国内／出口，加入前瞻经济机制，统一月度入口、弹性与网格。最后形成两个可执行行业模块、一个Skill入口和可维护的GitHub项目。

我们做到计算可复现与证据状态明确，但完整经济情景没有因果验证，也没有真实企业业务验收。下一步优先补发布版本、分层价格和目的地数据；ABS补融资成本、合格资产池、投资者和企业管线，再做真实前瞻跟踪。业务负责人最终决定风险取舍，AI不能替代。

## 老师可能追问

|问题|可答的要点|
|---|---|
|你们真正用了经济学，还是只跑时间序列？|需求主体、国内与出口、预算约束、TCO替代、弹性转换和ABS融资替代直接影响模型与条件；缺数据的机制明确不声称已量化|
|模型为什么不全部使用回归或VAR？|有效样本和识别不足，先用可比较基线；只有新方法在时间顺序验证中稳定增益才增加复杂度|
|为什么总量预测好，仍说不可靠？|国内高估与出口低估相互抵消；经营决策分别面对两条线，需单独误差|
|ABS真的已经验证了吗？|统计基线和训练内选模规则进行了当前版本回顾比较；利差／政策情景、历史发布日期实时回放与企业业务验收没有通过证明|
|为什么有三种方法年度结果相同？|完整12个月合计都等于过去12个月规模，是代数性质；月度形状才有区别，不能冒充多模型独立印证|
|数据完整权威吗？|保留来源、单位、指纹与核验层级；官方目录与部分官方原值已核，ABS用户导出81个月并未逐条核官方PDF，仍有缺口|
|其他同学能运行吗？|运行所需输入随项目提供，标准库离线可运行；程序已实际重跑，真实同学新案例独立试用还应单独记录|
|没有公司数据还能做什么？|做行业情景和条件核算，输出数据需求与触发规则；不编造份额、订单、管线和成本|
|为什么2027预测需要15个月提前期？|最后实际月是2026年9月，2026第四季度尚需桥接；2027年1—12月是之后第4—15月|
'''
    (docs/'课堂讲稿.md').write_text(lecture, encoding='utf-8')
    (docs/'课堂讲稿.html').write_text(render_markdown(lecture), encoding='utf-8')
    (ROOT/'开始使用.html').write_text('''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>开始使用行业需求预测Skill</title><style>body{margin:0;background:#f3f6f8;color:#213b53;font:17px/1.85 "Microsoft YaHei",sans-serif}main{max-width:1000px;margin:auto;padding:40px 24px}h1{font-size:36px}h2{margin-top:36px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:18px}.card{background:white;border:1px solid #d4e0e8;border-radius:12px;padding:24px}.button{display:block;background:#176f81;color:white;text-decoration:none;padding:12px 18px;border-radius:7px;margin-top:16px}a{color:#076d81}small{font-size:14px;color:#526b7d}.note{background:#e3eff1;padding:16px;border-left:4px solid #176f81}@media(max-width:600px){main{padding:20px 16px}h1{font-size:28px}}</style><main><p>Industry Demand Forecasting &amp; Planning Assistant</p><h1>行业需求预测与经营计划助手</h1><p>一个Skill，新能源汽车与ABS两个可运行模块。课堂信息截止：2026年11月3日。</p><div class="grid"><section class="card"><h2>新能源汽车</h2><p>国内与出口分开预测，解释收入、相对成本、补能、政策与海外条件，再做销售与产能条件核算。</p><a class="button" href="运行结果/新能源汽车/需求预测与经营预案.html">查看需求与经营报告</a><small><a href="教学演示/新能源汽车/需求预测与经营预案.html">查看教学企业参数演示</a></small></section><section class="card"><h2>ABS融资活动</h2><p>按项目数×单均规模解释新增备案活动，比较历史基线，并做项目机会、费用和工时条件核算。</p><a class="button" href="运行结果/ABS/ABS融资活动预测与业务预案.html">查看ABS报告与验证</a><small><a href="教学演示/ABS/ABS融资活动预测与业务预案.html">查看教学企业参数演示</a></small></section></div><h2>自己运行三步</h2><ol><li>在下载后的 demand-forecast 文件夹中，双击“选择行业运行.cmd”。其他系统按README中的Python命令运行。</li><li>选择行业。普通模式保留真实企业数据缺口；教学模式用明确标记的假设演示核算。</li><li>报告会自动打开，每次结果保存到新的“运行记录”目录；同时生成输入快照、回测明细、汇总和运行状态。</li></ol><p>修改前先复制一份输入。新能源汽车弹性、未来路径和企业参数分别维护；ABS场景在 abs-settings.json 中修改。不要只手改报告数字。</p><div class="note">能计算，不代表所有经济参数都被实证识别，也不代表企业已批准方案。缺少真实企业输入时给条件核算，教学数值不能当作订单或成本事实。</div><h2>课堂汇报与维护</h2><p><a href="docs/汇报说明.html">阅读计算原理、逐步改进、经济学理论和不足</a></p><p><a href="docs/课堂讲稿.html">阅读8—10分钟讲稿与答辩准备</a></p><p><a href="docs/验证记录.md">查看已完成的验证记录</a> · <a href="README.md">完整使用说明</a> · <a href="demand-forecast/SKILL.md">Skill入口</a></p><p><a href="https://github.com/leojoanyxl-ai/demand-forecast-skill">GitHub私有仓库：后续修改入口</a></p></main></html>''', encoding='utf-8')


def source_files():
    excluded = {'.git','dist','核验与构建','__pycache__','运行记录'}
    return sorted(p for p in ROOT.rglob('*') if p.is_file() and not any(x in excluded for x in p.relative_to(ROOT).parts))


def build():
    generate_docs()
    dist = ROOT/'dist'; dist.mkdir(exist_ok=True)
    manifest = []
    for path in source_files():
        manifest.append({'path':path.relative_to(ROOT).as_posix(),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    (dist/'交付文件清单.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    for name, files, prefix in [('demand-forecast-skill-final.zip', source_files(), Path('demand-forecast-skill')),
                                ('demand-forecast-skill-only.zip', sorted(p for p in (ROOT/'demand-forecast').rglob('*') if p.is_file() and '__pycache__' not in p.parts and '运行记录' not in p.parts), Path())]:
        with zipfile.ZipFile(dist/name, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in files:
                archive.write(path, str(prefix/path.relative_to(ROOT)))
        print(name, (dist/name).stat().st_size, hashlib.sha256((dist/name).read_bytes()).hexdigest())


if __name__ == '__main__':
    build()
