/**
 * WebMCP (experimental): read-only tools for an AI agent running in the
 * reader's browser.
 *
 * WebMCP lets a page hand a browser agent named tools with a JSON Schema
 * instead of leaving it to click through the interface. Equip offers two, both
 * over the public catalogue a stranger already sees without signing in:
 *
 *  - `search_courses` — `GET /api/v1/courses?search=`
 *  - `get_course`     — `GET /api/v1/courses/{id}`
 *
 * Nothing here touches the reader's data: requests go out with
 * `credentials: "omit"` and no Authorization header (deliberately not through
 * `services/api.ts`, which attaches the session), and both tools are marked
 * `readOnlyHint`.
 *
 * The API moved: Chrome's early preview exposed `navigator.modelContext`; the
 * spec and Chrome 150+ put it on `document.modelContext`. Both are detected,
 * the document one first. In a browser with neither, `main.tsx` never loads
 * this module. Origin-trial enrolment is a `<meta http-equiv="origin-trial">`
 * that `vite.config.ts` writes only when `VITE_WEBMCP_OT_TOKEN` is set.
 *
 * Spec: https://github.com/webmachinelearning/webmcp
 * Chrome: https://developer.chrome.com/docs/ai/webmcp/imperative-api
 */

const SITE_ORIGIN = "https://equipbible.com"
const API_URL = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/+$/, "")
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const DESCRIPTION_LIMIT = 600

type ToolResult = { content: Array<{ type: "text"; text: string }>; isError?: boolean }

interface WebMcpTool {
  name: string
  description: string
  inputSchema: Record<string, unknown>
  annotations?: { readOnlyHint?: boolean }
  execute: (input: Record<string, unknown>) => Promise<ToolResult>
}

interface ModelContext {
  registerTool: (tool: WebMcpTool, options?: { signal?: AbortSignal }) => unknown
}

/** `document.modelContext` (current spec) or `navigator.modelContext` (early preview). */
export function findModelContext(): ModelContext | null {
  const candidates = [
    (document as unknown as { modelContext?: unknown }).modelContext,
    (navigator as unknown as { modelContext?: unknown }).modelContext,
  ]
  for (const candidate of candidates) {
    if (candidate && typeof (candidate as ModelContext).registerTool === "function") {
      return candidate as ModelContext
    }
  }
  return null
}

function text(value: unknown, isError = false): ToolResult {
  return { content: [{ type: "text", text: typeof value === "string" ? value : JSON.stringify(value) }], isError }
}

function clip(value: unknown, limit = DESCRIPTION_LIMIT): string | null {
  if (typeof value !== "string" || !value.trim()) return null
  const plain = value.replace(/\s+/g, " ").trim()
  return plain.length > limit ? `${plain.slice(0, limit - 1)}…` : plain
}

function language(): string {
  return document.documentElement.lang || "en"
}

async function getJson(path: string): Promise<unknown> {
  const res = await fetch(`${API_URL}/api/v1${path}`, {
    credentials: "omit",
    headers: { Accept: "application/json", "Accept-Language": language() },
  })
  if (!res.ok) throw new Error(`Equip API answered ${res.status}`)
  return res.json()
}

type Row = Record<string, unknown>

function courseUrl(id: string): string {
  return `${SITE_ORIGIN}/courses/${id}`
}

export async function searchCourses(input: Record<string, unknown>): Promise<ToolResult> {
  const query = typeof input.query === "string" ? input.query.trim().slice(0, 200) : ""
  const rawLimit = typeof input.limit === "number" ? input.limit : 10
  const limit = Math.min(Math.max(Math.trunc(rawLimit), 1), 50)
  const params = new URLSearchParams({ limit: String(limit) })
  if (query) params.set("search", query)
  try {
    const rows = await getJson(`/courses?${params}`)
    if (!Array.isArray(rows)) return text("Unexpected response from the catalogue.", true)
    return text({
      query,
      count: rows.length,
      courses: (rows as Row[]).map((c) => ({
        id: c.id,
        title: c.title,
        description: clip(c.description, 300),
        organization: c.organization_name ?? null,
        lessons: c.chapter_count ?? null,
        url: typeof c.id === "string" ? courseUrl(c.id) : null,
      })),
    })
  } catch (err) {
    return text(err instanceof Error ? err.message : "The catalogue could not be reached.", true)
  }
}

export async function getCourse(input: Record<string, unknown>): Promise<ToolResult> {
  const id = typeof input.id === "string" ? input.id.trim() : ""
  if (!UUID_RE.test(id)) return text("`id` must be a course id (a UUID) as returned by search_courses.", true)
  try {
    const c = (await getJson(`/courses/${encodeURIComponent(id.toLowerCase())}`)) as Row
    const lessonTitles = (list: unknown) =>
      Array.isArray(list) ? (list as Row[]).map((ch) => ch.title).filter((t) => typeof t === "string" && t) : []
    return text({
      id: c.id,
      title: c.title,
      description: clip(c.description),
      url: courseUrl(String(c.id)),
      lessons: c.chapter_count ?? null,
      modules: Array.isArray(c.modules)
        ? (c.modules as Row[]).map((m) => ({ title: m.title, lessons: lessonTitles(m.chapters) }))
        : [],
      lessons_outside_modules: lessonTitles(c.chapters),
      enrolment: c.access_mode === "public" ? "open to anyone with a free account" : "by invitation only",
    })
  } catch (err) {
    return text(err instanceof Error ? err.message : "The course could not be loaded.", true)
  }
}

export const TOOLS: WebMcpTool[] = [
  {
    name: "search_courses",
    description:
      "Search Equip's public catalogue of free Bible courses. Returns matching courses with id, title, short description, teaching organization and URL. Omit `query` to list the catalogue.",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "Words to look for in course titles and descriptions." },
        limit: { type: "integer", minimum: 1, maximum: 50, description: "Most results to return (default 10)." },
      },
    },
    annotations: { readOnlyHint: true },
    execute: searchCourses,
  },
  {
    name: "get_course",
    description:
      "Get one public Equip course by id: title, description, its modules and lesson titles, and who may enrol. Lesson content itself is not returned.",
    inputSchema: {
      type: "object",
      properties: { id: { type: "string", description: "Course id (UUID) from search_courses." } },
      required: ["id"],
    },
    annotations: { readOnlyHint: true },
    execute: getCourse,
  },
]

let registered = false

/** Register the tools once. Silent where WebMCP is missing or refuses. */
export function registerWebMcpTools(): void {
  if (registered) return
  const context = findModelContext()
  if (!context) return
  registered = true
  for (const tool of TOOLS) {
    try {
      // `registerTool` may return a promise (spec) or nothing (early preview).
      void Promise.resolve(context.registerTool(tool)).catch(() => undefined)
    } catch {
      // An implementation that rejects a descriptor shape must not break the app.
    }
  }
}
