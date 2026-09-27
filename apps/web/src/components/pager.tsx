"use client";

import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";

export function Pager({
  offset,
  limit,
  total,
  onChange,
}: {
  offset: number;
  limit: number;
  total: number;
  onChange: (offset: number) => void;
}) {
  const t = useTranslations("common");
  if (total <= limit && offset === 0) return null;
  return (
    <nav aria-label={t("pagination")} className="flex items-center justify-between gap-2 py-3 text-sm">
      <p className="text-muted-foreground">
        {t("range", { from: total ? offset + 1 : 0, to: Math.min(offset + limit, total), total })}
      </p>
      <div className="flex gap-2">
        <Button variant="outline" size="sm" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>
          {t("previous")}
        </Button>
        <Button variant="outline" size="sm" disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}>
          {t("next")}
        </Button>
      </div>
    </nav>
  );
}
