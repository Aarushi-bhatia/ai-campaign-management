export type QuestionData = {
  id: number;
  kind: "missing" | "unclear" | "clash" | "conflict";
  question: string;
  why: string;
  source_path: string;
  quote: string;
  options: { label: string; value: string }[];
  answer: string | null;
  remaining: number;
  /** Asked before the plan was approved and left open; it no longer applies. */
  expired?: boolean;
};

export type Message = {
  id: number;
  role: "user" | "assistant";
  kind: "text" | "question" | "note" | "plan" | "memory" | "remember_offer" | "edit" | "removed";
  content: string;
  data: Record<string, unknown> | null;
  ai_call_id: number | null;
  created_at: string;
};

export type PlanAsset = {
  id: string;
  type: "email" | "linkedin_post" | "x_post" | "blog_post" | "landing_page";
  title: string;
  audience: string;
  main_message: string;
  date: string;
  image_idea: string;
  notes: string;
  research_query: string;
  draft_for?: string;
};

export type Finding = {
  id: string;
  query: string;
  asset_ids: string[];
  finding: string;
  quote: string;
  url: string;
  title: string;
  date: string;
  removed: boolean;
};

export type Campaign = {
  id: number;
  brand_id: number;
  stage: "brief" | "asking" | "plan_ready" | "approved" | "writing" | "done";
  brief: string;
  brief_rules: string[];
  assumptions: string[];
  plan: { summary: string; assets: PlanAsset[]; failed_searches?: string[] } | null;
  plan_version: number;
  approved_at: string | null;
  research: Finding[];
};

export type AssetType = PlanAsset["type"];

export type Warning = { check: string; problem: string; quote: string };

export type AssetImage = { path?: string; alt_text?: string; why?: string; suggestion?: string };

export type Asset = {
  id: number;
  plan_id: string;
  position: number;
  type: AssetType;
  title: string;
  state: "waiting" | "writing" | "checking" | "done" | "failed";
  content: Record<string, any> | null;
  image: AssetImage | null;
  image_url: string | null;
  looked_up: string[];
  fixed: string[];
  warnings: Warning[];
  version: number;
  call_id: number | null;
  error: string | null;
  draft_for: string;
};

export type AssetVersion = {
  id: number;
  number: number;
  reason: string;
  note: string;
  content: Record<string, any>;
  image: AssetImage | null;
  warnings: Warning[];
  call_ids: number[];
  cost_usd: number;
  based_on: number | null;
  created_at: string;
};

export type CostTotals = {
  calls: number;
  cost_usd: number;
  tokens_in: number;
  tokens_cached: number;
  tokens_out: number;
  cache_hit_rate: number;
};

export type CostReport = {
  total: CostTotals;
  stages: (CostTotals & { stage: string })[];
  assets: (CostTotals & { asset_id: number; title: string })[];
  edits: { asset_id: number; title: string; version: number; reason: string; note: string; cost_usd: number }[];
  steps: { id: number; step: string; model: string; cost_usd: number | null; tokens_in: number; tokens_cached: number; cache_hit_rate: number }[];
};

export type MemoryItem = {
  id: number;
  text: string;
  kind: "correction" | "preference" | "decision";
  pinned: boolean;
  source_chat_id: number | null;
  created_at: string;
};

export type CampaignRecord = {
  id: number;
  name: string;
  goal: string;
  audience: string;
  angle: string;
  assets: string[];
  images: string[];
  dates: string;
  chat_id: number | null;
  created_at: string;
};

export type ChatSummary = {
  id: number;
  title: string;
  created_at: string;
};

export type Chat = ChatSummary & {
  messages: Message[];
  campaign: Campaign;
};

export type AiCallSummary = {
  id: number;
  step: string;
  size: string;
  model: string;
  chat_id: number | null;
  tokens_in: number;
  tokens_cached: number;
  tokens_cache_write: number;
  tokens_out: number;
  cost_usd: number | null;
  duration_ms: number;
  error: string | null;
  created_at: string;
};

export type AiCall = AiCallSummary & {
  request: {
    model: string;
    /** Chat messages for text calls; plain strings for search-vector calls. */
    /** Messages (text, or a list of parts), tool calls and tool results, exactly as sent. */
    input: (string | Record<string, any>)[];
    [key: string]: unknown;
  };
  response_text: string | null;
};

export type BrandStatus = "reading" | "ready" | "failed";

export type BrandSummary = {
  id: number;
  name: string;
  status: BrandStatus;
  documents_total: number;
  documents_done: number;
  phase: string;
  phase_done: number;
  phase_total: number;
  error: string | null;
  reviewed: boolean;
  created_at: string;
  read_finished_at: string | null;
};

type Evidence = { evidence: string };

export type DocumentCard = {
  summary: string;
  kind: string;
  claimed_status: Evidence & { value: string };
  date: Evidence & { as_written: string; iso: string };
  owner: Evidence & { name: string; role: string };
  safe_to_quote: Evidence & { value: "yes" | "no" | "unknown" };
  rules_on: string[];
  replaces: (Evidence & { document: string })[];
  claims_about_other_documents: (Evidence & { document: string; claim: string })[];
  mentions: { products: string[]; channels: string[]; customers: string[]; people: string[] };
  unverified: { field: string; value: string; evidence: string }[];
};

export type DocumentBasics = {
  folder: string;
  tokens: number;
  frontmatter: Record<string, string>;
  top_labels: Record<string, string>;
  headings: { level: number; text: string }[];
  name_hints: string[];
};

export type BrandDocument = {
  id: number;
  path: string;
  tokens: number;
  sections: number;
  basics: DocumentBasics | null;
  card: DocumentCard | null;
  card_error: string | null;
  card_call_id: number | null;
  facts: number;
  facts_error: string | null;
  facts_call_id: number | null;
  doc_type: string | null;
  status: DocumentStatus | null;
  status_reason: string | null;
  replaced_by: string | null;
};

export type DocumentStatus = "current" | "replaced" | "draft" | "archived" | "unclear";

export type Conflict = {
  id: number;
  subject: string;
  point: string;
  topic: string;
  rule: "replaces" | "owner" | "approved" | "newer" | "live" | "you" | "needs_human" | "only_side_left" | "not_counting";
  reason: string;
  winner: string | null;
  owners: string[];
  /** The position each side takes. */
  sides: string[];
  winning_side: number | null;
  facts: { id: number; side: number; path: string; attribute: string; value: string; kind: string; evidence: string }[];
  target: string;
  decided_target: string | null;
  call_id: number | null;
};

export type Entity = {
  name: string;
  kind: string;
  short_forms: string[];
  old_names: { name: string; evidence: string; path: string }[];
};

export type CorrectionKind = "document_status" | "document_kind" | "conflict_winner" | "image_usable";

export type Decision = { id: number; kind: CorrectionKind; target: string; value: string; created_at: string };

export type Brand = BrandSummary & {
  documents: BrandDocument[];
  other_files: { path: string; kind: string; size_bytes: number }[];
  reading_cost: { usd: number; calls: number; tokens_in: number; tokens_out: number };
  conflicts: Conflict[];
  entities: Entity[];
  links: { source: string; target: string; effect: string; claim: string; evidence: string }[];
  decisions: Decision[];
  /** Folders and files left out of the last upload. */
  excluded: string[];
  summary: string | null;
  summary_edited: boolean;
  summary_stale: boolean;
  summary_call_id: number | null;
  images: BrandImage[];
  image_rules: ImageRules | null;
  image_rules_call_id: number | null;
};

export type AssetChannel = "email" | "linkedin" | "x" | "blog" | "landing_page";

export type ImageNotes = {
  usable: boolean;
  retired: boolean;
  expired: boolean;
  no_crop: boolean;
  allowed_channels: string[];
  blocked_channels: string[];
  rules: string[];
  reason: string;
};

export type BrandImage = {
  id: number;
  path: string;
  url: string;
  title: string;
  description: string;
  description_source: "file" | "ai" | "name" | "";
  image_type: string;
  tags: string[];
  width: number;
  height: number;
  transparent: boolean;
  record: Record<string, unknown>;
  notes: ImageNotes | null;
  usable_override: "yes" | "no" | null;
  blocked: string | null;
  channels: Record<AssetChannel, string | null>;
  describe_call_id: number | null;
  notes_call_id: number | null;
};

export type ChannelImageRule = {
  block_transparent: boolean;
  orientation: string;
  allowed_types: string[];
  blocked_types: string[];
  min_width: number;
  image_optional: boolean;
  notes: string[];
};

export type ImageRules = {
  channels: Record<AssetChannel, ChannelImageRule>;
  alt_text_rules: string[];
  general_rules: string[];
};

export type PickResult = {
  choices: { path: string; url: string; why: string; alt_text: string }[];
  suggestion: string;
  blocked: { path: string; reason: string }[];
  call_id: number | null;
};
