import { Draggable } from "@hello-pangea/dnd";
import { GripVertical, Lock, Pencil, Trash2, Unlock } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { getChapterTypeMeta, normalizeChapterType } from "@/lib/chapterTypes";
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
  const badgeClass = getChapterTypeMeta(type).badgeColor;

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
          <div className="flex items-center gap-3 p-4">
            <div
              {...dragProvided.dragHandleProps}
              className="cursor-grab active:cursor-grabbing text-muted-foreground/40 hover:text-muted-foreground shrink-0 transition-colors"
            >
              <GripVertical className="h-4 w-4" strokeWidth={1.75} />
            </div>

            <Input
              value={chapter.title}
              onChange={(e) => onTitleChange(e.target.value)}
              onBlur={(e) => onRename(e.target.value)}
              className="font-medium border-none shadow-none focus-visible:ring-1 h-8 text-sm flex-1"
            />

            <span
              className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium shrink-0 ${badgeClass}`}
            >
              {t(`chapterTypes.${type}.label`)}
            </span>

            <Button
              variant="ghost"
              size="sm"
              className={`h-8 w-8 shrink-0 p-0 ${
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
              className="shrink-0 h-8 w-8 p-0"
              onClick={onEdit}
              aria-label={t("moduleEditor.editChapterAria", { title: chapter.title })}
            >
              <Pencil className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
            </Button>

            <Button
              variant="ghost"
              size="sm"
              className="shrink-0 h-8 w-8 p-0 text-destructive hover:text-destructive"
              onClick={onDelete}
              aria-label={t("moduleEditor.deleteChapterAria", { title: chapter.title })}
            >
              <Trash2 className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
            </Button>
          </div>
        </Card>
      )}
    </Draggable>
  );
}
