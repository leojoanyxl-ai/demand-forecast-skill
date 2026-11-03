"""Deterministic planning arithmetic; no demand estimation or optimization."""
import argparse
import csv
import math
from pathlib import Path

RATES = ('domestic_service_ratio', 'domestic_share', 'export_service_ratio', 'export_share')
NONNEGATIVE = ('domestic_demand', 'exports', 'opening_inventory', 'target_inventory', 'effective_capacity')
NUMBERS = NONNEGATIVE + RATES + ('other_net_receipts',)
TEXT = ('period', 'scenario', 'quantity_unit', 'data_nature', 'assumption_basis')
RESULTS = ('industry_total', 'domestic_opportunity', 'export_opportunity', 'sales_opportunity',
           'net_production_need', 'conditional_production', 'excess_inventory',
           'capacity_gap', 'capacity_utilization')


def calculate(row):
    result = {key: row.get(key, '') for key in TEXT}
    result.update({key: None for key in RESULTS})
    # Preserve unaffected industry arithmetic when internal planning inputs are missing.
    try:
        domestic = float(row.get('domestic_demand'))
        exports = float(row.get('exports'))
        total = domestic + exports
        if domestic >= 0 and exports >= 0 and all(math.isfinite(v) for v in (domestic, exports, total)):
            result['industry_total'] = total
    except (TypeError, ValueError):
        pass
    missing = [key for key in TEXT + NUMBERS if row.get(key) is None or str(row[key]).strip() == '']
    if missing:
        result.update(status='needs_input', message='Missing: ' + ', '.join(missing))
        return result
    values = {}
    try:
        for key in NUMBERS:
            values[key] = float(row[key])
            if not math.isfinite(values[key]):
                raise ValueError('Non-finite: ' + key)
            if key in NONNEGATIVE and values[key] < 0:
                raise ValueError('Negative: ' + key)
            if key in RATES and not 0 <= values[key] <= 1:
                raise ValueError('Rate outside [0,1]: ' + key)
    except (TypeError, ValueError) as error:
        result.update(status='invalid_input', message=str(error))
        return result
    v = values
    domestic = v['domestic_demand'] * v['domestic_service_ratio'] * v['domestic_share']
    exports = v['exports'] * v['export_service_ratio'] * v['export_share']
    opportunity = domestic + exports
    net_need = opportunity + v['target_inventory'] - v['opening_inventory'] - v['other_net_receipts']
    production = max(0.0, net_need)
    utilization = production / v['effective_capacity'] if v['effective_capacity'] > 0 else None
    result.update(
        industry_total=v['domestic_demand'] + v['exports'],
        domestic_opportunity=domestic, export_opportunity=exports,
        sales_opportunity=opportunity, net_production_need=net_need,
        conditional_production=production, excess_inventory=max(0.0, -net_need),
        capacity_gap=max(0.0, production - v['effective_capacity']),
        capacity_utilization=utilization, status='ok',
        message='Conditional on all sales opportunity converting to planned sales; inventory target is an input, not optimized. Capacity utilization field is required production/capacity load; values above 1 indicate a gap, not realizable utilization.'
    )
    if utilization is None:
        result['message'] += ' Zero effective capacity: utilization is not applicable.'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error('Input and output must differ.')
    with args.input.open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        missing_headers = set(TEXT + NUMBERS) - set(reader.fieldnames or [])
        if missing_headers:
            parser.error('Missing columns: ' + ', '.join(sorted(missing_headers)))
        output = [calculate(row) for row in reader]
    if not output:
        parser.error('Input has no scenario rows.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(TEXT + RESULTS) + ['status', 'message'])
        writer.writeheader()
        writer.writerows(output)
    failures = sum(row['status'] != 'ok' for row in output)
    print(f'Rows: {len(output)}; incomplete/invalid: {failures}; output: {args.output}')
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
