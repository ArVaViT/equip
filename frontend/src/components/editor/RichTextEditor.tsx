import { useEffect, useRef } from "react";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Link from "@tiptap/extension-link";
import Placeholder from "@tiptap/extension-placeholder";
import Image from "@tiptap/extension-image";
import { Table } from "@tiptap/extension-table";
import { TableRow } from "@tiptap/extension-table-row";
import { TableHeader } from "@tiptap/extension-table-header";
import { TableCell } from "@tiptap/extension-table-cell";

import { Callout } from "./CalloutExtension";
import { YoutubeEmbed } from "./YoutubeExtension";
import { AudioEmbed } from "./AudioExtension";
import { EditorToolbar } from "./EditorToolbar";
import { useImageUpload } from "./useImageUpload";
import { useMediaPrompts } from "./useMediaPrompts";

interface RichTextEditorProps {
  content: string;
  onChange: (html: string) => void;
  placeholder?: string;
  editable?: boolean;
}

export default function RichTextEditor({
  content,
  onChange,
  placeholder = "Start writing…",
  editable = true,
}: RichTextEditorProps) {
  const imageUpload = useImageUpload();

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: { levels: [2, 3] },
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
      // ``Table`` configures the table node + injects the cell-resize
      // handles. ``resizable: true`` exposes the drag-handles teachers
      // expect from Notion / Coda. The remaining table-* extensions are
      // peer nodes that must be registered alongside.
      Table.configure({ resizable: true, HTMLAttributes: { class: "equip-table" } }),
      TableRow,
      TableHeader,
      TableCell,
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

  if (!editor) return null;

  return (
    <div className="rounded-md border border-input bg-background">
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
      <EditorContent editor={editor} />
    </div>
  );
}
