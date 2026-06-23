import os
import time
from typing import List, Optional

from fastapi import HTTPException
from google import genai
from google.genai import types
from google.genai.errors import APIError

from app.schemas import ChatTurn, LLMCodeAnalysis

# Configurable via env so a bad/retired model name doesn't require a code change.
# gemini-2.5-flash is the stable, broadly-available default; override with
# GEMINI_MODEL for anything else (e.g. gemini-3.5-flash) once you've confirmed
# it's enabled for your API key/project and quota tier.
DEFAULT_MODEL = "gemini-2.5-flash"

# How many prior turns of conversation to replay for context. Bounded to keep
# latency and token usage predictable on long chat sessions.
MAX_HISTORY_TURNS = 12

RETRYABLE_STATUS_CODES = {429, 500, 503, 504}
MAX_RETRIES = 3
BASE_RETRY_DELAY_SECONDS = 1.5


class GeminiAnalysisEngine:
    def __init__(self) -> None:
        self.model_name = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
        self._client: Optional[genai.Client] = None

    @property
    def client(self) -> genai.Client:
        """Lazily creates the client on first use rather than at import/startup
        time, so the rest of the server (health checks, etc.) still comes up
        cleanly if GEMINI_API_KEY isn't set yet, and the error message is shown
        exactly when and where it's actionable."""
        if self._client is None:
            if not os.environ.get("GEMINI_API_KEY"):
                raise HTTPException(
                    status_code=503,
                    detail="GEMINI_API_KEY is not set on the server. Set it and restart the backend.",
                )
            self._client = genai.Client()
        return self._client

    def _call_with_retry(self, fn, *args, **kwargs):
        last_err: Optional[Exception] = None
        for attempt in range(MAX_RETRIES):
            try:
                return fn(*args, **kwargs)
            except APIError as err:
                last_err = err
                code = getattr(err, "code", None)
                if code not in RETRYABLE_STATUS_CODES or attempt == MAX_RETRIES - 1:
                    raise
                time.sleep(BASE_RETRY_DELAY_SECONDS * (2 ** attempt))
        raise last_err  # pragma: no cover — unreachable, satisfies type checkers

    def analyze_codebase_payload(self, codebase_string: str) -> LLMCodeAnalysis:
        """Sends code blocks to Gemini and returns the narrow LLM-authored slice
        of the report (architecture summary, raw dependency links, vulnerabilities).
        tech_stack / entrypoints / modules are derived deterministically afterwards."""
        if not codebase_string.strip():
            raise ValueError("The parsed codebase payload string is completely empty.")

        system_prompt = (
            "Perform a deep static application security testing (SAST) architecture review "
            "and dependency audit on the following packed codebase payload. "
            "You must structure your JSON response according to the requested data schema."
        )

        try:
            response = self._call_with_retry(
                self.client.models.generate_content,
                model=self.model_name,
                contents=[f"Analyze the following codebase payload:\n\n{codebase_string}"],
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=LLMCodeAnalysis,
                    temperature=0.2,
                ),
            )

            if not response.text:
                raise HTTPException(
                    status_code=502,
                    detail="AI Engine Connection Error: the upstream model returned an empty response.",
                )

            return LLMCodeAnalysis.model_validate_json(response.text)

        except APIError as api_err:
            code = getattr(api_err, "code", None)
            print(f"[Gemini API Error] code={code} message={api_err}")
            if code == 429:
                raise HTTPException(
                    status_code=429,
                    detail="Gemini API quota/rate limit exceeded. Please wait a moment and try again.",
                )
            if code == 404:
                raise HTTPException(
                    status_code=502,
                    detail=(
                        f"Gemini model '{self.model_name}' was not found or is unavailable for this "
                        f"API key. Set GEMINI_MODEL to a model your key has access to."
                    ),
                )
            raise HTTPException(
                status_code=503,
                detail=f"Google API Service Unavailable: {getattr(api_err, 'message', str(api_err))}",
            )

        except ValueError as json_val_err:
            print(f"[Pydantic Structural Parsing Failure]: {json_val_err}")
            raise HTTPException(
                status_code=502,
                detail="The model's response didn't match the expected structured schema. Try again.",
            )

        except HTTPException:
            raise

        except Exception as unexpected_err:
            print(f"[Unexpected Client Loop Failure]: {unexpected_err}")
            raise HTTPException(status_code=500, detail=f"Internal pipeline failure: {unexpected_err}")

    def chat(self, context: str, question: str, history: List[ChatTurn]) -> str:
        """Multi-turn, context-grounded chat. Replays prior turns (capped) so
        follow-up questions stay coherent instead of being answered in isolation,
        and grounds every answer in the structured repo context (architecture,
        tech stack, entrypoints, modules, vulnerabilities) rather than a free-form
        dump of file paths."""
        if not question.strip():
            raise ValueError("Question must not be empty.")

        contents = []
        for turn in history[-MAX_HISTORY_TURNS:]:
            role = "user" if turn.role == "user" else "model"
            contents.append({"role": role, "parts": [{"text": turn.content}]})
        contents.append({"role": "user", "parts": [{"text": question}]})

        system_prompt = (
            "You are RepoSight, an expert codebase assistant having an ongoing conversation "
            "with a developer about a specific repository. Answer using ONLY the repository "
            "context below plus the conversation so far. Reference exact file paths when "
            "relevant. Be specific and avoid generic, repetitive answers — engage with the "
            "actual question asked. If the context doesn't contain the answer, say so honestly "
            "instead of guessing.\n\n"
            f"REPOSITORY CONTEXT:\n{context}"
        )

        try:
            response = self._call_with_retry(
                self.client.models.generate_content,
                model=self.model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.4,
                ),
            )
        except APIError as api_err:
            code = getattr(api_err, "code", None)
            print(f"[Gemini Chat API Error] code={code} message={api_err}")
            if code == 429:
                raise HTTPException(
                    status_code=429,
                    detail="Gemini API quota/rate limit exceeded. Please wait a moment and try again.",
                )
            raise HTTPException(
                status_code=503,
                detail=f"Google API Service Unavailable: {getattr(api_err, 'message', str(api_err))}",
            )

        if not response.text:
            raise HTTPException(status_code=502, detail="AI Engine returned an empty response.")

        return response.text
