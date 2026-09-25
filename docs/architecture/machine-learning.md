# Machine-learning scoring

The first Phase 10 slice is an optional logistic-regression baseline. A versioned feature definition fixes ordered,
unique feature names. Every observation records the UTC-aware time at which all values became available, rejects
non-finite values, and carries a binary label only for training/evaluation. Training requires chronological input and
uses only observations at or before the training cutoff; validation uses the later half-open period through its own
cutoff. Empty splits, missing labels, or one-class training data fail closed.

The baseline standardizes features and fits scikit-learn logistic regression with a fixed random state and solver.
Validation records sample count, accuracy, Brier score, log loss, and expected calibration error rather than declaring
success from one metric. Coefficient reporting maps every standardized coefficient back to its versioned feature name
and includes its absolute share; this is transparent model evidence, not a causal-importance claim.
Prediction rejects a feature snapshot that was unavailable at prediction time or does not exactly match the versioned
schema. Every prediction retains model and feature versions.

Point-in-time drift monitoring computes per-feature population stability index (PSI) from reference-quantile bins.
Both populations must match the exact schema and be available by the monitoring cutoff; future observations fail
closed. PSI is a monitoring signal whose thresholds must be configured and validated operationally.

The metadata-only registry records model/feature versions, training time, approved artifact URI, SHA-256 digest,
numeric metrics, and challenger/champion/archive stage. It never deserializes model binaries. Promotion archives the
previous champion for the same model name. Prediction logging is idempotent by prediction ID and fingerprints the
complete feature, model, instrument, snapshot, probability, and timestamp evidence; conflicting reuse fails closed.

Champion/challenger comparison is an explicit, side-effect-free policy. Models must share family and feature version,
provide finite values for every required metric, exceed the configured primary-metric improvement, and remain within
each named guardrail's maximum regression. The result contains stable reason codes and never promotes a model; an
independent audited registry action is still required.

Optional Platt scaling uses three strictly ordered and disjoint windows: the base classifier fits on training data,
the one-dimensional calibrator fits only on later calibration logits, and reported metrics use a still-later validation
window. Every window must be non-empty, labeled, and contain both classes. Point-in-time and exact-schema prediction
guards remain identical to the uncalibrated baseline; calibration never grants trading authority.

A bounded random-forest challenger uses explicit tree count, depth, leaf-size, seed, and single-worker settings. It
shares the logistic baseline's chronological split, exact-schema, label, availability-time, and multi-metric contracts.
Impurity-based importance is mapped to versioned feature names and identified only as model evidence; deterministic
settings make repeated offline runs reproducible but do not imply profitable or stable live behavior.

A bounded gradient-boosting challenger likewise fixes estimator count, learning rate, tree depth, minimum leaf size,
and random seed. It uses the same chronological validation and point-in-time prediction guards, reports the same
multi-metric evaluation, and maps impurity importance to the versioned feature schema. Its deterministic output is a
challenger score only and requires the independent comparison and promotion workflow.

The local artifact store treats artifacts as opaque bytes and never deserializes them. Content-addressed SHA-256 paths,
atomic no-overwrite publication, registered size/checksum verification, a configured size ceiling, root containment,
and symlink rejection protect local evidence. Artifact serialization remains the training pipeline's responsibility;
loading returns bytes only, so pickle-like payloads cannot execute through this boundary.

Remote artifact storage uses a narrow injected object-client contract rather than importing a vendor SDK into the
domain package. Objects use checksum-derived keys under one configured bucket/prefix, conditional create semantics,
and an `artifact+s3` evidence URI. Reads derive the only permitted key from the registered digest and reject bucket,
path, query, fragment, size, or checksum mismatches. The client implementation owns credentials and transport.
The optional S3 adapter accepts an already-configured SDK client, uses `If-None-Match: *` for immutable publication,
maps only precondition failure to an existing object, bounds reads using declared and actual length, and closes streams.

The logistic baseline has an explicit portable inference format containing only canonical JSON scalars and arrays.
Reconstruction requires an exact format/schema, finite parameters, positive scaler values, and vectors matching the
versioned feature definition. It recreates the standardized linear probability calculation rather than loading a
Python object graph, and retains the same exact-schema and point-in-time prediction guards.

The optional MLflow exporter accepts an injected fluent client and records only validated model/feature identity,
UTC training time, finite evaluation metrics, artifact URI/checksum/size, and explicit scoring-only/no-auto-promotion
tags. It neither uploads artifact bytes nor changes a registry stage, and returns the externally assigned run ID as
evidence. SDK configuration, authentication, transport, and lifecycle remain deployment concerns.

This model is a scoring input only. It has no broker, execution, or risk-engine dependency and cannot authorize or
place an order. Live object-store and MLflow service validation remain Phase 10 work.
