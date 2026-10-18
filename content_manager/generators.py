"""Inheritance-aware material families with optional typed addon dependency fanout."""
from __future__ import annotations
import copy
import json
from pathlib import PurePosixPath

from .assets import ModelResolver, item_references
from .core import (ContentError, Plan, ProposedFile, Workspace, _attach_inputs, _family_texture,
                   _manifest_path, _make_output, _model_ref_to_file, _palette, _safe_slug,
                   _serialize_json, _serialize_yaml, _sha, _split_source_name, _bytes)


def _delta(before, after):
    """Minimal map overrides; lists replace as required by VoxelCore inheritance."""
    if not isinstance(before, dict) or not isinstance(after, dict):
        return copy.deepcopy(after)
    out = {}
    for key, value in after.items():
        if key not in before or before[key] != value:
            out[key] = _delta(before.get(key), value)
    return out


def plan_family(workspace: Workspace, source_id: str, family: str,
                target='mc-26.2', strategy='alias', texture_slot='', selected=None,
                include_dependencies=False) -> Plan:
    if source_id not in workspace.items:
        raise ContentError(f'Unknown source item: {source_id}')
    if strategy not in ('alias', 'clone'):
        raise ContentError(f'Unsupported model strategy {strategy}')
    source = workspace.items[source_id]
    namespace, source_name = source_id.split(':', 1)
    source_material, noun = _split_source_name(source_name, family)
    palette = _palette(family, target)
    if source_material not in palette:
        raise ContentError(f'Source material {source_material} not available for {target}')
    chosen = tuple(selected) if selected is not None else palette
    if len(chosen) > 64 or len(set(chosen)) != len(chosen) or any(v not in palette for v in chosen):
        raise ContentError('Selected materials must be unique and part of the selected target palette (up to 64)')
    chosen = tuple(v for v in palette if v in chosen)  # canonical recipe ordering
    base_texture = _family_texture(family, source_material)
    resolver = ModelResolver(workspace)
    nodes, models, slots, inputs = {}, {}, {}, {}
    warnings = ['Local checks do not certify Minecraft rendering or plugin runtime acceptance. Run VoxelCore validation and staging tests.']
    todo = [source_id]
    while todo:
        ident = todo.pop(0)
        if ident in nodes:
            continue
        if len(nodes) >= 128:
            raise ContentError('Related item graph exceeds 128 items')
        item = workspace.items[ident]
        effective = workspace.resolve_item(ident)
        model_ref = effective.get('render', {}).get('model')
        if not model_ref:
            raise ContentError(f'Related item has no render.model: {ident}')
        model = resolver.resolve(model_ref)
        texture_map = model.effective.get('textures', {})
        slot = texture_slot
        if not slot:
            candidates = [key for key, value in texture_map.items() if value == base_texture]
            if len(candidates) != 1:
                raise ContentError(f'Select a texture slot for {ident}. Found {len(candidates)} slots using {base_texture}; slots: {list(texture_map)}')
            slot = candidates[0]
        if model.textures.get(slot) != base_texture:
            raise ContentError(f'Texture slot {slot!r} must resolve to {base_texture} in {ident}')
        if strategy == 'alias' and not (model.effective.get('elements') or model.external_parents):
            raise ContentError(f'Alias source has no geometry-bearing parent or elements: {ident}')
        for external in model.external_parents:
            warnings.append(f'Vanilla parent geometry unverified: {external} in {ident}')
        nodes[ident], models[ident], slots[ident] = effective, model, slot
        inputs.update(model.inputs)
        for ref in item_references(effective, item.pack.namespace):
            if ref.target not in workspace.items:
                raise ContentError(f'Missing item reference {ref.target} from {ident} at {ref.path}')
            if ref.target in nodes:
                continue
            ref_ns, ref_name = ref.target.split(':', 1)
            eligible = ref_ns == namespace and ref_name.startswith(source_material + '_')
            if include_dependencies and eligible:
                todo.append(ref.target)
            else:
                warnings.append(f'Preserved shared reference {ref.target} from {ident} at {".".join(map(str, ref.path))}')
    if len(nodes) * (len(chosen) - (source_material in chosen)) * 2 + 1 > 4096:
        raise ContentError('Generation exceeds 4096 output files; narrow the selection')
    manifest_file = _manifest_path(source.pack, source_id, family)
    previous = {}
    old_manifest = _bytes(manifest_file)
    if old_manifest is not None:
        try:
            previous = json.loads(old_manifest)
        except (ValueError, UnicodeError) as exc:
            raise ContentError(f'Broken generator manifest: {manifest_file}') from exc
        if not isinstance(previous, dict) or previous.get('schema') != 1:
            raise ContentError('Unsupported generator manifest schema')
        if previous.get('source_id') != source_id or previous.get('family') != family:
            raise ContentError('Existing manifest does not match recipe')
        if any(previous.get(key) != val for key, val in [('target', target), ('strategy', strategy), ('texture_slot', slots[source_id])]):
            raise ContentError('Recipe target/strategy/slot changed; detach or manually migrate existing generated files first')
        if previous.get('include_dependencies', False) != include_dependencies:
            raise ContentError('Recipe dependency policy changed; explicitly migrate the existing recipe first')
    owned = previous.get('files', {})
    if not isinstance(owned, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in owned.items()):
        raise ContentError('Invalid generator ownership manifest')
    outputs, ownership = [], dict(owned)
    for variant in chosen:
        if variant == source_material:
            continue
        mapping = {ident: f'{namespace}:{variant}_{ident.split(":",1)[1][len(source_material)+1:]}' for ident in nodes}
        for ident, effective in nodes.items():
            new_id = mapping[ident]
            item_name = new_id.split(':', 1)[1]
            model = models[ident]
            origin = PurePosixPath(model.reference.split(':', 1)[1])
            target_ref = f'{namespace}:{(origin.parent / item_name).as_posix()}'
            model_file = _model_ref_to_file(source.pack.root, target_ref, namespace)
            yml = source.pack.root / 'content/generated/contentmanager' / _safe_slug(f'{source_name}__{family}') / (item_name + '.yml')
            if new_id in workspace.items and workspace.items[new_id].file != yml:
                raise ContentError(f'Generated ID {new_id} already belongs to {workspace.items[new_id].file}')
            if new_id in workspace.blocks or new_id in workspace.glyphs:
                raise ContentError(f'Generated ID collides with another definition: {new_id}')
            child = {'extends': ident, 'abstract': False if ident == source_id else effective.get('abstract', False),
                     'display_name': '&f' + item_name.replace('_', ' ').title(), 'render': {'model': target_ref}}
            rewritten = copy.deepcopy(effective)
            for ref in item_references(effective, workspace.items[ident].pack.namespace):
                if ref.target in mapping:
                    current = rewritten
                    for key in ref.path[:-1]:
                        current = current[key]
                    current[ref.path[-1]] = mapping[ref.target]
            changes = _delta(effective.get('properties', {}), rewritten.get('properties', {}))
            if changes:
                child['properties'] = changes
            if strategy == 'alias':
                derivative = {'parent': model.reference, 'textures': {slots[ident]: _family_texture(family, variant)}}
            else:
                derivative = copy.deepcopy(model.authored)
                derivative.setdefault('textures', {})[slots[ident]] = _family_texture(family, variant)
            outputs.append(_make_output(yml, _serialize_yaml(item_name, child), owned, source.pack, f'{new_id} inherited child'))
            outputs.append(_make_output(model_file, _serialize_json(derivative), owned, source.pack, f'{ident} texture derivative'))
    if not outputs:
        raise ContentError('No new material variants selected')
    for output in outputs:
        relative = output.path.relative_to(source.pack.root).as_posix()
        ownership[relative] = _sha(output.payload)
    removed_selection = set(previous.get('selected', [])) - set(chosen)
    if removed_selection:
        warnings.append('Previously generated excluded variants are retained: ' + ', '.join(sorted(removed_selection)))
    manifest = {'schema': 1, 'source_id': source_id, 'family': family, 'target': target,
                'strategy': strategy, 'texture_slot': slots[source_id], 'selected': list(chosen),
                'files': dict(sorted(ownership.items()))}
    if include_dependencies:
        manifest['include_dependencies'] = True
        manifest['source_items'] = sorted(nodes)
    payload = _serialize_json(manifest)
    outputs.append(ProposedFile(manifest_file, payload, _sha(old_manifest) if old_manifest else None,
                    'unchanged' if old_manifest == payload else ('update' if old_manifest else 'create'), 'generator ownership manifest'))
    plan = Plan(source.pack, source, family, target, strategy, _safe_slug(f'{source_id}__{family}'), outputs,
                sorted(set(warnings)), '', manifest_file, manifest)
    _attach_inputs(plan, workspace)
    plan.input_hashes.update(inputs)
    return plan
