/**
 * Types for the locale-boot generator, so the unit suite can import it.
 *
 * The generator is plain `.mjs` because it runs under bare `node` in
 * `npm run build` and in `scripts/i18n-check.mjs`, before anything has been
 * compiled. The test that pins its behaviour lives under `src/` and is
 * type-checked like everything else, so it needs a declaration to import
 * against — this is that, and nothing more.
 */

export declare const LOCALES: string[]
export declare const DEFAULT_LOCALE: string
export declare const STORAGE_KEY: string
export declare const LEGACY_STORAGE_KEY: string
export declare const OUT_FILE: string
export declare function buildLocaleBoot(): string
