import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { View } from "../view";

type Props = {
  view: View;
  onNavigate: (view: View) => void;
  brandId: number | null;
  onSelectBrand: (brandId: number) => void;
};

export function Sidebar({ view, onNavigate, brandId, onSelectBrand }: Props) {
  const queryClient = useQueryClient();
  const chats = useQuery({ queryKey: ["chats"], queryFn: api.listChats });
  const brands = useQuery({ queryKey: ["brands"], queryFn: api.listBrands });
  const createChat = useMutation({
    mutationFn: () => api.createChat(brand?.id),
    onSuccess: (chat) => {
      queryClient.invalidateQueries({ queryKey: ["chats"] });
      onNavigate({ kind: "chat", chatId: chat.id });
    },
  });

  // New campaigns use the brand chosen here; until one is chosen, the newest brand that has been read.
  const brand = brands.data?.find((b) => b.id === brandId)
    ?? brands.data?.find((b) => b.status === "ready")
    ?? brands.data?.[0];

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-stone-100 bg-stone-50 text-stone-800">
      <div className="space-y-2 px-4 pb-4 pt-5">
        <button
          onClick={() => createChat.mutate()}
          disabled={createChat.isPending}
          className="w-full rounded-xl bg-violet-700 px-3 py-2 text-sm font-medium text-white shadow-sm hover:bg-violet-800 disabled:opacity-50"
        >
          New campaign
        </button>
        {createChat.error && <p className="text-xs text-red-600">{createChat.error.message}</p>}
      </div>

      <div className="space-y-1 px-3 pb-6">
        <p className="px-3 pb-1.5 text-[11px] font-medium uppercase tracking-[0.08em] text-stone-400">
          {(brands.data?.length ?? 0) > 1 ? "Brands" : "Brand"}
        </p>
        {brands.data?.map((b) => (
          <NavButton key={b.id} active={view.kind === "brand" && view.brandId === b.id}
            onClick={() => { onSelectBrand(b.id); onNavigate({ kind: "brand", brandId: b.id }); }}>
            <span className="truncate">{b.name}</span>
            {b.status === "reading" ? <span className="rounded-full bg-brand-soft px-2 text-[11px] text-violet-800">reading…</span>
              : (brands.data?.length ?? 0) > 1 && b.id === brand?.id && <span className="text-[11px] text-violet-700">new campaigns</span>}
          </NavButton>
        ))}
        {brand && (
          <NavButton active={view.kind === "memory"} onClick={() => onNavigate({ kind: "memory", brandId: brand.id })}>
            <span>Memory</span>
          </NavButton>
        )}
        <NavButton active={view.kind === "add-brand"} onClick={() => onNavigate({ kind: "add-brand" })}>
          <span className="text-stone-600">+ Add brand</span>
        </NavButton>
      </div>

      <nav className="min-h-0 flex-1 space-y-1 overflow-y-auto px-3 pb-6">
        <p className="px-3 pb-1.5 text-[11px] font-medium uppercase tracking-[0.08em] text-stone-400">Chats</p>
        {chats.data?.length === 0 && <p className="px-3 py-2 text-sm text-stone-400">No chats yet.</p>}
        {chats.data?.map((chat) => (
          <NavButton
            key={chat.id}
            active={view.kind === "chat" && view.chatId === chat.id}
            onClick={() => onNavigate({ kind: "chat", chatId: chat.id })}
          >
            <span className="truncate">{chat.title}</span>
          </NavButton>
        ))}
      </nav>
    </aside>
  );
}

function NavButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`flex w-full items-center justify-between gap-2 rounded-full px-3.5 py-2.5 text-left text-sm leading-snug ${
        active ? "bg-brand-soft font-medium text-violet-900" : "text-stone-600 hover:bg-stone-100 hover:text-stone-900"
      }`}
    >
      {children}
    </button>
  );
}
