/**
 * An invitation whose person arrived another way.
 *
 * The database closes it as `fulfilled` when the person enrols, joins the
 * organization or signs up without the link. The sender has to be able to
 * tell that apart from "used the link", and must not be offered to resend
 * or revoke an invitation to somebody who is already there.
 */
import type { ReactNode } from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";

import i18n from "@/i18n/config";
import { ConfirmProvider } from "@/components/ui/alert-dialog";
import { InvitationsTab } from "@/pages/Admin/invitations/InvitationsTab";

const listInvitations = vi.fn();

vi.mock("@/services/invitations", () => ({
  invitationsService: {
    listInvitations: (...args: unknown[]) => listInvitations(...args),
    revokeInvitation: vi.fn(),
    createInvitation: vi.fn(),
  },
}));

const BASE = {
  role: "student",
  is_expired: false,
  created_at: "2026-09-12T00:00:00Z",
  expires_at: "2026-09-19T00:00:00Z",
  invited_by: "admin-1",
  accepted_at: null,
  fulfilled_at: null,
};

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <ConfirmProvider>{children}</ConfirmProvider>
    </I18nextProvider>
  );
}

describe("InvitationsTab — fulfilled another way", () => {
  beforeEach(() => {
    listInvitations.mockReset().mockResolvedValue([
      { ...BASE, id: "a", email: "used.link@example.com", status: "accepted", accepted_at: "2026-09-13T00:00:00Z" },
      { ...BASE, id: "f", email: "came.alone@example.com", status: "fulfilled", fulfilled_at: "2026-09-14T00:00:00Z" },
    ]);
  });

  it("labels the two differently", async () => {
    render(
      <Wrapper>
        <InvitationsTab />
      </Wrapper>,
    );
    await waitFor(() => expect(screen.getAllByText("came.alone@example.com").length).toBeGreaterThan(0));

    expect(screen.getAllByText(i18n.t("admin.invitations.statusFulfilled")).length).toBeGreaterThan(0);
    expect(screen.getAllByText(i18n.t("admin.invitations.statusAccepted")).length).toBeGreaterThan(0);
    expect(i18n.t("admin.invitations.statusFulfilled")).not.toBe(i18n.t("admin.invitations.statusAccepted"));
  });

  it("offers neither resend nor revoke for somebody already there", async () => {
    render(
      <Wrapper>
        <InvitationsTab />
      </Wrapper>,
    );
    await waitFor(() => expect(screen.getAllByText("came.alone@example.com").length).toBeGreaterThan(0));

    expect(screen.queryByRole("button", { name: i18n.t("admin.invitations.resend") })).toBeNull();
    expect(screen.queryByRole("button", { name: i18n.t("admin.invitations.revoke") })).toBeNull();
  });
});
