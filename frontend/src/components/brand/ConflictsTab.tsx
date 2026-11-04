import type { Brand, Conflict } from "../../api/types";
import { Quote } from "./bits";
import type { Corrections } from "./useCorrections";

const RULE_LABELS: Record<Conflict["rule"], string> = {
  replaces: "Replaced document loses",
  owner: "Document in charge wins",
  approved: "Approved beats draft",
  newer: "Newer wins",
  live: "Live beats archived",
  you: "Chosen by you",
  needs_human: "Needs your decision",
  only_side_left: "Only one side still counts",
  not_counting: "No longer applies",
};

type Props = {
  brand: Brand;
  corrections: Corrections;
  onViewPrompt: (callId: number) => void;
};

export function ConflictsTab({ brand, corrections, onViewPrompt }: Props) {
  if (!brand.conflicts.length) {
    return <p className="p-6 text-sm text-stone-500">No documents disagree, or the brand hasn't been compared yet.</p>;
  }
  return (
    <div className="space-y-3 p-6">
      <p className="text-sm text-stone-500">
        Where documents disagree, the winning side is picked by these rules in order: replaced documents lose, the
        document in charge of the topic wins (internal documents never are), approved beats draft, newer beats older,
        live beats archived. Documents on the same side never compete. You can pick another side; it applies at once.
      </p>
      {brand.conflicts.map((conflict) => (
        <ConflictCard key={conflict.id} conflict={conflict} corrections={corrections} onViewPrompt={onViewPrompt} />
      ))}
    </div>
  );
}

function ConflictCard({ conflict, corrections, onViewPrompt }: { conflict: Conflict } & Omit<Props, "brand">) {
  // The choice that applies can be named after the documents it was made between, before another one joined.
  const decision = corrections.decisionFor("conflict_winner", conflict.decided_target ?? conflict.target);
  const undecided = conflict.rule === "needs_human";

  return (
    <article className={`rounded-xl border p-4 ${undecided ? "border-amber-300 bg-amber-50/40" : "border-stone-200"}`}>
      <header className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-wide text-stone-400">
            {conflict.subject} · {conflict.topic}
          </p>
          <h3 className="font-medium">{conflict.point}</h3>
        </div>
        <span
          className={`shrink-0 rounded-full px-2 py-0.5 text-xs ${undecided ? "bg-amber-100 text-amber-900" : "bg-stone-100 text-stone-700"}`}
        >
          {RULE_LABELS[conflict.rule]}
        </span>
      </header>
      <p className="mt-1 text-sm text-stone-600">{conflict.reason}</p>
      <div className="mt-3 space-y-2">
        {conflict.sides.map((position, side) => (
          <SideBox
            key={side}
            position={position}
            wins={conflict.winning_side === side}
            facts={conflict.facts.filter((fact) => fact.side === side)}
            owners={conflict.owners}
            onChoose={(path) => corrections.correct("conflict_winner", conflict.target, path)}
            busy={corrections.busy}
          />
        ))}
      </div>
      <div className="mt-2 flex gap-4 text-xs text-stone-500">
        {decision && (
          <button onClick={() => corrections.undo(decision)} className="text-violet-700 underline">
            Undo my choice
          </button>
        )}
        {conflict.call_id && (
          <button onClick={() => onViewPrompt(conflict.call_id!)} className="underline hover:text-stone-900">
            View prompt
          </button>
        )}
      </div>
    </article>
  );
}

type SideProps = {
  position: string;
  wins: boolean;
  facts: Conflict["facts"];
  owners: string[];
  onChoose: (path: string) => void;
  busy: boolean;
};

/** One position in the disagreement, with every document that takes it. */
function SideBox({ position, wins, facts, owners, onChoose, busy }: SideProps) {
  const byPath = new Map<string, Conflict["facts"]>();
  for (const fact of facts) byPath.set(fact.path, [...(byPath.get(fact.path) ?? []), fact]);
  const first = facts[0]?.path;
  return (
    <div className={`rounded-lg border p-2 text-sm ${wins ? "border-emerald-300 bg-emerald-50" : "border-stone-200"}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium">
          {wins && "✓ "}
          {position}
        </span>
        {!wins && first && (
          <button onClick={() => onChoose(first)} disabled={busy} className="text-xs text-violet-700 underline disabled:opacity-40">
            Use this side
          </button>
        )}
      </div>
      {[...byPath].map(([path, pathFacts]) => (
        <div key={path} className="mt-1">
          <p className="text-xs text-stone-500">
            {path}
            {owners.includes(path) && <span className="ml-2">in charge</span>}
          </p>
          {pathFacts.map((fact) => (
            <p key={fact.id} className="text-stone-700">
              {fact.attribute}: {fact.value}
              <Quote text={fact.evidence} />
            </p>
          ))}
        </div>
      ))}
    </div>
  );
}
