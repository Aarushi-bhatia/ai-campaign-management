import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { formatCost } from "../format";

export function TopBar({ chatId }: { chatId: number | null }) {
  const calls = useQuery({
    queryKey: ["calls", chatId],
    queryFn: () => api.listCalls(chatId!),
    enabled: chatId !== null,
  });
  const total = calls.data?.reduce((sum, call) => sum + (call.cost_usd ?? 0), 0) ?? 0;

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-stone-100 bg-white/80 px-6 backdrop-blur">
      <span className="text-sm font-medium text-stone-900">Campaign agent</span>
      {chatId !== null && (
        <span className="rounded-full bg-brand-soft px-3 py-0.5 text-sm text-violet-800">
          Campaign cost: <span className="font-medium text-violet-950">{formatCost(total)}</span>
        </span>
      )}
    </header>
  );
}
