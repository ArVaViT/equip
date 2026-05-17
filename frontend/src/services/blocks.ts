import api from "./api"
import { cached, cacheInvalidate, cacheInvalidatePrefix, CACHE_TTL } from "@/lib/cache"
import type { ChapterBlock, BlockType } from "@/types"

type ChapterBlockCreateData = {
  block_type: BlockType
  order_index?: number
  content?: string | null
  quiz_id?: string | null
  assignment_id?: string | null
  file_bucket?: string | null
  file_path?: string | null
  file_name?: string | null
}

type ChapterBlockUpdateData = Partial<Omit<ChapterBlockCreateData, "block_type">> & {
  block_type?: BlockType
}

export const blocksService = {
  async getChapterBlocks(chapterId: string): Promise<ChapterBlock[]> {
    return cached(`blocks:chapter:${chapterId}`, CACHE_TTL.TWO_MINUTES, async () => {
      const response = await api.get<ChapterBlock[]>(`/blocks/chapter/${chapterId}`)
      return response.data
    })
  },

  /**
   * Editor-only fetch: forces source-language `content` (TipTap HTML)
   * regardless of the viewer's `preferred_locale`. Use from
   * `ChapterBlockEditor` so a teacher in EN UI editing their RU course
   * doesn't see the EN translation in the rich-text editor (a PATCH would
   * then overwrite the source `content` column with English HTML).
   *
   * Owner / admin only — the backend returns 403 for anyone else.
   * Intentionally bypasses the `blocks:chapter:{id}` cache so the editor
   * view and the student view don't share state.
   */
  async getChapterBlocksForEdit(chapterId: string): Promise<ChapterBlock[]> {
    const response = await api.get<ChapterBlock[]>(
      `/blocks/chapter/${chapterId}`,
      { params: { source: 1 } },
    )
    return response.data
  },

  async createBlock(chapterId: string, data: ChapterBlockCreateData): Promise<ChapterBlock> {
    const response = await api.post<ChapterBlock>(`/blocks/chapter/${chapterId}`, data)
    cacheInvalidate(`blocks:chapter:${chapterId}`)
    return response.data
  },

  async updateBlock(blockId: string, data: ChapterBlockUpdateData): Promise<ChapterBlock> {
    const response = await api.put<ChapterBlock>(`/blocks/${blockId}`, data)
    cacheInvalidatePrefix("blocks:chapter:")
    return response.data
  },

  async deleteBlock(blockId: string): Promise<void> {
    await api.delete(`/blocks/${blockId}`)
    cacheInvalidatePrefix("blocks:chapter:")
  },

  async reorderBlocks(
    chapterId: string,
    blocks: { id: string; order_index: number }[],
  ): Promise<void> {
    await api.put(`/blocks/chapter/${chapterId}/reorder`, blocks)
    cacheInvalidate(`blocks:chapter:${chapterId}`)
  },
}
