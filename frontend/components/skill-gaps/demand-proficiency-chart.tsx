"use client";

import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartLegend, ChartTooltipCard } from "@/components/shared/chart-ui";
import {
  CHART_AXIS_STYLE,
  CHART_GRID_STROKE,
  CHART_TOOLTIP_STYLE,
  SERIES_COLORS,
  chartAxisLabel,
  percentTick,
} from "@/lib/chart-theme";
import type { SkillGapEntry } from "@/types/skill-gaps";

/**
 * Industry demand vs student proficiency, three series per skill:
 * demand %, assessment-demonstrated %, self-reported %. Self-reported is a
 * separate bar on purpose — reporting a skill is NOT demonstrating it.
 * Shows the top skills by priority (a chart of every skill is unreadable);
 * "Show all" expands the full list.
 */
const PREVIEW_COUNT = 12;

const SERIES = [
  { key: "Industry demand %", color: SERIES_COLORS.demand },
  { key: "Assessment-demonstrated %", color: SERIES_COLORS.demonstrated },
  { key: "Self-reported %", color: SERIES_COLORS.reported },
] as const;

interface TooltipEntry {
  dataKey?: string | number;
  name?: string | number;
  value?: number | string;
  payload?: { name?: string };
}

function DemandTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: TooltipEntry[];
}) {
  if (!active || !payload || payload.length === 0) return null;
  const rows = SERIES.flatMap((series) => {
    const entry = payload.find(
      (item) => item.dataKey === series.key || item.name === series.key
    );
    if (!entry) return [];
    return [
      {
        label: series.key,
        value: `${entry.value ?? "—"}%`,
        color: series.color,
      },
    ];
  });
  return (
    <ChartTooltipCard
      title={payload[0]?.payload?.name ?? "Skill"}
      rows={rows}
      footer="Self-reported is a separate signal, not proof of proficiency."
    />
  );
}

export function DemandProficiencyChart({ skills }: { skills: SkillGapEntry[] }) {
  const [showAll, setShowAll] = useState(false);
  const rows = showAll ? skills : skills.slice(0, PREVIEW_COUNT);
  const data = rows.map((skill) => ({
    name: skill.name,
    "Industry demand %": skill.demand_pct,
    "Assessment-demonstrated %": skill.demonstrated_pct,
    "Self-reported %": skill.reported_pct,
  }));

  if (skills.length === 0) return null;

  // The chart stays readable up to the preview count; the expanded view gets
  // a minimum width so three bars per skill never collapse into slivers.
  const scrollable = rows.length > PREVIEW_COUNT;
  const minWidth = scrollable ? Math.max(760, rows.length * 64) : undefined;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          Demand vs student proficiency
        </CardTitle>
        <CardDescription>
          Industry demand compared with two distinct student-evidence signals. Each metric keeps
          the same colour in every chart that shows it.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className={scrollable ? "overflow-x-auto pb-1" : undefined}>
          <div
            style={scrollable ? { minWidth } : undefined}
            role="img"
            aria-label="Industry demand compared with student proficiency by skill"
          >
            <ResponsiveContainer width="100%" height={380}>
              <BarChart
                data={data}
                margin={{ top: 8, right: 12, left: 4, bottom: 8 }}
                barGap={2}
                barCategoryGap="20%"
              >
                <CartesianGrid stroke={CHART_GRID_STROKE} strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey="name"
                  tick={{ ...CHART_AXIS_STYLE, fontSize: 10 }}
                  tickMargin={4}
                  interval={0}
                  angle={-30}
                  textAnchor="end"
                  height={96}
                  tickFormatter={(value: string) =>
                    value.length > 18 ? `${value.slice(0, 17)}…` : value
                  }
                  label={chartAxisLabel("Skill")}
                />
                <YAxis
                  domain={[0, 100]}
                  width={56}
                  tick={CHART_AXIS_STYLE}
                  tickMargin={4}
                  tickFormatter={percentTick}
                  label={chartAxisLabel("Share of students / postings (%)", "insideLeft")}
                />
                <Tooltip content={<DemandTooltip />} contentStyle={CHART_TOOLTIP_STYLE} />
                {SERIES.map((series) => (
                  <Bar
                    key={series.key}
                    dataKey={series.key}
                    name={series.key}
                    fill={series.color}
                    radius={[3, 3, 0, 0]}
                    maxBarSize={22}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <ChartLegend
          className="mt-3"
          ariaLabel="Demand and proficiency series legend"
          items={SERIES.map((series) => ({ label: series.key, color: series.color }))}
        />
        {skills.length > PREVIEW_COUNT && (
          <div className="mt-2 text-center">
            <Button variant="outline" size="sm" onClick={() => setShowAll((value) => !value)}>
              {showAll ? "Show top skills only" : `Show all ${skills.length} skills`}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
