"use client";

/**
 * Registration, in three steps.
 *
 * The steps are grouped by what the answers are for, not by how many fit on a
 * screen: who you are, what mentees will read about you, and what sets your
 * price. The third step says so in its heading, because the second step's
 * answers are stored and shown and never priced, and a mentor who assumes
 * their degree moved the number would be wrong.
 *
 * There is no password field. The API has no authentication yet, so a
 * password box would be collecting something nothing checks.
 */

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  FormErrorSummary,
  ProgressSteps,
  SelectInput,
  TextArea,
  TextInput,
} from "@/components/form";
import {
  ServiceFields,
  type ServiceFormState,
  emptyServiceState,
  servicePayload,
  validateService,
} from "@/components/service-fields";
import { Button, Card, ErrorNotice, LoadingBlock, PageHeading } from "@/components/ui";
import { api } from "@/lib/api-client";
import type { OptionsResponse } from "@/lib/api-types";
import { ApiError, messageFor, toFieldErrors } from "@/lib/errors";
import { writeMentorId } from "@/lib/mentor-session";
import { useAsync } from "@/lib/use-async";

const STEP_NAMES = ["Account", "Profile", "Your service"];

/**
 * Which step an answer belongs to.
 *
 * Used when the API refuses a submission: the mentor is taken back to the
 * earliest step that has something wrong on it, rather than being left on the
 * last step reading about a field they cannot see.
 */
const STEP_OF_FIELD: Record<string, number> = {
  full_name: 0,
  email: 0,
  headline: 1,
  bio: 1,
  education_level: 1,
  experience_summary: 1,
  credentials: 1,
  years_mentoring_band: 1,
  services_planned: 2,
  "service.field": 2,
  "service.max_mentees": 2,
  "service.min_commitment": 2,
  "service.skills": 2,
  "service.profile_verified": 2,
};

interface AccountState {
  fullName: string;
  email: string;
}

interface ProfileState {
  headline: string;
  bio: string;
  educationLevel: string;
  experienceSummary: string;
  credentials: string;
  yearsMentoringBand: string;
}

const EMAIL_SHAPE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

function validateAccount(state: AccountState): Record<string, string> {
  const errors: Record<string, string> = {};
  if (state.fullName.trim().length < 2) {
    errors.full_name = "Enter your full name.";
  }
  if (!EMAIL_SHAPE.test(state.email.trim())) {
    errors.email = "Enter an email address we can reach you at.";
  }
  return errors;
}

function validateProfile(state: ProfileState): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!state.headline.trim()) {
    errors.headline = "Write one line about what you help mentees with.";
  }
  if (!state.bio.trim()) {
    errors.bio = "Write a short bio for your profile.";
  }
  if (!state.educationLevel) {
    errors.education_level = "Choose your highest level of education.";
  }
  if (!state.experienceSummary.trim()) {
    errors.experience_summary = "Say a little about your professional experience.";
  }
  if (!state.yearsMentoringBand) {
    errors.years_mentoring_band = "Choose how long you have been mentoring.";
  }
  return errors;
}

export default function RegisterPage() {
  const router = useRouter();
  const options = useAsync<OptionsResponse>((signal) => api.options(signal), "options");

  if (options.status === "loading") {
    return <LoadingBlock label="Loading the registration form" />;
  }
  if (options.status === "error" || options.data === null) {
    return <ErrorNotice message={messageFor(options.error)} onRetry={options.reload} />;
  }

  return (
    <RegistrationForm options={options.data} onDone={(path) => router.push(path)} />
  );
}

function RegistrationForm({
  options,
  onDone,
}: {
  options: OptionsResponse;
  onDone: (path: string) => void;
}) {
  const [step, setStep] = useState(0);
  const [account, setAccount] = useState<AccountState>({ fullName: "", email: "" });
  const [profile, setProfile] = useState<ProfileState>({
    headline: "",
    bio: "",
    educationLevel: "",
    experienceSummary: "",
    credentials: "",
    yearsMentoringBand: "",
  });
  const [service, setService] = useState<ServiceFormState>(() =>
    emptyServiceState(options),
  );
  const [servicesPlanned, setServicesPlanned] = useState("1");

  const [errors, setErrors] = useState<Record<string, string>>({});
  const [general, setGeneral] = useState<string[]>([]);
  const [sending, setSending] = useState(false);

  const summaryRef = useRef<HTMLDivElement | null>(null);
  const movedToSummary = useRef(false);

  // Focus the summary only when there is one, and only once per appearance,
  // so a mentor correcting a field is not dragged back up the page.
  useEffect(() => {
    if (general.length > 0 && !movedToSummary.current) {
      summaryRef.current?.focus();
      movedToSummary.current = true;
    }
    if (general.length === 0) {
      movedToSummary.current = false;
    }
  }, [general]);

  const clearError = useCallback((name: string) => {
    setErrors((current) => {
      if (!(name in current)) {
        return current;
      }
      const next = { ...current };
      delete next[name];
      return next;
    });
  }, []);

  function errorsForStep(index: number): Record<string, string> {
    if (index === 0) {
      return validateAccount(account);
    }
    if (index === 1) {
      return validateProfile(profile);
    }
    return validateService(service, "service.");
  }

  function goNext() {
    const found = errorsForStep(step);
    setErrors(found);
    if (Object.keys(found).length > 0) {
      setGeneral(["Some answers on this step still need filling in."]);
      return;
    }
    setGeneral([]);
    setStep((current) => Math.min(STEP_NAMES.length - 1, current + 1));
  }

  function goBack() {
    setGeneral([]);
    setErrors({});
    setStep((current) => Math.max(0, current - 1));
  }

  async function submit() {
    const found = {
      ...validateAccount(account),
      ...validateProfile(profile),
      ...validateService(service, "service."),
    };
    if (Object.keys(found).length > 0) {
      setErrors(found);
      const earliest = Math.min(
        ...Object.keys(found).map((name) => STEP_OF_FIELD[name] ?? 0),
      );
      setStep(earliest);
      setGeneral(["Some answers still need filling in before we can suggest a price."]);
      return;
    }

    setSending(true);
    setErrors({});
    setGeneral([]);
    try {
      const result = await api.register({
        full_name: account.fullName.trim(),
        email: account.email.trim(),
        years_mentoring_band: profile.yearsMentoringBand,
        services_planned: Number.parseInt(servicesPlanned, 10),
        headline: profile.headline.trim() || null,
        bio: profile.bio.trim() || null,
        education_level: profile.educationLevel || null,
        experience_summary: profile.experienceSummary.trim() || null,
        credentials: profile.credentials.trim() || null,
        service: servicePayload(service),
      });
      writeMentorId(result.mentor.id, result.mentor.full_name);
      onDone(`/recommendation/${result.recommendation.id}`);
    } catch (error) {
      if (error instanceof ApiError && error.fieldErrors.length > 0) {
        const mapped = toFieldErrors(error.fieldErrors, error.detail);
        setErrors(mapped.fields);
        setGeneral(mapped.general.length > 0 ? mapped.general : [error.detail]);
        const named = Object.keys(mapped.fields);
        if (named.length > 0) {
          setStep(Math.min(...named.map((name) => STEP_OF_FIELD[name] ?? 0)));
        }
      } else {
        setGeneral([messageFor(error)]);
      }
      setSending(false);
    }
  }

  const lastStep = step === STEP_NAMES.length - 1;

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeading
        title="Become a mentor"
        lead="Three short steps. The last one ends with a suggested price for your first service."
      />

      <Card>
        <ProgressSteps steps={STEP_NAMES} current={step} />

        <div ref={summaryRef} tabIndex={-1}>
          <FormErrorSummary messages={general} />
        </div>

        <form
          className="mt-4 space-y-6"
          // The browser's own validation is turned off on purpose. The email
          // box is type="email", and left to itself the browser refuses the
          // submission before onSubmit runs and shows a tooltip of its own,
          // which is not tied to the field, disappears on the next click and
          // is worded by the browser rather than by us. With noValidate the
          // messages this form writes are the only ones a mentor sees, and
          // each one is tied to its field with aria-describedby.
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            if (lastStep) {
              void submit();
            } else {
              goNext();
            }
          }}
        >
          {step === 0 ? (
            <fieldset className="space-y-6">
              <legend className="sr-only">Account</legend>
              <h2 className="text-lg font-semibold">Your account</h2>
              <TextInput
                label="Full name"
                name="full_name"
                value={account.fullName}
                autoComplete="name"
                maxLength={200}
                error={errors.full_name}
                onChange={(value) => {
                  clearError("full_name");
                  setAccount({ ...account, fullName: value });
                }}
              />
              <TextInput
                label="Email address"
                name="email"
                type="email"
                autoComplete="email"
                maxLength={320}
                value={account.email}
                error={errors.email}
                hint="We use it to find your account. There is no password yet."
                onChange={(value) => {
                  clearError("email");
                  setAccount({ ...account, email: value });
                }}
              />
            </fieldset>
          ) : null}

          {step === 1 ? (
            <fieldset className="space-y-6">
              <legend className="sr-only">Profile</legend>
              <div>
                <h2 className="text-lg font-semibold">Your profile</h2>
                <p className="mt-1 text-sm text-ink-muted">
                  This is what mentees read. None of it is used to work out your price.
                </p>
              </div>
              <TextInput
                label="Headline"
                name="headline"
                maxLength={300}
                value={profile.headline}
                error={errors.headline}
                placeholder="Helping graduate engineers find their first role"
                onChange={(value) => {
                  clearError("headline");
                  setProfile({ ...profile, headline: value });
                }}
              />
              <TextArea
                label="Short bio"
                name="bio"
                maxLength={4000}
                value={profile.bio}
                error={errors.bio}
                hint="A few sentences about who you are and who you help."
                onChange={(value) => {
                  clearError("bio");
                  setProfile({ ...profile, bio: value });
                }}
              />
              <SelectInput
                label="Highest education"
                name="education_level"
                placeholder="Choose your highest level"
                value={profile.educationLevel}
                options={options.education_levels}
                error={errors.education_level}
                onChange={(value) => {
                  clearError("education_level");
                  setProfile({ ...profile, educationLevel: value });
                }}
              />
              <TextArea
                label="Professional experience"
                name="experience_summary"
                rows={3}
                maxLength={4000}
                value={profile.experienceSummary}
                error={errors.experience_summary}
                onChange={(value) => {
                  clearError("experience_summary");
                  setProfile({ ...profile, experienceSummary: value });
                }}
              />
              <TextArea
                label="Credentials"
                name="credentials"
                rows={2}
                optional
                maxLength={4000}
                value={profile.credentials}
                error={errors.credentials}
                hint="Licences, memberships or certifications, if you have them."
                onChange={(value) => {
                  clearError("credentials");
                  setProfile({ ...profile, credentials: value });
                }}
              />
              <SelectInput
                label="Years of mentoring experience"
                name="years_mentoring_band"
                placeholder="Choose a range"
                value={profile.yearsMentoringBand}
                options={options.years_mentoring_bands}
                error={errors.years_mentoring_band}
                hint="Shown on your profile. It does not change your price."
                onChange={(value) => {
                  clearError("years_mentoring_band");
                  setProfile({ ...profile, yearsMentoringBand: value });
                }}
              />
            </fieldset>
          ) : null}

          {step === 2 ? (
            <fieldset className="space-y-6">
              <legend className="sr-only">Your service</legend>
              <div>
                <h2 className="text-lg font-semibold">Your service</h2>
                <p className="mt-1 text-sm text-ink-muted">
                  These are the answers that set your price.
                </p>
              </div>
              <ServiceFields
                options={options}
                state={service}
                onChange={(next) => {
                  setErrors({});
                  setService(next);
                }}
                errors={errors}
                prefix="service."
                servicesPlanned={servicesPlanned}
                onServicesPlannedChange={(value) => {
                  clearError("services_planned");
                  setServicesPlanned(value);
                }}
                servicesPlannedError={errors.services_planned}
              />
            </fieldset>
          ) : null}

          <div className="flex flex-wrap items-center gap-3 border-t border-line pt-5">
            {step > 0 ? (
              <Button tone="quiet" onClick={goBack} disabled={sending}>
                Back
              </Button>
            ) : null}
            <Button type="submit" disabled={sending}>
              {lastStep
                ? sending
                  ? "Working out your price"
                  : "Suggest my price"
                : "Continue"}
            </Button>
            {sending ? (
              <p aria-live="polite" className="text-sm text-ink-soft">
                Sending your answers.
              </p>
            ) : null}
          </div>
        </form>
      </Card>
    </div>
  );
}
