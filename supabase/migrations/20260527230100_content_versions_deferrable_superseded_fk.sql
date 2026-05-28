-- Make ``superseded_by`` FK DEFERRABLE INITIALLY DEFERRED so the
-- supersession write order (UPDATE old.superseded_by = new.id;
-- INSERT new) can happen in a single transaction. The constraint
-- still fires at COMMIT, so integrity is preserved.
--
-- Without this, the write helper's natural order — point the old
-- row at the not-yet-inserted new row, then insert the new row —
-- would fail at the UPDATE because the referenced id doesn't exist
-- yet. The other workarounds (insert sentinel rows, two-phase
-- commit, drop the FK) are all worse: this is the standard pattern
-- for self-referencing version chains in Postgres.
ALTER TABLE content_versions
  DROP CONSTRAINT content_versions_superseded_by_fkey;

ALTER TABLE content_versions
  ADD CONSTRAINT content_versions_superseded_by_fkey
  FOREIGN KEY (superseded_by) REFERENCES content_versions(id)
  ON DELETE SET NULL
  DEFERRABLE INITIALLY DEFERRED;
