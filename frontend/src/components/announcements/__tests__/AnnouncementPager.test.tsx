import React from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import type { Announcement } from "@/types"
import { AnnouncementPager } from "@/components/announcements/AnnouncementPager"

/**
 * Contract of the pager:
 *
 *   1. Empty list → render nothing (parent shows its own empty state).
 *   2. Single item → render the card without nav controls.
 *   3. Many items → render nav controls; counter reads "1 / N" at start.
 *   4. Next / Prev buttons step the cursor and disable at the ends.
 *   5. ArrowLeft / ArrowRight keys step the cursor when focus is
 *      inside the pager. Other keys are ignored.
 *   6. When the list shrinks below the current cursor (e.g. delete),
 *      the cursor clamps to the new last item rather than blanking
 *      the card.
 *   7. Delete button calls ``onDelete`` with the *current* item's id,
 *      never a stale one — so a teacher deleting from the middle of
 *      the list doesn't nuke a different post.
 */

function Wrapper({ children }: { children: React.ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

const make = (id: string, title: string, content = ""): Announcement => ({
  id,
  title,
  content,
  course_id: null,
  created_by: "00000000-0000-0000-0000-000000000000",
  created_at: "2026-05-18T12:00:00Z",
  updated_at: "2026-05-18T12:00:00Z",
})

describe("AnnouncementPager", () => {
  it("renders nothing when the list is empty", () => {
    const { container } = render(<AnnouncementPager announcements={[]} onDelete={vi.fn()} />, {
      wrapper: Wrapper,
    })
    expect(container.firstChild).toBeNull()
  })

  it("hides the nav row when there is only one item", () => {
    render(<AnnouncementPager announcements={[make("a", "Only one")]} onDelete={vi.fn()} />, {
      wrapper: Wrapper,
    })
    expect(screen.getByText("Only one")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /previous/i })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /next/i })).not.toBeInTheDocument()
  })

  it("hides the delete button when no onDelete is provided (read-only mode)", () => {
    render(
      <AnnouncementPager
        announcements={[make("a", "First"), make("b", "Second")]}
      />,
      { wrapper: Wrapper },
    )
    // Nav still works in read-only mode.
    expect(screen.getByRole("button", { name: /next/i })).toBeInTheDocument()
    // But there's no delete affordance.
    expect(screen.queryByRole("button", { name: /delete announcement/i })).not.toBeInTheDocument()
  })

  it("shows the counter as '1 / N' on first render with many items", () => {
    render(
      <AnnouncementPager
        announcements={[make("a", "First"), make("b", "Second"), make("c", "Third")]}
        onDelete={vi.fn()}
      />,
      { wrapper: Wrapper },
    )
    expect(screen.getByText("1 / 3")).toBeInTheDocument()
    expect(screen.getByText("First")).toBeInTheDocument()
  })

  it("steps with the Next button and disables it at the end", async () => {
    const user = userEvent.setup()
    render(
      <AnnouncementPager
        announcements={[make("a", "First"), make("b", "Second")]}
        onDelete={vi.fn()}
      />,
      { wrapper: Wrapper },
    )
    const next = screen.getByRole("button", { name: /next/i })
    await user.click(next)
    expect(screen.getByText("Second")).toBeInTheDocument()
    expect(screen.getByText("2 / 2")).toBeInTheDocument()
    expect(next).toBeDisabled()
  })

  it("steps with the keyboard when focus is inside the pager", async () => {
    const user = userEvent.setup()
    render(
      <AnnouncementPager
        announcements={[make("a", "First"), make("b", "Second")]}
        onDelete={vi.fn()}
      />,
      { wrapper: Wrapper },
    )
    // Focus the region itself (tabIndex=-1) so keyboard events land
    // on the onKeyDown handler regardless of which control inside is
    // currently focusable. Focusing a button instead would silently
    // shift focus off when that button became disabled at the end.
    const region = screen.getByRole("region")
    ;(region as HTMLElement).focus()
    await user.keyboard("{ArrowRight}")
    expect(screen.getByText("Second")).toBeInTheDocument()
    await user.keyboard("{ArrowLeft}")
    expect(screen.getByText("First")).toBeInTheDocument()
  })

  it("clamps the cursor when the list shrinks below the current index", async () => {
    const user = userEvent.setup()
    const onDelete = vi.fn()
    // Pass the bare component to ``rerender`` — RTL re-uses the
    // wrapper from the initial ``render`` call. Wrapping again here
    // would remount the pager and reset its index to 0.
    const { rerender } = render(
      <AnnouncementPager
        announcements={[make("a", "First"), make("b", "Second"), make("c", "Third")]}
        onDelete={onDelete}
      />,
      { wrapper: Wrapper },
    )
    await user.click(screen.getByRole("button", { name: /next/i }))
    await user.click(screen.getByRole("button", { name: /next/i }))
    expect(screen.getByText("Third")).toBeInTheDocument()
    expect(screen.getByText("3 / 3")).toBeInTheDocument()

    rerender(
      <AnnouncementPager
        announcements={[make("a", "First"), make("b", "Second")]}
        onDelete={onDelete}
      />,
    )
    expect(screen.getByText("Second")).toBeInTheDocument()
    expect(screen.getByText("2 / 2")).toBeInTheDocument()
  })

  it("deletes the currently-displayed item, not a stale one", async () => {
    const user = userEvent.setup()
    const onDelete = vi.fn()
    render(
      <AnnouncementPager
        announcements={[make("a", "First"), make("b", "Second"), make("c", "Third")]}
        onDelete={onDelete}
      />,
      { wrapper: Wrapper },
    )
    await user.click(screen.getByRole("button", { name: /next/i }))
    // Now on "Second" — clicking delete must report 'b', not 'a' or 'c'.
    await user.click(screen.getByRole("button", { name: /delete announcement second/i }))
    expect(onDelete).toHaveBeenCalledWith("b")
  })
})
