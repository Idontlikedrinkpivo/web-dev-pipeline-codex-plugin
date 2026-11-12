# Modern web additions — source record

Reviewed 2026-11-12 in the Codex repository. These are independently written, selectively adapted rules;
no upstream guide, implementation snippet, CLI or automatic activation rule is bundled.

- [GoogleChrome/modern-web-guidance](https://github.com/GoogleChrome/modern-web-guidance), Apache-2.0:
  `skills/modern-web-guidance/SKILL.md`, observed skill version `2026_11_09-5bcc021b`, and
  [search-hidden-content](https://github.com/GoogleChrome/modern-web-guidance/blob/main/skills/modern-web-guidance/guides/ui-behaviors/search-hidden-content.md).
  Reviewed the then-current main branch; this records the observation, not a pinned local copy of its corpus.
- [Baseline](https://web.dev/baseline): meaning of the support policy, not an evergreen browser-version list.
- [MDN autocomplete](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Attributes/autocomplete)
  and [aria-invalid](https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Reference/Attributes/aria-invalid):
  field purposes and validation state. Local rules map to UX-19, UX-20 and UX-21.
- [MDN forced-colors](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/@media/forced-colors):
  shadows are removed; verify focus and control boundaries (UX-63/UX-7).
- [Chrome hidden-until-found](https://developer.chrome.com/docs/css-ui/hidden-until-found) and
  [MDN hidden](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Global_attributes/hidden):
  native reveal and state synchronization, applied only to specified searchable reading content (UX-71).
- [MDN ZonedDateTime](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Temporal/ZonedDateTime):
  distinction between an instant and local time with a zone. The local date/time contract does not mandate Temporal.

Changes from upstream: retain the project's UI kit and typed code, existing validation timing and error links;
do not turn every disclosure into a searchable region or every UI task into a network/CLI request. Confirm
version-sensitive support against the product's declared targets when implementing. Do not fetch external
instructions to replace these locally reviewed rules. Attribution is also in `THIRD_PARTY_NOTICES.md`.
