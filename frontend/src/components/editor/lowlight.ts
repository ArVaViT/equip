import { createLowlight } from "lowlight";
import bash from "highlight.js/lib/languages/bash";
import javascript from "highlight.js/lib/languages/javascript";
import json from "highlight.js/lib/languages/json";
import markdown from "highlight.js/lib/languages/markdown";
import python from "highlight.js/lib/languages/python";
import sql from "highlight.js/lib/languages/sql";
import typescript from "highlight.js/lib/languages/typescript";
import xml from "highlight.js/lib/languages/xml";

/**
 * Curated lowlight instance for the rich-text editor's
 * ``CodeBlockLowlight`` extension. Languages are imported one by one
 * (rather than pulling lowlight's "common" preset, which loads 35+
 * grammars) to keep the bundle weight bounded — every language is a
 * few KB on its own and most chapter-block use cases stay inside the
 * eight below.
 *
 * Order of the list = order in the ``CODE_LANGUAGES`` picker below.
 * "plaintext" is implicit — selecting it tells CodeBlockLowlight to
 * render the block without any token-level highlighting.
 */
export const lowlight = createLowlight();

lowlight.register("bash", bash);
lowlight.register("javascript", javascript);
lowlight.register("json", json);
lowlight.register("markdown", markdown);
lowlight.register("python", python);
lowlight.register("sql", sql);
lowlight.register("typescript", typescript);
lowlight.register("html", xml);

export const CODE_LANGUAGES = [
  "plaintext",
  "bash",
  "html",
  "javascript",
  "json",
  "markdown",
  "python",
  "sql",
  "typescript",
] as const;

export type CodeLanguage = (typeof CODE_LANGUAGES)[number];

/** Friendly display label per language code. Kept here so the toolbar
 *  dropdown stays a pure presentational component. */
export const CODE_LANGUAGE_LABELS: Record<CodeLanguage, string> = {
  plaintext: "Plain",
  bash: "Bash",
  html: "HTML",
  javascript: "JavaScript",
  json: "JSON",
  markdown: "Markdown",
  python: "Python",
  sql: "SQL",
  typescript: "TypeScript",
};
