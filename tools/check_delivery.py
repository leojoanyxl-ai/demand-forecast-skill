"""Check portable project structure, Python syntax, file links and shipped snapshot metadata."""
import ast
import csv
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def main():
    problems = []; links = 0; scripts = 0
    for path in (ROOT/'demand-forecast').rglob('*.py'):
        ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path)); scripts += 1
    for path in [ROOT/'README.md', ROOT/'CHANGELOG.md', *(ROOT/'docs').glob('*.md'), *(ROOT/'demand-forecast').rglob('*.md')]:
        text = path.read_text(encoding='utf-8-sig')
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', text):
            if '://' in target or target.startswith(('#','mailto:')):
                continue
            destination = path.parent/target.split('#')[0]
            if not destination.exists(): problems.append(str(path.relative_to(ROOT))+': '+target)
            links += 1
    entry = (ROOT/'demand-forecast'/'SKILL.md').read_text(encoding='utf-8')
    if not entry.startswith('---\nname: demand-forecast\n'):
        problems.append('Skill标识不一致')
    for cmd in (ROOT/'demand-forecast').glob('*.cmd'):
        raw = cmd.read_bytes()
        if raw.startswith(b'\xef\xbb\xbf') or b'\n' in raw.replace(b'\r\n', b''):
            problems.append('CMD需UTF-8无BOM及CRLF: '+cmd.name)
    for industry, directory in [('nev','新能源汽车'),('abs','ABS')]:
        state = json.loads((ROOT/'运行结果'/directory/'运行状态.json').read_text(encoding='utf-8'))
        if state['pipeline'] != 'completed' or state['as_of'] != '2026-11-03':
            problems.append('已附结果状态错误: '+industry)
    if problems:
        raise ValueError('\n'.join(problems))
    print(json.dumps({'project_check':'passed','relative_links':links,'python_scripts':scripts},ensure_ascii=False))


if __name__ == '__main__':
    main()
