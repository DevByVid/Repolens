// types/api.ts — mirrors backend/app/schemas.py exactly. Keep these two in sync.

export interface DependencyNode {
  source_file: string;
  imported_module: string;
  is_external_package: boolean;
}

export interface SecurityFinding {
  target_file: string;
  risk_level: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | string;
  issue_type: string;
  explanation: string;
  patch_recommendation: string;
}

export interface ModuleInfo {
  name: string;
  path: string;
  language: string;
  imports: string[];
  exports: string[];
  description: string;
}

// What /api/analyze returns, and what gets held in app state for the
// lifetime of a session. This is the single source of truth on the frontend —
// chat and the system map both read out of this same object's session_id.
export interface AnalysisReport {
  session_id: string;
  high_level_architecture: string;
  dependency_tree: DependencyNode[];
  vulnerabilities: SecurityFinding[];
  tech_stack: string[];
  entrypoints: string[];
  modules: ModuleInfo[];
  file_count: number;
  token_estimate: number;
}

export interface SystemMapResponse {
  modules: ModuleInfo[];
  entrypoints: string[];
  tech_stack: string[];
  architecture_summary: string;
}

export interface ChatHistoryTurn {
  role: "user" | "assistant";
  content: string;
}

export interface ChatRequest {
  session_id: string;
  question: string;
  history: ChatHistoryTurn[];
}

export interface ChatResponse {
  answer: string;
  session_id: string;
}

export type AppState =
  | { phase: "idle" }
  | { phase: "uploading" }
  | { phase: "ready"; report: AnalysisReport }
  | { phase: "error"; message: string };

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
}
