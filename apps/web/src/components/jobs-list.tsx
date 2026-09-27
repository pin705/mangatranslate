"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { useJobList } from "@/components/dashboard-view";
import { JobsTable } from "@/components/jobs-table";
import { Pager } from "@/components/pager";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Button } from "@/components/ui/button";

const LIMIT = 20;

export function JobsList() {
  const t = useTranslations("jobs");
  const [offset, setOffset] = useState(0);
  const jobs = useJobList(`/jobs?limit=${LIMIT}&offset=${offset}`);
  if (jobs.error) return <ErrorState error={jobs.error} onRetry={jobs.reload} />;
  if (!jobs.data) return <LoadingState rows={6} />;
  if (jobs.data.total === 0)
    return (
      <EmptyState>
        <p>{t("empty")}</p>
        <Button asChild size="sm">
          <Link href="/jobs/new">{t("new")}</Link>
        </Button>
      </EmptyState>
    );
  return (
    <>
      <JobsTable jobs={jobs.data.items} />
      <Pager offset={offset} limit={LIMIT} total={jobs.data.total} onChange={setOffset} />
    </>
  );
}
