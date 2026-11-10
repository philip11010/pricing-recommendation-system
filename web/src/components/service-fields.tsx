"use client";

/**
 * The questions that set the price.
 *
 * The same block of questions is asked twice: at registration, where the
 * answers arrive nested under `service`, and when a mentor adds another
 * service, where they arrive at the top level. Hence `prefix`: the fields are
 * rendered once and the error names follow whichever shape the endpoint uses.
 *
 * Everything here is an answer the model is actually given, which is why the
 * heading says so. The profile questions on the step before are stored and
 * shown and never priced, and a mentor is entitled to know which is which.
 */

import type { OptionsResponse, ServiceInputPayload } from "@/lib/api-types";
import { formatSessions } from "@/lib/format";
import { sessionLabel } from "@/lib/session-label";

import { MenteeStepper, RadioGroup, SelectInput, SkillChecklist, Toggle } from "./form";

export interface ServiceFormState {
  field: string;
  maxMentees: number;
  minCommitment: string;
  skills: string[];
  profileVerified: boolean;
}

export function emptyServiceState(options: OptionsResponse | null): ServiceFormState {
  return {
    field: "",
    maxMentees: options?.max_mentees.min ?? 1,
    minCommitment: "",
    skills: [],
    profileVerified: false,
  };
}

/** What the API is sent, once the answers are complete. */
export function servicePayload(state: ServiceFormState): ServiceInputPayload {
  return {
    field: state.field,
    max_mentees: state.maxMentees,
    min_commitment: Number.parseInt(state.minCommitment, 10),
    skills: state.skills,
    profile_verified: state.profileVerified,
  };
}

/**
 * What has to change before this can be sent, named as the API names it.
 *
 * Checked here as well as by the API, because a mentor should not have to
 * wait for a round trip to be told they have chosen no field. The API checks
 * the same things again and its message wins when the two disagree.
 */
export function validateService(
  state: ServiceFormState,
  prefix: string,
): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!state.field) {
    errors[`${prefix}field`] = "Choose the field you mentor in.";
  }
  if (!state.minCommitment) {
    errors[`${prefix}min_commitment`] =
      "Choose the smallest number of sessions a mentee can book.";
  }
  if (state.skills.length === 0) {
    errors[`${prefix}skills`] = "Choose at least one skill or topic you cover.";
  }
  return errors;
}

export function ServiceFields({
  options,
  state,
  onChange,
  errors,
  prefix,
  servicesPlanned,
  onServicesPlannedChange,
  servicesPlannedError,
}: {
  options: OptionsResponse;
  state: ServiceFormState;
  onChange: (next: ServiceFormState) => void;
  errors: Record<string, string>;
  /** "service." at registration, "" when adding a service. */
  prefix: string;
  /**
   * How many services the mentor plans to offer. Asked at registration only:
   * once they are adding a second service, the system counts them instead.
   */
  servicesPlanned?: string;
  onServicesPlannedChange?: (value: string) => void;
  servicesPlannedError?: string;
}) {
  const label = sessionLabel(state.maxMentees, options.session_label_rule);

  function toggleSkill(skillId: string) {
    const chosen = new Set(state.skills);
    if (chosen.has(skillId)) {
      chosen.delete(skillId);
    } else {
      chosen.add(skillId);
    }
    // Kept in the order the API published them, so the list a mentor reads
    // back does not depend on the order they happened to tick them.
    onChange({
      ...state,
      skills: options.skills
        .map((skill) => skill.id)
        .filter((candidate) => chosen.has(candidate)),
    });
  }

  return (
    <div className="space-y-6">
      <SelectInput
        label="Field"
        placeholder="Choose your field"
        value={state.field}
        options={options.fields}
        onChange={(value) => onChange({ ...state, field: value })}
        error={errors[`${prefix}field`]}
        hint="The area your mentees come to you for."
      />

      <MenteeStepper
        label="Maximum mentees per session"
        value={state.maxMentees}
        min={options.max_mentees.min}
        max={options.max_mentees.max}
        onChange={(value) => onChange({ ...state, maxMentees: value })}
        sessionLabel={label}
        error={errors[`${prefix}max_mentees`]}
        hint={`One mentee is a one to one session. Two or more is a group. Up to ${options.max_mentees.max} mentees.`}
      />

      <SelectInput
        label="Minimum booking commitment"
        placeholder="Choose the smallest booking"
        value={state.minCommitment}
        options={options.min_commitment}
        onChange={(value) => onChange({ ...state, minCommitment: value })}
        error={errors[`${prefix}min_commitment`]}
        hint={`The fewest sessions a mentee can book at once. Choose ${formatSessions(1)} if they may book one at a time.`}
      />

      <SkillChecklist
        legend="Skills and topics"
        options={options.skills}
        selected={state.skills}
        onToggle={toggleSkill}
        error={errors[`${prefix}skills`]}
        hint="Choose at least one. These are what mentees search by."
      />

      {servicesPlanned !== undefined && onServicesPlannedChange ? (
        <RadioGroup
          legend="How many services do you plan to offer?"
          value={servicesPlanned}
          options={options.services_planned}
          onChange={onServicesPlannedChange}
          error={servicesPlannedError}
          hint="You can add more later. This helps us price a single service against a full offering."
        />
      ) : null}

      <Toggle
        label="My profile is verified"
        description="Tick this if you have completed identity verification. A verified profile is worth more to a mentee, and the suggestion reflects that."
        checked={state.profileVerified}
        onChange={(checked) => onChange({ ...state, profileVerified: checked })}
      />
    </div>
  );
}
