"use client";

/**
 * The administration page: calm, with a banner, a sidebar and five sections.
 *
 * **It is one route and not five.** The five sections are five views of the
 * same service, and somebody looking at them moves between them freely, so
 * paging between them would mean five route loads and five banners to read
 * past. The section is held in the query string, so a particular view can
 * still be linked and the browser's back button still works.
 *
 * **Only the open section is fetched.** Loading all six endpoints on arrival
 * would make a page about response times slow to open. Overview needs the
 * summary and the usage series; each of the others needs one endpoint; and
 * `useAsync` re-runs keyed on the section, so moving between them loads what
 * is missing and aborts whatever is in flight.
 *
 * **403 is reported as what it is.** The guard above sends a mentor to their
 * own dashboard, but a browser that got past it still gets 403 from all six
 * endpoints, and the page says so rather than showing an empty dashboard
 * that looks broken.
 *
 * Nothing here claims the price responds to demand, and nothing here can
 * change a mentor's price: all six endpoints are read only.
 */

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback } from "react";

import { ADMIN_SECTIONS, AdminNav } from "@/components/admin/chrome";
import {
  ModelsSection,
  OutputsSection,
  OverviewSection,
  RecentActivity,
  UsageSection,
  UsersSection,
} from "@/components/admin/sections";
import { RequireAdmin } from "@/components/require-admin";
import { Banner, Column, ErrorNotice, LoadingBlock } from "@/components/ui";
import { api } from "@/lib/api-client";
import type {
  AdminModels,
  AdminOutputs,
  AdminRecent,
  AdminSignups,
  AdminSummary,
  AdminUsage,
} from "@/lib/api-types";
import { ApiError } from "@/lib/errors";
import { messageFor } from "@/lib/errors";
import { useAsync } from "@/lib/use-async";

/** Everything one section might need, with the rest left null. */
interface SectionData {
  summary: AdminSummary | null;
  usage: AdminUsage | null;
  outputs: AdminOutputs | null;
  signups: AdminSignups | null;
  models: AdminModels | null;
  recent: AdminRecent | null;
}

const NOTHING: SectionData = {
  summary: null,
  usage: null,
  outputs: null,
  signups: null,
  models: null,
  recent: null,
};

const DEFAULT_SECTION = "overview";

function sectionFrom(value: string | null): string {
  return ADMIN_SECTIONS.some((section) => section.id === value)
    ? (value as string)
    : DEFAULT_SECTION;
}

/**
 * Fetch what the open section needs, and nothing else.
 *
 * The calls for one section go out together rather than one after another:
 * Overview needs two answers and asking for them in sequence would double
 * the wait for no benefit.
 */
async function loadSection(section: string, signal: AbortSignal): Promise<SectionData> {
  if (section === "usage") {
    return { ...NOTHING, usage: await api.admin.usage(signal) };
  }
  if (section === "outputs") {
    return { ...NOTHING, outputs: await api.admin.outputs(signal) };
  }
  if (section === "users") {
    return { ...NOTHING, signups: await api.admin.signups(signal) };
  }
  if (section === "models") {
    return { ...NOTHING, models: await api.admin.models(signal) };
  }
  const [summary, usage, recent] = await Promise.all([
    api.admin.summary(signal),
    api.admin.usage(signal),
    api.admin.recent(signal),
  ]);
  return { ...NOTHING, summary, usage, recent };
}

const FORBIDDEN_TITLE = "This account cannot read these pages";

const FORBIDDEN_MESSAGE =
  "The API refused the request. Administration is a flag on an account, set by whoever administers the deployment, and it is checked on the server for every request on these pages.";

function AdminSections() {
  const router = useRouter();
  const search = useSearchParams();
  const section = sectionFrom(search?.get("section") ?? null);

  const { status, data, error, reload } = useAsync<SectionData>(
    (signal) => loadSection(section, signal),
    section,
  );

  const choose = useCallback(
    (next: string) => {
      // replace rather than push: five sections of one page are one place,
      // and a back button that stepped through every section somebody
      // glanced at would not take them back to where they came from.
      router.replace(next === DEFAULT_SECTION ? "/admin" : `/admin?section=${next}`);
    },
    [router],
  );

  const refused = error instanceof ApiError && error.status === 403;

  return (
    <>
      <Banner
        title="Administration"
        lead="What the service has been asked to do, what it advised, and how the models scored. Read only."
      />

      <Column wide className="py-8">
        <div className="flex flex-col gap-6 wide:flex-row wide:gap-8">
          <AdminNav current={section} onSelect={choose} />

          <div className="min-w-0 flex-1">
            {status === "loading" ? <LoadingBlock label="Loading the figures" /> : null}

            {status === "error" ? (
              refused ? (
                <ErrorNotice title={FORBIDDEN_TITLE} message={FORBIDDEN_MESSAGE} />
              ) : (
                <ErrorNotice message={messageFor(error)} onRetry={reload} />
              )
            ) : null}

            {status === "ready" && data ? (
              <div className="space-y-6">
                {section === "overview" && data.summary && data.usage ? (
                  <>
                    <OverviewSection summary={data.summary} usage={data.usage} />
                    {data.recent ? <RecentActivity recent={data.recent} /> : null}
                  </>
                ) : null}

                {section === "usage" && data.usage ? (
                  <UsageSection usage={data.usage} />
                ) : null}

                {section === "outputs" && data.outputs ? (
                  <OutputsSection outputs={data.outputs} />
                ) : null}

                {section === "users" && data.signups ? (
                  <UsersSection signups={data.signups} />
                ) : null}

                {section === "models" && data.models ? (
                  <ModelsSection models={data.models} />
                ) : null}
              </div>
            ) : null}
          </div>
        </div>
      </Column>
    </>
  );
}

export default function AdminPage() {
  return (
    <RequireAdmin>
      {() => (
        // useSearchParams needs a boundary in the App Router, and the
        // fallback is the same loading block the page shows while fetching,
        // so the two states look like one.
        <Suspense
          fallback={
            <Column className="py-10">
              <LoadingBlock label="Loading the figures" />
            </Column>
          }
        >
          <AdminSections />
        </Suspense>
      )}
    </RequireAdmin>
  );
}
