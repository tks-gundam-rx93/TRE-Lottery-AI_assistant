"""TRE-Lottery AI Assistant: 公開検証用のFastAPI。

登録済みのMySQL履歴、または同梱・取込CSVから予測する。
サーバーがみずほ銀行を自動スクレイピングする機能は含まない。
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
import logging
import hmac
from pathlib import Path
import tempfile
import threading
import time
import uuid
from typing import Any, Literal

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
from lottery_ai.additional_games import (
    AdditionalGameArchive, AdditionalGameRepository, GameCode, Loto6Draw, Numbers4Draw,
    generate_candidates,
)


class HistoryRequest(BaseModel):
    game: Literal["LOTO7", "LOTO6", "NUMBERS4"] = "LOTO7"
    session: str | None = None


class PredictRequest(HistoryRequest):
    count: int = Field(default=5, ge=1, le=10)
    samples: int = Field(default=180, ge=30, le=1000)
    seed: int = Field(default=42, ge=0, le=1_000_000)
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
        # 公開Render環境ではLOTTERY_DB_BACKEND=mysqlでTiDB Cloudへ接続する。
        # DBの資格情報はブラウザへ一切送信しない。
        self.mysql = (MySqlDrawRepository(MySqlSettings.from_env())
                      if os.getenv('LOTTERY_DB_BACKEND', 'memory').lower() == 'mysql' else None)

    def history(self, session: str | None) -> tuple[list[Draw], str]:
        if self.mysql is not None:
            try:
                draws = self.mysql.all()
            except Exception as exc:
                raise HTTPException(
                    status_code=503,
                    detail='クラウドMySQLに接続できません。TiDB CloudとRender環境変数を確認してください'
                ) from exc
            if not draws:
                raise HTTPException(status_code=409, detail='MySQLにLOTO7の履歴が登録されていません')
            return draws, 'MYSQL'
        if session:
            history = self.sessions.get(session)
            if history is None:
                raise HTTPException(status_code=404, detail='セッションの有効期限が切れました。CSVを再登録してください')
            return history, 'UPLOADED_CSV'
        return CsvDrawLoader().load(Loto7HistoryBootstrap.FILE), 'BUNDLED_CSV'

    def additional_history(self, game: GameCode) -> tuple[list[Loto6Draw] | list[Numbers4Draw], str]:
        if self.mysql is not None:
            try:
                draws = AdditionalGameRepository(self.mysql).all(game)
            except Exception as exc:
                raise HTTPException(status_code=503, detail='クラウドMySQLから履歴を取得できません') from exc
            if not draws:
                raise HTTPException(status_code=409, detail=f'MySQLに{game}の履歴が登録されていません')
            return draws, 'MYSQL'
        return AdditionalGameArchive().load(game), 'BUNDLED_CSV'

    @staticmethod
    def frequency_counts(
        game: str, history: list[Draw] | list[Loto6Draw] | list[Numbers4Draw],
    ) -> list[Counter[int]]:
        if game == 'NUMBERS4':
            return [Counter(int(draw.winning_number[i]) for draw in history) for i in range(4)]
        return [Counter(number for draw in history for number in draw.numbers)]

    @staticmethod
    def frequency_summary(game: str, counts: list[Counter[int]]) -> list[list[tuple[str, int]]]:
        width = 1 if game == 'NUMBERS4' else 2
        return [[(str(number).zfill(width), count) for number, count in group.most_common(5)]
                for group in counts]

    @staticmethod
    def train_model(game: str, history: list[Draw] | list[Loto6Draw] | list[Numbers4Draw],
                    seed: int = 42) -> NumpyDeepForecaster:
        if len(history) < 80:
            raise HTTPException(status_code=409, detail=f'{game}のディープラーニングには80回以上の履歴が必要です')
        model = NumpyDeepForecaster(seed=seed, epochs=45)
        if game == 'LOTO7':
            model.fit(history)
        else:
            model.fit_additional(game, history)
        return model

    def inspect_history(self, req: HistoryRequest, *, train: bool) -> dict[str, Any]:
        history, source = (self.history(req.session) if req.game == 'LOTO7'
                           else self.additional_history(req.game))
        result = {
            'game': req.game, 'mode': source, 'history_count': len(history),
            'first_draw': history[0].draw_no, 'last_draw': history[-1].draw_no,
        }
        if train:
            return dict(result, training=asdict(self.train_model(req.game, history).report))

        counts = self.frequency_counts(req.game, history)
        return dict(result, frequencies=self.frequency_summary(req.game, counts))

    def predict(self, req: PredictRequest) -> dict[str, Any]:
        history, source = (self.history(req.session) if req.game == 'LOTO7'
                           else self.additional_history(req.game))
        counts = self.frequency_counts(req.game, history)
        analysis = self.frequency_summary(req.game, counts)
        model = self.train_model(req.game, history, req.seed)
        result = {
            'game': req.game, 'mode': source, 'history_count': len(history),
            'first_draw': history[0].draw_no, 'last_draw': history[-1].draw_no,
            'target_draw': history[-1].draw_no + 1,
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'frequencies': analysis, 'training': asdict(model.report),
            'warning': '候補は統計・学習に基づきます。公平な抽せんでは各組み合わせの確率は等しくなります。',
        }
        if req.game == 'LOTO7':
            result.update(self.rank_loto7(req, history, model))
        else:
            scores = model.predict_additional(req.game, history)
            picks = generate_candidates(req.game, counts, scores, req.count, req.seed)
            result.update(candidates=[
                {'candidate_id': f'SET-{i:02d}', 'numbers': numbers, 'method': '出現頻度＋MLP'}
                for i, numbers in enumerate(picks, 1)
            ], debate=None)
        if self.mysql is not None and req.game == 'LOTO7':
            try:
                result['prediction_run_id'] = self.mysql.save_prediction(result)
            except Exception as exc:
                raise HTTPException(
                    status_code=503,
                    detail='予測履歴をMySQLに保存できませんでした。DBを確認してください'
                ) from exc
        return result

    def rank_loto7(self, req: PredictRequest, history: list[Draw],
                   model: NumpyDeepForecaster) -> dict[str, Any]:
        analyzer = HistoryAnalyzer(history)
        strategies = [FrequencyStrategy(), GapPairStrategy(), MonteCarloStrategy(),
                      DeepLearningStrategy(model.predict(history))]
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
        return {
            'candidates': [dict(c.as_dict(), votes=votes[c.candidate_id]) for c in picked],
            'all_candidates': [c.as_dict() for c in candidates], 'debate': debate.as_dict(),
        }


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



@app.on_event("startup")
def import_additional_game_history_on_startup() -> None:
    """LOTO6とNUMBERS4の検証済み履歴を、明示的な起動フラグがある場合だけDBへ投入。

    別テーブルを利用するためLOTO7履歴や予測結果に一切変更を加えない。
    例外メッセージは認証情報が含まれる可能性があるため公開しない。
    """
    if os.getenv("LOTTERY_BOOTSTRAP_ADDITIONAL_GAMES", "").strip() != "1":
        return
    if service.mysql is None:
        logging.getLogger("tre_lottery.additional_import").warning(
            "additional games import skipped: MySQL disabled"
        )
        return
    reader = AdditionalGameArchive()
    repository = AdditionalGameRepository(service.mysql)
    for game in ("LOTO6", "NUMBERS4"):
        try:
            draws = reader.load(game)
            result = repository.import_draws(game, draws)
            logging.getLogger("tre_lottery.additional_import").info(
                "additional game import OK: game=%s rows=%d inserted=%d skipped=%d total=%d",
                game, result["rows_in_file"], result["inserted"],
                result["skipped"], result["db_rows"],
            )
        except Exception as exc:
            logging.getLogger("tre_lottery.additional_import").error(
                "additional game import failed: game=%s error_type=%s",
                game, type(exc).__name__,
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
    history_mode = ('MYSQL' if db_state == 'connected' and summary['count'] >= 80
                    else 'MYSQL_WAITING' if service.mysql is not None else 'BUNDLED_CSV')
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


@app.get('/api/history/status/{game}')
def additional_history_status(game: str):
    """宝くじ種類ごとのDB履歴件数。LOTO7の既存APIは互換性維持。"""
    game = game.upper()
    if game == "LOTO7":
        return history_status()
    if game not in ("LOTO6", "NUMBERS4"):
        raise HTTPException(status_code=404, detail="未対応の宝くじ種類です")
    if service.mysql is None:
        return {'game': game, 'mode': 'memory', 'persistent': False, 'draw_count': 0,
                'prediction_available': True}
    try:
        stats = AdditionalGameRepository(service.mysql).stats(game)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="クラウドMySQLへの接続・照会に失敗しました") from exc
    return {
        'game': game,
        'mode': 'MYSQL',
        'persistent': True,
        'draw_count': stats['count'],
        'first_draw': stats['first_draw'],
        'last_draw': stats['last_draw'],
        'missing_count': stats['missing_count'],
        'dates_available': stats['dates_available'],
        'prediction_available': stats['count'] >= 80,
    }


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
        raise HTTPException(status_code=422, detail='セッションに登録するには20回以上の履歴が必要です')
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


@app.post('/api/analysis')
def analyze_history(request: HistoryRequest):
    return service.inspect_history(request, train=False)


@app.post('/api/train')
def train_on_history(request: HistoryRequest):
    return service.inspect_history(request, train=True)
