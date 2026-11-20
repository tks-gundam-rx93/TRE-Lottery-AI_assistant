"""ロト7のドメイン、CSV/SQLite、統計特徴量と3方式の候補抽出。"""
from __future__ import annotations

import csv
import json
import math
import random
import sqlite3
import statistics
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

MAX_NUMBER = 37
PICKS = 7


@dataclass(frozen=True)
class Draw:
    """抽せん1回分。番号は昇順・重複なしで保持する。"""
    draw_no: int
    draw_date: str
    numbers: tuple[int, ...]
    bonus: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if self.draw_no < 1 or len(self.numbers) != PICKS:
            raise ValueError("回号は1以上、本数字は7個必要です")
        if tuple(sorted(set(self.numbers))) != self.numbers or not all(1 <= n <= 37 for n in self.numbers):
            raise ValueError("本数字は1〜37の異なる7個を昇順で指定してください")
        if self.bonus and (len(self.bonus) != 2 or len(set(self.bonus)) != 2 or
                           not all(1 <= n <= 37 for n in self.bonus) or
                           set(self.bonus) & set(self.numbers)):
            raise ValueError("ボーナス数字は本数字と重ならない2個です")


@dataclass(frozen=True)
class Candidate:
    """予測候補。scoreは方式内部の相対評価値で当せん確率ではない。"""
    candidate_id: str
    method: str
    numbers: tuple[int, ...]
    score: float
    rationale: str

    def as_dict(self) -> dict:
        return {"id": self.candidate_id, "method": self.method,
                "numbers": list(self.numbers), "score": round(self.score, 5),
                "rationale": self.rationale}


class CsvDrawLoader:
    """指定スキーマのCSVを安全に読み込む。公式CSVの構造は未確認。"""
    _ALIASES = {"draw_no": ["draw_no", "round", "回号", "抽せん回"],
                "draw_date": ["draw_date", "date", "抽せん日", "抽選日"]}

    @staticmethod
    def _key(name: str) -> str:
        return name.strip().replace(" ", "").replace("_", "").lower().translate(
            str.maketrans("１２３４５６７８９０", "1234567890"))

    @classmethod
    def _column(cls, header: list[str], choices: list[str]) -> str:
        lookup = {cls._key(h): h for h in header}
        for choice in choices:
            if cls._key(choice) in lookup:
                return lookup[cls._key(choice)]
        raise ValueError(f"CSVに必要な列がありません: {choices[0]}")

    def load(self, filename: str | Path) -> list[Draw]:
        raw = Path(filename).read_bytes()
        text = None
        for encoding in ("utf-8-sig", "cp932"):
            try:
                text = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                pass
        if text is None:
            raise ValueError("CSVの文字コードがutf-8-sig/cp932ではありません")
        rows = csv.DictReader(text.splitlines())
        if not rows.fieldnames:
            raise ValueError("空のCSVです")
        header = rows.fieldnames
        draw_key = self._column(header, self._ALIASES["draw_no"])
        date_key = self._column(header, self._ALIASES["draw_date"])
        nkeys = [self._column(header, [f"n{i}", f"number{i}", f"本数字{i}"]) for i in range(1, 8)]
        # ボーナス数字がないCSVも許可する（当せん判定には使えない）。
        try:
            bkeys = [self._column(header, [f"b{i}", f"bonus{i}", f"ボーナス数字{i}"]) for i in (1, 2)]
        except ValueError:
            bkeys = []
        result: list[Draw] = []
        seen: set[int] = set()
        for line_no, row in enumerate(rows, start=2):
            try:
                no = int(row[draw_key])
                nums = tuple(sorted(int(row[k]) for k in nkeys))
                bonus = tuple(sorted(int(row[k]) for k in bkeys)) if bkeys else ()
                item = Draw(no, str(row[date_key]).strip(), nums, bonus)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"CSV {line_no}行目: {exc}") from exc
            if no in seen:
                raise ValueError(f"CSV内に回号{no}の重複があります")
            seen.add(no)
            result.append(item)
        if not result:
            raise ValueError("抽せん結果の行がありません")
        return sorted(result, key=lambda d: d.draw_no)


class SqliteDrawRepository:
    """不一致を黙って上書きしないSQLiteリポジトリ。"""

    def __init__(self, filename: str | Path):
        self.filename = Path(filename)
        self.filename.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.filename) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS draw_results (
                lottery_type TEXT NOT NULL, draw_no INTEGER NOT NULL,
                draw_date TEXT NOT NULL, numbers_json TEXT NOT NULL,
                bonus_json TEXT NOT NULL, source TEXT NOT NULL,
                PRIMARY KEY (lottery_type, draw_no))""")

    def upsert(self, draws: list[Draw], source: str = "CSV") -> int:
        inserted = 0
        with sqlite3.connect(self.filename) as db:
            for draw in draws:
                existing = db.execute(
                    "SELECT draw_date, numbers_json, bonus_json FROM draw_results "
                    "WHERE lottery_type='LOTO7' AND draw_no=?", (draw.draw_no,)).fetchone()
                values = (draw.draw_date, json.dumps(draw.numbers), json.dumps(draw.bonus))
                if existing:
                    if existing != values:
                        raise ValueError(f"DBの第{draw.draw_no}回とCSVが矛盾しています")
                    continue
                db.execute("INSERT INTO draw_results VALUES (?,?,?,?,?,?)",
                           ("LOTO7", draw.draw_no, *values, source))
                inserted += 1
        return inserted

    def all(self) -> list[Draw]:
        with sqlite3.connect(self.filename) as db:
            rows = db.execute("SELECT draw_no,draw_date,numbers_json,bonus_json "
                              "FROM draw_results WHERE lottery_type='LOTO7' ORDER BY draw_no").fetchall()
        return [Draw(int(n), str(dt), tuple(json.loads(ns)), tuple(json.loads(bs)))
                for n, dt, ns, bs in rows]


class HistoryAnalyzer:
    """対象回より前の履歴だけで特徴を計算する。未来情報は入力しない。"""

    def __init__(self, history: list[Draw]):
        if not history:
            raise ValueError("過去データがありません")
        self.history = sorted(history, key=lambda d: d.draw_no)
        if len({d.draw_no for d in self.history}) != len(self.history):
            raise ValueError("回号が重複しています")

    def frequency(self, window: int) -> dict[int, float]:
        history = self.history[-window:]
        counts = Counter(n for draw in history for n in draw.numbers)
        # ラプラス平滑化。分母は7回分の出現総数に対応する。
        return {n: (counts[n] + 1) / (PICKS * len(history) + MAX_NUMBER)
                for n in range(1, MAX_NUMBER + 1)}

    def gaps(self) -> dict[int, int]:
        gaps = {n: len(self.history) for n in range(1, MAX_NUMBER + 1)}
        for offset, draw in enumerate(reversed(self.history)):
            for n in draw.numbers:
                if gaps[n] == len(self.history):
                    gaps[n] = offset
        return gaps

    def pair_frequencies(self) -> dict[tuple[int, int], float]:
        counts = Counter(pair for draw in self.history for pair in combinations(draw.numbers, 2))
        return {pair: (count + 1) / (len(self.history) + 1)
                for pair, count in counts.items()}

    @staticmethod
    def shape(numbers: tuple[int, ...], previous: tuple[int, ...]) -> tuple[int, ...]:
        odds = sum(n % 2 for n in numbers)
        consecutive = sum(b == a + 1 for a, b in zip(numbers, numbers[1:]))
        lower = sum(n <= 18 for n in numbers)
        repeats = len(set(numbers) & set(previous))
        return sum(numbers), odds, consecutive, lower, repeats

    def profile(self) -> tuple[list[float], list[float]]:
        previous = self.history[0].numbers
        shapes = []
        for draw in self.history[1:]:
            shapes.append(self.shape(draw.numbers, previous))
            previous = draw.numbers
        if not shapes:
            shapes = [self.shape(self.history[0].numbers, ())]
        mean = [statistics.mean(x[i] for x in shapes) for i in range(5)]
        stdev = [max(1.0, statistics.pstdev(x[i] for x in shapes)) for i in range(5)]
        return mean, stdev

    def ml_features(self) -> list[float]:
        """37数字×(直近20回率,100回率,未出現間隔)の111次元。"""
        freq20 = self.frequency(20)
        freq100 = self.frequency(100)
        gaps = self.gaps()
        return [v for n in range(1, 38) for v in
                (freq20[n] * 37, freq100[n] * 37, min(gaps[n], 100) / 100)]


def _weighted_sample(rng: random.Random, weights: dict[int, float]) -> tuple[int, ...]:
    available = list(range(1, MAX_NUMBER + 1))
    selection = []
    for _ in range(PICKS):
        picked = rng.choices(available, weights=[max(0.000001, weights[n]) for n in available], k=1)[0]
        selection.append(picked)
        available.remove(picked)
    return tuple(sorted(selection))


class CandidateStrategy(ABC):
    """戦略を差し替え可能にする抽象基底クラス。"""
    name: str

    @abstractmethod
    def _score(self, numbers: tuple[int, ...], analyzer: HistoryAnalyzer) -> float:
        ...

    @abstractmethod
    def _sample(self, rng: random.Random, analyzer: HistoryAnalyzer) -> tuple[int, ...]:
        ...

    def generate(self, analyzer: HistoryAnalyzer, samples: int, top: int, seed: int) -> list[Candidate]:
        if samples < 1 or top < 1:
            raise ValueError("samplesとtopは1以上にしてください")
        rng = random.Random(seed)
        candidates: dict[tuple[int, ...], float] = {}
        for _ in range(samples):
            values = self._sample(rng, analyzer)
            candidates[values] = self._score(values, analyzer)
        ranking = sorted(candidates.items(), key=lambda x: (-x[1], x[0]))[:top]
        return [Candidate(f"{self.name}-{i}", self.name, nums, score,
                          f"{self.name}の特徴量による相対スコア（当せん確率ではありません）")
                for i, (nums, score) in enumerate(ranking, start=1)]


class FrequencyStrategy(CandidateStrategy):
    """A: 20回・100回・全履歴の頻度を混合。"""
    name = "FREQUENCY"

    @staticmethod
    def weights(a: HistoryAnalyzer) -> dict[int, float]:
        w20, w100, wall = a.frequency(20), a.frequency(100), a.frequency(len(a.history))
        return {n: 0.45 * w20[n] + 0.35 * w100[n] + 0.20 * wall[n]
                for n in range(1, MAX_NUMBER + 1)}

    def _sample(self, rng: random.Random, analyzer: HistoryAnalyzer) -> tuple[int, ...]:
        return _weighted_sample(rng, self.weights(analyzer))

    def _score(self, numbers: tuple[int, ...], analyzer: HistoryAnalyzer) -> float:
        weights = self.weights(analyzer)
        return sum(math.log(weights[n]) for n in numbers)


class GapPairStrategy(CandidateStrategy):
    """B: 未出現間隔・直前回±1・共起ペアを組み合わせる。"""
    name = "GAP_PAIR"

    @staticmethod
    def weights(a: HistoryAnalyzer) -> dict[int, float]:
        gaps = a.gaps()
        previous = set(a.history[-1].numbers)
        neighbors = {v for n in previous for v in (n - 1, n + 1) if 1 <= v <= 37}
        return {n: 1.0 + 0.7 * min(gaps[n], 35) / 35 +
                0.20 * (n in previous) + 0.12 * (n in neighbors)
                for n in range(1, MAX_NUMBER + 1)}

    def _sample(self, rng: random.Random, analyzer: HistoryAnalyzer) -> tuple[int, ...]:
        return _weighted_sample(rng, self.weights(analyzer))

    def _score(self, numbers: tuple[int, ...], analyzer: HistoryAnalyzer) -> float:
        weights, pairs = self.weights(analyzer), analyzer.pair_frequencies()
        return sum(weights[n] for n in numbers) + 2.0 * sum(
            pairs.get(pair, 1 / (len(analyzer.history) + 1)) for pair in combinations(numbers, 2))


class MonteCarloStrategy(CandidateStrategy):
    """C: 一様乱数で生成し過去の組み合わせ形状分布で相対評価。"""
    name = "MONTE_CARLO"

    def _sample(self, rng: random.Random, analyzer: HistoryAnalyzer) -> tuple[int, ...]:
        return tuple(sorted(rng.sample(range(1, MAX_NUMBER + 1), PICKS)))

    def _score(self, numbers: tuple[int, ...], analyzer: HistoryAnalyzer) -> float:
        mean, stdev = analyzer.profile()
        shape = analyzer.shape(numbers, analyzer.history[-1].numbers)
        # 分布への適合度。これにより実際の組み合わせの当せん確率は変わらない。
        return -sum(0.5 * ((x - m) / s) ** 2 for x, m, s in zip(shape, mean, stdev))


class DeepLearningStrategy(CandidateStrategy):
    """D: 学習済み予測値に基づく候補抽出（モデルの学習はdeep.py）。"""
    name = "DEEP_LEARNING"

    def __init__(self, probabilities: dict[int, float]):
        self.probabilities = probabilities

    def _sample(self, rng: random.Random, analyzer: HistoryAnalyzer) -> tuple[int, ...]:
        return _weighted_sample(rng, self.probabilities)

    def _score(self, numbers: tuple[int, ...], analyzer: HistoryAnalyzer) -> float:
        return sum(math.log(max(self.probabilities[n], 1e-8)) for n in numbers)