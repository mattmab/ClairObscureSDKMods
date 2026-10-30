# ClairObscureSDKMods

Public mods and examples for [ClairObscurSDK](https://github.com/mattmab/ClairObscurSDK).
Mod sources and releases live here independently of the SDK runtime.

## Install

1. Install [SDK RC24](https://github.com/mattmab/ClairObscurSDK/releases/tag/v0.1.0-rc24).
2. Download a mod ZIP from [this repository's releases](https://github.com/mattmab/ClairObscureSDKMods/releases).
3. With the game closed, extract the ZIP into the game folder beside `Sandfall`.
   Each ZIP contains `SDK_Mods/NAME.sdkmod`; leave that inner archive intact.
4. Launch the game and enable the mod in Mods. Existing settings and saved maps are preserved.

Only install trusted mods: Python mod packages are not a sandbox.

## Mods

| Folder | Purpose |
| --- | --- |
| EnemyHealth | Current enemy and boss HP, using natural health-bar visibility. |
| SceneEditor | Timelines, authored sequences, cast replacements, Blueprint NPCs and whole-scene placement. |
| Cinematics | Experimental cinematic browsing and supported playback routes. |
| EnemySpawner | Isolated and original encounter routes; `-` opens the menu. |
| E33WorldBuilder | Experimental free camera, props and saved world maps. |
| WorldBuilderMapLoader | Restore saved custom structures during loading. |
| MapTravel | Travel through normal native map entrances. |
| ContinentFlight | Exploration flight for supported characters. |
| PictoEditor | Picto editing and saved overrides. |
| Statistics | Supported battle-event statistics. |
| CatalogModels | Experimental user-supplied model browser and replacement. |

SDKManagement, IntrospectionHarness and LiveObjectViewer are core packages bundled with
SDK releases. Their mod entry points also live here; shared runtime implementation stays
in the SDK repository. Example folders are source references, not the default mod bundle.
See each folder's README for feature limits and controls. Cinematic and scene tools remain
experimental; catalog presence does not mean every game sequence is fully playable.
No third-party models or user settings/maps are distributed.

## Development

The SDK checkout pins this repository at its `mods` Git submodule. Use
`git clone --recurse-submodules https://github.com/mattmab/ClairObscurSDK.git`
for the matching SDK and mod sources. Commit mod changes here, then update the SDK's
submodule pointer to qualify a new combined release. Existing SDK integration tests
continue to use those pinned mod sources.

Build a mod from a standalone checkout:

```text
python scripts/build_mods.py --sdk ../ClairObscurSDK --mod EnemyHealth --output build/enemy-health
```

The packager validates every source and resource and creates deterministic `.sdkmod`
archives. Use an explicit mod list for releases. Run mod tests with the SDK `src` directory
on `PYTHONPATH`: `python -m unittest discover -s tests`.

MIT applies to repository code; see each mod's license. Rights to source game assets and
user-supplied models remain with their respective owners.
