"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Renders the small, well-defined Markdown subset the coach narrative uses:
 * headings, **bold**, *italic*, `inline code`, ordered/unordered lists,
 * blockquotes and paragraphs.
 *
 * Why a hand-written renderer instead of a Markdown library:
 *  - No new dependency (the project deliberately keeps its dependency set
 *    small), and
 *  - no `dangerouslySetInnerHTML`: every character is rendered as a React
 *    text node, so LLM output can never inject HTML or a script. Anything the
 *    parser does not recognise is shown literally rather than interpreted.
 */

type InlineToken =
  | { type: "text"; value: string }
  | { type: "bold"; value: string }
  | { type: "italic"; value: string }
  | { type: "code"; value: string };

// Bold first so `**x**` is never mistaken for two italic runs. Backticks are
// matched before emphasis so `*` inside code stays literal.
const INLINE_PATTERN =
  /(\*\*[^*\n]+\*\*|__[^_\n]+__|\*[^*\n]+\*|_[^_\n]+_|`[^`\n]+`)/g;

function parseInline(text: string): InlineToken[] {
  const tokens: InlineToken[] = [];
  let lastIndex = 0;
  for (const match of text.matchAll(INLINE_PATTERN)) {
    const index = match.index ?? 0;
    if (index > lastIndex) {
      tokens.push({ type: "text", value: text.slice(lastIndex, index) });
    }
    const raw = match[0];
    if (raw.startsWith("**") || raw.startsWith("__")) {
      tokens.push({ type: "bold", value: raw.slice(2, -2) });
    } else if (raw.startsWith("`")) {
      tokens.push({ type: "code", value: raw.slice(1, -1) });
    } else {
      tokens.push({ type: "italic", value: raw.slice(1, -1) });
    }
    lastIndex = index + raw.length;
  }
  if (lastIndex < text.length) {
    tokens.push({ type: "text", value: text.slice(lastIndex) });
  }
  return tokens;
}

function renderInline(text: string, keyPrefix: string): React.ReactNode[] {
  return parseInline(text).map((token, index) => {
    const key = `${keyPrefix}-${index}`;
    if (token.type === "bold") return <strong key={key}>{token.value}</strong>;
    if (token.type === "italic") return <em key={key}>{token.value}</em>;
    if (token.type === "code") {
      return (
        <code
          key={key}
          className="rounded bg-muted px-1 py-0.5 font-mono text-[0.85em] text-foreground"
        >
          {token.value}
        </code>
      );
    }
    return <React.Fragment key={key}>{token.value}</React.Fragment>;
  });
}

type Block =
  | { type: "paragraph"; lines: string[] }
  | { type: "heading"; level: number; text: string }
  | { type: "list"; ordered: boolean; items: string[] }
  | { type: "quote"; lines: string[] }
  | { type: "code"; lines: string[] }
  | { type: "rule" };

function parseBlocks(source: string): Block[] {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  let quote: string[] | null = null;
  let code: string[] | null = null;

  const flushParagraph = () => {
    if (paragraph.length) {
      blocks.push({ type: "paragraph", lines: paragraph });
      paragraph = [];
    }
  };
  const flushList = () => {
    if (list) {
      blocks.push({ type: "list", ordered: list.ordered, items: list.items });
      list = null;
    }
  };
  const flushQuote = () => {
    if (quote) {
      blocks.push({ type: "quote", lines: quote });
      quote = null;
    }
  };
  const flushCode = () => {
    if (code) {
      blocks.push({ type: "code", lines: code });
      code = null;
    }
  };
  const flushAll = () => {
    flushParagraph();
    flushList();
    flushQuote();
  };

  for (const rawLine of lines) {
    const line = rawLine.trimEnd();

    // Fenced code block: ``` ... ```
    if (line.trimStart().startsWith("```")) {
      if (code) {
        flushCode();
      } else {
        flushAll();
        code = [];
      }
      continue;
    }
    if (code) {
      code.push(rawLine);
      continue;
    }

    if (!line.trim()) {
      flushAll();
      continue;
    }

    const heading = /^(#{1,6})\s+(.*)$/.exec(line.trim());
    if (heading) {
      flushAll();
      blocks.push({
        type: "heading",
        level: heading[1]!.length,
        text: heading[2]!.trim(),
      });
      continue;
    }

    if (/^([-*_])\1{2,}\s*$/.test(line.trim())) {
      flushAll();
      blocks.push({ type: "rule" });
      continue;
    }

    const quoteMatch = /^>\s?(.*)$/.exec(line.trim());
    if (quoteMatch) {
      flushParagraph();
      flushList();
      quote = quote ?? [];
      quote.push(quoteMatch[1] ?? "");
      continue;
    }
    flushQuote();

    const unordered = /^[-*+]\s+(.*)$/.exec(line.trim());
    const ordered = /^\d+[.)]\s+(.*)$/.exec(line.trim());
    if (unordered || ordered) {
      flushParagraph();
      const isOrdered = Boolean(ordered);
      if (list && list.ordered !== isOrdered) flushList();
      list = list ?? { ordered: isOrdered, items: [] };
      list.items.push(((unordered ?? ordered)![1] ?? "").trim());
      continue;
    }
    flushList();

    paragraph.push(line.trim());
  }

  flushAll();
  flushCode();
  return blocks;
}

export interface MarkdownTextProps {
  content: string;
  className?: string;
}

export function MarkdownText({ content, className }: MarkdownTextProps) {
  const blocks = React.useMemo(() => parseBlocks(content), [content]);

  return (
    <div className={cn("space-y-3 text-sm leading-relaxed text-foreground", className)}>
      {blocks.map((block, index) => {
        const key = `block-${index}`;
        if (block.type === "heading") {
          const Heading = block.level <= 2 ? "h3" : "h4";
          return (
            <Heading
              key={key}
              className={cn(
                "font-semibold text-foreground",
                block.level <= 2 ? "text-base" : "text-sm"
              )}
            >
              {renderInline(block.text, key)}
            </Heading>
          );
        }
        if (block.type === "list") {
          const ListTag = block.ordered ? "ol" : "ul";
          return (
            <ListTag
              key={key}
              className={cn(
                "space-y-1 pl-5",
                block.ordered ? "list-decimal" : "list-disc"
              )}
            >
              {block.items.map((item, itemIndex) => (
                <li key={`${key}-${itemIndex}`}>{renderInline(item, `${key}-${itemIndex}`)}</li>
              ))}
            </ListTag>
          );
        }
        if (block.type === "quote") {
          return (
            <blockquote
              key={key}
              className="border-l-2 border-primary/40 pl-3 text-muted-foreground"
            >
              {block.lines.map((line, lineIndex) => (
                <p key={`${key}-${lineIndex}`}>{renderInline(line, `${key}-${lineIndex}`)}</p>
              ))}
            </blockquote>
          );
        }
        if (block.type === "code") {
          return (
            <pre
              key={key}
              className="overflow-x-auto rounded-md bg-muted p-3 font-mono text-xs text-foreground"
            >
              <code>{block.lines.join("\n")}</code>
            </pre>
          );
        }
        if (block.type === "rule") {
          return <hr key={key} className="border-border" />;
        }
        return (
          <p key={key}>
            {block.lines.map((line, lineIndex) => (
              <React.Fragment key={`${key}-${lineIndex}`}>
                {lineIndex > 0 && " "}
                {renderInline(line, `${key}-${lineIndex}`)}
              </React.Fragment>
            ))}
          </p>
        );
      })}
    </div>
  );
}
