/**
 * The page every certificate this platform has ever issued points at.
 *
 * `CertificateDocument` prints "Verify at equipbible.com/verify/<number>",
 * the landing page advertises verifiable certificates, and the backend has
 * answered `GET /certificates/verify/{number}` without authentication all
 * along. The page did not exist: that address returned 404 in production on
 * 2026-08-31, checked against a real issued number.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import i18n from "@/i18n/config";
import VerifyCertificatePage from "@/pages/Verify/VerifyCertificatePage";

/**
 * Hand-rolled rather than `vi.fn()`. A `vi.fn()` whose implementation returns
 * a rejected promise is recorded in `mock.results`, and the runner reports it
 * as an unhandled rejection before the component's own catch ever runs — the
 * failure path then cannot be tested at all. A plain function has no such
 * bookkeeping.
 */
type Verify = (certificateNumber: string) => Promise<unknown>;
let behaviour: Verify = async () => ({ valid: false });
const calls: string[] = [];

vi.mock("@/services/certificates", () => ({
  certificatesService: {
    verifyCertificate: (certificateNumber: string) => {
      calls.push(certificateNumber);
      return behaviour(certificateNumber);
    },
  },
}));

function renderAt(path: string) {
  return render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/verify" element={<VerifyCertificatePage />} />
          <Route path="/verify/:certificateNumber" element={<VerifyCertificatePage />} />
        </Routes>
      </MemoryRouter>
    </I18nextProvider>,
  );
}

const GENUINE = {
  valid: true,
  certificate_number: "CERT-9EA8AA9729A7",
  user_name: "Kushal B G",
  course_title: "A Glossary in Your Pocket",
  issued_at: "2026-05-18T01:50:58Z",
};

describe("VerifyCertificatePage", () => {
  beforeEach(() => {
    calls.length = 0;
    behaviour = async () => ({ valid: false });
  });

  it("checks the number in the URL without being asked", async () => {
    behaviour = async () => GENUINE;
    renderAt("/verify/CERT-9EA8AA9729A7");

    await waitFor(() => expect(calls).toContain("CERT-9EA8AA9729A7"));
    expect(await screen.findByText(i18n.t("verify.validHeading"))).toBeInTheDocument();
    expect(screen.getByText("Kushal B G")).toBeInTheDocument();
    expect(screen.getByText("A Glossary in Your Pocket")).toBeInTheDocument();
  });

  it("asks for a number when the URL carries none", () => {
    renderAt("/verify");
    expect(calls).toEqual([]);
    expect(screen.getByLabelText(i18n.t("verify.numberLabel"))).toBeInTheDocument();
  });

  it("says a number is unknown without naming anybody", async () => {
    behaviour = async () => ({
      valid: false,
      certificate_number: "CERT-000000000000",
      user_name: null,
      course_title: null,
      issued_at: null,
    });
    renderAt("/verify/CERT-000000000000");

    expect(await screen.findByText(i18n.t("verify.invalidHeading"))).toBeInTheDocument();
    // An unknown number must not become a way to probe who studied here.
    expect(screen.queryByText(i18n.t("verify.issuedTo"))).toBeNull();
  });

  it("does not present a server failure as a fake certificate", async () => {
    behaviour = async () => {
      throw new Error("network down");
    };
    renderAt("/verify/CERT-9EA8AA9729A7");

    expect(await screen.findByText(i18n.t("verify.errorTitle"))).toBeInTheDocument();
    // The two must never look alike on a page whose whole job is to be trusted.
    expect(screen.queryByText(i18n.t("verify.invalidHeading"))).toBeNull();
    expect(screen.queryByText(i18n.t("verify.validHeading"))).toBeNull();
  });

  it("looks up whatever is typed into the form", async () => {
    const user = userEvent.setup();
    behaviour = async () => GENUINE;
    renderAt("/verify");

    await user.type(screen.getByLabelText(i18n.t("verify.numberLabel")), "CERT-9EA8AA9729A7");
    await user.click(screen.getByRole("button", { name: new RegExp(i18n.t("verify.submit"), "i") }));

    await waitFor(() => expect(calls).toContain("CERT-9EA8AA9729A7"));
  });
});
