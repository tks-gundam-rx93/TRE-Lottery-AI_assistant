"""CSV入力の厳格な検証と戦略多態性を確認。"""
import random
import pytest
from lottery_ai.core import Draw, HistoryAnalyzer, FrequencyStrategy, GapPairStrategy, MonteCarloStrategy
from lottery_ai.agents import ThreeAgentDebate


def history(n=42):
    r = random.Random(4)
    return [Draw(i+1, f'2026-{i+1}', tuple(sorted(r.sample(range(1,38),7)))) for i in range(n)]


def test_draw_rejects_duplicates():
    with pytest.raises(ValueError):
        Draw(1, 'today', (1,2,3,4,5,6,6))


def test_three_strategies_and_debate():
    h = history()
    a = HistoryAnalyzer(h)
    candidates = [s.generate(a, 40, 2, idx) for idx, s in enumerate(
        [FrequencyStrategy(), GapPairStrategy(), MonteCarloStrategy()])]
    pool = [item for row in candidates for item in row]
    assert all(len(row)==2 for row in candidates)
    outcome = ThreeAgentDebate().run(pool,h)
    assert outcome.winner_id in {c.candidate_id for c in pool}
    assert outcome.mode == 'rules'