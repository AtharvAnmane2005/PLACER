"use client";

import { CheckCircle2, ClipboardCheck, Clock, GraduationCap, Loader2 } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { EmptyState } from "@/components/shared/empty-state";
import { useToast } from "@/hooks/use-toast";
import {
  useAttemptReview,
  useGradeDescriptive,
  usePendingReviews,
} from "@/hooks/use-assessments";
import type { AttemptReviewAnswer } from "@/types/assessment";

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function GradeAnswerForm({
  attemptId,
  answer,
}: {
  attemptId: string;
  answer: AttemptReviewAnswer;
}) {
  const { toast } = useToast();
  const gradeAnswer = useGradeDescriptive();
  const [marks, setMarks] = useState(String(answer.marks_awarded));
  const [feedback, setFeedback] = useState(answer.feedback ?? "");

  const parsed = Number(marks);
  const invalid = Number.isNaN(parsed) || parsed < 0 || parsed > answer.max_marks;

  const submit = async () => {
    if (invalid) {
      toast({
        variant: "destructive",
        title: "Invalid marks",
        description: `Enter a value between 0 and ${answer.max_marks}.`,
      });
      return;
    }
    try {
      await gradeAnswer.mutateAsync({
        attemptId,
        questionId: answer.question_id,
        marksAwarded: parsed,
        feedback: feedback.trim() || undefined,
      });
      toast({
        title: answer.graded_at ? "Grade updated" : "Answer graded",
        description: `${parsed}/${answer.max_marks} marks saved.`,
      });
    } catch {
      toast({
        variant: "destructive",
        title: "Could not save grade",
        description: "Please try again.",
      });
    }
  };

  return (
    <div className="rounded-md border border-border p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={answer.graded_at ? "success" : "warning"}>
          {answer.graded_at ? "Graded" : "Pending review"}
        </Badge>
        <span className="text-xs text-muted-foreground">
          {answer.marks_awarded}/{answer.max_marks} marks
        </span>
        {answer.graded_at && (
          <span className="text-xs text-muted-foreground">· {formatDate(answer.graded_at)}</span>
        )}
      </div>

      <p className="mt-3 whitespace-pre-wrap text-sm font-medium">{answer.question_text}</p>

      <div className="mt-3">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Student response
        </p>
        <pre className="mt-1 max-h-56 overflow-auto whitespace-pre-wrap rounded bg-secondary/50 p-2 font-mono text-xs">
          {answer.response || "(no response)"}
        </pre>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-[140px_1fr]">
        <div className="space-y-1.5">
          <Label htmlFor={`marks-${answer.question_id}`}>Marks (0–{answer.max_marks})</Label>
          <Input
            id={`marks-${answer.question_id}`}
            type="number"
            min={0}
            max={answer.max_marks}
            step={1}
            value={marks}
            onChange={(event) => setMarks(event.target.value)}
            aria-invalid={invalid}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={`feedback-${answer.question_id}`}>Feedback (optional)</Label>
          <Textarea
            id={`feedback-${answer.question_id}`}
            rows={3}
            placeholder="Explain the score so the student can improve."
            value={feedback}
            onChange={(event) => setFeedback(event.target.value)}
          />
        </div>
      </div>

      <div className="mt-3 flex justify-end">
        <Button size="sm" onClick={submit} disabled={invalid || gradeAnswer.isPending}>
          {gradeAnswer.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {answer.graded_at ? "Update grade" : "Save grade"}
        </Button>
      </div>
    </div>
  );
}

export default function TpoReviewPage() {
  const { data: pending, isLoading } = usePendingReviews();
  const [selectedAttemptId, setSelectedAttemptId] = useState<string | null>(null);
  const { data: review, isLoading: reviewLoading } = useAttemptReview(selectedAttemptId);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold">Descriptive review</h1>
        <p className="text-sm text-muted-foreground">
          Grade free-text answers from submitted assessments. MCQ, coding and aptitude
          questions are already scored automatically.
        </p>
      </div>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2">
          {Array.from({ length: 2 }).map((_, index) => (
            <Skeleton key={index} className="h-36 w-full" />
          ))}
        </div>
      ) : !pending || pending.length === 0 ? (
        <EmptyState
          icon={ClipboardCheck}
          title="Nothing to review"
          description="Every descriptive answer has been graded. New submissions will appear here automatically."
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {pending.map((item) => (
            <Card key={item.attempt_id}>
              <CardHeader>
                <div className="flex items-start justify-between gap-2">
                  <CardTitle className="text-base">{item.assessment_title}</CardTitle>
                  <Badge variant="warning">{item.pending_count} pending</Badge>
                </div>
                <CardDescription className="space-y-1">
                  <span className="flex items-center gap-1.5">
                    <GraduationCap className="h-3.5 w-3.5" />
                    {item.student_name || item.student_id}
                  </span>
                  <span className="flex items-center gap-1.5">
                    <Clock className="h-3.5 w-3.5" />
                    Submitted {formatDate(item.submitted_at)}
                  </span>
                </CardDescription>
              </CardHeader>
              <CardContent className="flex items-center justify-between gap-3 text-sm text-muted-foreground">
                <span className="capitalize">
                  {item.assessment_type} assessment
                  {item.drive_id ? " · drive-linked" : ""}
                </span>
                <Button size="sm" onClick={() => setSelectedAttemptId(item.attempt_id)}>
                  Review answers
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Dialog
        open={Boolean(selectedAttemptId)}
        onOpenChange={(open) => {
          if (!open) setSelectedAttemptId(null);
        }}
      >
        <DialogContent className="max-h-[85vh] max-w-3xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{review?.assessment_title || "Attempt review"}</DialogTitle>
            <DialogDescription>
              {review
                ? `${review.student_name || review.student_id} · ${review.total_marks}/${review.max_possible_marks} marks · ${review.pending_count} pending`
                : "Loading the attempt…"}
            </DialogDescription>
          </DialogHeader>

          {reviewLoading || !review ? (
            <div className="space-y-3">
              <Skeleton className="h-28 w-full" />
              <Skeleton className="h-28 w-full" />
            </div>
          ) : review.answers.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              This attempt has no descriptive answers to review.
            </p>
          ) : (
            <div className="space-y-4">
              {review.answers.map((answer) => (
                <GradeAnswerForm
                  key={`${answer.question_id}-${answer.graded_at ?? "pending"}`}
                  attemptId={review.attempt_id}
                  answer={answer}
                />
              ))}
              {review.pending_count === 0 && (
                <p className="flex items-center gap-2 text-sm text-success">
                  <CheckCircle2 className="h-4 w-4" />
                  All descriptive answers in this attempt are graded.
                </p>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
