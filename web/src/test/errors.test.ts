/**
 * Turning the API's refusal into something a form can show.
 *
 * The API names a nested answer with a dotted path, like
 * `service.max_mentees`, and the form keys its fields by exactly that name,
 * so most of this is about the cases that are not a simple match: a field the
 * form does not render, two messages for one field, and an error list that
 * arrived empty.
 */

import { describe, expect, it } from "vitest";

import { ApiError, isAlreadyDecided, isNotFound, messageFor } from "@/lib/errors";
import { NETWORK_MESSAGE, NetworkError, UNEXPECTED_MESSAGE } from "@/lib/errors";
import { toFieldErrors } from "@/lib/errors";

describe("toFieldErrors", () => {
  it("attaches each message to the field the API named", () => {
    const mapped = toFieldErrors([
      { field: "full_name", message: "String should have at least 2 characters" },
      {
        field: "email",
        message: "Enter an email address the mentor can be reached at.",
      },
      {
        field: "service.max_mentees",
        message: "The number of mentees in one session must be between 1 and 8.",
      },
    ]);

    expect(mapped.fields).toEqual({
      full_name: "String should have at least 2 characters",
      email: "Enter an email address the mentor can be reached at.",
      "service.max_mentees":
        "The number of mentees in one session must be between 1 and 8.",
    });
    expect(mapped.general).toEqual([]);
  });

  it("keeps the first message when a field has two", () => {
    const mapped = toFieldErrors([
      { field: "email", message: "First message." },
      { field: "email", message: "Second message." },
    ]);

    expect(mapped.fields.email).toBe("First message.");
    expect(mapped.general).toEqual([]);
  });

  it("shows a message about an unrendered field above the form rather than dropping it", () => {
    const mapped = toFieldErrors([
      { field: "something_the_form_does_not_send", message: "This is not a field." },
    ]);

    expect(mapped.fields).toEqual({});
    expect(mapped.general).toEqual([
      "something_the_form_does_not_send: This is not a field.",
    ]);
  });

  it("shows an unnamed message as it stands", () => {
    const mapped = toFieldErrors([{ field: "", message: "Something is wrong." }]);

    expect(mapped.general).toEqual(["Something is wrong."]);
  });

  it("does not repeat the same unattached message twice", () => {
    const mapped = toFieldErrors([
      { field: "", message: "Something is wrong." },
      { field: "", message: "Something is wrong." },
    ]);

    expect(mapped.general).toEqual(["Something is wrong."]);
  });

  it("ignores an entry with no message at all", () => {
    const mapped = toFieldErrors([{ field: "email", message: "   " }], undefined);

    expect(mapped.fields).toEqual({});
    expect(mapped.general).toEqual([]);
  });

  it("falls back to the sentence the API sent when the list is empty", () => {
    const mapped = toFieldErrors([], "Some of the answers need changing.");

    expect(mapped.fields).toEqual({});
    expect(mapped.general).toEqual(["Some of the answers need changing."]);
  });

  it("copes with the list being absent", () => {
    const mapped = toFieldErrors(undefined, "That record does not exist.");

    expect(mapped.general).toEqual(["That record does not exist."]);
  });

  it("maps the fields a decision sends", () => {
    const mapped = toFieldErrors([
      {
        field: "final_price",
        message: "That is the advised price. Accept it instead.",
      },
    ]);

    expect(mapped.fields.final_price).toBe(
      "That is the advised price. Accept it instead.",
    );
  });
});

describe("messageFor", () => {
  it("says plainly when the API could not be reached", () => {
    expect(messageFor(new NetworkError(NETWORK_MESSAGE))).toBe(NETWORK_MESSAGE);
  });

  it("passes the API's own sentence through", () => {
    const error = new ApiError(404, {
      detail: "That record does not exist.",
      errors: [],
    });
    expect(messageFor(error)).toBe("That record does not exist.");
  });

  it("has something to say about an error it has never seen", () => {
    expect(messageFor(new Error("boom"))).toBe(UNEXPECTED_MESSAGE);
    expect(messageFor("not even an error")).toBe(UNEXPECTED_MESSAGE);
  });
});

describe("recognising the statuses the pages act on", () => {
  it("knows a missing record from an already answered price", () => {
    const missing = new ApiError(404, { detail: "Gone.", errors: [] });
    const decided = new ApiError(409, { detail: "Already answered.", errors: [] });

    expect(isNotFound(missing)).toBe(true);
    expect(isAlreadyDecided(missing)).toBe(false);
    expect(isAlreadyDecided(decided)).toBe(true);
    expect(isNotFound(decided)).toBe(false);
  });
});
