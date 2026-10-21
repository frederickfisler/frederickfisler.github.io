# Measured results

Summary of 5 independent benchmark run(s). Timing cells show the median of per-run medians with a 95% percentile-bootstrap confidence interval (10,000 resamples of independent run medians; deterministic seed 20261021). With only five runs, intervals are descriptive and should be interpreted cautiously. See the raw JSON files for observations and environment metadata.

| Algorithm | Key generation (ms), median [95% CI] | Signing (ms), median [95% CI] | Verification (ms), median [95% CI] | Signature (B) | Public key DER (B) |
|---|---:|---:|---:|---:|---:|
| RSA-2048 | 49.9948 [38.7787, 74.1592] | 0.7441 [0.7418, 0.7461] | 0.0341 [0.0336, 0.0368] | 256 | 294 |
| RSA-3072 | 177.4884 [96.7010, 190.8982] | 2.3044 [2.2810, 2.4849] | 0.0608 [0.0605, 0.0633] | 384 | 422 |
| RSA-4096 | 572.0132 [415.1276, 858.3375] | 5.5283 [5.2318, 5.7266] | 0.0970 [0.0969, 0.1026] | 512 | 550 |
| ECDSA P-256 | 0.0216 [0.0207, 0.0230] | 0.0350 [0.0343, 0.0355] | 0.0939 [0.0900, 0.0941] | 71 | 91 |
| ECDSA P-384 | 0.9175 [0.8809, 0.9707] | 0.9175 [0.9107, 1.0066] | 0.7903 [0.7707, 0.8250] | 102 | 120 |
| ECDSA P-521 | 2.0937 [1.9962, 2.1391] | 2.2144 [2.1503, 2.3871] | 1.6982 [1.6640, 1.8121] | 139 | 158 |
| Ed25519 | 0.0427 [0.0423, 0.0428] | 0.0471 [0.0461, 0.0482] | 0.1226 [0.1216, 0.1234] | 64 | 44 |

Runs: 5 · Trials per operation per run: 10 · Warm-ups: 5 · Payload: 1024 bytes · Python: 3.14.5 · cryptography: 50.0.2

Configuration order was shuffled between runs. Recorded seeds and orders are in each JSON file.
