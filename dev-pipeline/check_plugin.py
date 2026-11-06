"""Local package checks; read-only, standard library, no pipeline orchestration.

Run: PYTHONDONTWRITEBYTECODE=1 python3.12 dev-pipeline/check_plugin.py
"""
import ast
import json
from pathlib import Path
import re
import subprocess
import tomllib

ROOT = Path(__file__).resolve().parent
SKILL_LINE_LIMIT = 500


def progress_labels(root: Path) -> list[str]:
    """Read literal mappings without importing scripts or starting their runtime."""
    mappings = []
    try:
        for filename, symbol in (("progress_page.py", "FILES"), ("progress_link.py", "LABEL")):
            path = root / "skills/pipeline/scripts" / filename
            tree = ast.parse(path.read_text())
            value = next(node.value for node in tree.body if isinstance(node, ast.Assign)
                         and any(isinstance(target, ast.Name) and target.id == symbol for target in node.targets))
            mappings.append(ast.literal_eval(value))
    except (OSError, SyntaxError, ValueError, StopIteration) as exc:
        return [f"progress labels: cannot read FILES/LABEL: {exc}"]
    files, labels = mappings
    return [f"progress labels: {name}: FILES={files.get(name)!r}, LABEL={labels.get(name)!r}"
            for name in sorted(files.keys() | labels.keys()) if name not in files or name not in labels
            or files[name] != labels[name]]


def check(root: Path) -> list[str]:
    errors = progress_labels(root)
    for path in sorted(root.rglob('*')):
        if not path.is_file() or '__pycache__' in path.parts:
            continue
        rel = path.relative_to(root)
        try:
            if path.suffix == '.py':
                ast.parse(path.read_text(), filename=str(rel))
            elif path.suffix == '.json':
                json.loads(path.read_text())
            elif path.suffix == '.toml':
                tomllib.loads(path.read_text())
            elif path.suffix == '.sh':
                result = subprocess.run(['bash', '-n', str(path)], capture_output=True, text=True)
                if result.returncode:
                    errors.append(f'{rel}: {result.stderr.strip()}')
            if path.name == 'SKILL.md':
                text = path.read_text()
                count = len(text.splitlines())
                if count > SKILL_LINE_LIMIT:
                    errors.append(f'{rel}: {count} lines > {SKILL_LINE_LIMIT}')
                front = re.match(r'---\n(.*?)\n---', text, re.S)
                if not front or not all(re.search(rf'^{key}:\s*\S', front[1], re.M)
                                        for key in ('name', 'description')):
                    errors.append(f'{rel}: missing name/description frontmatter')
        except (ValueError, SyntaxError, OSError) as exc:
            errors.append(f'{rel}: {exc}')
    return errors


if __name__ == '__main__':
    problems = check(ROOT)
    for problem in problems:
        print(problem)
    print(f'check_plugin: {len(problems)} problems; SKILL.md limit {SKILL_LINE_LIMIT} lines')
    raise SystemExit(bool(problems))
