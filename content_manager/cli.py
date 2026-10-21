"""Headless entry point; GUI and CLI share the same validated planner."""
import argparse
import json
from pathlib import Path
import sys

from .core import Workspace, ContentError, apply_plan, plan_family, rollback_snapshot


def main(argv=None):
    parser = argparse.ArgumentParser(description="Voxel Horizons Content Manager")
    sub = parser.add_subparsers(dest="command")
    gui = sub.add_parser("gui", help="Start Tkinter desktop studio")
    gui.add_argument("--root", default=None)
    scan = sub.add_parser("scan", help="List existing items and packs (read-only)")
    scan.add_argument("root")
    plan = sub.add_parser("generate", help="Preview (or explicitly apply) a material family")
    plan.add_argument("root")
    plan.add_argument("source_id")
    plan.add_argument("--family", choices=["wood", "wool"], required=True)
    plan.add_argument("--target", default="mc-26.3")
    plan.add_argument("--strategy", choices=["alias", "clone"], default="alias")
    plan.add_argument("--texture-slot", default="")
    plan.add_argument("--only", default="", help="Comma-separated palette names")
    plan.add_argument("--include-dependencies", action="store_true", help="Generate matching material-prefixed animation/state/chest item references")
    plan.add_argument("--apply", action="store_true", help="Write proposed changes (backups created)")
    restore = sub.add_parser("rollback", help="Restore a generator snapshot if files are unchanged")
    restore.add_argument("pack_root")
    restore.add_argument("snapshot")
    for command in ("recover", "redo"):
        action = sub.add_parser(command, help="Recover interrupted writes" if command == "recover" else "Redo a rolled-back snapshot")
        action.add_argument("pack_root")
        action.add_argument("snapshot")
    pending = sub.add_parser("snapshots", help="List interrupted transactions (read-only)")
    pending.add_argument("pack_root")
    graph = sub.add_parser("references", help="Inspect known item/model/texture dependencies (read-only)")
    graph.add_argument("root")
    graph.add_argument("--node", help="Typed ID, for example item:voxel:oak_table")
    lint = sub.add_parser("lint", help="Read-only structural checks (NOT Java compiler verification)")
    lint.add_argument("root")
    lint.add_argument("--json", action="store_true", help="Emit a stable JSON report")
    lint.add_argument("--strict", action="store_true", help="Also fail on warnings")
    java_validate = sub.add_parser("validate-java", help="Stage sources and invoke VoxelCore JavaPackCompiler.validate")
    java_validate.add_argument("root")
    java_validate.add_argument("--classpath-file", required=True, help="File containing external Java dependency classpath")
    java_validate.add_argument("--target", default="mc-26.3")
    java_validate.add_argument("--allocations", default=None, help="Optional existing render allocations (read-only)")
    java_validate.add_argument("--java", default="java", help="JDK java executable")
    java_validate.add_argument("--timeout", type=int, default=180, help="Timeout seconds (1–600)")
    java_validate.add_argument("--json", action="store_true")
    recipe = sub.add_parser("recipe", help="Preview/apply a bounded multi-axis YAML/JSON recipe")
    recipe.add_argument("root")
    recipe.add_argument("recipe_file", help="Recipe YAML/JSON or a previously generated recipe manifest")
    recipe.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command in (None, "gui"):
            from .app import launch
            launch(getattr(args, "root", None))
        elif args.command == "scan":
            ws = Workspace(args.root)
            print(f"Packs: {', '.join(ws.packs)} | Items: {len(ws.items)} | Blocks: {len(ws.blocks)} | Glyphs: {len(ws.glyphs)}")
            for item_id in sorted(ws.items):
                print(f"{item_id}\t{ws.kind(item_id)}")
        elif args.command == "generate":
            ws = Workspace(args.root)
            selection = tuple(s.strip() for s in args.only.split(",") if s.strip()) if args.only else None
            result = plan_family(ws, args.source_id, args.family, args.target, args.strategy, args.texture_slot, selection, args.include_dependencies)
            print(result.summary())
            if args.apply:
                snapshot = apply_plan(result)
                print(f"Applied. Backup: {snapshot}" if snapshot else "No changes.")
            else:
                print("\nDRY RUN ONLY: add --apply to write these outputs.")
        elif args.command == "recipe":
            from .core import _read_yaml, _sha
            from .recipes import plan_recipe
            recipe_file = Path(args.recipe_file).resolve()
            data = _read_yaml(recipe_file)
            result = plan_recipe(Workspace(args.root), data.get("recipe", data))
            result.input_hashes[recipe_file] = _sha(recipe_file.read_bytes())
            print(result.summary())
            if args.apply:
                print(f"Applied. Snapshot: {apply_plan(result)}")
            else:
                print("DRY RUN ONLY: add --apply to write these outputs.")
        elif args.command == "lint":
            from .lint import lint_workspace
            report = lint_workspace(Workspace(args.root))
            print(json.dumps(report.as_dict(), indent=2) if args.json else report.format_text())
            return 1 if report.count("error") or (args.strict and report.count("warning")) else 0
        elif args.command == "validate-java":
            from .validation import validate_java
            result = validate_java(Workspace(args.root), args.classpath_file, args.target,
                                   args.allocations, args.java, args.timeout)
            if args.json:
                print(json.dumps(result.as_dict(), indent=2))
            else:
                print(f"VoxelCore Java validation: {'PASSED' if result.success else 'FAILED'} | target {result.target}")
                print(f"Staged {result.input_files} files | input SHA256 {result.input_sha256}")
                if result.stdout:
                    print(result.stdout)
                if result.stderr:
                    print(result.stderr, file=sys.stderr)
            return 0 if result.success else 1
        elif args.command == "references":
            from .assets import ReferenceGraph
            graph = ReferenceGraph(Workspace(args.root))
            edges = graph.incoming(args.node) + graph.outgoing(args.node) if args.node else graph.edges
            for edge in edges:
                print(f"{edge.source} --{edge.relation}--> {edge.target}")
            for message in graph.diagnostics:
                print(f"WARNING: {message}")
            print("Unused candidates (known graph only):", *graph.unused_candidates(), sep="\n")
        elif args.command == "snapshots":
            from .transactions import pending_snapshots
            for snapshot in pending_snapshots(Path(args.pack_root).resolve()):
                print(snapshot)
        elif args.command in ("recover", "redo"):
            from .transactions import restore
            restore(args.pack_root, args.snapshot, redo=args.command == "redo", recover=args.command == "recover")
            print("Snapshot recovered." if args.command == "recover" else "Snapshot reapplied.")
        elif args.command == "rollback":
            rollback_snapshot(Path(args.pack_root), Path(args.snapshot))
            print("Snapshot restored.")
        else:
            parser.print_help()
        return 0
    except (ContentError, OSError, ValueError, KeyError) as exc:
        if getattr(args, "command", None) == "validate-java" and getattr(args, "json", False):
            print(json.dumps({
                "schema_version": 1, "validator": "voxelcore-java-pack-validate",
                "compiler_classpath_attested": False, "staged_content_only": False,
                "runtime_paper_tested": False, "success": False,
                "target": getattr(args, "target", None),
                "error": str(exc),
                "process": {"exit_code": None, "stdout": "", "stderr": str(exc)}
            }, indent=2))
        elif getattr(args, "command", None) == "lint" and getattr(args, "json", False):
            print(json.dumps({
                "schema_version": 1,
                "validator": "content-manager-offline-structural",
                "authoritative": False,
                "summary": {"packs": 0, "items": 0, "blocks": 0, "glyphs": 0,
                            "errors": 1, "warnings": 0, "info": 0},
                "findings": [{"severity": "error", "code": "workspace-invalid", "message": str(exc)}]
            }, indent=2))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
