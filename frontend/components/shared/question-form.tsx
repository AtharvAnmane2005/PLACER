"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Plus, Trash2 } from "lucide-react";
import { useEffect } from "react";
import { useFieldArray, useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type { CategoryResponse, QuestionAdminResponse, QuestionCreateRequest } from "@/types/question";

const testCaseSchema = z.object({
  name: z.string().optional(),
  input: z.string(),
  expected_output: z.string(),
  is_hidden: z.boolean(),
});

const questionSchema = z
  .object({
    category_id: z.string().min(1, "Select a category."),
    difficulty: z.enum(["easy", "medium", "hard"]),
    type: z.enum(["mcq", "multiple_select", "true_false", "coding", "descriptive"]),
    text: z.string().min(1, "Question text is required."),
    options: z.string().optional(),
    correct_answer: z.string().optional(),
    topic: z.string().optional(),
    skill: z.string().optional(),
    explanation: z.string().optional(),
    marks: z.string().optional(),
    status: z.enum(["active", "inactive"]).optional(),
    language: z.enum(["python", "javascript"]).optional(),
    starter_code: z.string().optional(),
    test_cases: z.array(testCaseSchema).optional(),
    skill_tags: z.string().optional(),
    company_tags: z.string().optional(),
  })
  .superRefine((values, ctx) => {
    const options = splitLines(values.options);
    if (values.type === "mcq" || values.type === "multiple_select") {
      if (options.length < 2) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["options"],
          message: "This question needs at least 2 options (one per line).",
        });
      }
      const answers = values.type === "multiple_select" ? splitCsv(values.correct_answer) : splitLines(values.correct_answer);
      if (answers.length === 0) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["correct_answer"],
          message: values.type === "multiple_select" ? "Select at least one correct answer." : "Requires a correct answer.",
        });
      } else {
        const invalid = answers.filter((answer) => !options.includes(answer));
        if (invalid.length > 0) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            path: ["correct_answer"],
            message: `Correct answer${invalid.length > 1 ? "s" : ""} must exactly match option text.`,
          });
        }
      }
    }
    if (values.type === "true_false") {
      const answer = values.correct_answer?.trim().toLowerCase();
      if (answer !== "true" && answer !== "false") {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["correct_answer"],
          message: "True/False questions require 'True' or 'False' as the correct answer.",
        });
      }
    }
    if (values.type === "coding") {
      if (!values.language) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["language"], message: "Select a language." });
      }
      const cases = values.test_cases ?? [];
      if (cases.length === 0) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["test_cases"],
          message: "Coding questions need at least one test case.",
        });
      } else if (cases.every((tc) => !tc.input.trim() && !tc.expected_output.trim())) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["test_cases"],
          message: "Fill in at least one test case (input and/or expected output).",
        });
      }
    }
  });

type QuestionFormValues = z.infer<typeof questionSchema>;

function splitLines(value: string | undefined): string[] {
  if (!value) return [];
  return value
    .split("\n")
    .map((v) => v.trim())
    .filter(Boolean);
}

function splitCsv(value: string | undefined): string[] {
  if (!value) return [];
  return value
    .split(",")
    .map((v) => v.trim())
    .filter(Boolean);
}

const emptyTestCase = { name: "", input: "", expected_output: "", is_hidden: false };

export function QuestionForm({
  categories,
  initialValues,
  onSubmit,
  submitLabel = "Save",
  isSubmitting = false,
}: {
  categories: CategoryResponse[];
  initialValues?: QuestionAdminResponse;
  onSubmit: (payload: QuestionCreateRequest) => Promise<void> | void;
  submitLabel?: string;
  isSubmitting?: boolean;
}) {
  const {
    register,
    handleSubmit,
    watch,
    setValue,
    reset,
    control,
    formState: { errors },
  } = useForm<QuestionFormValues>({
    resolver: zodResolver(questionSchema),
    defaultValues: {
      type: "mcq",
      difficulty: "medium",
      language: "python",
      starter_code: "",
      test_cases: [{ ...emptyTestCase }],
      status: "active",
    },
  });

  const { fields, append, remove } = useFieldArray({ control, name: "test_cases" });

  useEffect(() => {
    if (!initialValues) return;
    reset({
      category_id: initialValues.category_id,
      difficulty: initialValues.difficulty,
      type: initialValues.type,
      text: initialValues.text,
      options: initialValues.options.join("\n"),
      correct_answer: initialValues.correct_answer ?? "",
      language: initialValues.language ?? "python",
      starter_code: initialValues.starter_code ?? "",
      test_cases:
        initialValues.test_cases.length > 0
          ? initialValues.test_cases.map((tc) => ({
              name: tc.name ?? "",
              input: tc.input,
              expected_output: tc.expected_output,
              is_hidden: tc.is_hidden,
            }))
          : [{ ...emptyTestCase }],
      skill_tags: initialValues.skill_tags.join(", "),
      company_tags: initialValues.company_tags.join(", "),
      topic: initialValues.topic ?? "",
      skill: initialValues.skill ?? "",
      explanation: initialValues.explanation ?? "",
      marks: String(initialValues.marks),
      status: initialValues.status,
    });
  }, [initialValues, reset]);

  const questionType = watch("type");
  const testCasesError = errors.test_cases as { message?: string } | undefined;

  const submit = handleSubmit(async (values) => {
    const isCoding = values.type === "coding";
    let correctAnswer: string | undefined;
    if (values.type === "mcq") {
      correctAnswer = values.correct_answer?.trim() || undefined;
    } else if (values.type === "multiple_select") {
      correctAnswer = splitCsv(values.correct_answer).join("|") || undefined;
    } else if (values.type === "true_false") {
      const answer = values.correct_answer?.trim().toLowerCase();
      correctAnswer = answer === "true" || answer === "false" ? (answer === "true" ? "True" : "False") : undefined;
    } else if (isCoding) {
      correctAnswer = values.correct_answer?.trim() || undefined;
    }

    await onSubmit({
      category_id: values.category_id,
      difficulty: values.difficulty,
      type: values.type,
      text: values.text,
      options:
        values.type === "true_false"
          ? ["True", "False"]
          : values.type === "mcq" || values.type === "multiple_select"
            ? splitLines(values.options)
            : [],
      correct_answer: correctAnswer,
      language: isCoding ? values.language : undefined,
      starter_code: isCoding ? values.starter_code?.trim() || undefined : undefined,
      test_cases: isCoding
        ? (values.test_cases ?? []).map((tc) => ({
            name: tc.name?.trim() || undefined,
            input: tc.input ?? "",
            expected_output: tc.expected_output ?? "",
            is_hidden: tc.is_hidden,
          }))
        : [],
      skill_tags: splitCsv(values.skill_tags),
      company_tags: splitCsv(values.company_tags),
      topic: values.topic?.trim() || null,
      skill: values.skill?.trim() || null,
      explanation: values.explanation?.trim() || null,
      marks: values.marks ? Number(values.marks) : null,
      status: values.status,
    });
  });

  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="category_id">Category</Label>
          <Select value={watch("category_id")} onValueChange={(v) => setValue("category_id", v, { shouldValidate: true })}>
            <SelectTrigger id="category_id">
              <SelectValue placeholder="Select a category" />
            </SelectTrigger>
            <SelectContent>
              {categories.map((c) => (
                <SelectItem key={c.id} value={c.id}>
                  {c.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {errors.category_id && <p className="text-sm text-destructive">{errors.category_id.message}</p>}
        </div>
        <div className="space-y-2">
          <Label htmlFor="difficulty">Difficulty</Label>
          <Select value={watch("difficulty")} onValueChange={(v) => setValue("difficulty", v as QuestionFormValues["difficulty"])}>
            <SelectTrigger id="difficulty">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="easy">Easy</SelectItem>
              <SelectItem value="medium">Medium</SelectItem>
              <SelectItem value="hard">Hard</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="type">Question type</Label>
        <Select value={watch("type")} onValueChange={(v) => setValue("type", v as QuestionFormValues["type"])}>
          <SelectTrigger id="type">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="mcq">MCQ (single answer)</SelectItem>
            <SelectItem value="multiple_select">Multiple select</SelectItem>
            <SelectItem value="true_false">True / False</SelectItem>
            <SelectItem value="coding">Coding</SelectItem>
            <SelectItem value="descriptive">Descriptive</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-2">
        <Label htmlFor="text">Question text</Label>
        <Textarea id="text" rows={3} {...register("text")} />
        {errors.text && <p className="text-sm text-destructive">{errors.text.message}</p>}
      </div>

      {questionType === "coding" && (
        <>
          <div className="space-y-2">
            <Label htmlFor="language">Language</Label>
            <Select
              value={watch("language") ?? "python"}
              onValueChange={(v) => setValue("language", v as QuestionFormValues["language"], { shouldValidate: true })}
            >
              <SelectTrigger id="language">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="python">Python 3</SelectItem>
                <SelectItem value="javascript">JavaScript (Node.js)</SelectItem>
              </SelectContent>
            </Select>
            {errors.language && <p className="text-sm text-destructive">{errors.language.message}</p>}
          </div>

          <div className="space-y-2">
            <Label htmlFor="starter_code">Starter code (optional)</Label>
            <Textarea
              id="starter_code"
              rows={6}
              spellCheck={false}
              className="font-mono text-xs"
              placeholder={"# Students start from this code and fill in the missing parts.\n"}
              {...register("starter_code")}
            />
            <p className="text-xs text-muted-foreground">
              Shown pre-filled in the student&apos;s editor. Include any{" "}
              <span className="font-mono">stdin</span>/<span className="font-mono">stdout</span>{" "}
              boilerplate here if students only need to fill in a function body. Leave blank for a
              full-program question.
            </p>
          </div>

          <div className="space-y-3 rounded-md border border-border p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <Label>Test cases</Label>
                <p className="text-xs text-muted-foreground">
                  The program reads <span className="font-mono">stdin</span> and its{" "}
                  <span className="font-mono">stdout</span> is compared to the expected output. All test
                  cases must pass for the question to be marked correct.
                </p>
              </div>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => append({ ...emptyTestCase })}
              >
                <Plus className="mr-1 h-3.5 w-3.5" /> Add test case
              </Button>
            </div>

            {fields.map((field, index) => (
              <div key={field.id} className="space-y-2 rounded-md bg-secondary/40 p-3">
                <div className="flex items-center gap-2">
                  <Input
                    placeholder={`Test case ${index + 1} name (optional)`}
                    {...register(`test_cases.${index}.name`)}
                  />
                  <label className="flex shrink-0 items-center gap-1.5 text-xs">
                    <input type="checkbox" {...register(`test_cases.${index}.is_hidden`)} />
                    Hidden
                  </label>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => remove(index)}
                    disabled={fields.length <= 1}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  <div className="space-y-1">
                    <Label className="text-xs">Input (stdin)</Label>
                    <Textarea
                      rows={3}
                      spellCheck={false}
                      className="font-mono text-xs"
                      {...register(`test_cases.${index}.input`)}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Expected output (stdout)</Label>
                    <Textarea
                      rows={3}
                      spellCheck={false}
                      className="font-mono text-xs"
                      {...register(`test_cases.${index}.expected_output`)}
                    />
                  </div>
                </div>
              </div>
            ))}
            {testCasesError && (
              <p className="text-sm text-destructive">
                {testCasesError.message ?? "Add at least one test case."}
              </p>
            )}
          </div>
        </>
      )}

      {(questionType === "mcq" || questionType === "multiple_select") && (
        <div className="space-y-2">
          <Label htmlFor="options">Options (one per line)</Label>
          <Textarea id="options" rows={4} {...register("options")} />
          {errors.options && <p className="text-sm text-destructive">{errors.options.message}</p>}
        </div>
      )}

      {(questionType === "mcq" || questionType === "multiple_select" || questionType === "true_false") && (
        <div className="space-y-2">
          <Label htmlFor="correct_answer">
            {questionType === "multiple_select"
              ? "Correct answers (comma-separated, matching option text)"
              : questionType === "true_false"
                ? "Correct answer (True or False)"
                : "Correct answer (must match an option exactly)"}
          </Label>
          <Input
            id="correct_answer"
            placeholder={questionType === "multiple_select" ? "Option A, Option C" : undefined}
            {...register("correct_answer")}
          />
          {errors.correct_answer && <p className="text-sm text-destructive">{errors.correct_answer.message}</p>}
        </div>
      )}

      {questionType === "coding" && (
        <div className="space-y-2">
          <Label htmlFor="legacy_correct_answer">Legacy expected output (optional, for questions without test cases)</Label>
          <Input id="legacy_correct_answer" {...register("correct_answer")} />
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="topic">Topic</Label>
          <Input id="topic" placeholder="e.g. Trees" {...register("topic")} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="skill">Primary skill</Label>
          <Input id="skill" placeholder="e.g. Algorithms" {...register("skill")} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="marks">Marks (leave blank for difficulty default)</Label>
          <Input id="marks" type="number" min={0} {...register("marks")} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="status">Status</Label>
          <Select
            value={watch("status") ?? "active"}
            onValueChange={(v) => setValue("status", v as QuestionFormValues["status"])}
          >
            <SelectTrigger id="status">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="active">Active</SelectItem>
              <SelectItem value="inactive">Inactive</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
      <div className="space-y-2">
        <Label htmlFor="explanation">Explanation (revealed only in results)</Label>
        <Textarea id="explanation" rows={2} {...register("explanation")} />
      </div>

      <div className="space-y-2">
        <Label htmlFor="skill_tags">Skill tags (comma-separated)</Label>
        <Input id="skill_tags" placeholder="python, algorithms" {...register("skill_tags")} />
      </div>
      <div className="space-y-2">
        <Label htmlFor="company_tags">Company tags (comma-separated, optional)</Label>
        <Input id="company_tags" {...register("company_tags")} />
      </div>

      <Button type="submit" disabled={isSubmitting}>
        {isSubmitting ? "Saving…" : submitLabel}
      </Button>
    </form>
  );
}
