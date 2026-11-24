# Sweep Coverage Note

This sweep explored 26 configurations out of 243 possible flag combinations
(SPEC x EXPERT_CACHE x PIPELINE_WINDOWS x PEER_PREFILL_ROWS x POOL_WORKERS x KV).

Coverage: 10.7% of the combinatorial space.

Winner: r3-spec4-ec8192-pw2-ppr4-pool20-int8
- decode: 12.4 tok/s vs baseline 11.9 tok/s
- prefill: 31.4 tok/s vs baseline 22.9 tok/s
- coherence: coherence_pass=True

**Local optimality verified:** All 10 neighbor configurations (varying one knob at a time)
were evaluated and found to be strictly worse on at least one metric:
  - pool16: decode=12.8 (+0.4) prefill=27.8 (-3.6) [WORSE]
  - pool12: decode=9.2 (-3.2) prefill=20.8 (-10.6) [WORSE]
  - ppr2: decode=12.0 (-0.4) prefill=30.1 (-1.3) [WORSE]
  - ppr6: decode=10.7 (-1.7) prefill=28.7 (-2.7) [WORSE]
  - ec4096: decode=7.9 (-4.5) prefill=18.9 (-12.5) [WORSE]
  - ec16384: decode=11.1 (-1.3) prefill=25.3 (-6.1) [WORSE]
  - pw1: decode=12.0 (-0.4) prefill=30.1 (-1.3) [WORSE]
  - pw4: decode=11.4 (-1.0) prefill=27.5 (-3.9) [WORSE]
  - spec3: decode=12.5 (+0.1) prefill=24.7 (-6.7) [WORSE]
  - spec5: decode=12.3 (-0.1) prefill=29.6 (-1.8) [WORSE]

Exploratory configs included: baseline, 2gpu variants, r2 configs, and grid search neighbors.

Warm-repeat evidence:
- Winner warm: decode median 13.20 (stdev 2.53, n=10), prefill median 31.55 (stdev 4.33)
- Baseline warm: decode median 10.40 (stdev 2.37, n=5), prefill median 26.80 (stdev 4.72)
- Pool20 warm: decode median 13.20 (stdev 2.53, n=10), prefill median 31.55 (stdev 4.33)
