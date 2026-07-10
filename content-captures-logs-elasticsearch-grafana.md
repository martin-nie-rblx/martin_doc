# Content Captures: Logs, Metrics → Grafana

How backend logs reach Elasticsearch (**panopticlogs**) and how metrics flow through BEDEV2 instrumentation → VictoriaMetrics / Prometheus into Grafana.

## Short answer

The services **do not connect to Elasticsearch or VictoriaMetrics**. They:

- Write structured JSON logs to **stdout** → platform ships them to **panopticlogs**
- Expose Prometheus metrics on **`/metrics`** → platform scrapes them into **VictoriaMetrics**

Grafana already wires both as datasources on the managed/custom service dashboards (`panopticlogs`, `Prometheus`).

---

## What is panopticlogs?

**panopticlogs** is Roblox’s shared application-log store in Elasticsearch — the place Nomad service stdout/stderr lands after **Fluent Bit** scrapes it.

It is **not** a library or a sink you configure in the app. BEDEV2 services just write structured logs to the console; the platform ships them into panopticlogs. You query it from Grafana via the datasource named **`panopticlogs`** (dashboard variable `$panopticlogs_ds`).

```text
Your service (Serilog JSON → stdout / stderr)
  → Fluent Bit on the host/allocation
  → panopticlogs (Elasticsearch)
  → Grafana datasource "panopticlogs" ($panopticlogs_ds)
```

### Related stores (do not confuse)

| Name | Grafana variable | What it is | Best for |
|------|------------------|------------|----------|
| **panopticlogs** | `$panopticlogs_ds` | App stdout/stderr logs in Elasticsearch | Debugging, message text, OperationId / UseCase search |
| **canonical-log-lines** | `$cll_ds` | Request-shaped / CLL logs in Elasticsearch | Structured request log lines |
| **SystemEvents** | `$sysevents_ds` | System event stream in Elasticsearch | Platform system events |
| **Prometheus / VictoriaMetrics** | `$datasource` | Metrics TSDB (PromQL) | RPS, latency, error %, SLOs |
| **Tempo** | `tracing-${envir}` | Distributed traces | Request waterfall / cross-service correlation |

---

## Log pipeline

```text
ILogger / Serilog
    → RenderedCompactJsonFormatter (stdout)
    → Fluent Bit (Nomad container stdout/stderr scrape)
    → panopticlogs (Elasticsearch)
    → Grafana datasource "panopticlogs" ($panopticlogs_ds)
```

Managed dashboards also expose Fluent Bit health for the task (e.g. **% Logs Scraped**): percent of ingested logs that pass through Fluent Bit without being throttled/dropped. Logs can disappear **before** Elasticsearch retention if the collector throttles.

### 1. App emission (this repo)

All three services bootstrap Serilog the same way:

- `LogAsJson: true` in `appsettings.json`
- Console sink with `RenderedCompactJsonFormatter`

Example (`services/content-captures-api/src/Program.cs`):

```csharp
.WriteTo.Console(new RenderedCompactJsonFormatter())
```

Business logs use structured templates, e.g. processor flow context:

```text
[UseCase={UseCase} SourceType={SourceType} OperationId={OperationId}] {Step}: {detail}
```

See `docs/processor-pipeline.md` in the content-captures repo for the processor log contract.

### 2. Platform ingest (outside this repo)

Once deployed on Nomad, container stdout/stderr is collected by Fluent Bit and indexed into **panopticlogs**. Documents are tagged with Nomad metadata such as:

| Field | Role |
|-------|------|
| `nomad_task_name` / `.keyword` | Service filter (`content-captures-api`, `content-captures`, `content-captures-processor`, plus shard suffixes) |
| `log.level_normalized` | Level filter (used by managed dashboard `$log_level` variable) |

There is no Serilog Elasticsearch sink and no ES URL in service config.

### 3. Log retention

Retention is **not configured by content-captures**. How long panopticlogs keeps documents is a **platform ILM policy** owned by Telemetry/logging, not by this service.

Notes:

- Exact day count is not defined in this repo; confirm via Telemetry docs / `#Telemetry` / Mosaic, or empirically in Grafana Explore (widen the time range on a `nomad_task_name.keyword:<task>` query until results go empty).
- Effective availability can be shorter than ILM retention if Fluent Bit throttles/drops logs under load.
- Metrics retention (VictoriaMetrics) is a separate platform policy and is not the same as panopticlogs retention. Public Roblox observability talks have historically cited on the order of ~15 days for metrics — treat that as background, not a guarantee for logs.

### 4. Grafana consumption (logs)

Each service has a pair of dashboards (prod Grafana):

| Service | Managed (auto) | Custom (team-owned) |
|---------|----------------|---------------------|
| content-captures-api | [content-captures-api-managed](https://grafana.rbx.com/d/a9691a98a66f33e5ecf13e59dd39d0d3) | [content-captures-api-custom](https://grafana.rbx.com/d/7f5dceaa04789bafe8cabda8cc32edfa) |
| content-captures | [content-captures-managed](https://grafana.rbx.com/d/335153f036c5def8dc28c1fa63f866ff) | [content-captures-custom](https://grafana.rbx.com/d/7089840d77498f0cf732bb810cf55ad6) |
| content-captures-processor | [content-captures-processor-managed](https://grafana.rbx.com/d/d7ebf91b9c7d151810f4f9483363f496) | [content-captures-processor-custom](https://grafana.rbx.com/d/2e3e0732c5e2fd9b3b606ac877e58e9c) |

Managed dashboards already include log panels backed by `$panopticlogs_ds`:

- Recent log messages
- Logs landed by level
- Logs by message template / request path / error type
- % Logs Scraped / throttling signals (Fluent Bit via `$vm_orchestration`)

Base Lucene query used by those panels:

```lucene
nomad_task_name.keyword:$env AND log.level_normalized:$log_level
```

`$env` resolves to the Nomad task name(s) for the selected shard (e.g. `content-captures-api`).

Most **custom** panels today are Prometheus metrics (error rates, latency). Log panels live mainly on the **managed** dashboards; add new log charts on the **custom** dashboard.

### 5. How to build a log-based Grafana panel

1. Open the service **custom** dashboard (do not edit managed).
2. Add panel → datasource **panopticlogs** (or `$panopticlogs_ds` if the variable exists).
3. Use Lucene query syntax. Examples:

```lucene
# All logs for the API task
nomad_task_name.keyword:content-captures-api

# Errors only
nomad_task_name.keyword:content-captures-api AND log.level_normalized:Error

# Processor use-case / operation correlation
nomad_task_name.keyword:content-captures-processor AND message:"UseCase=UploadCaptureWithAsset"

# Specific operation id
nomad_task_name.keyword:content-captures-processor AND message:"OperationId=abc-123"
```

4. Panel types that work well:
   - **Logs** — raw recent messages (Explore-style)
   - **Time series** — count / rate with date histogram + terms aggregation on `log.level_normalized`, message template, etc.
5. Prefer filtering on structured message text you control (the `[UseCase=…]` prefix) so queries stay stable.

---

## Metrics vs logs vs traces

| Signal | Path | Grafana datasource | Best for |
|--------|------|--------------------|----------|
| Metrics | BEDEV2 instrumentation → scrape → VictoriaMetrics (PromQL) | `Prometheus` (`$datasource`) | RPS, latency, error %, SLOs |
| App logs | stdout → Fluent Bit → panopticlogs ES | `panopticlogs` | Debugging, message rates, error text |
| Traces | Tempo | `tracing-${envir}` | Request waterfall / correlation |

For operational health charts, prefer Prometheus (already on custom dashboards). Use panopticlogs when you need message content or counts of specific log lines.

---

## Metrics in detail: BEDEV2 → Prometheus / VictoriaMetrics

### Short answer

Services expose a Prometheus text scrape endpoint (`/metrics`). The platform scrapes each Nomad allocation, stores series in **VictoriaMetrics**, and Grafana queries that store through a datasource typed as **Prometheus** (`$datasource`). Apps do not push metrics to Grafana or VictoriaMetrics directly.

```text
BEDEV2 middleware / prometheus-net counters
    → HTTP GET /metrics (Prometheus exposition format)
    → platform scrape (per Nomad allocation)
    → VictoriaMetrics (central TSDB)
    → Grafana PromQL via datasource "Prometheus" ($datasource)
```

Roblox’s centralized observability stack uses VictoriaMetrics as the metrics backend and Grafana as the UI ([Grafana Labs write-up](https://grafana.com/blog/multiple-players-one-stack-inside-robloxs-centralized-observability-stack/)). In dashboards the datasource still appears as “Prometheus” because VictoriaMetrics speaks PromQL.

### 1. Emission inside the process

There are **two layers** of metrics.

#### A. Automatic BEDEV2 framework metrics (no app code)

Enabled by the service defaults in `Startup.cs`:

| Service | Registration | What gets instrumented |
|---------|--------------|------------------------|
| `content-captures-api` | `AddBEDEV2HttpServiceDefaults` + `UseBEDEV2HttpServiceDefaults` | Incoming HTTP server RPS, status codes, latency; ACL middleware |
| `content-captures` | `AddBEDEV2GrpcServiceDefaults` + `UseBEDEV2GrpcServiceDefaults` | Incoming gRPC server started/handled, latency |
| `content-captures-processor` | `AddBEDEV2SqsProcessorDefaults` + `UseBEDEV2SqsProcessorDefaults` | SQS reader/client metrics; outbound HTTP/gRPC clients |
| All | `AddBEDEV2GrpcClient<T>()` / HTTP clients | Outbound client RPS, errors, latency, circuit breakers |

These produce standard series such as:

| Metric (raw counter) | Meaning |
|----------------------|---------|
| `http_server_requests_total` | Incoming HTTP requests |
| `http_server_response_total` | Incoming HTTP responses (labels include `Endpoint`, `StatusCode`) |
| `grpc_server_started_total` | Incoming gRPC RPCs started |
| Client equivalents | `http_client_*`, `grpc_client_*` |

Common labels after scrape enrichment:

| Label | Example | Role |
|-------|---------|------|
| `task_name` | `content-captures-api` | Nomad task / service identity (dashboard `$env`) |
| `region` | `chi1`, … | Deployment region (`$region`) |
| `Endpoint` | `Moments.GetMoments`, `ContentCaptures.UploadCaptureWithAsset` | Controller/RPC name |
| `StatusCode` | `200`, `500` | HTTP status (server metrics) |
| `cell_id`, `cell_node_group`, `deployment_type` | … | Capacity / topology filters on managed dashboards |

Managed dashboards also use **recording rules** (pre-aggregated rates), e.g.:

- `task:http_server_requests:rate1m`
- `task:ok_http_server_response:rate1m`
- `task:grpc_server_started:rate1m`

Panels often query both the recording rule and the raw `rate(...[1m])` form for compatibility.

#### B. Custom business counters (`prometheus-net`)

App code creates named counters with `Metrics.CreateCounter(...)` and increments them on business outcomes. Examples in this repo:

| Metric name | Where | Labels / meaning |
|-------------|-------|------------------|
| `content_captures_api_sign_capture` | API `ContentCapturesController` | Sign-capture request count |
| `content_captures_api_counter` | API | `Method`, `UniverseId` for developer/upload paths |
| `cross_experience_post` | Processor | `status` = success/failure for moment posts |
| `captured_asset_metadata_validation` | Processor | `result` = present_valid / present_invalid / missing / … |
| `cross_experience_posting_description_textfiltered` | Processor | Description removed by text filter |
| IXP counters | gRPC + processor `MomentsExperimentProvider` | Layer / outcome labels |

Example:

```csharp
_ContentCapturesApiCounter = Metrics.CreateCounter(
    "content_captures_api_counter",
    "Number of requests to content captures api endpoints used by developer apis",
    new[] { "Method", "UniverseId" });

_ContentCapturesApiCounter.WithLabels("upload_capture_with_asset", uploadUniverseId.ToString()).Inc();
```

These appear on the same `/metrics` scrape as framework metrics. Prefer low-cardinality labels (enums, coarse IDs); avoid unbounded strings (full operation UUIDs, free-text).

Local check (gRPC service README): Prometheus metrics on **port 5001** at `/metrics`.

### 2. Scrape and storage (platform)

1. Each allocation exposes `/metrics` (BEDEV2 wires the prometheus-net metric server).
2. The platform scrape agent pulls on an interval and attaches Nomad labels (`task_name`, `region`, …).
3. Samples land in **VictoriaMetrics** (central TSDB).
4. Grafana’s `Prometheus` datasource points at that store; PromQL works as usual.

You do not configure VictoriaMetrics URLs in the service. Deployment + service-descriptor tags (`bedev2`, `type:http-service`, etc.) are enough for managed dashboards/alerts to discover the task.

### 3. Grafana: managed vs custom

**Managed** (`*-managed`, auto-generated, do not edit):

- Standard HTTP/gRPC/SQS/ACL/runtime panels
- Tags like `http_server`, `grpc_client`, `sqs_reader`, `platform-managed`
- Datasource variable `$datasource` → Prometheus
- Filter variables: `$envir`, `$env` / `$shard` (task_name), `$region`, …

Example managed PromQL (HTTP 2xx rate):

```promql
sum(rate(http_server_response_total{
  task_name=~"$env",
  region=~"$region",
  StatusCode=~"2.*",
  Endpoint!="Unknown"
}[1m])) by (StatusCode)
```

**Custom** (`*-custom`, team-owned):

- Product-specific charts (feed error %, upload error %, business counters)
- Same `$datasource` / `$env` pattern
- Example from `content-captures-api-custom` — Moments feed 5xx rate:

```promql
sum(rate(http_server_response_total{
  task_name=~"$env",
  Endpoint="Moments.GetMomentRecommendations",
  StatusCode=~"5.."
}[5m]))
/
sum(rate(http_server_response_total{
  task_name=~"$env",
  Endpoint="Moments.GetMomentRecommendations"
}[5m]))
* 100
```

### 4. Alerts

Repo alerts under `alerts/<env>/` are Prometheus rules evaluated against the same metric store. Example (`alerts/production/content-captures-content-captures-api-alerts.yml`):

```promql
(sum(rate(content_captures_api_ams_missing_signature[1m]))
 / sum(task:http_server_requests:rate1m{
     task_name=~"content-captures-api",
     Endpoint="ContentCaptures.RegisterCapture"
   })) * 100 > 5
```

Mix of custom counters + framework recording rules is normal.

### 5. How to add a metrics panel

1. Prefer **custom** dashboard for new charts.
2. Datasource: **Prometheus** / `$datasource`.
3. Always scope with `task_name=~"$env"` (and `$region` when useful).
4. Use `rate`/`increase` on counters; never graph raw counter values for RPS.
5. For endpoint health, filter `Endpoint="Controller.Action"` and `StatusCode=~"5.."`.
6. For business outcomes, query your `Metrics.CreateCounter` name + labels.
7. Validate locally: hit `/metrics` and confirm the series name/labels before shipping a panel.

### 6. When to use metrics vs logs

| Need | Use |
|------|-----|
| Error rate, latency SLO, RPS by endpoint | Metrics (`http_server_response_total`, …) |
| Count of “metadata validation failed” / IXP outcomes | Custom counters |
| Why a specific `OperationId` failed | Logs (panopticlogs) |
| Request waterfall across services | Traces (Tempo) |

---

## Practical tips

- Confirm logs locally first: `swarp run <service>` and watch JSON stdout.
- Confirm metrics locally: `curl localhost:5001/metrics` (gRPC) or the HTTP service metrics port and grep for your counter name.
- In Grafana Explore, pick **panopticlogs**, set time range, query `nomad_task_name.keyword:<task>` before building a log panel.
- In Grafana Explore, pick **Prometheus**, query `http_server_response_total{task_name=~"content-captures-api"}` before building a metrics panel.
- To approximate panopticlogs retention: widen Explore’s time range until the query returns no hits.
- Check **% Logs Scraped** on the managed dashboard if you suspect missing logs (Fluent Bit throttle/drop).
- Task names may include shard suffixes (`content-captures-api-1`); managed dashboards use `$env` / `$shard` regexes for this.
- Do not add an Elasticsearch Serilog sink or a custom VictoriaMetrics push client — platform scrape/ingest already covers both paths.
