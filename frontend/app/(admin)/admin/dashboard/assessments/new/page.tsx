"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ClipboardCheck, Layers3, Tags } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { CategoryMultiSelect } from "@/components/shared/category-multiselect";
import { TemplateManagerDialog } from "@/components/shared/template-manager";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/shared/empty-state";
import { useToast } from "@/hooks/use-toast";
import { useCreateAssessment } from "@/hooks/use-admin-assessments";
import { useCategories } from "@/hooks/use-admin-questions";
import { useTemplates } from "@/hooks/use-assessment-templates";
import { useGeneratePlacementAssessment } from "@/hooks/use-placement-assessments";
import { useDrives } from "@/hooks/use-drives";

const assessmentSchema = z.object({
  title: z.string().min(1, "Title is required."),
  category_ids: z.array(z.string()).min(1, "Select at least one category."),
  question_pool_size: z.coerce.number().int().min(1).max(100),
  time_limit_minutes: z.coerce.number().int().min(1).max(300),
  max_violations: z.coerce.number().int().min(1).max(20),
  require_fullscreen: z.boolean(),
  type: z.enum(["practice", "drive"]),
});

type AssessmentFormValues = z.infer<typeof assessmentSchema>;
type CreationMode = "adaptive" | "standardized";

function detailMessage(err: any, fallback: string): string {
  const detail = err?.response?.data?.detail;
  if (typeof detail === "string" && detail) return detail;
  if (detail && typeof detail === "object") {
    const parts: string[] = [];
    if (typeof detail.message === "string") parts.push(detail.message);
    if (Array.isArray(detail.deficits)) parts.push(...detail.deficits);
    if (parts.length > 0) return parts.join(" · ");
  }
  return fallback;
}

export default function NewAssessmentPage() {
  const router = useRouter();
  const { toast } = useToast();
  const [mode, setMode] = useState<CreationMode>("adaptive");
  const [templateDialogOpen, setTemplateDialogOpen] = useState(false);

  const { data: categories, isLoading: categoriesLoading } = useCategories();
  const { data: drives, isLoading: drivesLoading } = useDrives();
  const { data: templates } = useTemplates("active");
  const createAssessment = useCreateAssessment();
  const generatePlacement = useGeneratePlacementAssessment();

  const [driveId, setDriveId] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [adaptiveTemplateId, setAdaptiveTemplateId] = useState("");
  const [publish, setPublish] = useState(true);

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<AssessmentFormValues>({
    resolver: zodResolver(assessmentSchema),
    defaultValues: {
      category_ids: [],
      question_pool_size: 10,
      time_limit_minutes: 30,
      max_violations: 3,
      require_fullscreen: true,
      type: "practice",
    },
  });

  const selectedCategoryIds = watch("category_ids");

  const onSubmitAdaptive = async (values: AssessmentFormValues) => {
    try {
      const created = await createAssessment.mutateAsync({
        title: values.title,
        category_ids: values.category_ids,
        question_pool_size: values.question_pool_size,
        time_limit_sec: values.time_limit_minutes * 60,
        max_violations: values.max_violations,
        require_fullscreen: values.require_fullscreen,
        type: values.type,
        format: "adaptive",
      });
      toast({ title: "Assessment created", description: `${created.title} is now available to students.` });
      router.push("/admin/dashboard/assessments");
    } catch (err) {
      toast({ title: "Creation failed", description: detailMessage(err, "Couldn't create the assessment."), variant: "destructive" });
    }
  };

  const onSubmitStandardized = async () => {
    if (!driveId) {
      toast({ title: "Select a drive", description: "Standardized assessments are generated for a placement drive.", variant: "destructive" });
      return;
    }
    try {
      const created = await generatePlacement.mutateAsync({
        drive_id: driveId,
        template_id: templateId || null,
        publish,
      });
      toast({
        title: "Standardized assessment generated",
        description: `${created.title} — ${created.total_questions} questions, ${created.total_marks} marks.`,
      });
      router.push("/admin/dashboard/assessments");
    } catch (err) {
      toast({
        title: "Generation failed",
        description: detailMessage(err, "The question bank may not meet the 20-question quota."),
        variant: "destructive",
      });
    }
  };

  const standardizedTemplates = (templates ?? []).filter((template) => template.format === "standardized");
  const adaptiveTemplates = (templates ?? []).filter((template) => template.format === "adaptive");

  const applyAdaptiveTemplate = (id: string) => {
    setAdaptiveTemplateId(id);
    const template = adaptiveTemplates.find((item) => item.id === id);
    if (!template) return;
    const validIds = new Set((categories ?? []).map((category) => category.id));
    const categoryIds = (
      template.category_ids.length > 0
        ? template.category_ids
        : Array.from(new Set(template.sections.flatMap((section) => section.category_ids)))
    ).filter((categoryId) => validIds.has(categoryId));
    setValue("title", template.name, { shouldValidate: true });
    setValue("category_ids", categoryIds, { shouldValidate: true });
    if (template.total_questions > 0) {
      setValue("question_pool_size", Math.min(100, template.total_questions), { shouldValidate: true });
    }
    setValue("time_limit_minutes", Math.max(1, Math.round(template.time_limit_sec / 60)), {
      shouldValidate: true,
    });
  };

  return (
    <div className="max-w-3xl">
      <h1 className="mb-1 font-display text-2xl font-semibold">New assessment</h1>
      <p className="mb-6 text-sm text-muted-foreground">
        Create an adaptive practice or drive assessment, or generate a fixed standardized test for a drive.
      </p>

      <div className="mb-6 flex flex-wrap gap-2">
        {(["adaptive", "standardized"] as const).map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => setMode(option)}
            className={`rounded-full border px-4 py-2 text-sm capitalize transition-colors ${
              mode === option
                ? "border-primary bg-primary text-primary-foreground"
                : "border-border hover:bg-secondary"
            }`}
          >
            {option}
          </button>
        ))}
      </div>

      {mode === "standardized" ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <ClipboardCheck className="h-4 w-4" /> Standardized placement assessment
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="rounded-md border border-border bg-secondary/40 p-3 text-xs text-muted-foreground">
              Exactly 20 questions are selected once: 4 each from Quantitative Aptitude, Logical Reasoning,
              Verbal Ability, Technical Knowledge and Programming / Problem Solving, with 6 Easy, 10 Medium and
              4 Hard questions. The same set, order, marks and duration are used by every student.
            </div>
            <div className="space-y-2">
              <Label htmlFor="standard-drive">Placement drive</Label>
              {drivesLoading ? (
                <Skeleton className="h-10 w-full" />
              ) : (
                <Select value={driveId} onValueChange={setDriveId}>
                  <SelectTrigger id="standard-drive"><SelectValue placeholder="Select a drive" /></SelectTrigger>
                  <SelectContent>
                    {(drives ?? []).map((drive) => (
                      <SelectItem key={drive.id} value={drive.id}>
                        {drive.job_title} — {drive.company.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="standard-template">Template (optional)</Label>
                <Button type="button" size="sm" variant="outline" onClick={() => setTemplateDialogOpen(true)}>
                  <Layers3 className="mr-1.5 h-3.5 w-3.5" /> Manage templates
                </Button>
              </div>
              <Select value={templateId || "none"} onValueChange={(value) => setTemplateId(value === "none" ? "" : value)}>
                <SelectTrigger id="standard-template"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Use default configuration</SelectItem>
                  {standardizedTemplates.map((template) => (
                    <SelectItem key={template.id} value={template.id}>{template.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {standardizedTemplates.length === 0 && (
                <p className="text-xs text-muted-foreground">
                  No standardized templates yet. Use <span className="font-medium">Manage templates</span> to create one.
                </p>
              )}
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={publish} onChange={(e) => setPublish(e.target.checked)} />
              Publish immediately
            </label>
          </CardContent>
          <CardFooter className="gap-2">
            <Button onClick={onSubmitStandardized} disabled={generatePlacement.isPending}>
              {generatePlacement.isPending ? "Generating…" : "Generate standardized assessment"}
            </Button>
            <Button type="button" variant="secondary" onClick={() => router.back()}>Cancel</Button>
          </CardFooter>
        </Card>
      ) : !categoriesLoading && (!categories || categories.length === 0) ? (
        <EmptyState
          icon={Tags}
          title="No categories yet"
          description="Create at least one question category with some questions in it before building an assessment."
        />
      ) : (
        <Card>
          <form onSubmit={handleSubmit(onSubmitAdaptive)}>
            <CardHeader>
              <CardTitle className="text-base">Adaptive assessment details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Label htmlFor="adaptive-template">Start from a saved template (optional)</Label>
                  <Button type="button" size="sm" variant="outline" onClick={() => setTemplateDialogOpen(true)}>
                    <Layers3 className="mr-1.5 h-3.5 w-3.5" /> Manage templates
                  </Button>
                </div>
                <Select
                  value={adaptiveTemplateId || "none"}
                  onValueChange={(value) => applyAdaptiveTemplate(value === "none" ? "" : value)}
                >
                  <SelectTrigger id="adaptive-template"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Start blank</SelectItem>
                    {adaptiveTemplates.map((template) => (
                      <SelectItem key={template.id} value={template.id}>{template.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  Selecting a template pre-fills the fields below. You can still adjust everything before creating.
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="title">Title</Label>
                <Input id="title" placeholder="e.g. Core CS Fundamentals" {...register("title")} />
                {errors.title && <p className="text-sm text-destructive">{errors.title.message}</p>}
              </div>

              <div className="space-y-2">
                <Label>Assessment type</Label>
                <div className="flex gap-2">
                  {(["practice", "drive"] as const).map((option) => {
                    const active = watch("type") === option;
                    return (
                      <button
                        type="button"
                        key={option}
                        onClick={() => setValue("type", option, { shouldValidate: true })}
                        className={`rounded-md border px-3 py-1.5 text-sm capitalize transition-colors ${
                          active ? "border-primary bg-primary text-primary-foreground" : "border-border hover:bg-secondary"
                        }`}
                      >
                        {option}
                      </button>
                    );
                  })}
                </div>
                <p className="text-xs text-muted-foreground">
                  Practice assessments are for student self-improvement and are excluded from drive rankings.
                  Drive assessments are linked to a drive by a TPO and appear in drive rankings.
                </p>
              </div>

              <div className="space-y-2">
                <Label>Categories to draw questions from</Label>
                {categoriesLoading ? (
                  <Skeleton className="h-20 w-full" />
                ) : (
                  <CategoryMultiSelect
                    categories={categories ?? []}
                    value={selectedCategoryIds ?? []}
                    onChange={(ids) => setValue("category_ids", ids, { shouldValidate: true })}
                  />
                )}
                {errors.category_ids && <p className="text-sm text-destructive">{errors.category_ids.message}</p>}
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="question_pool_size">Number of questions</Label>
                  <Input id="question_pool_size" type="number" min={1} max={100} {...register("question_pool_size")} />
                  {errors.question_pool_size && (
                    <p className="text-sm text-destructive">{errors.question_pool_size.message}</p>
                  )}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="time_limit_minutes">Time limit (minutes)</Label>
                  <Input id="time_limit_minutes" type="number" min={1} max={300} {...register("time_limit_minutes")} />
                  {errors.time_limit_minutes && (
                    <p className="text-sm text-destructive">{errors.time_limit_minutes.message}</p>
                  )}
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="max_violations">Max anti-cheat violations before auto-submit</Label>
                <Input id="max_violations" type="number" min={1} max={20} {...register("max_violations")} />
              </div>

              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" className="h-4 w-4 rounded border-input" {...register("require_fullscreen")} />
                Require fullscreen mode during the attempt
              </label>
            </CardContent>
            <CardFooter className="gap-2">
              <Button type="submit" disabled={isSubmitting}>
                {isSubmitting ? "Creating…" : "Create adaptive assessment"}
              </Button>
              <Button type="button" variant="secondary" onClick={() => router.back()}>Cancel</Button>
            </CardFooter>
          </form>
        </Card>
      )}

      <TemplateManagerDialog
        open={templateDialogOpen}
        onOpenChange={setTemplateDialogOpen}
        categories={categories ?? []}
        selectedTemplateId={templateId}
        onUseTemplate={(template) => {
          setTemplateId(template.id);
          setMode("standardized");
        }}
      />
    </div>
  );
}
