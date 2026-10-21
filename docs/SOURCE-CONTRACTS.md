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

## Additional integration boundaries reviewed

| Repository | Commit | Reviewed entry point and boundary |
|---|---|---|
| VoxelFurnitureShop | `0bff7645cbbc7f9cb9cc501eef64ead027b6e69b` | `ShopRepository`: showroom cuboids/active variants/closure state are persistent world-facing data; not model-family derivatives |
| VoxelShop | `a308377d9d0a08224daaea9bfa4534c9063000b0` | `ShopGuiCatalogueImporter`: reads authored shops, `item.voxelcore` or offer-level `voxelcore`; market state and trade journals are separate |
| VoxelWorlds | `b184975176dca14962bc191c6ec0ef6b8e3ddbf1` | `WorldEntryService`: `first-entry.<world>` config differs from persisted `players.yml` visited/location data |
| Resourcepack-Expansion | `896e96ca34ef3d454f37ea06963c0c01873eb255` | `ResourcepackExpansion`: locale and `translate_` requests delegate to pack translations; runtime player pack status is separate |
| DeluxeMenus | `1e13655545ae0ef252959ab93c5c582594c4d2fa` | `DeluxeMenusConfig`: menu files, command arguments, requirements and item hooks have a separate grammar from VoxelCore items |

These inspections establish integration boundaries only. No complete editor or runtime adapter for these five plugins is shipped.

The pale-oak palette gate was corrected to include Minecraft 1.21.4, following
[Mojang's 1.21.4 release notes](https://www.minecraft.net/en-us/article/minecraft-java-edition-1-21-4).
No proprietary vanilla textures/models were copied.

## Updated pack-compiler contract — 21 October 2026

Current VoxelCore source revision: `1b6489c5d396c119f9f6e0326eabb1b2aeaf5b39`.
Read directly: `voxelcore-pack/.../JavaPackCompiler.java`,
`JavaPackTarget.java`, `JavaPackBuildResult.java`, and
`voxelcore-common/.../ContentPackDiscovery.java`.

- `JavaPackCompiler.validate(contentRoot, allocationManifestPath, target)`
  does **not** request ZIP output (`writeOutput=false`); the bridge stages
  inputs anyway to prevent read/write assumptions reaching user packs.
- `JavaPackTarget.MC_26_3`: target ID `mc-26.3`, pack format 97, minor 1,
  range metadata. `MC_26_2`: format 88, minor 0.
- `ContentPackDiscovery.discover` expects **pack directories beneath a
  content root**, even if a user has opened a single pack.
- These verified **source declarations** are not proof of a successful Maven
  build, JVM execution or Paper plugin startup. The external classpath
  is not cryptographically pinned yet.

See [Java validation bridge](JAVA-VALIDATION.md).
