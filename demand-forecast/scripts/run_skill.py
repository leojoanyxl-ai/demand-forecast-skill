"""Shared executable entry point; each industry retains its own economic/statistical adapter."""
import argparse
from datetime import datetime
from pathlib import Path
import json
import webbrowser

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--industry', required=True, choices=('nev', 'abs'))
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--demo', action='store_true', help='Use explicitly labeled teaching company assumptions')
    parser.add_argument('--open', action='store_true')
    parser.add_argument('--company', type=Path)
    parser.add_argument('--settings', type=Path)
    parser.add_argument('--monthly', type=Path)
    parser.add_argument('--validate', action='store_true', help='Run frozen-version and branch validation for the bundled NEV case')
    args = parser.parse_args()
    if args.validate and args.industry!='nev':parser.error('--validate用于新能源汽车版本比较；ABS已有专属回测。')
    if args.validate and any((args.settings,args.monthly,args.company)):
        parser.error('版本比较使用冻结案例；自定义情景请另开运行，避免误称同输入比较。')
    output = args.output_dir or ROOT/'运行记录'/(args.industry+'_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    if args.industry == 'abs':
        import abs_forecast as engine
        company = args.company or ROOT/'assets'/('abs-company.example.json' if args.demo else 'abs-company.json')
        status = engine.run(output, args.monthly, args.settings, company)
        report = output/'ABS融资活动预测与业务预案.html'
    else:
        import run_full as engine
        company = args.company or ROOT/'assets'/('company-input.example.csv' if args.demo else 'company-input.csv')
        status = engine.run(engine.load(ROOT/'assets'/'nev-evidence.json'),
                            engine.load(ROOT/'assets'/'nev-economic-scenario.example.json'), output, company,
                            engine.load(args.settings or ROOT/'assets'/'nev-settings.json'), args.monthly,
                            registry=engine.load(ROOT/'assets'/'economic-parameters.json'))
        report = output/'需求预测与经营预案.html'
        if not any((args.settings,args.monthly,args.company)):
            import version_backtest
            import total11_forecast
            status['version_validation']=version_backtest.run(output/'版本验证')
            branch_report=output/'分支经济情景与经营核算.html'
            report.rename(branch_report)
            status['total11']=total11_forecast.run(output,engine.load(ROOT/'assets'/'nev-evidence.json'),engine.load(output/'本轮校准输入.json'),branch_report)
            status['branch_history_rows']=status['history_rows']
            status['branch_fit']=status['fit']
            status['history_rows']=status['total11']['primary_history_rows']
            status['fit']=status['total11']['fit']
            status['primary_model']='2015—2025完整11年总量参照；经济乘数为条件敏感性；分支独立对照'
            (output/'运行状态.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(status, ensure_ascii=False, indent=2)); print(str(report))
    if args.open:
        webbrowser.open(report.resolve().as_uri())


if __name__ == '__main__':
    main()
