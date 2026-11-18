"""NumPyによる小規模MLP（2隠れ層）。公開デモでも実際に学習を実行する。"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import numpy as np

from .core import Draw, HistoryAnalyzer


@dataclass(frozen=True)
class NumpyTrainingReport:
    """時系列順の学習・検証結果。BCEは的中確率ではない。"""
    method: str
    training_samples: int
    validation_samples: int
    epochs: int
    validation_bce: float
    random_baseline_bce: float
    better_than_baseline: bool


class NumpyDeepForecaster:
    """111→32→16→37のニューラルネットワーク。

    7つの当せん数字をmulti-labelの37次元で表現してBCEを学習。
    データリーク防止のため時系列の後ろ20%を検証用に分離する。
    学習出力は未校正の選択スコアで、次回の確率を示さない。
    """

    def __init__(self, seed: int = 42, epochs: int = 65):
        self.seed = seed
        self.epochs = epochs
        self.report: NumpyTrainingReport | None = None
        self.params: dict[str, np.ndarray] = {}

    @staticmethod
    def _sigmoid(x: np.ndarray) -> np.ndarray:
        return 1 / (1 + np.exp(-np.clip(x, -30, 30)))

    @staticmethod
    def _bce(p: np.ndarray, y: np.ndarray) -> float:
        return float(-np.mean(y * np.log(p + 1e-8) + (1 - y) * np.log(1 - p + 1e-8)))

    def _forward(self, x: np.ndarray):
        p = self.params
        a = np.maximum(0, x @ p['w1'] + p['b1'])
        b = np.maximum(0, a @ p['w2'] + p['b2'])
        o = self._sigmoid(b @ p['w3'] + p['b3'])
        return a, b, o

    def fit(self, history: list[Draw]) -> NumpyTrainingReport:
        ordered = sorted(history, key=lambda d: d.draw_no)
        if len(ordered) < 80:
            raise ValueError('深層学習には80回以上の履歴が必要です')
        # 各入力の直後の抽せん結果だけを教師信号にする。
        x = np.array([HistoryAnalyzer(ordered[:i]).ml_features()
                      for i in range(20, len(ordered))], dtype=np.float64)
        y = np.array([[float(n in ordered[i].numbers) for n in range(1, 38)]
                      for i in range(20, len(ordered))], dtype=np.float64)
        cut = int(len(x) * .8)
        x_train, y_train, x_val, y_val = x[:cut], y[:cut], x[cut:], y[cut:]
        rng = np.random.default_rng(self.seed)
        self.params = {
            'w1': rng.normal(0, np.sqrt(2 / 111), (111, 32)), 'b1': np.zeros(32),
            'w2': rng.normal(0, np.sqrt(2 / 32), (32, 16)), 'b2': np.zeros(16),
            'w3': rng.normal(0, np.sqrt(1 / 16), (16, 37)), 'b3': np.zeros(37),
        }
        m = {k: np.zeros_like(v) for k, v in self.params.items()}
        v = {k: np.zeros_like(z) for k, z in self.params.items()}
        best_loss = float('inf')
        best = {}
        best_epoch = 0
        stale = 0
        for epoch in range(1, self.epochs + 1):
            a, b, out = self._forward(x_train)
            # BCE微分; サンプル数とラベル数の両方で正規化。
            dz3 = (out - y_train) / (len(x_train) * 37)
            grad = {'w3': b.T @ dz3, 'b3': dz3.sum(axis=0)}
            db = dz3 @ self.params['w3'].T * (b > 0)
            grad['w2'] = a.T @ db
            grad['b2'] = db.sum(axis=0)
            da = db @ self.params['w2'].T * (a > 0)
            grad['w1'] = x_train.T @ da
            grad['b1'] = da.sum(axis=0)
            # Adam; 小標本向けにL2正則化も加える。
            for k in self.params:
                g = grad[k] + (0.0001 * self.params[k] if k.startswith('w') else 0)
                m[k] = 0.9 * m[k] + 0.1 * g
                v[k] = 0.999 * v[k] + 0.001 * g * g
                self.params[k] -= 0.008 * (m[k] / (1 - 0.9 ** epoch)) / (
                    np.sqrt(v[k] / (1 - 0.999 ** epoch)) + 1e-8)
            val_loss = self._bce(self._forward(x_val)[2], y_val)
            if val_loss + 1e-5 < best_loss:
                best_loss = val_loss
                best = {k: t.copy() for k, t in self.params.items()}
                best_epoch = epoch
                stale = 0
            else:
                stale += 1
                if stale >= 12:
                    break
        self.params = best
        p = 7 / 37
        baseline = -p * np.log(p) - (1 - p) * np.log(1 - p)
        self.report = NumpyTrainingReport('numpy_mlp_111_32_16_37', len(x_train),
            len(x_val), best_epoch, round(best_loss, 6), round(float(baseline), 6),
            bool(best_loss < baseline))
        return self.report

    def predict(self, history: list[Draw]) -> dict[int, float]:
        if not self.params:
            raise RuntimeError('モデルが未学習です')
        x = np.array([HistoryAnalyzer(history).ml_features()], dtype=np.float64)
        output = self._forward(x)[2][0]
        return {n: float(output[n - 1]) for n in range(1, 38)}