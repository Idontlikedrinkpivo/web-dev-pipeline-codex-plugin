---
name: open-docs
description: >-
  Opens the documentation site in the built-in browser, building it if missing, and gives its link. Use for «открой
  документацию», «покажи документацию», «закрой сайт». Building: docs-site.
---

> **Codex runtime.** Before using this skill, read `../executor-catalog/references/codex-runtime.md`. It defines tool mappings, named-agent dispatch and stage-chat orchestration; use it for inherited Claude Code terms below.

# Open the documentation site

The site lives in `documentation/_web-docs/` and the plugin keeps it fresh by itself (`docs-site` → Built at the
first document, kept fresh after). This command only shows it.

## Open

From the project's root:

1. **Wait, and build or rebuild when needed**:
   `python3 "<folder of this SKILL.md>/../docs-site/scripts/rebuild.py" . --if-outdated`. It waits for a rebuild in
   flight, so the page is not a version behind; builds a missing site and rebuilds one another plugin version built
   (its new features — a back button, a new page — appear only after a rebuild), both through the rebuild queue,
   never `build_site.py` beside it (`docs-site` → step 1). Its one line says which — «собран сейчас», «пересобран
   для плагина <version>» or «актуален»; give it to the user when the site was built or rebuilt, and that it goes
   into git with the next documents' commit. Exit 1 (no `documentation/` at all): say there is nothing to show yet
   and stop.
2. **Serve and open**: `python3 "<folder of this SKILL.md>/../docs-site/scripts/site_server.py"` prints
   `http://127.0.0.1:<port>/index.html` and reuses a server already running for this site. Open that address in
   an available browser yourself, after reading its browser skill and actual tool schema. Discover the tools by
   capability; `preview_start` is a legacy name, not a required Codex tool. Serve HTTP so menus and search work.
   Give the HTTP address as a clickable chat link. Without browser tools, give that same HTTP link to the user;
   do not open an HTML source file or claim that a browser was opened. The server disables caching.

Answer in one line: the link, and step 1's line when it built or rebuilt the site. Nothing else — no report, no checks; those
are `docs-site`.

## Stop

«Закрой сайт», «останови сайт»: `python3 "<folder of this SKILL.md>/../docs-site/scripts/site_server.py" --stop`, and
one line that the link no longer opens until the next «открой сайт». The iteration's close stops it too.
