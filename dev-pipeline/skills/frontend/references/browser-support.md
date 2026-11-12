# Browser support contract

Read for a browser-facing product when deciding compatibility, configuring its build or browser tests,
or implementing/reviewing HTML, CSS or browser APIs. This is local guidance; no external skill or CLI is required.

## Requirements and architecture

SRS §4 owns supported browsers, minimum versions or a dated support policy, mobile/embedded environments,
and how support is verified. Existing product requirements win. With no policy, propose Baseline Widely
available as of an explicit date and record the unresolved choice through the stage's normal questions flow;
do not silently turn the proposal into a requirement. A product with no browser UI gets «Не применимо».
Baseline describes web features across its core browser set, not every browser, WebView or assistive technology.
Record special environments separately. Do not silently advance a dated policy on each build.

Architecture maps that NFR to concrete build targets, supported-runtime exceptions and a browser test matrix.
Use configuration supported by the installed toolchain: a Browserslist file has no effect on tools that do
not read it. Build targets transform supported syntax; they do not supply every missing DOM API or CSS feature.
The scaffold implements those decisions without choosing a different audience or adding blanket polyfills.

## Implementation and review

- Read the product's policy before choosing a browser feature. Check current primary documentation for the
  exact capability against the declared minimums; record the source/date and applicable fallback in the task's
  documentation evidence so the implementer and reviewer use the same answer. Reviewers need not fetch it again.
- A capability outside the target needs feature detection and a tested fallback that preserves the required
  action/content, or an explicitly accepted narrower support policy. Optional decoration can degrade without
  changing the required behaviour. Do not broaden the product's scope to demonstrate a new API.
- Reuse the project's components and chosen UI kit. Before adding a dependency, consider a native solution
  that satisfies the spec, accessibility and browser policy. Do not replace a working kit component just
  because a native alternative exists; document a new dependency and why the existing/native options fail.
- Adapt browser APIs to the project's framework and types; no `as any` escape or disabled lint to force adoption.
  Existing frontend version checks, SSR guards and UX rules still apply.

## Verification

The declared matrix selects Playwright projects and the required journeys; Chromium alone is sufficient only
when the policy or an explicitly scoped check says so. Reuse existing config. Engine emulation is not proof
of a particular older browser, Safari release or embedded runtime: name what actually ran and record required
manual/device checks that could not run. Install only the engines selected by the matrix.
Cases are reused across browser projects; each browser/stand must have isolated mutable fixtures or a reset,
including authentication setup, so a destructive case in one project does not break another.
Keep the existing size checks separate from browser coverage. Check required fallback paths as well as the
modern path. Never label an unrun target or fallback as passed.

## Sources and adaptation

Policy ideas reviewed from [Modern Web Guidance](https://github.com/GoogleChrome/modern-web-guidance),
its `skills/modern-web-guidance/SKILL.md` (observed skill version `2026_11_09-5bcc021b`, reviewed 2026-11-12).
This is an independently written Codex adaptation: existing components, typed code and explicit product
requirements retain priority; upstream auto-trigger, `npx @latest` and response formatting are not adopted.
[Baseline definition](https://web.dev/baseline) supplies terminology, not a fixed compatibility database.
