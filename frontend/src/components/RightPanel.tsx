import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Asset } from "../api/types";
import { AssetView } from "./assets/AssetView";
import { TYPE_LABELS } from "./assets/labels";
import { CostPanel } from "./CostPanel";
import { PlanPanel } from "./plan/PlanPanel";

type Tab = { kind: "plan" } | { kind: "asset"; id: number } | { kind: "costs" };

const STATE_DOT: Record<Asset["state"], string> = {
  waiting: "bg-stone-300", writing: "bg-sky-500 animate-pulse", checking: "bg-amber-400 animate-pulse",
  done: "bg-emerald-500", failed: "bg-red-500",
};

/** Next to the chat: the plan, then each finished asset as it would really look, and the costs. */
export function RightPanel({ chatId, onViewPrompt }: { chatId: number | null; onViewPrompt: (callId: number) => void }) {
  const chat = useQuery({ queryKey: ["chat", chatId], queryFn: () => api.getChat(chatId!), enabled: chatId !== null });
  const campaign = chat.data?.campaign;
  const writing = campaign?.stage === "writing" || campaign?.stage === "approved";
  const assets = useQuery({
    queryKey: ["assets", chatId],
    queryFn: () => api.listAssets(chatId!),
    enabled: chatId !== null && Boolean(campaign?.approved_at),
    refetchInterval: writing ? 1500 : false,
  });
  const brands = useQuery({ queryKey: ["brands"], queryFn: api.listBrands });
  const brandName = brands.data?.find((b) => b.id === campaign?.brand_id)?.name ?? "";
  const [tab, setTab] = useState<Tab>({ kind: "plan" });
  const list = assets.data ?? [];

  useEffect(() => setTab({ kind: "plan" }), [chatId]);
  useEffect(() => {
    if (list.length > 0 && tab.kind === "plan" && campaign?.approved_at) setTab({ kind: "asset", id: list[0].id });
    // only when the assets first appear
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [list.length > 0]);

  const selected = tab.kind === "asset" ? list.find((a) => a.id === tab.id) : undefined;

  return (
    <section className="flex w-[48%] shrink-0 flex-col border-l border-stone-100 bg-stone-50">
      {campaign && (campaign.plan || chatId) && (
        <nav className="flex shrink-0 gap-1.5 overflow-x-auto border-b border-stone-100 bg-white px-5 py-3 text-xs">
          {campaign.plan && <TabButton active={tab.kind === "plan"} onClick={() => setTab({ kind: "plan" })}>Plan</TabButton>}
          {list.map((asset) => (
            <TabButton key={asset.id} active={tab.kind === "asset" && tab.id === asset.id} onClick={() => setTab({ kind: "asset", id: asset.id })}>
              <span className={`mr-1.5 inline-block h-2 w-2 rounded-full ${STATE_DOT[asset.state]}`} />
              {asset.position + 1}. {TYPE_LABELS[asset.type]}
              {asset.warnings.length > 0 && asset.state === "done" && <span className="ml-1 text-amber-600">⚠</span>}
            </TabButton>
          ))}
          <TabButton active={tab.kind === "costs"} onClick={() => setTab({ kind: "costs" })}>Costs</TabButton>
        </nav>
      )}
      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
        {tab.kind === "costs" && chatId !== null && campaign ? (
          <CostPanel chatId={chatId} brandId={campaign.brand_id} />
        ) : selected ? (
          <AssetView key={selected.id} chatId={chatId!} asset={selected} brandName={brandName} onViewPrompt={onViewPrompt} />
        ) : campaign?.plan ? (
          <PlanPanel chatId={chatId!} campaign={campaign} />
        ) : (
          <div className="flex flex-1 items-center justify-center p-8">
            <p className="max-w-xs text-center text-sm text-stone-500">
              {campaign?.stage === "asking"
                ? "The plan appears here once the questions are answered."
                : "The campaign plan and the finished assets will show here."}
            </p>
          </div>
        )}
      </div>
    </section>
  );
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button onClick={onClick}
      className={`flex shrink-0 items-center whitespace-nowrap rounded-full px-3.5 py-1.5 ${active ? "bg-brand-soft font-medium text-violet-900" : "text-stone-500 hover:bg-stone-100 hover:text-stone-800"}`}>
      {children}
    </button>
  );
}
