"""独立した3人の判定者と二段階討論。API使用時のみLLMとして動作。"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Protocol

from .core import Candidate, HistoryAnalyzer


@dataclass(frozen=True)
class Verdict:
    agent: str
    round: int
    candidate_id: str
    reason: str
    critique: str = ""


@dataclass(frozen=True)
class DebateResult:
    mode: str
    winner_id: str
    first_round: list[Verdict]
    second_round: list[Verdict]
    votes: dict[str, int]

    def as_dict(self) -> dict:
        return {"mode": self.mode, "winner_id": self.winner_id,
                "first_round": [asdict(v) for v in self.first_round],
                "second_round": [asdict(v) for v in self.second_round],
                "votes": self.votes}


class LLMClient(Protocol):
    """テスト用の偽LLMも注入できるインターフェース。"""
    def select(self, agent: str, instructions: str, candidates: list[Candidate],
               peer_verdicts: list[Verdict]) -> tuple[str, str, str]: ...


class OpenAICompatibleClient:
    """OpenAI互換Chat Completions API。キーとエンドポイントを環境変数で指定。"""
    def __init__(self) -> None:
        self.key = os.environ.get("LOTTERY_LLM_API_KEY", "")
        self.base_url = os.environ.get("LOTTERY_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.model = os.environ.get("LOTTERY_LLM_MODEL", "gpt-4o-mini")
        if not self.key:
            raise ValueError("LLM判定にはLOTTERY_LLM_API_KEYを設定してください")
        if not self.base_url.startswith("https://"):
            raise ValueError("LOTTERY_LLM_BASE_URLにはHTTPSを指定してください")

    def select(self, agent: str, instructions: str, candidates: list[Candidate],
               peer_verdicts: list[Verdict]) -> tuple[str, str, str]:
        request_body = {
            "model": self.model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": instructions +
                 " 必ずJSONオブジェクトだけで返す。キー: candidate_id, reason, critique。"},
                {"role": "user", "content": json.dumps({
                    "role": agent, "candidates": [c.as_dict() for c in candidates],
                    "peer_opinions": [asdict(v) for v in peer_verdicts],
                    "warning": "全候補の公平な1等当せん確率は同じ。説明できない優位性を主張しないこと。",
                }, ensure_ascii=False)},
            ],
        }
        req = urllib.request.Request(self.base_url + "/chat/completions",
            data=json.dumps(request_body, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": "Bearer " + self.key, "Content-Type": "application/json"},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                data = json.load(response)
        except (urllib.error.URLError, ValueError) as exc:
            raise RuntimeError("LLMへの接続または応答の解析に失敗しました") from exc
        content = data["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        parsed = json.loads(content)
        return str(parsed["candidate_id"]), str(parsed["reason"]), str(parsed.get("critique", ""))


class DecisionAgent:
    """同じ候補群を独立に評価する基底クラス。"""
    name: str = "AGENT"
    instructions: str = ""

    def rank(self, candidate: Candidate, analyzer: HistoryAnalyzer) -> float:
        raise NotImplementedError

    def judge(self, candidates: list[Candidate], analyzer: HistoryAnalyzer,
              peers: list[Verdict], round_no: int, client: LLMClient | None) -> Verdict:
        if client is not None:
            selected, reason, critique = client.select(self.name, self.instructions, candidates, peers)
            if selected not in {c.candidate_id for c in candidates}:
                raise ValueError(f"{self.name}: LLMが存在しない候補を選択しました: {selected}")
            return Verdict(self.name, round_no, selected, reason, critique)
        # offlineモードはLLMではなく、説明可能なルール判定。
        ranked = sorted(candidates, key=lambda c: (-self.rank(c, analyzer), c.candidate_id))
        choice = ranked[0]
        challenge = "独立評価" if not peers else "他者の結論を参照したが、担当ルールを変えずに再評価"
        return Verdict(self.name, round_no, choice.candidate_id,
                       f"{self.name}の固定評価基準により{choice.candidate_id}を支持", challenge)


class LogosAgent(DecisionAgent):
    name = "LOGOS"
    instructions = "統計・検証重視。過学習とデータ漏洩を点検し、全候補を比較して一つ選ぶ。"

    def rank(self, c: Candidate, a: HistoryAnalyzer) -> float:
        freq = a.frequency(100)
        # 直近の頻度で比較。ただし的中確率とは解釈しない。
        return sum(freq[n] for n in c.numbers)


class ChaosAgent(DecisionAgent):
    name = "CHAOS"
    instructions = "紫ハロのCHAOS。ドSで辛辣、強気で攻撃的な口調。少数派候補も吟味し、根拠の弱い候補・他AIの主張には容赦なく反論する。ただし利用者個人への侮辱や脅迫はしない。客観的な統計事実と確率の限界は守る。"

    def rank(self, c: Candidate, a: HistoryAnalyzer) -> float:
        # 直前回との重複が少なく、数字帯が広い候補を探索用に選ぶ。
        repeated = len(set(c.numbers) & set(a.history[-1].numbers))
        spread = len({(n - 1) // 10 for n in c.numbers})
        return spread - repeated * 0.6


class NemesisAgent(DecisionAgent):
    name = "NEMESIS"
    instructions = "懐疑・反証重視。見かけの傾向、確率誤認、過学習を指摘して独自に選ぶ。"

    def rank(self, c: Candidate, a: HistoryAnalyzer) -> float:
        # 確率優位性を推定するのではなく、分布の極端さを検出する。
        mean, sd = a.profile()
        shape = a.shape(c.numbers, a.history[-1].numbers)
        return -sum(abs(v - m) / s for v, m, s in zip(shape, mean, sd))


class ThreeAgentDebate:
    """独立1回目→他者の見解を提示した2回目→票数による最終決定。"""

    def __init__(self, client: LLMClient | None = None):
        self.client = client
        self.agents = [LogosAgent(), ChaosAgent(), NemesisAgent()]

    def run(self, candidates: list[Candidate], history: list) -> DebateResult:
        if not candidates:
            raise ValueError("候補がありません")
        analyzer = HistoryAnalyzer(history)
        # 第1段階：他のAIの回答を一切渡さない。
        first = [agent.judge(candidates, analyzer, [], 1, self.client) for agent in self.agents]
        # 第2段階：自分以外の第1段階の意見を受け、再判定する。
        second = [agent.judge(candidates, analyzer,
                              [v for v in first if v.agent != agent.name], 2, self.client)
                  for agent in self.agents]
        votes = {c.candidate_id: sum(v.candidate_id == c.candidate_id for v in second)
                 for c in candidates}
        # 同票時は第1段階の支持数→ID順。得票は当せん確率ではない。
        first_votes = {c.candidate_id: sum(v.candidate_id == c.candidate_id for v in first)
                       for c in candidates}
        winner = sorted(candidates,
                        key=lambda c: (-votes[c.candidate_id], -first_votes[c.candidate_id], c.candidate_id))[0]
        return DebateResult("llm" if self.client else "rules", winner.candidate_id,
                            first, second, votes)