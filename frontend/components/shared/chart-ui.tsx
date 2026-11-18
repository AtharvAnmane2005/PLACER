import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export interface ChartSwatchProps {
  color: string;
  className?: string;
  shape?: "square" | "circle";
}

/** Small non-text colour cue. Always paired with a label by callers. */
export function ChartSwatch({ color, className, shape = "square" }: ChartSwatchProps) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "inline-block h-2.5 w-2.5 shrink-0 border border-black/5",
        shape === "circle" ? "rounded-full" : "rounded-sm",
        className
      )}
      style={{ backgroundColor: color }}
    />
  );
}

export interface ChartLegendItem {
  label: string;
  color: string;
  value?: ReactNode;
  detail?: ReactNode;
}

/** Shared legend: swatch colour, category name and optional value/detail. */
export function ChartLegend({
  items,
  ariaLabel,
  className,
}: {
  items: ChartLegendItem[];
  ariaLabel?: string;
  className?: string;
}) {
  if (items.length === 0) return null;
  return (
    <ul
      aria-label={ariaLabel}
      className={cn("flex flex-wrap items-center justify-center gap-x-4 gap-y-1.5", className)}
    >
      {items.map((item, index) => (
        <li key={`${item.label}-${index}`} className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <ChartSwatch color={item.color} />
          <span className="font-medium text-foreground">{item.label}</span>
          {item.value != null && <span className="tabular-nums">{item.value}</span>}
          {item.detail != null && <span className="text-muted-foreground">{item.detail}</span>}
        </li>
      ))}
    </ul>
  );
}

export interface ChartTooltipRow {
  label: ReactNode;
  value: ReactNode;
  color?: string;
  detail?: ReactNode;
}

/**
 * Shared tooltip body. Every row that represents a coloured mark carries the
 * same colour used by the chart, plus its category name — colour is never the
 * only cue.
 */
export function ChartTooltipCard({
  title,
  subtitle,
  rows,
  footer,
  className,
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  rows: ChartTooltipRow[];
  footer?: ReactNode;
  className?: string;
}) {
  const hasHeading = title != null || subtitle != null;
  return (
    <div
      className={cn(
        "min-w-[168px] rounded-md border border-border bg-popover p-3 text-sm text-popover-foreground shadow-md",
        className
      )}
    >
      {title != null && <p className="font-semibold">{title}</p>}
      {subtitle != null && <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p>}
      {rows.length > 0 && (
        <ul className={cn("space-y-1.5", hasHeading && "mt-2")}>
          {rows.map((row, index) => (
            <li key={index} className="flex items-start gap-2">
              {row.color ? (
                <ChartSwatch color={row.color} shape="circle" className="mt-1.5" />
              ) : (
                <span aria-hidden="true" className="mt-1.5 h-2.5 w-2.5 shrink-0" />
              )}
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="font-medium">{row.label}</span>
                  <span className="tabular-nums">{row.value}</span>
                </div>
                {row.detail != null && (
                  <p className="mt-0.5 text-xs text-muted-foreground">{row.detail}</p>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      {footer != null && (
        <p className="mt-2 border-t border-border pt-2 text-xs text-muted-foreground">{footer}</p>
      )}
    </div>
  );
}
