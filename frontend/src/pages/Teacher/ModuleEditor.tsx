import { useParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { CalendarDays, Pencil, Plus } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useConfirm } from "@/components/ui/alert-dialog";
import { EmptyState, ErrorState, InlineEdit, PageHeader } from "@/components/patterns";

import { ChapterList } from "./moduleEditor/ChapterList";
import { ModuleEditorSkeleton } from "./moduleEditor/LoadingSkeleton";
import { useModuleEditor } from "./moduleEditor/useModuleEditor";

export default function ModuleEditor() {
  const { courseId, moduleId } = useParams<{ courseId: string; moduleId: string }>();
  const navigate = useNavigate();
  const confirm = useConfirm();
  const { t } = useTranslation();

  const {
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
    updateChapterLocal,
    handleChapterDragEnd,
  } = useModuleEditor(courseId, moduleId, confirm);

  if (loading) {
    return <ModuleEditorSkeleton />;
  }

  if (!mod) {
    return (
      <div className="container mx-auto px-4">
        <ErrorState
          title={t("moduleEditor.notFound.title")}
          description={t("moduleEditor.notFound.description")}
          action={
            <Button
              variant="outline"
              size="sm"
              onClick={() => navigate(`/teacher/courses/${courseId}`)}
            >
              {t("moduleEditor.notFound.backToCourse")}
            </Button>
          }
        />
      </div>
    );
  }

  const chapters = [...(mod.chapters ?? [])].sort(
    (a, b) => a.order_index - b.order_index,
  );

  return (
    <div className="container mx-auto max-w-4xl px-4 py-6 sm:py-8">
      <PageHeader
        backTo={`/teacher/courses/${courseId}`}
        backLabel={t("moduleEditor.backToCourse")}
        title={
          <InlineEdit
            size="h1"
            value={mod.title}
            onSave={(v) => saveModuleField("title", v)}
            required
            placeholder={t("moduleEditor.untitledModule")}
            ariaLabel={t("moduleEditor.editTitle")}
            maxLength={200}
          />
        }
        description={
          <InlineEdit
            size="body"
            multiline
            value={mod.description ?? ""}
            onSave={(v) => saveModuleField("description", v)}
            placeholder={t("moduleEditor.addDescription")}
            ariaLabel={t("moduleEditor.editDescription")}
            maxLength={2000}
          />
        }
        meta={
          <>
            <Badge variant="muted">
              {t("teacherEditor.chapterCount", { count: chapters.length })}
            </Badge>
            <div className="flex items-center gap-2">
              <CalendarDays className="h-3.5 w-3.5 text-muted-foreground" strokeWidth={1.75} />
              <Label className="text-xs text-muted-foreground">
                {t("moduleEditor.dueDate")}
              </Label>
              <Input
                type="datetime-local"
                value={modDueDate}
                onChange={(e) => setModDueDate(e.target.value)}
                onBlur={(e) => saveDueDate(e.target.value)}
                className="h-9 w-auto border-border/50 text-xs sm:h-7"
              />
              {modDueDate && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-9 text-xs text-muted-foreground sm:h-6"
                  onClick={clearDueDate}
                >
                  {t("moduleEditor.clear")}
                </Button>
              )}
            </div>
          </>
        }
      />

      {chapters.length === 0 ? (
        <EmptyState
          icon={<Pencil strokeWidth={1.75} />}
          title={t("moduleEditor.noChapters.title")}
          description={t("moduleEditor.noChapters.description")}
          action={
            <Button onClick={addChapter} size="sm">
              <Plus className="h-4 w-4 mr-1.5" strokeWidth={1.75} />
              {t("moduleEditor.noChapters.action")}
            </Button>
          }
          className="mb-6"
        />
      ) : (
        <ChapterList
          chapters={chapters}
          onDragEnd={handleChapterDragEnd}
          onTitleChange={(id, title) => updateChapterLocal(id, { title })}
          onRename={renameChapter}
          onToggleLock={toggleLock}
          onEdit={(chId) =>
            navigate(
              `/teacher/courses/${courseId}/modules/${moduleId}/chapters/${chId}/edit`,
            )
          }
          onDelete={deleteChapter}
        />
      )}

      <Button variant="outline" className="w-full border-dashed h-12" onClick={addChapter}>
        <Plus className="h-4 w-4 mr-2" strokeWidth={1.75} />
        {t("moduleEditor.addChapter")}
      </Button>
    </div>
  );
}
