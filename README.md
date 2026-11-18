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