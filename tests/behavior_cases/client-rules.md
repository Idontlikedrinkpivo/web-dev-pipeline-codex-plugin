# Client rules — B cases

Status: NOT_RUN. Structural policy checks do not prove implementation behavior.

1. Hook-only use*.ts mutation affects card/list/count: packet carries React core
   rules; after success every detail/list/aggregate read is current, with errors
   and rollback handled. No unrelated screen pack is required.
2. Add a response enum/union variant consumed by an old exhaustive switch and
   schema validator: require a demonstrated compatibility action/version.
   Separately expand an input enum against the accepted request set.
3. Installed lint plugin predates v7: discover supported equivalents for the
   required behavior without forcing an upgrade or disabling the behavior.
