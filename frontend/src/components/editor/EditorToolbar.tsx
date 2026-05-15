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
} from "lucide-react";

import { cn } from "@/lib/utils";
import { CalloutDropdown } from "./CalloutDropdown";

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
      className={cn(
        "rounded p-1.5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
        active
          ? "bg-primary/15 text-primary"
          : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
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
  return <div role="separator" aria-orientation="vertical" className="mx-1 h-5 w-px bg-border" />;
}

interface EditorToolbarProps {
  editor: Editor;
  uploading: boolean;
  onAddImage: () => void;
  onAddYoutube: () => void;
  onAddAudio: () => void;
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
  onSetLink,
}: EditorToolbarProps) {
  const { t } = useTranslation();
  return (
    <div
      role="toolbar"
      aria-label={t("blockEditor.toolbar.ariaLabel")}
      className="flex flex-wrap items-center gap-0.5 border-b border-input px-2 py-1.5"
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
