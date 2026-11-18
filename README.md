# TRE-Lottery AI Assistant

ロト7を対象とした**統計解析・深層学習・3AI独立判定**の検証プロジェクト。ユーザー指定のハロ型コックピットUIを参考にしたHTML/CSS/SVGレイアウトを使用します。

> 注意：公平で独立した抽せんなら、1〜37の7数字はどの組み合わせも1等の確率が同じです。データ解析・ニューラルネットワーク・3AI得票は優位な当せん確率を保証しません。

## 公開UI / API

- `GET /` ハロ型HUD（参考レイアウト・API連携実装）
- `GET /api/health` 稼働状態
- `POST /api/predict` `{"count": 5, "samples": 180, "seed":42, "session":null, "judge":"rules"}`
- `POST /api/history/upload` `Content-Type: text/csv` のCSV原文。`session`を返す

**公開URLで履歴CSVが未登録の場合、予測は架空160回分の履歴を使用したデモです。** 画面とAPI双方に表示します。データはユーザーのCSVをセッション単位で保持し、1時間またはサーバー再起動で消去されます。Render無料プランでSQLiteファイル永続化は保証されません。

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

`main` は基盤用です。専用開発ブランチからPRでコードレビューしてから統合する運用を想定します。
RenderのPython Web Service: build `pip install -r requirements.txt`, start `uvicorn app:app --host 0.0.0.0 --port $PORT`。
## 発表用：ローカルMySQL／phpMyAdmin／iPhone

発表時はXAMPPのMySQLを使用します。GitHubにDBパスワードは保存しません。

1. XAMPPのMySQLとApacheを起動し、`http://localhost/phpmyadmin/` を開く。
2. `scripts/setup_local_mysql.sql` をphpMyAdminから実行してDBとテーブルを作る。
3. `tre_lottery_app` を接続元127.0.0.1だけで作成し、`tre_lottery` に必要な権限を与える。
4. `config/local.env.cmd.example` を `config/local.env.cmd` にコピーし、実際のDBパスワードを設定する。
5. `python -m pip install -r requirements.txt` 後、`scripts\\start_local.cmd` で起動する。
6. PCは `http://localhost:8000/`、iPhoneは同じWi-Fiから `http://PCのIPv4:8000/` にアクセスする。
7. `GET /api/health` の `database.status` が `connected` ならDB接続成功。

**MySQL時の処理:** CSV取込→`draw_results`に重複排除して永続保存→予測実行→`prediction_runs`に予測・判定JSONを保存。MySQLが空で20回未満の場合は架空データによるデモモードを明示します。SQLite用CLIもそのまま利用可能。RenderはMySQLを使わず従来のデモモードです。

**起動仕様:** 初期画面では「AIハロ起動」ボタンのみが中央に表示され、押すとメイン画面を公開して「3-AIマルチエージェント・システム、起動。メイン・オレンジ、サブ・グリーン、サブ・ブルー、同期完了」と音声合成します。音声認識にはブラウザの許可・HTTPS制約があります。

手順詳細: [docs/local_xampp_iphone.md](docs/local_xampp_iphone.md)

## ハロ音声の参考動画に基づく調整

提供された約2.03秒のゲーム録画を参考に、3体の耳を左右独立した開閉ハッチへ変更しました。
発話中は**内部の歯車・駆動軸の露出、目の発光、頭部の小さな揺れ**が起こります。

「HARO VOICE LINK」では、日本語音声のピッチ（初期値1.50）、話速（初期値1.25）、短いオリジナル電子音の有無を調整できます。「試聴」で確認し、設定をブラウザ内に保存します。
Web Speech APIの発話開始・語句境界・終了に加え、語句境界イベントが使えないブラウザ用の近似同期もあります。
**参考音源のゲームの声・楽曲・効果音は配布・埋め込みしていません。録画音声を完全複製する仕組みではありません。**
解析値はBGM・効果音を含む混合音源に由来し、単独音声の声紋や正確な基本周波数ではありません。

解析資料：[docs/haro_voice_reference_analysis.md](docs/haro_voice_reference_analysis.md)

## 承認済みハロ最終画像のUIへの反映（2026-11-18）

- ユーザーが承認した**格納庫のハロ3体デザイン画**を `web/assets/haro-approved.webp` としてリポジトリへ登録しています。絵を再作成するのではなく、承認画像をWeb表示します。
- オレンジ（LOGOS）中央最前面、緑（NEMESIS）左後方、紫（CHAOS）右後方。**青ハロは廃止**しました。紫は強気で辛辣な批判役ですが、候補の統計評価ロジック自体は変更していません。
- 承認画像には**上側の耳が開いた状態と下側の閉じた状態**の両方があります。
- 起動後の「耳を閉じる／耳を開く」で上側の表示状態をクロスフェードできます。Web Speech APIで発話中は開状態を優先し、話している個体の目の発光を強調します。
- この開閉は**2状態画像のトランジション**であり、ハッチを関節メッシュとして連続変形する3Dアニメーションではありません。実際の発話音声の波形を測定した厳密な同期でもありません。
- 画像は `/assets/haro-approved.webp` と `/assets/haro-closed-stage.webp` でFastAPIの静的ファイルとして提供します。既存CSV/MySQL/API/予測機能と分離しています。
- 旧ブラウザでも操作できるよう、人物を直接クリックする透明の選択領域と、下部の3AI切替ボタンを用意しています。
- 発表時の実機確認項目は、画像ロード、起動音声、音声停止、3AIの切替、耳の開閉、iPhone表示、予測5通りです。
