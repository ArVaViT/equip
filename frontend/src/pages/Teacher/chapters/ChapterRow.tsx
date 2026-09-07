import { useRef, type HTMLAttributes } from "react";
import { Draggable } from "@hello-pangea/dnd";
import { FolderInput, GripVertical, Lock, Pencil, Trash2, Unlock } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { CHAPTER_TYPE_LABEL_KEYS, normalizeChapterType } from "@/lib/chapterTypes";
import type { Chapter } from "@/types";

/**
 * Where a lesson can be re-filed, and what to call when it is.
 *
 * A module groups lessons; it does not own them. So the same row serves
 * both directions — out of a module, and into one — and the screen that
 * renders the row says which of the two it can offer. Both lists empty
 * means the course has no grouping at all, and then the control does not
 * render: a teacher whose course is four lessons is never shown a way to
 * file them under something that does not exist.
 */
export interface ChapterMove {
  /** Modules this lesson could move into. Never the one it is already in. */
  intoModules: { id: string; title: string }[];
  /** True when the lesson sits in a module and can be lifted out of it. */
  canUngroup: boolean;
  /** `null` takes the lesson out of its module and leaves it in the course. */
  onMove: (moduleId: string | null) => void;
}

interface ChapterRowProps {
  chapter: Chapter;
  index: number;
  onTitleChange: (title: string) => void;
  onRename: (title: string) => void;
  onToggleLock: () => void;
  onEdit: () => void;
  onDelete: () => void;
  /** Omit to render no move control at all. */
  move?: ChapterMove;
}

/**
 * A single draggable lesson row. Used by the course editor for the lessons
 * that sit straight in the course, and by the module editor for the ones a
 * module groups — the row is the same either way, which is the point: a
 * lesson is a lesson wherever it is filed.
 *
 * Kept as a pure component — all state mutation is owned by the parent hook.
 */
export function ChapterRow({
  chapter,
  index,
  onTitleChange,
  onRename,
  onToggleLock,
  onEdit,
  onDelete,
  move,
}: ChapterRowProps) {
  const { t } = useTranslation();
  const type = normalizeChapterType(chapter.chapter_type);

  // Nothing to offer — no module to move into, and nowhere to come out of.
  // Rendering a disabled menu here would put the word "module" in front of
  // a teacher who has no modules and needs none.
  const canMove = Boolean(move && (move.canUngroup || move.intoModules.length > 0));

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
          {...(dragProvided.draggableProps as HTMLAttributes<HTMLDivElement>)}
          className={`border-edge/60 ${
            snapshot.isDragging ? "shadow-lg ring-2 ring-primary/20" : ""
          }`}
        >
          <div className="flex flex-col gap-2 p-3 sm:flex-row sm:items-center sm:gap-3 sm:p-4">
            {/* Row 1 on mobile (grip + input). Inline on sm+. */}
            <div className="flex items-center gap-2 sm:gap-3">
              <div
                {...dragProvided.dragHandleProps}
                className="-ml-1 flex h-11 w-8 shrink-0 cursor-grab items-center justify-center text-ink-muted transition-colors hover:text-ink active:cursor-grabbing sm:ml-0 sm:h-9"
                role="button"
                tabIndex={0}
                aria-label={t("lessons.dragAria", { title: chapter.title })}
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
                  chapter.is_locked ? "text-warning hover:text-warning" : "text-ink-muted"
                }`}
                onClick={onToggleLock}
                title={chapter.is_locked ? t("lessons.unlockTooltip") : t("lessons.lockTooltip")}
                aria-label={chapter.is_locked ? t("lessons.unlockTooltip") : t("lessons.lockTooltip")}
              >
                {chapter.is_locked ? (
                  <Lock className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
                ) : (
                  <Unlock className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
                )}
              </Button>

              {canMove && move && (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-11 w-11 shrink-0 p-0 text-ink-muted sm:h-8 sm:w-8"
                      title={t("lessons.move.tooltip")}
                      aria-label={t("lessons.move.aria", { title: chapter.title })}
                    >
                      <FolderInput className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="min-w-[14rem]">
                    {move.canUngroup && (
                      <DropdownMenuItem onSelect={() => move.onMove(null)}>
                        {t("lessons.move.toCourse")}
                      </DropdownMenuItem>
                    )}
                    {move.intoModules.map((m) => (
                      <DropdownMenuItem key={m.id} onSelect={() => move.onMove(m.id)}>
                        <span className="truncate">
                          {t("lessons.move.intoModule", {
                            title: m.title || t("lessons.move.untitledModule"),
                          })}
                        </span>
                      </DropdownMenuItem>
                    ))}
                  </DropdownMenuContent>
                </DropdownMenu>
              )}

              <Button
                variant="ghost"
                size="sm"
                className="h-11 w-11 shrink-0 p-0 sm:h-8 sm:w-8"
                onClick={onEdit}
                aria-label={t("lessons.editAria", { title: chapter.title })}
              >
                <Pencil className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
              </Button>

              <Button
                variant="ghost"
                size="sm"
                className="h-11 w-11 shrink-0 p-0 text-destructive hover:text-destructive sm:h-8 sm:w-8"
                onClick={onDelete}
                aria-label={t("lessons.deleteAria", { title: chapter.title })}
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
