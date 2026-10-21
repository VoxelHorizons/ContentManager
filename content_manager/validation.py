"""Opt-in, isolated VoxelCore JavaPackCompiler.validate bridge.

This module never builds a ZIP, publishes files, or writes allocation manifests
into the selected workspace. Its JVM classpath is supplied by the operator;
the actual dependency binaries are not cryptographically attested here.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile

from .core import ContentError, SUPPORTED_TARGETS, Workspace

SUCCESS = re.compile(r"^VOXELCORE_VALIDATION_OK\t([a-z0-9.-]+)\t(\d+)\t(\d+)\t(\d+)\r?$", re.M)
MAX_FILES = 50000
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
MAX_SINGLE_BYTES = 128 * 1024 * 1024
MAX_LOG_BYTES = 128 * 1024

# Java source-file launch mode keeps the bridge available in installed Python
# packages and PyInstaller desktop bundles, without a precompiled unversioned jar.
BRIDGE_SOURCE = r"""
import java.nio.file.Path;
import java.nio.file.Paths;
import org.voxelhorizons.pack.JavaPackBuildResult;
import org.voxelhorizons.pack.JavaPackCompiler;
import org.voxelhorizons.pack.JavaPackTarget;

class VoxelCoreValidationBridge {
    public static void main(String[] args) {
        if (args.length != 3) {
            System.err.println("Usage: VoxelCoreValidationBridge <content-root> <allocations> <target>");
            System.exit(2);
        }
        JavaPackTarget target = JavaPackTarget.byId(args[2]);
        if (target == null) {
            System.err.println("Unsupported VoxelCore target: " + args[2]);
            System.exit(2);
        }
        try {
            Path contentRoot = Paths.get(args[0]);
            Path allocations = Paths.get(args[1]);
            JavaPackBuildResult result = new JavaPackCompiler().validate(
                    contentRoot, allocations, target);
            System.out.println("VOXELCORE_VALIDATION_OK\t" + target.id() + "\t"
                    + result.renderedItems() + "\t"
                    + result.renderedBlocks() + "\t"
                    + result.copiedAssets());
        } catch (Exception error) {
            System.err.println("VOXELCORE_VALIDATION_FAILED: " + error.getMessage());
            System.exit(1);
        }
    }
}
"""


@dataclass(frozen=True)
class JavaValidationResult:
    success: bool
    target: str
    input_files: int
    input_sha256: str
    rendered_items: int | None
    rendered_blocks: int | None
    copied_assets: int | None
    stdout: str
    stderr: str
    exit_code: int

    def as_dict(self) -> dict:
        return {
            "schema_version": 1,
            "validator": "voxelcore-java-pack-validate",
            "compiler_classpath_attested": False,
            "staged_content_only": True,
            "runtime_paper_tested": False,
            "success": self.success,
            "target": self.target,
            "source": {"files": self.input_files, "sha256": self.input_sha256},
            "counts": {
                "rendered_items": self.rendered_items,
                "rendered_blocks": self.rendered_blocks,
                "copied_assets": self.copied_assets,
            },
            "process": {
                "exit_code": self.exit_code,
                "stdout": self.stdout,
                "stderr": self.stderr,
            },
        }


def _is_link_or_reparse(path: Path) -> bool:
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return path.is_symlink() or bool(attributes & 0x400)


def _stage(workspace: Workspace, target_root: Path) -> tuple[int, str]:
    """Copy only selected authored packs, reject links/special files and drift."""
    count = 0
    byte_count = 0
    digest = hashlib.sha256()
    for pack in sorted(workspace.packs.values(), key=lambda p: p.namespace):
        if _is_link_or_reparse(pack.root):
            raise ContentError(f"Linked pack directory is not supported: {pack.root}")
        destination_root = target_root / pack.root.name
        destination_root.mkdir(parents=True, exist_ok=True)
        for directory, folders, files in os.walk(pack.root, followlinks=False):
            path = Path(directory)
            if _is_link_or_reparse(path):
                raise ContentError(f"Linked input directory is not supported: {path}")
            safe_folders = []
            for name in sorted(folders):
                candidate = path / name
                if name in (".contentmanager", ".git", "__pycache__"):
                    continue
                if _is_link_or_reparse(candidate) or not stat.S_ISDIR(candidate.lstat().st_mode):
                    raise ContentError(f"Linked/special input directory: {candidate}")
                safe_folders.append(name)
            folders[:] = safe_folders
            for name in sorted(files):
                source = path / name
                info = source.lstat()
                if _is_link_or_reparse(source) or not stat.S_ISREG(info.st_mode):
                    raise ContentError(f"Linked/special input file: {source}")
                count += 1
                byte_count += info.st_size
                if (count > MAX_FILES or byte_count > MAX_TOTAL_BYTES
                        or info.st_size > MAX_SINGLE_BYTES):
                    raise ContentError("Validation snapshot exceeds file/byte safety limits")
                relative = source.relative_to(pack.root)
                output = destination_root / relative
                output.parent.mkdir(parents=True, exist_ok=True)
                file_digest = hashlib.sha256()
                with source.open("rb") as input_stream, output.open("wb") as output_stream:
                    for chunk in iter(lambda: input_stream.read(1024 * 1024), b""):
                        output_stream.write(chunk)
                        file_digest.update(chunk)
                after = source.lstat()
                if (after.st_size != info.st_size or after.st_mtime_ns != info.st_mtime_ns
                        or _is_link_or_reparse(source)):
                    raise ContentError(f"Source changed during Java validation snapshot: {source}")
                verify_digest = hashlib.sha256()
                with source.open("rb") as check_stream:
                    for chunk in iter(lambda: check_stream.read(1024 * 1024), b""):
                        verify_digest.update(chunk)
                if verify_digest.digest() != file_digest.digest():
                    raise ContentError(f"Source changed while staging Java validation: {source}")
                digest.update(pack.namespace.encode("utf-8") + b"\0"
                              + relative.as_posix().encode("utf-8") + b"\0"
                              + file_digest.digest())
    return count, digest.hexdigest()


def _classpath(path: Path | str) -> str:
    source = Path(path).expanduser().resolve()
    if not source.is_file() or source.stat().st_size > 128 * 1024:
        raise ContentError(f"Classpath file missing or oversized: {source}")
    entries = source.read_text(encoding="utf-8-sig").strip().split(os.pathsep)
    if not entries or len(entries) > 2048:
        raise ContentError("Classpath file has no entries or exceeds the entry limit")
    verified = []
    for entry in entries:
        if not entry.strip():
            raise ContentError("Classpath file contains an empty component")
        component = Path(entry.strip()).expanduser()
        if not component.is_absolute():
            component = source.parent / component
        component = component.resolve()
        if not component.exists() or (not component.is_dir() and
                                     not (component.is_file() and component.suffix.lower() == ".jar")):
            raise ContentError(f"Missing or invalid Java classpath component: {component}")
        verified.append(str(component))
    return os.pathsep.join(verified)


def _read_log(path: Path) -> str:
    with path.open("rb") as stream:
        data = stream.read(MAX_LOG_BYTES + 1)
    return data[:MAX_LOG_BYTES].decode("utf-8", errors="replace") + (
        "\n[output truncated]" if len(data) > MAX_LOG_BYTES else ""
    )


def validate_java(
    workspace: Workspace, classpath_file: Path | str, target: str = "mc-26.3",
    allocations: Path | str | None = None, java: str = "java",
    timeout_seconds: int = 180,
) -> JavaValidationResult:
    """Validate an isolated snapshot using the externally supplied VoxelCore runtime."""
    if target not in SUPPORTED_TARGETS:
        raise ContentError(f"Unsupported authoring target: {target}")
    if not (1 <= timeout_seconds <= 600):
        raise ContentError("Java validation timeout must be 1–600 seconds")
    classpath = _classpath(classpath_file)
    with tempfile.TemporaryDirectory(prefix="voxelcore-java-validate-") as temp:
        staging = Path(temp)
        root = staging / "content"
        root.mkdir()
        count, digest = _stage(workspace, root)
        allocation_target = staging / "render-allocations.yml"
        if allocations is not None:
            allocation_source = Path(allocations).expanduser().resolve()
            if (not allocation_source.is_file() or _is_link_or_reparse(allocation_source)
                    or allocation_source.stat().st_size > 32 * 1024 * 1024):
                raise ContentError(f"Invalid allocation source file: {allocation_source}")
            shutil.copyfile(allocation_source, allocation_target)
        source = staging / "VoxelCoreValidationBridge.java"
        source.write_text(BRIDGE_SOURCE, encoding="utf-8")
        stdout_path, stderr_path = staging / "stdout.log", staging / "stderr.log"
        command = [
            java, "--class-path", classpath, str(source),
            str(root), str(allocation_target), target,
        ]
        try:
            with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
                process = subprocess.run(command, cwd=staging, stdout=stdout,
                                         stderr=stderr, timeout=timeout_seconds,
                                         check=False)
        except FileNotFoundError as exc:
            raise ContentError(f"Java executable unavailable: {java}") from exc
        except subprocess.TimeoutExpired as exc:
            raise ContentError(f"Java validation exceeded {timeout_seconds}s; no source files were written") from exc
        stdout, stderr = _read_log(stdout_path), _read_log(stderr_path)
        match = SUCCESS.search(stdout)
        success = process.returncode == 0 and match is not None and match[1] == target
        if process.returncode == 0 and not success:
            stderr += "\nJava validation finished without a matching success marker; refusing to certify."
        return JavaValidationResult(
            success, target, count, digest,
            int(match[2]) if success else None,
            int(match[3]) if success else None,
            int(match[4]) if success else None,
            stdout, stderr, process.returncode,
        )
