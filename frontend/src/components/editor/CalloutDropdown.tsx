import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { Editor } from "@tiptap/react";
import {
  Info,
  BookOpen,
  Lightbulb,
  AlertTriangle,
  ChevronDown,
} from "lucide-react";

import { cn } from "@/lib/utils";
import type { CalloutVariant } from "./CalloutExtension";

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
];

// Static i18n key lookup — exposes each literal to the keyCoverage
// static check that template-literal callsites silently bypass.
const CALLOUT_LABEL_KEYS: Record<CalloutVariant, string> = {
  info: "blockEditor.callout.info",
  verse: "blockEditor.callout.verse",
  takeaway: "blockEditor.callout.takeaway",
  warning: "blockEditor.callout.warning",
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
        type="button"
        onClick={() => setOpen((v) => !v)}
        title={t("blockEditor.callout.trigger")}
        aria-label={t("blockEditor.callout.trigger")}
        aria-haspopup="menu"
        aria-expanded={open}
        className={cn(
          "flex items-center gap-0.5 rounded p-1.5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
          isActive
            ? "bg-primary/15 text-primary"
            : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
        )}
      >
        <Info size={iconSize} strokeWidth={1.75} aria-hidden="true" />
        <ChevronDown size={12} strokeWidth={1.75} aria-hidden="true" />
      </button>
      {open && (
        <div
          role="menu"
          aria-label={t("blockEditor.callout.trigger")}
          className="absolute left-0 top-full z-20 mt-1 w-52 rounded-md border bg-background py-1 shadow-lg"
        >
          {CALLOUT_VARIANTS.map((v) => {
            const Icon = v.icon;
            return (
              <button
                key={v.value}
                type="button"
                role="menuitem"
                onClick={() => insertCallout(v.value)}
                className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-muted transition-colors text-left focus-visible:outline-none focus-visible:bg-muted"
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
                className="flex w-full items-center gap-2 px-3 py-2 text-sm text-destructive hover:bg-muted transition-colors text-left focus-visible:outline-none focus-visible:bg-muted"
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
