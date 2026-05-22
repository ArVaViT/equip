import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import type { Editor } from "@tiptap/react";

import { usePrompt } from "@/components/ui/alert-dialog";
import { toast } from "@/lib/toast";
import type { useImageUpload } from "./useImageUpload";

/**
 * Accept "naked" hostnames (``example.com/page``) by prepending
 * ``https://`` when the user didn't include a scheme. Then validate
 * the result parses as a real URL with an http(s) scheme. Returns
 * the normalised URL string or ``null`` if the input is unusable.
 *
 * Without this, a teacher who types ``example.com`` ends up with a
 * relative ``<a href="example.com">`` that resolves against the
 * chapter URL — broken in production. We catch the common case here
 * so the user sees an immediate toast instead of discovering it as
 * a student.
 */
function normalizeAndValidateUrl(raw: string): string | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const candidate =
    /^[a-z][a-z0-9+.-]*:/i.test(trimmed) || trimmed.startsWith("//")
      ? trimmed
      : `https://${trimmed}`;
  try {
    const parsed = new URL(candidate);
    // Only http(s) for chapter links — ``mailto:`` / ``tel:`` are
    // valid URL schemes but we don't want them silently sneaking
    // through this code path.
    if (parsed.protocol !== "https:" && parsed.protocol !== "http:") {
      return null;
    }
    return parsed.toString();
  } catch {
    return null;
  }
}

/**
 * Bundles the "media insert" handlers that all rely on a URL prompt:
 * link, image (with upload + URL fallback), YouTube, audio.
 *
 * Pulling these out of the RichTextEditor component keeps the component
 * focused on rendering and lets the handlers be replaced or tested in
 * isolation if needed.
 */
export function useMediaPrompts(
  editor: Editor | null,
  imageUpload: ReturnType<typeof useImageUpload>,
) {
  const { t } = useTranslation();
  const prompt = usePrompt();

  const setLink = useCallback(async () => {
    if (!editor) return;
    const previousUrl = editor.getAttributes("link").href as string | undefined;
    const url = await prompt({
      title: t("editor.prompt.addLinkTitle"),
      description: t("editor.prompt.addLinkDescription"),
      defaultValue: previousUrl ?? "https://",
      placeholder: t("editor.prompt.imageUrlPlaceholder"),
      inputType: "url",
      confirmLabel: t("editor.prompt.addLinkConfirm"),
    });
    if (url === null) return;
    if (url === "") {
      editor.chain().focus().extendMarkRange("link").unsetLink().run();
      return;
    }
    const normalized = normalizeAndValidateUrl(url);
    if (!normalized) {
      toast({
        title: t("editor.toast.invalidUrl"),
        variant: "destructive",
      });
      return;
    }
    editor.chain().focus().extendMarkRange("link").setLink({ href: normalized }).run();
  }, [editor, prompt, t]);

  const addImage = useCallback(() => {
    if (!editor) return;
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "image/*";
    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file) return;
      const inserted = await imageUpload.uploadAndInsert(file, editor);
      if (inserted) return;
      // Upload failed: give the user an escape hatch so they can paste
      // an existing URL instead of silently losing their action. The
      // dialog description shows the actual failure reason (file too
      // big, wrong type, network error) when available so the teacher
      // knows whether to try a different file or just use a URL.
      const fallbackReason = imageUpload.lastError;
      const url = await prompt({
        title: t("editor.prompt.uploadFailedTitle"),
        description: fallbackReason ?? t("editor.prompt.uploadFailedDescription"),
        placeholder: t("editor.prompt.imageUrlPlaceholder"),
        inputType: "url",
        confirmLabel: t("editor.prompt.uploadFailedConfirm"),
      });
      if (!url) return;
      // The URL-fallback path benefits from the same scheme-validation
      // the link prompt uses (#510). A teacher pasting ``example.com``
      // wouldn't notice the relative URL until a student saw the
      // broken image.
      const normalized = normalizeAndValidateUrl(url);
      if (!normalized) {
        toast({ title: t("editor.toast.invalidUrl"), variant: "destructive" });
        return;
      }
      editor.chain().focus().setImage({ src: normalized }).run();
    };
    input.click();
  }, [editor, imageUpload, prompt, t]);

  const addYoutube = useCallback(async () => {
    if (!editor) return;
    const url = await prompt({
      title: t("editor.prompt.youtubeTitle"),
      description: t("editor.prompt.youtubeDescription"),
      placeholder: t("editor.prompt.youtubePlaceholder"),
      inputType: "url",
      confirmLabel: t("editor.prompt.youtubeConfirm"),
    });
    if (!url) return;
    editor.chain().focus().setYoutubeVideo({ src: url }).run();
  }, [editor, prompt, t]);

  const addAudio = useCallback(async () => {
    if (!editor) return;
    const url = await prompt({
      title: t("editor.prompt.audioTitle"),
      description: t("editor.prompt.audioDescription"),
      placeholder: t("editor.prompt.audioPlaceholder"),
      inputType: "url",
      confirmLabel: t("editor.prompt.audioConfirm"),
    });
    if (!url) return;
    const ok = editor.chain().focus().setAudio({ src: url }).run();
    if (!ok) toast({ title: t("editor.toast.audioUrlInvalid"), variant: "destructive" });
  }, [editor, prompt, t]);

  const addMath = useCallback(async () => {
    if (!editor) return;
    // Teachers can also auto-trigger inline math by typing ``$x^2$``
    // directly — this prompt is the discoverability path for users
    // who don't know the shortcut. Stored shape:
    //   <span data-type="inlineMath" data-latex="x^2"></span>
    // KaTeX renders the latex via the extension's NodeView in-editor
    // and via the post-render hook on the chapter view.
    const latex = await prompt({
      title: t("editor.prompt.mathTitle"),
      description: t("editor.prompt.mathDescription"),
      placeholder: t("editor.prompt.mathPlaceholder"),
      confirmLabel: t("editor.prompt.mathConfirm"),
    });
    if (!latex) return;
    editor
      .chain()
      .focus()
      .insertContent({
        type: "inlineMath",
        attrs: { latex, evaluate: "no", display: "no" },
      })
      .run();
  }, [editor, prompt, t]);

  return { setLink, addImage, addYoutube, addAudio, addMath };
}
