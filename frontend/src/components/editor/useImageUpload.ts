import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import type { Editor } from "@tiptap/react";
import type { EditorView } from "@tiptap/pm/view";

import { storageService } from "@/services/storage";
import { getErrorDetail } from "@/lib/errorDetail";
import { toast } from "@/lib/toast";

/** Largest image we accept on the upload path. The bucket itself
 *  enforces a higher cap server-side; this client check fails fast so
 *  teachers don't burn a network round-trip on an obviously-too-big
 *  file. 10 MB covers high-quality screenshots, screen-printed
 *  diagrams, and photos straight off a phone. */
const MAX_IMAGE_BYTES = 10 * 1024 * 1024;

/**
 * Image upload state + handlers shared between the RichTextEditor's
 * toolbar button and its drag/drop/paste handlers.
 *
 * Keeping this in one place means the spinner state and the
 * success/failure toasts stay in sync regardless of which entry point
 * the user triggered.
 */
export function useImageUpload() {
  const { t } = useTranslation();
  const [uploading, setUploading] = useState(false);
  /** The most recent upload failure reason — surfaced by
   *  ``useMediaPrompts`` so the URL-fallback dialog can show the
   *  teacher *why* the upload failed (file too large, network
   *  error, storage rejected by bucket policy, etc.). Reset on the
   *  next successful upload or another failure. */
  const [lastError, setLastError] = useState<string | null>(null);

  const upload = useCallback(
    async (file: File): Promise<string | null> => {
      // Upfront client-side checks so a 50 MB photo gets a clear
      // toast immediately instead of after a 30-second network
      // round trip. Both errors are recorded so the URL-fallback
      // prompt can repeat them.
      if (!file.type.startsWith("image/")) {
        const message = t("editor.toast.imageWrongType", { type: file.type || "?" });
        setLastError(message);
        toast({ title: message, variant: "destructive" });
        return null;
      }
      if (file.size > MAX_IMAGE_BYTES) {
        const message = t("editor.toast.imageTooLarge", {
          maxMb: Math.round(MAX_IMAGE_BYTES / 1024 / 1024),
        });
        setLastError(message);
        toast({ title: message, variant: "destructive" });
        return null;
      }
      setUploading(true);
      setLastError(null);
      try {
        const url = await storageService.uploadContentImage(file);
        return url;
      } catch (error: unknown) {
        const detail = getErrorDetail(error);
        const message = detail
          ? t("editor.toast.imageUploadFailedDetail", { detail })
          : t("editor.toast.imageUploadFailed");
        setLastError(message);
        toast({ title: message, variant: "destructive" });
        return null;
      } finally {
        setUploading(false);
      }
    },
    [t],
  );

  /**
   * Upload an image and insert it at the current editor cursor. Used by
   * the toolbar "Insert Image" button.
   */
  const uploadAndInsert = useCallback(
    async (file: File, editor: Editor): Promise<boolean> => {
      const url = await upload(file);
      if (!url) return false;
      editor.chain().focus().setImage({ src: url }).run();
      return true;
    },
    [upload],
  );

  /**
   * TipTap `editorProps.handleDrop` impl — uploads the dropped image and
   * inserts it at the drop coordinates.
   */
  const handleDrop = useCallback(
    (view: EditorView, event: DragEvent, moved: boolean): boolean => {
      if (moved || !event.dataTransfer?.files?.length) return false;
      const file = event.dataTransfer.files[0];
      if (!file || !file.type.startsWith("image/")) return false;
      event.preventDefault();
      void upload(file).then((url) => {
        if (!url) return;
        const { schema } = view.state;
        const imageNode = schema.nodes.image;
        if (!imageNode) return;
        const node = imageNode.create({ src: url });
        const pos = view.posAtCoords({ left: event.clientX, top: event.clientY });
        if (pos) {
          view.dispatch(view.state.tr.insert(pos.pos, node));
        }
      });
      return true;
    },
    [upload],
  );

  /**
   * TipTap `editorProps.handlePaste` impl — uploads the first pasted
   * image and replaces the current selection with it.
   */
  const handlePaste = useCallback(
    (view: EditorView, event: ClipboardEvent): boolean => {
      const items = event.clipboardData?.items;
      if (!items) return false;
      for (const item of items) {
        if (!item.type.startsWith("image/")) continue;
        event.preventDefault();
        const file = item.getAsFile();
        if (!file) return false;
        void upload(file).then((url) => {
          if (!url) return;
          const { schema } = view.state;
          const imageNode = schema.nodes.image;
          if (!imageNode) return;
          const node = imageNode.create({ src: url });
          view.dispatch(view.state.tr.replaceSelectionWith(node));
        });
        return true;
      }
      return false;
    },
    [upload],
  );

  return { uploading, uploadAndInsert, handleDrop, handlePaste, lastError };
}
