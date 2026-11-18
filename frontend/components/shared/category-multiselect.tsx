"use client";

import { Plus, X } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Combobox } from "@/components/ui/combobox";
import { cn } from "@/lib/utils";

export interface CategoryOption {
  id: string;
  name: string;
}

interface CategoryMultiSelectProps {
  categories: readonly CategoryOption[];
  /** Selected category IDs. */
  value: string[];
  onChange: (ids: string[]) => void;
  id?: string;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
}

/**
 * Searchable, typeable category picker with removable chips.
 *
 * The admin can pick a category from the native dropdown, type to filter it,
 * or type a category name / ID manually. Manual values are resolved against
 * the real category list before they are added, so an invalid reference can
 * never be submitted to the API.
 */
export function CategoryMultiSelect({
  categories,
  value,
  onChange,
  id,
  placeholder = "Search or type a category, then press Add",
  disabled = false,
  className,
}: CategoryMultiSelectProps) {
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);

  const byId = useMemo(() => new Map(categories.map((category) => [category.id, category])), [categories]);
  const byName = useMemo(
    () => new Map(categories.map((category) => [category.name.trim().toLowerCase(), category])),
    [categories]
  );

  const selected = value
    .map((categoryId) => byId.get(categoryId))
    .filter((category): category is CategoryOption => Boolean(category));

  const options = categories
    .filter((category) => !value.includes(category.id))
    .map((category) => category.name);

  const add = () => {
    const raw = input.trim();
    if (!raw) return;
    const match = byId.get(raw) ?? byName.get(raw.toLowerCase());
    if (!match) {
      setError(`"${raw}" is not an existing category. Pick one from the list or create it first.`);
      return;
    }
    if (value.includes(match.id)) {
      setError(`"${match.name}" is already selected.`);
      return;
    }
    onChange([...value, match.id]);
    setInput("");
    setError(null);
  };

  const remove = (categoryId: string) => {
    onChange(value.filter((current) => current !== categoryId));
    setError(null);
  };

  return (
    <div className={cn("space-y-2", className)}>
      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {selected.map((category) => (
            <span
              key={category.id}
              className="inline-flex items-center gap-1 rounded-md border border-border bg-secondary px-2 py-1 text-xs"
            >
              {category.name}
              {!disabled && (
                <button
                  type="button"
                  aria-label={`Remove ${category.name}`}
                  className="text-muted-foreground transition-colors hover:text-foreground"
                  onClick={() => remove(category.id)}
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </span>
          ))}
        </div>
      )}

      <div className="flex gap-2">
        <Combobox
          id={id}
          options={options}
          value={input}
          disabled={disabled}
          placeholder={placeholder}
          className="flex-1"
          onChange={(event) => {
            setInput(event.target.value);
            setError(null);
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              add();
            }
          }}
        />
        <Button type="button" size="sm" variant="outline" disabled={disabled || !input.trim()} onClick={add}>
          <Plus className="mr-1 h-3.5 w-3.5" /> Add
        </Button>
      </div>

      {error && <p className="text-xs text-destructive">{error}</p>}
      {categories.length === 0 && (
        <p className="text-xs text-muted-foreground">
          No categories exist yet. Create one from the Question bank first.
        </p>
      )}
    </div>
  );
}
