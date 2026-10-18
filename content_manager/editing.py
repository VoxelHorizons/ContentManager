"""Comment-preserving, reviewed edits to one existing item definition.

Anchored documents stay read-only until alias ownership is explicitly modeled.
No format migration, content ID rename or runtime allocation write is performed.
"""
from __future__ import annotations

import copy
import io
import math

import yaml
from ruamel.yaml import YAML

from .core import (ContentError, Plan, ProposedFile, UniqueSafeLoader, _attach_inputs,
                   _safe_slug, _sha, canonical_id)

ITEM_KEYS = {'extends', 'type', 'material', 'display_name', 'lore', 'bound', 'abstract', 'render', 'properties', 'events'}
RENDER_KEYS = {'model', 'unbreakable', 'durability', 'attributes', 'custom_model_data', 'oversized_in_gui', 'rule'}


def validate_item_shape(definition):
    """Source-reviewed structural subset; not a replacement for Java compilation."""
    if not isinstance(definition, dict):
        raise ContentError('An item definition must be a mapping')
    unknown = set(definition) - ITEM_KEYS
    if unknown:
        raise ContentError(f'Unsupported item keys: {unknown}')
    for key in ('extends', 'type', 'material', 'display_name'):
        if key in definition and not isinstance(definition[key], str):
            raise ContentError(f'{key} must be a string')
    for key in ('abstract', 'bound'):
        if key in definition and not isinstance(definition[key], bool):
            raise ContentError(f'{key} must be boolean')
    if 'lore' in definition and (not isinstance(definition['lore'], list) or not all(isinstance(v, str) for v in definition['lore'])):
        raise ContentError('lore must be a list of strings')
    for key in ('render', 'properties', 'events'):
        if key in definition and not isinstance(definition[key], dict):
            raise ContentError(f'{key} must be a mapping')
    render = definition.get('render', {})
    if set(render) - RENDER_KEYS:
        raise ContentError(f'Unsupported render keys: {set(render) - RENDER_KEYS}')
    if 'model' in render and not isinstance(render['model'], str):
        raise ContentError('render.model must be a string')
    for key in ('unbreakable', 'oversized_in_gui'):
        if key in render and not isinstance(render[key], bool):
            raise ContentError(f'render.{key} must be boolean')
    if 'durability' in render:
        value = render['durability']
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or int(value) != value:
            raise ContentError('render.durability must be a nonnegative whole number')
    if 'attributes' in render and (not isinstance(render['attributes'], dict) or not all(isinstance(k, str) and isinstance(v, bool) for k, v in render['attributes'].items())):
        raise ContentError('render.attributes must map string keys to booleans')
    if 'custom_model_data' in render:
        value = render['custom_model_data']
        if isinstance(value, dict):
            if not all(isinstance(k, str) and isinstance(v, (str, bool, int, float)) for k, v in value.items()):
                raise ContentError('Structured custom model data needs string keys and scalar values')
        elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or int(value) != value:
            raise ContentError('custom_model_data must be a nonnegative whole number or mapping')
    if 'rule' in render and (not isinstance(render['rule'], dict) or not render['rule']):
        raise ContentError('render.rule must be a nonempty mapping')


def parse_item_text(text):
    if len(text.encode('utf-8')) > 3 * 1024 * 1024:
        raise ContentError('Item YAML exceeds 3 MiB')
    try:
        obj = yaml.load(text, Loader=UniqueSafeLoader)
    except yaml.YAMLError as exc:
        raise ContentError(f'Invalid item YAML: {exc}') from exc
    validate_item_shape(obj)
    return obj


def _patch_mapping(original, desired):
    # Mutating existing ruamel nodes keeps key comments, order and scalar styles.
    for key in list(original):
        if key not in desired:
            del original[key]
    for key, value in desired.items():
        if key in original and isinstance(original[key], dict) and isinstance(value, dict):
            _patch_mapping(original[key], value)
        elif key not in original or original[key] != value:
            original[key] = copy.deepcopy(value)


def plan_edit_item(workspace, item_id, definition):
    if item_id not in workspace.items:
        raise ContentError(f'Unknown item: {item_id}')
    validate_item_shape(definition)
    item = workspace.items[item_id]
    original_bytes = item.file.read_bytes()
    if _sha(original_bytes) != workspace.input_hashes[item.file]:
        raise ContentError('File changed since scan; refresh before editing')
    source_text = original_bytes.decode('utf-8-sig')
    for token in yaml.scan(source_text):
        if isinstance(token, (yaml.tokens.AnchorToken, yaml.tokens.AliasToken)):
            raise ContentError('Anchored/aliased YAML is read-only; shared node edits require an explicit alias policy')
    rt = YAML(typ='rt')
    rt.preserve_quotes = True
    rt.width = 4096
    rt.line_break = '\r\n' if '\r\n' in source_text else '\n'
    doc = rt.load(source_text)
    key = next(key for key in doc['items'] if canonical_id(key, item.pack.namespace) == item_id)
    if item.definition == definition:
        payload = original_bytes
    else:
        _patch_mapping(doc['items'][key], definition)
        stream = io.StringIO()
        rt.dump(doc, stream)
        payload = stream.getvalue().encode('utf-8')
        if original_bytes.startswith(b'\xef\xbb\xbf'):
            payload = b'\xef\xbb\xbf' + payload
        # Check semantic preservation of unrelated content and exact requested edit.
        expected = yaml.load(source_text, Loader=UniqueSafeLoader)
        expected['items'][key] = definition
        actual = yaml.load(payload.decode('utf-8-sig'), Loader=UniqueSafeLoader)
        if actual != expected:
            raise ContentError('Round-trip changed unrelated YAML semantics; edit refused')
    virtual = copy.copy(workspace)
    virtual.items = dict(workspace.items)
    from dataclasses import replace
    virtual.items[item_id] = replace(item, definition=copy.deepcopy(definition))
    for ident in virtual.items:
        virtual.resolve_item(ident)  # catch newly introduced parent cycles/missing parents
    from .assets import ModelResolver, item_references
    effective = virtual.resolve_item(item_id)
    inputs = []
    if effective.get('render', {}).get('model'):
        model = ModelResolver(virtual).resolve(effective['render']['model'])
        inputs.extend(model.inputs)
    for reference in item_references(effective, item.pack.namespace):
        if reference.target not in virtual.items:
            raise ContentError(f'Missing referenced item: {reference.target}')
    output = ProposedFile(item.file, payload, _sha(original_bytes), 'unchanged' if payload == original_bytes else 'update', f'approved item edit {item_id}')
    return _attach_inputs(Plan(item.pack, item, 'edit', 'mc-26.2', 'round-trip-yaml', _safe_slug('edit__'+item_id), [output],
        ['Structural checks only; run VoxelCore and addon validation before publishing. Formatting changes are shown in the full file diff.']), workspace, inputs)
