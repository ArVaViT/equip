import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import type { Editor } from "@tiptap/react";

import { usePrompt } from "@/components/ui/alert-dialog";
import { toast } from "@/lib/toast";
import type { useImageUpload } from "./useImageUpload";

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
    editor.chain().focus().extendMarkRange("link").setLink({ href: url }).run();
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
      // an existing URL instead of silently losing their action.
      const url = await prompt({
        title: t("editor.prompt.uploadFailedTitle"),
        description: t("editor.prompt.uploadFailedDescription"),
        placeholder: t("editor.prompt.imageUrlPlaceholder"),
        inputType: "url",
        confirmLabel: t("editor.prompt.uploadFailedConfirm"),
      });
      if (url) editor.chain().focus().setImage({ src: url }).run();
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

  return { setLink, addImage, addYoutube, addAudio };
}
