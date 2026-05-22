import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Link from "@tiptap/extension-link";
import Placeholder from "@tiptap/extension-placeholder";
import Image from "@tiptap/extension-image";
import { Table } from "@tiptap/extension-table";
import { TableRow } from "@tiptap/extension-table-row";
import { TableHeader } from "@tiptap/extension-table-header";
import { TableCell } from "@tiptap/extension-table-cell";
import { CharacterCount } from "@tiptap/extension-character-count";
import { CodeBlockLowlight } from "@tiptap/extension-code-block-lowlight";
import DragHandle from "@tiptap/extension-drag-handle-react";
import { GripVertical } from "lucide-react";

import { Callout } from "./CalloutExtension";
import { YoutubeEmbed } from "./YoutubeExtension";
import { AudioEmbed } from "./AudioExtension";
import { EditorToolbar } from "./EditorToolbar";
import { lowlight } from "./lowlight";
import { useImageUpload } from "./useImageUpload";
import { useMediaPrompts } from "./useMediaPrompts";
import { cn } from "@/lib/utils";

interface RichTextEditorProps {
  content: string;
  onChange: (html: string) => void;
  placeholder?: string;
  editable?: boolean;
  /** Optional character cap. When set, displays a live count in the
   *  editor footer and enforces the limit via the CharacterCount
   *  extension's ``limit`` option (the cap matches the Pydantic
   *  ``max_length`` on the backing field — currently 500 000 for
   *  ``chapter_blocks.content``). Omit to show no counter at all. */
  characterLimit?: number;
}

export default function RichTextEditor({
  content,
  onChange,
  placeholder = "Start writing…",
  editable = true,
  characterLimit,
}: RichTextEditorProps) {
  const { t } = useTranslation();
  const imageUpload = useImageUpload();

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: { levels: [2, 3] },
        // Disable the bundled plain-text code block so the
        // syntax-highlighted ``CodeBlockLowlight`` registered below
        // owns the node name without a conflict.
        codeBlock: false,
      }),
      Link.configure({
        openOnClick: false,
        HTMLAttributes: { class: "text-primary underline cursor-pointer" },
      }),
      Placeholder.configure({ placeholder }),
      Image.configure({
        HTMLAttributes: {
          class: "rounded-lg max-w-full h-auto my-4",
        },
      }),
      Callout,
      YoutubeEmbed,
      AudioEmbed,
      // ``resizable: false`` deliberately. Cell-resize emits a
      // ``<colgroup>`` with inline ``style="width: Npx"`` attrs that
      // bleach strips on save, so a teacher who resizes a column
      // would lose the width on the next reload — silently. Tables
      // stay flexible-width by default until we extend the bleach
      // allowlist to keep ``col[style]`` through round-trips.
      Table.configure({ resizable: false, HTMLAttributes: { class: "equip-table" } }),
      TableRow,
      TableHeader,
      TableCell,
      CodeBlockLowlight.configure({
        lowlight,
        defaultLanguage: "plaintext",
        // ``language-X`` class on the inner ``<code>`` element is what
        // highlight.js's themes target in CSS, matching the convention
        // every Markdown renderer and docs theme uses.
        languageClassPrefix: "language-",
      }),
      // The extension is always loaded so ``editor.storage.characterCount.characters()``
      // is available for the footer. The ``limit`` option only enforces a
      // hard cap when ``characterLimit`` is set — passing ``null`` /
      // ``undefined`` keeps input unbounded.
      CharacterCount.configure({ limit: characterLimit ?? null }),
    ],
    content,
    editable,
    onUpdate: ({ editor: e }) => {
      onChange(e.getHTML());
    },
    editorProps: {
      attributes: {
        class: "prose max-w-none min-h-[200px] px-4 py-3 focus:outline-none",
      },
      handleDrop: (view, event, _slice, moved) =>
        imageUpload.handleDrop(view, event as DragEvent, moved),
      handlePaste: (view, event) =>
        imageUpload.handlePaste(view, event as ClipboardEvent),
    },
  });

  // Syncing the TipTap doc to an externally-controlled `content` prop
  // needs care: calling `setContent` echoes back through `onUpdate` if
  // we don't guard on the cached value, causing infinite update loops.
  const lastExternalContent = useRef(content);
  useEffect(() => {
    if (!editor || editor.isDestroyed) return;
    if (content === lastExternalContent.current) return;
    lastExternalContent.current = content;
    const currentHTML = editor.getHTML();
    if (currentHTML !== content) {
      editor.commands.setContent(content, { emitUpdate: false });
    }
  }, [content, editor]);

  const { setLink, addImage, addYoutube, addAudio } = useMediaPrompts(editor, imageUpload);

  // TipTap mutates the editor in place; reading
  // ``editor.storage.characterCount.characters()`` only refreshes on a
  // React re-render. Subscribing to the ``update`` event and bumping
  // ``tick`` is the cheapest way to drive that re-render.
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!editor) return;
    const handler = () => setTick((v) => v + 1);
    editor.on("update", handler);
    return () => {
      editor.off("update", handler);
    };
  }, [editor]);

  const count = useMemo(() => {
    if (!editor) return 0;
    return editor.storage.characterCount?.characters?.() ?? 0;
    // ``tick`` is intentional: it drives the recompute. See above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editor, tick]);

  if (!editor) return null;

  return (
    <div className="relative rounded-md border border-input bg-background">
      {editable && (
        <EditorToolbar
          editor={editor}
          uploading={imageUpload.uploading}
          onAddImage={addImage}
          onAddYoutube={addYoutube}
          onAddAudio={addAudio}
          onSetLink={setLink}
        />
      )}
      {editable && (
        // The Drag Handle extension positions itself relative to the
        // block under the caret / hover. Floating-UI defaults give us
        // a clean ``left``-of-block placement; nested=true so the
        // handle also targets list items and table cells, not just
        // top-level blocks.
        <DragHandle editor={editor} nested>
          <button
            type="button"
            aria-label={t("blockEditor.toolbar.dragHandle")}
            title={t("blockEditor.toolbar.dragHandle")}
            className="flex h-6 w-5 cursor-grab items-center justify-center rounded text-muted-foreground/60 transition-colors hover:bg-muted hover:text-foreground active:cursor-grabbing"
          >
            <GripVertical size={14} strokeWidth={1.75} aria-hidden="true" />
          </button>
        </DragHandle>
      )}
      <EditorContent editor={editor} />
      {editable && characterLimit !== undefined && (
        <CharacterCounter count={count} limit={characterLimit} t={t} />
      )}
    </div>
  );
}

/**
 * Footer counter showing ``N / LIMIT`` with editorial colour shifts as
 * the user nears the cap. Lives inside this module — purely
 * presentational, single caller, no need for its own file.
 */
function CharacterCounter({
  count,
  limit,
  t,
}: {
  count: number;
  limit: number;
  t: (k: string, opts?: Record<string, unknown>) => string;
}) {
  const ratio = count / limit;
  const tone = ratio >= 1 ? "destructive" : ratio >= 0.9 ? "warning" : "muted";
  return (
    <div
      aria-live="polite"
      className="flex justify-end border-t border-input px-3 py-1.5 text-xs tabular-nums"
    >
      <span
        className={cn(
          tone === "muted" && "text-muted-foreground",
          tone === "warning" && "text-warning",
          tone === "destructive" && "text-destructive font-medium",
        )}
      >
        {t("blockEditor.toolbar.characters", { count, limit })}
      </span>
    </div>
  );
}
