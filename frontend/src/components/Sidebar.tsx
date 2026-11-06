import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { BrandSummary } from "../api/types";
import type { View } from "../view";

type Props = {
  view: View;
  onNavigate: (view: View) => void;
  /** Undefined while the list is loading. */
  brands: BrandSummary[] | undefined;
  /** The brand new campaigns use: the one chosen at the bottom of the sidebar. */
  brand: BrandSummary | undefined;
  onSelectBrand: (brandId: number) => void;
};

export function Sidebar({ view, onNavigate, brands, brand, onSelectBrand }: Props) {
  const queryClient = useQueryClient();
  const chats = useQuery({ queryKey: ["chats"], queryFn: api.listChats });
  const createChat = useMutation({
    mutationFn: () => api.createChat(brand?.id),
    onSuccess: (chat) => {
      queryClient.invalidateQueries({ queryKey: ["chats"] });
      onNavigate({ kind: "chat", chatId: chat.id });
    },
  });

  // Only the chosen brand's chats are listed. A chat with no brand (only possible when no brand exists) is never
  // hidden.
  const shown = chats.data?.filter((chat) => chat.brand_id === null || chat.brand_id === brand?.id);

  // Switching brands while its Brand page or Memory is open shows the same page for the newly chosen brand. An
  // open chat of the other brand leaves the list, so it makes way for a new campaign.
  const choose = (id: number) => {
    onSelectBrand(id);
    if (view.kind === "brand" || view.kind === "memory") onNavigate({ kind: view.kind, brandId: id });
    if (view.kind === "chat" && view.chatId !== null) {
      const open = chats.data?.find((chat) => chat.id === view.chatId);
      if (open && open.brand_id !== null && open.brand_id !== id) onNavigate({ kind: "chat", chatId: null });
    }
  };

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-stone-100 bg-stone-50 text-stone-800">
      <div className="space-y-2 px-4 pb-4 pt-5">
        <button
          onClick={() => createChat.mutate()}
          disabled={createChat.isPending || brand?.status !== "ready"}
          className="w-full rounded-xl bg-violet-700 px-3 py-2 text-sm font-medium text-white shadow-sm hover:bg-violet-800 disabled:opacity-50"
        >
          New campaign
        </button>
        {brand && brand.status !== "ready" && <p className="text-xs text-stone-500">{notReady(brand)}</p>}
        {brands?.length === 0 && <p className="text-xs text-stone-500">Add a brand first, at the bottom left.</p>}
        {createChat.error && <p className="text-xs text-red-600">{createChat.error.message}</p>}
      </div>

      {brand && (
        <div className="space-y-1 px-3 pb-6">
          <p className="truncate px-3 pb-1.5 text-[11px] font-medium uppercase tracking-[0.08em] text-stone-400">{brand.name}</p>
          <NavButton active={view.kind === "brand" && view.brandId === brand.id}
            onClick={() => onNavigate({ kind: "brand", brandId: brand.id })}>
            <span>Brand page</span>
            {brand.status === "reading" && <span className="rounded-full bg-brand-soft px-2 text-[11px] text-violet-800">reading…</span>}
          </NavButton>
          <NavButton active={view.kind === "memory" && view.brandId === brand.id}
            onClick={() => onNavigate({ kind: "memory", brandId: brand.id })}>
            <span>Memory</span>
          </NavButton>
        </div>
      )}

      <nav className="min-h-0 flex-1 space-y-1 overflow-y-auto px-3 pb-6">
        <p className="px-3 pb-1.5 text-[11px] font-medium uppercase tracking-[0.08em] text-stone-400">Chats</p>
        {shown?.length === 0 && (
          <p className="px-3 py-2 text-sm text-stone-400">{brand ? `No chats for ${brand.name} yet.` : "No chats yet."}</p>
        )}
        {shown?.map((chat) => (
          <NavButton
            key={chat.id}
            active={view.kind === "chat" && view.chatId === chat.id}
            onClick={() => onNavigate({ kind: "chat", chatId: chat.id })}
          >
            <span className="truncate">{chat.title}</span>
          </NavButton>
        ))}
      </nav>

      <BrandSwitcher
        brands={brands}
        brand={brand}
        onSelect={choose}
        onAdd={() => onNavigate({ kind: "add-brand" })}
      />
    </aside>
  );
}

/** Pinned to the bottom of the sidebar: which brand new campaigns use. The card opens a list of every brand
 * just above it, ending with "Add a brand"; Escape or a click outside closes it. */
function BrandSwitcher({ brands, brand, onSelect, onAdd }: {
  brands: BrandSummary[] | undefined;
  brand: BrandSummary | undefined;
  onSelect: (brandId: number) => void;
  onAdd: () => void;
}) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const outside = (event: MouseEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  return (
    <div ref={box} className="shrink-0 border-t border-stone-200/70 bg-stone-50 px-3 pb-4 pt-3">
      <p className="px-1 pb-1.5 text-[11px] font-medium uppercase tracking-[0.08em] text-stone-400">Brand</p>

      <div className="relative">
        {open && brands && (
          <div role="listbox" aria-label="Brands"
            className="absolute inset-x-0 bottom-full z-20 mb-1 overflow-hidden rounded-xl border border-stone-200 bg-white shadow-lg">
            <div className="max-h-72 overflow-y-auto p-1">
              {brands.map((b) => (
                <button key={b.id} role="option" aria-selected={b.id === brand?.id}
                  onClick={() => { onSelect(b.id); setOpen(false); }}
                  className={`flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left ${
                    b.id === brand?.id ? "bg-brand-soft" : "hover:bg-stone-50"}`}>
                  <BrandMark name={b.name} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-stone-800">{b.name}</span>
                    <StatusLine brand={b} />
                  </span>
                  {b.id === brand?.id && <Check />}
                </button>
              ))}
            </div>
            <button onClick={() => { setOpen(false); onAdd(); }}
              className="flex w-full items-center gap-2.5 border-t border-stone-100 px-3 py-2.5 text-left text-sm text-stone-600 hover:bg-stone-50 hover:text-stone-900">
              <span className="flex h-7 w-7 items-center justify-center rounded-md border border-dashed border-stone-300 text-stone-500"><Plus /></span>
              Add a brand
            </button>
          </div>
        )}

        {brands === undefined ? (
          <div className="h-12" />
        ) : brand ? (
          <button onClick={() => setOpen(!open)} aria-haspopup="listbox" aria-expanded={open}
            aria-label={`Brand: ${brand.name}. Change brand`} title="New campaigns use this brand"
            className={`flex w-full items-center gap-2.5 rounded-xl border bg-white px-2.5 py-2 text-left shadow-sm ${
              open ? "border-violet-300" : "border-stone-200 hover:border-stone-300"}`}>
            <BrandMark name={brand.name} />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium text-stone-800">{brand.name}</span>
              <StatusLine brand={brand} />
            </span>
            <Chevrons />
          </button>
        ) : (
          <button onClick={onAdd}
            className="flex w-full items-center gap-2.5 rounded-xl border border-dashed border-stone-300 bg-white px-2.5 py-2 text-left text-sm text-stone-600 hover:bg-stone-100 hover:text-stone-900">
            <span className="flex h-7 w-7 items-center justify-center rounded-md border border-dashed border-stone-300 text-stone-500"><Plus /></span>
            Add a brand
          </button>
        )}
      </div>
    </div>
  );
}

/** The brand's first letter, as a small square. */
function BrandMark({ name }: { name: string }) {
  return (
    <span aria-hidden className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-violet-100 text-xs font-semibold text-violet-800">
      {name.trim().charAt(0).toUpperCase() || "?"}
    </span>
  );
}

/** A coloured dot and a few words: ready, being read, or failed. */
function StatusLine({ brand }: { brand: BrandSummary }) {
  const [dot, text] = brand.status === "ready"
    ? ["bg-emerald-500", "Ready"]
    : brand.status === "reading"
      ? ["animate-pulse bg-amber-400", brand.documents_total > 0 && brand.documents_done < brand.documents_total
        ? `Reading ${brand.documents_done} of ${brand.documents_total}…` : "Being read…"]
      : ["bg-red-500", "Couldn't be read"];
  return (
    <span className="flex items-center gap-1.5 text-[11px] text-stone-500">
      <span aria-hidden className={`h-1.5 w-1.5 shrink-0 rounded-full ${dot}`} />
      <span className="truncate">{text}</span>
    </span>
  );
}

function Plus() {
  return (
    <svg aria-hidden viewBox="0 0 16 16" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round">
      <path d="M8 3v10M3 8h10" />
    </svg>
  );
}

function Check() {
  return (
    <svg aria-hidden viewBox="0 0 16 16" className="h-4 w-4 shrink-0 text-violet-700" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3.5 8.5l3 3 6-7" />
    </svg>
  );
}

function Chevrons() {
  return (
    <svg aria-hidden viewBox="0 0 16 16" className="h-4 w-4 shrink-0 text-stone-400" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 6l3-3 3 3M5 10l3 3 3-3" />
    </svg>
  );
}

function notReady(brand: BrandSummary): string {
  return brand.status === "reading"
    ? `${brand.name} is still being read. New campaigns can start once it's ready.`
    : `${brand.name} couldn't be read. Open its Brand page to try again, or pick another brand below.`;
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
