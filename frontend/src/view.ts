/** Which page fills the main area. */
export type View =
  | { kind: "chat"; chatId: number | null }
  | { kind: "brand"; brandId: number }
  | { kind: "memory"; brandId: number }
  | { kind: "add-brand"; updating?: { id: number; name: string } };
