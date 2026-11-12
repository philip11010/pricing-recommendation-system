"use client";

/**
 * Register: calm, with a banner.
 *
 * One long page rather than a stepper, so a mentor can see how much is left,
 * with the live price preview beside it. Four parts: the account, what they
 * offer, the skills they cover, and an optional collapsed section for the
 * three profile fields that are shown on their card and never priced.
 *
 * Every option list comes from /meta/options. The only part of the skill list
 * this file decides is which of the four headings each skill is read under,
 * and that lives in lib/copy.ts with a test that none can go missing.
 *
 * The answers live in one component with the preview panel, so the figure
 * beside the form is worked out from the same state the form submits.
 */

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  ErrorSummary,
  PillCheckbox,
  SelectInput,
  Stepper,
  TextInput,
  type SummaryProblem,
} from "@/components/form";
import { PricePreview } from "@/components/price-preview";
import {
  Banner,
  Button,
  Column,
  ErrorNotice,
  LoadingBlock,
  TextLink,
} from "@/components/ui";
import { api } from "@/lib/api-client";
import type { OptionsResponse } from "@/lib/api-types";
import { SKILL_GROUPS, UNVERIFIED_AFTER_SUBMIT } from "@/lib/copy";
import { ApiError, messageFor, toFieldErrors } from "@/lib/errors";
import { setMentor } from "@/lib/session";
import { writeToken } from "@/lib/token";
import { useAsync } from "@/lib/use-async";

const PASSWORD_MIN = 8;

interface Answers {
  name: string;
  email: string;
  password: string;
  field: string;
  maxMentees: number;
  skills: string[];
  yearsExperience: string;
  educationLevel: string;
  credentials: string;
}

const EMPTY: Answers = {
  name: "",
  email: "",
  password: "",
  field: "",
  maxMentees: 1,
  skills: [],
  yearsExperience: "",
  educationLevel: "",
  credentials: "",
};

/** The id of the input each message jumps to, keyed as the API names it. */
const FIELD_IDS: Record<string, string> = {
  name: "register-name",
  email: "register-email",
  password: "register-password",
  field: "register-field",
  max_mentees: "register-group-size",
  skills: "register-skills",
  years_experience: "register-years",
  education_level: "register-education",
  credentials: "register-credentials",
};

/** What this application can tell is wrong before it asks the API. */
/** The answers that live inside the optional section. */
const OPTIONAL_FIELDS = ["years_experience", "education_level", "credentials"];

function localProblems(
  answers: Answers,
  bounds: { min: number; max: number },
): Record<string, string> {
  const problems: Record<string, string> = {};
  if (answers.name.trim().length < 2) {
    problems.name = "Tell us the name mentees will see.";
  }
  if (!answers.email.trim()) {
    problems.email = "Enter an email address so you can log back in.";
  } else if (!answers.email.includes("@")) {
    problems.email = "Enter an email address we can reach you at.";
  }
  if (answers.password.length < PASSWORD_MIN) {
    problems.password = `Choose a password of at least ${PASSWORD_MIN} characters.`;
  }
  if (!answers.field) {
    problems.field = "Choose the field you mentor in most.";
  }
  if (answers.yearsExperience) {
    const years = Number(answers.yearsExperience);
    if (!Number.isInteger(years) || years < bounds.min || years > bounds.max) {
      problems.years_experience = `Give a whole number of years between ${bounds.min} and ${bounds.max}, or leave it blank.`;
    }
  }
  return problems;
}

function Registration({ options }: { options: OptionsResponse }) {
  const router = useRouter();
  const [answers, setAnswers] = useState<Answers>(EMPTY);
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [submitted, setSubmitted] = useState(false);
  const [sending, setSending] = useState(false);
  const [fromApi, setFromApi] = useState<{
    fields: Record<string, string>;
    general: string[];
  }>({ fields: {}, general: [] });

  const summaryRef = useRef<HTMLDivElement>(null);
  const [summarySignal, setSummarySignal] = useState(0);
  /*
   * Whether the optional section is open.
   *
   * It starts closed, because nothing in it is required, and it is forced
   * open by a failed submit that found a problem inside it: an error nobody
   * can see is an error nobody can fix.
   */
  const [optionalOpen, setOptionalOpen] = useState(false);

  const skillLabels = useMemo(() => {
    const labels = new Map<string, string>();
    for (const skill of options.skills) {
      labels.set(skill.id, skill.label);
    }
    return labels;
  }, [options.skills]);

  const problems = {
    ...localProblems(answers, options.years_experience),
    ...fromApi.fields,
  };

  const show = (name: string): string | null =>
    touched[name] || submitted ? (problems[name] ?? null) : null;

  const summary: SummaryProblem[] = submitted
    ? Object.entries(problems).map(([name, message]) => ({
        id: FIELD_IDS[name] ?? FIELD_IDS.name,
        message,
      }))
    : [];

  const generalProblems: SummaryProblem[] = fromApi.general.map((message) => ({
    id: FIELD_IDS.name,
    message,
  }));

  useEffect(() => {
    if (summarySignal > 0) {
      summaryRef.current?.focus();
    }
  }, [summarySignal]);

  function update<K extends keyof Answers>(key: K, value: Answers[K]) {
    setAnswers((was) => ({ ...was, [key]: value }));
    setFromApi({ fields: {}, general: [] });
  }

  function toggleSkill(id: string, on: boolean) {
    setAnswers((was) => ({
      ...was,
      skills: on ? [...was.skills, id] : was.skills.filter((skill) => skill !== id),
    }));
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitted(true);
    setFromApi({ fields: {}, general: [] });

    const found = localProblems(answers, options.years_experience);
    if (Object.keys(found).length > 0) {
      if (Object.keys(found).some((name) => OPTIONAL_FIELDS.includes(name))) {
        setOptionalOpen(true);
      }
      setSummarySignal((count) => count + 1);
      return;
    }

    setSending(true);
    try {
      const answer = await api.register({
        name: answers.name.trim(),
        email: answers.email.trim(),
        password: answers.password,
        field: answers.field,
        max_mentees: answers.maxMentees,
        skills: answers.skills,
        min_commitment: options.min_commitment_default,
        years_experience: answers.yearsExperience
          ? Number(answers.yearsExperience)
          : null,
        education_level: answers.educationLevel || null,
        credentials: answers.credentials.trim() || null,
      });
      writeToken(answer.access_token);
      setMentor(answer.mentor);
      // Replace rather than push: the form has been submitted and the
      // account exists, so going back to it would offer to register the same
      // mentor again.
      router.replace(`/recommendation/${answer.recommendation.id}`);
    } catch (error) {
      const mapped =
        error instanceof ApiError
          ? toFieldErrors(error.fieldErrors, error.detail)
          : { fields: {}, general: [messageFor(error)] };
      if (Object.keys(mapped.fields).some((name) => OPTIONAL_FIELDS.includes(name))) {
        setOptionalOpen(true);
      }
      setFromApi(mapped);
      setSending(false);
      setSummarySignal((count) => count + 1);
    }
  }

  return (
    <div className="grid items-start gap-8 wide:grid-cols-[minmax(0,1fr)_360px]">
      <form onSubmit={onSubmit} noValidate>
        <ErrorSummary ref={summaryRef} problems={[...generalProblems, ...summary]} />

        <section className="mb-6 rounded-card border border-line bg-surface p-6">
          <h2 className="text-h3 font-semibold">Your account</h2>
          <p className="text-small text-ink-500">So you can log back in.</p>
          <div className="grid gap-4 mid:grid-cols-2">
            <TextInput
              id={FIELD_IDS.name}
              label="Full name"
              autoComplete="name"
              placeholder="e.g. Amara Njoroge"
              value={answers.name}
              onChange={(event) => update("name", event.target.value)}
              onBlur={() => setTouched((was) => ({ ...was, name: true }))}
              error={show("name")}
            />
            <TextInput
              id={FIELD_IDS.email}
              label="Email"
              type="email"
              autoComplete="email"
              placeholder="you@example.com"
              value={answers.email}
              onChange={(event) => update("email", event.target.value)}
              onBlur={() => setTouched((was) => ({ ...was, email: true }))}
              error={show("email")}
            />
          </div>
          <TextInput
            id={FIELD_IDS.password}
            label="Password"
            type="password"
            autoComplete="new-password"
            helper={`At least ${PASSWORD_MIN} characters.`}
            value={answers.password}
            onChange={(event) => update("password", event.target.value)}
            onBlur={() => setTouched((was) => ({ ...was, password: true }))}
            error={show("password")}
          />
        </section>

        <section className="mb-6 rounded-card border border-line bg-surface p-6">
          <h2 className="text-h3 font-semibold">What you offer</h2>
          <p className="text-small text-ink-500">
            This does most of the work in your price.
          </p>
          <SelectInput
            id={FIELD_IDS.field}
            label="Your field"
            helper="The area you mentor in most."
            placeholder="Choose a field"
            options={options.fields}
            value={answers.field}
            onChange={(event) => update("field", event.target.value)}
            onBlur={() => setTouched((was) => ({ ...was, field: true }))}
            error={show("field")}
          />
          <Stepper
            id={FIELD_IDS.max_mentees}
            label="How many people per session?"
            helper={`Choose 1 for one to one. Up to ${options.max_mentees.max} for a group.`}
            value={answers.maxMentees}
            min={options.max_mentees.min}
            max={options.max_mentees.max}
            onChange={(next) => update("maxMentees", next)}
            describe={(value) => (value === 1 ? "1 person" : `${value} people`)}
            error={show("max_mentees")}
          />
        </section>

        <section
          id={FIELD_IDS.skills}
          className="mb-6 rounded-card border border-line bg-surface p-6"
        >
          <h2 className="text-h3 font-semibold">Skills you cover</h2>
          <p className="text-small text-ink-500">
            Tick everything that applies. Covering more skills slightly raises the
            suggestion.
          </p>
          {show("skills") ? (
            <p role="alert" className="mt-2 text-small text-danger-700">
              {show("skills")}
            </p>
          ) : null}
          {SKILL_GROUPS.map((group) => (
            <fieldset key={group.name} className="mt-5 min-w-0">
              <legend className="mb-2.5 text-overline uppercase text-ink-500">
                {group.name}
              </legend>
              <div className="flex flex-wrap gap-2">
                {group.skillIds
                  .filter((id) => skillLabels.has(id))
                  .map((id) => (
                    <PillCheckbox
                      key={id}
                      label={skillLabels.get(id) ?? id}
                      checked={answers.skills.includes(id)}
                      onChange={(on) => toggleSkill(id, on)}
                    />
                  ))}
              </div>
            </fieldset>
          ))}
        </section>

        <details
          className="group mb-6 rounded-card border border-line bg-surface"
          open={optionalOpen}
          onToggle={(event) => setOptionalOpen(event.currentTarget.open)}
        >
          <summary className="flex min-h-[44px] cursor-pointer items-center justify-between gap-3 px-6 py-5">
            <span>
              <span className="block text-h3 font-semibold">More about you</span>
              <span className="block text-small text-ink-500">
                Optional. Adds to your public profile. Shown on your card, not used in
                the price.
              </span>
            </span>
            <span
              aria-hidden="true"
              className="h-2.5 w-2.5 flex-none rotate-45 border-b-2 border-r-2 border-ink-700 transition-transform duration-[180ms] ease-entrance group-open:-rotate-[135deg]"
            />
          </summary>
          <div className="px-6 pb-6">
            <div className="grid gap-4 mid:grid-cols-2">
              <TextInput
                id={FIELD_IDS.years_experience}
                label="Years of experience"
                type="number"
                inputMode="numeric"
                min={options.years_experience.min}
                max={options.years_experience.max}
                placeholder="e.g. 8"
                value={answers.yearsExperience}
                onChange={(event) => update("yearsExperience", event.target.value)}
                onBlur={() => setTouched((was) => ({ ...was, years_experience: true }))}
                error={show("years_experience")}
              />
              <SelectInput
                id={FIELD_IDS.education_level}
                label="Education"
                placeholder="Prefer not to say"
                options={options.education_levels}
                value={answers.educationLevel}
                onChange={(event) => update("educationLevel", event.target.value)}
                error={show("education_level")}
              />
            </div>
            <TextInput
              id={FIELD_IDS.credentials}
              label="Credentials"
              placeholder="e.g. Certified coach, CPA"
              value={answers.credentials}
              onChange={(event) => update("credentials", event.target.value)}
              error={show("credentials")}
            />
          </div>
        </details>

        <Button type="submit" disabled={sending} aria-busy={sending}>
          {sending ? "Working out your price" : "See my suggested price"}
        </Button>
        <p className="mt-3 text-small text-ink-500">{UNVERIFIED_AFTER_SUBMIT}</p>
        <p className="mt-3 text-small">
          Already registered? <TextLink href="/login">Log in instead</TextLink>
        </p>
      </form>

      <aside aria-label="Live price preview" className="wide:sticky wide:top-4">
        <PricePreview
          field={answers.field}
          maxMentees={answers.maxMentees}
          skills={answers.skills}
        />
      </aside>
    </div>
  );
}

export default function RegisterPage() {
  const { status, data, error, reload } = useAsync(
    (signal) => api.options(signal),
    "register-options",
  );

  return (
    <>
      <Banner
        title="Create your mentor profile"
        lead="Four short parts. We use them to suggest a price. You can change anything later."
      />
      <Column wide className="py-10">
        {status === "loading" ? <LoadingBlock label="Loading the form" /> : null}
        {status === "error" ? (
          <ErrorNotice message={messageFor(error)} onRetry={reload} />
        ) : null}
        {status === "ready" && data ? <Registration options={data} /> : null}
      </Column>
    </>
  );
}
