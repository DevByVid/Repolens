import gc
import os
import pathlib
import shutil
import time
import uuid
import zipfile

from dotenv import load_dotenv

# Must run before app.gemini_client (or anything else) reads os.environ —
# a .env file on disk does nothing on its own unless something loads it.
# Resolved relative to this file (backend/app/main.py -> backend/.env) so it
# works regardless of which directory `uvicorn` is launched from.
load_dotenv(pathlib.Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI, UploadFile, File, HTTPException


from app.parser import (
    ingest_repository,
    classify_dependencies,
    detect_entrypoints,
    build_tech_stack,
    build_modules,
)
from app.gemini_client import GeminiAnalysisEngine
from app.schemas import (
    ProjectAnalysisReport,
    SystemMapResponse,
    ChatRequest,
    ChatResponse,
    EvictRequest,
)

app = FastAPI(
    title="RepoSight Analyzer Engine",
    description="Production-Ready High-Throughput Code Processing Pipeline",
)

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
ai_engine = GeminiAnalysisEngine()

# ──────────────────────────────────────────────────────────────────────────
# Single, session-scoped cache. Every endpoint (analyze / chat / system-map /
# evict) reads and writes this same store, keyed by session_id — there is no
# second parallel cache anymore, and no global "latest" that different users'
# requests could clobber.
# ──────────────────────────────────────────────────────────────────────────
SESSIONS: dict[str, dict] = {}
SESSION_TTL_SECONDS = 30 * 60  # matches the "30 min TTL" shown in the UI

MAX_ZIP_SIZE_BYTES = 20 * 1024 * 1024
MAX_UNCOMPRESSED_SIZE_BYTES = 100 * 1024 * 1024


def _purge_expired_sessions() -> None:
    now = time.time()
    expired = [sid for sid, s in SESSIONS.items() if now - s["created_at"] > SESSION_TTL_SECONDS]
    for sid in expired:
        SESSIONS.pop(sid, None)


def _get_session_report(session_id: str) -> ProjectAnalysisReport:
    _purge_expired_sessions()
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail="Session not found or expired. Please re-upload the repository.",
        )
    return session["report"]


def is_safe_path(base_dir: pathlib.Path, target_path: pathlib.Path) -> bool:
    """Mitigates Zip Slip by ensuring target paths stay within the temp folder boundary."""
    try:
        resolved_base = base_dir.resolve(strict=True)
        resolved_target = target_path.resolve()
        return resolved_base in resolved_target.parents or resolved_base == resolved_target
    except (OSError, ValueError):
        return False


def _safe_remove_file(path: pathlib.Path, attempts: int = 6, base_delay: float = 0.25) -> None:
    """Removes a single file with retry/backoff. On Windows, antivirus scanning
    or a not-yet-released handle from the just-closed read can make the very
    next unlink() raise PermissionError; a single fixed sleep (the previous
    approach) just narrows the race instead of closing it. Retrying with
    growing backoff, plus a gc.collect() to force any lingering file objects
    closed, makes cleanup actually reliable instead of crashing the request."""
    last_err: Exception | None = None
    for attempt in range(attempts):
        try:
            if path.exists():
                os.remove(path)
            return
        except FileNotFoundError:
            return
        except (PermissionError, OSError) as e:
            last_err = e
            gc.collect()
            time.sleep(base_delay * (attempt + 1))
    print(f"Cleanup warning: could not remove file {path}: {last_err}")


def _safe_rmtree(path: pathlib.Path, attempts: int = 6, base_delay: float = 0.25) -> None:
    last_err: Exception | None = None
    for attempt in range(attempts):
        try:
            if path.exists():
                shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except (PermissionError, OSError) as e:
            last_err = e
            gc.collect()
            time.sleep(base_delay * (attempt + 1))
    print(f"Cleanup warning: could not remove directory {path}: {last_err}")


@app.get("/api/health")
def health_check():
    """Simple endpoint to verify our server is active and running."""
    return {"status": "healthy", "service": "RepoSight Backend"}


@app.post("/api/analyze", response_model=ProjectAnalysisReport)
async def analyze_codebase(file: UploadFile = File(...)):
    """Ingests a repo zip, runs it through the parser + Gemini, deterministically
    enriches the result (entrypoints/tech_stack/modules from the ground-truth file
    list, dependency classification cross-checked against it), caches the final
    report under a fresh session_id, and returns it in a single round trip."""
    unique_id = uuid.uuid4().hex[:8]
    temp_dir = pathlib.Path(f"./temp_repo_{unique_id}").resolve()
    zip_path = pathlib.Path(f"./temp_{unique_id}.zip").resolve()

    try:
        with open(zip_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        await file.close()  # release the upload's spooled file handle promptly

        if zip_path.stat().st_size > MAX_ZIP_SIZE_BYTES:
            raise HTTPException(status_code=413, detail="Uploaded file exceeds compressed archive limit (20MB).")

        temp_dir.mkdir(parents=True, exist_ok=True)

        uncompressed_total_bytes = 0
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            for member in zip_ref.infolist():
                uncompressed_total_bytes += member.file_size
                if uncompressed_total_bytes > MAX_UNCOMPRESSED_SIZE_BYTES:
                    raise HTTPException(status_code=400, detail="Decompression halted: uncompressed payload limit exceeded (100MB).")

                target_member_path = (temp_dir / member.filename).resolve()
                if not is_safe_path(temp_dir, target_member_path):
                    raise HTTPException(status_code=400, detail=f"Malicious directory traversal path detected: {member.filename}")

            for member in zip_ref.infolist():
                zip_ref.extract(member, temp_dir)
        # zip_ref is closed here (context manager exit) before we ever read the
        # extracted files or attempt cleanup — avoids holding the archive handle
        # open across the parse step.

        ingested = ingest_repository(str(temp_dir))
        llm_result = ai_engine.analyze_codebase_payload(ingested.packed_text)

        corrected_deps = classify_dependencies(llm_result.dependency_tree, ingested.file_paths)
        entrypoints = detect_entrypoints(ingested.file_paths)
        tech_stack = build_tech_stack(corrected_deps)
        modules = build_modules(ingested.file_paths, corrected_deps, entrypoints)

        session_id = uuid.uuid4().hex[:12]
        report = ProjectAnalysisReport(
            session_id=session_id,
            high_level_architecture=llm_result.high_level_architecture,
            dependency_tree=corrected_deps,
            vulnerabilities=llm_result.vulnerabilities,
            tech_stack=tech_stack,
            entrypoints=entrypoints,
            modules=modules,
            file_count=len(ingested.file_paths),
            token_estimate=len(ingested.packed_text) // 4,
        )

        SESSIONS[session_id] = {"report": report, "created_at": time.time()}
        return report

    except HTTPException:
        raise
    except ValueError as val_ex:
        raise HTTPException(status_code=400, detail=str(val_ex))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid ZIP archive.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline execution failure: {str(e)}")

    finally:
        _safe_remove_file(zip_path)
        _safe_rmtree(temp_dir)


def _build_chat_context(report: ProjectAnalysisReport) -> str:
    """Assembles the actual structured repo context (architecture, tech stack,
    entrypoints, module graph, vulnerabilities) that gets grounded into the
    prompt — replacing the old approach of stringifying raw Python lists."""
    lines = [
        "ARCHITECTURE SUMMARY:",
        report.high_level_architecture,
        "",
        f"TECH STACK: {', '.join(report.tech_stack) or 'none detected'}",
        f"ENTRYPOINTS: {', '.join(report.entrypoints) or 'none detected'}",
        "",
        "MODULES:",
    ]
    for m in report.modules[:80]:
        imp = f" -> imports: {', '.join(m.imports[:6])}" if m.imports else ""
        lines.append(f"  - {m.path} [{m.language}]{imp}")

    if report.vulnerabilities:
        lines.append("")
        lines.append("KNOWN ISSUES / VULNERABILITIES:")
        for v in report.vulnerabilities[:30]:
            lines.append(f"  - [{v.risk_level}] {v.target_file}: {v.issue_type} — {v.explanation}")

    return "\n".join(lines)


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    report = _get_session_report(req.session_id)
    context = _build_chat_context(report)
    try:
        answer = ai_engine.chat(context=context, question=req.question, history=req.history)
    except ValueError as val_ex:
        raise HTTPException(status_code=400, detail=str(val_ex))
    return ChatResponse(answer=answer, session_id=req.session_id)


@app.get("/api/system-map", response_model=SystemMapResponse)
async def system_map(session_id: str):
    """Reads the same cached, already-enriched report used by /api/chat — the
    map is never regenerated from scratch or re-derived client-side, so it can't
    drift from what the rest of the app is using."""
    report = _get_session_report(session_id)
    return SystemMapResponse(
        modules=report.modules,
        entrypoints=report.entrypoints,
        tech_stack=report.tech_stack,
        architecture_summary=report.high_level_architecture,
    )


@app.post("/api/evict")
async def evict(req: EvictRequest):
    SESSIONS.pop(req.session_id, None)
    return {"status": "evicted", "session_id": req.session_id}
