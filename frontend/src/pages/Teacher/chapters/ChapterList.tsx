import { DragDropContext, Droppable, type DropResult } from "@hello-pangea/dnd";

import type { Chapter } from "@/types";
import { ChapterRow, type ChapterMove } from "./ChapterRow";

interface ChapterListProps {
  chapters: Chapter[];
  onDragEnd: (result: DropResult) => void;
  onTitleChange: (chapterId: string, title: string) => void;
  onRename: (chapter: Chapter, title: string) => void;
  onToggleLock: (chapter: Chapter) => void;
  onEdit: (chapterId: string) => void;
  onDelete: (chapterId: string) => void;
  /** Per-lesson move offer. Omit to render rows with no move control. */
  moveFor?: (chapter: Chapter) => ChapterMove;
  /**
   * Distinguishes this list from any other on the page. The course editor
   * draws one list of lessons and one of modules side by side, and two
   * droppables cannot share an id.
   */
  droppableId?: string;
}

/**
 * Drag-and-drop enabled list of lesson rows. Pure view that delegates
 * all mutations to the parent through callbacks.
 */
export function ChapterList({
  chapters,
  onDragEnd,
  onTitleChange,
  onRename,
  onToggleLock,
  onEdit,
  onDelete,
  moveFor,
  droppableId = "chapters",
}: ChapterListProps) {
  return (
    <DragDropContext onDragEnd={onDragEnd}>
      <Droppable droppableId={droppableId}>
        {(provided) => (
          <div
            className="space-y-3 mb-6"
            ref={provided.innerRef}
            {...provided.droppableProps}
          >
            {chapters.map((ch, idx) => (
              <ChapterRow
                key={ch.id}
                chapter={ch}
                index={idx}
                onTitleChange={(title) => onTitleChange(ch.id, title)}
                onRename={(title) => onRename(ch, title)}
                onToggleLock={() => onToggleLock(ch)}
                onEdit={() => onEdit(ch.id)}
                onDelete={() => onDelete(ch.id)}
                move={moveFor?.(ch)}
              />
            ))}
            {provided.placeholder}
          </div>
        )}
      </Droppable>
    </DragDropContext>
  );
}
