import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";
import type { CampaignRecord, MemoryItem } from "../api/types";

type Props = { brandId: number; onOpenChat: (chatId: number) => void };

/** What the agent remembers for this brand. Core memory goes into every request; history only into planning. */
export function MemoryPage({ brandId, onOpenChat }: Props) {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<"core" | "history">("core");
  const [adding, setAdding] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const memory = useQuery({ queryKey: ["memory", brandId], queryFn: () => api.getMemory(brandId) });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["memory", brandId] });
  const add = useMutation({
    mutationFn: (text: string) => api.addMemory(brandId, text, "preference"),
    onSuccess: (item) => {
      setAdding("");
      setNotice(item.replaced ? `That updated “${item.replaced}”.`
        : item.dropped.length ? `Memory was full, so the oldest unpinned item was dropped: ${item.dropped.map((t) => `“${t}”`).join(", ")}.`
        : null);
      refresh();
    },
  });
  const core = memory.data?.core ?? [];
  const history = memory.data?.history ?? [];

  return (
    <div className="min-w-0 flex-1 overflow-y-auto bg-white">
      <div className="mx-auto max-w-3xl p-8">
        <h1 className="text-xl font-medium">Memory</h1>
        <p className="mt-1 text-sm text-stone-600">
          What the agent keeps between campaigns for this brand. New items are saved from your chats, with an Undo note there.
        </p>
        <div className="mt-6 flex gap-1 border-b border-stone-100 text-sm">
          <TabButton active={tab === "core"} onClick={() => setTab("core")}>Core memory ({core.length}/50)</TabButton>
          <TabButton active={tab === "history"} onClick={() => setTab("history")}>Campaign history ({history.length})</TabButton>
        </div>
        {tab === "core" ? (
          <section className="mt-6 space-y-3">
            <p className="text-xs text-stone-500">
              Loaded into every request, so the agent always follows it. When memory is full (50 items), a new item drops
              the oldest unpinned one, and you're told which. Pinned items are never dropped; when all are pinned, nothing
              new is added until you unpin or delete one.
            </p>
            {core.length === 0 && <p className="text-sm text-stone-500">Nothing yet. Corrections and preferences from your chats will show here.</p>}
            {core.map((item) => <CoreItem key={item.id} item={item} onChanged={refresh} onOpenChat={onOpenChat} />)}
            <form className="flex gap-2 pt-2" onSubmit={(e) => { e.preventDefault(); if (adding.trim()) add.mutate(adding.trim()); }}>
              <input value={adding} onChange={(e) => setAdding(e.target.value)} placeholder="Add something to remember, e.g. Keep emails under 150 words."
                className="flex-1 rounded-lg border border-stone-200 px-3 py-1.5 text-sm" />
              <button disabled={!adding.trim() || add.isPending} className="rounded-lg bg-violet-700 px-3 py-1.5 text-sm text-white disabled:opacity-40">Add</button>
            </form>
            {add.error && <p className="text-sm text-red-600">{add.error.message}</p>}
            {notice && <p className="text-sm text-amber-800">{notice}</p>}
          </section>
        ) : (
          <section className="mt-6 space-y-3">
            <p className="text-xs text-stone-500">One record per finished campaign. Only the planning step reads these, so new plans don't repeat recent angles or images.</p>
            {history.length === 0 && <p className="text-sm text-stone-500">No finished campaigns yet.</p>}
            {history.map((record) => <Record key={record.id} record={record} onChanged={refresh} onOpenChat={onOpenChat} />)}
          </section>
        )}
      </div>
    </div>
  );
}

function CoreItem({ item, onChanged, onOpenChat }: { item: MemoryItem; onChanged: () => void; onOpenChat: (id: number) => void }) {
  const [draft, setDraft] = useState<string | null>(null);
  const change = useMutation({ mutationFn: (c: { text?: string; pinned?: boolean }) => api.changeMemory(item.id, c), onSuccess: () => { setDraft(null); onChanged(); } });
  const remove = useMutation({ mutationFn: () => api.deleteMemory(item.id), onSuccess: onChanged });
  const confirmRemove = () => window.confirm(`Delete “${item.text}” from memory? This can't be undone.`) && remove.mutate();
  return (
    <div className="flex items-start gap-3 rounded-xl border border-stone-200/70 bg-white px-5 py-4 text-sm shadow-sm">
      <span className="mt-0.5 rounded bg-violet-50 px-1.5 py-0.5 text-xs text-violet-800">{item.kind}</span>
      <div className="min-w-0 flex-1">
        {draft !== null ? (
          <input autoFocus value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => e.key === "Enter" && change.mutate({ text: draft })}
            className="w-full rounded-lg border border-stone-200 px-2 py-0.5" />
        ) : <p>{item.text}</p>}
        <p className="mt-0.5 text-xs text-stone-400">
          {item.source_chat_id ? <button onClick={() => onOpenChat(item.source_chat_id!)} className="underline">From chat {item.source_chat_id}</button> : "Added by hand"}
          {" · "}{new Date(item.created_at).toLocaleDateString()}
        </p>
      </div>
      <div className="flex shrink-0 gap-2 text-xs">
        {draft !== null ? (
          <>
            <button onClick={() => change.mutate({ text: draft })} className="text-violet-700 underline">Save</button>
            <button onClick={() => setDraft(null)} className="text-stone-500 underline">Cancel</button>
          </>
        ) : (
          <>
            <button onClick={() => change.mutate({ pinned: !item.pinned })} className={item.pinned ? "font-medium text-amber-700" : "text-stone-500 underline"}>
              {item.pinned ? "★ Pinned" : "Pin"}
            </button>
            <button onClick={() => setDraft(item.text)} className="text-stone-500 underline">Edit</button>
            <button onClick={confirmRemove} className="text-stone-400 hover:text-red-600">Delete</button>
          </>
        )}
      </div>
    </div>
  );
}

const RECORD_FIELDS = [["name", "Name"], ["goal", "Goal"], ["audience", "Audience"], ["angle", "Angle"]] as const;

/** A past campaign as the planner reads it. Its name, goal, audience and angle can be corrected. */
function Record({ record, onChanged, onOpenChat }: { record: CampaignRecord; onChanged: () => void; onOpenChat: (id: number) => void }) {
  const [draft, setDraft] = useState<Record<string, string> | null>(null);
  const remove = useMutation({ mutationFn: () => api.deleteRecord(record.id), onSuccess: onChanged });
  const save = useMutation({ mutationFn: () => api.changeRecord(record.id, draft!), onSuccess: () => { setDraft(null); onChanged(); } });
  const confirmRemove = () => window.confirm(`Delete the record of “${record.name}”? Planning won't see it again, and this can't be undone.`)
    && remove.mutate();
  if (draft) {
    return (
      <div className="space-y-2 rounded-xl border border-stone-200/70 bg-white px-5 py-4 text-sm shadow-sm">
        {RECORD_FIELDS.map(([key, label]) => (
          <label key={key} className="block">
            <span className="text-xs text-stone-400">{label}</span>
            <input value={draft[key]} onChange={(e) => setDraft({ ...draft, [key]: e.target.value })}
              className="block w-full rounded-lg border border-stone-200 px-2 py-1" />
          </label>
        ))}
        <div className="flex gap-3 text-xs">
          <button onClick={() => save.mutate()} disabled={save.isPending} className="text-violet-700 underline">Save</button>
          <button onClick={() => setDraft(null)} className="text-stone-500 underline">Cancel</button>
        </div>
        {save.error && <p className="text-red-600">{save.error.message}</p>}
      </div>
    );
  }
  return (
    <div className="rounded-xl border border-stone-200/70 bg-white px-5 py-4 text-sm shadow-sm">
      <div className="flex justify-between gap-3">
        <p className="font-medium">{record.name} <span className="font-normal text-stone-400">· {record.dates || "no dates"}</span></p>
        <div className="flex shrink-0 gap-3 text-xs">
          <button onClick={() => setDraft({ name: record.name, goal: record.goal, audience: record.audience, angle: record.angle })}
            className="text-stone-500 underline">Edit</button>
          <button onClick={confirmRemove} className="text-stone-400 hover:text-red-600">Delete</button>
        </div>
      </div>
      <dl className="mt-2 space-y-1 text-stone-700">
        <p><span className="text-xs text-stone-400">Goal</span> {record.goal}</p>
        <p><span className="text-xs text-stone-400">Audience</span> {record.audience}</p>
        <p><span className="text-xs text-stone-400">Angle</span> {record.angle}</p>
        <p><span className="text-xs text-stone-400">Assets</span> {record.assets.join(", ")}</p>
        {record.images.length > 0 && <p><span className="text-xs text-stone-400">Images</span> {record.images.join(", ")}</p>}
      </dl>
      {record.chat_id && <button onClick={() => onOpenChat(record.chat_id!)} className="mt-1 text-xs text-stone-500 underline">Open the chat</button>}
    </div>
  );
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button onClick={onClick} className={`-mb-px border-b-2 px-3 py-2 ${active ? "border-violet-700 font-medium" : "border-transparent text-stone-500"}`}>
      {children}
    </button>
  );
}
