"use client";

import { RotateCcw } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";
import { JobStatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useErrorText } from "@/hooks/use-error-text";
import { api, type Job } from "@/lib/api";

export function JobsTable({ jobs }: { jobs: Job[] }) {
  const t = useTranslations("jobs");
  const format = useFormatter();
  const router = useRouter();
  const text = useErrorText();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function retry(id: string) {
    setBusy(id);
    setError(null);
    try {
      await api<Job>(`/jobs/${id}/retry`, { method: "POST" });
      router.push(`/jobs/${id}`);
    } catch (e) {
      setError(text(e));
      setBusy(null);
    }
  }

  return (
    <>
      {error && (
        <p role="alert" className="mb-2 text-sm text-destructive">
          {error}
        </p>
      )}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t("col.title")}</TableHead>
            <TableHead>{t("col.status")}</TableHead>
            <TableHead className="text-right">{t("col.pages")}</TableHead>
            <TableHead className="hidden sm:table-cell">{t("col.created")}</TableHead>
            <TableHead>
              <span className="sr-only">{t("col.actions")}</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {jobs.map((j) => (
            <TableRow key={j.id}>
              <TableCell className="max-w-64 truncate font-medium">
                <Link href={`/jobs/${j.id}`} className="hover:underline">
                  {j.title || t("untitled")}
                </Link>
              </TableCell>
              <TableCell>
                <JobStatusBadge status={j.status} />
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {j.pages_done}/{j.page_count || "–"}
              </TableCell>
              <TableCell className="hidden text-muted-foreground sm:table-cell">
                {format.dateTime(new Date(j.created_at), { dateStyle: "medium", timeStyle: "short" })}
              </TableCell>
              <TableCell className="text-right">
                {(j.status === "FAILED" || j.status === "PARTIAL") && (
                  <Button variant="outline" size="sm" disabled={busy === j.id} onClick={() => retry(j.id)}>
                    <RotateCcw aria-hidden />
                    {t("retry")}
                  </Button>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </>
  );
}
