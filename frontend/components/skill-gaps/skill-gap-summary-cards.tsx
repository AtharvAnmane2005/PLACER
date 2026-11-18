"use client";

import { GraduationCap, MessageSquareWarning, Target, TrendingUp, Users } from "lucide-react";

import { StatCard } from "@/components/shared/stat-card";
import { formatCount } from "@/lib/format";
import type { SkillGapSummary } from "@/types/skill-gaps";

/**
 * The five summary cards. Every value is backend-computed; the labels state
 * exactly what each number means (documented definitions, not marketing).
 *
 * Long text values are split into a short value plus a `hint` so the card row
 * keeps a consistent height instead of stretching around one verbose cell.
 */
export function SkillGapSummaryCards({ summary }: { summary: SkillGapSummary }) {
  const missing = summary.most_demanded_missing_skill;
  const topRising = summary.rising_demand_skills[0];

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
      <StatCard
        label="Skills analyzed"
        value={formatCount(summary.total_skills_analyzed)}
        icon={Target}
      />
      <StatCard
        label="High-priority skill gaps"
        value={formatCount(summary.high_priority_gaps)}
        icon={MessageSquareWarning}
      />
      <StatCard
        label="Students without demonstrated skills"
        value={`${formatCount(summary.students_lacking_demonstrated_skills)} / ${formatCount(summary.student_population)}`}
        hint="of the student population"
        icon={GraduationCap}
      />
      <StatCard
        label="Most demanded missing skill"
        value={missing ? missing.name : "—"}
        valueClassName="text-lg"
        hint={
          missing
            ? `${missing.demand_pct}% of postings demand it`
            : "Every demanded skill has demonstrated students"
        }
        icon={Users}
      />
      <StatCard
        label="Fastest-rising demand"
        value={topRising ? topRising.name : "—"}
        valueClassName="text-lg"
        hint={
          topRising
            ? `+${topRising.latest_growth_pct}% latest comparable growth`
            : "No comparable previous period yet"
        }
        icon={TrendingUp}
      />
    </div>
  );
}
