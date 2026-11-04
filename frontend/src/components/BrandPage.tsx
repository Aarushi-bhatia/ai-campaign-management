import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Brand } from "../api/types";
import { formatCost, formatTokens } from "../format";
import { ConflictsTab } from "./brand/ConflictsTab";
import { ImagesTab } from "./brand/ImagesTab";
import { NamesTab } from "./brand/NamesTab";
import { SummaryTab } from "./brand/SummaryTab";
import { useCorrections } from "./brand/useCorrections";
import { DocumentsTab } from "./brand/DocumentsTab";

const POLL_WHILE_READING_MS = 1500;

const PHASES: Record<string, string> = {
  sections: "Splitting documents into sections",
  cards: "Writing a card for each document",
  names: "Matching old and new names",
  links: "Working out which documents replace which",
  facts: "Pulling out facts and rules",
  conflicts: "Checking where documents disagree",
  images: "Describing images that have no description",
  image_notes: "Reading image rights and restrictions",
  image_rules: "Working out image rules per channel",
  summary: "Writing the brand summary",
};

type Tab = "documents" | "conflicts" | "names" | "images" | "summary";

type Props = {
  brandId: number;
  onViewPrompt: (callId: number) => void;
  onUpdate: (brand: Brand) => void;
};

/** What the app learned about a brand, and where to correct it. */
export function BrandPage({ brandId, onViewPrompt, onUpdate }: Props) {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("documents");
  const brand = useQuery({
    queryKey: ["brand", brandId],
    queryFn: () => api.getBrand(brandId),
    refetchInterval: (query) => (query.state.data?.status === "reading" ? POLL_WHILE_READING_MS : false),
  });
  const readAgain = useMutation({
    mutationFn: () => api.readBrandAgain(brandId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["brand", brandId] }),
  });

  const data = brand.data;
  const readyAndUnreviewed = data?.status === "ready" && !data.reviewed;
  useEffect(() => {
    if (readyAndUnreviewed) {
      api.markBrandReviewed(brandId).then(() => queryClient.invalidateQueries({ queryKey: ["brands"] }));
    }
  }, [readyAndUnreviewed, brandId, queryClient]);

  useEffect(() => {
    if (data?.status !== "reading") queryClient.invalidateQueries({ queryKey: ["brands"] });
  }, [data?.status, queryClient]);

  if (!data) return <section className="flex-1 bg-white p-8 text-sm text-stone-500">Loading…</section>;

  const unsettled = data.conflicts.filter((c) => c.rule === "needs_human").length;
  const tabs: [Tab, string][] = [
    ["documents", `Documents (${data.documents.length})`],
    ["conflicts", `Conflicts (${data.conflicts.length})${unsettled ? ` · ${unsettled} to decide` : ""}`],
    ["names", `Names (${data.entities.length})`],
    ["images", `Images (${data.images.length})`],
    ["summary", "Brand summary"],
  ];

  return (
    <section className="flex min-w-0 flex-1 flex-col overflow-hidden bg-white">
      <header className="border-b border-stone-100 px-8 pt-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-medium">{data.name}</h1>
            <ReadingStatus brand={data} />
          </div>
          <div className="flex gap-2">
            <HeaderButton onClick={() => onUpdate(data)} disabled={data.status === "reading"}
              title="Upload the brand folder again. Only new or changed files are read.">
              Update brand
            </HeaderButton>
            <HeaderButton onClick={() => readAgain.mutate()} disabled={data.status === "reading" || readAgain.isPending}
              title="Reads new or failed documents. Unchanged work is kept.">
              Read again
            </HeaderButton>
          </div>
        </div>
        <nav className="mt-4 flex gap-5 text-sm">
          {tabs.map(([id, label]) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={`border-b-2 pb-2 ${tab === id ? "border-violet-700 font-medium" : "border-transparent text-stone-500 hover:text-stone-900"}`}
            >
              {label}
            </button>
          ))}
        </nav>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <BrandTab tab={tab} brand={data} onViewPrompt={onViewPrompt} />
      </div>
    </section>
  );
}

function BrandTab({ tab, brand, onViewPrompt }: { tab: Tab; brand: Brand; onViewPrompt: (callId: number) => void }) {
  const corrections = useCorrections(brand);
  return (
    <>
      {corrections.error && <p className="px-6 pt-3 text-sm text-red-600">{corrections.error.message}</p>}
      {tab === "documents" && <DocumentsTab brand={brand} corrections={corrections} onViewPrompt={onViewPrompt} />}
      {tab === "conflicts" && <ConflictsTab brand={brand} corrections={corrections} onViewPrompt={onViewPrompt} />}
      {tab === "names" && <NamesTab entities={brand.entities} />}
      {tab === "images" && <ImagesTab brand={brand} corrections={corrections} onViewPrompt={onViewPrompt} />}
      {tab === "summary" && <SummaryTab brand={brand} onViewPrompt={onViewPrompt} />}
    </>
  );
}

function HeaderButton(props: { onClick: () => void; disabled: boolean; title: string; children: React.ReactNode }) {
  return (
    <button
      onClick={props.onClick}
      disabled={props.disabled}
      title={props.title}
      className="rounded-lg border border-stone-200 px-3 py-1.5 text-sm hover:bg-stone-50 disabled:opacity-40"
    >
      {props.children}
    </button>
  );
}

function ReadingStatus({ brand }: { brand: Brand }) {
  const cost = brand.reading_cost;
  const costLine = `Reading cost ${formatCost(cost.usd)} · ${cost.calls} AI calls · ${formatTokens(cost.tokens_in)} tokens in`;
  if (brand.status === "reading") {
    const percent = brand.phase_total ? (brand.phase_done / brand.phase_total) * 100 : 0;
    return (
      <div className="mt-2 w-96">
        <p className="text-sm text-stone-600">
          {PHASES[brand.phase] ?? "Getting started"}
          {brand.phase_total > 1 && `: ${brand.phase_done} of ${brand.phase_total}`}
        </p>
        <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-stone-200">
          <div className="h-full bg-stone-800 transition-all" style={{ width: `${percent}%` }} />
        </div>
        <p className="mt-1 text-xs text-stone-400">{costLine}</p>
      </div>
    );
  }
  if (brand.status === "failed") {
    return <p className="mt-1 text-sm text-red-600">Reading failed: {brand.error}. Use Read again to retry.</p>;
  }
  const failed = brand.documents.filter((doc) => doc.card_error || doc.facts_error).length;
  return (
    <p className="mt-1 text-sm text-stone-500">
      {brand.documents.length} documents, {brand.other_files.length} other files · {costLine}
      {failed > 0 && <span className="text-amber-700"> · {failed} documents had errors, use Read again</span>}
    </p>
  );
}
