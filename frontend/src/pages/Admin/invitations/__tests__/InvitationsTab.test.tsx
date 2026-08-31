/**
 * Withdrawing an invitation.
 *
 * `revoked` has been a legal status since the invitations table was created,
 * the accept path already refused anything that was not `pending`, and this
 * screen could already filter by it — but nothing could set it. An admin who
 * invited the wrong address had no way to take it back: the link stayed live
 * for seven days and it carries a teacher role.
 */
import type { ReactNode } from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";

import i18n from "@/i18n/config";
import { ConfirmProvider } from "@/components/ui/alert-dialog";
import { InvitationsTab } from "@/pages/Admin/invitations/InvitationsTab";

const listInvitations = vi.fn();
const revokeInvitation = vi.fn();
const createInvitation = vi.fn();

vi.mock("@/services/invitations", () => ({
  invitationsService: {
    listInvitations: (...args: unknown[]) => listInvitations(...args),
    revokeInvitation: (...args: unknown[]) => revokeInvitation(...args),
    createInvitation: (...args: unknown[]) => createInvitation(...args),
  },
}));

const PENDING = {
  id: "inv-1",
  email: "wrong.address@example.com",
  role: "teacher",
  status: "pending",
  is_expired: false,
  created_at: "2026-08-31T00:00:00Z",
  expires_at: "2026-09-07T00:00:00Z",
  invited_by: "admin-1",
};

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <ConfirmProvider>{children}</ConfirmProvider>
    </I18nextProvider>
  );
}

describe("InvitationsTab — revoking", () => {
  beforeEach(() => {
    listInvitations.mockReset().mockResolvedValue([PENDING]);
    revokeInvitation.mockReset().mockResolvedValue({ ...PENDING, status: "revoked" });
  });

  it("offers to revoke a pending invitation", async () => {
    render(
      <Wrapper>
        <InvitationsTab />
      </Wrapper>,
    );
    await waitFor(() => expect(screen.getAllByText(PENDING.email).length).toBeGreaterThan(0));
    expect(
      screen.getAllByRole("button", { name: i18n.t("admin.invitations.revoke") }).length,
    ).toBeGreaterThan(0);
  });

  it("asks before it acts, and does nothing if the answer is no", async () => {
    const user = userEvent.setup();
    render(
      <Wrapper>
        <InvitationsTab />
      </Wrapper>,
    );
    await waitFor(() => expect(screen.getAllByText(PENDING.email).length).toBeGreaterThan(0));

    await user.click(
      screen.getAllByRole("button", { name: i18n.t("admin.invitations.revoke") })[0]!,
    );
    // The link in somebody's inbox dies the moment this succeeds, so it asks.
    expect(await screen.findByText(i18n.t("admin.invitations.confirmRevoke.title"))).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: i18n.t("common.cancel") }));
    expect(revokeInvitation).not.toHaveBeenCalled();
  });

  it("revokes the invitation it was pointed at", async () => {
    const user = userEvent.setup();
    render(
      <Wrapper>
        <InvitationsTab />
      </Wrapper>,
    );
    await waitFor(() => expect(screen.getAllByText(PENDING.email).length).toBeGreaterThan(0));

    await user.click(
      screen.getAllByRole("button", { name: i18n.t("admin.invitations.revoke") })[0]!,
    );
    await user.click(
      screen.getByRole("button", { name: i18n.t("admin.invitations.confirmRevoke.confirm") }),
    );

    await waitFor(() => expect(revokeInvitation).toHaveBeenCalledWith("inv-1"));
  });
});
