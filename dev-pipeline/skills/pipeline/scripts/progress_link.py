"""The one line a stage pastes in the chat about its progress: the count and a clickable link to the page.

    python3 progress_link.py <progress file .md>                 # the line; rebuilds the page first
    python3 progress_link.py <progress file .md> --desktop       # in the desktop app: start or reuse the server
    python3 progress_link.py <progress file .md> --count "2 из 5 исправлений"   # another count than the file's

Prints exactly one line, e.g.

    План: 3 из 6 · [progress.html](http://127.0.0.1:8790/progress.html)

The link is always the page beside the file (progress.md -> progress.html), never the Markdown.
The Codex build always starts or reuses the progress server's http://127.0.0.1:<port>/ address:
its local HTML file preview can be blocked. --desktop is accepted and remembered for compatibility.
When HTTP was requested but cannot start, report the failure instead of a broken file link.

Before printing, stamp the state and rebuild the page (pipeline → references/progress-keeping.md → How).
Unknown table statuses, missing counts and a bar that disagrees with its count are named on stderr;
stdout stays one chat line. Derived files do not need a stored count below the bar.

The count is the file's count line (the line under its bar, «Сделано: 3 из 6»), without its label; the label is
the stage's name. Paste the line as printed — never write the link by hand. Standard library only.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# the chat label per progress file (pipeline → references/progress-files.md → Which stages keep one)
LABEL = {
    "progress.md": "План", "progress-design.md": "Макеты", "progress-screen-specs.md": "ТЗ на экраны",
    "progress-test-cases.md": "Тест-кейсы", "test-run.md": "UI-тестирование",
    "security-audit.md": "Аудит безопасности",
    "progress-scaffold.md": "Каркас", "progress-deploy.md": "Релиз", "progress-mutation.md": "Мутации",
}


def rebuild(md: Path) -> None:
    """The page beside the file, as the hook would build it; a failure here never blocks the line."""
    try:
        import progress_page  # noqa: WPS433 — beside this script
        progress_page.page(md)
    except Exception:
        subprocess.run([sys.executable, str(HERE / "progress_page.py"), str(md)], capture_output=True)


def count_of(md: Path) -> str:
    text = md.read_text(encoding="utf-8", errors="replace")
    try:
        import progress_page   # the files whose count the page computes from the rows
        if md.name in progress_page.DERIVED:
            got = progress_page.derived(text)
            if got:
                return re.sub(r"^Готово:\s*", "", got[1]) + f" · {got[0]}%"
    except Exception:
        pass
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    line = ""
    for i, l in enumerate(lines):  # the count line sits right under the bar's block
        if re.search(r"[█░]{5,}", l):
            after = [x for x in lines[i + 1:] if not x.startswith("```")]
            line = after[0] if after and re.search(r"\d+\s*из\s*\d+", after[0]) else ""
            break
    if not line:
        line = next((l for l in lines if re.search(r"\d+\s*из\s*\d+", l) and not l.startswith(("|", "#"))), "")
    line = re.sub(r"[*`]", "", line)
    return re.sub(r"^[^:·|]{1,40}:\s*", "", line).strip()  # «Сделано: 3 из 6» -> «3 из 6»


DERIVED_NAMES = {"progress-design.md", "progress-screen-specs.md", "progress-test-cases.md", "security-audit.md",
                 "progress-scaffold.md", "progress-deploy.md"}


def warnings(md: Path) -> list[str]:
    """Validate every status column and every bar's count, without changing rows."""
    from progress_page import bars, status_word
    allowed = {"⏳ ждёт", "🔄 в работе", "🔍 проверка", "🔍 ревью", "🔍 аудит", "🔍 разбор",
               "✅ готово", "🔁 возвращено", "⛔ остановлено", "⏭ пропущено"}
    if md.name == "progress.md":
        allowed |= {"✅ прошёл", "⛔ есть падения"}
    if md.name == "test-run.md":
        allowed |= {"✅ прошёл", "❌ не прошёл", "⛔ заблокирован", "⏭ не автоматизирован",
                    "✅ тест исправлен, прошёл", "⛔ тест не удалось исправить", "❌ дефект приложения",
                    "🖼 расхождение с макетом", "❓ пробел в ТЗ"}
    text = md.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    result = []
    cols = []
    for i, line in enumerate(lines):
        if not line.lstrip().startswith("|"):
            cols = []
            continue
        cells = [re.sub(r"[*`]", "", c).strip() for c in line.strip().strip("|").split("|")]
        if i + 1 < len(lines) and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            cols = [k for k, c in enumerate(cells) if c.startswith("Статус")]
            continue
        if re.match(r"^\s*\|[\s:|-]+\|\s*$", line):
            continue
        for col in cols:
            cell = cells[col] if col < len(cells) else ""
            if status_word(cell) not in allowed:
                result.append(f"progress_link: {md.name}:{i + 1}: неизвестный статус {cell!r}; строка: {line.strip()}")
    if md.name not in DERIVED_NAMES:
        for bar in bars(text):
            if not re.search(r"\d+\s*из\s*\d+", bar["count"]):
                result.append(f"progress_link: {md.name}: под полосой {bar['label'] or 'в начале файла'} нет счёта N из M")
    return result


def bar_mismatch(md: Path, count: str) -> str:
    """A warning when the bar's percent is not the count's, else ""."""
    text = md.read_text(encoding="utf-8", errors="replace")
    b = re.search(r"([█░]{20,})\s*(\d+)\s*%", text)
    c = re.search(r"(\d+)\s*из\s*(\d+)", count)
    if md.name in DERIVED_NAMES:   # the page computes this bar from the rows; the file's own bar is not read
        return ""
    if not b or not c or int(c[2]) == 0 or "успешно" in count:  # a test run's bar is the share that passes
        return ""
    want = int(c[1]) * 100 // int(c[2])
    shown = b[1].count("█")
    if abs(shown - want) > 1 or abs(int(b[2]) - want) > 1:
        return (f"progress_link: the bar shows {b[2]}% but the count says {c[1]} из {c[2]} ({want}%) — fix the bar "
                f"with Edit (a file changed from the shell is not redrawn)")
    return ""


def running(folder: Path) -> str | None:
    """The address of a progress server already serving this folder, or None. Starts nothing."""
    try:
        import progress_server
        pid_port = (folder / ".progress-server").read_text().split()[:2]
        port = int(pid_port[1])
        return f"http://127.0.0.1:{port}/" if progress_server.serves(port, folder) else None
    except Exception:
        return None


def start(folder: Path) -> str | None:
    r = subprocess.run([sys.executable, str(HERE / "progress_server.py"), str(folder)], capture_output=True,
                       text=True)
    out = r.stdout.strip().splitlines()
    return out[-1] if r.returncode == 0 and out and out[-1].startswith("http") else None


def repo_path(page: Path) -> str:
    try:
        top = subprocess.run(["git", "-C", str(page.parent), "rev-parse", "--show-toplevel"], capture_output=True,
                             text=True).stdout.strip()
        if top:
            return page.resolve().relative_to(Path(top).resolve()).as_posix()
    except (OSError, ValueError):
        pass
    try:
        return page.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return page.resolve().as_posix()


def main() -> None:
    args = sys.argv[1:]
    paths = [a for i, a in enumerate(args) if not a.startswith("-") and (not i or args[i - 1] != "--count")]
    if not paths:   # flags go before or after the path: «--desktop <file>» works as «<file> --desktop»
        sys.exit(__doc__)
    md = Path(paths[0])
    if md.suffix != ".md" or not md.is_file():
        sys.exit(f"progress_link: no progress file {md}")
    md = md.resolve()
    from progress_page import stamp
    text = md.read_text(encoding="utf-8")
    state = re.search(r"^(?:\*\*)?(?:Состояние|Verdict):[^\n]*обновлено [^\n]*", text, re.M)
    if state:
        text = text[:state.start()] + stamp(state[0]) + text[state.end():]
        md.write_text(text, encoding="utf-8")
    count = args[args.index("--count") + 1] if "--count" in args else count_of(md)
    rebuild(md)
    for warning in warnings(md):
        print(warning, file=sys.stderr)
    page = md.with_suffix(".html")
    marker = md.parent / ".progress-desktop"
    # Codex-only: native file previews can block HTML. This build must use HTTP
    # even in a fresh stage chat that has not created .progress-desktop yet.
    codex = (HERE.parents[2] / ".codex-plugin" / "plugin.json").is_file()
    desktop = codex or "--desktop" in args or marker.exists()
    if "--desktop" in args and not marker.exists():
        try:
            marker.write_text("1\n")
        except OSError:
            pass
    base = start(md.parent) if desktop else running(md.parent)
    if desktop and not base:
        sys.exit("progress_link: could not start the local HTTP server; no file link emitted. "
                 "Run progress_server.py for this folder to inspect the error.")
    warn = bar_mismatch(md, count)
    if warn:
        print(warn, file=sys.stderr)
    if base:
        url = base + page.name
    else:
        url = repo_path(page)
        if " " in url or "(" in url or ")" in url:
            url = f"<{url}>"
    label = LABEL.get(md.name, md.stem)
    parts = [f"{label}: {count}" if count else label, f"[{page.name}]({url})"]
    print(" · ".join(parts))


if __name__ == "__main__":
    main()
