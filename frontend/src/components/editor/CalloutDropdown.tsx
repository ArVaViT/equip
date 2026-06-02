import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { Editor } from "@tiptap/react";
import {
  Info,
  BookOpen,
  Lightbulb,
  AlertTriangle,
  ChevronDown,
  ChevronsUpDown,
} from "lucide-react";

import { cn } from "@/lib/utils";
import type { CalloutVariant } from "./CalloutExtension";
import { useDropdownPosition } from "./useDropdownPosition";

interface CalloutChoice {
  value: CalloutVariant;
  icon: typeof Info;
  color: string;
}

const CALLOUT_VARIANTS: CalloutChoice[] = [
  { value: "info", icon: Info, color: "text-info" },
  { value: "verse", icon: BookOpen, color: "text-accent" },
  { value: "takeaway", icon: Lightbulb, color: "text-success" },
  { value: "warning", icon: AlertTriangle, color: "text-warning" },
  { value: "toggle", icon: ChevronsUpDown, color: "text-ink-muted" },
];

// Static i18n key lookup — exposes each literal to the keyCoverage
// static check that template-literal callsites silently bypass.
const CALLOUT_LABEL_KEYS: Record<CalloutVariant, string> = {
  info: "blockEditor.callout.info",
  verse: "blockEditor.callout.verse",
  takeaway: "blockEditor.callout.takeaway",
  warning: "blockEditor.callout.warning",
  toggle: "blockEditor.callout.toggle",
};

/**
 * Dropdown menu for inserting or removing a Callout block. Lives next
 * to the formatting toolbar but owns its own open/close state and
 * click-outside handling — the parent toolbar just renders it.
 */
export function CalloutDropdown({
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
  // Panel width matches the ``w-52`` tailwind class on the menu.
  const { alignClass } = useDropdownPosition(open, triggerRef, 208);

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

  const insertCallout = (variant: CalloutVariant) => {
    editor.chain().focus().setCallout({ variant }).run();
    setOpen(false);
  };

  const removeCallout = () => {
    editor.chain().focus().unsetCallout().run();
    setOpen(false);
  };

  const isActive = editor.isActive("callout");

  return (
    <div className="relative" ref={containerRef}>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        title={t("blockEditor.callout.trigger")}
        aria-label={t("blockEditor.callout.trigger")}
        aria-haspopup="menu"
        aria-expanded={open}
        // ADR-0011 Wave 7 — toolbar-button vocabulary migrated to v2.
        className={cn(
          "flex items-center gap-0.5 rounded p-1.5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2",
          isActive
            ? "bg-brand/20 text-brand ring-1 ring-inset ring-brand/30"
            : "text-ink-muted hover:bg-heritage hover:text-ink",
        )}
      >
        <Info size={iconSize} strokeWidth={1.75} aria-hidden="true" />
        <ChevronDown size={12} strokeWidth={1.75} aria-hidden="true" />
      </button>
      {open && (
        <div
          role="menu"
          aria-label={t("blockEditor.callout.trigger")}
          className={cn(
            // ADR-0011 Wave 7 — bg-surface -> bg-surface-elevated.
            "absolute top-full z-20 mt-1 w-52 rounded-md border bg-surface-elevated py-1 shadow-lg",
            alignClass,
          )}
        >
          {CALLOUT_VARIANTS.map((v) => {
            const Icon = v.icon;
            return (
              <button
                key={v.value}
                type="button"
                role="menuitem"
                onClick={() => insertCallout(v.value)}
                className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-heritage transition-colors text-left focus-visible:outline-none focus-visible:bg-heritage"
              >
                <Icon size={16} className={v.color} aria-hidden="true" />
                {t(CALLOUT_LABEL_KEYS[v.value])}
              </button>
            );
          })}
          {isActive && (
            <>
              <div className="my-1 border-t" role="separator" />
              <button
                type="button"
                role="menuitem"
                onClick={removeCallout}
                className="flex w-full items-center gap-2 px-3 py-2 text-sm text-destructive hover:bg-heritage transition-colors text-left focus-visible:outline-none focus-visible:bg-heritage"
              >
                {t("blockEditor.callout.remove")}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
