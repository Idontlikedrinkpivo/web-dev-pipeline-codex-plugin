# Changed mockups

Use only when changed-mockups mode is explicitly requested. Read the existing
frames register and stable-ID/anti-renumber rules in ui-design before comparing.

1. Obtain authorized Figma tool/login and the exact file/frame nodeIds. Missing
   access is a prerequisite blocker; never invent a successful comparison.
2. Compare current frames/nodeIds with the register: classify added, changed,
   unchanged, deleted. A renamed or moved node keeps its existing S-n/M-n ID.
   Append IDs for new nodes; never renumber or reuse old IDs.
3. Deleted/missing frame: add a named open question identifying the node and
   affected S/M IDs; do not silently remove its registry row or reuse its ID.
4. Record the delta and an affected screen-spec/case list. Invoke screen-spec
   for those specs, then ui-test-cases write for affected cases; unchanged specs
   and cases remain unchanged unless a demonstrated dependency requires them.
   Their existing review, traceability and anti-renumber rules remain mandatory.
5. The final forwarding phrase names the changed mockups path: «Изменённые
   макеты: <frames register path>; затронутые ТЗ: <paths>; кейсы: <paths/IDs>».

Structural tests establish routing and wording only. Behavioral cases and live
Figma comparison remain NOT_RUN until separately observed with authorization.
