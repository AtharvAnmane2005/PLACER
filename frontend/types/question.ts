import type {
  CodingLanguage,
  DifficultyLevel,
  QuestionStatus,
  QuestionTestCase,
  QuestionType,
} from "@/types/assessment";

export interface CategoryResponse {
  id: string;
  name: string;
  parent_category_id: string | null;
}

export interface CategoryCreateRequest {
  name: string;
  parent_category_id?: string;
}

export interface QuestionAdminResponse {
  id: string;
  category_id: string;
  skill_tags: string[];
  difficulty: DifficultyLevel;
  type: QuestionType;
  text: string;
  options: string[];
  correct_answer: string | null;
  language: CodingLanguage | null;
  starter_code: string | null;
  test_cases: QuestionTestCase[];
  marks: number;
  company_tags: string[];
  topic: string | null;
  skill: string | null;
  explanation: string | null;
  status: QuestionStatus;
  updated_at: string | null;
}

export interface QuestionCreateRequest {
  category_id: string;
  skill_tags: string[];
  difficulty: DifficultyLevel;
  type: QuestionType;
  text: string;
  options: string[];
  correct_answer?: string | null;
  language?: CodingLanguage | null;
  starter_code?: string | null;
  test_cases?: QuestionTestCase[];
  company_tags: string[];
  topic?: string | null;
  skill?: string | null;
  explanation?: string | null;
  status?: QuestionStatus;
  marks?: number | null;
}

export interface QuestionUpdateRequest {
  category_id?: string;
  skill_tags?: string[];
  difficulty?: DifficultyLevel;
  type?: QuestionType;
  text?: string;
  options?: string[];
  correct_answer?: string | null;
  language?: CodingLanguage | null;
  starter_code?: string | null;
  test_cases?: QuestionTestCase[];
  company_tags?: string[];
  topic?: string | null;
  skill?: string | null;
  explanation?: string | null;
  status?: QuestionStatus;
  marks?: number | null;
}

export interface QuestionStatsResponse {
  total: number;
  active: number;
  inactive: number;
  by_category: Record<string, number>;
  by_difficulty: Record<string, number>;
  by_type: Record<string, number>;
}

export interface QuestionFilters {
  category_id?: string;
  difficulty?: string;
  search?: string;
  question_type?: string;
  topic?: string;
  skill?: string;
  status?: string;
  limit?: number;
  ids?: string;
}

export interface ImportRowError {
  row: number;
  field: string;
  message: string;
}

export interface ImportPreviewRow {
  row: number;
  question: QuestionCreateRequest | null;
  raw_text: string | null;
  errors: ImportRowError[];
}

export interface ImportPreviewResponse {
  filename: string;
  detected_columns: Record<string, string>;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  duplicate_rows: number;
  rows: ImportPreviewRow[];
}

export interface ImportCommitResponse {
  total_rows: number;
  imported: number;
  duplicates: number;
  invalid: number;
  failed: number;
  duplicate_rows: ImportRowError[];
  failed_rows: ImportRowError[];
  questions: QuestionAdminResponse[];
}
