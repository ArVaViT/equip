-- Drop the server-side default on ``certificates.issued_at``.
--
-- ``func.now()`` was populating the column at certificate REQUEST time
-- (status='pending'), giving the API a fake "issued" datetime months
-- before ``admin_approve`` actually issues the credential. The frontend
-- displays that field in cert lists and on the verify page, so users
-- have been seeing a misleading "Issued: <request date>" for every
-- pending / teacher_approved / rejected certificate.
--
-- After this migration only ``admin_approve`` writes ``issued_at``.

ALTER TABLE certificates ALTER COLUMN issued_at DROP DEFAULT;

-- Clear the stale fake-issued dates on historical rows that are not in
-- 'approved' status so the API stops returning misleading datetimes.
UPDATE certificates
SET issued_at = NULL
WHERE status <> 'approved';
