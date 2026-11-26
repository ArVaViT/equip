import { render } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { OrganizationMark } from "../OrganizationMark"

/**
 * One face for an organization everywhere it is named: the logo once a
 * director uploads one, the name's initials until then.
 */
describe("OrganizationMark", () => {
  it("shows the logo, decoratively, when there is one", () => {
    const { container } = render(
      <OrganizationMark name="UCOAT" logoUrl="/img/organization-logos/abc/logo-0123abcd.png" size="sm" />,
    )
    const img = container.querySelector("img")
    expect(img).toHaveAttribute("src", "/img/organization-logos/abc/logo-0123abcd.png")
    // The name is printed beside it; a second reading would say it twice.
    expect(img).toHaveAttribute("alt", "")
    expect(container.textContent).toBe("")
  })

  it("stands in with the name's initials when there is none", () => {
    const { container } = render(<OrganizationMark name="Церковь «Слово Жизни»" logoUrl={null} />)
    expect(container.querySelector("img")).toBeNull()
    const tile = container.querySelector("[aria-hidden]")
    expect(tile).toHaveTextContent("СЖ")
  })

  it("never puts a non-web address into the page", () => {
    const { container } = render(<OrganizationMark name="School" logoUrl="javascript:alert(1)" />)
    expect(container.querySelector("img")).toBeNull()
    expect(container.textContent).toBe("S")
  })
})
