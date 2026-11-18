import type { LucideIcon } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/**
 * Compact KPI card.
 *
 * Values may be numbers or short text. Long text is allowed to wrap (never
 * clipped) and an optional `hint` carries the detail, so a single wordy value
 * cannot stretch or crowd the rest of the row.
 */
export function StatCard({
  label,
  value,
  icon: Icon,
  hint,
  valueClassName,
  className,
}: {
  label: string;
  value: React.ReactNode;
  icon: LucideIcon;
  hint?: React.ReactNode;
  valueClassName?: string;
  className?: string;
}) {
  return (
    <Card className={cn("h-full transition-shadow hover:shadow-elevated", className)}>
      <CardContent className="flex items-start justify-between gap-3 p-5">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium leading-snug text-muted-foreground">{label}</p>
          <div
            className={cn(
              "mt-2 break-words text-2xl font-semibold leading-tight tabular-nums text-foreground",
              valueClassName
            )}
          >
            {value}
          </div>
          {hint ? (
            <p className="mt-1 text-xs leading-snug text-muted-foreground">{hint}</p>
          ) : null}
        </div>
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-light text-primary">
          <Icon className="h-5 w-5" />
        </div>
      </CardContent>
    </Card>
  );
}
