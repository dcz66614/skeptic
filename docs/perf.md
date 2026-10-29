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

Both transports are measured the same way: **one long-lived proxy and one
long-lived upstream pair**, plus **one long-lived direct upstream** for the
baseline, serve every sample of a transport. Each sample is one `tools/call`
through the proxy minus the `tools/call` sent direct right after it with the same
arguments, so a sample is `proxied - direct` and the paired calls cancel the
run-to-run drift of the machine. The default is **5,000 samples per transport**;
p50/p90/p99/mean/max are computed over all of them.

- **stdio**: one SDK `ClientSession` drives the echo server direct and another
  drives `skeptic proxy stdio -- python echo_server.py`; both warm up once and
  then stay open for every sample.
- **HTTP**: the echo fixture and the proxy run as uvicorn servers in the
  benchmark process (the proxy is the same `HttpProxy` the CLI serves, and the
  fixture is the same `MCPServer` app). One `httpx.AsyncClient` opens a direct
  session and a proxied session (`initialize` first, so both session ids are
  real), and the same client code and request body are used on both sides, so
  the difference is the proxy hop.

Concurrency is reported separately. On stdio, 50 SDK sessions each make 100
`echo` calls through the proxy; on HTTP, 50 `httpx` clients each make 100 calls.
Every reply must carry its own id and its own text, so a lost message or a
crossed id counts as an error. That part serves the fixture and the proxy in the
benchmark process too.

The acceptance of the P17 card is **p50 < 5 ms and p99 < 30 ms** for each
transport, plus **0 errors** for the concurrency run.

## How to run it

```text
uv run python tests/perf/bench_proxy.py                       # full run, a few minutes
uv run python tests/perf/bench_proxy.py --only stdio http    # latency only
uv run python tests/perf/bench_proxy.py --count 500          # fewer samples
uv run python tests/perf/bench_proxy.py --report .tmp/perf.json
```

The script prints one line per transport and exits non-zero if an acceptance
fails. `--help` lists every knob (samples, warm-up, clients, calls, report path).

A short smoke run of the same code lives in `tests/perf/test_bench_proxy.py` and
is marked `perf`. That marker is deselected by default (`addopts` in
`pyproject.toml`); run it with `uv run pytest tests/perf -m perf`. The smoke
tests use two or five samples, so they stay fast. The full benchmark with the
default 5,000 samples never runs inside `pytest` because it takes minutes.

## Results on this machine (2026-10-29)

Machine: Windows 11 Home 10.0.26200, 13th Gen Intel Core i7-13650HX (14 cores,
20 threads), 32 GB RAM. Python 3.12.13, uv 0.12.2, MCP SDK 2.3.0, Starlette
1.10.0, httpx 0.28.1.

Command: `uv run python tests/perf/bench_proxy.py --report .tmp/opencode/perf.json`
(5,000 latency samples per transport, 3 warm-up calls per session):

| Transport | Added latency p50 | p90 | p99 | mean | max | Acceptance |
| --- | --- | --- | --- | --- | --- | --- |
| stdio | 0.185 ms | 0.302 ms | 0.563 ms | 0.191 ms | 0.926 ms | PASS |
| HTTP | 2.042 ms | 2.616 ms | 4.111 ms | 2.151 ms | 21.581 ms | PASS |

Concurrency (50 clients x 100 calls = 5,000 calls per transport):

| Transport | Calls | Errors | Mismatches |
| --- | --- | --- | --- |
| stdio | 5,000 | 0 | 0 |
| HTTP | 5,000 | 0 | 0 |

The run printed by the command above took about 1.6 minutes on this machine.

Three more runs on the same day, two of them latency-only (`--only stdio http`),
gave stdio p50 0.276 / 0.194 / 0.185 ms and HTTP p50 2.231 / 2.072 / 2.042 ms,
and p99 stayed between 0.59 and 0.94 ms on stdio and between 4.1 and 5.4 ms on
HTTP, so the percentiles are stable between runs on this machine. Individual
samples can be negative when the direct call happens to be slower than the
proxied one; the percentiles are what the acceptance uses.

The card's acceptance was written for `ubuntu-latest`. This machine is Windows
11, so these numbers are not a direct substitute for the CI run; the margin to
the limits is large on both transports, and the Windows relay is the slower of
the two platforms for stdio pipes.

## Reading the numbers

- HTTP carries about 2 ms more than stdio per message with these samples. On HTTP
  the proxy parses the body, forwards it with `httpx` over a new loopback
  connection per request, and re-frames the reply; on stdio it forwards a line
  over a pipe to a child process it started itself. Both are inside the limits.
- The samples are differences between a proxied call and the direct call right
  after it, both on processes that have been serving since the transport began.
  They no longer include process startup, so they are smaller and steadier than
  the first P17 run, which started a fresh process pair per sample.
- Absolute values will drift with machine load; the acceptance check is what
  should be trusted.
- No fault or Guard runs here. When a profile injects faults, the added cost is
  the fault's own work (a rewrite, a hold, an error reply), which is measured by
  that fault's tests, not by this benchmark.
