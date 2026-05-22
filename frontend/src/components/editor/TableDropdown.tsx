import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { Editor } from "@tiptap/react";
import {
  Table as TableIcon,
  ChevronDown,
  Rows3,
  Columns3,
  Trash2,
  ArrowDownToLine,
  ArrowUpToLine,
  ArrowLeftToLine,
  ArrowRightToLine,
} from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Single dropdown for every table operation. Mirrors the
 * ``CalloutDropdown`` pattern so the toolbar stays visually uniform.
 *
 * When the caret is OUTSIDE a table the menu offers only "insert table".
 * When the caret is INSIDE a table the menu swaps to the full
 * row/column/header/delete action set. One trigger button, two
 * mutually-exclusive menus — keeps the toolbar at one slot regardless
 * of selection state.
 */
export function TableDropdown({
  editor,
  iconSize,
}: {
  editor: Editor;
  iconSize: number;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [open]);

  const isInTable = editor.isActive("table");

  const run = (cb: () => void) => {
    cb();
    setOpen(false);
  };

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        title={t("blockEditor.table.trigger")}
        aria-label={t("blockEditor.table.trigger")}
        aria-haspopup="menu"
        aria-expanded={open}
        className={cn(
          "flex items-center gap-0.5 rounded p-1.5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
          isInTable
            ? "bg-primary/15 text-primary"
            : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
        )}
      >
        <TableIcon size={iconSize} strokeWidth={1.75} aria-hidden="true" />
        <ChevronDown size={12} strokeWidth={1.75} aria-hidden="true" />
      </button>
      {open && (
        <div
          role="menu"
          aria-label={t("blockEditor.table.trigger")}
          className="absolute left-0 top-full z-20 mt-1 w-56 rounded-md border bg-background py-1 shadow-lg"
        >
          {!isInTable && (
            <button
              type="button"
              role="menuitem"
              onClick={() =>
                run(() =>
                  editor
                    .chain()
                    .focus()
                    .insertTable({ rows: 3, cols: 3, withHeaderRow: true })
                    .run(),
                )
              }
              className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-muted transition-colors text-left focus-visible:outline-none focus-visible:bg-muted"
            >
              <TableIcon size={16} strokeWidth={1.75} aria-hidden="true" className="text-muted-foreground" />
              {t("blockEditor.table.insert")}
            </button>
          )}
          {isInTable && (
            <>
              <button
                type="button"
                role="menuitem"
                onClick={() => run(() => editor.chain().focus().addRowBefore().run())}
                className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-muted transition-colors text-left focus-visible:outline-none focus-visible:bg-muted"
              >
                <ArrowUpToLine size={16} strokeWidth={1.75} aria-hidden="true" className="text-muted-foreground" />
                {t("blockEditor.table.addRowBefore")}
              </button>
              <button
                type="button"
                role="menuitem"
                onClick={() => run(() => editor.chain().focus().addRowAfter().run())}
                className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-muted transition-colors text-left focus-visible:outline-none focus-visible:bg-muted"
              >
                <ArrowDownToLine size={16} strokeWidth={1.75} aria-hidden="true" className="text-muted-foreground" />
                {t("blockEditor.table.addRowAfter")}
              </button>
              <button
                type="button"
                role="menuitem"
                onClick={() => run(() => editor.chain().focus().addColumnBefore().run())}
                className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-muted transition-colors text-left focus-visible:outline-none focus-visible:bg-muted"
              >
                <ArrowLeftToLine size={16} strokeWidth={1.75} aria-hidden="true" className="text-muted-foreground" />
                {t("blockEditor.table.addColumnBefore")}
              </button>
              <button
                type="button"
                role="menuitem"
                onClick={() => run(() => editor.chain().focus().addColumnAfter().run())}
                className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-muted transition-colors text-left focus-visible:outline-none focus-visible:bg-muted"
              >
                <ArrowRightToLine size={16} strokeWidth={1.75} aria-hidden="true" className="text-muted-foreground" />
                {t("blockEditor.table.addColumnAfter")}
              </button>
              <div className="my-1 border-t" role="separator" />
              <button
                type="button"
                role="menuitem"
                onClick={() => run(() => editor.chain().focus().toggleHeaderRow().run())}
                className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-muted transition-colors text-left focus-visible:outline-none focus-visible:bg-muted"
              >
                <Columns3 size={16} strokeWidth={1.75} aria-hidden="true" className="text-muted-foreground" />
                {t("blockEditor.table.toggleHeaderRow")}
              </button>
              <div className="my-1 border-t" role="separator" />
              <button
                type="button"
                role="menuitem"
                onClick={() => run(() => editor.chain().focus().deleteRow().run())}
                className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-muted transition-colors text-left focus-visible:outline-none focus-visible:bg-muted"
              >
                <Rows3 size={16} strokeWidth={1.75} aria-hidden="true" className="text-muted-foreground" />
                {t("blockEditor.table.deleteRow")}
              </button>
              <button
                type="button"
                role="menuitem"
                onClick={() => run(() => editor.chain().focus().deleteColumn().run())}
                className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-muted transition-colors text-left focus-visible:outline-none focus-visible:bg-muted"
              >
                <Columns3 size={16} strokeWidth={1.75} aria-hidden="true" className="text-muted-foreground" />
                {t("blockEditor.table.deleteColumn")}
              </button>
              <div className="my-1 border-t" role="separator" />
              <button
                type="button"
                role="menuitem"
                onClick={() => run(() => editor.chain().focus().deleteTable().run())}
                className="flex w-full items-center gap-2 px-3 py-2 text-sm text-destructive hover:bg-muted transition-colors text-left focus-visible:outline-none focus-visible:bg-muted"
              >
                <Trash2 size={16} strokeWidth={1.75} aria-hidden="true" />
                {t("blockEditor.table.deleteTable")}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
