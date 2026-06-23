"use client";
import { Database, FileCode, Cpu, Trash2 } from "lucide-react";
import { AnalysisReport } from "../types/api";

interface Props {
  report: AnalysisReport;
  onEvict: () => void;
}

function fmt(n: number) {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n);
}

export default function StatusBar({ report, onEvict }: Props) {
  return (
    <div className="status-bar">
      <div className="status-pill">
        <span className="status-dot" />
        <span>Session Active</span>
      </div>

      <div className="status-stats">
        <span><FileCode size={13} /> {report.file_count} files</span>
        <span><Cpu size={13} /> ~{fmt(report.token_estimate)} tokens</span>
        <span><Database size={13} /> 30 min session TTL</span>
      </div>

      <button className="evict-btn" onClick={onEvict} title="Evict session and reset">
        <Trash2 size={13} />
        <span>Reset</span>
      </button>
    </div>
  );
}
