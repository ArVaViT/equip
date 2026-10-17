import { useCallback, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { Editor } from "@tiptap/react";
import type { EditorView } from "@tiptap/pm/view";

import { storageService } from "@/services/storage";
import { toast } from "@/lib/toast";
import { describeUploadError, preflightUpload } from "@/lib/uploadError";
import { COURSE_ASSETS } from "@/lib/uploadLimits";
import { htmlHasText, preparePastedHtml, replaceImageSrc, type PreparedPaste } from "./pastedImages";

/**
 * Image upload state + handlers shared between the RichTextEditor's
 * toolbar button and its drag/drop/paste handlers.
 *
 * Keeping this in one place means the spinner state and the
 * success/failure toasts stay in sync regardless of which entry point
 * the user triggered.
 */
type PreparedRef = { current: PreparedPaste | null };

function takePrepared(ref: PreparedRef): PreparedPaste | null {
  const prepared = ref.current;
  ref.current = null;
  return prepared;
}

/** The HTML is not going in after all: let go of its `blob:` URLs. */
function discard(prepared: PreparedPaste | null): void {
  prepared?.files.forEach((_file, url) => URL.revokeObjectURL(url));
}

export function useImageUpload() {
  const { t } = useTranslation();
  // How many uploads are in flight. A paste from Word can start several;
  // a boolean went false when the first finished while the rest still ran.
  const [pending, setPending] = useState(0);
  const uploading = pending > 0;
  /** The most recent upload failure reason — surfaced by
   *  ``useMediaPrompts`` so the URL-fallback dialog can show the
   *  teacher *why* the upload failed (file too large, network
   *  error, storage rejected by bucket policy, etc.). Reset on the
   *  next successful upload or another failure. */
  const [lastError, setLastError] = useState<string | null>(null);

  const upload = useCallback(
    async (file: File): Promise<string | null> => {
      // The same checks the bucket will make — size cap, accepted
      // formats, HEIC — run here first so a 6 MB phone photo gets a
      // sentence in the teacher's language at once instead of an
      // English 413 after the upload. The reason is recorded so the
      // URL-fallback prompt can repeat it.
      const issue = preflightUpload(file, COURSE_ASSETS);
      if (issue) {
        setLastError(issue.message);
        toast({ title: t("editor.toast.imageUploadFailed"), description: issue.message, variant: "destructive" });
        return null;
      }
      setPending((n) => n + 1);
      setLastError(null);
      try {
        const url = await storageService.uploadContentImage(file);
        return url;
      } catch (error: unknown) {
        const message = describeUploadError(error, COURSE_ASSETS);
        setLastError(message);
        toast({ title: t("editor.toast.imageUploadFailed"), description: message, variant: "destructive" });
        return null;
      } finally {
        setPending((n) => n - 1);
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

  /** What `transformPastedHTML` made of the last pasted or dropped HTML.
   *  ProseMirror runs that transform before `handlePaste`/`handleDrop`
   *  (it parses first, then asks), so the transform only rewrites and the
   *  handlers below decide whether the pictures it found are used. */
  const preparedRef = useRef<PreparedPaste | null>(null);

  /** The HTML is going in: upload its pictures, say once what could not come. */
  const settle = useCallback(
    (view: EditorView, prepared: PreparedPaste | null) => {
      if (!prepared) return;
      if (prepared.skipped > 0) {
        toast({ title: t("editor.toast.pastedImagesSkipped") });
      }
      prepared.files.forEach((file, blobUrl) => {
        void upload(file)
          .then((url) => replaceImageSrc(view, blobUrl, url))
          .finally(() => URL.revokeObjectURL(blobUrl));
      });
    },
    [t, upload],
  );

  /** TipTap `editorProps.transformPastedHTML` impl — see `pastedImages.ts`. */
  const transformPastedHTML = useCallback((html: string): string => {
    discard(takePrepared(preparedRef));
    const prepared = preparePastedHtml(html);
    preparedRef.current = prepared;
    return prepared.html;
  }, []);

  /**
   * TipTap `editorProps.handleDrop` impl — uploads the dropped image and
   * inserts it at the drop coordinates.
   */
  const handleDrop = useCallback(
    (view: EditorView, event: DragEvent, moved: boolean): boolean => {
      const prepared = takePrepared(preparedRef);
      const file = moved ? undefined : event.dataTransfer?.files?.[0];
      if (!file || !file.type.startsWith("image/")) {
        // Not a picture file: ProseMirror inserts the dropped content
        // itself, pictures and all.
        if (!moved) settle(view, prepared);
        else discard(prepared);
        return false;
      }
      discard(prepared);
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
    [upload, settle],
  );

  /**
   * TipTap `editorProps.handlePaste` impl.
   *
   * A picture on the clipboard with no words beside it (a screenshot, an
   * image copied from a page) is uploaded and replaces the selection.
   * Anything with words is a piece of a document: Word, Excel and Pages
   * also put a picture of the copied range on the clipboard, and taking
   * that instead of the HTML pasted a screenshot of the text. The document
   * goes in as HTML; its own pictures are handled by `settle`.
   */
  const handlePaste = useCallback(
    (view: EditorView, event: ClipboardEvent): boolean => {
      const prepared = takePrepared(preparedRef);
      const data = event.clipboardData;
      if (data && !htmlHasText(data.getData("text/html"))) {
        for (const item of data.items ?? []) {
          if (!item.type.startsWith("image/")) continue;
          const file = item.getAsFile();
          if (!file) break;
          event.preventDefault();
          discard(prepared);
          void upload(file).then((url) => {
            if (!url || view.isDestroyed) return;
            const { schema } = view.state;
            const imageNode = schema.nodes.image;
            if (!imageNode) return;
            const node = imageNode.create({ src: url });
            view.dispatch(view.state.tr.replaceSelectionWith(node));
          });
          return true;
        }
      }
      settle(view, prepared);
      return false;
    },
    [upload, settle],
  );

  return { uploading, uploadAndInsert, handleDrop, handlePaste, transformPastedHTML, lastError };
}
