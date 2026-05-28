# Supervised Progression Model

- Model version: `progression_v3_supervised_next_set`
- Selected model: `hybrid_ridge_weight_policy_reps`
- Weight model: `ridge`
- Reps source: `policy_guardrail`
- Artifact: `ml\models\artifacts\progression_next_set_model.joblib`
- Dataset: `638` workout sets, `585` supervised cases
- Split: `chronological_75_25`, train `438`, test `147`

| Model | Weight MAE kg | Weight RMSE kg | Reps MAE | Reps RMSE | Rep range hit-rate |
|---|---:|---:|---:|---:|---:|
| hybrid_ridge_weight_policy_reps | 5.997 | 13.752 | 0.891 | 1.505 | 0.735 |
| extra_trees | 6.175 | 12.738 | 1.034 | 1.289 | 0.694 |
| random_forest | 6.272 | 14.196 | 1.065 | 1.304 | 0.721 |
| policy_baseline | 6.999 | 14.247 | 0.891 | 1.505 | 0.735 |
| ridge | 5.997 | 13.752 | 3.66 | 6.104 | 0.571 |

Supervised next-set regression trained on deterministic demo workout history. Use as a thesis/product artifact, not a clinical prescription.
