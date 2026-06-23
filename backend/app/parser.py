import pathlib
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Set

from app.schemas import DependencyNode, ModuleInfo

# Canonical entrypoint filenames across common ecosystems. We match on exact
# basename (not substring!) to avoid false positives like "domain.py" or
# "maintenance.py" being mistaken for "main.py".
ENTRYPOINT_BASENAMES: Set[str] = {
    "main.py", "__main__.py", "app.py", "manage.py", "wsgi.py", "asgi.py",
    "server.py", "run.py",
    "main.go",
    "main.rs",
    "main.java", "Main.java",
    "index.js", "index.ts", "index.tsx", "index.jsx",
    "server.js", "server.ts",
    "app.js", "app.ts",
    "page.tsx", "page.jsx",  # Next.js App Router route entrypoints
    "layout.tsx",
}

LANGUAGE_BY_EXTENSION: Dict[str, str] = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".cpp": "C++",
    ".h": "C/C++",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
}


class FileFilter:
    def __init__(self, root: pathlib.Path):
        self.root = pathlib.Path(root)
        self.allowed_extensions = set(LANGUAGE_BY_EXTENSION.keys())
        self.ignored_dirs = {
            'node_modules', '.git', '__pycache__',
            'venv', 'env', '.venv', 'dist', 'build', '.next'
        }

    def collect(self) -> List[pathlib.Path]:
        """Recursively scans the directory and returns a sorted list of valid files."""
        valid_files = []
        for path in self.root.rglob('*'):
            if path.is_file():
                if any(part in self.ignored_dirs for part in path.parts):
                    continue
                if path.suffix.lower() in self.allowed_extensions:
                    valid_files.append(path)
        return sorted(valid_files, key=lambda p: str(p))


@dataclass
class IngestResult:
    packed_text: str
    file_paths: List[str] = field(default_factory=list)  # relative, posix-style, ground truth


def ingest_repository(repo_path_str: str) -> IngestResult:
    """Collects files, packs their text for the LLM, and records the ground-truth
    file list separately so downstream enrichment never has to rely on what the
    model chose to mention."""
    root_path = pathlib.Path(repo_path_str)
    filter_instance = FileFilter(root_path)
    allowed_files = filter_instance.collect()

    packed_codebase = []
    file_paths: List[str] = []

    for fp in allowed_files:
        rel_path = fp.relative_to(root_path).as_posix()
        file_paths.append(rel_path)
        try:
            file_contents = fp.read_text(encoding="utf-8", errors="replace")
            structured_block = (
                f"=== FILE SCHEMA START ===\n"
                f"PATH: {rel_path}\n"
                f"CONTENT:\n{file_contents}\n"
                f"=== FILE SCHEMA END ===\n"
            )
            packed_codebase.append(structured_block)
        except Exception:
            # File is in the ground-truth list either way; we just skip packing
            # its (unreadable) content for the LLM.
            continue

    return IngestResult(packed_text="\n".join(packed_codebase), file_paths=file_paths)


# ──────────────────────────────────────────────────────────────────────────
# Deterministic enrichment — runs after the LLM call, using the ground-truth
# file list as the source of truth instead of trusting model output blindly.
# ──────────────────────────────────────────────────────────────────────────

def detect_entrypoints(file_paths: List[str]) -> List[str]:
    """Exact-basename match against known entrypoint filenames. No substring
    matching, so 'domain.py' / 'maintenance.py' can never masquerade as 'main.py'."""
    found = [p for p in file_paths if p.rsplit("/", 1)[-1] in ENTRYPOINT_BASENAMES]
    return sorted(set(found))


def _normalize_module_ref(ref: str) -> str:
    """Turns an import string (relative path, dotted python module, etc.) into
    a path-like form comparable against the repo's actual file list."""
    ref = ref.strip().strip('"\'')
    ref = ref.replace("\\", "/")
    while ref.startswith("./"):
        ref = ref[2:]
    ref = ref.lstrip("/")
    for ext in (".py", ".js", ".jsx", ".ts", ".tsx"):
        if ref.endswith(ext):
            ref = ref[: -len(ext)]
            break
    if "." in ref and "/" not in ref:
        # looks like a dotted python module path, e.g. "app.parser"
        ref = ref.replace(".", "/")
    return ref


def classify_dependencies(
    dependency_tree: List[DependencyNode], file_paths: List[str]
) -> List[DependencyNode]:
    """Cross-checks each dependency's is_external_package flag against the
    ground-truth repo file list and corrects it deterministically. The LLM's
    guess is only trusted when it can't be verified either way."""
    internal_keys: Set[str] = set()
    for p in file_paths:
        norm = _normalize_module_ref(p)
        internal_keys.add(norm)
        internal_keys.add(norm.rsplit("/", 1)[-1])
        if norm.endswith("/index"):
            internal_keys.add(norm.rsplit("/", 1)[0])
        if norm.endswith("/__init__"):
            internal_keys.add(norm.rsplit("/", 1)[0])

    corrected: List[DependencyNode] = []
    for dep in dependency_tree:
        ref = dep.imported_module
        looks_relative = ref.startswith(".") or ref.startswith("/")
        norm = _normalize_module_ref(ref)
        basename = norm.rsplit("/", 1)[-1]
        is_external = dep.is_external_package

        if norm in internal_keys or basename in internal_keys:
            is_external = False
        elif looks_relative:
            # Relative-looking import that we couldn't match to a collected file
            # (e.g. it points at a file type we don't parse). Still local, not external.
            is_external = False

        corrected.append(
            DependencyNode(
                source_file=dep.source_file,
                imported_module=dep.imported_module,
                is_external_package=is_external,
            )
        )
    return corrected


def build_tech_stack(dependency_tree: List[DependencyNode], limit: int = 20) -> List[str]:
    seen: List[str] = []
    for dep in dependency_tree:
        if not dep.is_external_package:
            continue
        top = dep.imported_module.strip().strip('"\'').split("/")[0].split(".")[0]
        if top and top not in seen:
            seen.append(top)
    return sorted(seen)[:limit]


def build_modules(
    file_paths: List[str], dependency_tree: List[DependencyNode], entrypoints: List[str]
) -> List[ModuleInfo]:
    """Builds the module list from the *complete* ground-truth file set, not just
    the files the LLM happened to mention in dependency_tree — fixing system map
    generation that previously depended on incomplete/derived data."""
    imports_by_file: Dict[str, List[str]] = defaultdict(list)
    for dep in dependency_tree:
        imports_by_file[dep.source_file].append(dep.imported_module)

    entry_set = set(entrypoints)
    modules: List[ModuleInfo] = []

    for p in file_paths:
        name = p.rsplit("/", 1)[-1]
        ext = "." + name.rsplit(".", 1)[-1] if "." in name else ""
        stem = name[: -len(ext)] if ext else name
        imports = sorted(set(imports_by_file.get(p, [])))

        if p in entry_set:
            description = "Application entrypoint"
        elif imports:
            description = f"Depends on {len(imports)} module(s)"
        else:
            description = "Standalone module"

        modules.append(
            ModuleInfo(
                name=stem or "module",
                path=p,
                language=LANGUAGE_BY_EXTENSION.get(ext, "Other"),
                imports=imports,
                exports=[],
                description=description,
            )
        )
    return modules
