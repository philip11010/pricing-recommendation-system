"use client";

/**
 * Another service, priced as soon as it is described.
 *
 * The same questions as the third step of registration, rendered from the
 * same component, because they are the same questions: the API asks for them
 * the same way and validates them the same way, and two forms that drift
 * apart would be two different claims about what sets a price.
 *
 * One thing is not asked again. How many services the mentor plans to offer
 * is a registration question; once they are adding a second service, the
 * system counts the services it has rather than asking.
 */

import { useRouter } from "next/navigation";
import { useState } from "react";

import { FormErrorSummary } from "@/components/form";
import { RequireMentor } from "@/components/require-mentor";
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
import { useAsync } from "@/lib/use-async";

export default function AddServicePage() {
  return (
    <RequireMentor>
      {(mentorId) => <AddServiceForm mentorId={mentorId} />}
    </RequireMentor>
  );
}

function AddServiceForm({ mentorId }: { mentorId: number }) {
  const router = useRouter();
  const options = useAsync<OptionsResponse>((signal) => api.options(signal), "options");

  const [service, setService] = useState<ServiceFormState | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [general, setGeneral] = useState<string[]>([]);
  const [sending, setSending] = useState(false);

  if (options.status === "loading") {
    return <LoadingBlock label="Loading the form" />;
  }
  if (options.status === "error" || options.data === null) {
    return <ErrorNotice message={messageFor(options.error)} onRetry={options.reload} />;
  }

  const loaded = options.data;
  const state = service ?? emptyServiceState(loaded);

  async function submit() {
    const found = validateService(state, "");
    if (Object.keys(found).length > 0) {
      setErrors(found);
      setGeneral(["Some answers still need filling in before we can suggest a price."]);
      return;
    }

    setSending(true);
    setErrors({});
    setGeneral([]);
    try {
      const result = await api.addService(mentorId, servicePayload(state));
      router.push(`/recommendation/${result.recommendation.id}`);
    } catch (error) {
      if (error instanceof ApiError && error.fieldErrors.length > 0) {
        const mapped = toFieldErrors(error.fieldErrors, error.detail);
        setErrors(mapped.fields);
        setGeneral(mapped.general.length > 0 ? mapped.general : [error.detail]);
      } else {
        setGeneral([messageFor(error)]);
      }
      setSending(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeading
        title="Add another service"
        lead="Describe the session and we will suggest a price for it. These are the answers that set the price."
      />

      <Card>
        <FormErrorSummary messages={general} />

        <form
          className="mt-4 space-y-6"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <ServiceFields
            options={loaded}
            state={state}
            onChange={(next) => {
              setErrors({});
              setService(next);
            }}
            errors={errors}
            prefix=""
          />

          <div className="flex flex-wrap items-center gap-3 border-t border-line pt-5">
            <Button type="submit" disabled={sending}>
              {sending ? "Working out your price" : "Suggest my price"}
            </Button>
            <Button
              tone="quiet"
              onClick={() => router.push("/dashboard")}
              disabled={sending}
            >
              Cancel
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
