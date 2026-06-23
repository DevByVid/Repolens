import {
  AnalysisReport,
  ChatResponse,
  ChatHistoryTurn,
  SystemMapResponse,
} from "../types/api";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Request failed");
  }

  return res.json();
}

export const api = {
  async analyzeRepo(file: File): Promise<AnalysisReport> {
    const form = new FormData();
    form.append("file", file);

    return apiFetch<AnalysisReport>("/api/analyze", {
      method: "POST",
      body: form,
    });
  },

  // Actually calls the backend's Gemini-backed /api/chat endpoint, passing
  // conversation history so follow-up questions are context-aware instead of
  // being answered in isolation by client-side keyword matching.
  async chat(
    session_id: string,
    question: string,
    history: ChatHistoryTurn[]
  ): Promise<ChatResponse> {
    return apiFetch<ChatResponse>("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id, question, history }),
    });
  },

  // Reads the backend's deterministically-enriched system map (entrypoints,
  // tech stack, modules) for this session — not re-derived from scratch in
  // the browser with substring-matching heuristics.
  async systemMap(session_id: string): Promise<SystemMapResponse> {
    const params = new URLSearchParams({ session_id });
    return apiFetch<SystemMapResponse>(`/api/system-map?${params.toString()}`);
  },

  async evictCache(session_id: string): Promise<void> {
    await apiFetch<{ status: string }>("/api/evict", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id }),
    });
  },
};
