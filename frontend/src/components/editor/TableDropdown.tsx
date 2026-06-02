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
import { useDropdownPosition } from "./useDropdownPosition";

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
  const triggerRef = useRef<HTMLButtonElement>(null);
  // Panel width matches the ``w-56`` tailwind class on the menu.
  const { alignClass } = useDropdownPosition(open, triggerRef, 224);

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
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        title={t("blockEditor.table.trigger")}
        aria-label={t("blockEditor.table.trigger")}
        aria-haspopup="menu"
        aria-expanded={open}
        // ADR-0011 Wave 7 — toolbar-button vocabulary.
        className={cn(
          "flex items-center gap-0.5 rounded p-1.5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2",
          isInTable
            ? "bg-brand/20 text-brand ring-1 ring-inset ring-brand/30"
            : "text-ink-muted hover:bg-heritage hover:text-ink",
        )}
      >
        <TableIcon size={iconSize} strokeWidth={1.75} aria-hidden="true" />
        <ChevronDown size={12} strokeWidth={1.75} aria-hidden="true" />
      </button>
      {open && (
        <div
          role="menu"
          aria-label={t("blockEditor.table.trigger")}
          className={cn(
            "absolute top-full z-20 mt-1 w-56 rounded-md border bg-surface-elevated py-1 shadow-lg",
            alignClass,
          )}
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
              className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-heritage transition-colors text-left focus-visible:outline-none focus-visible:bg-heritage"
            >
              <TableIcon size={16} strokeWidth={1.75} aria-hidden="true" className="text-ink-muted" />
              {t("blockEditor.table.insert")}
            </button>
          )}
          {isInTable && (
            <>
              <button
                type="button"
                role="menuitem"
                onClick={() => run(() => editor.chain().focus().addRowBefore().run())}
                className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-heritage transition-colors text-left focus-visible:outline-none focus-visible:bg-heritage"
              >
                <ArrowUpToLine size={16} strokeWidth={1.75} aria-hidden="true" className="text-ink-muted" />
                {t("blockEditor.table.addRowBefore")}
              </button>
              <button
                type="button"
                role="menuitem"
                onClick={() => run(() => editor.chain().focus().addRowAfter().run())}
                className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-heritage transition-colors text-left focus-visible:outline-none focus-visible:bg-heritage"
              >
                <ArrowDownToLine size={16} strokeWidth={1.75} aria-hidden="true" className="text-ink-muted" />
                {t("blockEditor.table.addRowAfter")}
              </button>
              <button
                type="button"
                role="menuitem"
                onClick={() => run(() => editor.chain().focus().addColumnBefore().run())}
                className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-heritage transition-colors text-left focus-visible:outline-none focus-visible:bg-heritage"
              >
                <ArrowLeftToLine size={16} strokeWidth={1.75} aria-hidden="true" className="text-ink-muted" />
                {t("blockEditor.table.addColumnBefore")}
              </button>
              <button
                type="button"
                role="menuitem"
                onClick={() => run(() => editor.chain().focus().addColumnAfter().run())}
                className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-heritage transition-colors text-left focus-visible:outline-none focus-visible:bg-heritage"
              >
                <ArrowRightToLine size={16} strokeWidth={1.75} aria-hidden="true" className="text-ink-muted" />
                {t("blockEditor.table.addColumnAfter")}
              </button>
              <div className="my-1 border-t" role="separator" />
              <button
                type="button"
                role="menuitem"
                onClick={() => run(() => editor.chain().focus().toggleHeaderRow().run())}
                className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-heritage transition-colors text-left focus-visible:outline-none focus-visible:bg-heritage"
              >
                <Columns3 size={16} strokeWidth={1.75} aria-hidden="true" className="text-ink-muted" />
                {t("blockEditor.table.toggleHeaderRow")}
              </button>
              <div className="my-1 border-t" role="separator" />
              <button
                type="button"
                role="menuitem"
                onClick={() => run(() => editor.chain().focus().deleteRow().run())}
                className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-heritage transition-colors text-left focus-visible:outline-none focus-visible:bg-heritage"
              >
                <Rows3 size={16} strokeWidth={1.75} aria-hidden="true" className="text-ink-muted" />
                {t("blockEditor.table.deleteRow")}
              </button>
              <button
                type="button"
                role="menuitem"
                onClick={() => run(() => editor.chain().focus().deleteColumn().run())}
                className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-heritage transition-colors text-left focus-visible:outline-none focus-visible:bg-heritage"
              >
                <Columns3 size={16} strokeWidth={1.75} aria-hidden="true" className="text-ink-muted" />
                {t("blockEditor.table.deleteColumn")}
              </button>
              <div className="my-1 border-t" role="separator" />
              <button
                type="button"
                role="menuitem"
                onClick={() => run(() => editor.chain().focus().deleteTable().run())}
                className="flex w-full items-center gap-2 px-3 py-2 text-sm text-destructive hover:bg-heritage transition-colors text-left focus-visible:outline-none focus-visible:bg-heritage"
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
