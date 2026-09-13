import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import DashboardPage from "../app/(dashboard)/page";
import { authRedirect } from "../lib/auth/redirects";

describe("protected routing", () => {
  it("routes every non-full session to its correct authentication step", () => {
    expect(authRedirect({ status: "anonymous" })).toBe("/login");
    expect(authRedirect({ status: "totp_enrollment" })).toBe("/enroll");
    expect(authRedirect({ status: "totp_verification" })).toBe("/login?step=totp");
    expect(
      authRedirect({
        status: "authenticated",
        user: { id: "1", email: "admin@example.com", totp_enabled: true },
      }),
    ).toBeNull();
  });
});

describe("Mission Control", () => {
  it("shows honest empty states instead of fabricated metrics", () => {
    render(<DashboardPage />);

    expect(screen.getByRole("heading", { level: 1, name: "Mission Control" })).toBeVisible();
    for (const heading of ["Tasks", "Running Agents", "Pending Approvals", "Provider Health"]) {
      expect(screen.getByRole("heading", { level: 2, name: heading })).toBeVisible();
    }
    expect(screen.getByText("No tasks yet")).toBeVisible();
    expect(screen.getByText("No agents are running")).toBeVisible();
    expect(screen.getByText("Nothing is awaiting approval")).toBeVisible();
    expect(screen.getByText("No providers configured")).toBeVisible();
  });
});
