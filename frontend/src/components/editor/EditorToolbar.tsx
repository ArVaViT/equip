import type { Editor } from "@tiptap/react";
import { useTranslation } from "react-i18next";
import {
  Bold,
  Italic,
  Heading2,
  Heading3,
  List,
  ListOrdered,
  Quote,
  Link2,
  Loader2,
  Undo2,
  Redo2,
  ImageIcon,
  Video as Youtube,
  Headphones,
  Minus,
  Sigma,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { CalloutDropdown } from "./CalloutDropdown";
import { CodeBlockDropdown } from "./CodeBlockDropdown";
import { TableDropdown } from "./TableDropdown";

const TOOLBAR_ICON_SIZE = 18;

function ToolbarButton({
  onClick,
  active = false,
  disabled = false,
  children,
  title,
  /** Toggle buttons (bold/italic/list/etc.) communicate their on/off
   *  state via aria-pressed. One-shot buttons (insert image, undo) leave
   *  this undefined so AT doesn't announce a pointless pressed state. */
  pressable = false,
}: {
  onClick: () => void;
  active?: boolean;
  disabled?: boolean;
  children: React.ReactNode;
  title: string;
  pressable?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      aria-label={title}
      aria-pressed={pressable ? active : undefined}
      // ADR-0011 Wave 7 — migrated to v2 vocabulary.
      // ring-ring -> ring-brand, bg-primary/20 -> bg-brand/20,
      // text-primary -> text-brand, ring-primary/30 -> ring-brand/30,
      // text-muted-foreground -> text-ink-muted, hover:bg-accent ->
      // hover:bg-heritage, hover:text-accent-foreground -> hover:text-ink.
      className={cn(
        "rounded p-1.5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2",
        active
          ? "bg-brand/20 text-brand ring-1 ring-inset ring-brand/30"
          : "text-ink-muted hover:bg-heritage hover:text-ink",
        disabled && "cursor-not-allowed opacity-40",
      )}
    >
      {children}
    </button>
  );
}

function ToolbarDivider() {
  // role="separator" so AT treats the divider as a group boundary rather
  // than as a visible-but-unannounced element.
  // ADR-0011 Wave 7 — bg-border -> bg-edge.
  return <div role="separator" aria-orientation="vertical" className="mx-1 h-5 w-px bg-edge" />;
}

interface EditorToolbarProps {
  editor: Editor;
  uploading: boolean;
  onAddImage: () => void;
  onAddYoutube: () => void;
  onAddAudio: () => void;
  onAddMath: () => void;
  onSetLink: () => void;
}

/**
 * Full formatting toolbar for the RichTextEditor. Receives the active
 * editor instance plus media callbacks that open modal prompts —
 * keeping media flows out of this component lets it focus on direct
 * editor commands.
 */
export function EditorToolbar({
  editor,
  uploading,
  onAddImage,
  onAddYoutube,
  onAddAudio,
  onAddMath,
  onSetLink,
}: EditorToolbarProps) {
  const { t } = useTranslation();
  return (
    <div
      role="toolbar"
      aria-label={t("blockEditor.toolbar.ariaLabel")}
      // ``sticky top-0`` keeps the toolbar visible while teachers
      // scroll long chapters. ``z-20`` sits above prose content but
      // below modal/dialog overlays (z-50). ``bg-background`` is
      // required for sticky semi-transparent flicker over the
      // ProseMirror surface below.
      //
      // Mobile responsiveness: at small widths the 17+ button row
      // becomes a horizontal scroller (``flex-nowrap overflow-x-auto``)
      // rather than wrapping to 2-3 lines. ``sm:flex-wrap`` restores
      // the original wrap behaviour above the ``sm`` breakpoint where
      // there's enough room. ``no-scrollbar`` (utility added in
      // index.css) hides the visible bar — touch scroll still works.
      // ADR-0011 Wave 7 — border-input -> border-edge-strong, bg-background -> bg-surface.
      className="sticky top-0 z-20 flex flex-nowrap items-center gap-0.5 overflow-x-auto border-b border-edge-strong bg-surface px-2 py-1.5 no-scrollbar sm:flex-wrap sm:overflow-x-visible"
    >
      <ToolbarButton
        onClick={() => editor.chain().focus().toggleBold().run()}
        active={editor.isActive("bold")}
        pressable
        title={t("blockEditor.toolbar.bold")}
      >
        <Bold size={TOOLBAR_ICON_SIZE} strokeWidth={1.75} aria-hidden="true" />
      </ToolbarButton>

      <ToolbarButton
        onClick={() => editor.chain().focus().toggleItalic().run()}
        active={editor.isActive("italic")}
        pressable
        title={t("blockEditor.toolbar.italic")}
      >
        <Italic size={TOOLBAR_ICON_SIZE} strokeWidth={1.75} aria-hidden="true" />
      </ToolbarButton>

      <ToolbarDivider />

      <ToolbarButton
        onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
        active={editor.isActive("heading", { level: 2 })}
        pressable
        title={t("blockEditor.toolbar.heading2")}
      >
        <Heading2 size={TOOLBAR_ICON_SIZE} strokeWidth={1.75} aria-hidden="true" />
      </ToolbarButton>

      <ToolbarButton
        onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
        active={editor.isActive("heading", { level: 3 })}
        pressable
        title={t("blockEditor.toolbar.heading3")}
      >
        <Heading3 size={TOOLBAR_ICON_SIZE} strokeWidth={1.75} aria-hidden="true" />
      </ToolbarButton>

      <ToolbarDivider />

      <ToolbarButton
        onClick={() => editor.chain().focus().toggleBulletList().run()}
        active={editor.isActive("bulletList")}
        pressable
        title={t("blockEditor.toolbar.bulletList")}
      >
        <List size={TOOLBAR_ICON_SIZE} strokeWidth={1.75} aria-hidden="true" />
      </ToolbarButton>

      <ToolbarButton
        onClick={() => editor.chain().focus().toggleOrderedList().run()}
        active={editor.isActive("orderedList")}
        pressable
        title={t("blockEditor.toolbar.numberedList")}
      >
        <ListOrdered size={TOOLBAR_ICON_SIZE} strokeWidth={1.75} aria-hidden="true" />
      </ToolbarButton>

      <ToolbarButton
        onClick={() => editor.chain().focus().toggleBlockquote().run()}
        active={editor.isActive("blockquote")}
        pressable
        title={t("blockEditor.toolbar.blockquote")}
      >
        <Quote size={TOOLBAR_ICON_SIZE} strokeWidth={1.75} aria-hidden="true" />
      </ToolbarButton>

      <ToolbarButton
        onClick={() => editor.chain().focus().setHorizontalRule().run()}
        title={t("blockEditor.toolbar.horizontalRule")}
      >
        <Minus size={TOOLBAR_ICON_SIZE} strokeWidth={1.75} aria-hidden="true" />
      </ToolbarButton>

      <ToolbarDivider />

      <CalloutDropdown editor={editor} iconSize={TOOLBAR_ICON_SIZE} />

      <TableDropdown editor={editor} iconSize={TOOLBAR_ICON_SIZE} />

      <CodeBlockDropdown editor={editor} iconSize={TOOLBAR_ICON_SIZE} />

      <ToolbarDivider />

      <ToolbarButton onClick={onAddImage} disabled={uploading} title={t("blockEditor.toolbar.insertImage")}>
        {uploading ? (
          <Loader2 size={TOOLBAR_ICON_SIZE} strokeWidth={1.75} className="animate-spin" aria-hidden="true" />
        ) : (
          <ImageIcon size={TOOLBAR_ICON_SIZE} strokeWidth={1.75} aria-hidden="true" />
        )}
      </ToolbarButton>

      <ToolbarButton onClick={onAddYoutube} title={t("blockEditor.toolbar.insertYoutube")}>
        <Youtube size={TOOLBAR_ICON_SIZE} strokeWidth={1.75} aria-hidden="true" />
      </ToolbarButton>

      <ToolbarButton onClick={onAddAudio} title={t("blockEditor.toolbar.insertAudio")}>
        <Headphones size={TOOLBAR_ICON_SIZE} strokeWidth={1.75} aria-hidden="true" />
      </ToolbarButton>

      <ToolbarButton onClick={onAddMath} title={t("blockEditor.toolbar.insertMath")}>
        <Sigma size={TOOLBAR_ICON_SIZE} strokeWidth={1.75} aria-hidden="true" />
      </ToolbarButton>

      <ToolbarButton
        onClick={onSetLink}
        active={editor.isActive("link")}
        pressable
        title={t("blockEditor.toolbar.link")}
      >
        <Link2 size={TOOLBAR_ICON_SIZE} strokeWidth={1.75} aria-hidden="true" />
      </ToolbarButton>

      <ToolbarDivider />

      <ToolbarButton
        onClick={() => editor.chain().focus().undo().run()}
        disabled={!editor.can().undo()}
        title={t("blockEditor.toolbar.undo")}
      >
        <Undo2 size={TOOLBAR_ICON_SIZE} strokeWidth={1.75} aria-hidden="true" />
      </ToolbarButton>

      <ToolbarButton
        onClick={() => editor.chain().focus().redo().run()}
        disabled={!editor.can().redo()}
        title={t("blockEditor.toolbar.redo")}
      >
        <Redo2 size={TOOLBAR_ICON_SIZE} strokeWidth={1.75} aria-hidden="true" />
      </ToolbarButton>
    </div>
  );
}
