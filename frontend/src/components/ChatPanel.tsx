import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { AiCallSummary, Message, QuestionData } from "../api/types";
import { formatCost, formatTokens } from "../format";
import { QuestionCard } from "./chat/QuestionCard";
import { useChatActions } from "./chat/useChatActions";

type Props = {
  chatId: number | null;
  brandId: number | null;
  onChatCreated: (id: number) => void;
  onViewPrompt: (callId: number) => void;
};

const PLACEHOLDERS: Record<string, string> = {
  brief: "Paste the campaign brief. Enter to send, Shift+Enter for a new line.",
  asking: "Answer the question above, or type your own answer.",
  plan_ready: "Ask for changes to the plan, e.g. drop the X post, add a customer email.",
  approved: "Writing the assets…",
  writing: "Writing the assets… you can ask for changes once they're done.",
  done: "Ask for a change, e.g. shorten the second post, or use 'boundary' instead of 'guardrail' everywhere.",
};

export function ChatPanel({ chatId, brandId, onChatCreated, onViewPrompt }: Props) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const { answer, refresh } = useChatActions();
  // The panel stays the same when you switch chats, so a message still on its way remembers which chat it
  // belongs to, and only that chat shows it.
  const [sentTo, setSentTo] = useState<number | null>(null);

  const chat = useQuery({
    queryKey: ["chat", chatId],
    queryFn: () => api.getChat(chatId!),
    enabled: chatId !== null,
    refetchInterval: (query) => (["approved", "writing"].includes(query.state.data?.campaign.stage ?? "") ? 1500 : false),
  });
  const writingNow = ["approved", "writing"].includes(chat.data?.campaign.stage ?? "");
  const calls = useQuery({
    queryKey: ["calls", chatId],
    queryFn: () => api.listCalls(chatId!),
    enabled: chatId !== null,
    refetchInterval: writingNow ? 3000 : false,
  });
  const undoMemory = useMutation({ mutationFn: (messageId: number) => api.undoRemembered(messageId), onSettled: () => refresh(chatId) });
  const remember = useMutation({ mutationFn: (messageId: number) => api.acceptRemember(chatId!, messageId), onSettled: () => refresh(chatId) });
  const bringBack = useMutation({ mutationFn: (messageId: number) => api.bringBack(chatId!, messageId), onSettled: () => refresh(chatId) });

  const send = useMutation({
    mutationFn: async (content: string) => {
      setSentTo(chatId);
      const id = chatId ?? (await api.createChat(brandId ?? undefined)).id;
      setSentTo(id);
      if (id !== chatId) onChatCreated(id);
      await api.sendMessage(id, content);
      return id;
    },
    onSettled: (id) => {
      refresh(id);
      queryClient.invalidateQueries({ queryKey: ["chats"] });
    },
  });

  const messages = chat.data?.messages ?? [];
  const stage = chat.data?.campaign.stage ?? "brief";
  const callsById = new Map(calls.data?.map((call) => [call.id, call]));
  const openQuestionId = lastOpenQuestion(messages);
  const sendingHere = send.isPending && sentTo === chatId;
  const answeringHere = answer.isPending && answer.variables?.chatId === chatId;
  const sendError = sentTo === chatId ? send.error : null;
  const answerError = answer.variables?.chatId === chatId ? answer.error : null;
  const busy = sendingHere || answeringHere;
  const prevStage = useRef(stage);
  useEffect(() => {
    // the assets panel and costs follow the chat once writing ends
    if (prevStage.current !== stage) queryClient.invalidateQueries({ queryKey: ["assets", chatId] });
    prevStage.current = stage;
  }, [stage, chatId, queryClient]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, busy]);

  function submit() {
    const content = draft.trim();
    if (!content || busy) return;
    setDraft("");
    send.mutate(content);
  }

  return (
    <section className="flex min-w-0 flex-1 flex-col bg-white">
      <div className="min-h-0 flex-1 overflow-y-auto px-8 py-8">
        {messages.length === 0 && !sendingHere && (
          <div className="mx-auto mt-24 max-w-md text-center text-stone-500">
            <p className="text-lg font-medium text-stone-800">Start a campaign</p>
            <p className="mt-1 text-sm">Paste a campaign brief below. The agent checks it against the brand, asks only what it needs, then proposes a plan.</p>
          </div>
        )}
        <div className="mx-auto flex max-w-2xl flex-col gap-6">
          {messages.map((message) => (
            <MessageItem
              key={message.id}
              message={message}
              call={message.ai_call_id ? callsById.get(message.ai_call_id) : undefined}
              openQuestionId={openQuestionId}
              busy={busy}
              onAnswer={(questionId, text) => answer.mutate({ chatId: chatId!, questionId, text })}
              onViewPrompt={onViewPrompt}
              onUndoMemory={(messageId) => undoMemory.mutate(messageId)}
              onRemember={(messageId) => remember.mutate(messageId)}
              onBringBack={(messageId) => bringBack.mutate(messageId)}
            />
          ))}
          {sendingHere && (
            <>
              <UserBubble content={send.variables} />
              <Working />
            </>
          )}
          {answeringHere && <Working />}
          {writingNow && <p className="text-sm text-stone-400">Writing… each asset is checked and fixed before it shows as done.</p>}
          {(sendError || answerError || undoMemory.error) && (
            <p className="text-sm text-red-600">{(sendError ?? answerError ?? undoMemory.error)!.message}</p>
          )}
          <div ref={bottomRef} />
        </div>
      </div>
      <div className="border-t border-stone-100 px-8 pb-6 pt-4">
        <div className="mx-auto flex max-w-2xl gap-3">
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                submit();
              }
            }}
            rows={3}
            disabled={writingNow}
            placeholder={PLACEHOLDERS[stage]}
            className="flex-1 resize-none rounded-xl border border-stone-200 px-4 py-3 text-sm leading-normal disabled:bg-stone-50"
          />
          <button
            onClick={submit}
            disabled={!draft.trim() || busy}
            className="self-end rounded-xl bg-violet-700 px-5 py-2.5 text-sm font-medium text-white hover:bg-violet-800 disabled:opacity-40"
          >
            Send
          </button>
        </div>
      </div>
    </section>
  );
}

/** The newest question card that hasn't been answered yet. Only that one takes answers. */
function lastOpenQuestion(messages: Message[]): number | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    const message = messages[i];
    if (message.kind === "question") {
      const data = message.data as QuestionData;
      return data.answer ? null : data.id;
    }
  }
  return null;
}

function Working() {
  return <p className="text-sm text-stone-400">Working: looking things up in the brand…</p>;
}

function UserBubble({ content }: { content: string }) {
  return (
    <div className="ml-auto max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-brand-soft px-5 py-3 text-sm leading-relaxed text-violet-950">{content}</div>
  );
}

type ItemProps = {
  message: Message;
  call: AiCallSummary | undefined;
  openQuestionId: number | null;
  busy: boolean;
  onAnswer: (questionId: number, text: string) => void;
  onViewPrompt: (callId: number) => void;
  onUndoMemory: (messageId: number) => void;
  onRemember: (messageId: number) => void;
  onBringBack: (messageId: number) => void;
};

function MessageItem({ message, call, openQuestionId, busy, onAnswer, onViewPrompt, onUndoMemory, onRemember, onBringBack }: ItemProps) {
  if (message.role === "user") return <UserBubble content={message.content} />;
  if (message.kind === "note") {
    return <p className="text-xs leading-relaxed text-stone-500">↳ {message.content}</p>;
  }
  if (message.kind === "memory") {
    const data = message.data as { item_id: number; undone?: boolean };
    return (
      <p className="text-xs leading-relaxed text-violet-700">
        ✦ <span className={data.undone ? "line-through opacity-60" : ""}>{message.content}</span>
        {data.undone ? <span className="ml-2 text-stone-400">undone</span> : (
          <button onClick={() => onUndoMemory(message.id)} className="ml-2 underline hover:text-violet-900">Undo</button>
        )}
      </p>
    );
  }
  if (message.kind === "remember_offer") {
    const data = message.data as { text: string; done?: boolean };
    return (
      <div className="max-w-[85%] rounded-xl border border-violet-100 bg-violet-50 px-5 py-3.5 text-sm leading-relaxed text-violet-900">
        {message.content}
        {!data.done && (
          <button onClick={() => onRemember(message.id)} className="ml-3 rounded-full bg-violet-700 px-3 py-1 text-xs font-medium text-white">
            Remember this
          </button>
        )}
      </div>
    );
  }
  if (message.kind === "question") {
    const question = message.data as QuestionData;
    return (
      <QuestionCard
        question={question}
        open={question.id === openQuestionId}
        busy={busy}
        onAnswer={(text) => onAnswer(question.id, text)}
      />
    );
  }
  return (
    <div className="max-w-[85%]">
      {message.kind === "removed" ? (
        <div className="rounded-xl border border-stone-200/70 bg-stone-50 px-5 py-4 text-sm leading-relaxed">
          <p className={`whitespace-pre-wrap ${(message.data as { undone?: boolean }).undone ? "text-stone-400 line-through" : ""}`}>
            {message.content}
          </p>
          {(message.data as { undone?: boolean }).undone ? (
            <p className="mt-2 text-xs text-stone-500">Undone: the assets are back.</p>
          ) : (
            <button onClick={() => onBringBack(message.id)} className="mt-3 rounded-full border border-stone-200 bg-white px-3 py-1 text-xs font-medium text-stone-700 hover:bg-stone-100">
              Undo
            </button>
          )}
        </div>
      ) : message.kind === "edit" ? (
        <div className="rounded-xl border border-sky-100 bg-sky-50/60 px-5 py-4 text-sm leading-relaxed whitespace-pre-wrap">{message.content}</div>
      ) : message.kind === "plan" ? (
        <div className="rounded-xl border border-emerald-100 bg-emerald-50/60 px-5 py-4 text-sm leading-relaxed">
          <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-emerald-700">
            Plan {(message.data as { version: number }).version} · {(message.data as { assets: number }).assets} assets · on the right
          </p>
          <p className="mt-2 whitespace-pre-wrap">{message.content}</p>
        </div>
      ) : (
        <div className="whitespace-pre-wrap text-sm leading-relaxed">{message.content}</div>
      )}
      {call && <CallLine call={call} onViewPrompt={onViewPrompt} />}
    </div>
  );
}

function CallLine({ call, onViewPrompt }: { call: AiCallSummary; onViewPrompt: (callId: number) => void }) {
  return (
    <div className="mt-2.5 flex gap-3 text-xs text-stone-400">
      <span>
        {call.model} · {formatTokens(call.tokens_in)} in · {formatTokens(call.tokens_cached)} cached ·{" "}
        {formatTokens(call.tokens_out)} out · {formatCost(call.cost_usd)}
      </span>
      <button onClick={() => onViewPrompt(call.id)} className="underline hover:text-stone-700">
        View prompt
      </button>
    </div>
  );
}
