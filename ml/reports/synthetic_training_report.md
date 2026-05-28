# Real-Only vs Real+Synthetic Training Experiment

Date: 2026-05-24

This diagnostic experiment evaluates whether adding the generated synthetic scenario extension to the training set improves performance on the same real holdout.

Important limitation: synthetic rows are scenario data generated from the project profiles. They are not direct real observations and should not be presented as new empirical collection.

| Experiment | Train rows | Synthetic train rows | Test rows | MAE | RMSE | WAPE |
|---|---:|---:|---:|---:|---:|---:|
| real_only_train_real_holdout | 13269 | 0 | 3328 | 6.5896 | 9.7668 | 0.1501 |
| real_plus_synthetic_train_real_holdout | 53061 | 39792 | 3328 | 7.7724 | 12.178 | 0.1771 |

Interpretation should be based on the actual metric difference. If the synthetic supplement does not improve the real holdout, it is still useful for scenario demos and stress testing, not as a replacement for real collection.