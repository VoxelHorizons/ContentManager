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
    pass


def _unique_mapping(loader: yaml.Loader, node: yaml.nodes.MappingNode) -> dict:
    result: dict = {}
    for key_node, val_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        try:
            exists = key in result
        except TypeError as ex:
            raise ContentError("Unhashable YAML mapping key") from ex
        if exists:
            raise ContentError(f"Duplicate YAML key: {key!r}")
        result[key] = loader.construct_object(val_node, deep=True)
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
    result = value.strip().lower()
    if not ID_PATTERN.fullmatch(result):
        raise ContentError(f"Invalid ContentID segment: {value!r}")
    return result


def canonical_id(value: str, default_namespace: str) -> str:
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
        if current.is_symlink():
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
        return _model_ref_to_file(item.pack.root, model_ref, item.pack.namespace)

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
    if target in ("mc-1.20.5", "mc-1.21.4"):
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
    dest = _ensure_inside(pack.root, path)
    prior = _bytes(dest)
    prior_hash = _sha(prior) if prior is not None else None
    if prior == payload:
        return ProposedFile(dest, payload, prior_hash, "unchanged", detail)
    rel = dest.relative_to(pack.root).as_posix()
    if prior is not None and prior_hash != item_baseline.get(rel):
        raise ContentError(f"Refusing to overwrite unowned or manually changed file: {rel}")
    return ProposedFile(dest, payload, prior_hash, "update" if prior is not None else "create", detail)


def plan_family(workspace: Workspace, source_id: str, family: Literal["wood", "wool"],
                target: str = "mc-26.2", strategy: Literal["alias", "clone"] = "alias",
                texture_slot: str = "", selected: tuple[str, ...] | None = None) -> Plan:
    if source_id not in workspace.items:
        raise ContentError(f"Unknown source item: {source_id}")
    source = workspace.items[source_id]
    source_ns, source_name = source.content_id.split(":", 1)
    source_material, noun = _split_source_name(source_name, family)
    palette = _palette(family, target)
    if source_material not in palette:
        raise ContentError(f"Source material {source_material} not available for {target}")
    chosen = selected if selected is not None else palette
    if len(chosen) > 64 or len(set(chosen)) != len(chosen) or any(v not in palette for v in chosen):
        raise ContentError("Selected materials must be unique and part of the selected target palette (up to 64)")
    resolved = workspace.resolve_item(source_id)
    model_ref = resolved.get("render", {}).get("model")
    src_model = workspace.model_file(source_id)
    if not src_model.is_file() or src_model.stat().st_size > 2 * 1024 * 1024:
        raise ContentError(f"Missing or oversized model file: {src_model}")
    try:
        src_model_json = json.loads(src_model.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeError) as ex:
        raise ContentError(f"Invalid source model: {src_model} ({ex})") from ex
    if not isinstance(src_model_json, dict):
        raise ContentError("Model JSON must be an object")
    texture_map = src_model_json.get("textures", {})
    if not isinstance(texture_map, dict):
        raise ContentError("Source model textures must be an object")
    base_texture = _family_texture(family, source_material)
    if not texture_slot:
        candidates = [key for key, value in texture_map.items() if value == base_texture]
        if len(candidates) != 1:
            raise ContentError(f"Select a texture slot. Found {len(candidates)} slots using {base_texture}; slots: {list(texture_map)}")
        texture_slot = candidates[0]
    if texture_slot not in texture_map or texture_map[texture_slot] != base_texture:
        raise ContentError(f"Texture slot {texture_slot!r} must point to {base_texture} in the source model")
    if strategy == "alias" and not (src_model_json.get("parent") or src_model_json.get("elements")):
        raise ContentError("An alias model needs a geometry-bearing parent or source elements")
    if strategy not in ("alias", "clone"):
        raise ContentError(f"Unsupported model strategy {strategy}")
    warnings: list[str] = []
    _assert_clean_item_references(source, resolved, warnings)
    warnings.append("Local generator checks are not authoritative VoxelCore or Minecraft pack validation. Use /vc admin pack validate and a test server before deployment.")
    manifest_file = _manifest_path(source.pack, source_id, family)
    previous = {}
    if manifest_file.is_file():
        try:
            previous = json.loads(manifest_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeError) as ex:
            raise ContentError(f"Broken generator manifest {manifest_file}: {ex}") from ex
        if previous.get("source_id") != source_id or previous.get("family") != family:
            raise ContentError(f"Existing manifest does not match recipe: {manifest_file}")
        if previous.get("target") != target or previous.get("strategy") != strategy or previous.get("texture_slot") != texture_slot:
            raise ContentError("Recipe target/strategy/slot changed; detach or manually migrate existing generated files first")
    owned: dict[str, str] = previous.get("files", {})
    files: list[ProposedFile] = []
    new_ownership = dict(owned)
    origin = Path(model_ref.split(":", 1)[1])
    original_name = origin.name
    # Keep the geometry directory, but each generated model gets the child item ID.
    for variant in chosen:
        if variant == source_material:
            continue
        item_name = f"{variant}_{noun}"
        new_id = f"{source_ns}:{item_name}"
        yml = source.pack.root / "content" / "generated" / "contentmanager" / _safe_slug(f"{source_name}__{family}") / (item_name + ".yml")
        target_model_ref = f"{source_ns}:{origin.parent.as_posix()}/{item_name}" if origin.parent.as_posix() != "." else f"{source_ns}:{item_name}"
        model_file = _model_ref_to_file(source.pack.root, target_model_ref, source_ns)
        yaml_rel = yml.relative_to(source.pack.root).as_posix()
        if new_id in workspace.items and workspace.items[new_id].file != yml:
            raise ContentError(f"Generated ID {new_id} already belongs to {workspace.items[new_id].file}")
        if new_id in workspace.blocks or new_id in workspace.glyphs:
            raise ContentError(f"Generated ID collides with another content definition: {new_id}")
        child = {
            "extends": source_id, "abstract": False,
            "display_name": f"&f{variant.replace('_', ' ').title()} {noun.replace('_', ' ').title()}",
            "render": {"model": target_model_ref},
        }
        new_texture = _family_texture(family, variant)
        if strategy == "alias":
            model_json = {"parent": model_ref, "textures": {texture_slot: new_texture}}
        else:
            model_json = copy.deepcopy(src_model_json)
            model_json["textures"][texture_slot] = new_texture
        files.append(_make_output(yml, _serialize_yaml(item_name, child), owned, source.pack, f"{new_id} inherited child"))
        files.append(_make_output(model_file, _serialize_json(model_json), owned, source.pack, f"{new_texture} model"))
    if not files:
        raise ContentError("No new material variants selected")
    for f in files:
        new_ownership[f.path.relative_to(source.pack.root).as_posix()] = _sha(f.payload)
    manifest = {
        "schema": 1, "source_id": source_id, "family": family, "target": target,
        "strategy": strategy, "texture_slot": texture_slot, "selected": list(chosen),
        "files": {key: new_ownership[key] for key in sorted(new_ownership)},
    }
    # Managed manifests can only update if they correspond to this recipe.
    manifest_payload = _serialize_json(manifest)
    old_manifest_data = _bytes(manifest_file)
    files.append(ProposedFile(manifest_file, manifest_payload,
                              _sha(old_manifest_data) if old_manifest_data is not None else None,
                              "unchanged" if old_manifest_data == manifest_payload else ("update" if old_manifest_data is not None else "create"),
                              "generator ownership manifest"))
    return _attach_inputs(Plan(source.pack, source, family, target, strategy, _safe_slug(f"{source_id}__{family}"),
                files, warnings, _sha(source.file.read_bytes()) + ":" + _sha(src_model.read_bytes()),
                manifest_file, manifest), workspace, [src_model])



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
    associated_model = _model_ref_to_file(pack.root, model_ref.strip(), namespace)
    if not associated_model.is_file():
        raise ContentError(f"Model association not found: {associated_model}")
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
                "", None, {}), workspace, [associated_model])


def apply_plan(plan: Plan) -> Path | None:
    """Apply an explicitly approved plan using the durable transaction service."""
    from .transactions import apply
    return apply(plan)


def rollback_snapshot(pack_root: Path | str, snapshot_dir: Path | str) -> None:
    from .transactions import restore
    restore(pack_root, snapshot_dir)
