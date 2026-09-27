"use client";

import { useId, type ComponentProps, type ReactNode } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useErrorText } from "@/hooks/use-error-text";

/** Labelled input with an optional hint wired up via aria-describedby. */
export function Field({ label, hint, ...props }: { label: string; hint?: ReactNode } & ComponentProps<typeof Input>) {
  const id = useId();
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} aria-describedby={hint ? `${id}-hint` : undefined} {...props} />
      {hint && (
        <p id={`${id}-hint`} className="text-xs text-muted-foreground">
          {hint}
        </p>
      )}
    </div>
  );
}

export function FormError({ error }: { error: unknown }) {
  const text = useErrorText();
  if (error === null || error === undefined) return null;
  return (
    <p role="alert" className="text-sm text-destructive">
      {typeof error === "string" ? error : text(error)}
    </p>
  );
}
