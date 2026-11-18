"""実際にPyTorchで学習する実験用MLP。的中率向上を保証しない。"""
from __future__ import annotations

from dataclasses import dataclass
from .core import Draw, HistoryAnalyzer


@dataclass(frozen=True)
class TrainingReport:
    train_samples: int
    validation_samples: int
    epochs: int
    validation_bce: float
    random_baseline_bce: float
    # Trueであっても将来の抽せんに対する優位性の証明にはならない。
    beats_baseline_on_holdout: bool


class DeepLearningForecaster:
    """111特徴量→MLP→37数字の独立シグモイド出力。

    ラベルは次回抽せんの7数字。各学習サンプルに未来の抽せんを混ぜない。
    最後の時系列20%を検証に使い、早期終了する。
    """

    def __init__(self, seed: int = 42, epochs: int = 60, patience: int = 8):
        self.seed = seed
        self.epochs = epochs
        self.patience = patience
        self.model = None
        self.report: TrainingReport | None = None

    def fit(self, history: list[Draw]) -> TrainingReport:
        try:
            import torch
        except ImportError as exc:
            raise RuntimeError("PyTorchが必要です: pip install -e '.[dl]'") from exc
        ordered = sorted(history, key=lambda d: d.draw_no)
        if len(ordered) < 80:
            raise ValueError("深層学習には80回以上の履歴が必要です（精度は保証されません）")
        torch.manual_seed(self.seed)
        inputs, labels = [], []
        for index in range(20, len(ordered)):
            # index回目の結果を、index-1回目までだけから予測する。
            inputs.append(HistoryAnalyzer(ordered[:index]).ml_features())
            labels.append([1.0 if n in ordered[index].numbers else 0.0 for n in range(1, 38)])
        x, y = torch.tensor(inputs, dtype=torch.float32), torch.tensor(labels, dtype=torch.float32)
        cutoff = int(len(x) * 0.8)
        xtrain, ytrain = x[:cutoff], y[:cutoff]
        xval, yval = x[cutoff:], y[cutoff:]
        model = torch.nn.Sequential(
            torch.nn.Linear(111, 64), torch.nn.ReLU(),
            torch.nn.Dropout(0.2),
            torch.nn.Linear(64, 32), torch.nn.ReLU(),
            torch.nn.Linear(32, 37),
        )
        loss_fn = torch.nn.BCEWithLogitsLoss()
        optimizer = torch.optim.Adam(model.parameters(), lr=0.001, weight_decay=0.005)
        best_loss = float("inf")
        best_state = None
        stale, used_epochs = 0, 0
        for epoch in range(self.epochs):
            model.train()
            optimizer.zero_grad()
            loss_fn(model(xtrain), ytrain).backward()
            optimizer.step()
            model.eval()
            with torch.no_grad():
                val_loss = float(loss_fn(model(xval), yval).item())
            used_epochs = epoch + 1
            if val_loss < best_loss - 1e-5:
                best_loss = val_loss
                best_state = {key: value.detach().clone() for key, value in model.state_dict().items()}
                stale = 0
            else:
                stale += 1
                if stale >= self.patience:
                    break
        assert best_state is not None
        model.load_state_dict(best_state)
        model.eval()
        # 公平抽せん時の一数字の採用率(7/37)を固定ベースラインにする。
        baseline_probability = 7 / 37
        baseline = -(7 / 37) * __import__("math").log(baseline_probability) - (30 / 37) * __import__("math").log(1 - baseline_probability)
        self.model = model
        self.report = TrainingReport(len(xtrain), len(xval), used_epochs,
                                     round(best_loss, 6), round(baseline, 6),
                                     best_loss < baseline)
        return self.report

    def predict(self, history: list[Draw]) -> dict[int, float]:
        if self.model is None:
            raise RuntimeError("fit()を実行してください")
        import torch
        features = HistoryAnalyzer(history).ml_features()
        with torch.no_grad():
            x = torch.tensor([features], dtype=torch.float32)
            result = torch.sigmoid(self.model(x))[0].tolist()
        # 各出力は学習モデルのスコア。校正された当せん確率ではない。
        return {n: float(result[n - 1]) for n in range(1, 38)}