"use client";

/**
 * One mentor's public profile: calm.
 *
 * The same card the directory shows, with the skills they cover and whatever
 * they chose to add about themselves. Nothing private, and nothing a model
 * reads: the three optional fields here are profile text and are never part
 * of a price.
 */

import { useParams } from "next/navigation";

import { MentorCardTile } from "@/components/mentor-card";
import {
  Banner,
  Card,
  Chip,
  Column,
  ErrorNotice,
  LoadingBlock,
  TextLink,
} from "@/components/ui";
import { api } from "@/lib/api-client";
import { isNotFound, messageFor } from "@/lib/errors";
import { useAsync } from "@/lib/use-async";

export default function PublicProfilePage() {
  const params = useParams<{ id: string }>();
  const mentorId = Number.parseInt(params?.id ?? "", 10);

  const { status, data, error, reload } = useAsync(
    (signal) => api.publicMentor(mentorId, signal),
    `public-mentor-${mentorId}`,
  );

  const about = [
    data?.years_experience !== null && data?.years_experience !== undefined
      ? {
          label: "Years of experience",
          value: `${data.years_experience}`,
        }
      : null,
    data?.education_label ? { label: "Education", value: data.education_label } : null,
    data?.credentials ? { label: "Credentials", value: data.credentials } : null,
  ].filter((entry): entry is { label: string; value: string } => entry !== null);

  return (
    <>
      <Banner
        title={status === "ready" && data ? data.display_name : "Mentor profile"}
        lead={status === "ready" && data ? data.service_name : undefined}
      />
      <Column className="py-10">
        <p className="mb-6">
          <TextLink href="/mentors">Back to all mentors</TextLink>
        </p>

        {!Number.isInteger(mentorId) ? (
          <ErrorNotice
            title="We could not find that mentor"
            message="That link does not point at a mentor we hold."
          />
        ) : null}

        {Number.isInteger(mentorId) && status === "loading" ? (
          <LoadingBlock label="Loading this profile" />
        ) : null}

        {Number.isInteger(mentorId) && status === "error" ? (
          <ErrorNotice
            title={
              isNotFound(error)
                ? "We could not find that mentor"
                : "We could not load this"
            }
            message={
              isNotFound(error)
                ? "That profile does not exist, or it has no service on it yet."
                : messageFor(error)
            }
            onRetry={isNotFound(error) ? undefined : reload}
          />
        ) : null}

        {status === "ready" && data ? (
          <div className="grid items-start gap-6 wide:grid-cols-[360px_minmax(0,1fr)]">
            <MentorCardTile mentor={data} />

            <div className="grid gap-6">
              <Card>
                <h2 className="text-h3 font-semibold">Skills covered</h2>
                {data.skills.length > 0 ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {data.skills.map((skill) => (
                      <Chip key={skill.id}>{skill.label}</Chip>
                    ))}
                  </div>
                ) : (
                  <p className="mt-2 text-ink-700">
                    This mentor has not listed any skills yet.
                  </p>
                )}
              </Card>

              <Card>
                <h2 className="text-h3 font-semibold">About this mentor</h2>
                {about.length > 0 ? (
                  <dl className="mt-3 grid gap-3 mid:grid-cols-2">
                    {about.map((entry) => (
                      <div key={entry.label}>
                        <dt className="text-overline uppercase text-ink-500">
                          {entry.label}
                        </dt>
                        <dd className="mt-0.5">{entry.value}</dd>
                      </div>
                    ))}
                  </dl>
                ) : (
                  <p className="mt-2 text-ink-700">
                    This mentor has not added anything else to their profile yet.
                  </p>
                )}
              </Card>
            </div>
          </div>
        ) : null}
      </Column>
    </>
  );
}
