# TRE-Lottery AI Assistant

ロト7を対象とした**統計解析・深層学習・3AI独立判定**の検証プロジェクト。ユーザー指定のハロ型コックピットUIを参考にしたHTML/CSS/SVGレイアウトを使用します。

> 注意：公平で独立した抽せんなら、1〜37の7数字はどの組み合わせも1等の確率が同じです。データ解析・ニューラルネットワーク・3AI得票は優位な当せん確率を保証しません。

## 公開UI / API

- `GET /` ハロ型HUD（参考レイアウト・API連携実装）
- `GET /api/health` 稼働状態
- `POST /api/predict` `{"count": 5, "samples": 180, "seed":42, "session":null, "judge":"rules"}`
- `POST /api/history/upload` `Content-Type: text/csv` のCSV原文。`session`を返す

**DB未接続のデモモードでは架空160回分の履歴を使用します。クラウドMySQLが有効な場合は実際のCSV登録が必要です。** 画面とAPI双方に表示します。データはユーザーのCSVをセッション単位で保持し、1時間またはサーバー再起動で消去されます。Render無料プランでSQLiteファイル永続化は保証されません。

## ローカル実行

```bash
python -m pip install -r requirements.txt
python -m pip install -e .
uvicorn app:app --reload
python -m pytest -q
```

### CSVフォーマット例

```csv
draw_no,draw_date,n1,n2,n3,n4,n5,n6,n7,b1,b2
1,2013-04-05,1,2,3,4,5,6,7,8,9
```

`draw_no`, `draw_date`, `n1`〜`n7` が必須です。ボーナス数字は任意です。対応文字コードは UTF-8 / CP932。公式みずほCSVの構造は未確認のため、未確認形式への自動マッピングをしていません。

### CLI（SQLite保存・バックテスト・任意PyTorch学習）

```bash
python -m lottery_ai --csv history_loto7.csv --db data/lottery.db --samples 500 --top 5
python -m lottery_ai --db data/lottery.db --backtest 20
python -m pip install -e '.[dl]'
python -m lottery_ai --db data/lottery.db --with-dl
```

## 判定AIについて

- LOGOS: 頻度分析、統計的根拠とデータ品質を重視
- CHAOS: 広い探索範囲と多様性を重視
- NEMESIS: 極端な組み合わせや過学習を批判
- 第1ラウンド: 他者の意見を隠して独立投票
- 第2ラウンド: 他のAIの第1ラウンド意見を渡し再判定

**初期構成は3つのルールベース判定者（LLMではない）です。** `LOTTERY_LLM_API_KEY`, `LOTTERY_LLM_BASE_URL`, `LOTTERY_LLM_MODEL`をサーバーに設定して `judge=llm` を指定した場合のみ、実際のLLMによる3AI独立判定と二段階討論を使用します。APIキーはクライアントに渡しません。

## DLについて

公開APIはNumPy製2隠れ層MLP（111→32→16→37）を使用して実際に学習・ホールドアウト検証します。PyTorch版を `lottery_ai/deep.py` に別途備え、CLI `--with-dl` で使用できます。未来の結果を学習入力に混ぜず、最後20%で検証し、一様ランダム基準BCEと比較します。結果がランダム基準より悪い場合もそのまま報告します。

## 利用条件

公式Webの自動取得・アクセス制限迂回は実装していません。CSVを手動入手し、利用条件を確認してから取り込んでください。UIにはロト6・NUMBERS4の項目も残していますが、現段階では**ロト7のみ**を扱います。出典のある実データがない状態で実当せん履歴を捏造しません。

## GitHub / Render

`main` は方式1の高速GIF UIまでマージ済みです。追加改修は開発ブランチからPRでレビューして統合する運用です。
RenderのPython Web Service: build `pip install -r requirements.txt`, start `uvicorn app:app --host 0.0.0.0 --port $PORT`。
## クラウドMySQLに当せん履歴を永続保存（2026-11-20）

ローカルXAMPP / `localhost/phpmyadmin` への接続は、通常運用では使用しません。
**RenderのプライベートMySQL、または外部のクラウドMySQL**へFastAPIから接続する構成です。

- 接続情報はRender環境変数の `LOTTERY_MYSQL_URL` または `LOTTERY_DB_HOST` / `LOTTERY_DB_USER` / `LOTTERY_DB_PASSWORD` 等に設定（GitHubには含めない）
- `LOTTERY_DB_BACKEND=mysql` でMySQLを有効化。外部接続はSSL/TLS検証を既定で適用
- `LOTTERY_ADMIN_TOKEN` を使い、CSVからの永続DB登録を管理者に限定
- Webの「DRAW HISTORY / CSV IMPORT」から初回全履歴／追加回を登録
- `GET /api/health` と `GET /api/history/status` で登録件数・最新回・欠落回数を確認
- MySQLでは20回未満のデータしかなければ**架空デモに自動で切替えない**
- 予測・3AI判定の結果を `prediction_runs` に保存

CLIによるCSV初回取込と差分更新：

```sh
python -m lottery_ai.cloud_import --csv loto7_history.csv --dry-run
python -m lottery_ai.cloud_import --csv loto7_history.csv
```

**重要:** TiDB Cloud StarterのDBは別サービスで作成済みです。資格情報はRender環境変数にのみ保存します。第1〜703回の検証済みCSVをリポジトリに含め、明示的なBootstrap有効化で初回登録します。みずほ銀行の自動取得は接続制限・利用条件の確認が必要なため、未実装です。

手順詳細：[docs/cloud_mysql_history_import.md](docs/cloud_mysql_history_import.md)

## LOTO6 / NUMBERS4の過去データ保存（2026-11-20）

ユーザー提供のCP932 CSVを検証して、LOTO7と独立したテーブルへ取り込む機能を追加。

| 種類 | 収録回 | DBテーブル |
|---|---|---|
| LOTO6 | 第1～2156回（2,156件） | `loto6_draw_results` |
| NUMBERS4 | 第1～6436回（6,436件） | `numbers4_draw_results` |

- LOTO6第2134回の元CSV誤記（本数字`29`→公表番号`19`）を訂正。
- NUMBERS4は`0097`等の先頭0を保持した文字列`CHAR(4)`で保存。
- CSVには抽せん日がないため、DBの`draw_date`はNULL。架空の日付を補わない。
- **NUMBERS4は2024-03-29の第6436回までの部分履歴**で、2026-11-19時点の第7118回まで682回が未収録。
- 登録用ファイルは`data/*.csv.gz`として保存し、SHA-256を照合。重複回号の再登録を防ぎ、既存値との不一致はロールバックする。
- 初回のみRenderの`LOTTERY_BOOTSTRAP_ADDITIONAL_GAMES=1`を設定して取込。成功後は`0`に戻す。
- `GET /api/history/status/LOTO6`、`GET /api/history/status/NUMBERS4`で履歴件数を確認可能。
- **予測・深層学習・3AI判定はまだLOTO7のみ**。2種類の予測対応は別タスク。

詳細：[docs/loto6_numbers4_import.md](docs/loto6_numbers4_import.md)

## LOTO7実履歴の初回一括登録（2026-11-20）

ユーザー提供の `loto7.csv`（CP932）から、第1～703回の本数字・ボーナス数字を検証し、`data/loto7_history_001_703.csv`（UTF-8）として正規化しました。

- ファイル内の回号は連続・重複なし。日付範囲：2013-04-05～2026-11-13
- 第483回の元CSV日付が2022-08-13（土）だったため、楽天銀行の公表結果を確認して2022-08-12（金）に訂正
- **Render環境変数 `LOTTERY_BOOTSTRAP_CSV=1` を設定した場合のみ**、起動時に `tre_lottery.draw_results` へ不足分を一括登録する
- 登録はトランザクションで原子的に処理し、再デプロイで二重登録しない
- 本番DBの既存結果と相違がある場合は登録を中断する
- `GET /api/history/status` で登録後の件数・最終回号・欠落回数を確認できる
- 元CSVの賞金額・当せん口数は予測履歴テーブルへは登録しない
- 取込元の703件すべてについて外部公式結果との個別照合を完了したわけではない

来週以降の新規抽せん結果は、管理者認証付きのCSV取込で追加できます。

出典・データ訂正・検査内容: [docs/loto7_history_import_001_703.md](docs/loto7_history_import_001_703.md)

## ハロ音声の参考動画に基づく調整

提供された約2.03秒のゲーム録画を参考に、3体の耳を左右独立した開閉ハッチへ変更しました。
発話中は**内部の歯車・駆動軸の露出、目の発光、頭部の小さな揺れ**が起こります。

「HARO VOICE LINK」では、日本語音声のピッチ（初期値1.50）、話速（初期値1.25）、短いオリジナル電子音の有無を調整できます。「試聴」で確認し、設定をブラウザ内に保存します。
Web Speech APIの発話開始・語句境界・終了に加え、語句境界イベントが使えないブラウザ用の近似同期もあります。
**参考音源のゲームの声・楽曲・効果音は配布・埋め込みしていません。録画音声を完全複製する仕組みではありません。**
解析値はBGM・効果音を含む混合音源に由来し、単独音声の声紋や正確な基本周波数ではありません。

解析資料：[docs/haro_voice_reference_analysis.md](docs/haro_voice_reference_analysis.md)

## ハロ 方式1：GIF再生UI（比較用ブランチ）

この分岐は方式2（SVG）とは独立した**GIF表示方式の比較用実装**です。
GIFはユーザーが承認した3体のハロの8フレーム原画です。UIのキャラクター部分はSVGで再描画していません。

- 緑（NEMESIS）左、中央前面オレンジ（LOGOS）、紫（CHAOS）右の3体を同時表示
- 通常時は`web/assets/haro-idle.webp`（元GIFの先頭フレーム）を表示
- 発話時は**初期設定で高速GIF** `web/assets/haro-speaking-fast.gif` を再生。開く動作の最初の4フレームは180ms→90msで約2倍速、全体は1周1.02秒
- 画面の「耳の速度」で、元GIF `web/assets/haro-speaking.gif`（1周1.44秒）との切替が可能
- 音声終了・停止後は閉耳の静止画へ復帰。試聴・マイク起動・予測・CSV/MySQLには変更なし
- ハロ3体の選択操作は透明なクリック領域で維持し、話者名とチャットを切替
- **方式1の制約**：3体が1枚のGIFに含まれているため、発話時の耳・目は**3体同時**に動く。話す1体だけの耳を動かすには方式2が必要
- 本分岐は新規PRで元の開発ブランチと比較可能です。`main`には自動マージしません

詳細：[docs/haro_v1_gif_playback.md](docs/haro_v1_gif_playback.md)

## PWA（ホーム画面から起動）

`main` を基準に、iPhone・Android・PCのホーム画面から起動できるPWAを追加するブランチがあります。
アプリ名は **TRE Lottery**。ハロ3体のアイコン、スタンドアロン表示、静的画面のオフライン表示を提供します。
音声・統計解析・MySQL・APIの既存機能は維持し、予測データをService Workerでキャッシュしません。

**iPhoneの登録方法：** SafariでPWAのHTTPS公開URLを開き、「共有」→「ホーム画面に追加」→（表示される場合）「Webアプリとして開く」をオン→「追加」。
iOSのホーム画面への配置は本人が端末上で行う操作であり、サーバー側から自動実行はできません。

手順・仕様： [docs/pwa_install_iphone.md](docs/pwa_install_iphone.md)
