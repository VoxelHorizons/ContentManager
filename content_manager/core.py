"""Workspace discovery, variant plans and reversible updates to VoxelCore content.

Existing authored content is NEVER rewritten by the generator. The initial
implementation generates new child item YAML files and model JSON files only.
No VoxelCore render allocation or server runtime state is modified here.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import time
from typing import Any, Literal

import yaml

ID_PATTERN = re.compile(r"^[a-z0-9._-]+$")
COLORS = (
    "white", "orange", "magenta", "light_blue", "yellow", "lime", "pink", "gray",
    "light_gray", "cyan", "purple", "blue", "brown", "green", "red", "black",
)
WOODS = (
    "oak", "spruce", "birch", "jungle", "acacia", "dark_oak", "mangrove",
    "cherry", "bamboo", "crimson", "warped", "pale_oak",
)
# Deliberately not guessing old pre-flattening texture/resource paths.
SUPPORTED_TARGETS = ("mc-1.13.2", "mc-1.14.4", "mc-1.19.4", "mc-1.20.5", "mc-1.21.4", "mc-26.2")


class ContentError(Exception):
    """An expected user-facing validation or source conflict."""


class UniqueSafeLoader(yaml.SafeLoader):
    def compose_node(self, parent, index):
        self._cm_depth = getattr(self, "_cm_depth", 0) + 1
        self._cm_nodes = getattr(self, "_cm_nodes", 0) + 1
        self._cm_aliases = getattr(self, "_cm_aliases", 0) + int(self.check_event(yaml.AliasEvent))
        if self._cm_depth > 64 or self._cm_nodes > 100000 or self._cm_aliases > 256:
            raise ContentError("YAML nesting/node/alias safety limit exceeded")
        try:
            return super().compose_node(parent, index)
        finally:
            self._cm_depth -= 1


def _unique_mapping(loader: yaml.Loader, node: yaml.nodes.MappingNode) -> dict:
    explicit = set()
    for key_node, _ in node.value:
        if key_node.tag == "tag:yaml.org,2002:merge":
            continue
        key = loader.construct_object(key_node, deep=True)
        try:
            if key in explicit:
                raise ContentError(f"Duplicate YAML key: {key!r}")
            explicit.add(key)
        except TypeError as ex:
            raise ContentError("Unhashable YAML mapping key") from ex
    loader.flatten_mapping(node)
    result = {}
    for key_node, value_node in node.value:
        result[loader.construct_object(key_node, deep=True)] = loader.construct_object(value_node, deep=True)
    return result


UniqueSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping
)


def _read_yaml(path: Path) -> dict:
    if path.stat().st_size > 3 * 1024 * 1024:
        raise ContentError(f"YAML exceeds 3 MiB safety limit: {path}")
    try:
        data = yaml.load(path.read_text(encoding="utf-8-sig"), Loader=UniqueSafeLoader)
    except (yaml.YAMLError, UnicodeError) as ex:
        raise ContentError(f"Invalid YAML in {path}: {ex}") from ex
    if not isinstance(data, dict):
        raise ContentError(f"Expected YAML mapping in {path}")
    return data


def _validate_id(value: str) -> str:
    if not isinstance(value, str):
        raise ContentError(f"ContentID segment must be a string: {value!r}")
    result = value.strip().lower()
    if not ID_PATTERN.fullmatch(result):
        raise ContentError(f"Invalid ContentID segment: {value!r}")
    return result


def canonical_id(value: str, default_namespace: str) -> str:
    if not isinstance(value, str):
        raise ContentError(f"ContentID must be a string: {value!r}")
    parts = value.split(":")
    if len(parts) == 1:
        return f"{_validate_id(default_namespace)}:{_validate_id(parts[0])}"
    if len(parts) == 2:
        return f"{_validate_id(parts[0])}:{_validate_id(parts[1])}"
    raise ContentError(f"Invalid ContentID: {value}")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _bytes(path: Path) -> bytes | None:
    return path.read_bytes() if path.is_file() else None


def _ensure_inside(root: Path, candidate: Path) -> Path:
    root = root.resolve()
    target = candidate.resolve(strict=False)
    if not target.is_relative_to(root):
        raise ContentError(f"Path escapes content pack root: {candidate}")
    # Also reject symlinks within the workspace; never traverse an externally
    # redirected pack root via a generated path.
    current = candidate
    while current != root and current != current.parent:
        if current.is_symlink() or (current.exists() and getattr(current.lstat(), "st_file_attributes", 0) & 0x400):
            raise ContentError(f"Symlink output path is not writable: {current}")
        current = current.parent
    return target


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9_-]", "_", value.lower())
    return slug[:120]


def _model_ref_to_file(pack_dir: Path, model_ref: str, own_namespace: str) -> Path:
    if not isinstance(model_ref, str) or ":" not in model_ref:
        raise ContentError(f"Model must use namespace:path syntax: {model_ref}")
    namespace, name = model_ref.split(":", 1)
    if namespace != own_namespace or not name or not all(ID_PATTERN.fullmatch(s) for s in name.split("/")):
        raise ContentError("The initial generator supports only model files in the item's own pack namespace")
    path = pack_dir / "assets" / namespace / "models" / f"{name}.json"
    return _ensure_inside(pack_dir, path)


@dataclass(frozen=True)
class Pack:
    root: Path
    namespace: str
    dependencies: tuple[str, ...]


@dataclass(frozen=True)
class Item:
    content_id: str
    definition: dict
    file: Path
    pack: Pack


@dataclass(frozen=True)
class ProposedFile:
    path: Path
    payload: bytes
    baseline_sha: str | None
    status: Literal["create", "update", "unchanged"]
    detail: str


@dataclass
class Plan:
    pack: Pack
    source: Item
    family: str
    target: str
    strategy: str
    recipe_key: str
    outputs: list[ProposedFile]
    warnings: list[str] = field(default_factory=list)
    source_hash: str = ""
    manifest_path: Path | None = None
    manifest: dict = field(default_factory=dict)
    input_hashes: dict[Path, str] = field(default_factory=dict)
    workspace_inventory: dict[Path, str] | None = None
    workspace_root: Path | None = None

    @property
    def changed(self) -> list[ProposedFile]:
        return [file for file in self.outputs if file.status != "unchanged"]

    def summary(self) -> str:
        lines = [f"Source: {self.source.content_id}", f"Family: {self.family} | Target: {self.target}",
                 f"Model strategy: {self.strategy}", f"Writes: {len(self.changed)} | No change: {len(self.outputs) - len(self.changed)}", ""]
        for f in self.outputs:
            lines.append(f"{f.status.upper():9} {f.path.relative_to(self.pack.root)}  ({f.detail})")
        if self.warnings:
            lines.extend(["", "Warnings:", *[f"- {w}" for w in self.warnings]])
        return "\n".join(lines)


class Workspace:
    """Read-only discovery and version-aware preview of existing VoxelCore packs."""

    def __init__(self, root: Path | str):
        raw = Path(root).expanduser().resolve()
        if raw.name == "VoxelCore" and (raw / "content").is_dir():
            raw = raw / "content"
        if not raw.is_dir():
            raise ContentError(f"Not a directory: {raw}")
        if (raw / "pack.yml").is_file():
            self.root = raw.parent
            self._pack_dirs = [raw]
        else:
            self.root = raw
            self._pack_dirs = [p for p in sorted(raw.iterdir()) if p.is_dir() and (p / "pack.yml").is_file()]
            if any(p.is_dir() and not p.name.startswith(".") and not (p / "pack.yml").is_file() for p in raw.iterdir()):
                # This avoids accepting a wrong root such as the server /plugins directory.
                if not self._pack_dirs:
                    raise ContentError("Select plugins/VoxelCore/content or a single pack containing pack.yml")
        if not self._pack_dirs:
            raise ContentError("No content packs found (expected pack.yml)")
        self.packs: dict[str, Pack] = {}
        self.items: dict[str, Item] = {}
        self.blocks: dict[str, tuple[Pack, Path, dict]] = {}
        self.glyphs: dict[str, tuple[Pack, Path, dict]] = {}
        self.input_hashes: dict[Path, str] = {}
        self._scan()

    def _scan(self) -> None:
        for folder in self._pack_dirs:
            _ensure_inside(self.root, folder / "pack.yml")
            manifest = _read_yaml(folder / "pack.yml")
            self.input_hashes[folder / "pack.yml"] = _sha((folder / "pack.yml").read_bytes())
            if manifest.get("schema") != 1 or not isinstance(manifest.get("namespace"), str):
                raise ContentError(f"Unsupported pack.yml in {folder} (requires schema: 1, namespace)")
            name = _validate_id(manifest["namespace"])
            deps = manifest.get("dependencies", [])
            if not isinstance(deps, list) or not all(isinstance(s, str) for s in deps):
                raise ContentError(f"Invalid dependencies in {folder / 'pack.yml'}")
            if name in self.packs:
                raise ContentError(f"Duplicate pack namespace: {name}")
            self.packs[name] = Pack(folder, name, tuple(deps))
        for pack in self.packs.values():
            content_dir = pack.root / "content"
            if not content_dir.exists():
                continue
            for file in sorted(p for p in content_dir.rglob("*") if p.suffix.lower() in (".yml", ".yaml")):
                _ensure_inside(pack.root, file)
                data = _read_yaml(file)
                self.input_hashes[file] = _sha(file.read_bytes())
                for section, index in (("items", self.items), ("blocks", self.blocks), ("ui", self.glyphs)):
                    values = data.get(section, {})
                    if not isinstance(values, dict):
                        raise ContentError(f"{section} must be a mapping in {file}")
                    for name, definition in values.items():
                        if not isinstance(name, str) or not isinstance(definition, dict):
                            raise ContentError(f"Invalid {section} declaration in {file}")
                        ident = canonical_id(name, pack.namespace)
                        if ident.split(":")[0] != pack.namespace:
                            raise ContentError(f"Foreign namespace declaration {ident} in {file}")
                        if ident in index:
                            raise ContentError(f"Duplicate {section} ID: {ident}")
                        index[ident] = Item(ident, definition, file, pack) if section == "items" else (pack, file, definition)

    def resolve_item(self, item_id: str) -> dict:
        memo: dict[str, dict] = {}

        def walk(key: str, stack: set[str]) -> dict:
            if key in memo:
                return copy.deepcopy(memo[key])
            if key in stack:
                raise ContentError(f"Inheritance cycle at {key}")
            item = self.items.get(key)
            if not item:
                raise ContentError(f"Unknown parent ContentID: {key}")
            stack.add(key)
            value = copy.deepcopy(item.definition)
            parent = value.get("extends")
            if parent is not None:
                if not isinstance(parent, str):
                    raise ContentError(f"Invalid extends value in {key}")
                pid = canonical_id(parent, item.pack.namespace)
                if pid.split(":")[0] != item.pack.namespace and pid.split(":")[0] not in item.pack.dependencies:
                    raise ContentError(f"{key}: parent pack {pid} must be in pack dependencies")
                value = _merge_item(walk(pid, stack), value)
            stack.remove(key)
            memo[key] = value
            return copy.deepcopy(value)

        return walk(item_id, set())

    def model_file(self, item_id: str) -> Path:
        item = self.items[item_id]
        effective = self.resolve_item(item_id)
        model_ref = effective.get("render", {}).get("model")
        if not model_ref:
            raise ContentError(f"{item_id} has no render.model")
        from .assets import ModelResolver
        path = ModelResolver(self).path(model_ref)
        if path is None:
            raise ContentError(f"Vanilla model is external to this workspace: {model_ref}")
        return path

    def describe(self, item_id: str) -> str:
        item = self.items[item_id]
        resolved = self.resolve_item(item_id)
        detail = [f"{item_id}", f"File: {item.file}", f"Kind: {self.kind(item_id)}", "", "-- Authored --",
                  yaml.safe_dump(item.definition, sort_keys=False, allow_unicode=True), "-- Inherited / resolved --",
                  yaml.safe_dump(resolved, sort_keys=False, allow_unicode=True)]
        return "\n".join(detail)

    def kind(self, item_id: str) -> str:
        props = self.resolve_item(item_id).get("properties", {})
        if isinstance(props, dict) and props.get("furniture") is not None:
            return "Furniture"
        if isinstance(props, dict) and props.get("vehicle") is not None:
            return "Vehicle"
        return "Item"


def _deep_merge(parent: dict, child: dict) -> dict:
    # Mirrors VoxelCore's nested map merge, including explicit null values, while
    # making no claim to replace the full authoritative Java compiler.
    result = copy.deepcopy(parent)
    for key, val in child.items():
        if isinstance(val, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = copy.deepcopy(val)
    return result


def _merge_item(parent: dict, child: dict) -> dict:
    result = _deep_merge(parent, child)
    # ItemInheritanceResolver: explicitly empty events disables inherited actions.
    if child.get("events") == {}:
        result["events"] = {}
    # Structured custom-model-data values replace by key, not deep merge.
    p_cmd = parent.get("render", {}).get("custom_model_data")
    c_cmd = child.get("render", {}).get("custom_model_data")
    if isinstance(p_cmd, dict) and isinstance(c_cmd, dict):
        result["render"]["custom_model_data"] = {**copy.deepcopy(p_cmd), **copy.deepcopy(c_cmd)}
    return result


def _attach_inputs(plan: Plan, workspace: Workspace, extra=()) -> Plan:
    if len(plan.outputs) > 4096 or sum(len(output.payload) for output in plan.outputs) > 64 * 1024 * 1024:
        raise ContentError("Plan exceeds the 4096-file / 64 MiB safety budget")
    # Reject an already-stale UI index rather than binding old definitions to new hashes.
    for path, expected in workspace.input_hashes.items():
        if not path.is_file() or _sha(path.read_bytes()) != expected:
            raise ContentError(f"Workspace changed since scan: {path}; refresh first")
    plan.input_hashes = dict(workspace.input_hashes)
    for path in extra:
        plan.input_hashes[path] = _sha(path.read_bytes())
    plan.workspace_inventory = dict(workspace.input_hashes)
    plan.workspace_root = workspace._pack_dirs[0] if len(workspace._pack_dirs) == 1 else workspace.root
    return plan


def _palette(family: str, target: str) -> tuple[str, ...]:
    if target not in SUPPORTED_TARGETS:
        raise ContentError("MVP palette generation supports modern flattened resource paths (1.13.2+) only")
    if family == "wool":
        return COLORS
    if family != "wood":
        raise ContentError(f"Unknown material family: {family}")
    older = WOODS[:6]
    if target in ("mc-1.13.2", "mc-1.14.4"):
        return older
    if target == "mc-1.19.4":
        return tuple(w for w in WOODS if w not in ("cherry", "bamboo", "pale_oak"))
    if target == "mc-1.20.5":
        return tuple(w for w in WOODS if w != "pale_oak")
    return WOODS


def _family_texture(family: str, variant: str) -> str:
    return f"minecraft:block/{variant}_{'planks' if family == 'wood' else 'wool'}"


def _split_source_name(name: str, family: str) -> tuple[str, str]:
    values = WOODS if family == "wood" else COLORS
    for token in sorted(values, key=len, reverse=True):
        if name.startswith(token + "_"):
            return token, name[len(token) + 1:]
    raise ContentError(f"Source name {name!r} must start with a {family} prefix, e.g. oak_table or white_wool_chair")


def _assert_clean_item_references(source: Item, resolved: dict, warnings: list[str]) -> None:
    props = resolved.get("properties", {})
    if not isinstance(props, dict):
        return
    for kind in ("furniture", "vehicle"):
        config = props.get(kind)
        if not isinstance(config, dict):
            continue
        for key in ("model_item", "drop"):
            if key in config:
                warnings.append(f"Inherited {kind}.{key} is explicit ({config[key]!r}); generated child will preserve that reference. Review before deploying.")
        if kind == "furniture" and ("animation" in config or "blockstates" in config):
            warnings.append("Furniture has animation/blockstates; the current generator does not create associated state-model children. Review these inherited links.")
        if kind == "vehicle" and "inventory" in config:
            warnings.append("Vehicle inventory/preview dependencies are inherited unchanged; confirm them in Minecraft.")


def _serialize_yaml(item_name: str, obj: dict) -> bytes:
    return yaml.safe_dump({"items": {item_name: obj}}, sort_keys=False, allow_unicode=True, width=100).encode("utf-8")


def _serialize_json(obj: dict) -> bytes:
    return (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _manifest_path(pack: Pack, source_id: str, family: str) -> Path:
    name = _safe_slug(f"{source_id}__{family}")
    return _ensure_inside(pack.root, pack.root / ".contentmanager" / "manifests" / (name + ".json"))


def _make_output(path: Path, payload: bytes, item_baseline: dict[str, Any], pack: Pack, detail: str) -> ProposedFile:
    from .transactions import writable_path
    dest = writable_path(pack.root, path.relative_to(pack.root).as_posix())
    prior = _bytes(dest)
    prior_hash = _sha(prior) if prior is not None else None
    rel = dest.relative_to(pack.root).as_posix()
    if prior is not None and prior_hash != item_baseline.get(rel):
        raise ContentError(f"Refusing to overwrite unowned or manually changed file: {rel}")
    if prior == payload:
        return ProposedFile(dest, payload, prior_hash, "unchanged", detail)
    return ProposedFile(dest, payload, prior_hash, "update" if prior is not None else "create", detail)


def plan_family(workspace: Workspace, source_id: str, family: Literal["wood", "wool"],
                target: str = "mc-26.2", strategy: Literal["alias", "clone"] = "alias",
                texture_slot: str = "", selected: tuple[str, ...] | None = None,
                include_dependencies: bool = False) -> Plan:
    from .generators import plan_family as generate
    return generate(workspace, source_id, family, target, strategy, texture_slot, selected, include_dependencies)



def plan_new_item(workspace: Workspace, namespace: str, name: str, display_name: str,
                  model_ref: str, kind: Literal["item", "furniture", "vehicle"] = "item",
                  material: str = "minecraft:paper") -> Plan:
    """Author a new concrete item using a preexisting model association.

    No model file is generated here; the caller must select an existing asset.
    The file is placed under a distinct user-created Content Manager directory,
    so existing authored YAML comments and formatting are unaffected.
    """
    namespace = _validate_id(namespace)
    name = _validate_id(name)
    if namespace not in workspace.packs:
        raise ContentError(f"Unknown pack namespace: {namespace}")
    if kind not in ("item", "furniture", "vehicle"):
        raise ContentError(f"Unknown kind: {kind}")
    content_id = f"{namespace}:{name}"
    if content_id in workspace.items or content_id in workspace.blocks:
        raise ContentError(f"ContentID already exists: {content_id}")
    pack = workspace.packs[namespace]
    from .assets import ModelResolver
    resolver = ModelResolver(workspace)
    associated_model = resolver.path(model_ref.strip())
    if associated_model is None:
        raise ContentError("New content requires a local model association")
    if not associated_model.is_file():
        raise ContentError(f"Model association not found: {associated_model}")
    resolved_model = resolver.resolve(model_ref.strip())
    if not display_name.strip() or not material.strip():
        raise ContentError("Display name and material must be non-empty")
    item = {"material": material.strip(), "display_name": display_name.strip(),
            "render": {"model": model_ref.strip()}}
    if kind == "furniture":
        item["properties"] = {"furniture": {"renderer": "auto", "rotation_step": 90}}
    elif kind == "vehicle":
        item["properties"] = {"vehicle": {"type": "LAND"}}
    output = pack.root / "content" / "generated" / "contentmanager" / "authored" / f"{name}.yml"
    file = _make_output(output, _serialize_yaml(name, item), {}, pack, f"new {kind} {content_id}")
    # Unlike generated family recipes, the new file belongs to the user.
    # Re-run of plan_new_item will reject duplicate ID after application.
    source = Item(content_id, item, file.path, pack)
    return _attach_inputs(Plan(pack, source, "new-" + kind, "mc-26.2", "existing-model",
                _safe_slug("new__" + content_id), [file],
                ["Created configuration is a starter preset, not verified against an active VoxelCore/Furniture/Vehicles build."],
                "", None, {}), workspace, resolved_model.inputs)


def apply_plan(plan: Plan) -> Path | None:
    """Apply an explicitly approved plan using the durable transaction service."""
    from .transactions import apply
    return apply(plan)


def rollback_snapshot(pack_root: Path | str, snapshot_dir: Path | str) -> None:
    from .transactions import restore
    restore(pack_root, snapshot_dir)
