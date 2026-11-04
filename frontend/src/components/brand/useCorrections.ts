import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import type { Brand, CorrectionKind, Decision } from "../../api/types";

/** Corrections apply at once on the server and return the updated brand, which replaces the cached one. */
export function useCorrections(brand: Brand) {
  const queryClient = useQueryClient();
  const store = (updated: Brand) => queryClient.setQueryData(["brand", brand.id], updated);

  const correct = useMutation({
    mutationFn: ({ kind, target, value }: { kind: CorrectionKind; target: string; value: string }) =>
      api.correct(brand.id, kind, target, value),
    onSuccess: store,
  });
  const undo = useMutation({
    mutationFn: (decisionId: number) => api.undoCorrection(brand.id, decisionId),
    onSuccess: store,
  });

  const decisionFor = (kind: CorrectionKind, target: string): Decision | undefined =>
    brand.decisions.find((decision) => decision.kind === kind && decision.target === target);

  return {
    correct: (kind: CorrectionKind, target: string, value: string) => correct.mutate({ kind, target, value }),
    undo: (decision: Decision) => undo.mutate(decision.id),
    decisionFor,
    busy: correct.isPending || undo.isPending,
    error: correct.error ?? undo.error,
  };
}

export type Corrections = ReturnType<typeof useCorrections>;
