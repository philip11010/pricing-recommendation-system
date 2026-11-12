"use client";

/**
 * Add a service: calm, with a banner.
 *
 * A short form, because a mentor adding a second service has already told us
 * who they are. The three answers here are the three the price is worked out
 * from, and the live preview beside them is the same panel the registration
 * form uses.
 *
 * The mentor's existing skills are ticked to start with, since a second
 * service usually covers much of what the first one did, and every one of
 * them can be unticked.
 */

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { PillCheckbox, SelectInput, Stepper } from "@/components/form";
import { PricePreview } from "@/components/price-preview";
import { RequireAuth } from "@/components/require-auth";
import {
  Banner,
  Button,
  Column,
  ErrorNotice,
  LoadingBlock,
  TextLink,
} from "@/components/ui";
import { api } from "@/lib/api-client";
import type { Mentor, OptionsResponse } from "@/lib/api-types";
import { SKILL_GROUPS } from "@/lib/copy";
import { ApiError, messageFor, toFieldErrors } from "@/lib/errors";
import { useAsync } from "@/lib/use-async";

function AddServiceForm({
  mentor,
  options,
}: {
  mentor: Mentor;
  options: OptionsResponse;
}) {
  const router = useRouter();
  const existing = mentor.services[0] ?? null;

  const [field, setField] = useState(existing?.field ?? "");
  const [maxMentees, setMaxMentees] = useState(1);
  const [skills, setSkills] = useState<string[]>(existing?.skills ?? []);
  const [problems, setProblems] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  const skillLabels = useMemo(() => {
    const labels = new Map<string, string>();
    for (const skill of options.skills) {
      labels.set(skill.id, skill.label);
    }
    return labels;
  }, [options.skills]);

  function toggleSkill(id: string, on: boolean) {
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
      router.push(`/recommendation/${created.recommendation.id}`);
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
            onChange={(event) => setField(event.target.value)}
            error={problems.field ?? null}
          />

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
                      checked={skills.includes(id)}
                      onChange={(on) => toggleSkill(id, on)}
                    />
                  ))}
              </div>
            </fieldset>
          ))}
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
