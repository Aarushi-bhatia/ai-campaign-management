import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../../api/client";
import type { Asset, AssetVersion } from "../../api/types";
import { formatCost } from "../../format";
import { Compare } from "./Compare";
import { cleaned, FieldsEditor } from "./FieldsEditor";
import { TYPE_LABELS } from "./labels";
import { copyText, Preview } from "./Previews";

type Props = {
  chatId: number;
  asset: Asset;
  brandName: string;
  onViewPrompt: (callId: number) => void;
};

const STATE_TEXT: Record<Asset["state"], string> = {
  waiting: "Waiting to be written…",
  writing: "Writing: looking up the brand's rules and facts, choosing an image…",
  checking: "Checking: banned words, names, lengths, claims and tone…",
  done: "",
  failed: "Writing failed.",
};

/** One asset: its preview, what was checked and fixed, and the tools to change it. */
export function AssetView({ chatId, asset, brandName, onViewPrompt }: Props) {
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<"preview" | "edit" | "compare">("preview");
  const [draft, setDraft] = useState<Record<string, any> | null>(null);
  const [draftBase, setDraftBase] = useState(0);
  const [copied, setCopied] = useState(false);
  const ready = asset.state === "done" && asset.content;

  const versions = useQuery({
    queryKey: ["versions", chatId, asset.id, asset.version],
    queryFn: () => api.assetVersions(chatId, asset.id),
    enabled: Boolean(ready),
  });
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["assets", chatId] });
    queryClient.invalidateQueries({ queryKey: ["chat", chatId] });
    queryClient.invalidateQueries({ queryKey: ["calls", chatId] });
  };
  // Each change says which version it was made on; if the asset moved on meanwhile (say a chat edit landed),
  // the server refuses it, and the refresh shows the newer version.
  const save = useMutation({
    mutationFn: (content: Record<string, unknown>) => api.handEdit(chatId, asset.id, content, draftBase),
    onSuccess: () => { setMode("preview"); setDraft(null); refresh(); },
    onError: refresh,
  });
  const undo = useMutation({ mutationFn: () => api.undoAsset(chatId, asset.id, asset.version), onSettled: refresh });
  const check = useMutation({ mutationFn: () => api.checkAgain(chatId, asset.id), onSuccess: refresh });
  const retry = useMutation({ mutationFn: () => api.writeAgain(chatId), onSuccess: refresh });
  const restore = useMutation({
    mutationFn: (number: number) => api.restoreVersion(chatId, asset.id, number, asset.version),
    onSettled: refresh,
  });
  const error = save.error ?? undo.error ?? check.error ?? retry.error ?? restore.error;

  if (!ready) {
    return (
      <div className="space-y-5 p-6">
        <Header asset={asset} />
        <div className={`rounded-xl border p-6 text-sm ${asset.state === "failed" ? "border-red-200 bg-red-50 text-red-800" : "animate-pulse border-stone-200 bg-white text-stone-500"}`}>
          {STATE_TEXT[asset.state]}
          {asset.error && <p className="mt-2 text-xs">{asset.error}</p>}
          {asset.state === "failed" && (
            <button onClick={() => retry.mutate()} disabled={retry.isPending} className="mt-3 block rounded-lg bg-red-700 px-3 py-1.5 text-xs font-medium text-white">
              Write again
            </button>
          )}
        </div>
      </div>
    );
  }

  const list = versions.data ?? [];
  const current = list.find((v) => v.number === asset.version);
  const previous = previousOf(list, current);

  return (
    <div className="space-y-5 p-6">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <Header asset={asset} />
        <div className="flex flex-wrap gap-2 text-xs">
          {mode === "edit" ? (
            <>
              <Button primary onClick={() => save.mutate(cleaned(draft!))} disabled={save.isPending}>{save.isPending ? "Saving…" : "Save ($0)"}</Button>
              <Button onClick={() => { setMode("preview"); setDraft(null); }}>Cancel</Button>
            </>
          ) : (
            <>
              <Button onClick={() => { setDraft(structuredClone(asset.content)); setDraftBase(asset.version); setMode("edit"); }}>Edit</Button>
              <Button onClick={() => undo.mutate()} disabled={undo.isPending || asset.version <= 1}>Undo</Button>
              <Button onClick={() => setMode(mode === "compare" ? "preview" : "compare")} disabled={!previous}>
                {mode === "compare" ? "Preview" : "Compare"}
              </Button>
              <Button onClick={() => { navigator.clipboard.writeText(copyText(asset)); setCopied(true); setTimeout(() => setCopied(false), 1500); }}>
                {copied ? "Copied" : "Copy"}
              </Button>
              <Button onClick={() => check.mutate()} disabled={check.isPending}>{check.isPending ? "Checking…" : "Check again"}</Button>
              {asset.call_id && <Button onClick={() => onViewPrompt(asset.call_id!)}>View prompt</Button>}
            </>
          )}
        </div>
      </div>
      {error && <p className="text-sm text-red-600">{error.message}</p>}
      <CheckNotes asset={asset} />
      {mode === "edit" && draft && (
        <div className="rounded-xl border border-stone-200/70 bg-white p-5 shadow-sm">
          <p className="mb-3 text-xs text-stone-500">Typing here costs nothing. Saving runs the free checks (banned words, names, lengths, links); press Check again afterwards for the full check.</p>
          <FieldsEditor value={draft} onChange={setDraft} />
        </div>
      )}
      {mode === "compare" && previous && current && (
        <div>
          <p className="mb-2 text-xs text-stone-500">Version {previous.number} ({previous.reason}) → version {current.number} ({current.reason})</p>
          <Compare before={withImage(copyText({ ...asset, content: previous.content }), previous.image)}
            after={withImage(copyText(asset), current.image)} />
        </div>
      )}
      {mode === "preview" && <Preview asset={asset} brandName={brandName} />}
      {asset.image?.path && mode === "preview" && (
        <p className="text-xs text-stone-500">Image: {asset.image.path}. {asset.image.why} Alt text: “{asset.image.alt_text}”</p>
      )}
      <Versions list={list} current={asset.version} busy={restore.isPending || mode === "edit"} onRestore={(n) => restore.mutate(n)} />
    </div>
  );
}

/** The image is part of what changed between versions (an undo can bring an old one back), so Compare shows it. */
function withImage(text: string, image: AssetVersion["image"]): string {
  return `${text}\n\nImage: ${image?.path ?? "none"}`;
}

function previousOf(list: AssetVersion[], current: AssetVersion | undefined): AssetVersion | undefined {
  if (!current) return undefined;
  return [...list].reverse().find((v) => v.number < current.number && (JSON.stringify(v.content) !== JSON.stringify(current.content) || v.image?.path !== current.image?.path));
}

function Header({ asset }: { asset: Asset }) {
  return (
    <div>
      <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-stone-400">
        {asset.position + 1}. {TYPE_LABELS[asset.type]}{asset.version > 0 && ` · version ${asset.version}`}
      </p>
      <h2 className="font-medium">{asset.title}</h2>
      {asset.draft_for && (
        <p className="mt-1.5 inline-block rounded-full bg-amber-50 px-3 py-0.5 text-xs font-medium text-amber-800">
          Optional draft for {asset.draft_for}: not approved or scheduled
        </p>
      )}
    </div>
  );
}

const KEPT = "Kept as written: ";

function CheckNotes({ asset }: { asset: Asset }) {
  const fixed = asset.fixed.filter((line) => !line.startsWith(KEPT));
  const kept = asset.fixed.filter((line) => line.startsWith(KEPT)).map((line) => line.slice(KEPT.length));
  return (
    <div className="space-y-2.5 text-xs leading-relaxed">
      {asset.looked_up.length > 0 && <p className="text-stone-500">Looked up: {asset.looked_up.join(", ")}.</p>}
      {fixed.length > 0 && (
        <div className="rounded-lg border border-emerald-100 bg-emerald-50 px-4 py-3 text-emerald-900">
          <span className="font-medium">Fixed automatically:</span> {fixed.join(" ")}
        </div>
      )}
      {kept.length > 0 && (
        <p className="text-stone-500"><span className="font-medium">Flagged but kept, as the brief or brand supports it:</span> {kept.join(" ")}</p>
      )}
      {asset.warnings.length > 0 ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-amber-900">
          <p className="font-medium">Still to look at</p>
          <ul className="mt-1.5 list-disc space-y-1 pl-4">
            {asset.warnings.map((w, i) => (
              <li key={i}><span className="font-medium">{w.check}:</span> {w.problem}{w.quote && <q className="ml-1 text-amber-700">{w.quote}</q>}</li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="text-emerald-800">✓ Passed the checks.</p>
      )}
    </div>
  );
}

type VersionsProps = { list: AssetVersion[]; current: number; busy: boolean; onRestore: (number: number) => void };

/** Every saved version, newest first. Any of them can be brought back, free, as a new version. */
function Versions({ list, current, busy, onRestore }: VersionsProps) {
  if (list.length === 0) return null;
  return (
    <details className="rounded-xl border border-stone-200/70 bg-white px-4 py-3 text-xs shadow-sm">
      <summary className="cursor-pointer font-medium text-stone-600">{list.length} version{list.length > 1 ? "s" : ""}</summary>
      <ol className="mt-3 space-y-1.5">
        {[...list].reverse().map((v) => (
          <li key={v.id} className={`flex items-center justify-between gap-3 ${v.number === current ? "font-medium" : "text-stone-600"}`}>
            <span>v{v.number} · {v.reason}{v.note && `: ${v.note}`}</span>
            <span className="flex shrink-0 items-center gap-3">
              {v.number === current ? (
                <span className="rounded-full bg-brand-soft px-2 py-0.5 text-[11px] text-violet-800">showing</span>
              ) : (
                <button onClick={() => onRestore(v.number)} disabled={busy} className="text-violet-700 underline hover:text-violet-900 disabled:opacity-40">
                  Restore
                </button>
              )}
              <span className="w-12 text-right text-stone-400">{formatCost(v.cost_usd)}</span>
            </span>
          </li>
        ))}
      </ol>
    </details>
  );
}

function Button({ children, onClick, disabled, primary }: { children: React.ReactNode; onClick: () => void; disabled?: boolean; primary?: boolean }) {
  return (
    <button onClick={onClick} disabled={disabled}
      className={`rounded-lg border px-3 py-1.5 disabled:opacity-40 ${primary ? "border-violet-700 bg-violet-700 text-white" : "border-stone-200/70 bg-white hover:bg-stone-100"}`}>
      {children}
    </button>
  );
}
