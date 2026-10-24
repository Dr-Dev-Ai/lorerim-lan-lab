# Experimental native source ? blocked by startup crash

Read `../CODEX_HANDOFF.md` before doing anything. This is source for continuation, not an installable update.

Upstream: https://github.com/tiltedphoques/TiltedEvolution.git

Exact upstream base: `5a72cdcd17b998fb1462bb5c6fb0d60d29b98de9`

Full Windows development commit: `e1cd251346fbd35baceb1b2f5609c27e2af7da6f`

## Reconstruct the native worktree

1. Clone the upstream repository into a separate directory.
2. Check out the exact base commit above.
3. Run `git submodule update --init --recursive`.
4. Run `git apply --check /absolute/path/to/native-staging/lorerim-v05.patch`, then apply that patch.
5. `overlay/` contains the same changed/new source files for direct inspection/editing. Preserve the upstream license and instructions in AGENTS.md.
6. Build in Windows using the toolchain/targets in CODEX_HANDOFF.md. Obtain the official SKSE SDK headers separately; the co-save targets expect PluginAPI.h in the configured private SDK directory or LORERIM_SKSE_SDK.

The patch excludes compiled PEX files and private decompiled third-party scripts. It does not contain game assets, saves, credentials, private dependency sources, runtime databases or executables. The local Windows worktree retains those private build inputs for authorized inspection. Static Skill Leveling and rental overrides must be recreated with minimal source-preserving patchers against the user's installed version; do not distribute decompiled scripts.

The Python manager is also available under ../campaign-manager-staging/LoreRim-Campaign-Manager/campaign_manager/. Run its tests with that parent directory on PYTHONPATH. Native gameplay acceptance currently FAILS at Papyrus VM initialization on both installed 1.6.1170 clients, despite passing compilation and synthetic protocol/storage tests.

No automatic deployment is included. The known-working older binaries and original profile lists are currently restored on both PCs.
