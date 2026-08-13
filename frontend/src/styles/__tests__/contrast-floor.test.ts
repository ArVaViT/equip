/**
 * The readability floor, computed from the palette rather than asserted.
 *
 * This exists because of a specific failure, and the failure is instructive.
 * The footer was designed on the principle Apple's own footer uses — one type
 * size, hierarchy carried entirely by steps of opacity. The colophon line was
 * set at 40% of `ink-inverted`, which looked right and measured **3.6:1**. The
 * a11y suite caught that one because it happens to run on the home page.
 *
 * It did not catch the other forty-seven. `ink-muted` is *already* the quietest
 * readable colour in the palette; every `text-ink-muted/70`, `/60`, `/40` in
 * the product was below AA in both themes, on pages no a11y test visits. The
 * rule that falls out is short enough to remember:
 *
 *   **A muted token takes no alpha modifier. There is nothing quieter than
 *   quiet.** Something that needs less weight than `ink-muted` needs a
 *   different mechanism — smaller, further down, or gone — not a paler colour.
 *
 * Two things are pinned here, and the first is why the second is trustworthy:
 *
 * 1. The palette itself clears 4.5:1 at full strength, recomputed from
 *    `index.css` on every run. A future warm-up of `--muted-foreground` that
 *    quietly drops it under the floor fails here, at the source.
 * 2. No source file re-introduces an alpha modifier on a muted token, and any
 *    alpha rung that *is* used on `ink-inverted` still clears the floor against
 *    the ink it sits on.
 *
 * The maths is sRGB relative luminance (WCAG 2.1 §1.4.3) with straight alpha
 * compositing. It was validated against axe's own report of the footer bug:
 * axe measured `#797570` at 3.6:1, this file computes `#797572` at 3.61:1.
 */
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { readdirSync, statSync } from "node:fs";

const HERE = dirname(fileURLToPath(import.meta.url));
const INDEX_CSS = resolve(HERE, "..", "..", "index.css");
const SRC = resolve(HERE, "..", "..");

const AA_BODY = 4.5;

type Rgb = [number, number, number];

/** `42 50% 96%` — the channel triple Tailwind wraps in `hsl(...)`. */
function parseHslChannels(value: string): Rgb {
  const m = value.trim().match(/^([\d.]+)\s+([\d.]+)%\s+([\d.]+)%$/);
  if (!m) throw new Error(`not an HSL channel triple: "${value}"`);
  const h = Number(m[1]) / 360;
  const s = Number(m[2]) / 100;
  const l = Number(m[3]) / 100;
  if (s === 0) return [l * 255, l * 255, l * 255];
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
  const p = 2 * l - q;
  const channel = (t: number) => {
    if (t < 0) t += 1;
    if (t > 1) t -= 1;
    if (t < 1 / 6) return p + (q - p) * 6 * t;
    if (t < 1 / 2) return q;
    if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
    return p;
  };
  return [channel(h + 1 / 3) * 255, channel(h) * 255, channel(h - 1 / 3) * 255];
}

function linearise(c: number): number {
  const s = c / 255;
  return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}

function luminance([r, g, b]: Rgb): number {
  return 0.2126 * linearise(r) + 0.7152 * linearise(g) + 0.0722 * linearise(b);
}

function contrast(a: Rgb, b: Rgb): number {
  const la = luminance(a);
  const lb = luminance(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

/** Straight alpha compositing — what `hsl(var(--x) / 0.4)` actually paints. */
function over(fg: Rgb, bg: Rgb, alpha: number): Rgb {
  return [0, 1, 2].map((i) => fg[i]! * alpha + bg[i]! * (1 - alpha)) as Rgb;
}

/**
 * Reads one theme block out of `index.css`. The light theme lives in `:root`
 * and the dark one in `.dark`; both declare the same names, so the last match
 * inside the requested block is the value that theme actually renders with.
 */
function palette(block: "root" | "dark"): Record<string, Rgb> {
  const css = readFileSync(INDEX_CSS, "utf8");
  const start = css.indexOf(block === "root" ? ":root {" : ".dark {");
  expect(start, `${block} block not found in index.css`).toBeGreaterThan(-1);
  const end = css.indexOf("\n  }", start);
  const body = css.slice(start, end === -1 ? undefined : end);
  const out: Record<string, Rgb> = {};
  for (const [, name, value] of body.matchAll(/--([\w-]+):\s*([^;]+);/g)) {
    try {
      out[name!] = parseHslChannels(value!);
    } catch {
      // Non-colour custom properties (durations, easings, radii) live here too.
    }
  }
  return out;
}

function sourceFiles(dir: string, acc: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = resolve(dir, entry);
    if (statSync(full).isDirectory()) {
      if (entry !== "node_modules") sourceFiles(full, acc);
    } else if (/\.tsx?$/.test(entry) && !full.includes("__tests__")) {
      acc.push(full);
    }
  }
  return acc;
}

describe("the palette clears the floor at full strength", () => {
  for (const theme of ["root", "dark"] as const) {
    it(`${theme}: ink-muted is readable on both background and card`, () => {
      const p = palette(theme);
      // `--color-ink-muted` bridges to `--muted-foreground`; `ink` to
      // `--foreground`; `ink-inverted` to `--primary-foreground`.
      for (const surface of ["background", "card"] as const) {
        const ratio = contrast(p["muted-foreground"]!, p[surface]!);
        expect(
          ratio,
          `ink-muted on ${surface} in ${theme} is ${ratio.toFixed(2)}:1 — ` +
            `below AA. The muted rung is the floor; it cannot be lowered.`,
        ).toBeGreaterThanOrEqual(AA_BODY);
      }
    });
  }
});

describe("no source file paints below the floor", () => {
  const FILES = sourceFiles(SRC);

  it("finds source to scan (an empty sweep would pass silently)", () => {
    expect(FILES.length).toBeGreaterThan(200);
  });

  it("never puts an alpha modifier on a muted token", () => {
    const offenders: string[] = [];
    for (const file of FILES) {
      const text = readFileSync(file, "utf8");
      for (const [match] of text.matchAll(/text-(?:ink-muted|muted-foreground)\/\d+/g)) {
        offenders.push(`${file.replace(SRC, "src")}: ${match}`);
      }
    }
    expect(
      offenders,
      "There is nothing quieter than ink-muted. Every one of these measures " +
        "below 4.5:1 in both themes — use size, position or removal instead:\n" +
        offenders.join("\n"),
    ).toEqual([]);
  });

  it("keeps every ink-inverted alpha rung above the floor over ink", () => {
    // `ink-inverted` on `bg-ink` is the footer's inversion, and there the
    // opacity ladder is legitimate — the contrast headroom is enormous. It is
    // legitimate only up to a point, and this computes where that point is.
    const failures: string[] = [];
    for (const theme of ["root", "dark"] as const) {
      const p = palette(theme);
      const ink = p["foreground"]!;
      const inverted = p["primary-foreground"]!;
      for (const file of FILES) {
        const text = readFileSync(file, "utf8");
        for (const m of text.matchAll(/text-ink-inverted\/(\d+)/g)) {
          const alpha = Number(m[1]) / 100;
          const ratio = contrast(over(inverted, ink, alpha), ink);
          if (ratio < AA_BODY) {
            failures.push(
              `${file.replace(SRC, "src")}: ${m[0]} in ${theme} = ${ratio.toFixed(2)}:1`,
            );
          }
        }
      }
    }
    expect(failures, failures.join("\n")).toEqual([]);
  });
});
