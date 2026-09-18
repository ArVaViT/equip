/**
 * The age statement on the invite form.
 *
 * Self-registration is from 16 and always has been; an invitation is how
 * somebody younger gets in, and until now nothing said how much younger. The
 * floor is 13, because below it COPPA turns on — verifiable parental consent,
 * a records-access duty, a deletion duty — and there is no process here for
 * any of that. There are nine teachers.
 *
 * No date of birth is asked for. The sender knows the family; the platform
 * does not, and collecting a child's birthday in order to protect children is
 * a trade nobody wins. What is kept is the statement and who made it.
 *
 * These tests pin the three properties that make it a statement rather than a
 * formality: the box is not ticked on arrival, the button will not send until
 * it is, and the box does not stay ticked for the next person.
 */
import type { ReactNode } from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";

import i18n from "@/i18n/config";
import { CreateInvitationDialog } from "@/pages/Admin/invitations/CreateInvitationDialog";

const createInvitation = vi.fn();

vi.mock("@/services/invitations", () => ({
  invitationsService: {
    createInvitation: (...args: unknown[]) => createInvitation(...args),
  },
}));

function Wrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>;
}

function open() {
  return render(
    <CreateInvitationDialog open onClose={vi.fn()} onCreated={vi.fn()} />,
    { wrapper: Wrapper },
  );
}

const statement = () => screen.getByRole("checkbox");
const sendButton = () =>
  screen.getByRole("button", { name: i18n.t("admin.invitations.send") });

describe("the age statement on the invite form", () => {
  beforeEach(() => {
    createInvitation.mockReset();
    createInvitation.mockResolvedValue({ id: "inv-1" });
  });

  it("is not ticked when the form opens", () => {
    open();

    expect(statement()).not.toBeChecked();
  });

  it("says what it is for, in words", () => {
    open();

    expect(
      screen.getByText(i18n.t("admin.invitations.ageAttestation.label")),
    ).toBeInTheDocument();
  });

  it("will not send an invitation until it is made", async () => {
    const user = userEvent.setup();
    open();

    await user.type(screen.getByPlaceholderText(/@/), "pupil@example.com");

    expect(sendButton()).toBeDisabled();
  });

  it("sends once it is made, and says so to the server", async () => {
    const user = userEvent.setup();
    open();

    await user.type(screen.getByPlaceholderText(/@/), "pupil@example.com");
    await user.click(statement());
    await user.click(sendButton());

    expect(createInvitation).toHaveBeenCalledWith(
      "pupil@example.com",
      "student",
      true,
    );
  });

  it("does not stay ticked for the next invitation", async () => {
    const user = userEvent.setup();
    open();

    await user.type(screen.getByPlaceholderText(/@/), "pupil@example.com");
    await user.click(statement());
    await user.click(sendButton());

    expect(await screen.findByRole("checkbox")).not.toBeChecked();
  });
});
