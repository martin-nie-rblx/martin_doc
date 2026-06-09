# lua-apps: How to Run & Debug — Deep-Dive Analysis

_Analysis of `/Users/mnie/dev/lua-apps` (Roblox `lua-apps` monorepo). Written 2026-06-09._

## TL;DR

`lua-apps` is **not a standalone runnable program** — it is the Lua/Luau source for Roblox's
"Universal App" (the home/avatar/social/store UI shell) and in-experience CoreScripts. You
"run" it by **mounting its source into a Roblox host** (Roblox Studio or a locally-built Roblox
Player) and **playing** a project. You "debug" it primarily via:

1. **Unit tests** (`lest`) — fastest feedback loop, no host needed.
2. **Roblox Studio** — load a `Studio-*.rbxp` project, hit Play, inspect live UI.
3. **Roblox Player / Android** — for things Studio can't do (telemetry, real device behavior),
   using the `mpbundler` live-sync server.
4. **Debug FastFlags** + on-screen overlays.

> ⚠️ **Current machine state:** the workspace is **not bootstrapped yet**. `foreman` and all
> toolchain binaries (`lest`, `lute`, `rotrieve`, `stylua`, `selene`, `rbx-aged-cli`) are **not on
> PATH**, there is **no `.venv`**, **no `sourcemap.json`**, and **no `.tool-versions/robloxdev-cli`**.
> You must complete the "First-time setup" section before anything will run.

---

## 1. What this repo is

| Aspect | Detail |
|---|---|
| Language | Lua / Luau |
| UI | Roact / React-lua + **Foundation** design system |
| State | Rodux (legacy) → **Signals** (preferred, migrating) |
| Packages | **Rotriever** workspace |
| Tests | **lest** (Jest-like, runs on `robloxdev-cli`) |
| Platform | Roblox engine (~16ms/frame @ 60 FPS) |
| Workflow | Trunk-based on `master`; feature branches `feature/JIRA-ID-title` |
| Storage quirk | Uses **Git LFS** |

It produces the **Universal App** (`apps/UniversalApp`), the **InExperience** UI
(`apps/InExperience`), plus CoreScripts/PlayerScripts, RccServer, and several smaller apps
(`CrossExperienceVoice`, `PlaybackApp`, `Playground`).

## 2. Repository layout (the part that matters)

Source is intentionally spread across several roots (see `docs/structure.md`):

| Path | Role | Status | Mounts to (DataModel) |
|---|---|---|---|
| `src/internal/` | "the monolith" / CoreGui Modules (app env only) | **Legacy**, being migrated | `CoreGui.RobloxGui.Modules.<X>` |
| `modules/<domain>/<package>/` | Rotriever workspace packages | **Preferred** | `CorePackages.Workspace.Packages.<X>` |
| `content/LuaPackages/` | External deps ("CorePackages") + workspace pkgs | — | `CorePackages.Packages.<X>` |
| `content/scripts/` | `CoreScripts` (in-exp, not overridable) + `PlayerScripts` (in-exp, overridable) | — | `CoreGui` / `PlayerScripts` |
| `apps/` | App entry-point projects (UniversalApp, InExperience, …) | — | — |
| `projects/` | **~85 `.rbxp` project descriptors** — these define what gets mounted where | — | — |
| `tests/` | **~180 `*.json` test environment configs** for `lest` | — | — |

Module domains under `modules/` include: `avatar`, `economy`, `social`, `discovery`,
`communities`, `notifications`, `core-scripts`, `core-ui`, `server-driven-ui`, `roblox-app`, etc.

**`projects/*.rbxp` is the key concept for running.** A `.rbxp` is a Rojo-style "trampoline"
project file (generated/maintained by `lute build`) that tells Studio/Player which folders to
mount into which DataModel services. The naming convention:

- `Studio-*.rbxp` → open these in **Roblox Studio** (e.g. `Studio-UniversalApp.rbxp`,
  `Studio-InExperienceUI.rbxp`, `Studio-Storybook.rbxp`).
- `*-tests.rbxp` → used by `lest` for unit testing (e.g. `LuaApps-tests.rbxp`).
- `*-mpbundler.rbxp` → used by the live-sync bundler for Player/Android
  (e.g. `UniversalApp-mpbundler.rbxp`, `InExperience-mpbundler.rbxp`).
- `*-moonbeam.rbxp` → moonbeam build variants.

There are also `projects/StudioFlagsFor*.json(c)` files — preset FastFlag bundles to paste into
Studio for specific dev surfaces (Console nav, Marketplace, In-Game Menu, etc.).

## 3. Toolchain (from `foreman.toml`)

`foreman` is the toolchain manager; it installs pinned versions of everything else:

| Tool | Version | Purpose |
|---|---|---|
| `lest` | 3.11.1 | Test runner (Jest-like) |
| `lute` | nightly | Builds the rotriever workspace → generates `.rbxp` trampolines (`lute build`) |
| `rotrieve` | 0.5.32 | Per-package dependency install (`rotrieve install`) |
| `rbx-aged-cli` | 5.10.0 | Downloads `robloxdev-cli` (sourcemap, analyze, mpbundler convert) |
| `stylua` | 2.0.1 | Formatter |
| `selene` | 0.30.0 | Linter |
| `tarmac` | 0.8.2 | Asset/image management |
| `rojo` | 7.2.1 | Project/instance tooling |
| `quantqual`, `evaluate`, `lune`, `roto`, `luauforge` | pinned | QA / scripting / build helpers |

Plus: **`robloxdev-cli`** (downloaded separately, not via foreman) for sourcemap generation,
static `analyze`, and the mpbundler convert server. **Python 3** (+ `black`) for repo scripts.

## 4. First-time setup (required — current machine is un-bootstrapped)

> macOS only (per onboarding). Reach out in `#app-foundation` Slack for setup help.

```bash
# 1. Install foreman (toolchain manager) and put it on PATH
cargo install foreman                       # if not already installed
export PATH=$HOME/.foreman/bin:$PATH        # add to ~/.zshrc to persist

# 2. Configure a GitHub Personal Access Token (CLASSIC, with repo + write:packages,
#    authorized for Roblox SSO) in ~/.foreman/auth.toml  -> [github] = "..."
#    Fine-grained tokens are NOT supported.

# 3. Install pinned tools
foreman install

# 4. (Python tooling) create venv
python -m venv .venv && source .venv/bin/activate

# 5. Install workspace dependencies + generate .rbxp project trampolines
lute build                                  # formerly: git lua install

# 6. Ensure Git LFS is set up (repo uses LFS)
git lfs install && git lfs pull
```

**IntelliSense / sourcemap (for editor type info):**

```bash
mkdir -p .tool-versions
rbx-aged-cli download robloxdev-cli --channel stable --destination .tool-versions
chmod +x .tool-versions/robloxdev-cli
./.tool-versions/robloxdev-cli sourcemap projects/LuaApps-tests.rbxp --output sourcemap.json
```

Open `lua-apps.code-workspace` in Cursor/VS Code and install: **Luau LSP**
(`JohnnyMorganz.luau-lsp`), **StyLua** (`JohnnyMorganz.stylua`), **Selene**
(`Kampfkarren.selene-vscode`). The `.vscode/settings.json` can auto-regenerate the sourcemap on
file changes.

> Re-run `lute build` whenever you switch branches or add packages. Re-run the sourcemap step
> when you add new modules or LSP type info goes stale.

## 5. Running the app

### Option A — Roblox Studio (fastest, most common)

1. `lute build` (ensures `.rbxp` projects are current).
2. In Studio: **File → Open**, pick a project:
   - Universal App: `projects/Studio-UniversalApp.rbxp`
   - In-experience UI: `projects/Studio-InExperienceUI.rbxp`
   - Storybook (isolated component testing): `projects/Studio-Storybook.rbxp`
   - Specialized dev surfaces: `Studio-ConsoleUniversalApp`, `Studio-MarketplaceDevUniversalApp`,
     `Studio-ModerationDevUniversalApp`, `Studio-UniversalVRApp`, etc.
3. **Play**. Changes on disk sync automatically.
4. Paste a matching `projects/StudioFlagsFor*.json` flag bundle into Studio FFlags if the surface
   needs it.

Caveats: **no symlinks** (breaks file sync — always use `lute build` trampolines). **Telemetry
cannot be tested in Studio** — use Player/Android. If modules fail to load, re-run `lute build`.

### Option B — Roblox Player (real client; needed for telemetry)

Requires the **`game-engine`** repo (`~/git/roblox/game-engine`) and a ~30-min first build:

```bash
# Build a Mac client that points at this lua-apps checkout
lua_apps_root_dir=$(pwd)
cd ~/git/roblox/game-engine && PATH=$(pwd)/Tools/Util:$PATH \
  git-rbx build --target MacClient --client --arm64 --ninja --optimized \
  -D RBX_LUA_APPS_DIR=$lua_apps_root_dir \
  -D RBX_ENABLE_LOCAL_FLAGS_JSON=ON \
  -D RBX_TREAT_WARNINGS_AS_ERRORS=OFF

# Launch (helper auto-finds the xcode-<ver> build dir)
bash .claude/skills/lua-apps-onboarding/scripts/launch-roblox-player.sh ~/git/roblox/game-engine
```

### Option C — Player/Android with live sync (`mpbundler`)

Build with `-D RBX_ENABLE_LUA_BUNDLER=ON`, then run the bundler server so the client hot-reloads
from disk:

```bash
.tool-versions/robloxdev-cli convert --server --config ./projects/UniversalApp-mpbundler.rbxp
```

For **Android emulator**: start the same mpbundler, then in the emulator's **Roblox Configurator**
choose `Connect: com.roblox.client` → **LUA DEV Server** → enter your Mac's LAN IP
(`ifconfig en0 | grep 'inet '`). If changes don't appear: force-stop + clear cache on both the
Configurator and Roblox apps, reconfigure, relaunch.

## 6. Debugging

### 6.1 Unit tests (primary dev loop — no Roblox host needed)

```bash
lest --forceExit                              # run everything (10–15 min)
lest -e <EnvName> --forceExit true            # one environment (see tests/<EnvName>.json)
lest -e <EnvName> -t <File.test.lua> --forceExit true   # one file
```

- Test envs live in `tests/*.json` (~180 of them: `AppChat.json`, `AvatarExperience.json`,
  `Economy.json`, …). The env name is the `-e` argument.
- `.lestrc` sets `testRunner: robloxdev-cli` and runs both `default` and `allOn` flag profiles.
- Conventions: `*.test.lua` for `modules/`, `*.spec.lua` for the `src/internal/` monolith.
- Coverage: `lest --cov --coverageOpenReport=true --coverageReporter=lcov-html -e <Env>`.

If a test fails **only** under all-on or all-off flags, use the **flag-bisection** skill to find
the culprit flag.

### 6.2 Studio runtime debugging

- Open the relevant `Studio-*.rbxp`, Play, and use Studio's **Output**, **Script Debugger**,
  breakpoints, and the **Explorer/Properties** to inspect the live instance tree
  (`CoreGui.RobloxGui.Modules.*`, `CorePackages.Workspace.Packages.*`).
- **Storybook plugin** (`Studio-Storybook.rbxp`) renders individual components in isolation — the
  best way to debug a single UI component. If the plugin is hidden, set `EnableLoadModule=true`
  and `DebugLoadDenyListedPlugins=true`, then add the **Developer Storybook** tool.
- There is an MCP-based Studio workflow (see the `open-roblox-studio` / `use-roblox-studio-mcp`
  skills) to drive Studio programmatically for verification/screenshots.

### 6.3 Debug FastFlags (from `Readme.md`)

| Flag | Effect |
|---|---|
| `FFlagDebugLuaAppValidateProps` | Roact prop validation |
| `FFlagDebugLuaArgCheck` | ArgCheck errors |
| `FFlagDebugUnmuteLuaErrors` | Fatal on muted errors |
| `FStringDebugShowFlagState` | On-screen overlay of listed flags |
| `FFlagDebugShowSiteMessageBanner` | Force site message banner |
| `FFlagDebugShowAccountSecurityPromptBanner` | Force account-security banner |
| `FFlagDebugLuaAppsUseDarkTheme` | Force dark theme |

Local flag overrides: `LocalFlags.json` (built from `src/internal/LocalFlags.json.in`, enabled
via `RBX_ENABLE_LOCAL_FLAGS_JSON=ON` in the Player build). See the **add-flag** /
**check-flag-status** skills and `docs/local-fflags.md`.

### 6.4 Static analysis / type checking

```bash
git lua precheck --ci          # selene + stylua + rotriever consistency + flag validation
stylua --check .               # formatting only (stylua . to auto-fix)
python scripts/analyze.py --config projects/LuaApps-tests.rbxp \
  --robloxcli-path "$ROBLOXCLI" --workspace-path "$(pwd)"   # Luau type/lint analyze
```

## 7. Pre-push / CI parity

CI (`null-pr` → `ci.yaml`, `deferred-lua-readiness.yaml`, `validate-release-builds.yaml`) is mostly
reproducible locally:

```bash
git lua precheck --ci                                   # static checks
lest --forceExit                                        # unit tests
lest --forceExit -- --fastFlags.overrides \
  EnableSignalBehavior=true DebugForceDeferredSignalBehavior=true ProcessEventQueueOnInput=true   # deferred-lua
python scripts/analyze.py --config projects/LuaApps-tests.rbxp --robloxcli-path "$ROBLOXCLI" --workspace-path "$(pwd)"
```

`validate-release-builds.yaml` (bundles, moonbeam, Artifactory) and the Windows/multi-engine matrix
are **CI-only**. Pre-existing failures in `assets/content/` legacy files are not your concern.

## 8. Mental model: pick the right loop

| Goal | Use |
|---|---|
| Logic / reducer / util change | `lest` unit tests |
| Single UI component look/behavior | Studio **Storybook** |
| Full app flow / navigation / live UI | `Studio-UniversalApp.rbxp` (or `Studio-InExperienceUI.rbxp`) + Play |
| Telemetry, real-device, perf | Roblox **Player** (+ mpbundler for hot reload) |
| Mobile-specific | **Android emulator** + mpbundler |
| Pre-push confidence | `git lua precheck --ci` + `lest --forceExit` |

## 9. Gotchas

- Tooling is **not on PATH right now** — do the Section 4 setup first (`foreman` missing,
  no `.venv`, no `sourcemap.json`, no `robloxdev-cli`).
- **Git LFS** is required; without it, binary/asset files come down as pointers.
- **Never use symlinks** for syncing — always `lute build` trampolines.
- Re-run `lute build` after branch switches / new packages; re-run sourcemap after new modules.
- GitHub PAT must be **classic** + **SSO-authorized for Roblox**, else `foreman`/`rotrieve` 401/403.
- The repo has a rich **skills** system under `.claude/skills/` (onboarding, run-unit-tests,
  run-ci-checks, open-roblox-studio, add-flag, figma-to-foundation, etc.) — prefer those for
  task-specific workflows.

## Appendix — Key files referenced

- `Readme.md` — FAQ, debug FastFlags, dependency setup
- `docs/structure.md` — source-root → DataModel mapping
- `foreman.toml` — pinned toolchain versions
- `.lestrc` — test runner config
- `projects/*.rbxp` — run/test/bundle project descriptors
- `tests/*.json` — `lest` environments
- `.claude/skills/lua-apps-onboarding/` — full setup + manual-testing + useful-commands references
- `.claude/skills/run-ci-checks/`, `run-unit-tests/`, `open-roblox-studio/` — workflow skills
