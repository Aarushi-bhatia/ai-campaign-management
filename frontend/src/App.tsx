import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api } from "./api/client";
import type { BrandSummary } from "./api/types";
import { AddBrandPage } from "./components/AddBrandPage";
import { BrandPage } from "./components/BrandPage";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { MemoryPage } from "./components/MemoryPage";
import { ChatPanel } from "./components/ChatPanel";
import { PromptViewer } from "./components/PromptViewer";
import { RightPanel } from "./components/RightPanel";
import { Sidebar } from "./components/Sidebar";
import { TopBar } from "./components/TopBar";
import type { View } from "./view";

export function App() {
  const [view, setView] = useState<View>({ kind: "chat", chatId: null });
  const [viewedCallId, setViewedCallId] = useState<number | null>(null);
  const [brandId, setBrandId] = useBrandChoice();
  // Polled while a brand is being read, so the switcher and New campaign know as soon as it is ready.
  const brands = useQuery({
    queryKey: ["brands"],
    queryFn: api.listBrands,
    refetchInterval: (query) => (query.state.data?.some((b) => b.status === "reading") ? 3000 : false),
  });
  const brand = defaultBrand(brands.data ?? [], brandId);
  useOpenNewBrandOnce(setView);

  const chatId = view.kind === "chat" ? view.chatId : null;

  return (
    <div className="flex h-full">
      <Sidebar view={view} onNavigate={setView} brands={brands.data} brand={brand} onSelectBrand={setBrandId} />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar chatId={chatId} />
        <ErrorBoundary key={view.kind}>
          <div className="flex min-h-0 flex-1">
          {view.kind === "chat" && (
            <>
              <ChatPanel
                chatId={chatId}
                brand={brand}
                onChatCreated={(id) => setView({ kind: "chat", chatId: id })}
                onViewPrompt={setViewedCallId}
              />
              <RightPanel chatId={chatId} onViewPrompt={setViewedCallId} />
            </>
          )}
          {view.kind === "brand" && (
            <BrandPage
              key={view.brandId}
              brandId={view.brandId}
              onViewPrompt={setViewedCallId}
              onUpdate={(brand) => setView({ kind: "add-brand", updating: { id: brand.id, name: brand.name } })}
            />
          )}
          {view.kind === "memory" && (
            <MemoryPage key={view.brandId} brandId={view.brandId} onOpenChat={(id) => setView({ kind: "chat", chatId: id })} />
          )}
          {view.kind === "add-brand" && (
            <AddBrandPage
              key={view.updating?.id ?? "new"}
              updating={view.updating}
              onAdded={(id) => setView({ kind: "brand", brandId: id })}
            />
          )}
          </div>
        </ErrorBoundary>
      </div>
      {viewedCallId !== null && (
        <ErrorBoundary onClose={() => setViewedCallId(null)}>
          <PromptViewer callId={viewedCallId} onClose={() => setViewedCallId(null)} />
        </ErrorBoundary>
      )}
    </div>
  );
}

/** The brand new campaigns use: the one chosen in the sidebar's switcher; until one is chosen (or if it was
 * deleted), the newest brand that has been read, else the newest. The list comes newest first. */
function defaultBrand(brands: BrandSummary[], chosen: number | null): BrandSummary | undefined {
  return brands.find((b) => b.id === chosen) ?? brands.find((b) => b.status === "ready") ?? brands[0];
}

/** The brand chosen in the sidebar, kept between visits in this browser. Storage can be unavailable; then it
 * falls back to the newest brand. */
function useBrandChoice(): [number | null, (id: number) => void] {
  const [brandId, setBrandId] = useState<number | null>(() => {
    try {
      const saved = window.localStorage.getItem("brandId");
      return saved ? Number(saved) : null;
    } catch {
      return null;
    }
  });
  const choose = (id: number) => {
    setBrandId(id);
    try {
      window.localStorage.setItem("brandId", String(id));
    } catch {
      // not saved; the choice still holds for this visit
    }
  };
  return [brandId, choose];
}

/** A brand nobody has looked at yet opens its Brand page by itself, once, so its details get reviewed. */
function useOpenNewBrandOnce(setView: (view: View) => void) {
  const brands = useQuery({ queryKey: ["brands"], queryFn: api.listBrands });
  const opened = useRef(false);
  const unreviewed = brands.data?.find((brand) => !brand.reviewed);

  useEffect(() => {
    if (unreviewed && !opened.current) {
      opened.current = true;
      setView({ kind: "brand", brandId: unreviewed.id });
    }
  }, [unreviewed, setView]);
}
