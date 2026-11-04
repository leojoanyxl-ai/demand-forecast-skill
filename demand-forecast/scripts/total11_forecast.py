"""Eleven-year total-demand reference, conditional economic sensitivity and independent branch cross-check."""
import copy
import hashlib
import html
import json
import math
from pathlib import Path
import economic_scenarios as econ
import version_backtest as validation

ROOT=Path(__file__).resolve().parents[1]

def calculate(history,evidence,config):
    years=[r['year'] for r in history]
    if years!=list(range(2015,2026)):raise ValueError('主案例要求2015—2025共11个真实年度；2026估计不得放入拟合。')
    latest=history[-1];a=evidence['recent']['2026_ytd'];b=evidence['recent']['2025_ytd']
    anchor={'year':2026,'auto':latest['auto']*a['auto']/b['auto'],'nev':latest['nev']*a['nev']/b['nev']}
    ba=econ.anchors(config);wd=ba['domestic_nev']/(ba['domestic_nev']+ba['nev_export']);wx=1-wd
    slope=validation.slope([(r['year'],econ.logit(r['nev']/r['auto'])) for r in history])
    rows=[]
    for scenario in config['scenarios']:
        for h in (1,2):
            q=validation.v1_total(history,anchor,h)
            neutral=econ.evaluate(config,scenario,h,enabled=[])
            driven=econ.evaluate(config,scenario,h)
            df=driven['domestic_nev']/neutral['domestic_nev'];xf=driven['nev_export']/neutral['nev_export']
            factor=wd*df+wx*xf
            rows.append(dict(year=2026+h,scenario=scenario['name'],history_start=2015,history_end=2025,history_n=11,
                             total_reference=q,domestic_condition_factor=df,export_condition_factor=xf,
                             domestic_weight=wd,export_weight=wx,condition_factor=factor,total_conditioned=q*factor,
                             independent_domestic=driven['domestic_nev'],independent_export=driven['nev_export'],
                             independent_branch_total=driven['total_nev'],crosscheck_gap=q*factor-driven['total_nev'],
                             nature='11年总量参照＋明确结构权重下的条件敏感性；非已验证完整因果预测，分支未强制配平'))
    return rows,dict(years=years,observations=11,logit_slope=slope,anchor=anchor,domestic_weight=wd,export_weight=wx)

def run(output,evidence,config,branch_report):
    original=validation.load(ROOT/'assets'/'v1-frozen.json')
    rows,fit=calculate(original['history'],evidence,config)
    validation.csvwrite(output/'11年总量三情景.csv',rows)
    (output/'11年总量输入快照.json').write_text(json.dumps(original,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'11年总量校准.json').write_text(json.dumps(fit,ensure_ascii=False,indent=2),encoding='utf-8')
    render=lambda rs,cols:validation.table(rs,cols)
    body='<h1>2015—2025年完整历史：需求预测与验证</h1><p>主总量口径：全国厂家新能源销量，含出口，万辆。信息截止2026-11-03；11年真实历史全部参与总量份额趋势，2026全年仅桥接估计。</p>'
    body+=f"<p>11年logit份额斜率为{fit['logit_slope']:.8f}；2026汽车总量桥接{fit['anchor']['auto']:.2f}万辆、新能源桥接{fit['anchor']['nev']:.2f}万辆。不是只用2025一个实际点拟合。</p>"
    body+='<h2>总量主计算与独立分支校验</h2><p>总量参照：以2015—2025总体份额拟合趋势，用2026估计份额锚定，未来总车市沿用原版稳定规模。经济条件敏感性：沿用已登记的收入、成本、补能、海外与政策渠道，计算各分支相对无增量条件的比例，再按2026分支桥接结构权重加权到11年总量参照。这种权重迁移是规划假设，不是新识别的因果系数，不能把它称为已通过回测的精度提升。</p>'
    body+=render(rows,[('year','年度'),('scenario','情景'),('total_reference','11年参照'),('condition_factor','条件乘数'),('total_conditioned','条件总量'),('independent_branch_total','独立分支之和'),('crosscheck_gap','两模型差异')])
    body+='<p>这两套结果都预测同一含出口总量，但使用不同建模结构。独立分支仍由较短的同口径国内与出口历史计算，不按11年总量倒造早期分支、不强制分摊差额。条件总量不是国内分支＋出口分支的另一次“实际”加总；上表差异就是模型分歧，需保留复核。</p>'
    body+='<h2>国内与出口怎样解释</h2><p>完整11年总量不能自动补出2015—2020出口资料。原版未建分支，不能伪造其分支回测。此前2024→2025参照链国内高估136.81万辆、出口低估133.10万辆，抵消后总量只差3.71万辆，说明需要检查分支。新的训练内出口候选可以随历史趋势变化，但外层总量和国内误差未必改善，所以仍列为研究候选。</p>'
    body+='<p><a href="分支经济情景与经营核算.html">查看独立分支经济情景与企业条件核算</a>。其中原“国内＋出口”预测不作为11年主总量的强制分配，也不能直接据此批准产能。企业实际订单、成本、份额和风险容忍度仍需补齐。</p>'
    body+='<h2>历史验证与2026估计</h2><p><a href="版本验证/版本横向回测与分支诊断.html">打开第一版／改进版同起点比较、多年度与月度验证、全年桥接检查</a>。原版总量在共同2023—2025目标年的一年期WAPE约3.16%，V2参照链约5.29%；不能宣称整体精度提高。11年总量参照的历史得分不验证其新增经济条件乘数。</p>'
    body+='<p>未来2026Q4可以按统计方法预测补齐，已单独保存；没有2026全年实际，所以它不参与回测评分。月度滚动12月窗口可以包含已公布的2026月份，仍不代表2026日历全年实际。</p>'
    body+='<h2>这次怎样用于经营计划</h2><p>建议将11年总量用作行业规模参考，将国内、出口和两模型分歧用于销售结构与风险校验。理由是更长总量历史能检验扩散趋势稳定性，而出口增长与国内需求可能分化。适用条件是实际发布口径、政策和企业约束与输入相符。风险是趋势外推、2026桥接、外部参数迁移和结构权重都可能失效；没有实际数据支持时给条件规则，不编造订单或最优产能。</p>'
    page='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>11年历史需求预测与验证</title><style>body{font:16px/1.85 Microsoft YaHei,sans-serif;background:#f3f6f8;color:#20384d;margin:0}main{max-width:1200px;margin:auto;padding:32px 20px 80px}h2{border-top:1px solid #cadbe4;padding-top:20px;margin-top:32px}.scroll{overflow:auto;background:white}table{border-collapse:collapse;min-width:920px;width:100%}td,th{padding:12px;border-bottom:1px solid #dce5ec;text-align:left}th{background:#203e55;color:white}a{color:#087f89}</style><main>'+body+'</main></html>'
    (output/'需求预测与经营预案.html').write_text(page,encoding='utf-8')
    return dict(primary_history_rows=11,primary_history_period='2015—2025',fit=fit,forecast_status='总量参照与条件敏感性已重算；新增乘数及完整情景未经因果历史验证')
