/** TanStack Query hooks, one per endpoint group. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import type {
  ApiKey,
  ApiKeyCreated,
  BreadDocument,
  Conversation,
  ConversationDetail,
  DatasetReport,
  DatasetRun,
  DatasetSources,
  DatasetValidation,
  Health,
  IndexResult,
  KnowledgeSpace,
  ModelStatus,
  ModelSummary,
  PromptPreset,
  RagSearchResult,
  RuntimeSettings,
  SystemStatus,
  TrainingConfigSummary,
  TrainingRun,
  UploadResult,
} from "./types";

export const queryKeys = {
  health: ["health"] as const,
  systemStatus: ["system", "status"] as const,
  models: ["models"] as const,
  modelStatus: ["models", "status"] as const,
  conversations: (search: string) => ["conversations", search] as const,
  conversation: (id: string) => ["conversation", id] as const,
  spaces: ["knowledge-spaces"] as const,
  documents: (spaceId?: string) => ["documents", spaceId ?? "all"] as const,
  datasets: ["datasets"] as const,
  datasetSources: ["datasets", "sources"] as const,
  trainingRuns: ["training", "runs"] as const,
  trainingConfigs: ["training", "configs"] as const,
  trainingLogs: (id: string) => ["training", id, "logs"] as const,
  settings: ["settings"] as const,
  apiKeys: ["api-keys"] as const,
  presets: ["prompts", "presets"] as const,
};

// ------------------------------------------------------------------- system
export const useHealth = () =>
  useQuery({ queryKey: queryKeys.health, queryFn: () => api.get<Health>("/api/health") });

export const useSystemStatus = (refetchMs = 15_000) =>
  useQuery({
    queryKey: queryKeys.systemStatus,
    queryFn: () => api.get<SystemStatus>("/api/system/status"),
    refetchInterval: refetchMs,
  });

// ------------------------------------------------------------------- models
export const useModels = () =>
  useQuery({ queryKey: queryKeys.models, queryFn: () => api.get<ModelSummary[]>("/api/models") });

export const useModelStatus = (refetchMs = 10_000) =>
  useQuery({
    queryKey: queryKeys.modelStatus,
    queryFn: () => api.get<ModelStatus>("/api/models/status"),
    refetchInterval: refetchMs,
  });

export function useLoadModel() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post<ModelStatus>("/api/models/load", body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.modelStatus });
      void client.invalidateQueries({ queryKey: queryKeys.systemStatus });
    },
  });
}

export function useUnloadModel() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<ModelStatus>("/api/models/unload", {}),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.modelStatus });
      void client.invalidateQueries({ queryKey: queryKeys.systemStatus });
    },
  });
}

export function useRegisterModel() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post<ModelSummary>("/api/models/register", body),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.models }),
  });
}

export function useDeleteModel() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete<ModelSummary>(`/api/models/${id}`),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.models }),
  });
}

// ------------------------------------------------------------ conversations
export const useConversations = (search = "") =>
  useQuery({
    queryKey: queryKeys.conversations(search),
    queryFn: () =>
      api.get<Conversation[]>(
        `/api/conversations${search ? `?search=${encodeURIComponent(search)}` : ""}`,
      ),
  });

export const useConversation = (id: string | undefined) =>
  useQuery({
    queryKey: queryKeys.conversation(id ?? ""),
    queryFn: () => api.get<ConversationDetail>(`/api/conversations/${id}`),
    enabled: Boolean(id),
  });

export function useCreateConversation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post<Conversation>("/api/conversations", body),
    onSuccess: () => client.invalidateQueries({ queryKey: ["conversations"] }),
  });
}

export function useUpdateConversation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      api.patch<Conversation>(`/api/conversations/${id}`, body),
    onSuccess: (_data, variables) => {
      void client.invalidateQueries({ queryKey: ["conversations"] });
      void client.invalidateQueries({ queryKey: queryKeys.conversation(variables.id) });
    },
  });
}

export function useDeleteConversation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete<{ deleted: boolean }>(`/api/conversations/${id}`),
    onSuccess: () => client.invalidateQueries({ queryKey: ["conversations"] }),
  });
}

export function useRollbackMessage() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ conversationId, messageId }: { conversationId: string; messageId: string }) =>
      api.post<ConversationDetail>(
        `/api/conversations/${conversationId}/messages/${messageId}/rollback`,
      ),
    onSuccess: (_data, variables) =>
      client.invalidateQueries({ queryKey: queryKeys.conversation(variables.conversationId) }),
  });
}

// -------------------------------------------------------- knowledge spaces
export const useKnowledgeSpaces = () =>
  useQuery({
    queryKey: queryKeys.spaces,
    queryFn: () => api.get<KnowledgeSpace[]>("/api/knowledge-spaces"),
  });

export function useCreateSpace() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post<KnowledgeSpace>("/api/knowledge-spaces", body),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.spaces }),
  });
}

export function useUpdateSpace() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      api.patch<KnowledgeSpace>(`/api/knowledge-spaces/${id}`, body),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.spaces }),
  });
}

export function useDeleteSpace() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete<{ deleted: boolean }>(`/api/knowledge-spaces/${id}`),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.spaces });
      void client.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}

// ----------------------------------------------------------------- documents
export const useDocuments = (spaceId?: string) =>
  useQuery({
    queryKey: queryKeys.documents(spaceId),
    queryFn: () =>
      api.get<BreadDocument[]>(
        `/api/documents${spaceId ? `?knowledge_space_id=${spaceId}` : ""}`,
      ),
  });

export function useUploadDocuments() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ files, spaceId }: { files: File[]; spaceId?: string }) => {
      const form = new FormData();
      files.forEach((file) => form.append("files", file));
      if (spaceId) form.append("knowledge_space_id", spaceId);
      form.append("index_now", "true");
      return api.upload<UploadResult>("/api/documents/upload", form);
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["documents"] });
      void client.invalidateQueries({ queryKey: queryKeys.spaces });
    },
  });
}

export function useIndexDocuments() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post<IndexResult>("/api/documents/index", body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["documents"] });
      void client.invalidateQueries({ queryKey: queryKeys.spaces });
    },
  });
}

export function useDeleteDocument() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete<{ deleted: boolean }>(`/api/documents/${id}`),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["documents"] });
      void client.invalidateQueries({ queryKey: queryKeys.spaces });
    },
  });
}

export const useRagSearch = () =>
  useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post<RagSearchResult>("/api/rag/search", body),
  });

// ------------------------------------------------------------------ datasets
export const useDatasetRuns = (refetchMs = 5_000) =>
  useQuery({
    queryKey: queryKeys.datasets,
    queryFn: () => api.get<DatasetRun[]>("/api/datasets"),
    refetchInterval: refetchMs,
  });

export const useDatasetSources = () =>
  useQuery({
    queryKey: queryKeys.datasetSources,
    queryFn: () => api.get<DatasetSources>("/api/datasets/sources"),
    staleTime: Infinity,
  });

export function useCollectDataset() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post<DatasetRun>("/api/datasets/collect", body),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.datasets }),
  });
}

export const useValidateDataset = () =>
  useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post<DatasetValidation>("/api/datasets/validate", body),
  });

export const useDatasetReport = () =>
  useMutation({
    mutationFn: (path: string) =>
      api.get<DatasetReport>(`/api/datasets/report?path=${encodeURIComponent(path)}`),
  });

// ------------------------------------------------------------------ training
export const useTrainingRuns = (refetchMs = 5_000) =>
  useQuery({
    queryKey: queryKeys.trainingRuns,
    queryFn: () => api.get<TrainingRun[]>("/api/training/runs"),
    refetchInterval: refetchMs,
  });

export const useTrainingConfigs = () =>
  useQuery({
    queryKey: queryKeys.trainingConfigs,
    queryFn: () => api.get<TrainingConfigSummary[]>("/api/training/configs"),
    staleTime: Infinity,
  });

export const useTrainingLogs = (runId: string | undefined, enabled: boolean) =>
  useQuery({
    queryKey: queryKeys.trainingLogs(runId ?? ""),
    queryFn: () => api.get<{ run_id: string; lines: string[]; truncated: boolean }>(
      `/api/training/${runId}/logs?tail=400`,
    ),
    enabled: Boolean(runId) && enabled,
    refetchInterval: 4_000,
  });

export function useStartTraining() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post<TrainingRun>("/api/training/start", body),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.trainingRuns }),
  });
}

export function useStopTraining() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => api.post<TrainingRun>("/api/training/stop", { run_id: runId }),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.trainingRuns }),
  });
}

// ------------------------------------------------------------------ settings
export const useSettings = () =>
  useQuery({ queryKey: queryKeys.settings, queryFn: () => api.get<RuntimeSettings>("/api/settings") });

export function useUpdateSettings() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.patch<RuntimeSettings>("/api/settings", body),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.settings }),
  });
}

// ------------------------------------------------------------------ security
export const useApiKeys = () =>
  useQuery({ queryKey: queryKeys.apiKeys, queryFn: () => api.get<ApiKey[]>("/api/api-keys") });

export function useCreateApiKey() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post<ApiKeyCreated>("/api/api-keys", body),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.apiKeys }),
  });
}

export function useRevokeApiKey() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete<{ deleted: boolean }>(`/api/api-keys/${id}`),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.apiKeys }),
  });
}

// ------------------------------------------------------------------- prompts
export const usePresets = () =>
  useQuery({
    queryKey: queryKeys.presets,
    queryFn: () => api.get<PromptPreset[]>("/api/prompts/presets"),
    staleTime: Infinity,
  });
