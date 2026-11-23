# Python project template (pydantic-settings v2)

Keep the model in the project's config package. Re-export it from config and instantiate it only at runtime.
Use the project's virtual environment for both generation and checks. In a Python-only project the two commands
are `python scripts/env_doc.py` (env:doc) and `python scripts/env_doc.py --check` (env:check).

## app/env_schema.py

```python
from typing import Literal
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def meta(block, purpose, prod, *, secret=False):
    return dict(block=block, purpose=purpose, prod=prod, secret=secret)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", env_ignore_empty=True, case_sensitive=True,
                                      validate_default=True, hide_input_in_errors=True)
    APP_ENV: Literal["test", "dev", "prod"] = Field(json_schema_extra=meta(
        "Приложение", "Среда запуска приложения", "prod"))
    PORT: int = Field(default=8000, gt=0, json_schema_extra=meta(
        "Приложение", "Порт HTTP приложения", "8000"))
    API_TOKEN: SecretStr | None = Field(default=None, json_schema_extra=meta(
        "Интеграции", "Токен внешнего сервиса", "", secret=True))


# Field.is_required() is the same no-default rule used at startup.
COMPOSE_INPUTS = {"DEV_BIND": dict(secret=False, purpose="Интерфейс сайта на этой машине")}
LOCAL_INPUTS = {".env.test.local": {"API_TOKEN": ""},
                ".env.dev.local": {"API_TOKEN": "", "DEV_BIND": "127.0.0.1"}}
```

## scripts/env_doc.py

```python
import argparse
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.env_schema import COMPOSE_INPUTS, LOCAL_INPUTS, Settings

DOC = Path("documentation/deploy/deploy.md")
START, END = "<!-- env-doc:start -->", "<!-- env-doc:end -->"


def pair(name, value, info):
    purpose = info["purpose"]
    if not purpose.strip() or re.search(r"[\r\n]", purpose + value):
        raise ValueError(name)
    if info["secret"] and value and not re.fullmatch(r"<[^<>]+>", value):
        raise ValueError(f"secret example: {name}")
    labels = [label for key, label in (("required", "[required]"), ("secret", "[secret]")) if info.get(key)]
    return f"# {' '.join([*labels, purpose])}\n{name}={value}"


def render(root, *, check=False):
    entries = {name: dict(field.json_schema_extra, required=field.is_required())
               for name, field in Settings.model_fields.items()}
    inputs = entries | COMPOSE_INPUTS
    sections, tables = [], []
    for block in dict.fromkeys(info["block"] for info in entries.values()):
        pairs = [f"# ===== {block} ====="]
        rows = [f"### {block}", "", "| Переменная | Обязательна | Секрет | Пример | Для чего |", "|---|---|---|---|---|"]
        for name, info in entries.items():
            if info["block"] != block:
                continue
            pairs.append(pair(name, info["prod"], info))
            cells = [name, "да" if info["required"] else "нет", "да" if info["secret"] else "нет",
                     info["prod"], info["purpose"]]
            rows.append("| " + " | ".join(c.replace("|", r"\|") for c in cells) + " |")
        sections.append("\n\n".join(pairs))
        tables.append("\n".join(rows))
    local = ["\n\n".join([f"# ===== {file} =====", *(pair(n, v, inputs[n]) for n, v in keys.items())])
             for file, keys in LOCAL_INPUTS.items()]
    outputs = {Path("deploy/prod.env.example"): "\n\n".join(sections) + "\n",
               Path(".env.example"): "\n\n".join(local) + "\n"}
    text = (root / DOC).read_bytes().decode() if (root / DOC).is_file() else ""
    if text.count(START) != 1 or text.count(END) != 1 or text.index(START) > text.index(END):
        if not check:
            raise ValueError(f"{DOC}: expected one ordered marker pair")
        outputs[DOC] = None  # stale; check the remaining artifacts too
    else:
        outputs[DOC] = text.partition(START)[0] + START + "\n\n" + "\n\n".join(tables) + "\n\n" + END + text.partition(END)[2]
    return outputs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    check = parser.parse_args().check
    stale = []
    for rel, text in render(ROOT, check=check).items():
        path = ROOT / rel
        if text is not None and path.is_file() and path.read_bytes() == text.encode():
            continue
        stale.append(rel)
        if not check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode())
    if check:
        for rel in stale:
            print(rel, file=sys.stderr)
    return int(check and bool(stale))


if __name__ == "__main__":
    raise SystemExit(main())
```

## tests/test_env_doc.py (pytest)

```python
import pytest
from pydantic import ValidationError
from app.env_schema import Settings, COMPOSE_INPUTS, LOCAL_INPUTS
from scripts.env_doc import render


def test_schema_and_empty_values(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("PORT", "")
    assert Settings(LEGACY_STAND_KEY="old").PORT == 8000
    monkeypatch.setenv("APP_ENV", "")
    with pytest.raises(ValidationError):
        Settings()
    fields = Settings.model_fields
    assert fields["APP_ENV"].is_required()
    assert not fields.keys() & COMPOSE_INPUTS.keys()
    for keys in LOCAL_INPUTS.values():
        assert keys.keys() <= (fields.keys() | COMPOSE_INPUTS.keys())
    for f in fields.values():
        assert f.json_schema_extra["purpose"].splitlines() == [f.json_schema_extra["purpose"]]


def test_drift():
    from scripts.env_doc import ROOT
    for path, text in render(ROOT).items():
        assert (ROOT / path).read_bytes() == text.encode(), path
```

Use the [file and stand contract cases](env-doc-contract-tests.md) for the remaining integration tests.
