/**
 * A refused upload used to be explained in English, or not at all.
 *
 * Storage answers "The object exceeded the maximum allowed size", "mime
 * type image/heic is not supported", "Invalid key: …" — sentences for a
 * developer, shown to a teacher on a Russian screen. One call site had a
 * bare ``catch {}`` and said only "Загрузка не удалась" whatever happened.
 *
 * These pin two things: the sentence is in the reader's language, and it
 * says what to do. Russian throughout — that is who is uploading tomorrow.
 * Exact strings, no ``\b`` (ASCII-only in JavaScript; never matches beside
 * a Cyrillic letter).
 */

import { AxiosError } from "axios"
import { afterAll, beforeAll, describe, expect, it } from "vitest"

import i18n from "@/i18n/config"
import { describeUploadError, preflightUpload } from "@/lib/uploadError"
import { COURSE_ASSETS, COURSE_MATERIALS, MB } from "@/lib/uploadLimits"

/** What storage-js throws: a StorageApiError, read as a plain shape. */
function storageError(status: number, message: string, code?: string) {
  const err = new Error(message) as Error & { status: number; statusCode: string; code?: string }
  err.name = "StorageApiError"
  err.status = status
  err.statusCode = String(status)
  err.code = code
  return err
}

function fileOf(bytes: number, name: string, type: string): File {
  const file = new File(["x"], name, { type })
  // jsdom builds the bytes eagerly; a 6 MB string is wasteful when only
  // `size` is read. Overriding the getter keeps the test instant.
  Object.defineProperty(file, "size", { value: bytes })
  return file
}

const LATIN_WORD = /(?<!\p{L})(size|mime|Invalid|object|exceeded)(?!\p{L})/u

describe("what the teacher is told", () => {
  beforeAll(async () => {
    await i18n.changeLanguage("ru")
  })
  afterAll(async () => {
    await i18n.changeLanguage("en")
  })

  describe("before the upload", () => {
    it("names the file's size and the limit for a phone photo over 5 MB", () => {
      const issue = preflightUpload(fileOf(6.2 * MB, "IMG_0042.jpg", "image/jpeg"), COURSE_ASSETS)
      expect(issue?.kind).toBe("size")
      expect(issue?.message).toBe("Файл весит 6,2 МБ, а предел — 5 МБ.")
    })

    it("lets a 4.9 MB photo through — the bucket takes 5", () => {
      expect(preflightUpload(fileOf(4.9 * MB, "IMG_0042.jpg", "image/jpeg"), COURSE_ASSETS)).toBeNull()
    })

    it("explains HEIC as the phone's setting, not the file", () => {
      const issue = preflightUpload(fileOf(2 * MB, "IMG_0042.HEIC", "image/heic"), COURSE_ASSETS)
      expect(issue?.kind).toBe("heic")
      expect(issue?.message).toBe(
        "Фото в формате HEIC с айфона не поддерживается. Сохраните его как JPEG — на айфоне: Настройки → Камера → Форматы → Наиболее совместимый.",
      )
    })

    it("catches HEIC by extension when the browser gives no type", () => {
      expect(preflightUpload(fileOf(2 * MB, "IMG_0042.heic", ""), COURSE_ASSETS)?.kind).toBe("heic")
    })

    it("lists the formats the bucket takes when this one is not among them", () => {
      const issue = preflightUpload(fileOf(1 * MB, "clip.mp4", "video/mp4"), COURSE_MATERIALS)
      expect(issue?.kind).toBe("type")
      expect(issue?.message).toBe(
        "Такой формат файла не поддерживается. Подойдут: PDF, MP3, M4A, OGG, WAV, DOC, DOCX, PPT, PPTX, TXT.",
      )
    })

    it("accepts an iPhone voice memo under the name Chrome gives it", () => {
      expect(preflightUpload(fileOf(3 * MB, "Заметка.m4a", "audio/x-m4a"), COURSE_MATERIALS)).toBeNull()
    })

    it("stops a 60 MB recording before a minute of upload", () => {
      const issue = preflightUpload(fileOf(60 * MB, "Лекция.mp3", "audio/mpeg"), COURSE_MATERIALS)
      expect(issue?.kind).toBe("size")
      expect(issue?.message).toBe("Файл весит 60,0 МБ, а предел — 50 МБ.")
    })
  })

  describe("after Storage refused", () => {
    it("translates the 413", () => {
      const err = storageError(413, "The object exceeded the maximum allowed size", "Payload too large")
      expect(describeUploadError(err, COURSE_ASSETS)).toBe("Хранилище отклонило файл: он больше 5 МБ.")
    })

    it("translates the 415 and names the formats", () => {
      const err = storageError(415, "mime type image/heic is not supported", "InvalidMimeType")
      expect(describeUploadError(err, COURSE_ASSETS)).toBe(
        "Такой формат файла не поддерживается. Подойдут: JPG, PNG, WebP, GIF, SVG.",
      )
    })

    it("translates InvalidKey — the production failure this started from", () => {
      const err = storageError(400, "Invalid key: abc/_probe-Проповедь_12_сентября.pdf", "InvalidKey")
      expect(describeUploadError(err, COURSE_MATERIALS)).toBe(
        "Хранилище не приняло имя файла. Переименуйте файл латиницей и попробуйте снова.",
      )
    })

    it("recognises a size refusal by its sentence alone, without a status", () => {
      // Older supabase-js left `status` off; the message is the constant.
      expect(describeUploadError(new Error("The object exceeded the maximum allowed size"), COURSE_MATERIALS)).toBe(
        "Хранилище отклонило файл: он больше 50 МБ.",
      )
    })

    it("calls a lost connection a lost connection", () => {
      expect(describeUploadError(new TypeError("Failed to fetch"), COURSE_MATERIALS)).toBe(
        "Не удалось связаться с хранилищем. Проверьте интернет и попробуйте снова.",
      )
    })

    it("translates a 403 from the bucket policy", () => {
      const err = storageError(403, "new row violates row-level security policy", "AccessDenied")
      expect(describeUploadError(err, COURSE_MATERIALS)).toBe("Нет прав на загрузку в этот курс. Войдите снова и повторите.")
    })

    it("hands an API error from the step after the upload to getErrorDetail", () => {
      const err = new AxiosError("request failed")
      err.response = {
        status: 403,
        statusText: "",
        headers: {},
        config: { headers: undefined } as never,
        data: {},
      }
      expect(describeUploadError(err, COURSE_MATERIALS)).toBe("У вас нет прав на это действие.")
    })

    it("never lets Storage's English through, even for a code it has no sentence for", () => {
      const err = storageError(500, "Something unexpected happened in the object store", "InternalError")
      const text = describeUploadError(err, COURSE_MATERIALS)
      expect(text).toBe("Загрузка не удалась (InternalError). Попробуйте ещё раз.")
      expect(text).not.toMatch(LATIN_WORD)
    })

    it("has a sentence for an error that is nothing at all", () => {
      expect(describeUploadError(undefined, COURSE_MATERIALS)).toBe("Загрузка не удалась. Попробуйте ещё раз.")
    })
  })
})
