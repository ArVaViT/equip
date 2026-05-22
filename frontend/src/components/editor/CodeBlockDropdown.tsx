import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { Editor } from "@tiptap/react";
import { Code2, ChevronDown, Check } from "lucide-react";

import { cn } from "@/lib/utils";
import { CODE_LANGUAGES, CODE_LANGUAGE_LABELS, type CodeLanguage } from "./lowlight";
import { useDropdownPosition } from "./useDropdownPosition";

/**
 * Toolbar slot for code blocks. Mirrors the ``TableDropdown`` pattern:
 *
 * - Outside a code block: clicking the button inserts a new code block
 *   in ``plaintext`` (the default). No menu is shown — keeps the path
 *   to "first code block" one click.
 * - Inside a code block: clicking opens a language picker. Selecting
 *   a language updates the block's ``language`` attribute, which
 *   ``CodeBlockLowlight`` uses to drive highlight.js tokenisation.
 */
export function CodeBlockDropdown({
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
  // Panel width matches the ``w-44`` tailwind class on the menu.
  const { alignClass } = useDropdownPosition(open, triggerRef, 176);

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

  const isInCodeBlock = editor.isActive("codeBlock");
  const currentLanguage: CodeLanguage =
    (editor.getAttributes("codeBlock")?.language as CodeLanguage | undefined) ?? "plaintext";

  const triggerClick = () => {
    if (!isInCodeBlock) {
      editor.chain().focus().toggleCodeBlock({ language: "plaintext" }).run();
      return;
    }
    setOpen((v) => !v);
  };

  const pickLanguage = (lang: CodeLanguage) => {
    editor.chain().focus().updateAttributes("codeBlock", { language: lang }).run();
    setOpen(false);
  };

  return (
    <div className="relative" ref={containerRef}>
      <button
        ref={triggerRef}
        type="button"
        onClick={triggerClick}
        title={
          isInCodeBlock
            ? t("blockEditor.codeBlock.changeLanguage")
            : t("blockEditor.codeBlock.insert")
        }
        aria-label={
          isInCodeBlock
            ? t("blockEditor.codeBlock.changeLanguage")
            : t("blockEditor.codeBlock.insert")
        }
        aria-haspopup={isInCodeBlock ? "menu" : undefined}
        aria-expanded={isInCodeBlock ? open : undefined}
        className={cn(
          "flex items-center gap-0.5 rounded p-1.5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
          isInCodeBlock
            ? "bg-primary/15 text-primary"
            : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
        )}
      >
        <Code2 size={iconSize} strokeWidth={1.75} aria-hidden="true" />
        {isInCodeBlock && <ChevronDown size={12} strokeWidth={1.75} aria-hidden="true" />}
      </button>
      {open && isInCodeBlock && (
        <div
          role="menu"
          aria-label={t("blockEditor.codeBlock.changeLanguage")}
          className={cn(
            "absolute top-full z-20 mt-1 w-44 rounded-md border bg-background py-1 shadow-lg",
            alignClass,
          )}
        >
          {CODE_LANGUAGES.map((lang) => (
            <button
              key={lang}
              type="button"
              role="menuitemradio"
              aria-checked={lang === currentLanguage}
              onClick={() => pickLanguage(lang)}
              className={cn(
                "flex w-full items-center justify-between gap-2 px-3 py-1.5 text-sm hover:bg-muted transition-colors text-left focus-visible:outline-none focus-visible:bg-muted",
                lang === currentLanguage && "font-medium",
              )}
            >
              <span>{CODE_LANGUAGE_LABELS[lang]}</span>
              {lang === currentLanguage && (
                <Check size={14} strokeWidth={1.75} aria-hidden="true" className="text-primary" />
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
