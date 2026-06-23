"use client";
import { useState } from "react";
import { Layers, ChevronDown, ChevronRight, Globe, Cpu, ArrowRight, AlertTriangle } from "lucide-react";
import { SystemMapResponse, ModuleInfo } from "../types/api";

interface Props {
  data: SystemMapResponse | null;
  error: string | null;
  onGenerate: () => void;
  loading: boolean;
}

function ModuleCard({ mod }: { mod: ModuleInfo }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`module-card lang-${mod.language.toLowerCase()}`}>
      <button className="module-header" onClick={() => setOpen((o) => !o)}>
        <span className="module-lang">{mod.language}</span>
        <span className="module-name">{mod.name}</span>
        <span className="module-path">{mod.path}</span>
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      </button>
      {open && (
        <div className="module-body">
          <p className="module-desc">{mod.description}</p>
          {mod.imports.length > 0 && (
            <div className="module-deps">
              <span className="dep-label">Imports</span>
              <div className="dep-chips">
                {mod.imports.map((i) => <span key={i} className="dep-chip import">{i}</span>)}
              </div>
            </div>
          )}
          {mod.exports.length > 0 && (
            <div className="module-deps">
              <span className="dep-label">Exports</span>
              <div className="dep-chips">
                {mod.exports.map((e) => <span key={e} className="dep-chip export">{e}</span>)}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function SystemMap({ data, error, onGenerate, loading }: Props) {
  return (
    <div className="sysmap-panel">
      <div className="sysmap-header">
        <div className="sysmap-title">
          <Layers size={20} />
          <h2>System Architecture Map</h2>
        </div>
        <button className="generate-btn" onClick={onGenerate} disabled={loading}>
          {loading ? "Mapping…" : "Regenerate Map"}
        </button>
      </div>

      {!data && !loading && !error && (
        <div className="sysmap-empty">
          <Cpu size={36} />
          <p>Click <strong>Regenerate Map</strong> to produce a deterministic dependency graph</p>
          <p className="sysmap-note">Entrypoints, tech stack, and modules are derived server-side from the parsed file list</p>
        </div>
      )}

      {error && !loading && (
        <div className="sysmap-empty">
          <AlertTriangle size={36} />
          <p>{error}</p>
        </div>
      )}

      {data && !loading && (
        <>
          <div className="arch-summary">
            <p>{data.architecture_summary}</p>
          </div>

          <div className="sysmap-meta">
            <div className="meta-block">
              <Globe size={14} />
              <span>Entrypoints</span>
              <div className="dep-chips">
                {data.entrypoints.length > 0 ? (
                  data.entrypoints.map((e) => (
                    <span key={e} className="dep-chip entry">{e}</span>
                  ))
                ) : (
                  <span className="dep-chip">None detected</span>
                )}
              </div>
            </div>
            <div className="meta-block">
              <Cpu size={14} />
              <span>Tech Stack</span>
              <div className="dep-chips">
                {data.tech_stack.length > 0 ? (
                  data.tech_stack.map((t) => (
                    <span key={t} className="dep-chip tech">{t}</span>
                  ))
                ) : (
                  <span className="dep-chip">None detected</span>
                )}
              </div>
            </div>
          </div>

          <div className="modules-list">
            <h3>{data.modules.length} Modules</h3>
            {data.modules.map((m) => (
              <ModuleCard key={m.path} mod={m} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
