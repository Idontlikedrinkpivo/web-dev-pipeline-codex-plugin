# Web platform policy — behavioral acceptance cases

These are scenarios for a future live executor/reviewer check, not claims that instructions were executed.
Status: NOT_RUN. The Python focus-scan tests cover only deterministic candidate detection.

| Case | Inputs / task | Expected observable result |
|---|---|---|
| Browser policy | Product targets a named older Safari/WebView; scaffold and UI use a newer DOM capability | Preserve the declared target, document/build the compatible fallback, configure the selected test matrix; no claim that a build target or green Chromium run supplies the API |
| Missing policy | New browser product with no support decision; author its SRS | Propose a dated policy via the normal questions flow; do not invent user consent or silently reduce coverage to Chromium |
| Browser aggregation | Same case passes Chromium but fails Firefox; later Chromium repeat passes | Case stays failed until the Firefox failure is resolved; comments preserve per-browser evidence. Unavailable required target is blocked, not passed |
| Calendar date | Birthday is `2000-01-01`; UI runs in zones on opposite sides of UTC | Display/submit `2000-01-01` unchanged; no conversion through a midnight UTC instant |
| Local schedule | Office and user zones differ; spec defines treatment of missing/repeated local times | Booking uses office zone; errors or selected occurrence match contract; calendar boundaries have one domain owner |
| Form state | Empty login form, blur, failed submit with untouched fields, correction; password change includes old/new fields | Correct autocomplete tokens; initial aria-invalid absent/false, error states true and tied to message, corrected state cleared; old/new password tokens differ |
| Forced colours | Component removes outline and draws focus with a shadow; switch forced colours on | Scanner emits a candidate; reviewer examines rendered focus and shared CSS. If no replacement survives, fix it; a working external fallback dismisses the candidate |
| Existing kit | UI has a shared Dialog; task adds confirmation | Reuse shared Dialog; no native rewrite/new dependency just because a guide demonstrates one |
| Searchable reading | Help text is collapsed; spec requires native search and fragment reveal | Content remains mounted; actual search reveals match; React/ARIA stays consistent after rerender; unsupported target gets agreed fallback. Synthetic event alone is insufficient evidence |
| Ordinary tab / hidden step | Form wizard without a reading-search requirement | No blanket until-found/expand-all change and no unrequested controls or layout |
