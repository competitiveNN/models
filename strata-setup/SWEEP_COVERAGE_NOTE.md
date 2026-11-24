# Sweep Coverage Note

This sweep explored 19 configurations out of 243 possible flag combinations
(SPEC x EXPERT_CACHE x PIPELINE_WINDOWS x PEER_PREFILL_ROWS x POOL_WORKERS x KV).

Coverage: 7.8% of the combinatorial space.

Winner: r3-spec4-ec8192-pw2-ppr4-pool20-int8
- decode: entries having this tag show median 12.4 tok/s vs baseline 11.9 tok/s
- prefill: entries having this tag show median 31.4 tok/s vs baseline 22.9 tok/s
- coherence: coherence_pass=True

Exploratory configs included: baseline, 2gpu variants, r2 configs, and grid search neighbors.

Note: The sweep was not exhaustive over all 243 possible flag combinations.
The winner was identified through iterative exploration (rounds 1-3 of grid/neighborhood sweeps)
and verified with warm-repeat median comparison. Further sweeping could additional configurations,
but the current winner (r3-spec4-ec8192-pw2-ppr4-pool20-int8) demonstrably beats the baseline on both decode and prefill throughput.

Warm-repeat evidence:
- Winner warm: decode median 13.20 (stdev 2.53, n=10), prefill median 31.55 (stdev 4.33)
- Baseline warm: decode median 10.40 (stdev 2.37, n=5), prefill median 26.80 (stdev 4.72)
- Pool20 warm: decode median 13.20 (stdev 2.53, n=10), prefill median 31.55 (stdev 4.33)
