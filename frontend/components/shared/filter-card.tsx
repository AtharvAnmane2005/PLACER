"use client";

import { useId, useState, type ReactNode } from "react";
import { ChevronDown, Filter } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/**
 * Compact, collapsible shell for the dashboard filter panels.
 *
 * The header always shows the applied-filter count and a short summary, so the
 * current selection is visible while the controls themselves stay collapsed.
 * Everything inside `children` is only mounted when expanded, which keeps the
 * collapsed panel to a single slim row.
 */
export function FilterCard({
  activeCount,
  summary,
  children,
  className,
}: {
  activeCount: number;
  summary: string;
  children: ReactNode;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const panelId = useId();

  return (
    <Card className={cn("shadow-sm", className)}>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-x-3 gap-y-2 space-y-0 px-4 py-3">
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <Filter className="h-4 w-4 shrink-0 text-muted-foreground" />
          <span className="shrink-0 text-sm font-semibold">Filters</span>
          {activeCount > 0 && (
            <Badge variant="secondary" className="shrink-0 px-1.5 py-0 text-[11px]">
              {activeCount} active
            </Badge>
          )}
          <span
            className="hidden min-w-0 truncate text-xs text-muted-foreground sm:inline"
            title={summary}
          >
            {summary}
          </span>
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="h-8 shrink-0 gap-1 px-2 text-xs"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((value) => !value)}
        >
          {open ? "Hide" : "Show"}
          <ChevronDown
            className={cn("h-4 w-4 transition-transform", open && "rotate-180")}
            aria-hidden="true"
          />
        </Button>
      </CardHeader>
      {open && (
        <CardContent id={panelId} className="space-y-4 border-t border-border px-4 pb-4 pt-4">
          {children}
        </CardContent>
      )}
    </Card>
  );
}
