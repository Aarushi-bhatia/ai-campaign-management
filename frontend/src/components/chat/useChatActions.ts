import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";

/** Everything that sends something to a chat refreshes the chat, its cost, its assets and the chat list afterwards. */
export function useChatActions() {
  const queryClient = useQueryClient();
  const refresh = (id: number | null | undefined) => {
    queryClient.invalidateQueries({ queryKey: ["chats"] });
    queryClient.invalidateQueries({ queryKey: ["chat", id] });
    queryClient.invalidateQueries({ queryKey: ["calls", id] });
    queryClient.invalidateQueries({ queryKey: ["assets", id] });
  };

  // The chat goes with each answer, so a pending answer is shown in its own chat only, even after switching chats.
  const answer = useMutation({
    mutationFn: ({ chatId, questionId, text }: { chatId: number; questionId: number; text: string }) =>
      api.answer(chatId, questionId, text),
    onSettled: (_data, _error, { chatId }) => refresh(chatId),
  });

  return { answer, refresh };
}
