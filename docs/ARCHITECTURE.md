# System architecture

## 1. Goals and non-goals

**Goals:** locally edit real authored content; plan large variant families without copy/paste; provide a reliable identity/asset dependency graph; make runtime-compatible outputs; preserve human-owned edits; perform deterministic/reversible builds; give a comfortable visual interface; make bulk authoring fast without losing control.

**Non-goals:** rebuild Minecraft's resource-pack compiler; change VoxelCore runtime item identity; directly change world entities while a project is being edited; become a gameplay plugin/economy ledger; generate arbitrary 3D geometry with AI as an MVP feature; make Java 26.2 content automatically run on old versions; publish copyrighted or licensed ShopGUIPlus artifacts.

## 2. Native desktop reference architecture

```text
    Python Tkinter + ttk desktop application
      | native widgets and Canvas preview, no browser/HTTP server
      | all actions call the same Python services as the CLI
    Python 3.10+ domain services
      +-- Workspace scanner / parsers (PyYAML + json)
      +-- ContentID and inherited item inspector
      +-- Model association and texture slot resolver
      +-- Wood/wool family planner -> virtual proposed files
      +-- Ownership manifests + snapshots + rollback
      +-- Diagnostics and CLI (argparse)
      +-- Future: typed graph, property schema editors, richer previews,
                   VoxelCore Java pack validation subprocess adapter
    VoxelCore content packs and authored JSON models (canonical)
```

**Only Tkinter/Python is an application stack requirement.** VoxelCore itself remains a Java Minecraft plugin, and its Java 25 pack compiler is invoked as a *future optional external tool*, not embedded or reimplemented in Python. The first milestone contains a basic model-viewing Canvas, not a Three.js or Minecraft renderer.

**Current files:** Python `core.py`, `assets.py`, `editing.py`, `generators.py`, `recipes.py`, `transactions.py`, `lint.py`, `preview.py`, `cli.py` and `app.py`. Packaging, CI and tests are in `pyproject.toml`, `.github/workflows/` and `tests/`. Only a subset of the final studio and authoritative validation pipeline is implemented.

## 3. Modules / package boundaries

| Planned module | Responsibility | May write | Must not do |
|---|---|---|---|
| `studio-domain` | Identifiers, immutable graph, changesets, recipe AST, diagnostics | none | UI/server access |
| `studio-workspace` | Roots, discovery, CST/YAML/JSON round-trip patches, path safety, locking | staging + approved paths | change runtime allocations silently |
| `studio-adapters` | Versioned readers/writers for real plugin schemas | staged configs | invent unsupported runtime YAML keys |
| `studio-generators` | Matrices, parameter interpolation, output tracking, dependency edges | virtual files only | mutate source while previewing |
| `studio-assets` | Texture/model parsing, inherited parent chains, alias resolution, transformations | virtual assets | overwrite hand-authored models by default |
| `studio-validation` (planned) | Python schema checks and a VoxelCore compiler subprocess bridge | temporary validation roots | mutate live data on validation |
| `studio-build` (planned) | Python subprocess bridge invoking pinned VoxelCore Java compiler; capture diagnostics and ZIPs | build staging | reimplement atlas fixes |
| `studio-deploy` | Backups, transactional publishing, rollback, optional remote bridge | approved targets only | silent hot reload |
| `studio-cli` | Python argparse commands sharing domain functions | via services | bypass policy |
| `studio-ui` | Native Tkinter/ttk windows, forms, Treeview, text and Canvas | via Python domain services | duplicate plugin parsing |

All authoring semantics are Python modules shared between the native Tkinter interface and argparse CLI. Item editing now uses ruamel.yaml round trips and dedicated tests; generators continue to author isolated new YAML/model outputs to avoid rewriting human source. Full plugin schema editing and three-way conflict resolution remain future work. Version-pinned VoxelCore compiler execution will use a tightly controlled subprocess adapter and temporary sandbox, not a second compiler.

## 4. Canonical graph

**Nodes:** Project, target profile, VoxelCore pack, ContentID item, ContentID block, abstract variant/state, furniture definition, vehicle definition, model JSON, parent model, texture, font/UI glyph, language override, shop offer, showroom layout reference, recipe, generated artifact, allocation manifest, build output.

**Edges (typed):** `extends`, `render.model`, `model.parent`, `model.texture`, `model_item`, `drop`, `animation.use`, `blockstates`, `display_parts`, `seat/model preview`, `shop-stock`, `font-texture`, `pack-depends-on`, `generated-from`, `owned-by-recipe`.

Every edge carries source file, YAML/JSON path, target namespace, strength (required/optional), target compatibility and provenance. Unknown referenced resources create explicit unresolved nodes rather than disappearing. Expose inbound references and impact assessment on rename/delete. **A placed instance is not automatically rewritten** when a ContentID is renamed; warn that existing saved world data may depend on it.

A resource path such as `voxel:item/furniture/oak_table` is a model reference; `voxel:oak_table` is an item ID. Never conflate slash-style model refs, hyphenated aliases, and ContentID keys. Only the relevant runtime adapter may normalize a supported shorthand.

## 5. Workspace and file ownership

Example project:
```text
 MyVoxelProject/
   plugins/VoxelCore/
     content/<pack>/pack.yml
     content/<pack>/content/**/*.yml
     content/<pack>/assets/<namespace>/models/**/*.json
     content/<pack>/assets/<namespace>/textures/**/*.png
     render-allocations.yml      # runtime-owned, protected
     block-allocations.yml       # runtime-owned, protected
     glyph-allocations.yml       # runtime-owned, protected
   plugins/VoxelFurniture/config.yml         # optional integration
   plugins/VoxelVehicles/config.yml          # optional integration
   plugins/VoxelShop/...                     # optional integration
   .contentmanager/
     project.yml              # project pointers / schema / target profiles
     recipes/*.yml           # editable declarative generators
     manifests/*.json        # derived path ownership, hashes, ancestry
     snapshots/              # local undo and recoverable transactions
     cache/                  # disposable search/preview metadata
```
Actual source locations are configured from explicit workspace mounts; do not assume the sample tree must live under a single root. Do not track world saves, user account data, server secrets or stock/economy databases as authoring assets. Backup and ignore metadata in an explicit project policy.

A source file can be **human-authored**, **recipe-owned**, or **mixed**. Mixed files require semantic patch operations scoped to known YAML paths, with before/after hashes and conflict prompts. Deleting a recipe offers (1) detach and retain output, or (2) remove only untouched recipe-owned artifacts; human edits default to retained.

## 6. Mutation transaction (desired final guarantees; MVP is narrower)

1. Read revision and dependencies; reject external modification conflicts.
2. Construct virtual proposed output; validate namespaces, generator bounds and file collisions.
3. Present exact additions/updates/deletions and affected references, including warning severity.
4. On explicit Apply: hold workspace write lease, snapshot originals, write temporary sibling files, fsync where supported, replace only approved paths and update recipe manifest last.
5. On any write/validation error: restore originals and leave a recovery journal.
6. Notify indexer and rebuild graph; maintain undo/redo as changesets, not blind full-file resets.

The transaction service now performs optimistic dependency checks, OS-backed writer locking, sibling atomic replacement, durable before/after snapshots and explicit journal recovery. Platform durability and live publication certification remain open. Symlinks resolving outside approved roots are rejected. Read-only workspaces still support preview and validation.

## 7. Validation and build

**Future validation levels:** parse (YAML/JSON/PNG), schema (current plugin adapters), semantic inheritance, references/namespace/pack dependencies, assets/texture layers/parent cycles, generator provenance, target-feature availability, and **authoritative VoxelCore pack validate**.

VoxelCore exposes `ContentLoader`, `ItemInheritanceResolver`, `JavaPackCompiler.validate(...)`, `JavaPackCompiler.compile(...)`, and `JavaPackTarget`. A future Python subprocess bridge must invoke those capabilities through a tiny Java CLI harness, version-pinned to an exact commit. The current Python inspector approximates inheritance for display, and cannot certify a full plugin/pack build. `validate` must run against a sandbox copy including appropriate allocation manifests, and must never write the live manifests. Compiler output remains the source of truth even when Three.js preview differs.

Build compilation emits a target-specific ZIP, compiler diagnostics, input manifest, output hash, supported-version profile, and reproducibility report; content is published only after successful validation. The model/atlas compatibility fixes remain the responsibility of VoxelCore.

## 8. Integration direction

- **VoxelCore:** item/block/UI pack authoring, version-aware structured custom model data, abstract render-only items, fixed allocations, deterministic build.
- **VoxelFurniture:** `properties.furniture` forms for hitbox, local offset, seat, rotation, collision blocks, `blockstates`, animation.use, display parts, idle motion, inventories, worth.
- **VoxelVehicles:** `properties.vehicle` forms for visual/collision hitboxes, seat, suspension, physics, LAND/PLANE, storage/chest mount, tint and preview art. Vehicle plugin config and item-level properties are edited separately.
- **VoxelFurnitureShop:** read-only layout introspection first; explicit edits of shop settings, value fields, showroom variants in a gated later adapter. In-world region snapshots are *world state*, not texture or item-family generators.
- **VoxelShop:** catalogue/worth/menu authoring, source import and ID references; no editing balances, trade journal, market state or executing trades.
- **DeluxeMenus/other integrations:** read-only reference lint and placeholder preview initially; schema-valid editing only after adapters are separately verified.
- **Resourcepack-Expansion/localization:** lint namespace, textures, language files, glyph aliases and localized display names; do not auto-rewrite vanilla language keys.

## 9. Compatibility contract

The studio targets the exact VoxelCore tested profiles: `mc-1.12.2`, `mc-1.13.2`, `mc-1.14.4`, `mc-1.19.4`, `mc-1.20.5`, `mc-1.21.4`, `mc-26.2`. When data cannot be represented in a target (e.g., bitmap fonts on 1.12.2, modern tint rules or display entities on old clients), show incompatible or degraded behavior and require an explicit policy to exclude that target. Do not silently convert modern features into unsafe approximations.
