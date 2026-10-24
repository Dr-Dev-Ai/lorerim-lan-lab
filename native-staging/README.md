# Experimental native source — 1170 recovery and co-op candidates

Read `../CODEX_HANDOFF.md` before doing anything. This is source for continuation, not an installable update.

Upstream: https://github.com/tiltedphoques/TiltedEvolution.git

Exact upstream base: `5a72cdcd17b998fb1462bb5c6fb0d60d29b98de9`

Full Windows development commit: `910f468f32c06da2be3625b49306dfbabd51b7d9`

## Reconstruct the native worktree

1. Clone the upstream repository into a separate directory.
2. Check out the exact base commit above.
3. Run `git submodule update --init --recursive`.
4. Run `git apply --check /absolute/path/to/native-staging/lorerim-v05.patch`, then apply that patch.
5. `overlay/` contains the same changed/new source files for direct inspection/editing. Preserve the upstream license and instructions in AGENTS.md.
6. Build in Windows using the toolchain/targets in CODEX_HANDOFF.md. Obtain the official SKSE SDK headers separately; the co-save targets expect PluginAPI.h in the configured private SDK directory or LORERIM_SKSE_SDK.

The patch excludes compiled PEX files and private decompiled third-party scripts. It does not contain game assets, saves, credentials, private dependency sources, runtime databases or executables. The local Windows worktree retains those private build inputs for authorized inspection. Static Skill Leveling and rental overrides must be recreated with minimal source-preserving patchers against the user's installed version; do not distribute decompiled scripts.

The Python manager is also available under ../campaign-manager-staging/LoreRim-Campaign-Manager/campaign_manager/. Run its tests with that parent directory on PYTHONPATH. Host 1170 startup, save loading, connection, party sleep and repeated single-item pickup have passed local checks. Unpartied sleep, the remaining magicka regeneration penalty and two-client acceptance remain unresolved. The connected-menu candidate passed host Map/Journal clock progression, a new manual save/reload, first/third-person map checks and local-map/camera/sound checks. Arbitrary custom menus, overwrite/quicksave and two-client/checkpoint regressions remain untested.

No automatic deployment is included. The host runs the experimental recovery candidate with reversible backups. Terra has not received this candidate. The historical patch filename is retained; SOURCE_MANIFEST.json identifies the current source commit.
