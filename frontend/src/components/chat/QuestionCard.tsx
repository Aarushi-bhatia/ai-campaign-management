import { useState } from "react";
import type { QuestionData } from "../../api/types";
import { plainQuote } from "../../format";

const KIND_LABELS: Record<QuestionData["kind"], string> = {
  missing: "Missing from the brief",
  unclear: "Needs a choice",
  clash: "Your brief goes against a brand rule",
  conflict: "The brand's documents disagree",
};

type Props = {
  question: QuestionData;
  open: boolean;
  busy: boolean;
  onAnswer: (answer: string) => void;
};

/** One question: clickable options, recommendation first, and a box to type an answer instead. */
export function QuestionCard({ question, open, busy, onAnswer }: Props) {
  const [typed, setTyped] = useState("");
  const clash = question.kind === "clash" || question.kind === "conflict";

  return (
    <div className={`max-w-[90%] rounded-xl border px-5 py-4 text-sm leading-relaxed ${clash ? "border-amber-200 bg-amber-50/50" : "border-stone-200/70 bg-stone-50"}`}>
      <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-stone-400">
        {KIND_LABELS[question.kind]}
        {open && question.remaining > 1 && ` · ${question.remaining - 1} more after this`}
      </p>
      <p className="mt-2 font-medium">{question.question}</p>
      {question.why && <p className="mt-1.5 text-stone-600">{question.why}</p>}
      {question.quote && (
        <blockquote className="mt-3 border-l-2 border-amber-300 pl-3 text-stone-700">
          “{plainQuote(question.quote)}”
          <span className="mt-0.5 block text-xs text-stone-400">{question.source_path}</span>
        </blockquote>
      )}
      {question.answer ? (
        <p className="mt-3 text-stone-500">
          Answered: <span className="font-medium text-stone-800">{question.answer}</span>
        </p>
      ) : question.asked_again ? (
        <p className="mt-3 text-stone-500">
          “{question.asked_again}” wasn't a clear yes or no, so this is asked again below.
        </p>
      ) : question.expired ? (
        <p className="mt-3 text-stone-500">No longer needed: the plan was approved before this was answered.</p>
      ) : (
        open && (
          <>
            <div className="mt-4 flex flex-wrap gap-2">
              {question.options.map((option, index) => (
                <button
                  key={option.value}
                  onClick={() => onAnswer(option.value)}
                  disabled={busy}
                  className={`rounded-full border px-4 py-1.5 disabled:opacity-40 ${
                    index === 0 ? "border-violet-700 bg-violet-700 text-white" : "border-stone-200 bg-white hover:bg-stone-100"
                  }`}
                >
                  {option.label}
                  {index === 0 && <span className="ml-1 text-xs opacity-70">(suggested)</span>}
                </button>
              ))}
            </div>
            <form
              className="mt-3 flex gap-2"
              onSubmit={(event) => {
                event.preventDefault();
                if (typed.trim()) onAnswer(typed.trim());
              }}
            >
              <input
                value={typed}
                onChange={(event) => setTyped(event.target.value)}
                placeholder="Or type your own answer"
                className="flex-1 rounded-lg border border-stone-200 px-3 py-2"
              />
              <button disabled={busy || !typed.trim()} className="rounded-lg border border-stone-200 bg-white px-4 hover:bg-stone-100 disabled:opacity-40">
                Answer
              </button>
            </form>
          </>
        )
      )}
    </div>
  );
}
