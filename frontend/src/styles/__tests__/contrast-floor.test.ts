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

/**
 * Tokens that appear as a wash behind their own text. `brand` reads its value
 * from `--primary` (the bridge maps `--color-accent` onto it), which is why it
 * is spelled differently from the rest.
 */
const CHIP_TOKENS = ["brand", "destructive", "success", "warning", "info"] as const;

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

/**
 * Variant-aware pairing of a tint with the text that sits on it.
 *
 * `active:bg-destructive/85` does not pair with an unprefixed
 * `text-destructive` — those two are never painted at the same moment. A
 * dropdown item that is red at rest and inverts on `active` is correct, and a
 * scan that ignores the prefix calls it a 1.5:1 catastrophe. So utilities are
 * matched prefix-to-prefix: `""` with `""`, `hover:` with `hover:`.
 */
function chipPairs(line: string): { token: string; alpha: number; text: "default" | "ink" }[] {
  const tints = new Map<string, number>();
  const texts = new Map<string, "default" | "ink">();
  for (const cls of line.split(/[\s"'`]+/)) {
    const cut = cls.lastIndexOf(":");
    const prefix = cut === -1 ? "" : cls.slice(0, cut + 1);
    const util = cut === -1 ? cls : cls.slice(cut + 1);
    for (const token of CHIP_TOKENS) {
      const tint = new RegExp(`^bg-${token}/(\\d+)$`).exec(util);
      if (tint) tints.set(`${prefix}${token}`, Number(tint[1]) / 100);
      if (util === `text-${token}`) texts.set(`${prefix}${token}`, "default");
      if (util === `text-${token}-ink`) texts.set(`${prefix}${token}`, "ink");
    }
  }
  const out: { token: string; alpha: number; text: "default" | "ink" }[] = [];
  for (const [key, alpha] of tints) {
    const text = texts.get(key);
    if (!text) continue;
    out.push({ token: CHIP_TOKENS.find((t) => key.endsWith(t))!, alpha, text });
  }
  return out;
}

/**
 * The same pairing, but across an element boundary.
 *
 * `chipPairs` only sees one line, and the commonest shape in this codebase
 * puts the tint on a wrapper and the text on a child:
 *
 *     <div className="border-success/30 bg-success/5 px-4 py-3">
 *       <p className="text-success">…</p>
 *
 * Nesting is approximated by indentation, which is exact here because the
 * whole tree is Prettier-formatted: a line indented further than the tint line,
 * before the first line indented the same or less, is inside that element. It
 * is a heuristic, and it errs toward reporting — a false positive costs a
 * glance, a false negative ships 2.8:1 to a student.
 */
function nestedChipPairs(
  lines: string[],
  want: "default" | "ink" = "default",
): { line: number; token: string; alpha: number }[] {
  const out: { line: number; token: string; alpha: number }[] = [];
  lines.forEach((line, i) => {
    const indent = line.length - line.trimStart().length;
    for (const token of CHIP_TOKENS) {
      const tint = new RegExp(`bg-${token}/(\\d+)`).exec(line);
      if (!tint) continue;
      for (let j = i + 1; j < lines.length; j++) {
        const next = lines[j]!;
        if (!next.trim()) continue;
        if (next.length - next.trimStart().length <= indent) break;
        const pattern =
          want === "ink"
            ? new RegExp(`\\btext-${token}-ink(?![\\w-])`)
            : new RegExp(`\\btext-${token}(?![\\w-])`);
        if (pattern.test(next)) {
          out.push({ line: j + 1, token, alpha: Number(tint[1]) / 100 });
        }
      }
    }
  });
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

  it("never puts an alpha modifier on a text colour", () => {
    // The rule started as "nothing is quieter than ink-muted" and generalised
    // once the semantic tokens were measured too: `text-brand/60` is 2.68:1,
    // `text-destructive/40` is 1.99:1, `text-success/60` is 2.27:1. Not one
    // alpha rung on any text colour in this palette survived — which makes the
    // rule a single sentence instead of a table.
    const TEXT_TOKENS = ["ink-muted", "muted-foreground", ...CHIP_TOKENS];
    const offenders: string[] = [];
    for (const file of FILES) {
      const text = readFileSync(file, "utf8");
      for (const token of TEXT_TOKENS) {
        for (const [match] of text.matchAll(new RegExp(`text-${token}\\/\\d+`, "g"))) {
          offenders.push(`${file.replace(SRC, "src")}: ${match}`);
        }
      }
    }
    expect(
      offenders,
      "An alpha modifier on a text colour puts it under the floor. Use a " +
        "different size, position or token — not a paler one:\n" +
        offenders.join("\n"),
    ).toEqual([]);
  });

  it("never sets a token's text on the token's own tint", () => {
    // `bg-info/15 text-info` — the token as a wash behind itself at full
    // strength. It always looks coordinated, which is why it survived: both
    // halves move together, so no amount of squinting shows the problem. axe
    // measured that exact pair at 4.46:1, and the rest of the family is worse
    // (`warning` in the light theme is 2.71:1). Every one of these must point
    // at the `-ink` step instead.
    const offenders: string[] = [];
    for (const file of FILES) {
      for (const line of readFileSync(file, "utf8").split("\n")) {
        for (const pair of chipPairs(line)) {
          if (pair.text === "default") {
            offenders.push(
              `${file.replace(SRC, "src")}: bg-${pair.token}/${pair.alpha * 100} ` +
                `with text-${pair.token}`,
            );
          }
        }
      }
    }
    expect(
      offenders,
      "Text on a token's own tint needs the token's -ink step, not its " +
        "DEFAULT:\n" + offenders.join("\n"),
    ).toEqual([]);
  });

  it("catches a tint on the wrapper and the token's own text on a child", () => {
    const offenders: string[] = [];
    for (const file of FILES) {
      const lines = readFileSync(file, "utf8").split("\n");
      for (const hit of nestedChipPairs(lines)) {
        offenders.push(
          `${file.replace(SRC, "src")}:${hit.line}: text-${hit.token} inside ` +
            `bg-${hit.token}/${hit.alpha * 100}`,
        );
      }
    }
    expect(offenders, offenders.join("\n")).toEqual([]);
  });

  it("keeps every -ink step readable on the tints it is actually used at", () => {
    const pairs = new Set<string>();
    for (const file of FILES) {
      const lines = readFileSync(file, "utf8").split("\n");
      for (const line of lines) {
        for (const pair of chipPairs(line)) {
          if (pair.text === "ink") pairs.add(`${pair.token}:${pair.alpha}`);
        }
      }
      // Wrapper-and-child too, or the alphas only ever used that way — `/5`
      // among them — would go unmeasured.
      for (const hit of nestedChipPairs(lines, "ink")) {
        pairs.add(`${hit.token}:${hit.alpha}`);
      }
    }
    expect(pairs.size, "no chip pairs found — the scan is not finding source").toBeGreaterThan(0);

    const failures: string[] = [];
    for (const theme of ["root", "dark"] as const) {
      const p = palette(theme);
      for (const pair of pairs) {
        const [token, alphaText] = pair.split(":") as [string, string];
        const base = p[token === "brand" ? "primary" : token]!;
        const ink = p[`${token}-ink`];
        expect(ink, `--${token}-ink missing from the ${theme} palette`).toBeDefined();
        for (const surface of ["background", "card"] as const) {
          const ratio = contrast(ink!, over(base, p[surface]!, Number(alphaText)));
          if (ratio < AA_BODY) {
            failures.push(
              `${theme}: ${token}-ink on bg-${token}/${Number(alphaText) * 100} over ` +
                `${surface} = ${ratio.toFixed(2)}:1`,
            );
          }
        }
      }
    }
    expect(failures, failures.join("\n")).toEqual([]);
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
