"""Read-only structural diagnostics for VoxelCore content sources.

These checks are intentionally not a replacement for VoxelCore Java pack
validation, Minecraft resource pack loading, or addon runtime verification.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .assets import ReferenceGraph
from .core import ContentError, Workspace

Severity = Literal["error", "warning", "info"]


@dataclass(frozen=True)
class LintFinding:
    severity: Severity
    code: str
    message: str

    def as_dict(self) -> dict:
        return {"severity": self.severity, "code": self.code, "message": self.message}


@dataclass
class LintReport:
    packs: int
    items: int
    blocks: int
    glyphs: int
    findings: list[LintFinding]

    def count(self, severity: Severity) -> int:
        return sum(f.severity == severity for f in self.findings)

    def as_dict(self) -> dict:
        return {
            "schema_version": 1,
            "validator": "content-manager-offline-structural",
            "authoritative": False,
            "summary": {
                "packs": self.packs,
                "items": self.items,
                "blocks": self.blocks,
                "glyphs": self.glyphs,
                "errors": self.count("error"),
                "warnings": self.count("warning"),
                "info": self.count("info"),
            },
            "findings": [finding.as_dict() for finding in self.findings],
        }

    def format_text(self) -> str:
        lines = [
            "Content Manager offline structural lint (NOT VoxelCore Java validation)",
            f"Packs: {self.packs} | Items: {self.items} | Blocks: {self.blocks} | UI: {self.glyphs}",
            f"Errors: {self.count('error')} | Warnings: {self.count('warning')} | Info: {self.count('info')}",
        ]
        lines.extend(f"{f.severity.upper()} [{f.code}] {f.message}" for f in self.findings)
        if not self.findings:
            lines.append("No structural problems found by these limited checks.")
        lines.append("Validate the resource pack with VoxelCore on a staging server before deployment.")
        return "\n".join(lines)


def lint_workspace(workspace: Workspace) -> LintReport:
    """Build deterministic diagnostics without changing authored content."""
    graph = ReferenceGraph(workspace)
    findings: list[LintFinding] = []
    for message in graph.diagnostics:
        if message.startswith("External vanilla parent unverified:"):
            findings.append(LintFinding("info", "external-vanilla-parent", message))
        elif message.startswith("Missing texture "):
            findings.append(LintFinding("error", "missing-texture", message))
        elif "Missing item " in message:
            findings.append(LintFinding("error", "missing-item", message))
        else:
            findings.append(LintFinding("error", "invalid-reference", message))

    for pack in workspace.packs.values():
        for dependency in pack.dependencies:
            if dependency not in workspace.packs and dependency != "minecraft":
                findings.append(LintFinding(
                    "warning", "dependency-not-loaded",
                    f"Pack {pack.namespace} depends on {dependency!r}, which is not loaded in this workspace"
                ))

    for ident in sorted(workspace.items):
        try:
            effective = workspace.resolve_item(ident)
            props = effective.get("properties") or {}
            if not isinstance(props, dict):
                raise ContentError("properties must be a mapping")
            if props.get("furniture") is not None and props.get("vehicle") is not None:
                findings.append(LintFinding(
                    "warning", "multiple-addon-properties",
                    f"{ident} defines both furniture and vehicle properties"
                ))
        except ContentError:
            # The reference graph already records invalid item inheritance.
            pass

    for group in graph.duplicate_models():
        findings.append(LintFinding(
            "info", "duplicate-model-bytes",
            "Models share identical JSON bytes (may be intentional): " + ", ".join(group)
        ))

    findings.sort(key=lambda f: (
        {"error": 0, "warning": 1, "info": 2}[f.severity], f.code, f.message
    ))
    return LintReport(
        packs=len(workspace.packs), items=len(workspace.items),
        blocks=len(workspace.blocks), glyphs=len(workspace.glyphs),
        findings=findings
    )
