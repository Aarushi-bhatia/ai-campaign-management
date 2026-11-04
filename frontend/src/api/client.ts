import type {
  AiCall, AiCallSummary, Asset, AssetChannel, AssetVersion, Brand, BrandSummary, Campaign, CampaignRecord, Chat,
  ChatSummary, CorrectionKind, CostReport, MemoryItem, Message, PickResult, PlanAsset,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const isForm = init?.body instanceof FormData;
  const response = await fetch(path, {
    ...init,
    headers: isForm ? init?.headers : { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? `Request failed (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export type PickedFile = { path: string; file: File };

/** A folder upload: each file is sent with its path inside the folder as its name. */
function folderForm(files: PickedFile[], exclude: string[]): FormData {
  const form = new FormData();
  exclude.forEach((pattern) => form.append("exclude", pattern));
  files.forEach(({ path, file }) => form.append("files", file, path));
  return form;
}

export const api = {
  listChats: () => request<ChatSummary[]>("/api/chats"),
  getChat: (id: number) => request<Chat>(`/api/chats/${id}`),
  createChat: (brandId?: number) =>
    request<Chat>("/api/chats", { method: "POST", body: JSON.stringify({ brand_id: brandId ?? null }) }),
  sendMessage: (chatId: number, content: string) =>
    request<Message[]>(`/api/chats/${chatId}/messages`, { method: "POST", body: JSON.stringify({ content }) }),
  answer: (chatId: number, questionId: number, answer: string) =>
    request<Message[]>(`/api/chats/${chatId}/answer`, {
      method: "POST",
      body: JSON.stringify({ question_id: questionId, answer }),
    }),
  updatePlan: (chatId: number, assets: PlanAsset[]) =>
    request<Campaign>(`/api/chats/${chatId}/plan`, { method: "PUT", body: JSON.stringify({ assets }) }),
  approvePlan: (chatId: number) => request<Message[]>(`/api/chats/${chatId}/approve`, { method: "POST" }),
  writeAgain: (chatId: number) => request<Campaign>(`/api/chats/${chatId}/write`, { method: "POST" }),
  removeFinding: (chatId: number, findingId: string) =>
    request<Campaign>(`/api/chats/${chatId}/research/${findingId}`, { method: "DELETE" }),
  bringBackFinding: (chatId: number, findingId: string) =>
    request<Campaign>(`/api/chats/${chatId}/research/${findingId}/restore`, { method: "POST" }),
  retryResearch: (chatId: number) =>
    request<Message[]>(`/api/chats/${chatId}/research/retry`, { method: "POST" }),
  betterSource: (chatId: number, findingId: string) =>
    request<Message[]>(`/api/chats/${chatId}/research/${findingId}/better`, { method: "POST" }),
  listAssets: (chatId: number) => request<Asset[]>(`/api/chats/${chatId}/assets`),
  assetVersions: (chatId: number, assetId: number) =>
    request<AssetVersion[]>(`/api/chats/${chatId}/assets/${assetId}/versions`),
  handEdit: (chatId: number, assetId: number, content: Record<string, unknown>, baseVersion: number) =>
    request<{ asset: Asset; messages: Message[] }>(`/api/chats/${chatId}/assets/${assetId}`, {
      method: "PUT",
      body: JSON.stringify({ content, base_version: baseVersion }),
    }),
  undoAsset: (chatId: number, assetId: number, baseVersion: number) =>
    request<Asset>(`/api/chats/${chatId}/assets/${assetId}/undo?base_version=${baseVersion}`, { method: "POST" }),
  restoreVersion: (chatId: number, assetId: number, number: number, baseVersion: number) =>
    request<Asset>(`/api/chats/${chatId}/assets/${assetId}/versions/${number}/restore?base_version=${baseVersion}`, {
      method: "POST",
    }),
  checkAgain: (chatId: number, assetId: number) =>
    request<{ asset: Asset; messages: Message[] }>(`/api/chats/${chatId}/assets/${assetId}/check`, { method: "POST" }),
  bringBack: (chatId: number, messageId: number) =>
    request<Message[]>(`/api/chats/${chatId}/removed/${messageId}/undo`, { method: "POST" }),
  acceptRemember: (chatId: number, messageId: number) =>
    request<Message[]>(`/api/chats/${chatId}/remember/${messageId}`, { method: "POST" }),
  costs: (chatId: number) => request<CostReport>(`/api/chats/${chatId}/costs`),

  getMemory: (brandId: number) =>
    request<{ core: MemoryItem[]; history: CampaignRecord[] }>(`/api/brands/${brandId}/memory`),
  addMemory: (brandId: number, text: string, kind: MemoryItem["kind"]) =>
    request<MemoryItem & { dropped: string[]; replaced: string | null }>(`/api/brands/${brandId}/memory`, {
      method: "POST", body: JSON.stringify({ text, kind }),
    }),
  changeMemory: (id: number, change: { text?: string; pinned?: boolean }) =>
    request<MemoryItem>(`/api/memory/${id}`, { method: "PUT", body: JSON.stringify(change) }),
  deleteMemory: (id: number) => request<void>(`/api/memory/${id}`, { method: "DELETE" }),
  undoRemembered: (messageId: number) => request<void>(`/api/memory/notes/${messageId}/undo`, { method: "POST" }),
  deleteRecord: (id: number) => request<void>(`/api/campaign-records/${id}`, { method: "DELETE" }),
  changeRecord: (id: number, change: Partial<Pick<CampaignRecord, "name" | "goal" | "audience" | "angle">>) =>
    request<CampaignRecord>(`/api/campaign-records/${id}`, { method: "PUT", body: JSON.stringify(change) }),

  listCalls: (chatId: number) => request<AiCallSummary[]>(`/api/ai-calls?chat_id=${chatId}`),
  getCall: (id: number) => request<AiCall>(`/api/ai-calls/${id}`),

  listBrands: () => request<BrandSummary[]>("/api/brands"),
  getBrand: (id: number) => request<Brand>(`/api/brands/${id}`),
  addBrand: (name: string, files: PickedFile[], exclude: string[]) => {
    const form = folderForm(files, exclude);
    form.append("name", name);
    return request<BrandSummary>("/api/brands", { method: "POST", body: form });
  },
  updateBrand: (id: number, files: PickedFile[], exclude: string[]) =>
    request<BrandSummary>(`/api/brands/${id}/files`, { method: "POST", body: folderForm(files, exclude) }),
  correct: (id: number, kind: CorrectionKind, target: string, value: string) =>
    request<Brand>(`/api/brands/${id}/corrections`, { method: "POST", body: JSON.stringify({ kind, target, value }) }),
  undoCorrection: (id: number, decisionId: number) =>
    request<Brand>(`/api/brands/${id}/corrections/${decisionId}`, { method: "DELETE" }),
  editSummary: (id: number, text: string) =>
    request<BrandSummary>(`/api/brands/${id}/summary`, { method: "PUT", body: JSON.stringify({ text }) }),
  rebuildSummary: (id: number) => request<BrandSummary>(`/api/brands/${id}/summary/rebuild`, { method: "POST" }),
  pickImages: (id: number, body: { channel: AssetChannel; asset_type: string; message: string; campaign_rules?: string }) =>
    request<PickResult>(`/api/brands/${id}/images/pick`, { method: "POST", body: JSON.stringify(body) }),
  readBrandAgain: (id: number) => request<BrandSummary>(`/api/brands/${id}/read`, { method: "POST" }),
  markBrandReviewed: (id: number) => request<BrandSummary>(`/api/brands/${id}/reviewed`, { method: "POST" }),
};
