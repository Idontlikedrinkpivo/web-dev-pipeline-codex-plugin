# TypeScript project template (Zod)

Place the following modules in the project's backend. Use its installed Zod version and module conventions.
Re-export the schema from config and use its parser in the composition root. Replace the sample entries with
the real application and image inputs. For conditional requirements keep the existing cross-field validators.

## src/shared/providers/env-schema.ts

```ts
import { z } from "zod";

type Entry = {
  parse: z.ZodTypeAny; block: string; required: boolean; secret: boolean;
  purpose: string; prod: string; default?: string;
};

export const schema: Record<string, Entry> = {
  APP_ENV: { parse: z.enum(["test", "dev", "prod"]), block: "Приложение", required: true,
    secret: false, purpose: "Среда запуска приложения", prod: "prod" },
  PORT: { parse: z.coerce.number().int().positive(), block: "Приложение", required: false,
    secret: false, purpose: "Порт HTTP приложения", default: "8000", prod: "8000" },
  API_TOKEN: { parse: z.string().min(32), block: "Интеграции", required: false,
    secret: true, purpose: "Токен внешнего сервиса", prod: "" },
};

export const composeInputs = {
  DEV_BIND: { purpose: "Интерфейс сайта на этой машине", secret: false },
};
export const localInputs: Record<string, Record<string, string>> = {
  ".env.test.local": { API_TOKEN: "" },
  ".env.dev.local": { API_TOKEN: "", DEV_BIND: "127.0.0.1" },
};

export const required = (e: Entry) => e.required && e.default === undefined;
export function loadConfig(env: NodeJS.ProcessEnv) {
  return Object.fromEntries(Object.entries(schema).map(([name, e]) => {
    const value = env[name] || e.default;
    if (value === undefined && !required(e)) return [name, undefined];
    const result = e.parse.safeParse(value);
    if (!result.success) throw new Error(`Invalid configuration: ${name}`);
    return [name, result.data];
  }));
}
```

## scripts/env-doc.ts

Install `tsx` as a project development dependency. In the owning package use
`"env:doc": "tsx scripts/env-doc.ts"` and `"env:check": "tsx scripts/env-doc.ts --check"`.
Include scripts/**/*.ts in typecheck, ESLint and knip. This sample assumes backend/scripts under the repo root.

```ts
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { composeInputs, localInputs, required, schema } from "../src/shared/providers/env-schema.js";

const root = fileURLToPath(new URL("../../", import.meta.url));
const doc = "documentation/deploy/deploy.md";
const read = (file: string) => existsSync(resolve(root, file)) ? readFileSync(resolve(root, file), "utf8") : undefined;
type Meta = { purpose: string; secret: boolean };
const inputs: Record<string, Meta> = { ...schema, ...composeInputs };
const entries = Object.entries(schema);
const blocks = [...new Set(entries.map(([, e]) => e.block))];
function pair(name: string, value: string) {
  const e = inputs[name];
  if (!e || !e.purpose.trim() || /[\r\n]/.test(e.purpose + value)) throw new Error(name);
  if (e.secret && value && !/^<[^<>]+>$/.test(value)) throw new Error(`secret example: ${name}`);
  const flags = [schema[name] && required(schema[name]) && "[required]", e.secret && "[secret]", e.purpose];
  return `# ${flags.filter(Boolean).join(" ")}\n${name}=${value}`;
}
const section = (label: string, pairs: string[]) => [`# ===== ${label} =====`, ...pairs].join("\n\n");
const kit = blocks.map(b => section(b, entries.filter(([, e]) => e.block === b).map(([n,e]) => pair(n,e.prod))));
const local = Object.entries(localInputs).map(([file, keys]) =>
  section(file, Object.entries(keys).map(([n,v]) => pair(n,v))));
const cell = (s: string) => s.replaceAll("|", "\\|");
const tables = blocks.map(b => [
  `### ${b}`, "", "| Переменная | Обязательна | Секрет | Пример | Для чего |", "|---|---|---|---|---|",
  ...entries.filter(([, e]) => e.block === b).map(([n,e]) =>
    `| ${n} | ${required(e) ? "да" : "нет"} | ${e.secret ? "да" : "нет"} | ${cell(e.prod)} | ${cell(e.purpose)} |`),
].join("\n")).join("\n\n");
const start = "<!-- env-doc:start -->", end = "<!-- env-doc:end -->";
const source = read(doc) ?? "";
const checking = process.argv.includes("--check");
const outputs: Record<string, string> = {
  "deploy/prod.env.example": kit.join("\n\n") + "\n", ".env.example": local.join("\n\n") + "\n",
};
if (source.split(start).length !== 2 || source.split(end).length !== 2 || source.indexOf(start) > source.indexOf(end)) {
  const message = `${doc}: expected one ordered marker pair`;
  if (!checking) throw new Error(message);
  console.error(message);
  process.exitCode = 1;
} else {
  outputs[doc] = source.slice(0, source.indexOf(start) + start.length) +
    "\n\n" + tables + "\n\n" + source.slice(source.indexOf(end));
}
for (const [file, rendered] of Object.entries(outputs)) {
  if (read(file) === rendered) continue;
  if (checking) { console.error(file); process.exitCode = 1; }
  else { const path = resolve(root, file); mkdirSync(dirname(path), { recursive: true }); writeFileSync(path, rendered); }
}
```

## tests/deploy/env-doc.test.ts (Vitest)

```ts
import { expect, it } from "vitest";
import { composeInputs, loadConfig, localInputs, required, schema } from "../../src/shared/providers/env-schema.js";

it("parses defaults and ignores legacy stand keys", () => {
  expect(loadConfig({ APP_ENV: "dev", PORT: "", LEGACY_FLAG: "1" }).PORT).toBe(8000);
  expect(() => loadConfig({ APP_ENV: "" })).toThrow("APP_ENV");
  expect(required(schema.APP_ENV)).toBe(true);
  for (const e of Object.values(schema)) {
    expect(e.purpose).toMatch(/^[^\r\n]+$/);
    if (e.default !== undefined) expect(e.parse.safeParse(e.default).success).toBe(true);
  }
  const names = [...Object.keys(schema), ...Object.keys(composeInputs)];
  expect(new Set(names).size).toBe(names.length);
  for (const keys of Object.values(localInputs))
    for (const n of Object.keys(keys)) expect(names).toContain(n);
});
```

Add the [file and stand contract cases](env-doc-contract-tests.md) to the project suite. Include build-only
variables in image provenance and truly stand-only inputs in composeInputs, outside the production catalogue.
