# Proxy performance (P17)

This page records the measured cost of putting Skeptic between an MCP client and
an upstream server: how much latency one `tools/call` gains, and whether
concurrent clients keep every reply intact.

## What is measured

`tests/perf/bench_proxy.py` benchmarks the proxy with its default pipeline, which
means **no faults and no Guards**: that isolates the cost of parsing, the
pipeline stages, episode bookkeeping and the transport relay from any fault
behaviour. The upstream is `tests/fixtures/echo_server.py` (an SDK server with
one `echo` tool), so the work inside the server is the same on both sides.

Both transports are measured the same way: one fresh pair of processes per
sample, a warm-up call on each, then one timed call through the proxy and one
timed call direct. The **added latency** of a sample is `proxied - direct`, and
p50/p99 are computed over all samples.

- **stdio**: an MCP SDK client (`ClientSession`) drives the echo server direct,
  then drives `skeptic proxy stdio -- python echo_server.py`.
- **HTTP**: an `httpx` client posts a raw `tools/call` to the echo server's
  streamable-HTTP endpoint (`initialize` first, so the session id is real), then
  to `skeptic proxy http` in front of that endpoint. The same client code and the
  same request body are used on both sides, so the difference is the proxy hop.

Concurrency is reported separately. On stdio, 50 SDK sessions each make 100
`echo` calls; on HTTP, 50 `httpx` clients each make 100 calls through the proxy.
Every reply must carry its own id and its own text, so a lost message or a
crossed id counts as an error.

The acceptance of the P17 card is **p50 < 5 ms and p99 < 30 ms** for each
transport, plus **0 errors** for the concurrency run.

## How to run it

```text
uv run python tests/perf/bench_proxy.py                       # full run, ~10 min
uv run python tests/perf/bench_proxy.py --only stdio http    # latency only
uv run python tests/perf/bench_proxy.py --count 500          # more samples
uv run python tests/perf/bench_proxy.py --report .tmp/perf.json
```

The script prints one line per transport and exits non-zero if an acceptance
fails. `--help` lists every knob (samples, warm-up, clients, calls, report path).

A short smoke run of the same code lives in `tests/perf/test_bench_proxy.py` and
is marked `perf`. That marker is deselected by default (`addopts` in
`pyproject.toml`); run it with `uv run pytest tests/perf -m perf`. The full
benchmark never runs inside `pytest` because it starts hundreds of processes and
takes minutes.

## Results on this machine (2026-10-29)

Machine: Windows 11 Home 10.0.26200, 13th Gen Intel Core i7-13650HX (14 cores,
20 threads), 32 GB RAM. Python 3.12.13, uv 0.12.2, MCP SDK 2.3.0, Starlette
1.10.0, httpx 0.28.1.

Command: `uv run python tests/perf/bench_proxy.py --report .tmp/opencode/perf.json`
(100 latency samples per transport, 3 warm-up calls per session).

| Transport | Added latency p50 | p90 | p99 | mean | max | Acceptance |
| --- | --- | --- | --- | --- | --- | --- |
| stdio | 0.228 ms | 0.392 ms | 0.768 ms | 0.238 ms | 1.009 ms | PASS |
| HTTP | 0.804 ms | 1.117 ms | 1.639 ms | 0.811 ms | 3.380 ms | PASS |

Concurrency (50 clients x 100 calls = 5,000 calls per transport):

| Transport | Calls | Errors | Mismatches |
| --- | --- | --- | --- |
| stdio | 5,000 | 0 | 0 |
| HTTP | 5,000 | 0 | 0 |

A second latency-only run (`--only stdio http`, 100 samples) gave stdio
p50 0.205 ms / p99 0.624 ms and HTTP p50 0.764 ms / p99 1.285 ms, so the
percentiles are stable between runs on this machine. Individual samples can be
negative when the direct call happens to be slower than the proxied one; the
percentiles are what the acceptance uses.

The card's acceptance was written for `ubuntu-latest`. This machine is Windows
11, so these numbers are not a direct substitute for the CI run; the margin to
the limits is large on both transports, and the Windows relay is the slower of
the two platforms for stdio pipes.

## Reading the numbers

- HTTP carries about 0.8 ms more than stdio per message. On HTTP the proxy parses
  the body, forwards it with `httpx`, and re-frames the reply; on stdio it
  forwards a line over a pipe to a child process it started itself. Both are well
  inside the limits.
- The samples are differences between two calls on two freshly started
  processes, so they include the run-to-run jitter of the upstream startup and
  scheduler. Absolute values will drift with machine load; the acceptance check
  is what should be trusted.
- No fault or Guard runs here. When a profile injects faults, the added cost is
  the fault's own work (a rewrite, a hold, an error reply), which is measured by
  that fault's tests, not by this benchmark.
