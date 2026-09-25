"""Point-in-time machine-learning scoring; models never authorize orders."""

from packages.machine_learning.artifacts import (
    ArtifactReference,
    LocalArtifactStore,
    ObjectArtifactClient,
    RemoteArtifactStore,
)
from packages.machine_learning.baseline import (
    FeatureDefinition,
    FeatureDrift,
    FeatureImportance,
    FeatureObservation,
    LogisticBaseline,
    ModelEvaluation,
    ModelPrediction,
    expected_calibration_error,
    population_stability_index,
    train_logistic_baseline,
)
from packages.machine_learning.calibration import (
    PlattCalibratedBaseline,
    train_platt_calibrated_baseline,
)
from packages.machine_learning.gradient_boosting import (
    GradientBoostingBaseline,
    GradientBoostingConfig,
    train_gradient_boosting_baseline,
)
from packages.machine_learning.persistence import (
    ModelRegistry,
    ModelStage,
    PredictionLogger,
    RegisteredModel,
)
from packages.machine_learning.portable import PortableLogisticModel
from packages.machine_learning.random_forest import (
    RandomForestBaseline,
    RandomForestConfig,
    train_random_forest_baseline,
)
from packages.machine_learning.s3_artifacts import S3ObjectArtifactClient, S3SDKClient
from packages.machine_learning.selection import (
    MetricDirection,
    MetricGuardrail,
    ModelComparison,
    ModelComparisonPolicy,
    compare_models,
)
from packages.machine_learning.tracking import (
    MLflowMetadataExporter,
    MLflowModule,
    MLflowRunRecord,
)

__all__ = [
    "ArtifactReference",
    "FeatureDefinition",
    "FeatureDrift",
    "FeatureImportance",
    "FeatureObservation",
    "GradientBoostingBaseline",
    "GradientBoostingConfig",
    "LocalArtifactStore",
    "LogisticBaseline",
    "MLflowMetadataExporter",
    "MLflowModule",
    "MLflowRunRecord",
    "MetricDirection",
    "MetricGuardrail",
    "ModelComparison",
    "ModelComparisonPolicy",
    "ModelEvaluation",
    "ModelPrediction",
    "ModelRegistry",
    "ModelStage",
    "ObjectArtifactClient",
    "PlattCalibratedBaseline",
    "PortableLogisticModel",
    "PredictionLogger",
    "RandomForestBaseline",
    "RandomForestConfig",
    "RegisteredModel",
    "RemoteArtifactStore",
    "S3ObjectArtifactClient",
    "S3SDKClient",
    "compare_models",
    "expected_calibration_error",
    "population_stability_index",
    "train_gradient_boosting_baseline",
    "train_logistic_baseline",
    "train_platt_calibrated_baseline",
    "train_random_forest_baseline",
]
