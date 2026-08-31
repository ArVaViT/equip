/**
 * Every action the backend records must have a word for it.
 *
 * The audit log renders `t("admin.audit.actionValue." + action)` with the
 * raw action as the fallback, so an untranslated action does not fail — it
 * just shows the identifier. In production the admin's own log read
 * "7 Обновление · 7 Запись · 6 resync_progress · 1 Создание ·
 * 1 appoint_director · 1 permanent_delete": machine names mixed in with
 * Russian, in the one place that exists to be read by a person.
 *
 * The catalogue had 8 of the 34 actions the code writes. This test reads the
 * backend and fails when the two drift again — including for actions added
 * by whoever comes next.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

import ru from "@/i18n/locales/ru.json";

const BACKEND = resolve(process.cwd(), "..", "backend", "app");

function pythonFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) return pythonFiles(full);
    return full.endsWith(".py") ? [full] : [];
  });
}

/**
 * Actions passed to `log_action`, whether named (`action="…"`) or
 * positional (`db, actor, "…", "resource"`). The positional form takes the
 * first string after the first two arguments — the second string is the
 * resource type, which is catalogued separately.
 */
function recordedActions(): Set<string> {
  const actions = new Set<string>();
  for (const file of pythonFiles(BACKEND)) {
    const source = readFileSync(file, "utf8");
    for (const call of source.matchAll(/log_action\(\s*([\s\S]*?)\n\s*\)/g)) {
      const args = call[1] ?? "";
      const named = /action\s*=\s*"([a-z_]+)"/.exec(args);
      if (named?.[1]) {
        actions.add(named[1]);
        continue;
      }
      const parts = args.split(/,\s*(?![^{[(]*[}\])])/).map((part) => part.trim());
      for (const part of parts.slice(2)) {
        const literal = /^"([a-z_]+)"$/.exec(part);
        if (literal?.[1]) {
          actions.add(literal[1]);
          break;
        }
      }
    }
  }
  return actions;
}

describe("audit log action labels", () => {
  it("has a word for every action the backend records", () => {
    const catalogued = new Set(Object.keys(ru.admin.audit.actionValue));
    const missing = [...recordedActions()].filter((a) => !catalogued.has(a)).sort();
    expect(missing, `untranslated audit actions: ${missing.join(", ")}`).toEqual([]);
  });

  it("finds the actions at all — a parser that matches nothing proves nothing", () => {
    // Without this, a regex that silently stops working would make the test
    // above pass for ever.
    const found = recordedActions();
    expect(found.size).toBeGreaterThan(20);
    expect(found).toContain("resync_progress");
    expect(found).toContain("create");
  });
});
