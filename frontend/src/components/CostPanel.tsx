import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { CostTotals } from "../api/types";
import { formatCost, formatTokens } from "../format";

/** What this campaign cost, per stage, per asset and per edit, with how much came from the cache. */
export function CostPanel({ chatId, brandId }: { chatId: number; brandId: number }) {
  const report = useQuery({ queryKey: ["costs", chatId], queryFn: () => api.costs(chatId), refetchInterval: 5000 });
  const brand = useQuery({ queryKey: ["brand", brandId], queryFn: () => api.getBrand(brandId) });
  const data = report.data;
  if (!data) return <p className="p-5 text-sm text-stone-500">Loading costs…</p>;

  return (
    <div className="space-y-7 p-6 text-sm">
      <div>
        <h2 className="font-medium">Campaign cost: {formatCost(data.total.cost_usd)}</h2>
        <p className="mt-1 text-xs text-stone-500">
          {data.total.calls} AI calls · {formatTokens(data.total.tokens_in)} tokens in, {pct(data.total)} from the cache ·{" "}
          {formatTokens(data.total.tokens_out)} out
        </p>
        {brand.data && (
          <p className="mt-1 text-xs text-stone-500">
            Reading the brand (once, shared by every campaign): {formatCost(brand.data.reading_cost.usd)} over {brand.data.reading_cost.calls} calls.
          </p>
        )}
      </div>
      <Table title="By stage" rows={data.stages.map((s) => ({ label: s.stage, ...s }))} />
      {data.assets.length > 0 && <Table title="By asset (writing, image, checks, edits)" rows={data.assets.map((a) => ({ label: a.title, ...a }))} />}
      {data.edits.length > 0 && (
        <section>
          <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.08em] text-stone-400">Edits</p>
          <ul className="space-y-1.5 text-xs">
            {data.edits.map((e) => (
              <li key={`${e.asset_id}-${e.version}`} className="flex justify-between gap-3">
                <span className="truncate">{e.title} · v{e.version} {e.reason}{e.note && `: ${e.note}`}</span>
                <span className="shrink-0">{formatCost(e.cost_usd)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function pct(t: CostTotals) {
  return `${Math.round(t.cache_hit_rate * 100)}%`;
}

function Table({ title, rows }: { title: string; rows: (CostTotals & { label: string })[] }) {
  return (
    <section>
      <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.08em] text-stone-400">{title}</p>
      <table className="w-full text-xs">
        <thead className="text-stone-400">
          <tr><th className="text-left font-normal"></th><th className="text-right font-normal">Calls</th><th className="text-right font-normal">Cached</th><th className="text-right font-normal">Cost</th></tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-stone-100">
              <td className="max-w-48 truncate py-2">{r.label}</td>
              <td className="text-right">{r.calls}</td>
              <td className="text-right">{pct(r)}</td>
              <td className="text-right font-medium">{formatCost(r.cost_usd)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
