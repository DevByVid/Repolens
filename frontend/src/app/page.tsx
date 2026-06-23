"use client";
import { useState, useCallback } from "react";
import { Code2, Map } from "lucide-react";

import { AppState, ChatMessage, SystemMapResponse } from "../types/api";
import { api } from "../hooks/useApi";
import UploadZone from "../components/UploadZone";
import ChatPanel from "../components/ChatPanel";
import SystemMap from "../components/SystemMap";
import StatusBar from "../components/StatusBar";

type Tab = "chat" | "map";

let msgCounter = 0;
function mkId() {
  return `m-${++msgCounter}`;
}

export default function Home() {
  const [state, setState] = useState<AppState>({ phase: "idle" });
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [tab, setTab] = useState<Tab>("chat");
  const [mapData, setMapData] = useState<SystemMapResponse | null>(null);
  const [mapLoading, setMapLoading] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);

  // ── Upload ──────────────────────────────────────────────────────────────
  const handleUpload = useCallback(async (file: File) => {
    setState({ phase: "uploading" });
    try {
      const report = await api.analyzeRepo(file);
      setState({ phase: "ready", report });
      setMessages([]);
      setMapData(null);
      setMapError(null);
    } catch (e: any) {
      setState({ phase: "error", message: e.message });
    }
  }, []);

  // ── Chat ────────────────────────────────────────────────────────────────
  // Sends the question to the real backend along with prior turns, so
  // follow-ups are answered with conversational context instead of being
  // matched against keywords in isolation.
  const handleSend = useCallback(
    async (question: string) => {
      if (state.phase !== "ready") return;
      const { session_id } = state.report;

      const userMsg: ChatMessage = {
        id: mkId(),
        role: "user",
        content: question,
        timestamp: new Date(),
      };

      const history = messages.map((m) => ({ role: m.role, content: m.content }));

      setMessages((prev) => [...prev, userMsg]);
      setChatLoading(true);

      try {
        const res = await api.chat(session_id, question, history);
        setMessages((prev) => [
          ...prev,
          { id: mkId(), role: "assistant", content: res.answer, timestamp: new Date() },
        ]);
      } catch (e: any) {
        setMessages((prev) => [
          ...prev,
          {
            id: mkId(),
            role: "assistant",
            content: `⚠️ ${e.message || "Something went wrong talking to the AI engine."}`,
            timestamp: new Date(),
          },
        ]);
      } finally {
        setChatLoading(false);
      }
    },
    [state, messages]
  );

  // ── System Map ──────────────────────────────────────────────────────────
  // Fetches the backend's already-enriched map for this session (same data
  // chat is grounded in) instead of re-deriving it client-side.
  const handleMap = useCallback(async () => {
    if (state.phase !== "ready") return;
    setMapLoading(true);
    setMapError(null);
    try {
      const data = await api.systemMap(state.report.session_id);
      setMapData(data);
    } catch (e: any) {
      setMapError(e.message || "Failed to load system map.");
    } finally {
      setMapLoading(false);
    }
  }, [state]);

  // ── Evict ───────────────────────────────────────────────────────────────
  const handleEvict = useCallback(async () => {
    if (state.phase !== "ready") return;
    try {
      await api.evictCache(state.report.session_id);
    } catch {
      /* best-effort */
    }
    setState({ phase: "idle" });
    setMessages([]);
    setMapData(null);
    setMapError(null);
  }, [state]);

  // ── Render ───────────────────────────────────────────────────────────────
  const isReady = state.phase === "ready";

  return (
    <div className="app">
      {/* ── Header ── */}
      <header className="app-header">
        <div className="header-brand">
          <Code2 size={22} />
          <span>RepoLens</span>
          <span className="header-badge">Gemini</span>
        </div>
        <nav className="header-nav">
          <a href="https://github.com" target="_blank" rel="noreferrer">Docs</a>
        </nav>
      </header>

      {/* ── Status bar (when repo is loaded) ── */}
      {isReady && state.phase === "ready" && (
        <StatusBar report={state.report} onEvict={handleEvict} />
      )}

      {/* ── Main ── */}
      <main className="app-main">
        {!isReady ? (
          /* Landing / Upload */
          <div className="landing">
            <div className="landing-copy">
              <h1>Understand any codebase<br /><em>in seconds</em></h1>
              <p>
                Drop a repo ZIP. RepoLens parses it, runs it through Gemini, and caches
                the structured result server-side — every question and the system map
                are answered from that one cache, no re-uploads, no drift.
              </p>
              <div className="feature-pills">
                <span>⚡ Session Caching</span>
                <span>🔍 File Filtering</span>
                <span>🗺 System Mapping</span>
              </div>
            </div>

            <div className="landing-upload">
              <UploadZone onUpload={handleUpload} loading={state.phase === "uploading"} />
              {state.phase === "error" && <p className="error-msg">{state.message}</p>}
            </div>
          </div>
        ) : (
          /* Workspace */
          <div className="workspace">
            <div className="tab-bar">
              <button
                className={`tab-btn ${tab === "chat" ? "active" : ""}`}
                onClick={() => setTab("chat")}
              >
                <Code2 size={15} /> Chat
              </button>
              <button
                className={`tab-btn ${tab === "map" ? "active" : ""}`}
                onClick={() => {
                  setTab("map");
                  if (!mapData && !mapLoading) handleMap();
                }}
              >
                <Map size={15} /> System Map
              </button>
            </div>

            <div className="tab-content">
              {tab === "chat" ? (
                <ChatPanel messages={messages} onSend={handleSend} loading={chatLoading} />
              ) : (
                <SystemMap
                  data={mapData}
                  error={mapError}
                  onGenerate={handleMap}
                  loading={mapLoading}
                />
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
