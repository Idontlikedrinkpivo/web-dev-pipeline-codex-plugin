# Stage selection behavior cases (B)

Status: **NOT RUN**. R tests establish registry semantics, not real agent consent.
For each case record the prompt, response, actual created chat IDs, verdict and evidence.

| Case | Fixture / trigger | Required response | Authorization boundary |
|---|---|---|---|
| B1 | Propose SRS/API/work, user picks API/work, then continue after compaction. | Open only explicitly selected stages; preserve canonical 04/12 titles. A repeated plan/show does not authorize SRS. | Only the recorded current workflow selection permits creation. |
| B2 | Fresh clone has documents authored by another person; user selects work. | Offer all stages ready by requirements, allow work regardless of historical author, constrain simultaneous file ownership only. | Author history is evidence, never consent or an executor restriction. |
| B3 | Legacy registry has opened SRS and unopened work; user says continue. | Preserve opened row as fact, recover saved authorization; never infer work authorization from the old proposal. | Old sessions.md alone grants no new creation. |
| B4 | User selects work and chat tools are absent. | Run in the same chat with the chosen stage; do not invent a created chat or demand unnecessary confirmation. | Selection persists through continuation. |
