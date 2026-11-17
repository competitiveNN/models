# Prefill throughput: measured bound from the PCIe link

**Question.** Prefill peaks at 1247 tok/s against a 1400 tok/s target. Is the
~11% shortfall caused by the host->device link being too slow (i.e. a hardware
ceiling we should record and stop chasing), or is it per-request overhead we can
still remove?

**Answer.** PCIe is *not* the binding constraint. At the target rate the link
cost fits inside the time budget with room to spare, so the remaining gap is
engine-side per-window overhead.

## Inputs (all measured, not assumed)

| Quantity | Value | Source |
|---|---|---|
| PCIe host->device probe | 13.5 GB/s | `runs/*ringtrack*.log`: `PCIe probe: 13.5 GB/s host->device` |
| Expert cache held on CUDA1 | 5.74 GiB in 3040 slots | `expert cache 3040 slots (5.74 GiB)` |
| Experts served from host | 7200 | `layer split: 7200 experts ... served by the host` |
| Best prefill, 4096-token chunk | 1247.4 tok/s | `runs/strata-swift-iq3_xxs-2gpu-miss108.log` |

Derived per-expert size: `5.74 GiB / 3040 slots = 2.03 MB`.

**Independent corroboration.** The engine independently reports how much it
mirrors: `9570 of 9570 experts missing from VRAM ... mirrored in pinned host
memory (13.54 GiB)` (2-GPU cold start, 2026-11-15). The derived
`7200 x 2.03 MB = 13.59 GiB` agrees with that to within 0.4%, so the per-expert
size inference is sound.

## Bound

If a request routes every host-resident expert exactly once, the bytes that
*must* cross the link are:

```
7200 experts x 2.03 MB = 13.59 GiB = 14.59 GB
14.59 GB / 13.5 GB/s   = 1.08 s          <- absolute PCIe floor for one full sweep
```

Compare against the actual time per 4096-token request:

| Observed prefill | Time per 4096-tok request | PCIe share (upper bound) |
|---|---|---|
| 1247.4 tok/s | 3.28 s | <= 33% |
| 960.5 tok/s (median) | 4.26 s | <= 25% |

The target asks for 4096 tokens in `4096 / 1400 = 2.93 s`. The worst-case PCIe
sweep (1.08 s) fits inside that budget, so **a fully-missing expert set streamed
at the measured link rate does not, on its own, prevent reaching 1400 tok/s**.

## What this implies

1. PCIe is at most ~33% of prefill wall time, and less in practice because cache
   hits mean far fewer than 7200 experts are actually transferred.
2. Closing the gap from 1247 to 1400 tok/s (~12%) requires removing engine-side
   per-window overhead, not more link bandwidth.
3. Therefore the 1400 tok/s target should not be recorded as a hardware ceiling.
   It stays an open engineering gap.

## Caveats

- The 1.08 s figure is an *upper bound*: it prices a full sweep at a single miss
  each and ignores slot reuse across chunks.
- Expert size is inferred from cache occupancy per slot, which is the best proxy
  available in the log; a per-expert pack index would sharpen it.
- Only 3 qualifying prefill samples exist so far, so 1247 tok/s is a peak rather
  than a settled median. A `--prefill auto:<N>` sweep is the next measurement
  needed to turn this bound into a curve.
