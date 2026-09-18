/**
 * The complaints ledger, from the side somebody actually uses.
 *
 * § 512(i)(1)(A) asks for a repeat-infringer policy, notice of it, and
 * reasonable implementation. BMG v. Cox lost the safe harbour holding a
 * thirteen-step written policy whose last step was never taken; Ventura v.
 * Motherless kept it with one person, a simple procedure and a record.
 *
 * The closure itself is the server's — it happens in the same transaction as
 * the decision, so there is no step here for anybody to forget. What this
 * screen owes the person clicking is that they know what the click does
 * before they make it, and can see how many times it has been this person.
 */
import type { ReactNode } from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";

import i18n from "@/i18n/config";
import { ConfirmProvider } from "@/components/ui/alert-dialog";
import { DmcaTab } from "@/pages/Admin/dmca/DmcaTab";
import type { DmcaComplaint } from "@/services/dmca";

const list = vi.fn();
const decide = vi.fn();

vi.mock("@/services/dmca", () => ({
  dmcaService: {
    list: (...args: unknown[]) => list(...args),
    decide: (...args: unknown[]) => decide(...args),
  },
}));

function complaint(overrides: Partial<DmcaComplaint> = {}): DmcaComplaint {
  return {
    id: "c-1",
    received_at: "2026-09-17T10:00:00Z",
    complainant_name: "Jane Rightsholder",
    complainant_email: "jane@publisher.example",
    complainant_organization: "Example Press",
    work_described: "The Cross of Christ, chapter 4",
    material_location: "https://equipbible.com/courses/acts/lesson-3",
    uploaded_by: "u-1",
    uploader_name: "Pavel Teacher",
    uploader_notified_at: null,
    status: "received",
    resolved_at: null,
    resolved_by: null,
    resolution_note: null,
    strike_number: null,
    uploader_upheld_count: 0,
    uploader_account_closed: false,
    ...overrides,
  };
}

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <ConfirmProvider>{children}</ConfirmProvider>
    </I18nextProvider>
  );
}

describe("the complaints ledger", () => {
  beforeEach(() => {
    list.mockReset();
    decide.mockReset();
    decide.mockResolvedValue(complaint({ status: "upheld" }));
  });

  it("shows who complained and about what", async () => {
    list.mockResolvedValue([complaint()]);

    render(<DmcaTab />, { wrapper: Wrapper });

    expect(
      await screen.findByText("The Cross of Christ, chapter 4"),
    ).toBeInTheDocument();
    expect(screen.getByText(/Jane Rightsholder/)).toBeInTheDocument();
    expect(screen.getByText(/Pavel Teacher/)).toBeInTheDocument();
  });

  it("says when the uploader has not been told yet", async () => {
    list.mockResolvedValue([complaint()]);

    render(<DmcaTab />, { wrapper: Wrapper });

    expect(
      await screen.findByText(i18n.t("admin.dmca.field.notYet")),
    ).toBeInTheDocument();
  });

  it("shows which strike an upheld complaint was", async () => {
    list.mockResolvedValue([
      complaint({ status: "upheld", strike_number: 2, uploader_upheld_count: 2 }),
    ]);

    render(<DmcaTab />, { wrapper: Wrapper });

    expect(
      await screen.findByText(i18n.t("admin.dmca.strike", { number: 2 })),
    ).toBeInTheDocument();
  });

  it("warns, before the click, that this one closes the account", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([complaint({ uploader_upheld_count: 2 })]);

    render(<DmcaTab />, { wrapper: Wrapper });
    await user.click(await screen.findByRole("button", {
      name: i18n.t("admin.dmca.action.uphold"),
    }));

    expect(
      await screen.findByText(
        i18n.t("admin.dmca.confirm.willCloseAccount", { name: "Pavel Teacher" }),
      ),
    ).toBeInTheDocument();
  });

  it("does not warn when it is only the first one", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([complaint({ uploader_upheld_count: 0 })]);

    render(<DmcaTab />, { wrapper: Wrapper });
    await user.click(await screen.findByRole("button", {
      name: i18n.t("admin.dmca.action.uphold"),
    }));

    expect(await screen.findByText(i18n.t("admin.dmca.confirm.body"))).toBeInTheDocument();
  });

  it("records the decision, and that the uploader was told", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([complaint()]);

    render(<DmcaTab />, { wrapper: Wrapper });
    await user.click(await screen.findByRole("button", {
      name: i18n.t("admin.dmca.action.uphold"),
    }));
    await user.click(
      await screen.findByRole("button", { name: i18n.t("admin.dmca.confirm.confirm") }),
    );

    expect(decide).toHaveBeenCalledWith("c-1", {
      status: "upheld",
      uploader_notified: true,
    });
  });

  it("offers no decision on a complaint already decided", async () => {
    list.mockResolvedValue([
      complaint({ status: "rejected", resolution_note: "Public domain." }),
    ]);

    render(<DmcaTab />, { wrapper: Wrapper });

    expect(await screen.findByText("Public domain.")).toBeInTheDocument();
    expect(screen.queryByRole("button", {
      name: i18n.t("admin.dmca.action.uphold"),
    })).toBeNull();
  });

  it("marks an account that has passed the threshold", async () => {
    list.mockResolvedValue([
      complaint({
        status: "upheld",
        strike_number: 3,
        uploader_upheld_count: 3,
        uploader_account_closed: true,
      }),
    ]);

    render(<DmcaTab />, { wrapper: Wrapper });

    expect(
      await screen.findByText(i18n.t("admin.dmca.accountClosed")),
    ).toBeInTheDocument();
  });
});
