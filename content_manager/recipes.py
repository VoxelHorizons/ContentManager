"""Versioned, bounded multi-axis material recipes; no executable expressions.

Recipes are editor metadata, never emitted into VoxelCore item definitions.
Only explicitly bound texture slots and typed item references are substituted.
"""
from __future__ import annotations

import copy
import itertools
import json
import re

from .assets import ModelResolver, item_references, resource_id
from .core import (ContentError, Plan, ProposedFile, SUPPORTED_TARGETS, _attach_inputs,
                   _bytes, _make_output, _model_ref_to_file, _safe_slug, _serialize_json,
                   _serialize_yaml, _sha, _validate_id, canonical_id)
from .generators import _delta
from .transactions import portable_path


def _expand(template, values):
    if not isinstance(template, str):
        raise ContentError('Recipe templates must be strings')
    def replace(match):
        key = match.group(1)
        if key not in values:
            raise ContentError(f'Unknown recipe axis: {key}')
        return values[key]
    result = re.sub(r'\{([a-z0-9_-]+)\}', replace, template)
    if '{' in result or '}' in result:
        raise ContentError('Only plain {axis} substitutions are supported')
    return result


def plan_recipe(workspace, recipe):
    if not isinstance(recipe, dict) or recipe.get('recipe_schema') != 1:
        raise ContentError('Expected recipe_schema: 1')
    allowed = {'recipe_schema', 'id', 'source', 'target', 'strategy', 'axes', 'items', 'texture_slots'}
    if set(recipe) - allowed:
        raise ContentError(f'Unknown recipe keys: {set(recipe) - allowed}')
    recipe_id = _validate_id(recipe.get('id', ''))
    source_id = recipe.get('source')
    if source_id not in workspace.items:
        raise ContentError(f'Unknown recipe source: {source_id}')
    source = workspace.items[source_id]
    target, strategy = recipe.get('target', 'mc-26.3'), recipe.get('strategy', 'alias')
    if target not in SUPPORTED_TARGETS or strategy not in ('alias', 'clone'):
        raise ContentError('Unsupported recipe target or strategy')
    axes, bindings, templates = recipe.get('axes'), recipe.get('texture_slots'), recipe.get('items')
    if not isinstance(axes, dict) or not 1 <= len(axes) <= 4:
        raise ContentError('Recipes require one to four axes')
    count = 1
    for name, options in axes.items():
        if not isinstance(name, str) or _validate_id(name) != name:
            raise ContentError('Axis names must be lowercase identifiers')
        if not isinstance(options, dict) or not options:
            raise ContentError(f'Axis {name} requires named texture choices')
        count *= len(options)
        for key, texture in options.items():
            if not isinstance(key, str) or _validate_id(key) != key:
                raise ContentError('Axis values must be lowercase identifiers')
            resource_id(texture)
    if not isinstance(bindings, dict) or not bindings or any(axis not in axes for axis in bindings.values()):
        raise ContentError('texture_slots must map model slot names to defined axes')
    if set(bindings.values()) != set(axes):
        raise ContentError('Every axis must be bound to at least one texture slot')
    if not isinstance(templates, dict) or source_id not in templates:
        raise ContentError('items must map source ContentIDs to output ID templates, including source')
    if count * len(templates) * 2 + 1 > 4096:
        raise ContentError('Recipe exceeds 4096 output files')
    resolver = ModelResolver(workspace)
    models, definitions, inputs = {}, {}, {}
    warnings = ['Custom texture availability and target atlas support require VoxelCore validation.']
    for ident in templates:
        if ident not in workspace.items or workspace.items[ident].pack != source.pack:
            raise ContentError(f'Recipe items must exist in source pack: {ident}')
        effective = workspace.resolve_item(ident)
        model = resolver.resolve(effective.get('render', {}).get('model'))
        for slot in bindings:
            if slot not in model.textures:
                raise ContentError(f'Missing bound texture slot {slot!r} in {ident}')
        models[ident], definitions[ident] = model, effective
        inputs.update(model.inputs)
        for parent in model.external_parents:
            warnings.append(f'External vanilla parent unverified: {parent}')
    manifest_file = portable_path(source.pack.root, f'.contentmanager/manifests/recipe_{recipe_id}.json')
    old_manifest = _bytes(manifest_file)
    previous = json.loads(old_manifest) if old_manifest else {}
    if previous and (previous.get('schema') != 1 or previous.get('recipe_id') != recipe_id or previous.get('source_id') != source_id or previous.get('source_items') != sorted(templates)):
        raise ContentError('Recipe identity/source set changed; explicitly migrate the existing recipe')
    owned = previous.get('files', {})
    if not isinstance(owned, dict):
        raise ContentError('Invalid recipe ownership manifest')
    outputs, seen_ids, seen_paths = [], set(), set()
    axis_names = sorted(axes)
    for combination in itertools.product(*(sorted(axes[a]) for a in axis_names)):
        values = dict(zip(axis_names, combination))
        mapping = {ident: canonical_id(_expand(template, values), source.pack.namespace) for ident, template in templates.items()}
        for ident, new_id in mapping.items():
            if new_id in seen_ids:
                raise ContentError(f'Recipe produces duplicate ID: {new_id}; include every axis in naming')
            seen_ids.add(new_id)
            if new_id == ident:
                raise ContentError(f'Recipe output collides with authored source {ident}; choose distinct output names')
            namespace, name = new_id.split(':', 1)
            if namespace != source.pack.namespace:
                raise ContentError('Recipe outputs must remain in the source pack namespace')
            yml = source.pack.root / 'content/generated/contentmanager' / ('recipe_' + recipe_id) / (name + '.yml')
            if new_id in workspace.items and workspace.items[new_id].file != yml:
                raise ContentError(f'Generated ID already exists: {new_id}')
            if new_id in workspace.blocks or new_id in workspace.glyphs:
                raise ContentError(f'Generated ID collides with another definition: {new_id}')
            target_model = f'{namespace}:contentmanager/{recipe_id}/{name}'
            model_path = _model_ref_to_file(source.pack.root, target_model, namespace)
            effective = definitions[ident]
            rewritten = copy.deepcopy(effective)
            for ref in item_references(effective, namespace):
                if ref.target not in workspace.items:
                    raise ContentError(f'Missing item reference: {ref.target}')
                if ref.target in mapping:
                    cursor = rewritten
                    for key in ref.path[:-1]:
                        cursor = cursor[key]
                    cursor[ref.path[-1]] = mapping[ref.target]
                else:
                    warnings.append(f'Preserved shared item reference: {ref.target} from {ident}')
            child = {'extends': ident, 'abstract': False if ident == source_id else effective.get('abstract', False),
                     'display_name': '&f' + name.replace('_', ' ').title(), 'render': {'model': target_model}}
            delta = _delta(effective.get('properties', {}), rewritten.get('properties', {}))
            if delta:
                child['properties'] = delta
            model = {'parent': models[ident].reference} if strategy == 'alias' else copy.deepcopy(models[ident].authored)
            texture_map = model.setdefault('textures', {})
            for slot, axis in bindings.items():
                texture_map[slot] = resource_id(axes[axis][values[axis]])
            for path, payload in ((yml, _serialize_yaml(name, child)), (model_path, _serialize_json(model))):
                key = path.relative_to(source.pack.root).as_posix().casefold()
                if key in seen_paths:
                    raise ContentError(f'Duplicate recipe output path: {path}')
                seen_paths.add(key)
                outputs.append(_make_output(path, payload, owned, source.pack, 'recipe ' + recipe_id))
                if sum(len(output.payload) for output in outputs) > 64 * 1024 * 1024:
                    raise ContentError('Generated payload exceeds 64 MiB; narrow the selection')
    if not outputs:
        raise ContentError('Recipe produces no new variants')
    ownership = dict(owned)
    current_paths = set()
    for output in outputs:
        key = output.path.relative_to(source.pack.root).as_posix()
        ownership[key] = _sha(output.payload)
        current_paths.add(key)
    retained = set(owned) - current_paths
    if retained:
        warnings.append(f'{len(retained)} previously generated files are retained outside this selection; no implicit deletion')
    manifest = {'schema': 1, 'recipe_id': recipe_id, 'source_id': source_id, 'source_items': sorted(templates),
                'recipe': recipe, 'revision_sha256': _sha(_serialize_json(recipe)), 'files': dict(sorted(ownership.items()))}
    payload = _serialize_json(manifest)
    outputs.append(ProposedFile(manifest_file, payload, _sha(old_manifest) if old_manifest else None,
        'unchanged' if payload == old_manifest else ('update' if old_manifest else 'create'), 'versioned recipe and ownership'))
    plan = _attach_inputs(Plan(source.pack, source, 'recipe', target, strategy, _safe_slug('recipe_'+recipe_id), outputs,
        sorted(set(warnings)), '', manifest_file, manifest), workspace)
    plan.input_hashes.update(inputs)
    return plan
