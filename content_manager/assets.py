"""Read-only Minecraft model resolution and typed authored-content references.

Vanilla resources not provided by the workspace stay explicitly external; this
module does not invent vanilla geometry or certify atlas/runtime compatibility.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
import json
from pathlib import Path
import re

from .core import ContentError, canonical_id, _sha
from .transactions import portable_path

RESOURCE_PART = re.compile(r'^[a-z0-9_.-]+$')


def resource_id(value: str) -> str:
    if not isinstance(value, str):
        raise ContentError(f'Resource reference must be a string: {value!r}')
    namespace, name = value.split(':', 1) if ':' in value else ('minecraft', value)
    parts = name.split('/')
    if (not RESOURCE_PART.fullmatch(namespace) or not name or
            any(p in ('', '.', '..') or not RESOURCE_PART.fullmatch(p) for p in parts)):
        raise ContentError(f'Invalid resource reference: {value!r}')
    return f'{namespace}:{name}'


@dataclass
class ResolvedModel:
    reference: str
    authored: dict
    effective: dict
    textures: dict[str, str]
    inputs: dict[Path, str] = field(default_factory=dict)
    external_parents: tuple[str, ...] = ()


class ModelResolver:
    def __init__(self, workspace):
        self.workspace = workspace

    def path(self, reference: str, kind='models') -> Path | None:
        reference = resource_id(reference)
        namespace, name = reference.split(':', 1)
        pack = self.workspace.packs.get(namespace)
        if pack is None:
            if namespace == 'minecraft':
                return None
            raise ContentError(f'Missing asset namespace {namespace}: {reference}')
        return portable_path(pack.root, f'assets/{namespace}/{kind}/{name}{".json" if kind == "models" else ".png"}')

    def resolve(self, reference: str) -> ResolvedModel:
        inputs = {}
        external = []
        def walk(ref, chain):
            ref = resource_id(ref)
            if ref in chain:
                raise ContentError('Model parent cycle: ' + ' -> '.join((*chain, ref)))
            if len(chain) >= 128:
                raise ContentError('Model parent depth exceeds 128')
            path = self.path(ref)
            if path is None:
                external.append(ref)
                return {}, {}
            if not path.is_file():
                raise ContentError(f'Missing model: {ref} ({path})')
            raw = path.read_bytes()
            if len(raw) > 2 * 1024 * 1024:
                raise ContentError(f'Model exceeds 2 MiB: {ref}')
            inputs[path] = _sha(raw)
            try:
                def pairs(entries):
                    result = {}
                    for key, value in entries:
                        if key in result:
                            raise ContentError(f'Duplicate JSON key {key!r} in {ref}')
                        result[key] = value
                    return result
                authored = json.loads(raw, object_pairs_hook=pairs)
            except (ValueError, UnicodeError) as exc:
                raise ContentError(f'Invalid model JSON {ref}: {exc}') from exc
            if not isinstance(authored, dict):
                raise ContentError(f'Model must be an object: {ref}')
            effective = {}
            if 'parent' in authored:
                _, effective = walk(authored['parent'], (*chain, ref))
            effective = copy.deepcopy(effective)
            for key, value in authored.items():
                if key in ('textures', 'display'):
                    if not isinstance(value, dict):
                        raise ContentError(f'Model {key} must be an object: {ref}')
                    effective[key] = {**effective.get(key, {}), **copy.deepcopy(value)}
                else:
                    effective[key] = copy.deepcopy(value)
            return authored, effective
        authored, effective = walk(reference, ())
        slots = effective.get('textures', {})
        resolved = {}
        def slot(key, chain=()):
            if key in chain:
                raise ContentError('Texture alias cycle: ' + ' -> '.join((*chain, key)))
            if len(chain) >= 128:
                raise ContentError('Texture alias depth exceeds 128')
            value = slots.get(key)
            if not isinstance(value, str):
                raise ContentError(f'Missing/invalid texture slot #{key} in {reference}')
            return slot(value[1:], (*chain, key)) if value.startswith('#') else resource_id(value)
        for key in slots:
            resolved[key] = slot(key)
        elements = effective.get('elements', [])
        if not isinstance(elements, list):
            raise ContentError(f'Model elements must be a list: {reference}')
        for element in elements:
            if not isinstance(element, dict) or not isinstance(element.get('faces', {}), dict):
                raise ContentError(f'Invalid model element in {reference}')
            for face in element.get('faces', {}).values():
                if not isinstance(face, dict) or not isinstance(face.get('texture'), str):
                    raise ContentError(f'Invalid face texture in {reference}')
                value = face['texture']
                if value.startswith('#'):
                    slot(value[1:])
                else:
                    resource_id(value)
        return ResolvedModel(resource_id(reference), authored, effective, resolved, inputs, tuple(external))


@dataclass(frozen=True)
class ItemReference:
    path: tuple
    target: str


def item_references(definition: dict, namespace: str) -> list[ItemReference]:
    """Only source-verified item reference fields; never replace arbitrary strings."""
    paths = []
    props = definition.get('properties', {})
    if not isinstance(props, dict):
        return []
    for kind in ('furniture', 'vehicle'):
        config = props.get(kind)
        if not isinstance(config, dict):
            continue
        prefix = ('properties', kind)
        for key in ('model_item', 'drop'):
            if config.get(key) is not None:
                paths.append(prefix + (key,))
        if kind == 'furniture':
            animation = config.get('animation')
            if isinstance(animation, dict) and 'use' in animation:
                paths.append(prefix + ('animation', 'use'))
            states = config.get('blockstates') or []
            if not isinstance(states, list):
                raise ContentError('Furniture blockstates must be a list')
            for i, state in enumerate(states):
                if isinstance(state, dict) and 'model_item' in state:
                    paths.append(prefix + ('blockstates', i, 'model_item'))
            parts = config.get('display_parts') or {}
            if isinstance(parts, dict):
                for name, part in parts.items():
                    if isinstance(part, dict) and str(part.get('type', 'text')).lower() == 'item' and 'model_item' in part:
                        paths.append(prefix + ('display_parts', name, 'model_item'))
        else:
            for tail in (('inventory', 'preview_item'), ('inventory', 'chest', 'preview_item'),
                         ('inventory', 'chest', 'visual', 'item'), ('inventory', 'chest', 'visual', 'model_item')):
                value = config
                for key in tail:
                    value = value.get(key) if isinstance(value, dict) else None
                if value is not None:
                    paths.append(prefix + tail)
    refs = []
    for path in paths:
        value = definition
        for key in path:
            value = value[key]
        if not isinstance(value, str):
            raise ContentError(f'Expected ContentID at {path}: {value!r}')
        refs.append(ItemReference(path, canonical_id(value, namespace)))
    return refs


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    relation: str


class ReferenceGraph:
    """Known item/model/texture edges. Unused candidates are not deletion advice."""
    def __init__(self, workspace):
        self.edges: list[Edge] = []
        self.diagnostics: list[str] = []
        self.models: dict[str, Path] = {}
        self.textures: dict[str, Path] = {}
        resolver = ModelResolver(workspace)
        for pack in workspace.packs.values():
            for kind, suffix, index in (('models', '.json', self.models), ('textures', '.png', self.textures)):
                root = pack.root / 'assets' / pack.namespace / kind
                for path in sorted(root.rglob('*')):
                    if path.is_file() and path.suffix == suffix:
                        ref = f'{pack.namespace}:{path.relative_to(root).with_suffix("").as_posix()}'
                        try:
                            checked = resolver.path(ref, kind)
                            index[ref] = checked
                        except ContentError as exc:
                            self.diagnostics.append(str(exc))
        for ident, item in workspace.items.items():
            try:
                effective = workspace.resolve_item(ident)
                if item.definition.get('extends'):
                    self.edges.append(Edge('item:'+ident, 'item:'+canonical_id(item.definition['extends'], item.pack.namespace), 'extends'))
                model = effective.get('render', {}).get('model')
                if model:
                    self.edges.append(Edge('item:'+ident, 'model:'+resource_id(model), 'render.model'))
                    resolver.resolve(model)
                for ref in item_references(effective, item.pack.namespace):
                    self.edges.append(Edge('item:'+ident, 'item:'+ref.target, '.'.join(map(str, ref.path))))
                    if ref.target not in workspace.items:
                        self.diagnostics.append(f'Missing item {ref.target} referenced by {ident} at {ref.path}')
            except (ContentError, OSError, ValueError) as exc:
                self.diagnostics.append(f'{ident}: {exc}')
        for ref, path in self.models.items():
            try:
                model = resolver.resolve(ref)
                if model.authored.get('parent'):
                    self.edges.append(Edge('model:'+ref, 'model:'+resource_id(model.authored['parent']), 'parent'))
                textures = set(model.textures.values())
                for element in model.effective.get('elements', []):
                    for face in element.get('faces', {}).values():
                        if not face['texture'].startswith('#'):
                            textures.add(resource_id(face['texture']))
                for texture in sorted(textures):
                    self.edges.append(Edge('model:'+ref, 'texture:'+texture, 'texture'))
                    texture_path = resolver.path(texture, 'textures')
                    if texture_path is not None and not texture_path.is_file():
                        self.diagnostics.append(f'Missing texture {texture} in {ref}')
                for parent in model.external_parents:
                    self.diagnostics.append(f'External vanilla parent unverified: {parent} in {ref}')
            except (ContentError, OSError, ValueError) as exc:
                self.diagnostics.append(f'{ref}: {exc}')
        self.diagnostics = sorted(set(self.diagnostics))

    def incoming(self, node):
        return [edge for edge in self.edges if edge.target == node]

    def outgoing(self, node):
        return [edge for edge in self.edges if edge.source == node]

    def unused_candidates(self):
        reached = set()
        adjacency = {}
        for edge in self.edges:
            adjacency.setdefault(edge.source, []).append(edge.target)
        todo = [node for node in adjacency if node.startswith('item:')]
        while todo:
            node = todo.pop()
            if node not in reached:
                reached.add(node)
                todo.extend(adjacency.get(node, []))
        return sorted([f'model:{ref}' for ref in self.models if f'model:{ref}' not in reached] +
                      [f'texture:{ref}' for ref in self.textures if f'texture:{ref}' not in reached])

    def duplicate_models(self):
        hashes = {}
        for ref, path in self.models.items():
            hashes.setdefault(_sha(path.read_bytes()), []).append(ref)
        return [sorted(refs) for refs in hashes.values() if len(refs) > 1]
