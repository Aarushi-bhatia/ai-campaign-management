import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../../api/client";
import type { Campaign, Finding, PlanAsset } from "../../api/types";
import { domainOf, TYPE_LABELS } from "../assets/labels";

const FIELDS: [keyof PlanAsset, string][] = [
  ["audience", "Audience"],
  ["main_message", "Main message"],
  ["date", "Date"],
  ["image_idea", "Image"],
  ["notes", "Notes"],
  ["draft_for", "Draft for"],
];

type Props = {
  chatId: number;
  campaign: Campaign;
};

/** The plan as cards. Small changes happen here; anything bigger goes through the chat. */
export function PlanPanel({ chatId, campaign }: Props) {
  const queryClient = useQueryClient();
  const [dragging, setDragging] = useState<string | null>(null);
  const plan = campaign.plan!;
  const locked = campaign.stage !== "plan_ready";
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["chat", chatId] });
    queryClient.invalidateQueries({ queryKey: ["calls", chatId] });
  };

  // Both send the plan version shown, so a plan that changed meanwhile isn't overwritten or approved unseen;
  // a refused save refreshes the cards to the latest plan.
  const save = useMutation({
    mutationFn: (assets: PlanAsset[]) => api.updatePlan(chatId, assets, campaign.plan_version),
    onSettled: refresh,
  });
  const exclusions = plan.image_exclusions ?? [];
  const allowType = useMutation({
    mutationFn: (type: string) =>
      api.updatePlan(chatId, plan.assets, campaign.plan_version,
        exclusions.map((e) => e.image_type).filter((t) => t !== type)),
    onSettled: refresh,
  });
  const approve = useMutation({ mutationFn: () => api.approvePlan(chatId, campaign.plan_version), onSettled: refresh });
  const remove = useMutation({ mutationFn: (id: string) => api.removeFinding(chatId, id), onSuccess: refresh });
  const better = useMutation({ mutationFn: (id: string) => api.betterSource(chatId, id), onSettled: refresh });
  const bringBack = useMutation({ mutationFn: (id: string) => api.bringBackFinding(chatId, id), onSuccess: refresh });
  const retry = useMutation({ mutationFn: () => api.retryResearch(chatId), onSettled: refresh });
  const error = save.error ?? allowType.error ?? approve.error ?? better.error ?? remove.error ?? bringBack.error ?? retry.error;
  const failed = new Set((plan.failed_searches ?? []).map(searchKey));

  function move(fromId: string, toId: string) {
    const assets = [...plan.assets];
    const from = assets.findIndex((a) => a.id === fromId);
    const to = assets.findIndex((a) => a.id === toId);
    const [moved] = assets.splice(from, 1);
    assets.splice(to, 0, moved);
    save.mutate(assets);
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-6">
        <div>
          <h2 className="font-medium">Campaign plan</h2>
          <p className="mt-2 text-sm leading-relaxed text-stone-600">{plan.summary}</p>
        </div>
        {campaign.brief_rules.length > 0 && (
          <Box title="This campaign overrides the brand on">
            {campaign.brief_rules.map((rule) => <li key={rule}>{rule}</li>)}
          </Box>
        )}
        {exclusions.length > 0 && (
          <Box title="Images this campaign keeps off">
            {exclusions.map((e) => (
              <li key={e.image_type}>
                {e.image_type.replace(/_/g, " ")} <span className="text-stone-500">(brief: “{e.quote}”)</span>
                {!locked && (
                  <button
                    onClick={() => allowType.mutate(e.image_type)}
                    disabled={allowType.isPending || save.isPending}
                    className="ml-2 text-xs text-stone-500 underline hover:text-stone-800 disabled:opacity-40"
                  >
                    Allow
                  </button>
                )}
              </li>
            ))}
          </Box>
        )}
        {plan.assets.map((asset, index) => (
          <AssetCard
            key={asset.id}
            number={index + 1}
            asset={asset}
            locked={locked}
            busy={save.isPending}
            dragging={dragging === asset.id}
            onDragStart={() => setDragging(asset.id)}
            onDrop={() => dragging && dragging !== asset.id && move(dragging, asset.id)}
            onDragEnd={() => setDragging(null)}
            onRemove={() => save.mutate(plan.assets.filter((a) => a.id !== asset.id))}
            onSave={(changed) => save.mutate(plan.assets.map((a) => (a.id === changed.id ? changed : a)))}
          >
            <Research
              query={asset.research_query}
              findings={campaign.research.filter((f) => f.asset_ids.includes(asset.id) && !f.removed)}
              removed={campaign.research.filter((f) => f.asset_ids.includes(asset.id) && f.removed)}
              failed={failed.has(searchKey(asset.research_query))}
              retrying={retry.isPending}
              onRetry={() => retry.mutate()}
              locked={locked}
              busy={remove.isPending || better.isPending || bringBack.isPending}
              searching={better.isPending ? better.variables : null}
              onRemove={(id) => remove.mutate(id)}
              onBetter={(id) => better.mutate(id)}
              onBringBack={(id) => bringBack.mutate(id)}
            />
          </AssetCard>
        ))}
        {campaign.assumptions.length > 0 && (
          <Box title="Assumptions">
            {campaign.assumptions.map((line) => <li key={line}>{line}</li>)}
          </Box>
        )}
        {error && <p className="text-sm text-red-600">{error.message}</p>}
      </div>
      <footer className="border-t border-stone-100 bg-white px-6 py-4">
        {locked ? (
          <p className="text-sm text-emerald-800">Approved. The plan is locked.</p>
        ) : (
          <div className="flex items-center justify-between gap-3">
            <p className="text-xs text-stone-500">Nothing is written until you approve.</p>
            <button
              onClick={() => approve.mutate()}
              disabled={approve.isPending || plan.assets.length === 0}
              className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-40"
            >
              {approve.isPending ? "Starting…" : "Approve plan"}
            </button>
          </div>
        )}
      </footer>
    </div>
  );
}

type CardProps = {
  number: number;
  asset: PlanAsset;
  locked: boolean;
  busy: boolean;
  dragging: boolean;
  onDragStart: () => void;
  onDrop: () => void;
  onDragEnd: () => void;
  onRemove: () => void;
  onSave: (asset: PlanAsset) => void;
  children?: React.ReactNode;
};

function AssetCard({ number, asset, locked, busy, dragging, onDragStart, onDrop, onDragEnd, onRemove, onSave, children }: CardProps) {
  const [draft, setDraft] = useState<PlanAsset | null>(null);
  const editing = draft !== null;
  return (
    <article
      draggable={!locked && !editing}
      onDragStart={onDragStart}
      onDragOver={(event) => event.preventDefault()}
      onDrop={onDrop}
      onDragEnd={onDragEnd}
      className={`rounded-xl border border-stone-200/70 bg-white p-5 text-sm shadow-sm ${dragging ? "opacity-40" : ""} ${locked ? "" : "cursor-grab"}`}
    >
      <header className="flex items-start justify-between gap-2">
        <div>
          <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-stone-400">
            {number}. {TYPE_LABELS[asset.type]}
          </p>
          {editing ? (
            <input value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} className="mt-0.5 w-full rounded-lg border border-stone-200 px-1 font-medium" />
          ) : (
            <h3 className="font-medium">{asset.title}</h3>
          )}
        </div>
        {!locked && (
          <div className="flex shrink-0 gap-2 text-xs">
            {editing ? (
              <>
                <button onClick={() => { onSave(draft); setDraft(null); }} disabled={busy} className="text-violet-700 underline">Save</button>
                <button onClick={() => setDraft(null)} className="text-stone-500 underline">Cancel</button>
              </>
            ) : (
              <>
                <button onClick={() => setDraft(asset)} className="text-stone-500 underline">Edit</button>
                <button onClick={onRemove} disabled={busy} title="Remove from the plan" className="text-stone-400 hover:text-red-600">✕</button>
              </>
            )}
          </div>
        )}
      </header>
      <dl className="mt-3 space-y-2">
        {FIELDS.map(([key, label]) =>
          editing ? (
            <label key={key} className="block">
              <span className="text-xs text-stone-400">{label}</span>
              <input value={draft[key] ?? ""} onChange={(e) => setDraft({ ...draft, [key]: e.target.value })} className="block w-full rounded-lg border border-stone-200 px-1" />
            </label>
          ) : (
            asset[key] && (
              <div key={key} className="flex gap-2">
                <dt className="w-24 shrink-0 text-xs text-stone-400">{label}</dt>
                <dd className="text-stone-700">{asset[key]}</dd>
              </div>
            )
          ),
        )}
      </dl>
      {children}
    </article>
  );
}

/** The same search however it is spaced or capitalised, as the server compares them. */
function searchKey(query: string): string {
  return query.toLowerCase().split(/\s+/).filter(Boolean).join(" ");
}

type ResearchProps = {
  query: string;
  failed: boolean;
  retrying: boolean;
  onRetry: () => void;
  findings: Finding[];
  removed: Finding[];
  locked: boolean;
  busy: boolean;
  searching: string | null;
  onRemove: (id: string) => void;
  onBetter: (id: string) => void;
  onBringBack: (id: string) => void;
};

/** Web findings for one asset, each with its source and date. Removing one keeps it out of the writing. */
function Research({ query, failed, retrying, onRetry, findings, removed, locked, busy, searching, onRemove, onBetter, onBringBack }: ResearchProps) {
  if (!query && findings.length === 0 && removed.length === 0) return null;
  return (
    <div className="mt-4 rounded-lg bg-sky-50/70 px-4 py-3">
      <p className="text-xs text-sky-900">
        <span className="font-medium">Web research</span>
        {query && <> · “{query}”</>}
      </p>
      {failed ? (
        <p className="mt-1 text-xs text-red-700">
          The search failed, so this asset has no research yet.
          {!locked && (
            <button onClick={onRetry} disabled={retrying} className="ml-2 font-medium underline hover:text-red-900">
              {retrying ? "Searching…" : "Try again"}
            </button>
          )}
        </p>
      ) : findings.length === 0 && <p className="mt-1 text-xs text-stone-500">No findings kept for this asset.</p>}
      <ul className="mt-2 space-y-2.5">
        {findings.map((f) => (
          <li key={f.id} className="text-xs leading-relaxed">
            <p className="text-stone-800">{f.finding}</p>
            <p className="text-stone-500">
              <a href={f.url} target="_blank" rel="noreferrer" className="underline hover:text-stone-800">{domainOf(f.url)}</a>
              {" · "}{f.date}
              {searchKey(f.query) !== searchKey(query) && <>{" · "}found for “{f.query}”</>}
              {!locked && (
                <>
                  {" · "}
                  <button onClick={() => onBetter(f.id)} disabled={busy} className="underline hover:text-stone-800">
                    {searching === f.id ? "Searching…" : "Find a better source"}
                  </button>
                  {" · "}
                  <button onClick={() => onRemove(f.id)} disabled={busy} className="underline hover:text-red-700">Remove</button>
                </>
              )}
            </p>
          </li>
        ))}
      </ul>
      {removed.length > 0 && (
        <ul className="mt-2 space-y-1 border-t border-sky-100 pt-2">
          {removed.map((f) => (
            <li key={f.id} className="text-xs text-stone-400">
              <span className="line-through">{f.finding}</span>
              {!locked && (
                <button onClick={() => onBringBack(f.id)} disabled={busy} className="ml-2 text-stone-600 underline hover:text-stone-900">
                  Bring back
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Box({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-stone-200/70 bg-white p-5 text-sm shadow-sm">
      <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-stone-400">{title}</p>
      <ul className="mt-2 list-disc space-y-1 pl-4 text-stone-700">{children}</ul>
    </section>
  );
}
