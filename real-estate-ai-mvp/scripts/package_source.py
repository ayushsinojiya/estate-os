"""Create and verify a movable source archive. No build products or secrets."""
import argparse
import hashlib
import os
from pathlib import Path
import tempfile
import zipfile

EXCLUDED_DIRS = {"node_modules", "target", "build", "dist", "coverage", "logs", ".git", ".idea", ".vscode", "__pycache__", ".pytest_cache", ".vite", ".cache", ".m2", ".npm"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".log", ".tsbuildinfo", ".zip", ".pem", ".key"}
REQUIRED = ["README.md", "frontend/package.json", "frontend/package-lock.json", "frontend/Dockerfile", "frontend/.env.example", "frontend/.dockerignore", "frontend/README.md", "backend/pom.xml", "backend/Dockerfile", "backend/.env.example", "backend/.dockerignore", "backend/README.md", "backend/src/main/resources/db/migration/V1__schema.sql", "database/README.md", "docs/architecture.md", "docs/api.md", "docs/setup.md", "docs/integration.md", "docs/troubleshooting.md", "docs/verification.md"]


def included(path, root):
    relative = path.relative_to(root)
    if any(part in EXCLUDED_DIRS for part in relative.parts):
        return False
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    if path.name.startswith(".env") and path.name != ".env.example":
        return False
    if path.name in {"backend.env", "frontend.env", ".DS_Store", "Thumbs.db"}:
        return False
    return path.is_file() and not path.is_symlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = (args.output or root.parent / "real-estate-ai-mvp.zip").resolve()
    files = sorted(p for p in root.rglob("*") if included(p, root))
    names = {p.relative_to(root).as_posix() for p in files}
    missing = set(REQUIRED) - names
    if missing:
        raise SystemExit("Missing required files: " + ", ".join(sorted(missing)))
    if not any(n.startswith("frontend/src/") and n.endswith(".tsx") for n in names):
        raise SystemExit("Frontend source missing")
    if not any(n.startswith("backend/src/test/") and n.endswith(".java") for n in names):
        raise SystemExit("Backend tests missing")
    if not any(n.startswith("database/migrations/") and n.endswith(".sql") for n in names):
        raise SystemExit("Distributed migrations missing")
    # Scan known runtime credentials if provided without ever printing values.
    secrets = [os.environ.get(key, "").encode() for key in ("DEMO_PASSWORD", "DATABASE_PASSWORD", "JWT_SECRET", "RAG_API_KEY", "VOICE_AGENT_API_KEY", "NOTIFICATION_API_KEY")]
    secrets = [value for value in secrets if len(value) >= 12]
    for path in files:
        data = path.read_bytes()
        if any(secret in data for secret in secrets):
            raise SystemExit("Runtime credential found in " + path.relative_to(root).as_posix())
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            archive.write(path, "real-estate-ai-mvp/" + path.relative_to(root).as_posix())
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise SystemExit("Archive CRC validation failed")
        for member in archive.namelist():
            parts = Path(member).parts
            if member.startswith(("/", "\\")) or ".." in parts or ":" in member:
                raise SystemExit("Unsafe archive member")
        # Extract only our freshly generated validated members into the workspace.
        with tempfile.TemporaryDirectory(prefix="source-check-", dir=root.parent) as directory:
            if not Path(directory).resolve().is_relative_to(root.parent.resolve()):
                raise SystemExit("Extraction verification directory escaped workspace")
            archive.extractall(directory)
            extracted = Path(directory) / "real-estate-ai-mvp"
            for path in files:
                relative = path.relative_to(root)
                if (extracted / relative).read_bytes() != path.read_bytes():
                    raise SystemExit("Extraction mismatch: " + str(relative))
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print(f"Verified {len(files)} source files; archive CRC, required files, exclusions, safe paths, and extracted bytes passed.")
    print(f"SHA256 {digest}")
    print(f"Archive: {output.name} ({output.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
