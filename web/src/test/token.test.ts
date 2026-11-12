/**
 * The access token, and being signed out by the server.
 *
 * Two things are worth testing here rather than trusting. Storage throws in a
 * private window and when site data is blocked, and a page that cannot read a
 * token has to carry on rather than break. And a 401 from anywhere has to
 * discard the token before it sends the mentor to log in, because a token the
 * API has refused would otherwise be sent again by the next page.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  EXPIRED_QUERY,
  clearToken,
  handleUnauthorized,
  hasToken,
  readToken,
  writeToken,
} from "@/lib/token";

const STORAGE_KEY = "careerMentor.token";

function stubLocation(pathname: string) {
  const assign = vi.fn();
  Object.defineProperty(window, "location", {
    configurable: true,
    writable: true,
    value: { pathname, assign, href: `http://localhost${pathname}` },
  });
  return assign;
}

describe("the stored token", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("is kept under the one key the whole application reads", () => {
    writeToken("a-signed-token");

    expect(window.localStorage.getItem(STORAGE_KEY)).toBe("a-signed-token");
    expect(readToken()).toBe("a-signed-token");
    expect(hasToken()).toBe(true);
  });

  it("reads as absent when nothing is stored", () => {
    expect(readToken()).toBeNull();
    expect(hasToken()).toBe(false);
  });

  it("treats a blank entry as no token at all", () => {
    window.localStorage.setItem(STORAGE_KEY, "   ");

    expect(readToken()).toBeNull();
  });

  it("is gone after clearing", () => {
    writeToken("a-signed-token");
    clearToken();

    expect(readToken()).toBeNull();
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("carries on when storage refuses to answer", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("site data is blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("site data is blocked");
    });

    expect(() => writeToken("a-signed-token")).not.toThrow();
    expect(readToken()).toBeNull();
  });

  it("announces a change, so the header can follow along", () => {
    const heard = vi.fn();
    window.addEventListener("pathwise:sessionchanged", heard);

    writeToken("a-signed-token");
    clearToken();

    expect(heard).toHaveBeenCalledTimes(2);
    window.removeEventListener("pathwise:sessionchanged", heard);
  });
});

describe("being refused by the API", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("discards the token and sends the mentor to log in", () => {
    writeToken("an-expired-token");
    const assign = stubLocation("/dashboard");

    handleUnauthorized();

    expect(readToken()).toBeNull();
    expect(assign).toHaveBeenCalledWith(`/login?${EXPIRED_QUERY}=1`);
  });

  it("does not bounce the log in page off itself", () => {
    writeToken("a-wrong-password-attempt");
    const assign = stubLocation("/login");

    handleUnauthorized();

    expect(readToken()).toBeNull();
    expect(assign).not.toHaveBeenCalled();
  });
});
