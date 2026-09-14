/**
 * The bundle sentinel's rules.
 *
 * Every case below was a real state of `main` on 2026-09-13, when the
 * sentinel passed and should not have: `index` at 24.5 kB under a 200 kB
 * ceiling, a `dnd.esm` budget whose chunk had been renamed, and `katex`
 * shipping 74.7 kB with nothing watching it.
 */
import { describe, it, expect } from "vitest";
// @ts-expect-error — plain ESM build script, no type declarations by design.
import { chunkPrefix, evaluate, explain } from "../bundle-budget.mjs";

describe("chunkPrefix", () => {
  it("reads the name off a hashed chunk", () => {
    expect(chunkPrefix("index-C98zrt8L.js")).toBe("index");
  });

  it("keeps dots in the name, splitting on the last hyphen only", () => {
    expect(chunkPrefix("dnd.esm-DcITUONc.js")).toBe("dnd.esm");
  });

  it("keeps hyphens in the name", () => {
    expect(chunkPrefix("use-reduced-motion-CXFKzUjI.js")).toBe("use-reduced-motion");
  });

  it("ignores non-JS files", () => {
    expect(chunkPrefix("index-C98zrt8L.css")).toBeNull();
    expect(chunkPrefix("logo-DdW1lq2x.svg")).toBeNull();
  });

  it("ignores files with no hash segment", () => {
    expect(chunkPrefix("sw.js")).toBeNull();
    expect(chunkPrefix("chunk-ab.js")).toBeNull();
  });
});

describe("evaluate — regression (the case the sentinel always caught)", () => {
  it("fails a chunk over its ceiling", () => {
    const v = evaluate({ sizes: { vendor: 91 }, budgets: { vendor: 82 } });
    expect(v.ok).toBe(false);
    expect(v.over).toEqual([{ name: "vendor", actual: 91, budget: 82 }]);
  });

  it("passes a chunk sitting just under its ceiling", () => {
    const v = evaluate({ sizes: { vendor: 81 }, budgets: { vendor: 82 } });
    expect(v.ok).toBe(true);
  });

  it("treats exactly-at-budget as within budget", () => {
    const v = evaluate({ sizes: { vendor: 82 }, budgets: { vendor: 82 } });
    expect(v.over).toEqual([]);
  });
});

describe("evaluate — stale budget (index sat at 24.5 under 200)", () => {
  it("fails when the ceiling is so far above the chunk that it gates nothing", () => {
    const v = evaluate({ sizes: { index: 24.5 }, budgets: { index: 200 } });
    expect(v.ok).toBe(false);
    expect(v.stale[0]).toMatchObject({ name: "index", actual: 24.5, budget: 200 });
  });

  it("suggests a ceiling ~15% above the measured size", () => {
    const v = evaluate({ sizes: { index: 24.5 }, budgets: { index: 200 } });
    expect(v.stale[0].suggested).toBe(29);
  });

  it("leaves small chunks alone — noise, not drift", () => {
    const v = evaluate({ sizes: { tiny: 3 }, budgets: { tiny: 20 } });
    expect(v.stale).toEqual([]);
    expect(v.ok).toBe(true);
  });

  it("accepts a budget within the normal headroom band", () => {
    const v = evaluate({ sizes: { vendor: 71 }, budgets: { vendor: 82 } });
    expect(v.stale).toEqual([]);
  });

  it("does not report a chunk as both over and stale", () => {
    const v = evaluate({ sizes: { a: 100 }, budgets: { a: 50 } });
    expect(v.over).toHaveLength(1);
    expect(v.stale).toHaveLength(0);
  });
});

describe("evaluate — dead budget (dnd.esm outlived its chunk)", () => {
  it("fails when a budget matches no emitted chunk", () => {
    const v = evaluate({ sizes: { esm: 50 }, budgets: { "dnd.esm": 35, esm: 59 } });
    expect(v.ok).toBe(false);
    expect(v.dead).toEqual([{ name: "dnd.esm", budget: 35 }]);
  });

  it("does not also count the missing chunk as unbudgeted", () => {
    const v = evaluate({ sizes: {}, budgets: { gone: 35 } });
    expect(v.unbudgeted).toEqual([]);
  });
});

describe("evaluate — unwatched chunk (katex shipped 74.7 kB unbudgeted)", () => {
  it("fails on a heavy chunk with no budget entry", () => {
    const v = evaluate({ sizes: { katex: 74.7 }, budgets: {} });
    expect(v.ok).toBe(false);
    expect(v.unbudgeted[0]).toMatchObject({ name: "katex", actual: 74.7, suggested: 86 });
  });

  it("ignores the long tail of small chunks", () => {
    const sizes = Object.fromEntries(Array.from({ length: 150 }, (_, i) => [`c${i}`, 2 + i * 0.1]));
    const v = evaluate({ sizes, budgets: {} });
    expect(v.unbudgeted).toEqual([]);
    expect(v.ok).toBe(true);
  });

  it("uses the documented threshold as an inclusive floor", () => {
    expect(evaluate({ sizes: { a: 24.9 }, budgets: {} }).unbudgeted).toEqual([]);
    expect(evaluate({ sizes: { a: 25 }, budgets: {} }).unbudgeted).toHaveLength(1);
  });
});

describe("evaluate — the shape of a healthy build", () => {
  const sizes = {
    ChapterEditor: 218.6,
    katex: 74.7,
    vendor: 71,
    supabase: 52.8,
    esm: 50.7,
    motion: 40.4,
    ChapterList: 30.1,
    index: 24.5,
    schemas: 17.2,
    config: 16.1,
    ChapterView: 11.5,
    someSmallRoute: 4.2,
  };
  const budgets = {
    ChapterEditor: 252,
    katex: 86,
    vendor: 82,
    supabase: 61,
    esm: 59,
    motion: 47,
    ChapterList: 35,
    index: 29,
    schemas: 20,
    config: 19,
    ChapterView: 14,
  };

  it("passes the numbers this PR ships", () => {
    const v = evaluate({ sizes, budgets });
    expect(v).toMatchObject({ over: [], stale: [], dead: [], unbudgeted: [], ok: true });
  });

  it("catches the shell growing eightfold — which the old 200 kB ceiling allowed", () => {
    const v = evaluate({ sizes: { ...sizes, index: 196 }, budgets });
    expect(v.over.map((c: { name: string }) => c.name)).toEqual(["index"]);
  });

  it("accepts thresholds being tuned without touching the rules", () => {
    const v = evaluate({
      sizes: { a: 30 },
      budgets: {},
      options: { unbudgetedLimitKb: 50 },
    });
    expect(v.ok).toBe(true);
  });
});

describe("explain", () => {
  it("names the chunk and the fix for every kind of failure", () => {
    const v = evaluate({
      sizes: { over: 100, stale: 20, fresh: 30 },
      budgets: { over: 50, stale: 200, gone: 10 },
    });
    const text = explain(v).join("\n");
    expect(text).toContain("OVER BUDGET  over");
    expect(text).toContain("STALE BUDGET stale");
    expect(text).toContain("DEAD BUDGET  gone");
    expect(text).toContain("NO BUDGET    fresh");
  });

  it("says nothing when the build is clean", () => {
    expect(explain(evaluate({ sizes: { a: 10 }, budgets: { a: 11 } }))).toEqual([]);
  });
});
