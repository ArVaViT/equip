-- Restored from prod schema_migrations on 2026-05-21 — this migration was
-- originally applied via Supabase MCP without a corresponding repo file.
--
-- Data fix: two Pocket mini-courses had source_locale = ru but English-only
-- title/description on public.courses. Align canonical RU strings on courses
-- + EN overlays in content_translations (source_hash matches
-- compute_source_hash(..., locale='ru') in the backend).

BEGIN;

UPDATE public.courses
SET
  title = $p1t$Глоссарий в кармане: библейские слова, которые повторяются снова и снова$p1t$,
  description = $p1d$Короткие определения слов, которые вы будете встречать снова и снова в английских Библиях и на занятиях. Здесь не глубокое богословие — только минимум, чтобы уверенно читать и понимать контекст.$p1d$,
  updated_at = now()
WHERE id = '4f8d5432-4510-43d8-bc2b-00acc677d99e';

UPDATE public.courses
SET
  title = $p2t$Карта в кармане: 66 книг$p2t$,
  description = $p2d$Практичный обзор распространённой английской таблицы из 66 книг: как обычно группируют Ветхий и Новый заветы. Без споров о каноне — только ориентир для чтения.$p2d$,
  updated_at = now()
WHERE id = '7a57298d-814e-4c08-ab88-1099a54bf507';

UPDATE public.content_translations
SET
  text = $e1t$A Pocket Glossary: Bible Words That Keep Coming Up$e1t$,
  source_hash = 'c3d39e81f72e005df52dd519f7b61352',
  updated_at = now()
WHERE entity_type = 'course'
  AND entity_id = '4f8d5432-4510-43d8-bc2b-00acc677d99e'
  AND locale = 'en'
  AND field = 'title';

UPDATE public.content_translations
SET
  text = $e1d$Short definitions for words you will see again and again in English Bibles and in class. This is not deep theology—just the minimum you need to read with confidence and understand the context.$e1d$,
  source_hash = '09626f1a39a7a8ffddf6c70ccf80e96e',
  updated_at = now()
WHERE entity_type = 'course'
  AND entity_id = '4f8d5432-4510-43d8-bc2b-00acc677d99e'
  AND locale = 'en'
  AND field = 'description';

UPDATE public.content_translations
SET
  text = $e2t$A Pocket Map: The 66 Books$e2t$,
  source_hash = 'c0c209456747602fc9e1acb83d2ff90d',
  updated_at = now()
WHERE entity_type = 'course'
  AND entity_id = '7a57298d-814e-4c08-ab88-1099a54bf507'
  AND locale = 'en'
  AND field = 'title';

UPDATE public.content_translations
SET
  text = $e2d$A practical overview of the common English 66-book table of contents: how the Old and New Testaments are typically grouped. Not a debate about the canon—just a compass for reading.$e2d$,
  source_hash = 'f11dd498f9a0336bc84056fad321d8f5',
  updated_at = now()
WHERE entity_type = 'course'
  AND entity_id = '7a57298d-814e-4c08-ab88-1099a54bf507'
  AND locale = 'en'
  AND field = 'description';

COMMIT;
