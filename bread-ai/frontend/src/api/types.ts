/**
 * Types mirroring the Pydantic schemas in backend/app/schemas.py.
 *
 * They are written by hand rather than generated so the UI stays readable; the
 * contract test in src/test/apiContract.test.ts checks them against the live
 * OpenAPI document when a server is running.
 */

export type Role = "system" | "user" | "assistant";

export interface ApiErrorBody {
  code: string;
  message: string;
  hint?: string;
  details?: Record<string, unknown>;
}

export interface Health {
  status: "ok";
  app: string;
  version: string;
  time: string;
}

export interface GpuDevice {
  index: number;
  name: string;
  total_memory_mb?: number | null;
  allocated_memory_mb?: number | null;
  reserved_memory_mb?: number | null;
  free_memory_mb?: number | null;
  capability?: string | null;
}

export interface GpuStatus {
  cuda_available: boolean;
  torch_installed: boolean;
  torch_version?: string | null;
  cuda_version?: string | null;
  driver_version?: string | null;
  device_count: number;
  devices: GpuDevice[];
  notes: string[];
}

export interface ModelStatus {
  loaded: boolean;
  backend: string;
  model_id?: string | null;
  tokenizer_id?: string | null;
  adapter_path?: string | null;
  quantization_mode?: string | null;
  dtype?: string | null;
  device?: string | null;
  context_length?: number | null;
  loaded_at?: string | null;
  load_seconds?: number | null;
  vram_allocated_mb?: number | null;
  detail?: string | null;
}

export interface SystemStatus {
  app: string;
  version: string;
  python_version: string;
  platform: string;
  host: string;
  port: number;
  binds_to_lan: boolean;
  api_key_required: boolean;
  data_dir: string;
  database_url: string;
  rag_enabled: boolean;
  model: ModelStatus;
  gpu: GpuStatus;
  optional_dependencies: Record<string, boolean>;
  warnings: string[];
}

export interface ModelSummary {
  id: string;
  name: string;
  model_id: string;
  backend: string;
  quantization_mode: string;
  dtype: string;
  device: string;
  adapter_path?: string | null;
  context_length: number;
  notes?: string | null;
  is_builtin: boolean;
}

export interface Citation {
  document_id: string;
  document_name: string;
  chunk_id: string;
  chunk_index: number;
  score: number;
  excerpt: string;
  start_line?: number | null;
  end_line?: number | null;
}

export interface ChatMessage {
  id: string;
  conversation_id: string;
  role: Role;
  content: string;
  sources: Citation[];
  model_id?: string | null;
  token_count?: number | null;
  latency_ms?: number | null;
  stopped_early: boolean;
  error?: string | null;
  created_at: string;
}

export interface Conversation {
  id: string;
  title: string;
  model_id?: string | null;
  system_prompt?: string | null;
  temperature?: number | null;
  top_p?: number | null;
  max_new_tokens?: number | null;
  rag_enabled: boolean;
  knowledge_space_id?: string | null;
  pinned: boolean;
  archived: boolean;
  message_count: number;
  last_message_preview?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConversationDetail extends Conversation {
  messages: ChatMessage[];
}

export interface KnowledgeSpace {
  id: string;
  name: string;
  description?: string | null;
  embedding_model_id: string;
  chunk_size: number;
  chunk_overlap: number;
  document_count: number;
  chunk_count: number;
  created_at: string;
  updated_at: string;
}

export interface BreadDocument {
  id: string;
  knowledge_space_id: string;
  filename: string;
  extension: string;
  size_bytes: number;
  content_hash: string;
  language?: string | null;
  status: string;
  chunk_count: number;
  error?: string | null;
  created_at: string;
  indexed_at?: string | null;
}

export interface UploadResult {
  documents: BreadDocument[];
  skipped: { filename: string; reason: string }[];
}

export interface IndexResult {
  indexed_documents: number;
  created_chunks: number;
  skipped_documents: number;
  failed: { document_id: string; error: string }[];
  embedding_model_id: string;
  duration_ms: number;
}

export interface RagSearchResult {
  query: string;
  knowledge_space_id?: string | null;
  results: Citation[];
  embedding_model_id: string;
  reranked: boolean;
}

export interface DatasetRun {
  id: string;
  name: string;
  kind: string;
  source: string;
  output_path: string;
  record_count: number;
  accepted_terms: boolean;
  terms_url?: string | null;
  license_summary?: string | null;
  manifest_json?: string | null;
  status: string;
  error?: string | null;
  created_at: string;
  finished_at?: string | null;
}

export interface DatasetSources {
  local: { id: string; title: string; requires_terms: boolean; notes: string }[];
  external: {
    id: string;
    title: string;
    requires_terms: boolean;
    dataset_name: string;
    source_url: string;
    terms_url: string;
  }[];
  languages: string[];
  notice: string;
}

export interface DatasetReport {
  path: string;
  total_records: number;
  total_characters: number;
  approx_tokens: number;
  language_counts: Record<string, number>;
  license_counts: Record<string, number>;
  source_counts: Record<string, number>;
  length_percentiles: Record<string, number>;
  warnings: string[];
}

export interface DatasetValidation {
  path: string;
  total_records: number;
  valid_records: number;
  invalid_records: number;
  issues: { line: number; field?: string | null; problem: string }[];
  duplicate_records: number;
  secret_hits: number;
}

export interface TrainingRun {
  id: string;
  name: string;
  method: string;
  base_model_id: string;
  dataset_path: string;
  config_path: string;
  output_dir: string;
  status: string;
  pid?: number | null;
  current_step: number;
  total_steps?: number | null;
  train_loss?: number | null;
  eval_loss?: number | null;
  error?: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface TrainingConfigSummary {
  path: string;
  name: string;
  base_model_id: string;
  method: string;
  description: string;
  min_vram_gb?: number | null;
}

export interface RuntimeSettings {
  model_id: string;
  tokenizer_id: string;
  model_backend: string;
  model_device: string;
  model_dtype: string;
  quantization_mode: string;
  max_context_length: number;
  max_new_tokens: number;
  temperature: number;
  top_p: number;
  repetition_penalty: number;
  adapter_path: string;
  system_prompt_path: string;
  embedding_model_id: string;
  rag_enabled: boolean;
  rag_top_k: number;
  rag_rerank_enabled: boolean;
  chunk_size: number;
  chunk_overlap: number;
  vector_backend: string;
  host: string;
  port: number;
  require_api_key: boolean;
  allow_model_download: boolean;
  max_upload_bytes: number;
  data_dir: string;
}

export interface ApiKey {
  id: string;
  label: string;
  key_prefix: string;
  scopes: string;
  revoked: boolean;
  created_at: string;
  last_used_at?: string | null;
}

export interface ApiKeyCreated extends ApiKey {
  key: string;
}

export interface PromptPreset {
  name: string;
  title: string;
  description: string;
  body: string;
}

export interface ChatRequestBody {
  conversation_id?: string;
  message: string;
  system_prompt?: string;
  model_id?: string;
  temperature?: number;
  top_p?: number;
  max_new_tokens?: number;
  rag_enabled?: boolean;
  knowledge_space_id?: string;
  rag_top_k?: number;
  preset?: string;
  persist?: boolean;
}
