import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { DropResult } from "@hello-pangea/dnd";
import { isAxiosError } from "axios";

import { coursesService } from "@/services/courses";
import { getErrorDetail } from "@/lib/errorDetail";
import { toast } from "@/lib/toast";
import { isoToLocalInput, localInputToIso } from "@/i18n/format";
import { makeChapterSchema, makeModuleSchema } from "@/lib/validations/course";
import { chapterEditHref, reuseOrderNumbers } from "@/lib/courseStructure";
import type { Chapter, Module } from "@/types";
import type { ChapterType } from "@/lib/chapterTypes";


/**
 * Encapsulates everything behind the Module editor page: loading the
 * module, inline edits on its title / description / due date, chapter
 * CRUD, lock toggling, and drag-reorder with optimistic local state.
 *
 * Split out so the component file is purely about layout — a good
 * reference point for the CourseEditor pattern established earlier.
 */
export function useModuleEditor(
  courseId: string | undefined,
  moduleId: string | undefined,
) {
  const navigate = useNavigate();
  const { t } = useTranslation();

  const [mod, setMod] = useState<Module | null>(null);
  const [loading, setLoading] = useState(true);
  const [modDueDate, setModDueDate] = useState("");
  const [reordering, setReordering] = useState(false);

  const load = useCallback(
    async (signal?: { cancelled: boolean }) => {
      if (!courseId || !moduleId) return;
      setLoading(true);
      try {
        // `getModuleForEdit` forces ``?source=1`` so the editor binds to
        // source-language `title` / `description` columns regardless of
        // the viewer's UI locale. Without this an admin/owner in EN UI
        // would type into the EN translation and overwrite the source.
        const data = await coursesService.getModuleForEdit(courseId, moduleId);
        if (signal?.cancelled) return;
        setMod(data);
        setModDueDate(isoToLocalInput(data.due_date));
      } catch (err) {
        if (signal?.cancelled) return;
        // «Module not found» was the sentence for every failure, including a
        // dropped connection to a module that is right there.
        const notFound = isAxiosError(err) && err.response?.status === 404;
        toast({
          title: notFound
            ? t("moduleEditor.toast.moduleNotFound")
            : getErrorDetail(err, t("moduleEditor.toast.loadFailed")),
          variant: "destructive",
        });
        navigate(`/teacher/courses/${courseId}`);
      } finally {
        if (!signal?.cancelled) setLoading(false);
      }
    },
    [courseId, moduleId, navigate, t],
  );

  useEffect(() => {
    const signal = { cancelled: false };
    load(signal);
    return () => {
      signal.cancelled = true;
    };
  }, [load]);

  const saveModuleField = async (field: "title" | "description", value: string) => {
    if (!courseId || !moduleId) return;
    // Build inside the handler so error messages match the current
    // locale, not the bootstrap snapshot.
    const check = makeModuleSchema()
      .pick({ title: true, description: true })
      .partial()
      .safeParse({ [field]: value });
    if (!check.success) {
      toast({
        title:
          check.error.issues[0]?.message ?? t("moduleEditor.invalidField", { field }),
        variant: "destructive",
      });
      throw new Error("validation");
    }
    try {
      await coursesService.updateModule(courseId, moduleId, { [field]: value });
      setMod((prev) => (prev ? { ...prev, [field]: value } : prev));
    } catch {
      toast({ title: t("moduleEditor.toast.failedSaveModule"), variant: "destructive" });
      throw new Error("save failed");
    }
  };

  const saveDueDate = async (value: string) => {
    if (!courseId || !moduleId) return;
    try {
      const due = localInputToIso(value);
      await coursesService.updateModule(courseId, moduleId, { due_date: due });
      setMod((prev) => (prev ? { ...prev, due_date: due } : prev));
    } catch {
      toast({ title: t("moduleEditor.toast.failedSaveDueDate"), variant: "destructive" });
    }
  };

  const clearDueDate = () => {
    setModDueDate("");
    void saveDueDate("");
  };

  const addingChapterRef = useRef(false);
  const addChapter = async (chapterType: ChapterType = "reading") => {
    if (!courseId || !moduleId || !mod) return;
    // Lock: a fast double-click before the optimistic ``setMod`` lands
    // recomputes the same ``order_index`` from a stale
    // ``mod.chapters?.length``, and the server then accepts two
    // chapters at the same ``order_index`` -- breaking ``sortedChapters``
    // until a refresh. Same shape as ``addModule``'s ref-based guard.
    if (addingChapterRef.current) return;
    addingChapterRef.current = true;
    const order = mod.chapters?.length ?? 0;  // for the fallback title only
    // Default title counts existing chapters of the SAME type so
    // teachers see "Quiz 2" rather than "Chapter 5" when adding their
    // second quiz to a mostly-reading module. Falls back to the
    // generic ``defaults.chapterTitle`` key when the type-specific
    // key is missing (defensive for future chapter types).
    const sameTypeCount =
      (mod.chapters ?? []).filter((c) => c.chapter_type === chapterType).length;
    const typeSpecificKey = `lessons.defaults.${chapterType}Title`;
    const fallbackKey = "lessons.defaults.chapterTitle";
    const typeSpecific = t(typeSpecificKey, { n: sameTypeCount + 1 });
    const seededTitle =
      typeSpecific === typeSpecificKey
        ? t(fallbackKey, { n: order + 1 })
        : typeSpecific;
    try {
      const ch = await coursesService.createChapter(courseId, moduleId, {
        // Seed in the teacher's UI locale. Persisted as-is, so the
        // previous ``Chapter N`` literal stuck English into every
        // Russian-UI teacher's course tree until they renamed it.
        title: seededTitle,
        // No `order_index`: it is course-wide on the server, and the
        // module's own count collided with lessons elsewhere in the course.
        // Left out, the server puts the lesson at the course's tail.
        chapter_type: chapterType,
      });
      setMod((prev) =>
        prev ? { ...prev, chapters: [...(prev.chapters ?? []), ch] } : prev,
      );
      toast({ title: t("lessons.toast.added"), variant: "success" });
      // Course-shaped, like every other link to a lesson now: it is the one
      // address that survives the lesson being moved out of this module.
      navigate(chapterEditHref(courseId, ch.id));
    } catch {
      toast({ title: t("lessons.toast.addFailed"), variant: "destructive" });
    } finally {
      addingChapterRef.current = false;
    }
  };

  const updateChapterLocal = (chapterId: string, patch: Partial<Chapter>) => {
    setMod((prev) =>
      prev
        ? {
            ...prev,
            chapters: prev.chapters?.map((c) =>
              c.id === chapterId ? { ...c, ...patch } : c,
            ),
          }
        : prev,
    );
  };

  const renameChapter = async (ch: Chapter, newTitle: string) => {
    if (!courseId || !moduleId || !newTitle.trim()) return;
    const trimmed = newTitle.trim();
    const check = makeChapterSchema().pick({ title: true }).safeParse({ title: trimmed });
    if (!check.success) {
      toast({
        title:
          check.error.issues[0]?.message ?? t("lessons.invalidTitle"),
        variant: "destructive",
      });
      return;
    }
    const previousTitle = ch.title;
    updateChapterLocal(ch.id, { title: trimmed });
    try {
      await coursesService.updateCourseChapter(courseId, ch.id, {
        title: trimmed,
      });
    } catch {
      updateChapterLocal(ch.id, { title: previousTitle });
      toast({
        title: t("lessons.toast.renameFailed"),
        variant: "destructive",
      });
    }
  };

  const deleteChapter = async (chId: string) => {
    if (!courseId || !moduleId) return;
    // "Undo" after, not "are you sure?" before — as on the course page.
    try {
      await coursesService.deleteCourseChapter(courseId, chId);
      setMod((prev) =>
        prev
          ? { ...prev, chapters: prev.chapters?.filter((c) => c.id !== chId) }
          : prev,
      );
      toast({
        title: t("lessons.toast.deleted"),
        variant: "success",
        duration: 8000,
        action: {
          label: t("lessons.toast.undo"),
          onClick: () => {
            void coursesService
              .restoreCourseChapter(courseId, chId)
              .then((restored) => {
                // Into the module as it stands now, not a snapshot from
                // before the delete, so edits made meanwhile survive.
                setMod((prev) =>
                  prev
                    ? {
                        ...prev,
                        chapters: [
                          ...(prev.chapters ?? []).filter((c) => c.id !== restored.id),
                          restored,
                        ].sort((a, b) => a.order_index - b.order_index),
                      }
                    : prev,
                );
                toast({ title: t("lessons.toast.restored"), variant: "success" });
              })
              .catch(() => toast({ title: t("lessons.toast.restoreFailed"), variant: "destructive" }));
          },
        },
      });
    } catch {
      toast({
        title: t("lessons.toast.deleteFailed"),
        variant: "destructive",
      });
    }
  };

  const toggleLock = async (ch: Chapter) => {
    if (!courseId || !moduleId) return;
    const newLocked = !ch.is_locked;
    updateChapterLocal(ch.id, { is_locked: newLocked });
    try {
      await coursesService.updateCourseChapter(courseId, ch.id, {
        is_locked: newLocked,
      });
      toast({
        title: newLocked
          ? t("lessons.toast.locked")
          : t("lessons.toast.unlocked"),
        variant: "success",
      });
    } catch (error: unknown) {
      updateChapterLocal(ch.id, { is_locked: ch.is_locked });
      const detail = getErrorDetail(error) || t("lessons.unknownError");
      toast({
        title: t("lessons.toast.lockFailed", { detail }),
        variant: "destructive",
      });
    }
  };

  /**
   * Lift a lesson out of this module. It stays in the course — the module
   * was only grouping it — so this is a re-filing, not a deletion, and the
   * lesson keeps its content, its type and its id.
   *
   * The other direction (filing a loose lesson under a module) lives in the
   * course editor, which is the screen that knows the whole list of modules
   * to choose from. Between them the lesson can go either way.
   */
  const ungroupChapter = async (ch: Chapter) => {
    if (!courseId) return;
    try {
      await coursesService.updateCourseChapter(courseId, ch.id, { module_id: null });
      setMod((prev) =>
        prev ? { ...prev, chapters: prev.chapters?.filter((c) => c.id !== ch.id) } : prev,
      );
      toast({ title: t("lessons.toast.movedToCourse"), variant: "success" });
    } catch {
      toast({ title: t("lessons.toast.moveFailed"), variant: "destructive" });
    }
  };

  const handleChapterDragEnd = useCallback(
    async (result: DropResult) => {
      if (!result.destination || !courseId || !moduleId || reordering) return;
      const from = result.source.index;
      const to = result.destination.index;
      if (from === to) return;

      const sorted = [...(mod?.chapters ?? [])].sort(
        (a, b) => a.order_index - b.order_index,
      );
      const reordered = Array.from(sorted);
      const [moved] = reordered.splice(from, 1);
      if (!moved) return;
      reordered.splice(to, 0, moved);

      // The numbers the lessons already had, in the new order — see
      // `reuseOrderNumbers` for why not 0..n-1.
      const renumbered = reuseOrderNumbers(sorted, reordered);
      setMod((prev) => (prev ? { ...prev, chapters: renumbered } : prev));

      setReordering(true);
      try {
        await Promise.all(
          renumbered
            .map((c, i) =>
              c.order_index !== reordered[i]!.order_index
                ? coursesService.updateCourseChapter(courseId, c.id, {
                    order_index: c.order_index,
                  })
                : null,
            )
            .filter(Boolean),
        );
      } catch {
        toast({
          title: t("lessons.toast.reorderFailed"),
          variant: "destructive",
        });
        load();
      } finally {
        setReordering(false);
      }
    },
    [mod, courseId, moduleId, load, reordering, t],
  );

  return {
    mod,
    loading,
    modDueDate,
    setModDueDate,
    saveModuleField,
    saveDueDate,
    clearDueDate,
    addChapter,
    renameChapter,
    deleteChapter,
    toggleLock,
    ungroupChapter,
    updateChapterLocal,
    handleChapterDragEnd,
  };
}
