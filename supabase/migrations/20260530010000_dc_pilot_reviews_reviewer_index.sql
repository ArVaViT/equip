-- Adds an index on daily_challenge_pilot_reviews.reviewer_id so
-- "rows reviewed by user X" queries don't sequential-scan as the
-- pilot pool grows. Surfaced by the post-Sprint-6 architectural audit.

CREATE INDEX IF NOT EXISTS ix_dc_pilot_reviews_reviewer
    ON daily_challenge_pilot_reviews (reviewer_id);
