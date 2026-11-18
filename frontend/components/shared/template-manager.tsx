"use client";

import { Copy, Layers3, Pencil, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import { CategoryMultiSelect, type CategoryOption } from "@/components/shared/category-multiselect";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { EmptyState } from "@/components/shared/empty-state";
import { useToast } from "@/hooks/use-toast";
import {
  useCreateTemplate,
  useDuplicateTemplate,
  useSetTemplateStatus,
  useTemplatePresets,
  useTemplates,
  useUpdateTemplate,
} from "@/hooks/use-assessment-templates";
import type {
  AssessmentFormat,
  AssessmentTemplateResponse,
  AssessmentTemplateUpsertRequest,
  DifficultyLevel,
  QuestionType,
  SectionConfig,
  TemplateStatus,
} from "@/types/assessment";

const QUESTION_TYPES: QuestionType[] = ["mcq", "multiple_select", "true_false", "coding", "descriptive"];
const DIFFICULTIES: DifficultyLevel[] = ["easy", "medium", "hard"];

function blankConfig(): AssessmentTemplateUpsertRequest {
  return {
    name: "",
    description: "",
    category_ids: [],
    sections: [],
    difficulty_distribution: { easy: 0, medium: 0, hard: 0 },
    question_types: ["mcq"],
    topics: [],
    skills: [],
    total_questions: 0,
    total_marks: 0,
    time_limit_sec: 1800,
    passing_marks: 0,
    negative_marks: 0,
    instructions: "",
    randomize_options: false,
    allow_retake: false,
    status: "active",
    format: "standardized",
  };
}

/** Resolve preset/template category names to real IDs and drop unknown values. */
function resolveCategoryIds(values: string[], categories: CategoryOption[]): string[] {
  if (categories.length === 0) return values;
  const ids = new Set(categories.map((category) => category.id));
  const byName = new Map(categories.map((category) => [category.name.trim().toLowerCase(), category.id]));
  const resolved = values
    .map((value) => (ids.has(value) ? value : byName.get(value.trim().toLowerCase()) ?? null))
    .filter((value): value is string => Boolean(value));
  return Array.from(new Set(resolved));
}

function detailMessage(err: any, fallback: string): string {
  const detail = err?.response?.data?.detail;
  if (typeof detail === "string" && detail) return detail;
  if (detail && typeof detail === "object" && typeof detail.message === "string") return detail.message;
  return fallback;
}

interface TemplateManagerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  categories: CategoryOption[];
  /** Called when the admin chooses a template for the assessment being created. */
  onUseTemplate?: (template: AssessmentTemplateResponse) => void;
  selectedTemplateId?: string;
}

export function TemplateManagerDialog({
  open,
  onOpenChange,
  categories,
  onUseTemplate,
  selectedTemplateId,
}: TemplateManagerDialogProps) {
  const { data: templates, isLoading } = useTemplates();
  const { data: presets } = useTemplatePresets();
  const createTemplate = useCreateTemplate();
  const updateTemplate = useUpdateTemplate();
  const duplicateTemplate = useDuplicateTemplate();
  const setStatus = useSetTemplateStatus();
  const { toast } = useToast();

  const [view, setView] = useState<"list" | "edit">("list");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [config, setConfig] = useState<AssessmentTemplateUpsertRequest>(blankConfig());
  const [presetKey, setPresetKey] = useState("placement_drive_mock");
  const [topicsText, setTopicsText] = useState("");
  const [skillsText, setSkillsText] = useState("");

  const isStandardized = config.format === "standardized";
  const isSaving = createTemplate.isPending || updateTemplate.isPending;

  useEffect(() => {
    if (!open) {
      setView("list");
      setEditingId(null);
    }
  }, [open]);

  // Load the selected preset into a fresh configuration.
  useEffect(() => {
    if (!open || view !== "edit" || editingId) return;
    const preset = presets?.find((item) => item.key === presetKey);
    if (!preset) return;
    const next = JSON.parse(JSON.stringify(preset.config)) as AssessmentTemplateUpsertRequest;
    next.category_ids = resolveCategoryIds(next.category_ids, categories);
    next.sections = next.sections.map((section) => ({
      ...section,
      category_ids: resolveCategoryIds(section.category_ids, categories),
    }));
    setConfig(next);
    setTopicsText(next.topics.join(", "));
    setSkillsText(next.skills.join(", "));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [presetKey, open, view, editingId, presets]);

  const openCreate = () => {
    setEditingId(null);
    setPresetKey("placement_drive_mock");
    setConfig(blankConfig());
    setTopicsText("");
    setSkillsText("");
    setView("edit");
  };

  const openEdit = (template: AssessmentTemplateResponse) => {
    setEditingId(template.id);
    setPresetKey(template.preset_key ?? "");
    setConfig({
      ...template,
      category_ids: resolveCategoryIds(template.category_ids, categories),
      sections: template.sections.map((section) => ({
        ...section,
        category_ids: resolveCategoryIds(section.category_ids, categories),
      })),
    });
    setTopicsText(template.topics.join(", "));
    setSkillsText(template.skills.join(", "));
    setView("edit");
  };

  const patch = <K extends keyof AssessmentTemplateUpsertRequest>(
    key: K,
    value: AssessmentTemplateUpsertRequest[K]
  ) => setConfig((current) => ({ ...current, [key]: value }));

  const patchSection = (index: number, changes: Partial<SectionConfig>) => {
    setConfig((current) => ({
      ...current,
      sections: current.sections.map((section, i) => (i === index ? { ...section, ...changes } : section)),
    }));
  };

  const removeSection = (index: number) => {
    setConfig((current) => ({ ...current, sections: current.sections.filter((_, i) => i !== index) }));
  };

  const addSection = () => {
    setConfig((current) => ({
      ...current,
      sections: [
        ...current.sections,
        { name: `Section ${current.sections.length + 1}`, questions: 1, category_ids: [] },
      ],
    }));
  };

  const splitList = (value: string): string[] =>
    value
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);

  const handleSave = async () => {
    const name = config.name.trim();
    if (!name) {
      toast({ title: "Template name is required", variant: "destructive" });
      return;
    }
    if (config.sections.length === 0) {
      toast({ title: "Add at least one section", variant: "destructive" });
      return;
    }
    const invalidSection = config.sections.find(
      (section) => !section.name.trim() || section.questions < 1
    );
    if (invalidSection) {
      toast({
        title: "Fix the section configuration",
        description: "Every section needs a name and at least one question.",
        variant: "destructive",
      });
      return;
    }

    const configured = config.sections.reduce((total, section) => total + section.questions, 0);
    const payload: AssessmentTemplateUpsertRequest = {
      ...config,
      name,
      description: config.description.trim(),
      topics: splitList(topicsText),
      skills: splitList(skillsText),
      total_questions: isStandardized ? config.total_questions : configured,
      sections: config.sections.map((section) => ({
        ...section,
        name: section.name.trim(),
        category_ids: section.category_ids,
      })),
    };

    try {
      if (editingId) {
        await updateTemplate.mutateAsync({ id: editingId, payload });
        toast({ title: "Template updated" });
      } else {
        await createTemplate.mutateAsync(payload);
        toast({ title: "Template created" });
      }
      setView("list");
      setEditingId(null);
    } catch (err) {
      toast({
        title: "Couldn't save template",
        description: detailMessage(err, "Check the template configuration."),
        variant: "destructive",
      });
    }
  };

  const handleDuplicate = async (id: string) => {
    try {
      await duplicateTemplate.mutateAsync(id);
      toast({ title: "Template duplicated" });
    } catch (err) {
      toast({ title: "Couldn't duplicate", description: detailMessage(err, ""), variant: "destructive" });
    }
  };

  const handleStatus = async (template: AssessmentTemplateResponse) => {
    const next: TemplateStatus = template.status === "active" ? "inactive" : "active";
    try {
      await setStatus.mutateAsync({ id: template.id, status: next });
      toast({ title: `Template marked ${next}` });
    } catch (err) {
      toast({ title: "Status update failed", description: detailMessage(err, ""), variant: "destructive" });
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-4xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{view === "edit" ? (editingId ? "Edit template" : "New template") : "Assessment templates"}</DialogTitle>
          <DialogDescription>
            {view === "edit"
              ? "Templates store configuration only — never questions or answer keys."
              : "Choose a saved configuration, or create one without leaving assessment creation."}
          </DialogDescription>
        </DialogHeader>

        {view === "list" ? (
          <div className="space-y-4">
            <div className="flex justify-end">
              <Button size="sm" onClick={openCreate}>
                <Plus className="mr-1.5 h-3.5 w-3.5" /> New template
              </Button>
            </div>

            {isLoading ? (
              <Skeleton className="h-40 w-full" />
            ) : !templates || templates.length === 0 ? (
              <EmptyState
                icon={Layers3}
                title="No templates yet"
                description="Start from a preset to save a reusable assessment configuration."
                action={<Button size="sm" onClick={openCreate}>Create template</Button>}
              />
            ) : (
              <div className="overflow-x-auto rounded-md border border-border">
                <table className="w-full text-left text-sm">
                  <thead className="bg-secondary/60 text-xs uppercase tracking-wide text-muted-foreground">
                    <tr>
                      <th className="p-2.5 font-medium">Template</th>
                      <th className="p-2.5 font-medium">Format</th>
                      <th className="p-2.5 font-medium">Sections</th>
                      <th className="p-2.5 font-medium">Questions</th>
                      <th className="p-2.5 font-medium">Status</th>
                      <th className="p-2.5 text-right font-medium">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {templates.map((template) => (
                      <tr key={template.id} className="border-t border-border align-middle">
                        <td className="p-2.5">
                          <p className="font-medium">{template.name}</p>
                          {template.description && (
                            <p className="text-xs text-muted-foreground">{template.description}</p>
                          )}
                        </td>
                        <td className="p-2.5 capitalize">{template.format}</td>
                        <td className="p-2.5 tabular-nums">{template.sections.length}</td>
                        <td className="p-2.5 tabular-nums">{template.total_questions}</td>
                        <td className="p-2.5">
                          <Badge variant={template.status === "active" ? "success" : "secondary"} className="capitalize">
                            {template.status}
                          </Badge>
                        </td>
                        <td className="p-2.5">
                          <div className="flex flex-wrap justify-end gap-1.5">
                            {onUseTemplate &&
                              template.format === "standardized" &&
                              template.status === "active" && (
                                <Button
                                  size="sm"
                                  variant={selectedTemplateId === template.id ? "secondary" : "default"}
                                  onClick={() => {
                                    onUseTemplate(template);
                                    onOpenChange(false);
                                  }}
                                >
                                  {selectedTemplateId === template.id ? "Selected" : "Use"}
                                </Button>
                              )}
                            <Button size="sm" variant="outline" onClick={() => openEdit(template)}>
                              <Pencil className="mr-1 h-3.5 w-3.5" /> Edit
                            </Button>
                            <Button size="sm" variant="outline" onClick={() => handleDuplicate(template.id)}>
                              <Copy className="mr-1 h-3.5 w-3.5" /> Duplicate
                            </Button>
                            <Button size="sm" variant="outline" onClick={() => handleStatus(template)}>
                              {template.status === "active" ? "Deactivate" : "Activate"}
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-5">
            {!editingId && (
              <div className="space-y-2">
                <Label htmlFor="template-preset">Start from preset</Label>
                <Select value={presetKey} onValueChange={setPresetKey}>
                  <SelectTrigger id="template-preset"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {presets?.map((preset) => (
                      <SelectItem key={preset.key} value={preset.key}>{preset.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="template-name">Name</Label>
                <Input id="template-name" value={config.name} onChange={(e) => patch("name", e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="template-format">Format</Label>
                <Select value={config.format} onValueChange={(value) => patch("format", value as AssessmentFormat)}>
                  <SelectTrigger id="template-format"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="standardized">Standardized (fixed 20 questions)</SelectItem>
                    <SelectItem value="adaptive">Adaptive</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="template-description">Description</Label>
              <Textarea
                id="template-description"
                rows={2}
                value={config.description}
                onChange={(e) => patch("description", e.target.value)}
              />
            </div>

            <div className="grid gap-4 sm:grid-cols-3">
              <div className="space-y-2">
                <Label htmlFor="template-time">Time limit (minutes)</Label>
                <Input
                  id="template-time"
                  type="number"
                  min={1}
                  value={Math.round(config.time_limit_sec / 60)}
                  onChange={(e) => patch("time_limit_sec", Math.max(1, Number(e.target.value) || 1) * 60)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="template-passing">Passing marks</Label>
                <Input
                  id="template-passing"
                  type="number"
                  min={0}
                  value={config.passing_marks}
                  onChange={(e) => patch("passing_marks", Number(e.target.value) || 0)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="template-negative">Negative marks</Label>
                <Input
                  id="template-negative"
                  type="number"
                  min={0}
                  step={0.5}
                  value={config.negative_marks}
                  onChange={(e) => patch("negative_marks", Number(e.target.value) || 0)}
                />
              </div>
            </div>

            {isStandardized ? (
              <div className="rounded-md border border-border bg-secondary/40 p-3 text-xs text-muted-foreground">
                Standardized templates use five four-question sections and the 6 Easy / 10 Medium / 4 Hard
                quota. Section names and counts are fixed; choose the categories each section draws from.
              </div>
            ) : (
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label>Total questions</Label>
                  <Input value={config.sections.reduce((total, section) => total + section.questions, 0)} readOnly />
                  <p className="text-xs text-muted-foreground">Calculated from the sections below.</p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="template-marks">Total marks</Label>
                  <Input
                    id="template-marks"
                    type="number"
                    min={0}
                    value={config.total_marks}
                    onChange={(e) => patch("total_marks", Number(e.target.value) || 0)}
                  />
                </div>
              </div>
            )}

            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label>Sections</Label>
                {!isStandardized && (
                  <Button type="button" size="sm" variant="outline" onClick={addSection}>
                    <Plus className="mr-1 h-3.5 w-3.5" /> Add section
                  </Button>
                )}
              </div>

              {config.sections.length === 0 ? (
                <p className="rounded-md border border-dashed border-border p-4 text-sm text-muted-foreground">
                  No sections yet. Add a section to define its name, question count and categories.
                </p>
              ) : (
                <div className="space-y-3">
                  {config.sections.map((section, index) => (
                    <div key={index} className="space-y-3 rounded-md border border-border p-3">
                      <div className="grid gap-2 sm:grid-cols-[1fr_110px_auto]">
                        <div className="space-y-1">
                          <Label className="text-xs text-muted-foreground" htmlFor={`section-name-${index}`}>
                            Section name
                          </Label>
                          <Input
                            id={`section-name-${index}`}
                            value={section.name}
                            disabled={isStandardized}
                            onChange={(e) => patchSection(index, { name: e.target.value })}
                            placeholder="e.g. Quantitative Aptitude"
                          />
                        </div>
                        <div className="space-y-1">
                          <Label className="text-xs text-muted-foreground" htmlFor={`section-questions-${index}`}>
                            Questions
                          </Label>
                          <Input
                            id={`section-questions-${index}`}
                            type="number"
                            min={1}
                            value={section.questions}
                            disabled={isStandardized}
                            onChange={(e) =>
                              patchSection(index, { questions: Math.max(1, Number(e.target.value) || 1) })
                            }
                          />
                        </div>
                        {!isStandardized && (
                          <div className="flex items-end">
                            <Button
                              type="button"
                              size="sm"
                              variant="ghost"
                              aria-label={`Remove section ${index + 1}`}
                              onClick={() => removeSection(index)}
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </div>
                        )}
                      </div>
                      <div className="space-y-1">
                        <Label className="text-xs text-muted-foreground">Categories</Label>
                        <CategoryMultiSelect
                          categories={categories}
                          value={section.category_ids}
                          onChange={(ids) => patchSection(index, { category_ids: ids })}
                          placeholder="Search or type a category"
                        />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label>Global category filter (optional)</Label>
                <CategoryMultiSelect
                  categories={categories}
                  value={config.category_ids}
                  onChange={(ids) => patch("category_ids", ids)}
                  placeholder="Search or type a category"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="template-topics">Topics</Label>
                <Input
                  id="template-topics"
                  value={topicsText}
                  onChange={(e) => setTopicsText(e.target.value)}
                  placeholder="Comma-separated"
                />
                <Label htmlFor="template-skills">Skills</Label>
                <Input
                  id="template-skills"
                  value={skillsText}
                  onChange={(e) => setSkillsText(e.target.value)}
                  placeholder="Comma-separated"
                />
              </div>
            </div>

            <div className="space-y-3">
              <Label>Allowed question types</Label>
              <div className="flex flex-wrap gap-2">
                {QUESTION_TYPES.map((type) => {
                  const active = config.question_types.includes(type);
                  return (
                    <button
                      key={type}
                      type="button"
                      onClick={() =>
                        patch(
                          "question_types",
                          active
                            ? config.question_types.filter((item) => item !== type)
                            : [...config.question_types, type]
                        )
                      }
                      className={`rounded-full border px-3 py-1 text-xs uppercase transition-colors ${
                        active ? "border-primary bg-primary text-primary-foreground" : "border-border hover:bg-secondary"
                      }`}
                    >
                      {type.replace(/_/g, " ")}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="space-y-2">
              <Label>Difficulty distribution</Label>
              <div className="grid grid-cols-3 gap-3">
                {DIFFICULTIES.map((difficulty) => (
                  <div key={difficulty} className="space-y-1">
                    <Label className="text-xs capitalize text-muted-foreground" htmlFor={`difficulty-${difficulty}`}>
                      {difficulty}
                    </Label>
                    <Input
                      id={`difficulty-${difficulty}`}
                      type="number"
                      min={0}
                      value={config.difficulty_distribution[difficulty] ?? 0}
                      disabled={isStandardized}
                      onChange={(e) =>
                        patch("difficulty_distribution", {
                          ...config.difficulty_distribution,
                          [difficulty]: Math.max(0, Number(e.target.value) || 0),
                        })
                      }
                    />
                  </div>
                ))}
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="template-instructions">Instructions</Label>
              <Textarea
                id="template-instructions"
                rows={2}
                value={config.instructions}
                onChange={(e) => patch("instructions", e.target.value)}
              />
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="template-status">Status</Label>
                <Select value={config.status} onValueChange={(value) => patch("status", value as TemplateStatus)}>
                  <SelectTrigger id="template-status"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="active">Active</SelectItem>
                    <SelectItem value="inactive">Inactive</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-wrap items-end gap-4 text-sm">
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={config.allow_retake}
                    onChange={(e) => patch("allow_retake", e.target.checked)}
                  />{" "}
                  Allow retake
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={config.randomize_options}
                    onChange={(e) => patch("randomize_options", e.target.checked)}
                  />{" "}
                  Randomize options
                </label>
              </div>
            </div>
          </div>
        )}

        <DialogFooter>
          {view === "edit" ? (
            <>
              <Button variant="secondary" onClick={() => setView("list")}>Back</Button>
              <Button onClick={handleSave} disabled={isSaving || !config.name.trim()}>
                {isSaving ? "Saving…" : editingId ? "Save changes" : "Create template"}
              </Button>
            </>
          ) : (
            <Button variant="secondary" onClick={() => onOpenChange(false)}>Close</Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
