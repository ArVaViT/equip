import { useRef } from "react";
import { Draggable } from "@hello-pangea/dnd";
import { GripVertical, Lock, Pencil, Trash2, Unlock } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { CHAPTER_TYPE_LABEL_KEYS, normalizeChapterType } from "@/lib/chapterTypes";
import type { Chapter } from "@/types";

interface ChapterRowProps {
  chapter: Chapter;
  index: number;
  onTitleChange: (title: string) => void;
  onRename: (title: string) => void;
  onToggleLock: () => void;
  onEdit: () => void;
  onDelete: () => void;
}

/**
 * A single draggable chapter row inside the module editor's chapter
 * list. Kept as a pure component — all state mutation is owned by the
 * parent hook.
 */
export function ChapterRow({
  chapter,
  index,
  onTitleChange,
  onRename,
  onToggleLock,
  onEdit,
  onDelete,
}: ChapterRowProps) {
  const { t } = useTranslation();
  const type = normalizeChapterType(chapter.chapter_type);

  // Capture the title at focus time so blur can skip the PATCH when
  // nothing actually changed. Without this, every Tab-through or
  // accidental click on the row's title field fired a no-op update —
  // wasted network round-trip and an audit-log row per visit.
  const focusValueRef = useRef<string>("");

  return (
    <Draggable draggableId={chapter.id} index={index}>
      {(dragProvided, snapshot) => (
        <Card
          ref={dragProvided.innerRef}
          {...dragProvided.draggableProps}
          className={`border-border/60 ${
            snapshot.isDragging ? "shadow-lg ring-2 ring-primary/20" : ""
          }`}
        >
          <div className="flex flex-col gap-2 p-3 sm:flex-row sm:items-center sm:gap-3 sm:p-4">
            {/* Row 1 on mobile (grip + input). Inline on sm+. */}
            <div className="flex items-center gap-2 sm:gap-3">
              <div
                {...dragProvided.dragHandleProps}
                className="-ml-1 flex h-11 w-8 shrink-0 cursor-grab items-center justify-center text-muted-foreground/40 transition-colors hover:text-muted-foreground active:cursor-grabbing sm:ml-0 sm:h-9"
                role="button"
                tabIndex={0}
                aria-label={t("moduleEditor.dragChapterAria", { title: chapter.title })}
              >
                <GripVertical className="h-4 w-4" strokeWidth={1.75} aria-hidden />
              </div>

              <Input
                value={chapter.title}
                onChange={(e) => onTitleChange(e.target.value)}
                onFocus={(e) => {
                  focusValueRef.current = e.target.value;
                }}
                onBlur={(e) => {
                  if (e.target.value.trim() === focusValueRef.current.trim()) {
                    return;
                  }
                  onRename(e.target.value);
                }}
                className="h-9 flex-1 border-none font-medium shadow-none focus-visible:ring-1 sm:h-8 sm:text-sm"
              />
            </div>

            {/* Row 2 on mobile (badge + actions). Inline on sm+. */}
            <div className="flex items-center justify-end gap-1 sm:gap-2">
              <Badge variant="muted" className="mr-auto shrink-0 sm:mr-0">
                {t(CHAPTER_TYPE_LABEL_KEYS[type])}
              </Badge>

              <Button
                variant="ghost"
                size="sm"
                className={`h-11 w-11 shrink-0 p-0 sm:h-8 sm:w-8 ${
                  chapter.is_locked ? "text-warning hover:text-warning" : "text-muted-foreground"
                }`}
                onClick={onToggleLock}
                title={chapter.is_locked ? t("moduleEditor.unlockChapterTooltip") : t("moduleEditor.lockChapterTooltip")}
                aria-label={chapter.is_locked ? t("moduleEditor.unlockChapterTooltip") : t("moduleEditor.lockChapterTooltip")}
              >
                {chapter.is_locked ? (
                  <Lock className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
                ) : (
                  <Unlock className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
                )}
              </Button>

              <Button
                variant="ghost"
                size="sm"
                className="h-11 w-11 shrink-0 p-0 sm:h-8 sm:w-8"
                onClick={onEdit}
                aria-label={t("moduleEditor.editChapterAria", { title: chapter.title })}
              >
                <Pencil className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
              </Button>

              <Button
                variant="ghost"
                size="sm"
                className="h-11 w-11 shrink-0 p-0 text-destructive hover:text-destructive sm:h-8 sm:w-8"
                onClick={onDelete}
                aria-label={t("moduleEditor.deleteChapterAria", { title: chapter.title })}
              >
                <Trash2 className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
              </Button>
            </div>
          </div>
        </Card>
      )}
    </Draggable>
  );
}
