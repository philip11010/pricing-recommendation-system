/**
 * A message about a field has to reach someone who cannot see it turn red.
 *
 * The registration form turns the browser's own validation off, so these
 * messages are the only ones a mentor gets. That makes their wiring part of
 * the application's behaviour rather than a styling detail: the message is
 * tied to its field with aria-describedby, the field is marked invalid, and
 * the message is announced when it appears rather than only when the field is
 * reached.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SelectInput, TextInput } from "@/components/form";

describe("a field with a message about it", () => {
  it("ties the message to the input and marks the input invalid", () => {
    render(
      <TextInput
        label="Email address"
        type="email"
        value="not-an-address"
        onChange={() => {}}
        error="Enter an email address we can reach you at."
      />,
    );

    const input = screen.getByLabelText("Email address");
    expect(input).toHaveAttribute("aria-invalid", "true");

    const describedBy = input.getAttribute("aria-describedby");
    expect(describedBy).toBeTruthy();
    const ids = (describedBy ?? "").split(" ");
    const message = screen.getByText("Enter an email address we can reach you at.");
    expect(ids).toContain(message.id);
  });

  it("announces the message, so pressing Continue is not silent", () => {
    render(
      <TextInput
        label="Full name"
        value=""
        onChange={() => {}}
        error="Enter your full name."
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Enter your full name.");
  });

  it("keeps the helper text as well as the message, in that order", () => {
    render(
      <TextInput
        label="Email address"
        type="email"
        value=""
        onChange={() => {}}
        helper="We use it to find your account."
        error="Enter an email address we can reach you at."
      />,
    );

    const input = screen.getByLabelText("Email address");
    const ids = (input.getAttribute("aria-describedby") ?? "").split(" ");
    expect(ids).toHaveLength(2);
    expect(document.getElementById(ids[0] ?? "")).toHaveTextContent(
      "We use it to find your account.",
    );
    expect(document.getElementById(ids[1] ?? "")).toHaveTextContent(
      "Enter an email address we can reach you at.",
    );
  });

  it("says nothing about a field that is answered", () => {
    render(<TextInput label="Full name" value="Test Mentor" onChange={() => {}} />);

    const input = screen.getByLabelText("Full name");
    expect(input).not.toHaveAttribute("aria-invalid");
    expect(input).not.toHaveAttribute("aria-describedby");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("wires a dropdown the same way", () => {
    render(
      <SelectInput
        label="Field"
        value=""
        options={[{ id: "technology_software", label: "Technology and software" }]}
        onChange={() => {}}
        error="Choose the field you mentor in."
      />,
    );

    const select = screen.getByLabelText("Field");
    expect(select).toHaveAttribute("aria-invalid", "true");
    const ids = (select.getAttribute("aria-describedby") ?? "").split(" ");
    expect(ids).toContain(screen.getByRole("alert").id);
  });
});
