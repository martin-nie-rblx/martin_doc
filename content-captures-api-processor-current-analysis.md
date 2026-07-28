# Content Captures API and Processor — Current Architecture Analysis

Date: 2026-07-28  
Source: `Roblox/content-captures` `master` plus the current Creator Hub integration

## Executive summary

Separating `content-captures-api` from `content-captures-processor` is architecturally justified:

- the API owns synchronous HTTP concerns and quickly hands long-running work to SQS;
- the processor can scale independently and isolates transcode, moderation, permission, feed, DataStore, and notification work from API request capacity.

The main issue is not the existence of a processor. It is that one processor handler has become the workflow engine for several use cases. `ContentCaptureEventHandler.cs` is 1,398 lines, has more than ten injected dependencies, and performs routing, polling, validation, permission grants, content filtering, feed registration, DataStore writes, status persistence, notifications, and compatibility handling.

The most urgent integration issue is a status-contract mismatch:

- Creator Hub calls `contentCapturesCreateInfluencerMomentFromVideo`, receives an `operationId`, and polls `contentCapturesCheckUploadStatus` up to 60 times.
- `ProcessInfluencerMomentPublishAsync` explicitly invokes the shared core with `storeClientUploadResult: false`.
- `check-upload-status` reads the upload result that the processor persists through `StoreRobloxCapturedAssetUploadResultAsync`.
- Therefore the influencer path does not naturally write the state that Creator Hub is waiting for. Publishing the Moment and sending a notification do not make that status endpoint return `Found`.

This should be fixed before larger architectural work.

## 1. Current service boundaries

### `content-captures-api`

The API is not merely a thin transport adapter. It currently owns:

- authentication and request validation;
- feature switches and rollout allowlists;
- capture-signing and eligibility operations;
- influencer video upload to `assets-upload-api`;
- server-side Moment ID generation;
- construction and enqueueing of `ContentCapturesSqsMessage`;
- upload-status reads;
- Moments reads, recommendations, reactions, deletion, and data cleanup;
- Post and text-generation functionality through other controllers and hosted workers.

For the capture publish flow, its intended responsibility is still clear: establish a trusted synchronous boundary, start the asynchronous operation, enqueue a command, and return an operation handle.

### `content-captures-processor`

The processor is a BEDEV2 SQS consumer. `Startup` configures one queue and maps it to `ContentCaptureEventHandler`.

The handler routes these message types:

- `RobloxCapturedAssetUpload`
- `UploadCaptureWithAsset`
- `InfluencerMomentPublish`
- `Unknown` legacy fallback

The shared processing trunk:

1. Resolve the asset ID directly or by polling `assets-upload-api`.
2. Poll moderation until reviewed.
3. Validate captured-asset metadata where required.
4. Grant `PlayerSharedUniverseUse` to the selected universe.
5. Optionally persist an upload result and send an upload notification.
6. For Moment use cases, filter description/overlays and stickers.
7. Register a feed item.
8. Write the Moment to DataStore.
9. Send a success/failure notification.
10. Update the user-has-Moments Redis cache.

The processor therefore behaves as an application workflow orchestrator, not a small queue adapter.

## 2. End-to-end flows

### Creator Hub influencer flow

1. Creator Hub submits the video and serialized `MomentPublishData`.
2. The API accepts a request body up to 3.75 GB, validates the request, and forwards the video through `assets-upload-api`.
3. For multipart uploads, the API computes an MD5 over the complete file, obtains pre-signed chunk URLs, reads a batch of chunks into memory, and uploads them in parallel.
4. The API extracts an asynchronous upload operation ID, generates the Moment ID, and sends `InfluencerMomentPublish` to SQS.
5. The processor polls `v1/operations/{operationId}` until the asset ID is available.
6. It polls moderation, grants permissions, filters metadata, registers the feed item, writes the Moment, and sends a result notification.
7. Creator Hub separately polls `check-upload-status` using the operation ID.

Step 7 is not connected to a status write in the influencer processor path.

### In-experience flow

`UploadCaptureWithAsset` can represent either:

- an in-experience Moment publish when `MomentPublishData` is present; or
- a permission-extension operation when it is absent.

The behavior depends on `Type`, `SourceType`, `MomentPublishData`, and rollout settings such as `EnableMomentPostUploadResultPersistence`.

The gRPC-originated `RobloxCapturedAssetUpload` path usually handles a capture whose transcode has already completed. It persists client status and sends stream notifications. A legacy variant may also include embedded Moment publish data.

## 3. What is working well

### Correct asynchronous service boundary

Transcode and moderation can take minutes. Keeping them out of the HTTP request lifecycle protects API concurrency and allows independent worker scaling.

### Explicit message routing is improving the legacy design

`ContentCaptureProcessorMessageType` and `ContentCaptureSourceType` make routing intent more explicit than inferring behavior solely from nullable fields. The handler validates several illegal combinations.

### Shared core reduces direct duplication

`ProcessUploadCoreAsync` centralizes asset resolution, moderation, metadata checks, and permission grants. Each use-case adapter supplies policy flags.

### Useful observability exists

The processor records end-to-end handling duration by source and counters for business failure reasons, filtering, metadata validation, and Moment posting.

### Sensitive outcome handling

Moderated or failed uploads hide the asset ID before storing a developer-facing result, and notification paths avoid leaking a moderated asset ID.

## 4. Main risks

### P0/P1: inconsistent completion contract

Creator Hub polls a status store that `InfluencerMomentPublish` does not update. This is a concrete cross-repository contract defect, not only an architectural preference.

Recommended immediate choices:

1. Persist a unified influencer publish result under the returned operation/correlation ID; or
2. Make Creator Hub query Moment publish state by the returned `momentId`; or
3. Expose/consume the existing success/failure notification as the completion signal.

The first option is the smallest conceptual change if `check-upload-status` is intended to remain the canonical contract, but its model should distinguish `Pending`, `Succeeded`, `Moderated`, and `Failed` rather than only `Found`/`NotFound`.

### P1: blocking polling consumes SQS concurrency

Defaults allow:

- influencer operation polling: 30 attempts with 2-second delay, approximately 58 seconds;
- moderation polling: 30 attempts with 10-second delay, approximately 5 minutes;
- metadata retry delays after that.

During `Task.Delay`, the handler still occupies one of the default ten consumer concurrency slots. Ten slow messages can therefore stop useful work even while almost no CPU is used.

The default visibility timeout is 11,000 seconds, approximately 3 hours 3 minutes. That prevents normal redelivery during the long handler but also shows that SQS message handling is being used as long-running workflow state.

### P1: the API proxies very large videos

The influencer endpoint accepts request bodies up to 3.75 GB. Even though multipart forwarding bounds chunk-buffer memory, the bytes traverse the API and the upload requires:

- one complete read to compute MD5;
- another complete read to upload;
- a long-lived inbound HTTP request;
- outbound bandwidth from the API;
- temporary request-body storage or buffering behavior controlled by the ASP.NET host.

A client-direct pre-signed multipart upload would make the API a control-plane service rather than a media data-plane proxy.

### P1/P2: non-atomic Moment publication

The processor registers the feed item first and writes the Moment DataStore second. If the DataStore write fails, the handler sends failure and returns, but there is no visible compensation to remove the feed item.

At-least-once delivery also means retries can repeat side effects. The flow needs explicit idempotency keys and compensation or reconciliation for:

- feed registration;
- Moment DataStore writes;
- notifications.

### P2: one weakly typed message represents multiple commands

`ContentCapturesSqsMessage` contains fields that are required only for some use cases:

- `AssetId` versus `OperationId`;
- optional `MomentPublishData`;
- `SourceType`;
- legacy `IsInfluencer`;
- `Type`;
- optional forwarded request context.

Illegal combinations are caught only at runtime. Separate versioned command contracts would make required fields explicit and reduce the branch matrix.

### P2: mixed failure and deletion semantics

Many business failures log, increment a metric, and return successfully from the SQS handler. Some infrastructure failures throw. Parse failures and stale messages are explicitly acknowledged without retry.

`Startup` also configures `deleteOnHandlingErrors: true`; the exact framework semantics should be verified, because if it acknowledges messages after thrown handler errors, transient failures may be lost rather than retried.

Failures should be classified explicitly:

- permanent invalid command: acknowledge and emit a terminal result;
- expected business rejection: acknowledge and persist rejection;
- transient dependency failure: retry with bounded backoff;
- exhausted retries: DLQ plus terminal status.

### P2: handler and API controller concentration

`ContentCaptureEventHandler` is 1,398 lines. `ContentCapturesController` is over 1,100 lines. Both encode multiple use cases and policy decisions.

The processor's constructor dependencies include assets registry, metadata, content captures gRPC, raw HTTP, feed, Moment DAO, environment resolution, notifications, text filtering, settings, logging, and Redis. This is a strong signal that the handler is an orchestration composition root rather than one unit-testable use case.

### P2: legacy compatibility remains in the hot path

`Unknown`, `IsInfluencer`, and `SourceType` coexist. Legacy `RobloxCapturedAssetUpload` messages may unexpectedly contain `MomentPublishData` and trigger publishing.

Compatibility code should have a measured removal condition based on maximum queue retention and deployed producer versions.

## 5. Recommended evolution

### Phase 1: fix contracts and reliability

1. Define one publish-operation model:
   `Accepted → Uploading/Transcoding → Moderating → Publishing → Succeeded/Rejected/Failed`.
2. Persist every transition by correlation ID.
3. Correct Creator Hub to use that contract.
4. Add an idempotency key to feed and DataStore writes.
5. Verify SQS exception/deletion semantics and configure a DLQ.
6. Remove static AWS access-key construction from the API in favor of the standard credential chain/IAM role.

### Phase 2: split the processor without changing infrastructure

Keep SQS but introduce one typed handler per command:

- `HandleRobloxCapturedAssetUpload`
- `PublishInExperienceMoment`
- `PublishInfluencerMoment`
- `ExtendCapturePermission`

Extract shared activities:

- resolve asset;
- await moderation;
- validate metadata;
- grant permission;
- publish Moment;
- persist operation status.

This makes retry and idempotency policy explicit per step while retaining the existing deployment model.

### Phase 3: stop waiting inside a handler

Prefer asset-ready and moderation-decision events. If upstream services cannot emit events, enqueue delayed continuation messages:

- `ResolveAssetRequested`
- `ModerationCheckRequested`
- `PublishMomentRequested`

Each message performs bounded work and releases the consumer slot. The operation store becomes durable workflow state.

### Phase 4: move large media off the API

Have the API initiate multipart upload and return pre-signed URLs. Creator Hub uploads directly, then calls a completion endpoint. The API validates completion and enqueues publication.

### Phase 5: adopt a workflow engine only if justified

Temporal, Step Functions, or another durable orchestrator becomes worthwhile if the number of steps, retries, timers, compensations, and cross-team events keeps growing. It should not be the first move; the status-contract defect and handler decomposition can be fixed with the existing stack.

## Bottom line

The API/processor split itself is sound. The current design problem is that the queue consumer has become a long-lived, poll-driven workflow engine with implicit state and mixed completion contracts.

The highest-return sequence is:

1. repair the Creator Hub completion contract;
2. establish idempotent, terminal operation states;
3. split the handler into typed use cases and activities;
4. replace in-handler waits with event or delayed-message continuations;
5. move large video bytes to direct upload.

