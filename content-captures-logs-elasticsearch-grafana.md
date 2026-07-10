# Content Captures: Logs → Elasticsearch → Grafana

How backend logs from the content-captures services reach Elasticsearch and how to build Grafana panels on them.

## Short answer

The services **do not connect to Elasticsearch**. They write structured JSON to **stdout**. The Nomad/platform log pipeline scrapes that stdout into the **panopticlogs** Elasticsearch cluster. Grafana already has a `panopticlogs` Elasticsearch datasource wired into the managed/custom service dashboards.

## Pipeline

```text
ILogger / Serilog
    → RenderedCompactJsonFormatter (stdout)
    → Nomad task stdout scrape
    → panopticlogs (Elasticsearch)
    → Grafana datasource "panopticlogs" ($panopticlogs_ds)
```

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

See `docs/processor-pipeline.md` for the processor log contract.

### 2. Platform ingest (outside this repo)

Once deployed on Nomad, container stdout is collected by the platform logging stack and indexed into **panopticlogs**. Documents are tagged with Nomad metadata such as:

| Field | Role |
|-------|------|
| `nomad_task_name` / `.keyword` | Service filter (`content-captures-api`, `content-captures`, `content-captures-processor`, plus shard suffixes) |
| `log.level_normalized` | Level filter (used by managed dashboard `$log_level` variable) |

There is no Serilog Elasticsearch sink and no ES URL in service config.

### 3. Grafana consumption

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

Base Lucene query used by those panels:

```lucene
nomad_task_name.keyword:$env AND log.level_normalized:$log_level
```

`$env` resolves to the Nomad task name(s) for the selected shard (e.g. `content-captures-api`).

Related Elasticsearch datasources also present on these dashboards:

- `panopticlogs` — application stdout logs (primary)
- `canonical-log-lines` — CLL / request-shaped logs (`$cll_ds`)
- `SystemEvents` — system events (`$sysevents_ds`)

Most **custom** panels today are Prometheus metrics (error rates, latency). Log panels live mainly on the **managed** dashboards; add new log charts on the **custom** dashboard.

## How to build a log-based Grafana panel

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

## Metrics vs logs

| Signal | Path | Grafana datasource | Best for |
|--------|------|--------------------|----------|
| Metrics | BEDEV2 instrumentation → Prometheus/VictoriaMetrics | `Prometheus` (`$datasource`) | RPS, latency, error %, SLOs |
| App logs | stdout → panopticlogs ES | `panopticlogs` | Debugging, message rates, error text |
| Traces | Tempo | `tracing-${envir}` | Request waterfall / correlation |

For operational health charts, prefer Prometheus (already on custom dashboards). Use panopticlogs when you need message content or counts of specific log lines.

## Practical tips

- Confirm logs locally first: `swarp run <service>` and watch JSON stdout.
- In Grafana Explore, pick **panopticlogs**, set time range, query `nomad_task_name.keyword:<task>` before building a panel.
- Task names may include shard suffixes (`content-captures-api-1`); managed dashboards use `$env` / `$shard` regexes for this.
- Do not add an Elasticsearch Serilog sink to the app — platform ingest already covers it.
