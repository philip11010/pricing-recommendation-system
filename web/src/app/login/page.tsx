"use client";

/**
 * Log in: bold register.
 *
 * The gradient fills the screen and holds one white card, so nothing competes
 * with the two fields. A refusal is reported in one sentence that does not
 * say which of the two answers was wrong, because the API does not say
 * either, and guessing would tell a visitor which addresses have accounts.
 */

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

import { ErrorSummary, TextInput, type SummaryProblem } from "@/components/form";
import { Button, Note, RaisedCard, TextLink } from "@/components/ui";
import { api } from "@/lib/api-client";
import { LOGIN_FAILED, SESSION_EXPIRED } from "@/lib/copy";
import { ApiError, messageFor } from "@/lib/errors";
import { setMentor } from "@/lib/session";
import { EXPIRED_QUERY, writeToken } from "@/lib/token";

function emailProblem(value: string): string | null {
  if (!value.trim()) {
    return "Enter the email address you registered with.";
  }
  if (!value.includes("@")) {
    return "Enter an email address we can reach you at.";
  }
  return null;
}

function passwordProblem(value: string): string | null {
  return value ? null : "Enter your password.";
}

function LoginForm() {
  const router = useRouter();
  const search = useSearchParams();
  const expired = search?.get(EXPIRED_QUERY) === "1";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const summaryRef = useRef<HTMLDivElement>(null);

  const problems = {
    email: emailProblem(email),
    password: passwordProblem(password),
  };

  const shown = (name: keyof typeof problems) =>
    touched[name] || submitted ? problems[name] : null;

  const summary: SummaryProblem[] = [];
  if (submitted && problems.email) {
    summary.push({ id: "login-email", message: problems.email });
  }
  if (submitted && problems.password) {
    summary.push({ id: "login-password", message: problems.password });
  }

  useEffect(() => {
    if (summary.length > 0) {
      summaryRef.current?.focus();
    }
    // Only when a submit produced problems, not on every keystroke.
  }, [submitted, summary.length]);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitted(true);
    setFailure(null);
    if (problems.email || problems.password) {
      return;
    }
    setSending(true);
    try {
      const answer = await api.login({ email: email.trim(), password });
      writeToken(answer.access_token);
      setMentor(answer.mentor);
      router.push("/dashboard");
    } catch (error) {
      setFailure(
        error instanceof ApiError && error.status === 401
          ? LOGIN_FAILED
          : messageFor(error),
      );
      setSending(false);
    }
  }

  return (
    <RaisedCard className="w-full max-w-[440px]">
      <h1 className="text-h2 font-bold">Welcome back</h1>
      <p className="mt-1 text-small text-ink-500">
        Log in to see your price history and how you compare.
      </p>

      {expired ? (
        <Note tone="info" className="mt-4">
          {SESSION_EXPIRED}
        </Note>
      ) : null}

      <form onSubmit={onSubmit} noValidate className="mt-2">
        <ErrorSummary ref={summaryRef} problems={summary} />

        {failure ? (
          <div
            role="alert"
            className="mb-4 rounded-field bg-danger-fill px-3.5 py-3 text-small text-danger-700"
          >
            {failure}
          </div>
        ) : null}

        <TextInput
          id="login-email"
          label="Email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          onBlur={() => setTouched((was) => ({ ...was, email: true }))}
          error={shown("email")}
        />
        <TextInput
          id="login-password"
          label="Password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          onBlur={() => setTouched((was) => ({ ...was, password: true }))}
          error={shown("password")}
        />

        <Button
          type="submit"
          className="mt-4 w-full"
          disabled={sending}
          aria-busy={sending}
        >
          {sending ? "Logging in" : "Log in"}
        </Button>
      </form>

      <p className="mt-5 text-center text-small">
        New here? <TextLink href="/register">Register as a mentor</TextLink>
      </p>
    </RaisedCard>
  );
}

export default function LoginPage() {
  return (
    <div className="on-gradient grid min-h-[70vh] place-items-center bg-hero px-4 py-10 sm:px-6">
      <Suspense fallback={null}>
        <LoginForm />
      </Suspense>
    </div>
  );
}
