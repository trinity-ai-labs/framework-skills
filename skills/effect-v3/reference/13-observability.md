# Effect Observability: Logging, Metrics, Tracing

When you reach for this: you need structured logs, counters/gauges/histograms, distributed traces, or OTel export in an Effect application.

---

## Contents

- [Structured Logging](#structured-logging)
- [Metrics](#metrics)
- [Tracing](#tracing)
- [`@effect/opentelemetry`](#effectopentelemetry)
- [Common pitfalls](#common-pitfalls)
- [See also](#see-also)


## Structured Logging

### Log functions

```ts
import { Effect } from "effect"

// All accept variadic args; the first is the primary message
Effect.log("something happened")            // INFO
Effect.logTrace("low-level detail")         // TRACE
Effect.logDebug("debug info")               // DEBUG
Effect.logInfo("informational")             // INFO (same as log)
Effect.logWarning("something suspicious")   // WARNING
Effect.logError("something went wrong")     // ERROR
Effect.logFatal("unrecoverable state")      // FATAL
```

Log functions accept multiple args; all are printed as the message array:

```ts
yield* Effect.logError("db error", error, { userId })
```

### Log levels and filtering

Default minimum level is `INFO`. Change it with `Logger.withMinimumLogLevel` (scoped to an effect) or the `Logger.minimumLogLevel` layer (process-wide):

```ts
import { Effect, Logger, LogLevel } from "effect"

// Scoped to one effect
const program = Effect.logDebug("trace this").pipe(
  Logger.withMinimumLogLevel(LogLevel.Debug)
)

// Process-wide layer
const MinDebug = Logger.minimumLogLevel(LogLevel.Debug)
Layer.launch(MyLive.pipe(Layer.provide(MinDebug)))
```

`LogLevel` values (ascending verbosity): `None` < `Fatal` < `Error` < `Warning` < `Info` < `Debug` < `Trace` < `All`.

### Annotating logs

Annotations attach key-value metadata to every log line emitted inside a scoped effect:

```ts
import { Effect } from "effect"

const program = Effect.gen(function* () {
  yield* Effect.logInfo("processing request")
  yield* Effect.logInfo("done")
}).pipe(
  Effect.annotateLogs("requestId", "abc-123"),
  // or pass a record for multiple keys at once:
  Effect.annotateLogs({ service: "api", version: "1" })
)
// → timestamp=... level=INFO fiber=#0 message=processing request requestId=abc-123 service=api version=1
```

`Effect.annotateLogsScoped` does the same but only while a Scope is open — useful when you want cleanup.

### Log spans (`withLogSpan`)

`withLogSpan` adds a timing label to every log inside the effect:

```ts
const traced = Effect.gen(function* () {
  yield* Effect.logInfo("start")
  yield* Effect.sleep("200 millis")
  yield* Effect.logInfo("end")
}).pipe(Effect.withLogSpan("myOperation"))
// → message=start myOperation=0ms
// → message=end   myOperation=200ms
```

Spans nest: inner spans show elapsed time relative to their own start.

### Custom loggers

```ts
import { Logger, Layer, LogLevel } from "effect"

// Build a logger from scratch
const myLogger = Logger.make(({ logLevel, message, annotations, spans }) => {
  // message is ReadonlyArray<unknown>
  console.log(JSON.stringify({ level: logLevel._tag, msg: message, ...Object.fromEntries(annotations) }))
})

// Swap the default logger
const MyLoggerLive: Layer.Layer<never> = Logger.replace(Logger.defaultLogger, myLogger)

// Add a second logger alongside the default
const ExtraLogger: Layer.Layer<never> = Logger.add(myLogger)
```

#### Built-in logger layers

| Layer | Format | Notes |
|---|---|---|
| `Logger.pretty` | Colorised, human-readable | dev default |
| `Logger.json` | Newline-delimited JSON | structured prod logging |
| `Logger.logFmt` | `key=value` logfmt | Loki / syslog friendly |
| `Logger.structured` | JS object (useful for testing) | |

```ts
// Provide as a layer
const ProdLive = MyAppLive.pipe(Layer.provide(Logger.json))
```

---

## Metrics

### Constructors

```ts
import { Metric, MetricBoundaries } from "effect"

// Counter — monotonically increasing (or bidirectional with incremental: false)
const requests = Metric.counter("http_requests_total", {
  description: "Total HTTP requests",
  incremental: true  // default true — prevents decrement
})

// Gauge — current value, goes up or down
const activeConns = Metric.gauge("active_connections", {
  description: "Currently open connections"
})

// Histogram — distribution of observed values across buckets
const latency = Metric.histogram(
  "request_duration_ms",
  MetricBoundaries.linear({ start: 0, width: 10, count: 11 }),
  "HTTP request latency in milliseconds"
)

// Summary — sliding-window quantiles
const rtSummary = Metric.summary({
  name: "response_time_summary",
  maxAge: "1 minutes",
  maxSize: 100,
  error: 0.01,               // 1 % allowed error on quantile values
  quantiles: [0.5, 0.9, 0.99],
  description: "P50/P90/P99 response time"
})

// Frequency — count occurrences of string events
const errorKinds = Metric.frequency("error_kinds", {
  description: "Counts distinct error kinds",
  preregisteredWords: ["timeout", "auth", "not_found"]
})

// Timer — histogram pre-wired to accept Duration, auto-tagged time_unit=milliseconds
const dbTimer = Metric.timer("db_query_ms", "DB query duration")
```

### Tagging

```ts
// Static tag
const tagged = Metric.tagged(requests, "method", "GET")
// or fluent:
const tagged2 = requests.pipe(Metric.tagged("method", "GET"))

// Multiple static tags via label list
import { MetricLabel } from "effect"
const withLabels = Metric.taggedWithLabels(requests, [
  MetricLabel.make("env", "prod"),
  MetricLabel.make("region", "us-east-1")
])

// Dynamic tags derived from the update value
const dynamicTagged = Metric.taggedWithLabelsInput(
  errorKinds,
  (errorCode: string) => [MetricLabel.make("code", errorCode)]
)
```

### Applying a metric to an effect

A metric is a function from `Effect<A, E, R>` → `Effect<A, E, R>`:

```ts
// Apply as aspect (call the metric like a function)
const countedEffect = requests(Effect.succeed("ok"))
// or pipe form:
const countedPipe = Effect.succeed("ok").pipe(requests)

// Track success value
const tracked = Effect.succeed(42).pipe(Metric.trackSuccess(requests))

// Track errors
const errTracked = Effect.fail("oops").pipe(Metric.trackError(errorMetric))

// Track defects (unexpected crashes)
const defectTracked = riskyOp.pipe(Metric.trackDefect(crashCounter))

// Track duration (works with Histogram<Duration> / timer)
const timedOp = dbQuery.pipe(Metric.trackDuration(dbTimer))
// or transform the duration:
const timedMs = dbQuery.pipe(
  Metric.trackDurationWith(latency, (dur) => Number(dur.millis))
)
```

### Increment / set directly

```ts
yield* Metric.increment(requests)
yield* Metric.incrementBy(requests, 5)
yield* Metric.set(activeConns, 42)       // for gauges
yield* Metric.update(errorKinds, "timeout")
```

### Reading a snapshot

```ts
const snap = yield* Metric.value(requests)  // MetricState.Counter
const all  = yield* Metric.snapshot         // ReadonlyArray<MetricPair.Untyped>
```

---

## Tracing

### `Effect.withSpan`

```ts
import { Effect } from "effect"

const result = yield* Effect.gen(function* () {
  yield* Effect.sleep("50 millis")
  return 42
}).pipe(
  Effect.withSpan("myOperation", {
    attributes: { userId: "u-1" },
    kind: "server"          // "internal" | "server" | "client" | "producer" | "consumer"
  })
)
```

Spans nest automatically — child spans reference their parent via the fiber context. Pass `root: true` to force a new root even if a parent exists. Pass `parent: externalSpan` to link to an externally propagated span.

`SpanOptions`:

```ts
{
  attributes?: Record<string, unknown>
  links?: ReadonlyArray<SpanLink>
  parent?: AnySpan              // override parent
  root?: boolean                // force new root
  context?: Context<never>      // inject W3C trace-context from inbound request
  kind?: SpanKind
  captureStackTrace?: boolean
}
```

### Annotating spans

```ts
// Add attributes to ALL spans in the sub-effect (set before they begin)
yield* longOp.pipe(Effect.annotateSpans("db.system", "postgres"))
yield* longOp.pipe(Effect.annotateSpans({ "db.system": "postgres", "db.name": "app" }))

// Add attributes to the CURRENTLY ACTIVE span at the call site
yield* Effect.annotateCurrentSpan("rowsAffected", 14)
yield* Effect.annotateCurrentSpan({ userId: "u-1", plan: "pro" })
```

### Accessing the current span

```ts
import { Effect, Tracer } from "effect"

const span = yield* Effect.currentSpan   // Effect<Tracer.Span, NoSuchElementException>
```

### External / propagated spans

```ts
const external = Tracer.externalSpan({
  traceId: incomingTraceId,
  spanId: incomingSpanId,
  sampled: true
})

yield* myEffect.pipe(
  Effect.withSpan("handler", { parent: external })
)
```

---

## `@effect/opentelemetry`

### `NodeSdk.layer` — recommended entrypoint

```ts
import { NodeSdk } from "@effect/opentelemetry"
import { BatchSpanProcessor } from "@opentelemetry/sdk-trace-base"
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-http"
import { PrometheusExporter } from "@opentelemetry/exporter-prometheus"
import { SimpleLogRecordProcessor } from "@opentelemetry/sdk-logs"
import { OTLPLogExporter } from "@opentelemetry/exporter-logs-otlp-http"
import { Layer } from "effect"

const OtelLive = NodeSdk.layer(() => ({
  resource: { serviceName: "my-service", serviceVersion: "1.0.0" },

  // Traces
  spanProcessor: new BatchSpanProcessor(
    new OTLPTraceExporter({ url: "http://localhost:4318/v1/traces" })
  ),

  // Metrics
  metricReader: new PrometheusExporter({ port: 9464 }),

  // Logs (Effect logs → OTel log records)
  logRecordProcessor: new SimpleLogRecordProcessor(
    new OTLPLogExporter({ url: "http://localhost:4318/v1/logs" })
  ),

  shutdownTimeout: "5 seconds"
}))

// Provide OtelLive to your main layer
Layer.launch(AppLive.pipe(Layer.provide(OtelLive)))
```

`NodeSdk.layer` accepts a lazy config object **or** an `Effect<Configuration>`. It creates exactly what you configure: pass no `spanProcessor` to skip tracing, no `metricReader` to skip metrics, no `logRecordProcessor` to skip log bridging.

### Lightweight OTLP-HTTP alternative (`Otlp.layer`)

For environments where you control the transport (e.g. Fetch-based):

```ts
import { Otlp } from "@effect/opentelemetry"
import { FetchHttpClient } from "@effect/platform"
import { Layer } from "effect"

const OtlpLive = Otlp.layer({
  baseUrl: "http://localhost:4318",
  resource: { serviceName: "my-service" },
  metricsExportInterval: "10 seconds",
  tracerExportInterval: "5 seconds"
}).pipe(Layer.provide(FetchHttpClient.layer))
```

### How Effect signals flow to OTel

| Effect signal | OTel entity |
|---|---|
| `Effect.withSpan` | `Span` (hierarchy preserved) |
| `Effect.annotateCurrentSpan` | `Span.attribute` |
| `Metric.*` counters/gauges/histograms | OTel `Instrument` (via MetricReader) |
| `Effect.log*` | `LogRecord` (via LogRecordProcessor) |
| Fiber annotations set by `annotateLogs` | `LogRecord` attributes |

The `Logger.tracerLogger` (attached by default when tracing is active) bridges Effect log calls into the active span's events and the OTel log pipeline simultaneously.

---

## Common pitfalls

❌ Don't call `Logger.withMinimumLogLevel` at the top of a large program and assume it propagates — it only affects the sub-effect it wraps.

✅ Use `Logger.minimumLogLevel(level)` as a `Layer` for process-wide control.

❌ Don't manually increment a counter in a `tap` — use `Metric.trackSuccess` / `Metric.trackDuration` to keep metrics and effect semantics together.

✅ Metrics are global by default (share the `globalMetricRegistry`). Unique names are required per metric type.

---

## See also

- `packages/effect/src/Logger.ts` — full logger API
- `packages/effect/src/Metric.ts` — full metric constructors and aspects
- `packages/effect/src/Tracer.ts` — `SpanOptions`, `SpanKind`, `Span`, `ExternalSpan`
- `packages/opentelemetry/src/NodeSdk.ts` — `layer`, `layerTracerProvider`
- `packages/opentelemetry/src/Otlp.ts` — `layer`, `layerJson`, `layerProtobuf`
- Effect website: https://effect.website/docs/observability/logging
