"""Headless entry point; GUI and CLI share the same validated planner."""
import argparse
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
    plan.add_argument("--target", default="mc-26.2")
    plan.add_argument("--strategy", choices=["alias", "clone"], default="alias")
    plan.add_argument("--texture-slot", default="")
    plan.add_argument("--only", default="", help="Comma-separated palette names")
    plan.add_argument("--apply", action="store_true", help="Write proposed changes (backups created)")
    restore = sub.add_parser("rollback", help="Restore a generator snapshot if files are unchanged")
    restore.add_argument("pack_root")
    restore.add_argument("snapshot")
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
            result = plan_family(ws, args.source_id, args.family, args.target, args.strategy, args.texture_slot, selection)
            print(result.summary())
            if args.apply:
                snapshot = apply_plan(result)
                print(f"Applied. Backup: {snapshot}" if snapshot else "No changes.")
            else:
                print("\nDRY RUN ONLY: add --apply to write these outputs.")
        elif args.command == "rollback":
            rollback_snapshot(Path(args.pack_root), Path(args.snapshot))
            print("Snapshot restored.")
        else:
            parser.print_help()
        return 0
    except (ContentError, OSError, ValueError, KeyError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
