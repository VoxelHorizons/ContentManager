# Source verification — 18 October 2026

The following sources were read directly, not inferred from earlier documentation:

| Repository | Commit | Inspected contract |
|---|---|---|
| VoxelCore | `8fa329941e83623db1baaf8685d943456f363f7a` | `ItemDefinitionParser`, `ItemInheritanceResolver`, `ContentLoader` |
| VoxelFurniture | `648fec7c4f06016b8d6ad0612019fe1210897f6a` | `FurnitureDefinitionParser` |
| VoxelVehicles | `c39416b3a9e26b3be8fed5208bf80edf11cbbcbb` | `VehicleDefinition`, `VehicleInventoryDefinition`, `VehicleChestDefinition` |

## Corrections to the original architecture examples

VoxelCore's properties/rule map merge **retains explicit null values**; it does not remove map keys. Lists replace. An explicitly empty `events: {}` clears inherited events. Structured custom-model-data maps merge by key. Concrete generated owner items explicitly override `abstract: false`. Both `.yml` and `.yaml` content files are discovered.

Furniture reference fields include `model_item`, `drop`, `animation.use`, each `blockstates` list entry's `model_item`, and item-type `display_parts.*.model_item`. Blockstate selector lists and flags must remain unchanged when substituting models. Vehicle references include `model_item`, `drop`, `inventory.preview_item`, `inventory.chest.preview_item`, and `inventory.chest.visual.item/model_item`. Chest `item` outside `visual` is a vanilla material, not a ContentID.

These are source-reviewed contracts, **not Java/Paper execution results**. Full parser parity, compiler integration, other ecosystem repositories and staging certification remain P0/P5/P6/P8 work.
