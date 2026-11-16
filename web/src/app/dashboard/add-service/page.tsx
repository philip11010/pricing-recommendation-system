"use client";

/**
 * Add a service: calm, with a banner.
 *
 * A short form, because a mentor adding a second service has already told us
 * who they are. The three answers here are the three the price is worked out
 * from, and the live preview beside them is the same panel the registration
 * form uses.
 *
 * All three answers start from the mentor's most recent service, since a new
 * service usually looks much like the last one they described, and every one
 * of them can be changed. The most recent rather than the first: a mentor who
 * has moved from one to one sessions to groups of six would otherwise be
 * handed the one to one they set up when they joined, every time.
 *
 * The prefilled skills are read under that service's own field, so the ten
 * labels a mentor sees on opening the form are the ten they saw when they
 * described it. Changing the field here clears the ticked skills at work and
 * says so, exactly as the registration form does, because the ten labels are
 * about to become ten different labels.
 */

import { useRouter } from "next/navigation";
import { useState } from "react";

import { SelectInput, Stepper } from "@/components/form";
import { PricePreview } from "@/components/price-preview";
import { RequireAuth } from "@/components/require-auth";
import { SkillPills } from "@/components/skill-pills";
import {
  Banner,
  Button,
  Column,
  ErrorNotice,
  LoadingBlock,
  Note,
  TextLink,
} from "@/components/ui";
import { api } from "@/lib/api-client";
import type { Mentor, OptionsResponse } from "@/lib/api-types";
import { WORK_SKILLS_RESET_NOTE } from "@/lib/copy";
import { ApiError, messageFor, toFieldErrors } from "@/lib/errors";
import { mostRecentService, startingGroupSize } from "@/lib/prefill";
import { refreshMentor } from "@/lib/session";
import { useAsync } from "@/lib/use-async";
import { countWorkSkills, withoutWorkSkills } from "@/lib/work-skills";

function AddServiceForm({
  mentor,
  options,
}: {
  mentor: Mentor;
  options: OptionsResponse;
}) {
  const router = useRouter();
  const existing = mostRecentService(mentor.services);

  const [field, setField] = useState(existing?.field ?? "");
  const [maxMentees, setMaxMentees] = useState(() =>
    startingGroupSize(existing, options.max_mentees),
  );
  const [skills, setSkills] = useState<string[]>(existing?.skills ?? []);
  const [problems, setProblems] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  /* Whether the last field change dropped any ticked skills at work. */
  const [workSkillsReset, setWorkSkillsReset] = useState(false);

  /**
   * Pick a field, and start the skills at work again.
   *
   * The same rule as the registration form: the ticked skills at work go and
   * the three constant headings stay. A mentor who opens this form and leaves
   * the prefilled field alone is told nothing, because nothing changed.
   */
  function chooseField(next: string) {
    if (next === field) {
      return;
    }
    setWorkSkillsReset(countWorkSkills(skills) > 0);
    setField(next);
    setSkills((was) => withoutWorkSkills(was));
  }

  function toggleSkill(id: string, on: boolean) {
    setWorkSkillsReset(false);
    setSkills((was) => (on ? [...was, id] : was.filter((skill) => skill !== id)));
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setFailure(null);

    if (!field) {
      setProblems({ field: "Choose the field this service is in." });
      return;
    }
    setProblems({});
    setSending(true);

    try {
      const created = await api.addService(mentor.id, {
        field,
        max_mentees: maxMentees,
        min_commitment: options.min_commitment_default,
        skills,
      });
      // The held record of this mentor lists their services, and it has just
      // become out of date. Asked for again rather than patched, so what the
      // next screen reads is the API's answer and not this page's guess.
      void refreshMentor();
      // Replace rather than push: the service exists now, and going back to
      // the form would offer to add the same one a second time.
      router.replace(`/recommendation/${created.recommendation.id}`);
    } catch (error) {
      if (error instanceof ApiError) {
        const mapped = toFieldErrors(error.fieldErrors, error.detail);
        setProblems(mapped.fields);
        setFailure(mapped.general[0] ?? null);
      } else {
        setFailure(messageFor(error));
      }
      setSending(false);
    }
  }

  return (
    <div className="grid items-start gap-8 wide:grid-cols-[minmax(0,1fr)_360px]">
      <form onSubmit={onSubmit} noValidate>
        {failure ? (
          <div
            role="alert"
            className="mb-6 rounded-card border border-line bg-danger-fill p-6 text-danger-700"
          >
            {failure}
          </div>
        ) : null}

        <section className="mb-6 rounded-card border border-line bg-surface p-6">
          <h2 className="text-h3 font-semibold">What this service is</h2>
          <p className="text-small text-ink-500">
            The name on your card follows from these two answers, so there is nothing
            else to type.
          </p>

          <SelectInput
            id="service-field"
            label="Field"
            helper="The area this service is in."
            placeholder="Choose a field"
            options={options.fields}
            value={field}
            onChange={(event) => chooseField(event.target.value)}
            error={problems.field ?? null}
          />

          {/* Prefilled from the mentor's most recent service, exactly as the
              field and the skills above are, and changed the same way. */}
          <Stepper
            id="service-group-size"
            label="How many people per session?"
            helper={`Choose 1 for one to one. Up to ${options.max_mentees.max} for a group.`}
            value={maxMentees}
            min={options.max_mentees.min}
            max={options.max_mentees.max}
            onChange={setMaxMentees}
            describe={(value) => (value === 1 ? "1 person" : `${value} people`)}
            error={problems.max_mentees ?? null}
          />
        </section>

        <section className="mb-6 rounded-card border border-line bg-surface p-6">
          <h2 className="text-h3 font-semibold">Skills it covers</h2>
          <p className="text-small text-ink-500">
            Ticked to match your profile. Change them to suit this service.
          </p>
          {problems.skills ? (
            <p role="alert" className="mt-2 text-small text-danger-700">
              {problems.skills}
            </p>
          ) : null}
          {workSkillsReset ? (
            <Note tone="info" role="status" className="mt-3">
              {WORK_SKILLS_RESET_NOTE}
            </Note>
          ) : null}
          <SkillPills
            field={field}
            skills={options.skills}
            chosen={skills}
            onToggle={toggleSkill}
          />
        </section>

        <Button type="submit" disabled={sending} aria-busy={sending}>
          {sending ? "Working out the price" : "See the suggested price"}
        </Button>
        <p className="mt-3 text-small">
          <TextLink href="/dashboard">Back to your dashboard</TextLink>
        </p>
      </form>

      <aside aria-label="Live price preview" className="wide:sticky wide:top-4">
        <PricePreview
          field={field}
          maxMentees={maxMentees}
          skills={skills}
          heading="Price for this service"
        />
      </aside>
    </div>
  );
}

export default function AddServicePage() {
  const options = useAsync((signal) => api.options(signal), "add-service-options");

  return (
    <RequireAuth>
      {(mentor) => (
        <>
          <Banner
            title="Add a service"
            lead="Offer something new and get a suggested price for it."
          />
          <Column wide className="py-10">
            {options.status === "loading" ? (
              <LoadingBlock label="Loading the form" />
            ) : null}
            {options.status === "error" ? (
              <ErrorNotice
                message={messageFor(options.error)}
                onRetry={options.reload}
              />
            ) : null}
            {options.status === "ready" && options.data ? (
              <AddServiceForm mentor={mentor} options={options.data} />
            ) : null}
          </Column>
        </>
      )}
    </RequireAuth>
  );
}
