import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../../api/client";
import type { Brand } from "../../api/types";

type Props = {
  brand: Brand;
  onViewPrompt: (callId: number) => void;
};

/** The summary sent with every campaign request. The user can edit it, or rebuild it from the facts. */
export function SummaryTab({ brand, onViewPrompt }: Props) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<string | null>(null);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["brand", brand.id] });

  const save = useMutation({
    mutationFn: (text: string) => api.editSummary(brand.id, text),
    onSuccess: () => {
      setDraft(null);
      refresh();
    },
  });
  const rebuild = useMutation({ mutationFn: () => api.rebuildSummary(brand.id), onSuccess: refresh });

  if (!brand.summary) {
    return <p className="p-6 text-sm text-stone-500">The summary is written at the end of reading.</p>;
  }

  return (
    <div className="space-y-3 p-6">
      <p className="text-sm text-stone-500">
        This exact text goes at the start of every campaign request, so it should hold what every asset needs.
        Channel rules are looked up per asset.
      </p>
      {brand.summary_edited && <Notice>You edited this summary. It stays as you wrote it until you rebuild it.</Notice>}
      {brand.summary_stale && !brand.summary_edited && (
        <Notice>Your corrections changed the facts since this summary was written. Rebuild it to include them.</Notice>
      )}
      <div className="flex gap-2">
        {draft === null ? (
          <Button onClick={() => setDraft(brand.summary)}>Edit</Button>
        ) : (
          <>
            <Button onClick={() => save.mutate(draft)} disabled={save.isPending || !draft.trim()}>
              Save
            </Button>
            <Button onClick={() => setDraft(null)}>Cancel</Button>
          </>
        )}
        <Button
          onClick={() => rebuild.mutate()}
          disabled={rebuild.isPending || brand.status === "reading"}
          title="Writes the summary again from the current facts. Your edits are replaced."
        >
          Rebuild from the documents
        </Button>
        {brand.summary_call_id && (
          <button onClick={() => onViewPrompt(brand.summary_call_id!)} className="text-xs text-stone-500 underline">
            View prompt
          </button>
        )}
      </div>
      {draft === null ? (
        <pre className="whitespace-pre-wrap rounded-lg border border-stone-200 bg-stone-50 p-4 font-sans text-sm leading-relaxed">
          {brand.summary}
        </pre>
      ) : (
        <textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          className="h-[60vh] w-full rounded-lg border border-stone-200 p-4 font-mono text-sm"
        />
      )}
    </div>
  );
}

function Notice({ children }: { children: React.ReactNode }) {
  return <p className="rounded-lg border border-amber-200 bg-amber-50 p-2 text-sm text-amber-900">{children}</p>;
}

function Button(props: { onClick: () => void; disabled?: boolean; title?: string; children: React.ReactNode }) {
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
