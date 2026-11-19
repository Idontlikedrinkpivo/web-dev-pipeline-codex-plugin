"""Inspect or opt one trusted project into native Codex history compaction (Python 3.11+)."""
import argparse
import os
from pathlib import Path
import stat
import tomllib

from state_paths import checkout_root, contained_path


KEY = "model_auto_compact_token_limit"


def project_limit(project: Path, enable: int | None = None) -> int | None:
    project = project.resolve(strict=True)
    checkout = checkout_root(project)
    config_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").resolve()
    if (project == Path.home() or project / ".codex" == config_home
            or project.is_relative_to(config_home) or ".codex" in project.relative_to(checkout).parts):
        raise ValueError("select the project directory that Codex opens")
    path = contained_path(checkout, project / ".codex" / "config.toml")
    if enable is not None and not 0 < enable < 2**63:
        raise ValueError("the compaction threshold must be a positive 64-bit integer")
    original = path.read_bytes() if path.exists() else None
    current = tomllib.loads((original or b"").decode()).get(KEY)
    if current is not None and (type(current) is not int or not 0 < current < 2**63):
        raise ValueError(f"invalid {KEY} in {path}")
    if enable is None or current == enable:
        return current
    if current is not None:
        raise ValueError(f"{path} already sets {KEY} = {current}; edit that setting to replace it")
    path.parent.mkdir(exist_ok=True)
    # Insert before any table and keep all existing content, including comments.
    pending = path.with_suffix(".toml.lock")
    lock = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    renamed = False
    try:
        with os.fdopen(lock, "wb") as stream:
            stream.write(f"{KEY} = {enable}\n".encode() + (original or b""))
        if original is not None:
            os.chmod(pending, stat.S_IMODE(path.stat().st_mode))
            if path.read_bytes() != original:
                raise ValueError(f"{path} changed; retry")
            os.replace(pending, path)
            renamed = True
        else:
            os.link(pending, path)
    finally:
        if not renamed:
            pending.unlink(missing_ok=True)
    return enable


def iteration_offer(project: Path) -> str | None:
    """Codex loads project config layers from the checkout down to its working directory."""
    project = project.resolve(strict=True)
    checkout = checkout_root(project)
    for folder in (project, *project.parents):
        if project_limit(folder) is not None:
            return None
        if folder == checkout:
            break
    return "Вопрос 1 из 1. Включить для новых чатов этого проекта автосжатие на 300 000 токенов?"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path, help="the exact directory opened in Codex")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--enable", type=int, metavar="TOKENS", help="set the local threshold after opt-in")
    mode.add_argument("--iteration-offer", action="store_true", help="print the optional opening question if unset")
    args = parser.parse_args()
    try:
        if args.iteration_offer:
            question = iteration_offer(args.project)
            if question:
                print(question)
        else:
            value = project_limit(args.project, args.enable)
            print(f"{KEY} = {value}" if value is not None else "No project-local threshold")
    except (OSError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")
