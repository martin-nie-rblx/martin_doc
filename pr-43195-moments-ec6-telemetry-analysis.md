# PR #43195 Deep Dive — Moments EC6: wire recommendation View impressions into the platform feed

- **PR:** [Roblox/lua-apps#43195](https://github.com/Roblox/lua-apps/pull/43195)
- **Title:** `SHARE-2424 #flagged EC6 Moments: wire recommendation View impressions into the platform feed`
- **Author:** Eric Leong (`bloxmcrobloxface`) — co-authored with Claude
- **Branch:** `eleong-moments-ec6-analytics` → `master`
- **State:** OPEN (mergeable), not a draft
- **Size:** +323 / −35 across 15 files (6 commits)
- **Flag:** `FFlagArgusDev` (`#flagged`)
- **Analyzed:** 2026-06-09

---

## 1. TL;DR

This is a small, well-structured, flag-gated wiring PR. It connects two pieces of pre-existing-but-disconnected machinery in the Moments "Trending" feed:

1. The standalone recommendation-telemetry **emitters** (`emitRecommendationImpression` / `emitRecommendationAction`) shipped in PR #42904 but only ever called by tests.
2. The feed's **telemetry seam** (`FeedTelemetry` sink + `useFeedTelemetry` dwell tracking + `FeedContext.logAction`), which defaulted to a **no-op** because `TrendingScreen` never passed a `telemetry` prop.

The bridge is a new adapter, `createRecommendationTelemetry`, injected by `TrendingScreen` only when `FFlagArgusDev` is on. With the flag off, behavior is unchanged (no-op sink). The change is overwhelmingly additive and low-risk.

**Verdict:** Solid, mergeable, low-risk. Two minor dead-code leftovers (a declared-but-unconsumed `onJoinActivated` prop and a now-single-use `momentAttribution` helper) are worth cleaning up or annotating, but neither blocks merge. One Arrow E2E failure in the flags-on run appears unrelated to Moments and should be confirmed flaky/unrelated before landing.

---

## 2. Background & intent

- **Program:** EC6, Sprint 5 of the recs-migration plan (§1). The goal is to re-wire the new modular Moments feed to the platform recommendation telemetry pipeline.
- **Spec:** SHARE-2424 (this PR). Adjacent seams referenced: SHARE-2362 (game-launch attribution via `moments_play_intent_id`) and the SHARE-2433 navigation/perf analytics events.
- The *impression lifecycle* already existed: `useFeedTelemetry` handles viewport entry, dwell timing, and dedupe automatically. So EC6 is deliberately narrow — an adapter plus a flag-gated injection, rather than new lifecycle logic.

---

## 3. What the PR does (file by file)

### Core new file
- **`createRecommendationTelemetry.lua`** (+85, NEW) — the production `FeedTelemetry` sink. Delegates to the PR #42904 emitters and reconciles the two contracts:
  - **Action enum map** `SignalActionType → RecommendationActionType`: `AddReaction`, `RemoveReaction`, `Share`, `Report`, and `Join → Play`. `"View"` is intentionally absent (it is the impression, emitted only via `logView`) and unmapped actions return `nil`.
  - **`tracingId`**: sink attribution carries `tracingId?`; the emitter requires a `string`, so a missing id defaults to `""` rather than dropping the event.
  - **`momentsSessionId`**: injected from the store's session getter, read **non-reactively** (`getMomentsSessionId(false)`).
  - Deliberately kept in its own file so `feedTelemetry.lua` (no-op + recording sinks used in storybook/tests) stays free of any `TelemetryService` dependency.

### Type / contract widening
- **`FeedTypes.lua`**, **`FeedContext.lua`**, **`Feed.lua`** — widen `FeedTelemetry.logAction` return type from `()` to `string?` so the generated `moments_play_intent_id` (returned by the `Play` emitter) can later reach game launch. This is the EC6 ↔ SHARE-2362 seam, threaded through `FeedContext` and the `Feed` wrapper.
- **`feedTelemetry.lua`** — the no-op and recording sinks now explicitly `return nil` to satisfy the widened `string?` signature (no-op "mints no play intent id"; recording sink captures the action for assertions but returns nil).

### Position convention simplification
- **`emitRecommendationImpression.lua`** — drops the `+ 1` offset; the emitter now accepts a **1-based** `item_position` directly (matching Lua/pager convention), removing a 1-based → 0-based → 1-based round trip. Tests updated accordingly.

### Injection site
- **`TrendingScreen.lua`** (+22) — builds the adapter in a `useMemo` returning `FeedModule.FeedTelemetry?`: returns `nil` unless `FFlagArgusDev`, else `createRecommendationTelemetry({ getMomentsSessionId = GetMomentsStore().getMomentsSessionId })`. The `telemetry` prop is forwarded to the main `Feed` element **and** to `ResizeFeedContainer` (which forwards it to its inner `Feed`) so both layout arms emit impressions.

### Item-level seam (forward-looking)
- **`MomentItem.lua`** — adds an `onJoinActivated: (() -> ())?` prop, documented as "the registry container supplies one that emits the Play recommendation action."
- **`Items/Moment/init.lua`** — extracts a `momentAttribution(moment)` helper from the inline `getAttribution` logic.

### Tests
- **`createRecommendationTelemetry.test.lua`** (+129, NEW) — mocks the two emitters and asserts the adapter's mapping: impression payload fields, position pass-through, empty-string `tracingId` default, non-reactive session read, each action-type mapping, `Join → Play` returning the intent id, and `View` emitting nothing / returning nil.
- **`TrendingScreen.test.lua`** / **`TrendingScreen.overlay.test.lua`** — add `createRecommendationTelemetry` and `GetMomentsStore` stubs so the suites don't instantiate the real store or `TelemetryService` (and don't crash under all-flags-on CI).

---

## 4. Data flow (flag ON)

```
useFeedTelemetry (viewport + dwell + dedupe)
        │  logView(attribution, info{ itemPosition (1-based), durationSeconds })
        ▼
createRecommendationTelemetry sink
        │  emitRecommendationImpression{ itemId, tracingId or "", momentsSessionId, position, durationSeconds }
        ▼
TelemetryService emitter  →  recommendation impression signal

FeedContext.logAction(actionType, attribution, payload)
        │  SignalActionType → RecommendationActionType (Join → Play; View → nil)
        ▼
emitRecommendationAction{...}  →  returns moments_play_intent_id (Play only) → bubbles up as string?
```

With the flag OFF, `TrendingScreen` passes `telemetry = nil`, `Feed` falls back to the no-op sink, and nothing is emitted. Clean kill-switch.

---

## 5. Findings

### 5.1 Dead / dangling code (minor, non-blocking)

1. **`onJoinActivated` prop is declared but never wired or consumed.**
   - `MomentItem.lua` adds `onJoinActivated: (() -> ())?` (line 63) and its doc-comment claims "the registry container supplies one."
   - But `Items/Moment/init.lua`'s `render` creates `MomentItem` with only `{ data, mediaSurface }` — it does **not** pass `onJoinActivated`.
   - Inside `MomentItem.lua`, `CallToActionBar` is created with only `{ LayoutOrder }`; `props.onJoinActivated` is never referenced.
   - Net: the prop is fully inert in this PR. This is an intentional forward seam for SHARE-2362 (the Join CTA dispatch now lives internal to `MomentItem`/`MomentContext` after a master refactor), but as committed it reads as dead code. **Recommend** either (a) drop the prop until SHARE-2362 lands, or (b) keep it with a `TODO(SHARE-2362)` comment that makes the "currently unwired" status explicit, since the existing comment implies it is wired.

2. **`momentAttribution` helper is now single-use.**
   - It was extracted (with the comment "Shared by the registry's `getAttribution` … **and the item's action wiring**") to be reused by the Join attribution path. That action wiring was removed in commit `c5a4c8f`, so the helper is now called only by `getAttribution`. The extraction is harmless but no longer earns its keep, and the comment is now misleading. **Recommend** either inline it again or fix the comment.

> Both findings stem from the same history: the PR originally added a `MomentItemContainer` that read `FeedContext` and emitted the Join action, then removed it after a master refactor moved the CTA internal. The telemetry adapter (the actual EC6 deliverable) is unaffected; these are residue from that pivot.

### 5.2 Correctness / risk review

- **Position convention change is safe.** The only production caller of `emitRecommendationImpression` is the new sink (the codebase otherwise references it only from tests and the mock-datamodel config). The sink passes `info.itemPosition`, which is 1-based, matching the emitter's new expectation. No other call site still passes 0-based, so no silent off-by-one regression.
- **No-op preservation verified.** Flag-off path returns `nil` telemetry → no-op sink → no emissions. The widened `string?` return is satisfied by explicit `return nil` in both no-op and recording sinks.
- **Non-reactive session read** (`getMomentsSessionId(false)`) is correct: telemetry should snapshot the session id at emit time, not subscribe to it.
- **BuilderAI's earlier `flushView()` concern is now moot** for this PR: it flagged the original `MomentItemContainer` Join handler for emitting `Play` without first calling `feed.flushView()` (which would inflate dwell and mis-order View vs. Play). That handler was removed; no Join action is emitted from the item layer in this PR. The ordering contract (`flushView` before a Join) remains documented for whoever implements SHARE-2362, and should be honored then.
- **`ResizeFeedContainer` telemetry forwarding** was a real gap that the author fixed in the final commit (added `telemetry` to `ResizeFeedContainerProps` and forwarded it to the inner `Feed`). Without it, impressions would be silently dropped in the resize-viewport arm when both immersive flags are on. Good catch — verify a test exercises that arm if feasible.

### 5.3 Test coverage

- New adapter is thoroughly unit-tested (mapping, defaults, return values, non-reactive read) without pulling in `TelemetryService` — a clean isolation pattern.
- Both `TrendingScreen` suites were updated to stub the new dependencies, fixing an all-flags-on crash that BuilderAI flagged (P1).
- **Codecov:** 97.65% patch coverage; 2 uncovered lines (`Feed.lua` 1 line, `Items/Moment/init.lua` 1 line). Acceptable; the uncovered `Feed.lua` line is the trivial `return telemetry.logAction(...)` passthrough.
- A `Feed.test.lua` "SHOULD emit a Join action" test was intentionally removed (commit `c5a4c8f`) with a `TODO(SHARE-2362)` to re-add once the CTA dispatch is wired. Tracked, acceptable.

---

## 6. CI / automated review status

| Check | Result | Notes |
|---|---|---|
| **Require Count** | ⚪ 0 delta | No bundle-size regression (StartupPage / UniversalApp / LaunchApp / HomePage all unchanged). |
| **Codecov** | 97.65% patch | 2 missing lines; project-acceptable. |
| **Quantqual** | mixed, negligible | 7 metrics slightly up, 5 slightly down (all deltas ≤ 0.003, mostly noise). |
| **BuilderAI** | 1+2 issues, all addressed | Initial `flushView`/Join concern moot after removal; the P1 overlay-test crash and P2 resize-forwarding gap were both fixed in later commits. |
| **Arrow E2E** | ⚠️ flags-on FAIL | `test_experience_details_page_more_invite_friend` failed only with flags on ("UI/UX Change"); flags-off passed. |

**Arrow E2E caveat:** the single flags-on failure is on the *experience details / invite-friend* path, which is unrelated to the Moments feed. The flags-on run only enabled `FFlagArgusDev`. This is most likely a flaky/unrelated E2E or a baseline visual diff, but it should be confirmed (re-run or triage the Allure report) before merge so it isn't masking a real regression from the flag.

---

## 7. Strengths

- **Minimal blast radius:** strictly additive, fully gated behind `FFlagArgusDev`, with a clean no-op fallback.
- **Good separation of concerns:** the adapter lives in its own file specifically to keep the dependency-free sinks free of `TelemetryService` — thoughtful about storybook/test isolation.
- **Self-documenting:** comments explain the *why* (enum gaps, tracingId defaulting, non-reactive read, the EC6↔SHARE-2362 seam) rather than the *what*.
- **Responsive to review:** every BuilderAI finding was either fixed or rendered moot, and the author proactively fixed the resize-arm forwarding gap and an analyze type error.

## 8. Recommendations (priority order)

1. **(Low) Resolve the `onJoinActivated` dead prop** — drop it, or relabel it with an explicit `TODO(SHARE-2362): currently unwired` so reviewers don't assume it's active.
2. **(Low) Reconcile `momentAttribution`** — inline it again or correct its "shared with action wiring" comment now that it's single-use.
3. **(Should-do before merge) Triage the flags-on Arrow E2E failure** — confirm it's unrelated/flaky rather than a `FFlagArgusDev` side effect.
4. **(Future / SHARE-2362) Honor the `flushView()`-before-`Join` contract** when the Join dispatch is finally wired, to avoid the dwell-inflation/ordering issue BuilderAI originally raised.

---

## 9. File change summary

| File | +/− | Type | Role |
|---|---|---|---|
| `Feed/createRecommendationTelemetry.lua` | +85 | NEW | The adapter sink (core deliverable). |
| `Feed/createRecommendationTelemetry.test.lua` | +129 | NEW | Adapter unit tests. |
| `Feed/FeedTypes.lua` | +4/−2 | mod | Widen `logAction` → `string?`. |
| `Feed/FeedContext.lua` | +2/−1 | mod | Thread `string?` return. |
| `Feed/Feed.lua` | +2/−2 | mod | Return `logAction` result. |
| `Feed/feedTelemetry.lua` | +6/−2 | mod | No-op/recording sinks return nil. |
| `Feed/init.lua` | +7/−4 | mod | Export `createRecommendationTelemetry`. |
| `Feed/Items/Moment/MomentItem.lua` | +3 | mod | Add (currently inert) `onJoinActivated` prop. |
| `Feed/Items/Moment/init.lua` | +21/−15 | mod | Extract `momentAttribution` helper. |
| `Analytics/emitRecommendationImpression.lua` | +2/−1 | mod | Accept 1-based position directly. |
| `Analytics/emitRecommendationImpression.test.lua` | +8/−8 | mod | Update position expectations. |
| `Feed/Feed.test.lua` | +3 | mod | TODO note; removed Join test. |
| `TrendingScreen.lua` | +22 | mod | Build + forward telemetry behind flag. |
| `TrendingScreen.test.lua` | +17 | mod | Stub adapter + store. |
| `TrendingScreen.overlay.test.lua` | +12 | mod | Stub adapter + store (fix all-on crash). |
