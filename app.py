"""TRE-Lottery AI Assistant: 公開検証用のFastAPI。

公開サイトはデモデータか、利用者が送信したCSVのセッションデータを使用する。
サーバーがみずほ銀行を自動スクレイピングする機能は含まない。
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import random
import tempfile
import threading
import time
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from lottery_ai.agents import OpenAICompatibleClient, ThreeAgentDebate
from lottery_ai.core import (Candidate, CsvDrawLoader, DeepLearningStrategy, Draw,
    FrequencyStrategy, GapPairStrategy, HistoryAnalyzer, MonteCarloStrategy)
from lottery_ai.deep_numpy import NumpyDeepForecaster
from lottery_ai.mysql_repository import MySqlSettings, MySqlDrawRepository


class PredictRequest(BaseModel):
    count: int = Field(default=5, ge=1, le=10)
    samples: int = Field(default=180, ge=30, le=1000)
    seed: int = Field(default=42, ge=0, le=1_000_000)
    session: str | None = None
    judge: str = Field(default='rules', pattern='^(rules|llm)$')


class SessionHistoryStore:
    """公開デモ用の時間限定アップロード履歴。異なる利用者のCSVを混在させない。"""
    TTL_SECONDS = 3600

    def __init__(self):
        self._records: dict[str, tuple[float, list[Draw]]] = {}
        self._lock = threading.Lock()

    def create(self, draws: list[Draw]) -> str:
        token = uuid.uuid4().hex
        with self._lock:
            cutoff = time.time() - self.TTL_SECONDS
            self._records = {k: v for k, v in self._records.items() if v[0] >= cutoff}
            if len(self._records) >= 40:
                raise ValueError('同時セッション上限です。後で再実行してください')
            self._records[token] = (time.time(), draws)
        return token

    def get(self, token: str | None) -> list[Draw] | None:
        if not token:
            return None
        with self._lock:
            stored = self._records.get(token)
            if not stored or stored[0] < time.time() - self.TTL_SECONDS:
                return None
            return stored[1]


class PredictionService:
    """データの由来と各方式の候補を一括管理するアプリケーションサービス。"""
    def __init__(self):
        self.sessions = SessionHistoryStore()
        self.demo = self._make_demo(160)
        # Renderはデモ、ローカル発表は環境変数によってMySQLに切替える。
        # DBの資格情報はブラウザへ一切送信しない。
        self.mysql = (MySqlDrawRepository(MySqlSettings.from_env())
                      if os.getenv('LOTTERY_DB_BACKEND', 'memory').lower() == 'mysql' else None)

    @staticmethod
    def _make_demo(size: int) -> list[Draw]:
        """UI動作確認専用の人工データ。実際の当せん結果ではない。"""
        rng = random.Random(20261118)
        return [Draw(i + 1, f'SYNTHETIC-{i+1}',
            tuple(sorted(rng.sample(range(1, 38), 7))), ()) for i in range(size)]

    def history(self, session: str | None) -> tuple[list[Draw], str]:
        if session:
            history = self.sessions.get(session)
            if history is None:
                raise HTTPException(status_code=404, detail='セッションの有効期限が切れました。CSVを再登録してください')
            return history, 'UPLOADED_CSV'
        if self.mysql is not None:
            try:
                draws = self.mysql.all()
            except Exception as exc:
                raise HTTPException(
                    status_code=503,
                    detail='MySQLに接続できません。XAMPPのMySQL起動と環境変数を確認してください'
                ) from exc
            if len(draws) >= 20:
                return draws, 'MYSQL'
            # 空DBには架空の抽せん結果を保存しない。
        return self.demo, 'SYNTHETIC_DEMO'

    def predict(self, req: PredictRequest) -> dict[str, Any]:
        history, source = self.history(req.session)
        analyzer = HistoryAnalyzer(history)
        strategies = [FrequencyStrategy(), GapPairStrategy(), MonteCarloStrategy()]
        training = None
        if len(history) >= 80:
            model = NumpyDeepForecaster(seed=req.seed, epochs=45)
            training = asdict(model.fit(history))
            strategies.append(DeepLearningStrategy(model.predict(history)))
        candidates: list[Candidate] = []
        for idx, strat in enumerate(strategies):
            candidates.extend(strat.generate(analyzer, req.samples, max(3, req.count),
                                              req.seed + idx))
        if req.judge == 'llm':
            if not os.getenv('LOTTERY_LLM_API_KEY'):
                raise HTTPException(status_code=400, detail='LLM用APIキーがサーバーに設定されていません')
            client = OpenAICompatibleClient()
        else:
            client = None
        debate = ThreeAgentDebate(client).run(candidates, history)
        votes = debate.votes
        # 得票→スコア順で上位を決定。類似数字の重複を除外する。
        ranked = sorted(candidates, key=lambda c: (-votes[c.candidate_id], -c.score, c.candidate_id))
        picked: list[Candidate] = []
        for item in ranked:
            if item.numbers not in [v.numbers for v in picked]:
                picked.append(item)
            if len(picked) == req.count:
                break
        # 同方式だけに偏った場合も候補には方式ラベルを残す。
        result = {
            'game': 'LOTO7', 'mode': source, 'last_draw': history[-1].draw_no if source != 'SYNTHETIC_DEMO' else None,
            'target_draw': history[-1].draw_no + 1 if source != 'SYNTHETIC_DEMO' else None,
            'history_count': len(history), 'generated_at': datetime.now(timezone.utc).isoformat(),
            'candidates': [dict(c.as_dict(), votes=votes[c.candidate_id]) for c in picked],
            'all_candidates': [c.as_dict() for c in candidates], 'debate': debate.as_dict(),
            'training': training, 'warning': (
                '架空の抽せん履歴を使った機能デモです。実際の当せん番号予測ではありません。'
                if source == 'SYNTHETIC_DEMO' else
                '統計・学習・得票スコアは当せん確率ではありません。公平な抽せんなら全組み合わせの確率は等しい。'),
        }
        if self.mysql is not None:
            try:
                result['prediction_run_id'] = self.mysql.save_prediction(result)
            except Exception as exc:
                raise HTTPException(
                    status_code=503,
                    detail='予測履歴をMySQLに保存できませんでした。DBを確認してください'
                ) from exc
        return result


service = PredictionService()
app = FastAPI(title='TRE-Lottery AI Assistant', version='0.1.0')

# 承認済みハロ画像をWeb用静的ファイルとして提供する。APIとは独立した読取専用配信。
app.mount('/assets', StaticFiles(directory=Path(__file__).parent / 'web' / 'assets'), name='assets')


@app.get('/')
def home():
    return FileResponse(Path(__file__).parent / 'web' / 'index.html', media_type='text/html')


@app.get('/api/health')
def health():
    # DBが未起動でもAPIプロセスを止めず、UIに接続状態を返す。
    db_state = 'disabled'
    rows = 0
    if service.mysql is not None:
        try:
            rows = len(service.mysql.all())
            db_state = 'connected'
        except Exception:
            db_state = 'unavailable'
    return {'status': 'ok', 'game': 'LOTO7',
            'history_mode': 'MYSQL' if db_state == 'connected' and rows >= 20 else 'SYNTHETIC_DEMO',
            'database': {'backend': 'mysql' if service.mysql is not None else 'memory',
                         'status': db_state, 'draw_count': rows},
            'learning': 'numpy_mlp', 'three_agents': 'rules; llm optional',
            'upload_storage': 'MySQL persistent' if service.mysql is not None
                              else 'one-hour in-memory session'}


@app.post('/api/history/upload')
async def upload_csv(request: Request):
    """公式CSV直リンクを呼ばず、利用者のCSVを読み込む。最大3MB。"""
    payload = await request.body()
    if not payload or len(payload) > 3_000_000:
        raise HTTPException(status_code=413, detail='CSVは3MB以下にしてください')
    with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as temp:
        temp.write(payload)
        filepath = temp.name
    try:
        draws = CsvDrawLoader().load(filepath)
    except (ValueError, UnicodeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        Path(filepath).unlink(missing_ok=True)
    if len(draws) < 20:
        raise HTTPException(status_code=422, detail='20回以上の履歴が必要です')
    if service.mysql is not None:
        try:
            inserted = service.mysql.upsert(draws, 'CSV')
            total = service.mysql.all()
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail='MySQL登録失敗。XAMPPの起動・接続権限・テーブル設定を確認してください'
            ) from exc
        return {'mode': 'MYSQL', 'session': None, 'count': len(total),
                'inserted': inserted, 'last_draw': total[-1].draw_no,
                'message': f'MySQLに{inserted}件新規登録しました（永続保存）'}
    try:
        session = service.sessions.create(draws)
    except ValueError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    return {'mode': 'UPLOADED_CSV', 'session': session,
            'count': len(draws), 'last_draw': draws[-1].draw_no,
            'message': 'CSV取込完了。このセッション内で予測できます（1時間・再起動まで）。'}


@app.post('/api/predict')
def predict(request: PredictRequest):
    return service.predict(request)