# Project integration tests for both generator templates

Install these cases in the project's test suite (Vitest or pytest can call the same standard-library test
below). Run from the repository root with `python3 tests/env_contract.py`. Adapt the small independent input
matrix to the real stands: the expected keys come from the supported machine overrides and secret consumers.
Keep the per-stack schema tests as well. Never inspect an operator's env files during tests.

```python
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ("deploy/prod.env.example", "documentation/deploy/deploy.md", ".env.example")
INPUTS = {".env.test.local": {"API_TOKEN"}, ".env.dev.local": {"API_TOKEN", "DEV_BIND"}}


def parse_example(text):
    blocks = {}
    current = None
    for paragraph in text.removesuffix("\n").split("\n\n"):
        header = re.fullmatch(r"# ===== (.+) =====", paragraph)
        if header:
            current = header[1]
            assert current not in blocks
            blocks[current] = {}
            continue
        pair = re.fullmatch(r"# (\[required\] )?(\[secret\] )?([^\[\n][^\n]*)\n([A-Z][A-Z0-9_]*)=([^\n]*)", paragraph)
        assert pair and current and pair[4] not in blocks[current], paragraph.splitlines()[0]
        blocks[current][pair[4]] = pair[5]
        if pair[2]:
            assert not pair[5] or re.fullmatch(r"<[^<>]+>", pair[5])
    return blocks


class EnvironmentContract(unittest.TestCase):
    def test_layout(self):
        kit = parse_example((ROOT / OUTPUTS[0]).read_text())
        self.assertTrue(kit)
        local = parse_example((ROOT / OUTPUTS[2]).read_text())
        self.assertEqual({n: set(keys) for n, keys in local.items()}, INPUTS)
        for keys in local.values():
            self.assertTrue(all(v == "" or (n, v) == ("DEV_BIND", "127.0.0.1") for n, v in keys.items()))

    def test_local_inputs_reach_the_stand(self):
        # Adapt service names and binding port to the real project. Exercise each machine input:
        # a value consumed by Compose is checked at its output (port, upstream or store credential).
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for stand in ("test", "dev"):
                file = f"docker-compose.{stand}.yml"
                shutil.copy(ROOT / file, root / file)
                local = f".env.{stand}.local"
                token = "example-for-an-isolated-contract-test"
                synthetic = f"API_TOKEN={token}\nLEGACY_FLAG=unused\n"
                if stand == "dev":
                    synthetic += "DEV_BIND=0.0.0.0\n"
                (root / local).write_text(synthetic)
                env = {k: v for k, v in os.environ.items() if k not in {"API_TOKEN", "DEV_BIND", "COMPOSE_ENV_FILES"}}
                result = subprocess.check_output(["docker", "compose", "--env-file", local, "-f", file,
                                                  "config", "--format", "json"], cwd=root, env=env)
                declared = subprocess.check_output(["docker", "compose", "-f", file, "config",
                                                    "--no-interpolate", "--no-env-resolution", "--format", "json"],
                                                   cwd=root, env=env)
                for svc in json.loads(declared)["services"].values():
                    if not any(Path(f["path"]).name == local for f in svc.get("env_file", [])):
                        continue
                    mapping = svc.get("environment", {})
                    for name in INPUTS[local] & mapping.keys():
                        self.assertRegex(mapping[name], rf"^\$\{{{name}(?::-[^}}]+)?\}}$")
                services = json.loads(result)["services"]
                self.assertEqual(services["backend"]["environment"]["API_TOKEN"], token)
                self.assertEqual(services["backend"]["environment"]["APP_ENV"], stand)
                if stand == "dev":
                    self.assertTrue(any(p["host_ip"] == "0.0.0.0" for p in services["frontend"]["ports"]))
                self.assertEqual((root / local).read_text(), synthetic)

    def test_build_gate_and_bootstrap(self):
        # Copy only tracked PUBLIC inputs for these targets. Extend this allowlist if the project
        # imports other public modules. Share installed dependencies; all generated output stays in tmp.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = (*OUTPUTS, "Makefile", "scripts/build-images.sh",
                      "backend/package.json", "backend/tsconfig.json", "backend/scripts/env-doc.ts",
                      "backend/src/shared/providers/env-schema.ts", "scripts/env_doc.py", "app/env_schema.py")
            for name in inputs:
                if (ROOT / name).is_file():
                    (root / name).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(ROOT / name, root / name)
            for name in ("backend/node_modules", ".venv"):
                if (ROOT / name).is_dir():
                    (root / name).symlink_to(ROOT / name, target_is_directory=True)
            subprocess.run(["make", ".env.test.local"], cwd=root, check=True)
            local = root / ".env.test.local"
            self.assertEqual((local.read_bytes(), stat.S_IMODE(local.stat().st_mode)), (b"", 0o600))
            local.write_text("LEGACY_FLAG=kept\n")
            subprocess.run(["make", ".env.test.local"], cwd=root, check=True)
            self.assertEqual(local.read_text(), "LEGACY_FLAG=kept\n")
            if (root / "scripts/env_doc.py").exists():
                python = root / ".venv/bin/python"
                check = [str(python) if python.is_file() else sys.executable, "scripts/env_doc.py", "--check"]
            else:
                check = ["npm", "--prefix", "backend", "run", "env:check"]
            subprocess.run(check, cwd=root, check=True)
            for output in OUTPUTS:
                path = root / output
                if output.endswith(".md"):
                    text = path.read_text().replace("<!-- env-doc:start -->", "<!-- env-doc:start -->\nstale")
                else:
                    text = path.read_text() + "STALE=1\n"
                path.write_text(text)
            result = subprocess.run(check, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            self.assertNotEqual(result.returncode, 0)
            for file in OUTPUTS:
                self.assertIn(file, result.stdout)
            spy = root / "docker"
            spy.write_text("#!/bin/sh\ntouch docker-was-called\nexit 99\n")
            spy.chmod(0o700)
            env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ["PATH"])
            build = subprocess.run(["make", "build-images"], cwd=root, env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            self.assertNotEqual(build.returncode, 0)
            self.assertIn(".env.example", build.stdout)
            self.assertFalse((root / "docker-was-called").exists())


if __name__ == "__main__":
    unittest.main()
```

Also parse the two tracked YAML files in the project's native test runner. For each service loading a local
file, intersect its environment keys with INPUTS for that stand. A fixed value at any intersection is a
failure. Allow explicit same-key interpolation with a fallback when the synthetic override above reaches the
service. Test the empty-address fallback against the test stub and require dev to fail when its local file
is absent. Keep a fixture of the **old** tracked dev defaults and compare its effective settings, ports and
volumes after the upgrade, using only synthetic values.
