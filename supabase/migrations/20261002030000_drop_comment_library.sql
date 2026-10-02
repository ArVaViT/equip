-- The teacher's comment library (20261001170000) was taken out of the product
-- before it shipped. Nothing else reads the column; drop it and its CHECK.
alter table public.profiles drop constraint if exists profiles_comment_library_check;
alter table public.profiles drop column if exists comment_library;
