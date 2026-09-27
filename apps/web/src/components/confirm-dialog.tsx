"use client";

import { Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { useErrorText } from "@/hooks/use-error-text";

/**
 * Confirmation gate for mutations. Extra form fields go in `children`; `canConfirm` disables the button.
 * Errors thrown by onConfirm stay in the dialog.
 */
export function ConfirmDialog({
  trigger,
  open: openProp,
  title,
  description,
  confirmLabel,
  destructive,
  canConfirm = true,
  onConfirm,
  onOpenChange,
  children,
}: {
  /** Omit for a controlled dialog (pass `open` + `onOpenChange`). */
  trigger?: ReactNode;
  open?: boolean;
  title: string;
  description?: ReactNode;
  confirmLabel: string;
  destructive?: boolean;
  canConfirm?: boolean;
  onConfirm: () => Promise<unknown> | unknown;
  onOpenChange?: (open: boolean) => void;
  children?: ReactNode;
}) {
  const t = useTranslations("common");
  const text = useErrorText();
  const [openState, setOpen] = useState(false);
  const open = openProp ?? openState;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const change = (o: boolean) => {
    if (busy) return;
    setOpen(o);
    setError(null);
    onOpenChange?.(o);
  };

  async function run() {
    setBusy(true);
    setError(null);
    try {
      await onConfirm();
      setBusy(false);
      change(false);
    } catch (e) {
      setError(e);
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={change}>
      {trigger && <DialogTrigger asChild>{trigger}</DialogTrigger>}
      <DialogContent showCloseButton={false}>
        <form
          className="grid gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (canConfirm && !busy) run();
          }}
        >
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            {description && <DialogDescription>{description}</DialogDescription>}
          </DialogHeader>
          {children}
          {error !== null && (
            <p role="alert" className="text-sm text-destructive">
              {text(error)}
            </p>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => change(false)} disabled={busy}>
              {t("cancel")}
            </Button>
            <Button type="submit" variant={destructive ? "destructive" : "default"} disabled={busy || !canConfirm}>
              {busy && <Loader2 className="animate-spin" aria-hidden />}
              {confirmLabel}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
