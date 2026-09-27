"use client";

import { AlertCircle, Inbox } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useErrorText } from "@/hooks/use-error-text";

/** Error with retry. Pass `error` from client code or a pre-rendered `message` from server components. */
export function ErrorState({ error, message, onRetry }: { error?: unknown; message?: string; onRetry?: () => void }) {
  const t = useTranslations("common");
  const text = useErrorText();
  const router = useRouter();
  return (
    <Alert variant="destructive" role="alert" className="my-4">
      <AlertCircle />
      <AlertTitle>{t("errorTitle")}</AlertTitle>
      <AlertDescription>
        <p>{message ?? text(error)}</p>
        <Button variant="outline" size="sm" className="mt-2" onClick={onRetry ?? (() => router.refresh())}>
          {t("retry")}
        </Button>
      </AlertDescription>
    </Alert>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
      <Inbox className="size-6" aria-hidden />
      {children}
    </div>
  );
}

export function LoadingState({ rows = 3 }: { rows?: number }) {
  const t = useTranslations("common");
  return (
    <div role="status" aria-live="polite" className="space-y-2 py-2">
      <span className="sr-only">{t("loading")}</span>
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  );
}
