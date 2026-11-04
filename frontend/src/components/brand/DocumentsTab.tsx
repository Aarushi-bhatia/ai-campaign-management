import { useState } from "react";
import type { Brand, BrandDocument, DocumentCard } from "../../api/types";
import { formatTokens } from "../../format";
import { Line, Quote, StatusBadge } from "./bits";
import type { Corrections } from "./useCorrections";

const KINDS = ["rule", "reference", "example", "template", "persona", "case_study", "press", "internal_note", "index", "other"];
const STATUSES = ["current", "replaced", "draft", "archived"];
const SAFE_LABELS = { yes: "Safe to quote", no: "Not for public copy", unknown: "Not stated" };
const SAFE_SHORT = { yes: "yes", no: "no", unknown: "—" };

type Props = {
  brand: Brand;
  corrections: Corrections;
  onViewPrompt: (callId: number) => void;
};

export function DocumentsTab({ brand, corrections, onViewPrompt }: Props) {
  const [openId, setOpenId] = useState<number | null>(null);

  return (
    <table className="w-full text-left text-sm">
      <thead className="sticky top-0 bg-stone-50 text-xs uppercase tracking-wide text-stone-500">
        <tr>
          <th className="px-6 py-2 font-medium">Document</th>
          <th className="px-2 py-2 font-medium">Type</th>
          <th className="px-2 py-2 font-medium">Status</th>
          <th className="px-2 py-2 font-medium">Date</th>
          <th className="px-2 py-2 font-medium">Owner</th>
          <th className="px-2 py-2 font-medium">Public</th>
        </tr>
      </thead>
      <tbody>
        {brand.documents.map((doc) => (
          <DocumentRow
            key={doc.id}
            doc={doc}
            open={openId === doc.id}
            onToggle={() => setOpenId(openId === doc.id ? null : doc.id)}
            corrections={corrections}
            onViewPrompt={onViewPrompt}
          />
        ))}
      </tbody>
    </table>
  );
}

type RowProps = {
  doc: BrandDocument;
  open: boolean;
  onToggle: () => void;
  corrections: Corrections;
  onViewPrompt: (callId: number) => void;
};

function DocumentRow({ doc, open, onToggle, corrections, onViewPrompt }: RowProps) {
  const card = doc.card;
  const slash = doc.path.lastIndexOf("/");
  const corrected = corrections.decisionFor("document_status", doc.path) || corrections.decisionFor("document_kind", doc.path);
  return (
    <>
      <tr onClick={onToggle} className="cursor-pointer border-t border-stone-100 hover:bg-stone-50">
        <td className="px-6 py-2">
          <span className="text-stone-400">{doc.path.slice(0, slash + 1)}</span>
          <span className="font-medium">{doc.path.slice(slash + 1)}</span>
          {card && card.unverified.length > 0 && (
            <span className="ml-2 text-xs text-amber-700" title="Claims dropped because their quote wasn't found">
              {card.unverified.length} unproven
            </span>
          )}
          {corrected && <span className="ml-2 text-xs text-violet-700">corrected</span>}
        </td>
        {card ? (
          <>
            <td className="px-2 py-2 text-stone-600">{(doc.doc_type ?? card.kind).replace("_", " ")}</td>
            <td className="px-2 py-2">{doc.status && <StatusBadge status={doc.status} />}</td>
            <td className="px-2 py-2 text-stone-600">{card.date.iso || "—"}</td>
            <td className="px-2 py-2 text-stone-600">{card.owner.name || "—"}</td>
            <td className={`px-2 py-2 ${card.safe_to_quote.value === "no" ? "text-red-700" : "text-stone-600"}`}>
              {SAFE_SHORT[card.safe_to_quote.value]}
            </td>
          </>
        ) : (
          <td colSpan={5} className="px-2 py-2 text-stone-400">
            {doc.card_error ? <span className="text-red-600">Card failed: {doc.card_error}</span> : "Reading…"}
          </td>
        )}
      </tr>
      {open && (
        <tr className="bg-stone-50">
          <td colSpan={6} className="px-6 pb-4 pt-1">
            <DocumentDetail doc={doc} corrections={corrections} onViewPrompt={onViewPrompt} />
          </td>
        </tr>
      )}
    </>
  );
}

function DocumentDetail({ doc, corrections, onViewPrompt }: Omit<RowProps, "open" | "onToggle">) {
  const card = doc.card;
  const basics = doc.basics;
  return (
    <div className="space-y-3 text-sm">
      {card && <p className="text-stone-700">{card.summary}</p>}
      {doc.status_reason && (
        <Line label="Status">
          <StatusBadge status={doc.status!} /> <span className="ml-1 text-stone-600">{doc.status_reason}</span>
        </Line>
      )}
      <Corrector doc={doc} corrections={corrections} />
      {card && <Proofs card={card} />}
      {card && card.rules_on.length > 0 && <Line label="Sets rules on">{card.rules_on.join(", ")}</Line>}
      {card && <Mentions card={card} />}
      {card && card.unverified.length > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
          <p className="font-medium">Dropped because the quote wasn't found in the document:</p>
          <ul className="mt-1 list-disc pl-4">
            {card.unverified.map((item, index) => (
              <li key={index}>
                {item.field}: {item.value} (quoted “{item.evidence}”)
              </li>
            ))}
          </ul>
        </div>
      )}
      {basics && (
        <Line label="Found without AI">
          {formatTokens(basics.tokens)} tokens · {doc.sections} sections · {doc.facts} facts ·{" "}
          {basics.headings.length} headings
          {basics.name_hints.length > 0 && ` · file name hints: ${basics.name_hints.join(", ")}`}
          {Object.keys(basics.frontmatter).length > 0 && ` · labels: ${formatLabels(basics.frontmatter)}`}
          {Object.keys(basics.top_labels).length > 0 && ` · top lines: ${formatLabels(basics.top_labels)}`}
        </Line>
      )}
      {doc.facts_error && <p className="text-xs text-red-600">Facts failed: {doc.facts_error}</p>}
      <div className="flex gap-4 text-xs text-stone-500">
        {doc.card_call_id && (
          <button onClick={() => onViewPrompt(doc.card_call_id!)} className="underline hover:text-stone-900">
            View prompt for the card
          </button>
        )}
        {doc.facts_call_id && (
          <button onClick={() => onViewPrompt(doc.facts_call_id!)} className="underline hover:text-stone-900">
            View prompt for the facts
          </button>
        )}
      </div>
    </div>
  );
}

/** Lets the user overrule the status or type the app worked out. */
function Corrector({ doc, corrections }: { doc: BrandDocument; corrections: Corrections }) {
  const statusFix = corrections.decisionFor("document_status", doc.path);
  const kindFix = corrections.decisionFor("document_kind", doc.path);
  return (
    <div className="flex flex-wrap items-center gap-3 text-xs">
      <span className="min-w-28 font-medium uppercase tracking-wide text-stone-400">Correct</span>
      <label className="flex items-center gap-1">
        Status
        <select
          value={statusFix?.value ?? ""}
          disabled={corrections.busy}
          onChange={(event) => corrections.correct("document_status", doc.path, event.target.value)}
          className="rounded-lg border border-stone-200 bg-white px-1 py-0.5"
        >
          <option value="" disabled>
            as worked out
          </option>
          {STATUSES.map((status) => (
            <option key={status}>{status}</option>
          ))}
        </select>
      </label>
      <label className="flex items-center gap-1">
        Type
        <select
          value={kindFix?.value ?? ""}
          disabled={corrections.busy}
          onChange={(event) => corrections.correct("document_kind", doc.path, event.target.value)}
          className="rounded-lg border border-stone-200 bg-white px-1 py-0.5"
        >
          <option value="" disabled>
            as worked out
          </option>
          {KINDS.map((kind) => (
            <option key={kind} value={kind}>
              {kind.replace("_", " ")}
            </option>
          ))}
        </select>
      </label>
      {[statusFix, kindFix].filter(Boolean).map((decision) => (
        <button key={decision!.id} onClick={() => corrections.undo(decision!)} className="text-violet-700 underline">
          Undo {decision!.kind === "document_status" ? "status" : "type"} correction
        </button>
      ))}
    </div>
  );
}

function Proofs({ card }: { card: DocumentCard }) {
  const rows: [string, string, string][] = [
    ["Says it is", card.claimed_status.value, card.claimed_status.evidence],
    ["Date", card.date.as_written, card.date.evidence],
    ["Owner", [card.owner.name, card.owner.role].filter(Boolean).join(", "), card.owner.evidence],
    ["Public copy", SAFE_LABELS[card.safe_to_quote.value], card.safe_to_quote.evidence],
    ...card.replaces.map((item): [string, string, string] => ["Replaces", item.document, item.evidence]),
    ...card.claims_about_other_documents.map((item): [string, string, string] => [
      `About ${item.document}`,
      item.claim,
      item.evidence,
    ]),
  ];
  return (
    <div className="space-y-1">
      {rows
        .filter(([, value, evidence]) => value || evidence)
        .map(([label, value, evidence], index) => (
          <Line key={index} label={label}>
            {value || "—"}
            {evidence && <Quote text={evidence} />}
          </Line>
        ))}
    </div>
  );
}

function Mentions({ card }: { card: DocumentCard }) {
  const groups = Object.entries(card.mentions).filter(([, names]) => names.length > 0);
  if (!groups.length) return null;
  return <Line label="Mentions">{groups.map(([group, names]) => `${group}: ${names.join(", ")}`).join(" · ")}</Line>;
}

function formatLabels(labels: Record<string, string>): string {
  return Object.entries(labels)
    .map(([key, value]) => `${key}: ${value}`)
    .join("; ");
}
