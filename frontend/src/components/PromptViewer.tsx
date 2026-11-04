import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { api } from "../api/client";
import { formatCost } from "../format";

type Props = {
  callId: number;
  onClose: () => void;
};

/** Shows exactly what was sent to the model for one call, and what came back. */
export function PromptViewer({ callId, onClose }: Props) {
  const call = useQuery({ queryKey: ["call", callId], queryFn: () => api.getCall(callId) });

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  const data = call.data;
  const { input, ...options } = data?.request ?? { input: [] };

  return (
    <div className="fixed inset-0 z-10 flex items-center justify-center bg-black/40 p-6" onClick={onClose}>
      <div
        className="flex max-h-full w-full max-w-4xl flex-col overflow-hidden rounded-xl bg-white shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="flex items-start justify-between border-b border-stone-100 px-6 py-4">
          <div>
            <h2 className="font-medium">{data?.step ?? "Loading…"}</h2>
            {data && (
              <p className="text-xs text-stone-500">
                Answered by {data.model} · {data.tokens_in} tokens in ({data.tokens_cached} read from cache,{" "}
                {data.tokens_cache_write} written to cache) · {data.tokens_out} out · {formatCost(data.cost_usd)} ·{" "}
                {(data.duration_ms / 1000).toFixed(1)}s
              </p>
            )}
          </div>
          <button onClick={onClose} className="text-sm text-stone-500 hover:text-stone-900">
            Close
          </button>
        </header>
        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-6">
          <Section title="Request options">
            <pre className="text-xs">{JSON.stringify(options, null, 2)}</pre>
          </Section>
          {input.map((item, index) => {
            const { title, text } = describe(item, index);
            return (
              <Section key={index} title={title}>
                <pre className="whitespace-pre-wrap text-xs">{text}</pre>
              </Section>
            );
          })}
          <Section title="Reply">
            <pre className="whitespace-pre-wrap text-xs">{data?.error ?? data?.response_text}</pre>
          </Section>
        </div>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="mb-1.5 text-[11px] font-medium uppercase tracking-[0.08em] text-stone-400">{title}</h3>
      <div className="rounded-lg border border-stone-200/70 bg-stone-50 p-4">{children}</div>
    </section>
  );
}

type Part = { type?: string; text?: string; image_url?: string; prompt_cache_breakpoint?: unknown };
type InputItem = string | {
  role?: string;
  content?: string | Part[];
  type?: string;
  name?: string;
  arguments?: string;
  output?: string;
};

/** One item of the request as readable text. A message's text can be a plain string or a list of parts;
 * tool calls and their results come back as their own items. */
function describe(item: InputItem, index: number): { title: string; text: string } {
  const number = index + 1;
  if (typeof item === "string") return { title: `Text ${number}`, text: item };
  if (item.type === "function_call") return { title: `Tool call ${number}: ${item.name}`, text: item.arguments ?? "" };
  if (item.type === "function_call_output") return { title: `Tool result ${number}`, text: item.output ?? "" };
  const content = item.content;
  if (typeof content === "string") return { title: `Message ${number}: ${item.role}`, text: content };
  const parts = content ?? [];
  const cached = parts.some((part) => part.prompt_cache_breakpoint);
  const text = parts.map((part) => part.text ?? (part.image_url ? `[${part.image_url}]` : "")).join("\n\n");
  return { title: `Message ${number}: ${item.role}${cached ? " · cache point after this" : ""}`, text };
}
