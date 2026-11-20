"""TRE-Lottery AI Assistant: 公開検証用のFastAPI。

公開サイトはデモデータか、利用者が送信したCSVのセッションデータを使用する。
サーバーがみずほ銀行を自動スクレイピングする機能は含まない。
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
import logging
import hmac
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
from lottery_ai.cloud_import import Loto7HistoryImporter
from lottery_ai.bootstrap_history import Loto7HistoryBootstrap


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
        # 公開Render環境ではLOTTERY_DB_BACKEND=mysqlでTiDB Cloudへ接続する。
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
                    detail='クラウドMySQLに接続できません。TiDB CloudとRender環境変数を確認してください'
                ) from exc
            if len(draws) < 20:
                # 本番MySQLモードで架空の結果を混在させない。
                raise HTTPException(
                    status_code=409,
                    detail=f'ロト7履歴が{len(draws)}件です。20回以上の実データCSVをDBに取り込んでください'
                )
            return draws, 'MYSQL'
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

# 方式1の固定画像と8フレームGIFはFastAPIで静的配信する。
# この分岐ではMySQL・予測処理・音声認識エンドポイントを変更しない。
app.mount('/assets', StaticFiles(directory=Path(__file__).parent / 'web' / 'assets'), name='haro-assets')


@app.on_event("startup")
def import_verified_loto7_history_on_startup() -> None:
    """管理者が明示的に有効化したときのみ、第1～703回を初回投入する。

    起動処理にDB資格情報・CSVの各行を書き出さない。既存回の矛盾や
    接続失敗でも公開UIは停止させず、/api/history/statusで実態を確認できる。
    """
    if os.getenv("LOTTERY_BOOTSTRAP_CSV", "").strip() != "1":
        return
    if service.mysql is None:
        logging.getLogger("tre_lottery.import").warning(
            "history bootstrap skipped: database mode is not enabled"
        )
        return
    try:
        result = Loto7HistoryBootstrap(service.mysql).run()
        logging.getLogger("tre_lottery.import").info(
            "history bootstrap completed: csv_rows=%d inserted=%d skipped=%d db_rows=%d",
            result["csv_rows"], result["inserted"],
            result["skipped"], result["db_rows"],
        )
    except Exception as exc:
        # 例外メッセージには接続先・資格情報が入る場合があるため公開しない。
        logging.getLogger("tre_lottery.import").error(
            "history bootstrap failed: error_type=%s", type(exc).__name__
        )



@app.get('/')
def home():
    return FileResponse(Path(__file__).parent / 'web' / 'index.html', media_type='text/html')


def _safe_db_error_code(exc: Exception) -> str:
    """DB資格情報や接続先を露出させず、エラーの種類だけを分類する。"""
    message = str(exc).lower()
    if "certificate verify failed" in message or "certificate_verify_failed" in message:
        return "tls_certificate"
    if "ssl" in message or "tls" in message:
        return "tls_handshake"
    if "access denied" in message or "authentication" in message:
        return "authentication"
    if "unknown database" in message:
        return "database_missing"
    if "name or service not known" in message or "getaddrinfo" in message:
        return "dns"
    if "timed out" in message or "timeout" in message:
        return "timeout"
    args = getattr(exc, 'args', ())
    code = args[0] if args and isinstance(args[0], int) else None
    if code == 1045:
        return "authentication"
    if code == 1049:
        return "database_missing"
    if code in (2003, 2005):
        return "network"
    if code in (1044, 1142):
        return "permission"
    return "driver_or_query"


@app.get('/api/health')
def health():
    """MySQLの実接続状態と保存済み回号を公開。接続情報や秘密は返さない。"""
    db_state = 'disabled'
    db_error_type = None
    db_error_code = None
    summary = {'count': 0, 'first_draw': None, 'last_draw': None, 'last_date': None, 'missing_count': 0}
    if service.mysql is not None:
        try:
            summary = service.mysql.stats() if hasattr(service.mysql, 'stats') else dict(
                count=len(service.mysql.all()), first_draw=None, last_draw=None,
                last_date=None, missing_count=0)
            db_state = 'connected'
        except Exception as exc:
            db_state = 'unavailable'
            db_error_type = type(exc).__name__
            db_error_code = _safe_db_error_code(exc)
    history_mode = ('MYSQL' if db_state == 'connected' and summary['count'] >= 20
                    else 'MYSQL_WAITING' if service.mysql is not None else 'SYNTHETIC_DEMO')
    return {'status': 'ok', 'game': 'LOTO7', 'history_mode': history_mode,
            'database': {'backend': 'mysql' if service.mysql is not None else 'memory',
                         'status': db_state, 'draw_count': summary['count'],
                         'first_draw': summary['first_draw'], 'last_draw': summary['last_draw'],
                         'last_date': summary['last_date'],
                         'missing_count': summary['missing_count'],
                         'error_type': db_error_type, 'error_code': db_error_code},
            'learning': 'numpy_mlp', 'three_agents': 'rules; llm optional',
            'upload_storage': 'MySQL persistent' if service.mysql is not None
                              else 'one-hour in-memory session'}


@app.get('/api/history/status')
def history_status():
    """登録済みの抽せん履歴件数・初回/最新回を確認する。管理操作は含まない。"""
    if service.mysql is None:
        return {'mode': 'memory', 'persistent': False, 'draw_count': 0}
    try:
        stats = (service.mysql.stats() if hasattr(service.mysql, 'stats')
                 else {'count': len(service.mysql.all())})
    except Exception as exc:
        raise HTTPException(status_code=503, detail='MySQLへの接続に失敗しました') from exc
    return {'mode': 'MYSQL', 'persistent': True, 'draw_count': stats['count'],
            'first_draw': stats.get('first_draw'), 'last_draw': stats.get('last_draw'),
            'last_date': stats.get('last_date'), 'missing_count': stats.get('missing_count', 0)}


def _require_import_admin(request: Request) -> None:
    """クラウドMySQLへ永続書込するCSV取込を管理者認証で保護する。"""
    expected = os.getenv('LOTTERY_ADMIN_TOKEN', '')
    if not expected:
        raise HTTPException(
            status_code=503,
            detail='クラウド取込が未設定です。管理者トークンをRenderの環境変数へ設定してください'
        )
    provided = request.headers.get('authorization', '')
    if not provided.startswith('Bearer '):
        raise HTTPException(status_code=401, detail='管理者トークンが必要です')
    if not hmac.compare_digest(provided[7:].encode(), expected.encode()):
        raise HTTPException(status_code=403, detail='管理者トークンが一致しません')

@app.post('/api/history/upload')
async def upload_csv(request: Request):
    """CSVから当せん履歴を登録。クラウドMySQLへの書込時は管理者認証が必須。"""
    if service.mysql is not None:
        _require_import_admin(request)
    payload = await request.body()
    if not payload or len(payload) > 3_000_000:
        raise HTTPException(status_code=413, detail='CSVは3MB以下にしてください')
    with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as temp:
        temp.write(payload)
        filepath = temp.name
    try:
        # 本番MySQLのみ抽せん日の実在性を検証。デモの既存CSV互換性は維持する。
        draws = (Loto7HistoryImporter(service.mysql).load_and_validate(filepath)
                 if service.mysql is not None else CsvDrawLoader().load(filepath))
    except (ValueError, UnicodeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        Path(filepath).unlink(missing_ok=True)
    if service.mysql is None and len(draws) < 20:
        raise HTTPException(status_code=422, detail='デモ予測には20回以上の履歴が必要です')
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