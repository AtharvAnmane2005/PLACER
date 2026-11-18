"use client";

import Link from "next/link";
import {
  Database,
  Download,
  FileSpreadsheet,
  FileWarning,
  ListChecks,
  PlusCircle,
  Search,
  Tags,
  Upload,
} from "lucide-react";
import { useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { StatCard } from "@/components/shared/stat-card";
import { EmptyState } from "@/components/shared/empty-state";
import { QuestionForm } from "@/components/shared/question-form";
import { useToast } from "@/hooks/use-toast";
import {
  downloadImportErrorReport,
  downloadQuestionTemplate,
  downloadQuestionWorkbook,
  useCategories,
  useCreateCategory,
  usePreviewQuestionImport,
  useCommitQuestionImport,
  useQuestionStats,
  useQuestions,
  useSetQuestionStatus,
  useUpdateQuestion,
} from "@/hooks/use-admin-questions";
import type { ImportPreviewResponse, QuestionAdminResponse, QuestionCreateRequest, QuestionFilters } from "@/types/question";

function errorDetail(err: any, fallback: string): string {
  const detail = err?.response?.data?.detail;
  if (typeof detail === "string" && detail) return detail;
  if (detail && typeof detail === "object") {
    if (typeof detail.message === "string") return detail.message;
    if (Array.isArray(detail.deficits) && detail.deficits.length > 0) return detail.deficits.join("; ");
  }
  return fallback;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function QuestionsTab() {
  const [filters, setFilters] = useState<QuestionFilters>({});
  const [searchInput, setSearchInput] = useState("");
  const [editingQuestion, setEditingQuestion] = useState<QuestionAdminResponse | null>(null);

  const [importOpen, setImportOpen] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreviewResponse | null>(null);
  const [excludedRows, setExcludedRows] = useState<Set<number>>(new Set());
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { data: categories } = useCategories();
  const { data: stats, isLoading: statsLoading } = useQuestionStats();
  const { data: questions, isLoading } = useQuestions(filters);
  const updateQuestion = useUpdateQuestion();
  const setStatus = useSetQuestionStatus();
  const previewImport = usePreviewQuestionImport();
  const commitImport = useCommitQuestionImport();
  const { toast } = useToast();

  const categoryName = (id: string) => categories?.find((c) => c.id === id)?.name ?? id;

  const updateFilter = (key: keyof QuestionFilters, value: string) => {
    setFilters((current) => ({ ...current, [key]: value || undefined }));
  };

  const handleUpdate = async (payload: QuestionCreateRequest) => {
    if (!editingQuestion) return;
    try {
      await updateQuestion.mutateAsync({ id: editingQuestion.id, payload });
      toast({ title: "Question updated" });
      setEditingQuestion(null);
    } catch (err) {
      toast({ title: "Update failed", description: errorDetail(err, "Couldn't save changes."), variant: "destructive" });
    }
  };

  const handleToggleStatus = async (question: QuestionAdminResponse) => {
    const next = question.status === "active" ? "inactive" : "active";
    try {
      await setStatus.mutateAsync({ id: question.id, status: next });
      toast({ title: `Question marked ${next}` });
    } catch (err) {
      toast({ title: "Status update failed", description: errorDetail(err, ""), variant: "destructive" });
    }
  };

  const resetImport = () => {
    setImportFile(null);
    setPreview(null);
    setExcludedRows(new Set());
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handlePreview = async () => {
    if (!importFile) {
      toast({ title: "Choose a file first", description: "Select an .xlsx or .csv question file." });
      return;
    }
    const name = importFile.name.toLowerCase();
    if (!name.endsWith(".xlsx") && !name.endsWith(".csv")) {
      toast({
        title: "Unsupported file type",
        description: "Only .xlsx and .csv files are accepted.",
        variant: "destructive",
      });
      return;
    }
    try {
      const result = await previewImport.mutateAsync(importFile);
      setPreview(result);
      setExcludedRows(new Set());
    } catch (err) {
      toast({ title: "Preview failed", description: errorDetail(err, "Couldn't read that file."), variant: "destructive" });
    }
  };

  const selectedImportQuestions = (preview?.rows ?? [])
    .filter((row) => row.question && !excludedRows.has(row.row))
    .map((row) => row.question as QuestionCreateRequest);

  const handleCommit = async () => {
    if (!preview || selectedImportQuestions.length === 0) {
      toast({ title: "No valid rows selected", description: "Fix or exclude the invalid rows before importing." });
      return;
    }
    try {
      const result = await commitImport.mutateAsync(selectedImportQuestions);
      toast({
        title: "Import complete",
        description: `${result.imported} imported · ${result.duplicates} duplicate · ${result.invalid + result.failed} failed.`,
      });
      resetImport();
      setImportOpen(false);
    } catch (err) {
      toast({ title: "Import failed", description: errorDetail(err, "Couldn't import the selected rows."), variant: "destructive" });
    }
  };

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-4">
        <StatCard
          label="Total questions"
          value={statsLoading ? <Skeleton className="h-7 w-10" /> : (stats?.total ?? 0)}
          icon={Database}
        />
        <StatCard
          label="Active"
          value={statsLoading ? <Skeleton className="h-7 w-10" /> : (stats?.active ?? 0)}
          icon={ListChecks}
        />
        <StatCard
          label="Inactive"
          value={statsLoading ? <Skeleton className="h-7 w-10" /> : (stats?.inactive ?? 0)}
          icon={FileWarning}
        />
        <StatCard label="Categories" value={categories?.length ?? 0} icon={Tags} />
      </div>

      {stats && (
        <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
          {Object.entries(stats.by_difficulty).map(([name, count]) => (
            <Badge key={`difficulty-${name}`} variant="outline" className="capitalize">
              {name}: {count}
            </Badge>
          ))}
          {Object.entries(stats.by_type).map(([name, count]) => (
            <Badge key={`type-${name}`} variant="secondary" className="uppercase">
              {name}: {count}
            </Badge>
          ))}
        </div>
      )}

      <Card>
        <CardContent className="space-y-3 p-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <div className="relative">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                className="pl-8"
                placeholder="Search question text"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && updateFilter("search", searchInput)}
              />
            </div>
            <Select value={filters.category_id || "all"} onValueChange={(v) => updateFilter("category_id", v === "all" ? "" : v)}>
              <SelectTrigger>
                <SelectValue placeholder="All categories" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All categories</SelectItem>
                {categories?.map((c) => (
                  <SelectItem key={c.id} value={c.id}>
                    {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={filters.difficulty || "all"} onValueChange={(v) => updateFilter("difficulty", v === "all" ? "" : v)}>
              <SelectTrigger>
                <SelectValue placeholder="All difficulties" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All difficulties</SelectItem>
                <SelectItem value="easy">Easy</SelectItem>
                <SelectItem value="medium">Medium</SelectItem>
                <SelectItem value="hard">Hard</SelectItem>
              </SelectContent>
            </Select>
            <Select value={filters.question_type || "all"} onValueChange={(v) => updateFilter("question_type", v === "all" ? "" : v)}>
              <SelectTrigger>
                <SelectValue placeholder="All types" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All types</SelectItem>
                <SelectItem value="mcq">MCQ</SelectItem>
                <SelectItem value="multiple_select">Multiple select</SelectItem>
                <SelectItem value="true_false">True / False</SelectItem>
                <SelectItem value="coding">Coding</SelectItem>
                <SelectItem value="descriptive">Descriptive</SelectItem>
              </SelectContent>
            </Select>
            <Select value={filters.status || "all"} onValueChange={(v) => updateFilter("status", v === "all" ? "" : v)}>
              <SelectTrigger>
                <SelectValue placeholder="All statuses" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                <SelectItem value="active">Active</SelectItem>
                <SelectItem value="inactive">Inactive</SelectItem>
              </SelectContent>
            </Select>
            <div className="flex gap-2">
              <Input
                placeholder="Topic"
                value={filters.topic ?? ""}
                onChange={(e) => updateFilter("topic", e.target.value)}
              />
              <Input
                placeholder="Skill"
                value={filters.skill ?? ""}
                onChange={(e) => updateFilter("skill", e.target.value)}
              />
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={() => updateFilter("search", searchInput)}>
              <Search className="mr-1.5 h-3.5 w-3.5" /> Search
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setFilters({});
                setSearchInput("");
              }}
            >
              Clear filters
            </Button>
          </div>
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          {questions?.length ?? 0} question{questions?.length === 1 ? "" : "s"} shown
        </p>
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() =>
              downloadQuestionTemplate().catch(() =>
                toast({ title: "Download failed", description: "Couldn't download the template.", variant: "destructive" })
              )
            }
          >
            <Download className="mr-1.5 h-3.5 w-3.5" /> Download template
          </Button>
          <Button size="sm" variant="outline" onClick={() => setImportOpen(true)}>
            <Upload className="mr-1.5 h-3.5 w-3.5" /> Import completed file
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() =>
              downloadQuestionWorkbook(filters).catch(() =>
                toast({ title: "Export failed", description: "Couldn't export the question bank.", variant: "destructive" })
              )
            }
          >
            <FileSpreadsheet className="mr-1.5 h-3.5 w-3.5" /> Export question bank
          </Button>
          <Button asChild size="sm">
            <Link href="/admin/dashboard/questions/new">
              <PlusCircle className="mr-1.5 h-3.5 w-3.5" /> New question
            </Link>
          </Button>
        </div>
      </div>

      {isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : !questions || questions.length === 0 ? (
        <EmptyState
          icon={ListChecks}
          title="No questions found"
          description="Create one, import a completed template, or adjust your filters."
        />
      ) : (
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="w-full text-left text-sm">
            <thead className="bg-secondary/60 text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="p-3 font-medium">Question</th>
                <th className="p-3 font-medium">Category</th>
                <th className="p-3 font-medium">Type</th>
                <th className="p-3 font-medium">Difficulty</th>
                <th className="p-3 font-medium">Marks</th>
                <th className="p-3 font-medium">Status</th>
                <th className="p-3 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {questions.map((q) => (
                <tr key={q.id} className="border-t border-border align-top">
                  <td className="max-w-md p-3">
                    <p className="font-medium leading-snug">{q.text}</p>
                    <div className="mt-1 flex flex-wrap gap-x-2 gap-y-1 text-xs text-muted-foreground">
                      {q.topic && <span>{q.topic}</span>}
                      {q.skill && <span>· {q.skill}</span>}
                      {q.type === "coding" && q.language && <span>· {q.language}</span>}
                      {q.type === "coding" && <span>· {q.test_cases.length} test case(s)</span>}
                    </div>
                  </td>
                  <td className="p-3">{categoryName(q.category_id)}</td>
                  <td className="p-3">
                    <Badge variant="secondary" className="uppercase">{q.type}</Badge>
                  </td>
                  <td className="p-3 capitalize">{q.difficulty}</td>
                  <td className="p-3 tabular-nums">{q.marks}</td>
                  <td className="p-3">
                    <Badge variant={q.status === "active" ? "success" : "secondary"} className="capitalize">
                      {q.status}
                    </Badge>
                  </td>
                  <td className="p-3">
                    <div className="flex justify-end gap-1.5">
                      <Button size="sm" variant="outline" onClick={() => handleToggleStatus(q)} disabled={setStatus.isPending}>
                        {q.status === "active" ? "Deactivate" : "Activate"}
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => setEditingQuestion(q)}>
                        Edit
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Dialog
        open={importOpen}
        onOpenChange={(open) => {
          setImportOpen(open);
          if (!open) resetImport();
        }}
      >
        <DialogContent className="max-h-[88vh] max-w-4xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Import completed template</DialogTitle>
            <DialogDescription>
              Upload the filled .xlsx or .csv file. Every row is validated and previewed; only rows you confirm are
              inserted. Existing questions are never overwritten.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-3 rounded-md border border-border p-3">
              <input
                ref={fileInputRef}
                type="file"
                accept=".xlsx,.csv"
                className="sr-only"
                onChange={(e) => {
                  setImportFile(e.target.files?.[0] ?? null);
                  setPreview(null);
                  setExcludedRows(new Set());
                }}
              />
              <Button size="sm" variant="outline" onClick={() => fileInputRef.current?.click()}>
                <Upload className="mr-1.5 h-3.5 w-3.5" /> Choose file
              </Button>
              <div className="min-w-0 flex-1 text-sm">
                {importFile ? (
                  <span className="block truncate">
                    {importFile.name} <span className="text-muted-foreground">({formatBytes(importFile.size)})</span>
                  </span>
                ) : (
                  <span className="text-muted-foreground">No file selected</span>
                )}
              </div>
              <Button size="sm" onClick={handlePreview} disabled={!importFile || previewImport.isPending}>
                {previewImport.isPending ? "Validating…" : "Preview"}
              </Button>
              <Button
                size="sm"
                variant="secondary"
                onClick={() =>
                  downloadQuestionTemplate().catch(() =>
                    toast({ title: "Download failed", variant: "destructive" })
                  )
                }
              >
                <Download className="mr-1.5 h-3.5 w-3.5" /> Blank template
              </Button>
            </div>

            {preview && (
              <>
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <Badge variant="outline">{preview.total_rows} rows</Badge>
                  <Badge variant="success">{preview.valid_rows} valid</Badge>
                  <Badge variant="destructive">{preview.invalid_rows} invalid</Badge>
                  <Badge variant="warning">{preview.duplicate_rows} duplicates in file</Badge>
                  <Button
                    size="sm"
                    variant="link"
                    onClick={() =>
                      downloadImportErrorReport(preview).catch(() =>
                        toast({ title: "Couldn't download error report", variant: "destructive" })
                      )
                    }
                  >
                    <FileWarning className="mr-1 h-3.5 w-3.5" /> Download error report
                  </Button>
                </div>

                <div className="max-h-[45vh] overflow-auto rounded-md border border-border">
                  <table className="w-full text-left text-xs">
                    <thead className="sticky top-0 bg-secondary/80">
                      <tr>
                        <th className="p-2">Include</th>
                        <th className="p-2">Row</th>
                        <th className="p-2">Question</th>
                        <th className="p-2">Category</th>
                        <th className="p-2">Difficulty</th>
                        <th className="p-2">Type</th>
                        <th className="p-2">Errors</th>
                      </tr>
                    </thead>
                    <tbody>
                      {preview.rows.map((row) => (
                        <tr key={row.row} className="border-t border-border align-top">
                          <td className="p-2">
                            {row.question ? (
                              <input
                                type="checkbox"
                                checked={!excludedRows.has(row.row)}
                                onChange={(e) =>
                                  setExcludedRows((current) => {
                                    const next = new Set(current);
                                    if (e.target.checked) next.delete(row.row);
                                    else next.add(row.row);
                                    return next;
                                  })
                                }
                              />
                            ) : (
                              "—"
                            )}
                          </td>
                          <td className="p-2">{row.row}</td>
                          <td className="max-w-xs p-2">{row.question?.text ?? row.raw_text ?? ""}</td>
                          <td className="p-2">{row.question ? categoryName(row.question.category_id) : "—"}</td>
                          <td className="p-2 capitalize">{row.question?.difficulty ?? "—"}</td>
                          <td className="p-2 uppercase">{row.question?.type ?? "—"}</td>
                          <td className="p-2 text-destructive">
                            {row.errors.length === 0
                              ? "—"
                              : row.errors.map((error) => `${error.field}: ${error.message}`).join("; ")}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {preview.invalid_rows > 0 && (
                  <p className="text-xs text-muted-foreground">
                    Invalid rows and duplicates are never imported. Fix them in the file and preview again, or
                    leave them unchecked.
                  </p>
                )}
              </>
            )}
          </div>

          <DialogFooter>
            <Button variant="secondary" onClick={resetImport}>Clear</Button>
            <Button
              onClick={handleCommit}
              disabled={!preview || selectedImportQuestions.length === 0 || commitImport.isPending}
            >
              {commitImport.isPending ? "Importing…" : `Confirm import (${selectedImportQuestions.length})`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(editingQuestion)} onOpenChange={(open) => !open && setEditingQuestion(null)}>
        <DialogContent className="max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Edit question</DialogTitle>
          </DialogHeader>
          {editingQuestion && (
            <QuestionForm
              categories={categories ?? []}
              initialValues={editingQuestion}
              onSubmit={handleUpdate}
              submitLabel="Save changes"
              isSubmitting={updateQuestion.isPending}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function CategoriesTab() {
  const { data: categories, isLoading } = useCategories();
  const createCategory = useCreateCategory();
  const { toast } = useToast();
  const [name, setName] = useState("");

  const handleCreate = async () => {
    if (!name.trim()) return;
    try {
      await createCategory.mutateAsync({ name: name.trim() });
      setName("");
      toast({ title: "Category created" });
    } catch (err) {
      toast({ title: "Creation failed", description: errorDetail(err, "Couldn't create the category."), variant: "destructive" });
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Add category</CardTitle>
        </CardHeader>
        <CardContent className="flex gap-2">
          <div className="flex-1 space-y-2">
            <Label htmlFor="category-name" className="sr-only">Category name</Label>
            <Input
              id="category-name"
              placeholder="e.g. Data Structures & Algorithms"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreate()}
            />
          </div>
          <Button onClick={handleCreate} disabled={createCategory.isPending || !name.trim()}>Add</Button>
        </CardContent>
      </Card>

      {isLoading ? (
        <Skeleton className="h-32 w-full" />
      ) : !categories || categories.length === 0 ? (
        <EmptyState icon={Tags} title="No categories yet" description="Add one above to start building the question bank." />
      ) : (
        <div className="flex flex-wrap gap-2">
          {categories.map((c) => (
            <Badge key={c.id} variant="outline" className="px-3 py-1.5 text-sm">{c.name}</Badge>
          ))}
        </div>
      )}
    </div>
  );
}

export default function QuestionBankPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold">Question bank</h1>
        <p className="text-sm text-muted-foreground">
          Manage questions for adaptive and standardized assessments. Download the blank template to add questions in
          bulk, then import the completed file.
        </p>
      </div>

      <QuestionsTabs />
    </div>
  );
}

function QuestionsTabs() {
  const [tab, setTab] = useState<"questions" | "categories">("questions");
  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <Button size="sm" variant={tab === "questions" ? "default" : "outline"} onClick={() => setTab("questions")}>
          Questions
        </Button>
        <Button size="sm" variant={tab === "categories" ? "default" : "outline"} onClick={() => setTab("categories")}>
          Categories
        </Button>
      </div>
      {tab === "questions" ? <QuestionsTab /> : <CategoriesTab />}
    </div>
  );
}
