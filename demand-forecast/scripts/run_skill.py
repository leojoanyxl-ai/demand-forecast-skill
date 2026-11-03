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
    args = parser.parse_args()
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
    print(json.dumps(status, ensure_ascii=False, indent=2)); print(str(report))
    if args.open:
        webbrowser.open(report.resolve().as_uri())


if __name__ == '__main__':
    main()
