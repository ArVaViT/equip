import { describe, expect, it } from "vitest"

import { reuseOrderNumbers } from "@/lib/courseStructure"

const l = (id: string, order_index: number) => ({ id, order_index })

describe("reuseOrderNumbers", () => {
  it("hands the same numbers out again in the new order", () => {
    // A module whose lessons are 7, 8, 9 in a course-wide order: moving the
    // last to the top must not renumber them from 0, which would move where
    // the module starts and carry loose lessons past it.
    const before = [l("a", 7), l("b", 8), l("c", 9)]
    const after = [before[2]!, before[0]!, before[1]!]
    expect(reuseOrderNumbers(before, after)).toEqual([l("c", 7), l("a", 8), l("b", 9)])
  })

  it("pulls ties apart so the new order is the only reading", () => {
    const before = [l("a", 4), l("b", 4), l("c", 5)]
    const after = [before[1]!, before[0]!, before[2]!]
    expect(reuseOrderNumbers(before, after).map((c) => c.order_index)).toEqual([4, 5, 6])
  })
})
