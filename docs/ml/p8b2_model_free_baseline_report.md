# ML-P8B.2 Model-Free Baseline Evaluation Report

**Date:** 2026-06-21  
**Branch:** `research/zdte-fusion-model`  
**Commit:** `c21ccbd3c8b372806f93f6e44e74e7381d6cdac0`  
**Stage:** ML-P8B.2  
**Gate:** **PASS**

## Executive Summary

| Item | Result |
|------|--------|
| Input joined rows | 1391 |
| Baseline-eligible rows | 1390 |
| Feature columns | 198 |
| Split protocol | session_grouped chronological 11/3/5 |
| Split validation | PASS |
| Forbidden input validation | PASS |
| Model fitting | **None** |
| sklearn `.fit()` | **Not called** |
| P8B.3 | **BLOCKED** |

**Test-set P0 (train_median_em):** MAE 2.17 EM, within_0.50_EM 19.5%  
**Test-set P1 @ 0.50 (train_prior):** balanced_accuracy 0.50, Brier 0.166, ROC-AUC 0.24  
**Train prior P(near):** 25.7% (train only)

Full metrics below. Artifacts under `artifacts/reports/p8b2_model_free_baselines/` (not committed).

---

- Phase: **ML-P8B.2**
- `model_fitting_allowed`: **false**
- `model_type`: **model_free_baseline**

## Input Summary

- Dataset: `artifacts\datasets\pit_sample_baseline_v1_1_validation`
- Features: `artifacts\features\pit_features_baseline_v1_1_validation`
- Joined rows: 1391
- Baseline-eligible rows: 1390
- Feature columns: 198
- Sessions: 19

## Split Sessions

- Mode: `chronological`
- Train (11): 2024-01-05, 2024-01-19, 2024-02-13, 2024-03-08, 2024-04-05, 2024-05-03, 2024-06-07, 2024-07-03, 2024-08-02, 2024-09-06, 2024-10-04
- Validation (3): 2024-11-01, 2024-11-29, 2024-12-06
- Test (5): 2025-01-03, 2025-02-07, 2025-03-07, 2025-04-04, 2025-05-02

## Split Validation

- PASS: **True**
- Row-level random split PASS: **True**
- Train rows: 811 | Val: 195 | Test: 385

## Forbidden Input Validation

- PASS: **True**
- Feature columns checked: 198
- Forbidden columns found: none

## P0 Regression (`close_distance_to_primary_pin_em`)

- **train**:
  - **zero_em**:
    - valid_count: 810
    - mae: 2.164204
    - rmse: 3.977445
    - median_absolute_error: 1.306535
    - sign_accuracy: 0.000000
    - within_0.25_EM_accuracy: 0.140741
    - within_0.50_EM_accuracy: 0.256790
    - outlier_rate: 0.177778

  - **train_median_em**:
    - valid_count: 810
    - mae: 2.044814
    - rmse: 3.864565
    - median_absolute_error: 1.100375
    - sign_accuracy: 0.670370
    - within_0.25_EM_accuracy: 0.141975
    - within_0.50_EM_accuracy: 0.279012
    - outlier_rate: 0.156790

  - **train_mean_em**:
    - valid_count: 810
    - mae: 2.081152
    - rmse: 3.848405
    - median_absolute_error: 1.073004
    - sign_accuracy: 0.670370
    - within_0.25_EM_accuracy: 0.120988
    - within_0.50_EM_accuracy: 0.229630
    - outlier_rate: 0.167901


- **validation**:
  - **zero_em**:
    - valid_count: 195
    - mae: 3.040698
    - rmse: 4.924361
    - median_absolute_error: 1.348696
    - sign_accuracy: 0.000000
    - within_0.25_EM_accuracy: 0.005128
    - within_0.50_EM_accuracy: 0.164103
    - outlier_rate: 0.287179

  - **train_median_em**:
    - valid_count: 195
    - mae: 3.192792
    - rmse: 4.765730
    - median_absolute_error: 1.931887
    - sign_accuracy: 0.384615
    - within_0.25_EM_accuracy: 0.015385
    - within_0.50_EM_accuracy: 0.046154
    - outlier_rate: 0.287179

  - **train_mean_em**:
    - valid_count: 195
    - mae: 3.285291
    - rmse: 4.715340
    - median_absolute_error: 2.188187
    - sign_accuracy: 0.384615
    - within_0.25_EM_accuracy: 0.035897
    - within_0.50_EM_accuracy: 0.082051
    - outlier_rate: 0.297436


- **test**:
  - **zero_em**:
    - valid_count: 385
    - mae: 2.007085
    - rmse: 3.459345
    - median_absolute_error: 1.236406
    - sign_accuracy: 0.000000
    - within_0.25_EM_accuracy: 0.096104
    - within_0.50_EM_accuracy: 0.205195
    - outlier_rate: 0.158442

  - **train_median_em**:
    - valid_count: 385
    - mae: 2.172722
    - rmse: 3.598733
    - median_absolute_error: 1.417971
    - sign_accuracy: 0.389610
    - within_0.25_EM_accuracy: 0.098701
    - within_0.50_EM_accuracy: 0.194805
    - outlier_rate: 0.200000

  - **train_mean_em**:
    - valid_count: 385
    - mae: 2.324415
    - rmse: 3.720015
    - median_absolute_error: 1.586282
    - sign_accuracy: 0.389610
    - within_0.25_EM_accuracy: 0.114286
    - within_0.50_EM_accuracy: 0.192208
    - outlier_rate: 0.215584


- **train_priors**:
  - **train_median_em**:
    - median_em: 0.651859

  - **train_mean_em**:
    - mean_em: 1.004913



## P1 Binary Preferred (`close_near_primary_pin_050`)

- label_key: labels.close_near_primary_pin_050
- **train_priors**:
  - **majority_class**:
    - majority: False

  - **constant_not_near**:
    - constant: False

  - **train_prior_probability**:
    - near: 0.256790
    - not_near: 0.743210


- **train**:
  - **majority_class**:
    - valid_count: 810
    - **class_distribution**:
      - near: 208
      - not_near: 602
      - near_ratio: 0.256790

    - majority_baseline_accuracy: 1.000000
    - balanced_accuracy: 0.500000
    - precision: None
    - recall: 0.000000
    - f1: None
    - brier_score: None
    - roc_auc: None
    - roc_auc_skipped_reason: scores_not_provided
    - pr_auc: None
    - pr_auc_skipped_reason: scores_not_provided
    - **confusion_matrix**:
      - tn: 602
      - fp: 0
      - fn: 208
      - tp: 0

    - positive_label: True

  - **constant_not_near**:
    - valid_count: 810
    - **class_distribution**:
      - near: 208
      - not_near: 602
      - near_ratio: 0.256790

    - majority_baseline_accuracy: 1.000000
    - balanced_accuracy: 0.500000
    - precision: None
    - recall: 0.000000
    - f1: None
    - brier_score: None
    - roc_auc: None
    - roc_auc_skipped_reason: scores_not_provided
    - pr_auc: None
    - pr_auc_skipped_reason: scores_not_provided
    - **confusion_matrix**:
      - tn: 602
      - fp: 0
      - fn: 208
      - tp: 0

    - positive_label: True

  - **train_prior_probability**:
    - valid_count: 810
    - **class_distribution**:
      - near: 208
      - not_near: 602
      - near_ratio: 0.256790

    - majority_baseline_accuracy: 1.000000
    - balanced_accuracy: 0.500000
    - precision: None
    - recall: 0.000000
    - f1: None
    - brier_score: 0.190849
    - roc_auc: 0.304514
    - roc_auc_skipped_reason: None
    - pr_auc: 0.187159
    - pr_auc_skipped_reason: None
    - **confusion_matrix**:
      - tn: 602
      - fp: 0
      - fn: 208
      - tp: 0

    - positive_label: True


- **validation**:
  - **majority_class**:
    - valid_count: 195
    - **class_distribution**:
      - near: 32
      - not_near: 163
      - near_ratio: 0.164103

    - majority_baseline_accuracy: 1.000000
    - balanced_accuracy: 0.500000
    - precision: None
    - recall: 0.000000
    - f1: None
    - brier_score: None
    - roc_auc: None
    - roc_auc_skipped_reason: scores_not_provided
    - pr_auc: None
    - pr_auc_skipped_reason: scores_not_provided
    - **confusion_matrix**:
      - tn: 163
      - fp: 0
      - fn: 32
      - tp: 0

    - positive_label: True

  - **constant_not_near**:
    - valid_count: 195
    - **class_distribution**:
      - near: 32
      - not_near: 163
      - near_ratio: 0.164103

    - majority_baseline_accuracy: 1.000000
    - balanced_accuracy: 0.500000
    - precision: None
    - recall: 0.000000
    - f1: None
    - brier_score: None
    - roc_auc: None
    - roc_auc_skipped_reason: scores_not_provided
    - pr_auc: None
    - pr_auc_skipped_reason: scores_not_provided
    - **confusion_matrix**:
      - tn: 163
      - fp: 0
      - fn: 32
      - tp: 0

    - positive_label: True

  - **train_prior_probability**:
    - valid_count: 195
    - **class_distribution**:
      - near: 32
      - not_near: 163
      - near_ratio: 0.164103

    - majority_baseline_accuracy: 1.000000
    - balanced_accuracy: 0.500000
    - precision: None
    - recall: 0.000000
    - f1: None
    - brier_score: 0.145764
    - roc_auc: 0.282975
    - roc_auc_skipped_reason: None
    - pr_auc: 0.114547
    - pr_auc_skipped_reason: None
    - **confusion_matrix**:
      - tn: 163
      - fp: 0
      - fn: 32
      - tp: 0

    - positive_label: True


- **test**:
  - **majority_class**:
    - valid_count: 385
    - **class_distribution**:
      - near: 79
      - not_near: 306
      - near_ratio: 0.205195

    - majority_baseline_accuracy: 1.000000
    - balanced_accuracy: 0.500000
    - precision: None
    - recall: 0.000000
    - f1: None
    - brier_score: None
    - roc_auc: None
    - roc_auc_skipped_reason: scores_not_provided
    - pr_auc: None
    - pr_auc_skipped_reason: scores_not_provided
    - **confusion_matrix**:
      - tn: 306
      - fp: 0
      - fn: 79
      - tp: 0

    - positive_label: True

  - **constant_not_near**:
    - valid_count: 385
    - **class_distribution**:
      - near: 79
      - not_near: 306
      - near_ratio: 0.205195

    - majority_baseline_accuracy: 1.000000
    - balanced_accuracy: 0.500000
    - precision: None
    - recall: 0.000000
    - f1: None
    - brier_score: None
    - roc_auc: None
    - roc_auc_skipped_reason: scores_not_provided
    - pr_auc: None
    - pr_auc_skipped_reason: scores_not_provided
    - **confusion_matrix**:
      - tn: 306
      - fp: 0
      - fn: 79
      - tp: 0

    - positive_label: True

  - **train_prior_probability**:
    - valid_count: 385
    - **class_distribution**:
      - near: 79
      - not_near: 306
      - near_ratio: 0.205195

    - majority_baseline_accuracy: 1.000000
    - balanced_accuracy: 0.500000
    - precision: None
    - recall: 0.000000
    - f1: None
    - brier_score: 0.165752
    - roc_auc: 0.241334
    - roc_auc_skipped_reason: None
    - pr_auc: 0.137303
    - pr_auc_skipped_reason: None
    - **confusion_matrix**:
      - tn: 306
      - fp: 0
      - fn: 79
      - tp: 0

    - positive_label: True



## P1 Sensitivity (`close_near_primary_pin_025`)

- label_key: labels.close_near_primary_pin_025
- **train_priors**:
  - **majority_class**:
    - majority: False

  - **constant_not_near**:
    - constant: False

  - **train_prior_probability**:
    - near: 0.140741
    - not_near: 0.859259


- **train**:
  - **majority_class**:
    - valid_count: 810
    - **class_distribution**:
      - near: 114
      - not_near: 696
      - near_ratio: 0.140741

    - majority_baseline_accuracy: 1.000000
    - balanced_accuracy: 0.500000
    - precision: None
    - recall: 0.000000
    - f1: None
    - brier_score: None
    - roc_auc: None
    - roc_auc_skipped_reason: scores_not_provided
    - pr_auc: None
    - pr_auc_skipped_reason: scores_not_provided
    - **confusion_matrix**:
      - tn: 696
      - fp: 0
      - fn: 114
      - tp: 0

    - positive_label: True

  - **constant_not_near**:
    - valid_count: 810
    - **class_distribution**:
      - near: 114
      - not_near: 696
      - near_ratio: 0.140741

    - majority_baseline_accuracy: 1.000000
    - balanced_accuracy: 0.500000
    - precision: None
    - recall: 0.000000
    - f1: None
    - brier_score: None
    - roc_auc: None
    - roc_auc_skipped_reason: scores_not_provided
    - pr_auc: None
    - pr_auc_skipped_reason: scores_not_provided
    - **confusion_matrix**:
      - tn: 696
      - fp: 0
      - fn: 114
      - tp: 0

    - positive_label: True

  - **train_prior_probability**:
    - valid_count: 810
    - **class_distribution**:
      - near: 114
      - not_near: 696
      - near_ratio: 0.140741

    - majority_baseline_accuracy: 1.000000
    - balanced_accuracy: 0.500000
    - precision: None
    - recall: 0.000000
    - f1: None
    - brier_score: 0.120933
    - roc_auc: 0.473067
    - roc_auc_skipped_reason: None
    - pr_auc: 0.145219
    - pr_auc_skipped_reason: None
    - **confusion_matrix**:
      - tn: 696
      - fp: 0
      - fn: 114
      - tp: 0

    - positive_label: True


- **validation**:
  - **majority_class**:
    - valid_count: 195
    - **class_distribution**:
      - near: 1
      - not_near: 194
      - near_ratio: 0.005128

    - majority_baseline_accuracy: 1.000000
    - balanced_accuracy: 0.500000
    - precision: None
    - recall: 0.000000
    - f1: None
    - brier_score: None
    - roc_auc: None
    - roc_auc_skipped_reason: scores_not_provided
    - pr_auc: None
    - pr_auc_skipped_reason: scores_not_provided
    - **confusion_matrix**:
      - tn: 194
      - fp: 0
      - fn: 1
      - tp: 0

    - positive_label: True

  - **constant_not_near**:
    - valid_count: 195
    - **class_distribution**:
      - near: 1
      - not_near: 194
      - near_ratio: 0.005128

    - majority_baseline_accuracy: 1.000000
    - balanced_accuracy: 0.500000
    - precision: None
    - recall: 0.000000
    - f1: None
    - brier_score: None
    - roc_auc: None
    - roc_auc_skipped_reason: scores_not_provided
    - pr_auc: None
    - pr_auc_skipped_reason: scores_not_provided
    - **confusion_matrix**:
      - tn: 194
      - fp: 0
      - fn: 1
      - tp: 0

    - positive_label: True

  - **train_prior_probability**:
    - valid_count: 195
    - **class_distribution**:
      - near: 1
      - not_near: 194
      - near_ratio: 0.005128

    - majority_baseline_accuracy: 1.000000
    - balanced_accuracy: 0.500000
    - precision: None
    - recall: 0.000000
    - f1: None
    - brier_score: 0.023493
    - roc_auc: 0.386598
    - roc_auc_skipped_reason: None
    - pr_auc: 0.004167
    - pr_auc_skipped_reason: None
    - **confusion_matrix**:
      - tn: 194
      - fp: 0
      - fn: 1
      - tp: 0

    - positive_label: True


- **test**:
  - **majority_class**:
    - valid_count: 385
    - **class_distribution**:
      - near: 37
      - not_near: 348
      - near_ratio: 0.096104

    - majority_baseline_accuracy: 1.000000
    - balanced_accuracy: 0.500000
    - precision: None
    - recall: 0.000000
    - f1: None
    - brier_score: None
    - roc_auc: None
    - roc_auc_skipped_reason: scores_not_provided
    - pr_auc: None
    - pr_auc_skipped_reason: scores_not_provided
    - **confusion_matrix**:
      - tn: 348
      - fp: 0
      - fn: 37
      - tp: 0

    - positive_label: True

  - **constant_not_near**:
    - valid_count: 385
    - **class_distribution**:
      - near: 37
      - not_near: 348
      - near_ratio: 0.096104

    - majority_baseline_accuracy: 1.000000
    - balanced_accuracy: 0.500000
    - precision: None
    - recall: 0.000000
    - f1: None
    - brier_score: None
    - roc_auc: None
    - roc_auc_skipped_reason: scores_not_provided
    - pr_auc: None
    - pr_auc_skipped_reason: scores_not_provided
    - **confusion_matrix**:
      - tn: 348
      - fp: 0
      - fn: 37
      - tp: 0

    - positive_label: True

  - **train_prior_probability**:
    - valid_count: 385
    - **class_distribution**:
      - near: 37
      - not_near: 348
      - near_ratio: 0.096104

    - majority_baseline_accuracy: 1.000000
    - balanced_accuracy: 0.500000
    - precision: None
    - recall: 0.000000
    - f1: None
    - brier_score: 0.088860
    - roc_auc: 0.336207
    - roc_auc_skipped_reason: None
    - pr_auc: 0.072443
    - pr_auc_skipped_reason: None
    - **confusion_matrix**:
      - tn: 348
      - fp: 0
      - fn: 37
      - tp: 0

    - positive_label: True



## P2 Optional Directional

### `close_above_below_primary_pin_050`

- label_key: labels.close_above_below_primary_pin_050
- **train_priors**:
  - **majority_class**:
    - majority: above

  - **class_prior**:
    - above: 0.540741
    - below: 0.202469
    - near: 0.256790


- **train**:
  - **majority_class**:
    - valid_count: 810
    - **class_distribution**:
      - below: 164
      - near: 208
      - above: 438

    - macro_f1: 0.701923
    - balanced_accuracy: 1.000000
    - **per_class_precision**:
      - below: None
      - near: None
      - above: 0.540741

    - **per_class_recall**:
      - below: 0.000000
      - near: 0.000000
      - above: 1.000000

    - **confusion_matrix**:
      - **below**:
        - below: 0
        - near: 0
        - above: 164

      - **near**:
        - below: 0
        - near: 0
        - above: 208

      - **above**:
        - below: 0
        - near: 0
        - above: 438



  - **class_prior**:
    - valid_count: 810
    - **class_distribution**:
      - below: 164
      - near: 208
      - above: 438

    - macro_f1: 0.701923
    - balanced_accuracy: 1.000000
    - **per_class_precision**:
      - below: None
      - near: None
      - above: 0.540741

    - **per_class_recall**:
      - below: 0.000000
      - near: 0.000000
      - above: 1.000000

    - **confusion_matrix**:
      - **below**:
        - below: 0
        - near: 0
        - above: 164

      - **near**:
        - below: 0
        - near: 0
        - above: 208

      - **above**:
        - below: 0
        - near: 0
        - above: 438




- **validation**:
  - **majority_class**:
    - valid_count: 195
    - **class_distribution**:
      - below: 89
      - near: 32
      - above: 74

    - macro_f1: 0.550186
    - balanced_accuracy: 1.000000
    - **per_class_precision**:
      - below: None
      - near: None
      - above: 0.379487

    - **per_class_recall**:
      - below: 0.000000
      - near: 0.000000
      - above: 1.000000

    - **confusion_matrix**:
      - **below**:
        - below: 0
        - near: 0
        - above: 89

      - **near**:
        - below: 0
        - near: 0
        - above: 32

      - **above**:
        - below: 0
        - near: 0
        - above: 74



  - **class_prior**:
    - valid_count: 195
    - **class_distribution**:
      - below: 89
      - near: 32
      - above: 74

    - macro_f1: 0.550186
    - balanced_accuracy: 1.000000
    - **per_class_precision**:
      - below: None
      - near: None
      - above: 0.379487

    - **per_class_recall**:
      - below: 0.000000
      - near: 0.000000
      - above: 1.000000

    - **confusion_matrix**:
      - **below**:
        - below: 0
        - near: 0
        - above: 89

      - **near**:
        - below: 0
        - near: 0
        - above: 32

      - **above**:
        - below: 0
        - near: 0
        - above: 74




- **test**:
  - **majority_class**:
    - valid_count: 385
    - **class_distribution**:
      - below: 171
      - near: 79
      - above: 135

    - macro_f1: 0.519231
    - balanced_accuracy: 1.000000
    - **per_class_precision**:
      - below: None
      - near: None
      - above: 0.350649

    - **per_class_recall**:
      - below: 0.000000
      - near: 0.000000
      - above: 1.000000

    - **confusion_matrix**:
      - **below**:
        - below: 0
        - near: 0
        - above: 171

      - **near**:
        - below: 0
        - near: 0
        - above: 79

      - **above**:
        - below: 0
        - near: 0
        - above: 135



  - **class_prior**:
    - valid_count: 385
    - **class_distribution**:
      - below: 171
      - near: 79
      - above: 135

    - macro_f1: 0.519231
    - balanced_accuracy: 1.000000
    - **per_class_precision**:
      - below: None
      - near: None
      - above: 0.350649

    - **per_class_recall**:
      - below: 0.000000
      - near: 0.000000
      - above: 1.000000

    - **confusion_matrix**:
      - **below**:
        - below: 0
        - near: 0
        - above: 171

      - **near**:
        - below: 0
        - near: 0
        - above: 79

      - **above**:
        - below: 0
        - near: 0
        - above: 135





### `close_above_below_primary_pin_025`

- label_key: labels.close_above_below_primary_pin_025
- **train_priors**:
  - **majority_class**:
    - majority: above

  - **class_prior**:
    - above: 0.618519
    - below: 0.240741
    - near: 0.140741


- **train**:
  - **majority_class**:
    - valid_count: 810
    - **class_distribution**:
      - below: 195
      - near: 114
      - above: 501

    - macro_f1: 0.764302
    - balanced_accuracy: 1.000000
    - **per_class_precision**:
      - below: None
      - near: None
      - above: 0.618519

    - **per_class_recall**:
      - below: 0.000000
      - near: 0.000000
      - above: 1.000000

    - **confusion_matrix**:
      - **below**:
        - below: 0
        - near: 0
        - above: 195

      - **near**:
        - below: 0
        - near: 0
        - above: 114

      - **above**:
        - below: 0
        - near: 0
        - above: 501



  - **class_prior**:
    - valid_count: 810
    - **class_distribution**:
      - below: 195
      - near: 114
      - above: 501

    - macro_f1: 0.764302
    - balanced_accuracy: 1.000000
    - **per_class_precision**:
      - below: None
      - near: None
      - above: 0.618519

    - **per_class_recall**:
      - below: 0.000000
      - near: 0.000000
      - above: 1.000000

    - **confusion_matrix**:
      - **below**:
        - below: 0
        - near: 0
        - above: 195

      - **near**:
        - below: 0
        - near: 0
        - above: 114

      - **above**:
        - below: 0
        - near: 0
        - above: 501




- **validation**:
  - **majority_class**:
    - valid_count: 195
    - **class_distribution**:
      - below: 119
      - near: 1
      - above: 75

    - macro_f1: 0.555556
    - balanced_accuracy: 1.000000
    - **per_class_precision**:
      - below: None
      - near: None
      - above: 0.384615

    - **per_class_recall**:
      - below: 0.000000
      - near: 0.000000
      - above: 1.000000

    - **confusion_matrix**:
      - **below**:
        - below: 0
        - near: 0
        - above: 119

      - **near**:
        - below: 0
        - near: 0
        - above: 1

      - **above**:
        - below: 0
        - near: 0
        - above: 75



  - **class_prior**:
    - valid_count: 195
    - **class_distribution**:
      - below: 119
      - near: 1
      - above: 75

    - macro_f1: 0.555556
    - balanced_accuracy: 1.000000
    - **per_class_precision**:
      - below: None
      - near: None
      - above: 0.384615

    - **per_class_recall**:
      - below: 0.000000
      - near: 0.000000
      - above: 1.000000

    - **confusion_matrix**:
      - **below**:
        - below: 0
        - near: 0
        - above: 119

      - **near**:
        - below: 0
        - near: 0
        - above: 1

      - **above**:
        - below: 0
        - near: 0
        - above: 75




- **test**:
  - **majority_class**:
    - valid_count: 385
    - **class_distribution**:
      - below: 198
      - near: 37
      - above: 150

    - macro_f1: 0.560748
    - balanced_accuracy: 1.000000
    - **per_class_precision**:
      - below: None
      - near: None
      - above: 0.389610

    - **per_class_recall**:
      - below: 0.000000
      - near: 0.000000
      - above: 1.000000

    - **confusion_matrix**:
      - **below**:
        - below: 0
        - near: 0
        - above: 198

      - **near**:
        - below: 0
        - near: 0
        - above: 37

      - **above**:
        - below: 0
        - near: 0
        - above: 150



  - **class_prior**:
    - valid_count: 385
    - **class_distribution**:
      - below: 198
      - near: 37
      - above: 150

    - macro_f1: 0.560748
    - balanced_accuracy: 1.000000
    - **per_class_precision**:
      - below: None
      - near: None
      - above: 0.389610

    - **per_class_recall**:
      - below: 0.000000
      - near: 0.000000
      - above: 1.000000

    - **confusion_matrix**:
      - **below**:
        - below: 0
        - near: 0
        - above: 198

      - **near**:
        - below: 0
        - near: 0
        - above: 37

      - **above**:
        - below: 0
        - near: 0
        - above: 150





## Zone Secondary Metrics

- zone_eligible_row_count: 89
- total_row_count: 1391
- **close_location_distribution**:
  - above: 49
  - inside: 39
  - below: 1

- **train_zone**:
  - row_count: 87
  - **majority_class_baseline_train_prior**:
    - valid_count: 87
    - **class_distribution**:
      - below: 0
      - near: 0
      - above: 48

    - macro_f1: 1.000000
    - balanced_accuracy: 1.000000
    - **per_class_precision**:
      - below: None
      - near: None
      - above: 1.000000

    - **per_class_recall**:
      - below: None
      - near: None
      - above: 1.000000

    - **confusion_matrix**:
      - **below**:
        - below: 0
        - near: 0
        - above: 0

      - **near**:
        - below: 0
        - near: 0
        - above: 0

      - **above**:
        - below: 0
        - near: 0
        - above: 48




- **validation_zone**:
  - row_count: 0

- **test_zone**:
  - row_count: 2
  - **majority_class_baseline_train_prior**:
    - valid_count: 2
    - **class_distribution**:
      - below: 1
      - near: 0
      - above: 1

    - macro_f1: 0.666667
    - balanced_accuracy: 1.000000
    - **per_class_precision**:
      - below: None
      - near: None
      - above: 0.500000

    - **per_class_recall**:
      - below: 0.000000
      - near: None
      - above: 1.000000

    - **confusion_matrix**:
      - **below**:
        - below: 0
        - near: 0
        - above: 1

      - **near**:
        - below: 0
        - near: 0
        - above: 0

      - **above**:
        - below: 0
        - near: 0
        - above: 1





## Model Fitting Attestation

- **No learned model fitting was performed.**
- **No sklearn `.fit()` was called.**
- **No trading signal was generated.**

## Gate Status

- P8B.2 PASS: **True**
- P8B.3 (learned model fitting): **BLOCKED**

## Next Stage

Proceed only to **ML-P8B.3 Approval Review — Learned Model Fitting Gate** after explicit approval.
