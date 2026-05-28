from __future__ import annotations

import copy
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gymflow_core.weather_features import WEATHER_FEATURES, join_weather

try:
    import torch
    from torch import nn
    from torch.utils.data import DataLoader, TensorDataset
except ModuleNotFoundError:
    torch = None
    class _MissingNN:
        class Module:
            pass

    nn = _MissingNN()
    DataLoader = None
    TensorDataset = None


FEATURES_PATH = ROOT / "data" / "processed" / "occupancy_features.csv"
WEATHER_PATH = ROOT / "data" / "external" / "weather_observation_features.csv"
REPORTS_DIR = ROOT / "ml" / "reports"
ARTIFACTS_DIR = ROOT / "ml" / "models" / "artifacts"

TARGET = "active_people"
SEQUENCE_WINDOW = int(os.getenv("GYMFLOW_DEEP_WINDOW", "12"))
BATCH_SIZE = int(os.getenv("GYMFLOW_DEEP_BATCH_SIZE", "256"))
MAX_EPOCHS = int(os.getenv("GYMFLOW_DEEP_EPOCHS", "18"))
PATIENCE = int(os.getenv("GYMFLOW_DEEP_PATIENCE", "5"))
SEED = int(os.getenv("GYMFLOW_DEEP_SEED", "42"))

CONTEXT_FEATURES = [
    "hour",
    "day_of_week",
    "is_weekend",
    "month",
    "day_of_month",
    "week_of_year",
    "is_open_estimated",
    "is_public_holiday_ua",
    "is_gym_closed_holiday",
    "is_major_low_traffic_holiday",
    "is_major_holiday_window",
    "days_to_nearest_major_holiday",
    "holiday_effect_multiplier",
    "lag_1",
    "lag_4",
    "lag_96",
    "rolling_mean_4",
    "rolling_mean_16",
    "rolling_mean_96",
    *WEATHER_FEATURES,
]
TOKEN_FEATURES = [TARGET, *CONTEXT_FEATURES]


@dataclass(frozen=True)
class DeepMetric:
    model: str
    scope: str
    sequence_window: int
    train_rows: int
    validation_rows: int
    test_rows: int
    epochs_trained: int
    device: str
    mae: float
    rmse: float
    wape: float


class LSTMForecast(nn.Module):
    def __init__(
        self,
        input_dim: int,
        context_dim: int,
        gym_count: int,
        hidden_dim: int = 96,
        embedding_dim: int = 16,
        dropout: float = 0.15,
    ) -> None:
        super().__init__()
        self.gym_embedding = nn.Embedding(gym_count, embedding_dim)
        self.encoder = nn.LSTM(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=2,
            batch_first=True,
            dropout=dropout,
        )
        self.head = nn.Sequential(
            nn.Linear(hidden_dim + context_dim + embedding_dim, 128),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(128, 1),
        )

    def forward(self, sequence, context, gym_index):
        _, (hidden, _) = self.encoder(sequence)
        gym_vector = self.gym_embedding(gym_index)
        features = torch.cat([hidden[-1], context, gym_vector], dim=1)
        return self.head(features).squeeze(1)


class GRUForecast(nn.Module):
    def __init__(
        self,
        input_dim: int,
        context_dim: int,
        gym_count: int,
        hidden_dim: int = 96,
        embedding_dim: int = 16,
        dropout: float = 0.15,
    ) -> None:
        super().__init__()
        self.gym_embedding = nn.Embedding(gym_count, embedding_dim)
        self.encoder = nn.GRU(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=2,
            batch_first=True,
            dropout=dropout,
        )
        self.head = nn.Sequential(
            nn.Linear(hidden_dim + context_dim + embedding_dim, 128),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(128, 1),
        )

    def forward(self, sequence, context, gym_index):
        _, hidden = self.encoder(sequence)
        gym_vector = self.gym_embedding(gym_index)
        features = torch.cat([hidden[-1], context, gym_vector], dim=1)
        return self.head(features).squeeze(1)


class TransformerForecast(nn.Module):
    def __init__(
        self,
        input_dim: int,
        context_dim: int,
        gym_count: int,
        sequence_window: int,
        model_dim: int = 96,
        embedding_dim: int = 16,
        dropout: float = 0.15,
    ) -> None:
        super().__init__()
        self.gym_embedding = nn.Embedding(gym_count, embedding_dim)
        self.input_projection = nn.Linear(input_dim, model_dim)
        self.position_embedding = nn.Parameter(torch.zeros(1, sequence_window, model_dim))
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=model_dim,
            nhead=4,
            dim_feedforward=192,
            dropout=dropout,
            activation="gelu",
            batch_first=True,
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=2)
        self.head = nn.Sequential(
            nn.Linear(model_dim + context_dim + embedding_dim, 128),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(128, 1),
        )

    def forward(self, sequence, context, gym_index):
        projected = self.input_projection(sequence) + self.position_embedding
        encoded = self.encoder(projected)
        gym_vector = self.gym_embedding(gym_index)
        features = torch.cat([encoded[:, -1, :], context, gym_vector], dim=1)
        return self.head(features).squeeze(1)


def require_torch() -> None:
    if torch is None:
        raise SystemExit(
            "PyTorch is not installed. Run `make torch-setup` first, then run `make deep`."
        )


def set_seed() -> None:
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(SEED)


def load_dataset() -> pd.DataFrame:
    if not FEATURES_PATH.exists():
        raise FileNotFoundError(f"Missing features file: {FEATURES_PATH}. Run make data first.")
    df = pd.read_csv(FEATURES_PATH)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    if WEATHER_PATH.exists():
        df = join_weather(df, WEATHER_PATH)
    for column in [TARGET, *CONTEXT_FEATURES]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    return df.sort_values(["gym_id", "timestamp"]).reset_index(drop=True)


def build_sequence_arrays(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, pd.DataFrame, dict[str, int]]:
    gym_ids = sorted(str(value) for value in df["gym_id"].unique())
    gym_mapping = {gym_id: index for index, gym_id in enumerate(gym_ids)}
    sequences: list[np.ndarray] = []
    contexts: list[np.ndarray] = []
    gym_indices: list[int] = []
    targets: list[float] = []
    meta_rows: list[dict[str, object]] = []

    for gym_id, group in df.groupby("gym_id", sort=False):
        group = group.sort_values("timestamp").reset_index(drop=True)
        token_values = group[TOKEN_FEATURES].astype(float).to_numpy()
        context_values = group[CONTEXT_FEATURES].astype(float).to_numpy()
        target_values = group[TARGET].astype(float).to_numpy()
        mapped_gym = gym_mapping[str(gym_id)]

        for index in range(SEQUENCE_WINDOW, len(group)):
            sequences.append(token_values[index - SEQUENCE_WINDOW : index])
            contexts.append(context_values[index])
            gym_indices.append(mapped_gym)
            targets.append(float(target_values[index]))
            meta_rows.append(
                {
                    "gym_id": str(gym_id),
                    "timestamp": group.loc[index, "timestamp"],
                }
            )

    if not sequences:
        raise ValueError("Not enough rows to build deep-learning sequences.")

    return (
        np.stack(sequences).astype(np.float32),
        np.stack(contexts).astype(np.float32),
        np.asarray(gym_indices, dtype=np.int64),
        np.asarray(targets, dtype=np.float32),
        pd.DataFrame(meta_rows),
        gym_mapping,
    )


def split_indices(meta_df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    train_indices: list[int] = []
    validation_indices: list[int] = []
    test_indices: list[int] = []

    for _, group in meta_df.reset_index().groupby("gym_id", sort=False):
        group = group.sort_values("timestamp")
        first_split = max(1, int(len(group) * 0.7))
        second_split = max(first_split + 1, int(len(group) * 0.8))
        train_indices.extend(group.iloc[:first_split]["index"].tolist())
        validation_indices.extend(group.iloc[first_split:second_split]["index"].tolist())
        test_indices.extend(group.iloc[second_split:]["index"].tolist())

    return (
        np.asarray(train_indices, dtype=np.int64),
        np.asarray(validation_indices, dtype=np.int64),
        np.asarray(test_indices, dtype=np.int64),
    )


def preprocess_arrays(
    sequences: np.ndarray,
    contexts: np.ndarray,
    targets: np.ndarray,
    train_indices: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float, float]:
    token_imputer = SimpleImputer(strategy="median")
    token_scaler = StandardScaler()
    context_imputer = SimpleImputer(strategy="median")
    context_scaler = StandardScaler()

    train_tokens = sequences[train_indices].reshape(-1, sequences.shape[-1])
    token_scaler.fit(token_imputer.fit_transform(train_tokens))
    flat_tokens = sequences.reshape(-1, sequences.shape[-1])
    scaled_tokens = token_scaler.transform(token_imputer.transform(flat_tokens))
    sequences_scaled = scaled_tokens.reshape(sequences.shape).astype(np.float32)

    context_scaler.fit(context_imputer.fit_transform(contexts[train_indices]))
    contexts_scaled = context_scaler.transform(context_imputer.transform(contexts)).astype(np.float32)

    transformed_targets = np.log1p(np.clip(targets, 0, None))
    target_mean = float(np.mean(transformed_targets[train_indices]))
    target_std = float(np.std(transformed_targets[train_indices]))
    if target_std < 1e-6:
        target_std = 1.0
    targets_scaled = ((transformed_targets - target_mean) / target_std).astype(np.float32)
    return sequences_scaled, contexts_scaled, targets_scaled, target_mean, target_std


def make_loader(
    sequences: np.ndarray,
    contexts: np.ndarray,
    gym_indices: np.ndarray,
    targets: np.ndarray,
    indices: np.ndarray,
    shuffle: bool,
) -> DataLoader:
    dataset = TensorDataset(
        torch.from_numpy(sequences[indices]),
        torch.from_numpy(contexts[indices]),
        torch.from_numpy(gym_indices[indices]),
        torch.from_numpy(targets[indices]),
    )
    return DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=shuffle)


def train_model(
    model: nn.Module,
    train_loader: DataLoader,
    validation_loader: DataLoader,
    device: torch.device,
) -> tuple[nn.Module, int]:
    criterion = nn.SmoothL1Loss(beta=0.5)
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.001, weight_decay=0.001)
    model.to(device)

    best_state = copy.deepcopy(model.state_dict())
    best_validation_loss = float("inf")
    stale_epochs = 0
    epochs_trained = 0

    for epoch in range(1, MAX_EPOCHS + 1):
        model.train()
        for sequence, context, gym_index, target in train_loader:
            sequence = sequence.to(device)
            context = context.to(device)
            gym_index = gym_index.to(device)
            target = target.to(device)

            optimizer.zero_grad(set_to_none=True)
            loss = criterion(model(sequence, context, gym_index), target)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()

        validation_loss = evaluate_loss(model, validation_loader, criterion, device)
        epochs_trained = epoch
        if validation_loss < best_validation_loss:
            best_validation_loss = validation_loss
            best_state = copy.deepcopy(model.state_dict())
            stale_epochs = 0
        else:
            stale_epochs += 1
            if stale_epochs >= PATIENCE:
                break

    model.load_state_dict(best_state)
    return model, epochs_trained


def evaluate_loss(model: nn.Module, loader: DataLoader, criterion: nn.Module, device: torch.device) -> float:
    model.eval()
    losses: list[float] = []
    with torch.no_grad():
        for sequence, context, gym_index, target in loader:
            sequence = sequence.to(device)
            context = context.to(device)
            gym_index = gym_index.to(device)
            target = target.to(device)
            losses.append(float(criterion(model(sequence, context, gym_index), target).item()))
    return float(np.mean(losses)) if losses else float("inf")


def predict(model: nn.Module, loader: DataLoader, device: torch.device, target_mean: float, target_std: float) -> np.ndarray:
    model.eval()
    predictions: list[np.ndarray] = []
    with torch.no_grad():
        for sequence, context, gym_index, _ in loader:
            sequence = sequence.to(device)
            context = context.to(device)
            gym_index = gym_index.to(device)
            batch_prediction = model(sequence, context, gym_index).cpu().numpy()
            predictions.append(batch_prediction)
    scaled = np.concatenate(predictions)
    return np.clip(np.expm1(scaled * target_std + target_mean), 0, None)


def calculate_metrics(
    model_name: str,
    y_true: np.ndarray,
    y_pred: np.ndarray,
    train_rows: int,
    validation_rows: int,
    epochs_trained: int,
    device: str,
) -> DeepMetric:
    absolute_errors = np.abs(y_true - y_pred)
    actual_total = np.sum(np.abs(y_true))
    return DeepMetric(
        model=model_name,
        scope="all_gyms_pooled_sequence",
        sequence_window=SEQUENCE_WINDOW,
        train_rows=train_rows,
        validation_rows=validation_rows,
        test_rows=len(y_true),
        epochs_trained=epochs_trained,
        device=device,
        mae=round(float(mean_absolute_error(y_true, y_pred)), 4),
        rmse=round(float(np.sqrt(mean_squared_error(y_true, y_pred))), 4),
        wape=round(float(np.sum(absolute_errors) / actual_total), 4) if actual_total else 0.0,
    )


def run_experiment() -> list[DeepMetric]:
    require_torch()
    set_seed()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    df = load_dataset()
    sequences, contexts, gym_indices, targets, meta_df, gym_mapping = build_sequence_arrays(df)
    train_indices, validation_indices, test_indices = split_indices(meta_df)
    sequences, contexts, targets_scaled, target_mean, target_std = preprocess_arrays(
        sequences,
        contexts,
        targets,
        train_indices,
    )

    train_loader = make_loader(sequences, contexts, gym_indices, targets_scaled, train_indices, shuffle=True)
    validation_loader = make_loader(sequences, contexts, gym_indices, targets_scaled, validation_indices, shuffle=False)
    test_loader = make_loader(sequences, contexts, gym_indices, targets_scaled, test_indices, shuffle=False)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model_specs = {
        "lstm_sequence_torch": LSTMForecast(
            input_dim=sequences.shape[-1],
            context_dim=contexts.shape[-1],
            gym_count=len(gym_mapping),
        ),
        "gru_sequence_torch": GRUForecast(
            input_dim=sequences.shape[-1],
            context_dim=contexts.shape[-1],
            gym_count=len(gym_mapping),
        ),
        "transformer_sequence_torch": TransformerForecast(
            input_dim=sequences.shape[-1],
            context_dim=contexts.shape[-1],
            gym_count=len(gym_mapping),
            sequence_window=SEQUENCE_WINDOW,
        ),
    }

    metrics: list[DeepMetric] = []
    predictions = meta_df.iloc[test_indices].copy().reset_index(drop=True)
    predictions["actual_active_people"] = targets[test_indices]

    for model_name, model in model_specs.items():
        trained_model, epochs_trained = train_model(model, train_loader, validation_loader, device)
        y_pred = predict(trained_model, test_loader, device, target_mean, target_std)
        predictions[f"pred_{model_name}"] = y_pred
        metrics.append(
            calculate_metrics(
                model_name=model_name,
                y_true=targets[test_indices],
                y_pred=y_pred,
                train_rows=len(train_indices),
                validation_rows=len(validation_indices),
                epochs_trained=epochs_trained,
                device=str(device),
            )
        )
        torch.save(
            {
                "state_dict": trained_model.cpu().state_dict(),
                "model_name": model_name,
                "sequence_window": SEQUENCE_WINDOW,
                "token_features": TOKEN_FEATURES,
                "context_features": CONTEXT_FEATURES,
                "gym_mapping": gym_mapping,
            },
            ARTIFACTS_DIR / f"{model_name}.pt",
        )

    records = [asdict(row) for row in sorted(metrics, key=lambda row: (row.mae, row.rmse))]
    pd.DataFrame(records).to_csv(REPORTS_DIR / "deep_learning_metrics.csv", index=False)
    (REPORTS_DIR / "deep_learning_metrics.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    predictions.to_csv(REPORTS_DIR / "deep_learning_predictions_sample.csv", index=False)
    return metrics


def main() -> None:
    records = [asdict(row) for row in run_experiment()]
    print(json.dumps(records, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
