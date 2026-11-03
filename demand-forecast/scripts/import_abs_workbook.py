"""Optional read-only importer. Runtime analysis uses the portable CSV, not Excel paths."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

FIELDS = {10: 'new_volume_100m_cny', 11: 'new_projects', 8: 'outstanding_projects',
          12: 'szse_turnover_cny', 13: 'szse_turnover_ytd_cny', 14: 'szse_market_value_cny',
          16: 'receivable_stock_100m_cny', 17: 'cmbs_stock_100m_cny', 18: 'leasing_stock_100m_cny'}


def extract(source, destination):
    import openpyxl
    book = openpyxl.load_workbook(source, read_only=True, data_only=True)
    sheet = book.active
    rows = []
    for row in sheet.iter_rows(min_row=4):
        raw = row[0].value
        if raw is None or not str(raw)[:4].isdigit():
            continue
        period = str(raw)[:7]
        item = {'period': period, 'source_row': row[0].row}
        for column, key in FIELDS.items():
            item[key] = row[column-1].value
        rows.append(item)
    rows.sort(key=lambda r: r['period'])
    destination.mkdir(parents=True, exist_ok=True)
    with (destination/'abs-monthly.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    meta = {'source_file': source.name, 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'source_provider': '同花顺 iFinD（用户提供的导出文件）', 'sheet': sheet.title,
            'rows': len(rows), 'start': rows[0]['period'], 'end': rows[-1]['period'],
            'columns': {key: {'column': openpyxl.utils.get_column_letter(col),
                        'label': sheet.cell(1, col).value, 'unit': sheet.cell(3, col).value}
                        for col, key in FIELDS.items()},
            'vintage': '用户提供的当前导出版本；未重建各月首次发布值及修订历史',
            'public_source': 'https://www.amac.org.cn/sjtj/tjbg/zczqh/',
            'latest_brief': 'https://www.amac.org.cn/sjtj/tjbg/zczqh/202610/P020261030623458249458.pdf',
            'latest_list_publication': '2026-10-30',
            'verification': '已核验协会目录在截止日前列出2026年9月简报；PDF正文访问超时，未逐项核验全部81个月数值。目录发布日期不替代全部原值核验。',
            'availability': '截至2026-11-03按用户导出使用；历史发布日期未逐项取得，回测为当前版本伪滚动验证，非实时回放'}
    (destination/'abs-source.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    book.close()
    return meta


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workbook', type=Path)
    parser.add_argument('--assets', type=Path, default=Path(__file__).resolve().parents[1]/'assets')
    args = parser.parse_args()
    print(json.dumps(extract(args.workbook, args.assets), ensure_ascii=False, indent=2))
