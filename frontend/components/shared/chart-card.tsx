import type { ReactNode } from "react";
import { BarChart3 } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export interface ChartCardProps {
  title: string;
  description?: string;
  /** Filter controls or a link, rendered beside the title. */
  action?: ReactNode;
  /** Context/observation line rendered under the chart body. */
  footer?: ReactNode;
  children: ReactNode;
  className?: string;
  contentClassName?: string;
}

/**
 * Shared shell for a dashboard chart: title, plain-language description,
 * optional controls and the chart body. Every new dashboard chart uses this
 * so headings and spacing stay consistent with the existing cards.
 */
export function ChartCard({
  title,
  description,
  action,
  footer,
  children,
  className,
  contentClassName,
}: ChartCardProps) {
  return (
    <Card className={className}>
      <CardHeader className="flex flex-col gap-3 space-y-0 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <CardTitle className="text-base">{title}</CardTitle>
          {description && <CardDescription className="mt-1">{description}</CardDescription>}
        </div>
        {action && <div className="flex shrink-0 flex-wrap items-center gap-2">{action}</div>}
      </CardHeader>
      <CardContent className={cn(contentClassName)}>
        {children}
        {footer && <div className="mt-3 border-t border-border pt-3 text-xs text-muted-foreground">{footer}</div>}
      </CardContent>
    </Card>
  );
}

/**
 * Chart-specific empty state. Distinct from the page-level `EmptyState` so a
 * single chart can explain that the underlying records exist but the filtered
 * slice is empty without pushing the rest of the dashboard away.
 */
export function ChartEmptyState({
  title,
  description,
  height = 240,
}: {
  title: string;
  description: string;
  height?: number;
}) {
  return (
    <div
      className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border px-4 text-center"
      style={{ height }}
    >
      <div className="mb-2 rounded-full bg-secondary p-2">
        <BarChart3 className="h-4 w-4 text-muted-foreground" />
      </div>
      <p className="text-sm font-semibold">{title}</p>
      <p className="mt-1 max-w-xs text-xs text-muted-foreground">{description}</p>
    </div>
  );
}
