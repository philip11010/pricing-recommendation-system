/**
 * The guard on the administration pages.
 *
 * Three answers rather than two, and the third is the one worth a test: a
 * signed-in mentor who follows a link to /admin is sent to their own
 * dashboard, not to the log in screen. Sending them to log in would put them
 * in a loop, because they are already signed in and logging in again changes
 * nothing.
 *
 * The fourth case is the one that is not this component's job, and it is
 * asserted here so the boundary is written down: the guard reads a flag the
 * API sent, and the API checks the same flag on the account for every request
 * these pages make. A browser that set the flag by hand reaches the page and
 * then gets 403 from all six endpoints.
 */

import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Mentor } from "@/lib/api-types";

const replace = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn() }),
  // The header reads the path to decide whether it is on a bold screen, so
  // the mock has to answer that too: the navigation test below renders it.
  usePathname: () => "/dashboard",
}));

const session =
  vi.fn<() => { loading: boolean; mentor: Mentor | null; logout: () => void }>();

vi.mock("@/lib/session", () => ({
  useSession: () => session(),
}));

const { RequireAdmin } = await import("@/components/require-admin");

function mentor(overrides: Partial<Mentor> = {}): Mentor {
  return {
    id: 7,
    full_name: "Test Mentor",
    email: "mentor@example.com",
    headline: null,
    bio: null,
    education_level: null,
    experience_summary: null,
    credentials: null,
    years_experience: null,
    years_mentoring_band: null,
    verified: true,
    is_demo: false,
    is_admin: false,
    services: [],
    history: null,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function inside(): ReactNode {
  return <RequireAdmin>{() => <p>The figures</p>}</RequireAdmin>;
}

describe("RequireAdmin", () => {
  beforeEach(() => {
    replace.mockClear();
    session.mockReset();
  });

  it("waits while the token is still being checked", () => {
    session.mockReturnValue({ loading: true, mentor: null, logout: vi.fn() });

    render(inside());

    // Nothing is decided yet, so nothing is redirected. A guard that
    // redirected here would bounce an administrator to the log in screen on
    // every page reload.
    expect(replace).not.toHaveBeenCalled();
    expect(screen.getByRole("status")).toHaveTextContent("Checking your account");
    expect(screen.queryByText("The figures")).not.toBeInTheDocument();
  });

  it("sends somebody who is not signed in to log in", () => {
    session.mockReturnValue({ loading: false, mentor: null, logout: vi.fn() });

    render(inside());

    expect(replace).toHaveBeenCalledWith("/login");
    expect(screen.queryByText("The figures")).not.toBeInTheDocument();
  });

  it("sends a signed-in mentor to their own dashboard", () => {
    session.mockReturnValue({
      loading: false,
      mentor: mentor({ is_admin: false }),
      logout: vi.fn(),
    });

    render(inside());

    expect(replace).toHaveBeenCalledWith("/dashboard");
    // Not even for a frame: a flash of the page followed by a redirect reads
    // as a fault, and this page is not theirs to see.
    expect(screen.queryByText("The figures")).not.toBeInTheDocument();
  });

  it("lets an administrator through", () => {
    session.mockReturnValue({
      loading: false,
      mentor: mentor({ is_admin: true }),
      logout: vi.fn(),
    });

    render(inside());

    expect(replace).not.toHaveBeenCalled();
    expect(screen.getByText("The figures")).toBeInTheDocument();
  });
});

describe("the navigation link", () => {
  it("is shown to an administrator and to nobody else", async () => {
    const { SiteHeader } = await import("@/components/site-header");

    session.mockReturnValue({
      loading: false,
      mentor: mentor({ is_admin: false }),
      logout: vi.fn(),
    });
    const plain = render(<SiteHeader />);
    expect(screen.queryByRole("link", { name: "Admin" })).not.toBeInTheDocument();
    plain.unmount();

    session.mockReturnValue({
      loading: false,
      mentor: mentor({ is_admin: true }),
      logout: vi.fn(),
    });
    render(<SiteHeader />);
    expect(screen.getByRole("link", { name: "Admin" })).toHaveAttribute(
      "href",
      "/admin",
    );
  });

  it("is absent for a visitor who is not signed in", async () => {
    const { SiteHeader } = await import("@/components/site-header");
    session.mockReturnValue({ loading: false, mentor: null, logout: vi.fn() });

    render(<SiteHeader />);

    expect(screen.queryByRole("link", { name: "Admin" })).not.toBeInTheDocument();
    // The public navigation is unchanged: there is no sign anywhere that an
    // administration page exists.
    expect(screen.getByRole("link", { name: "Register" })).toBeInTheDocument();
  });
});
