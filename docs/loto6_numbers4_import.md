# LOTO6・NUMBERS4 過去データ取込仕様

## 入力元

ユーザー提供ファイルはCP932 CSV。改変せず原本のSHA-256で出典を追跡する。

| ゲーム | 原本の収録範囲 | 原本SHA-256 | 正規化CSV SHA-256 |
|---|---|---|---|
| LOTO6 | 第1回～2156回（2,156件） | `f7b2d1f27278e740e546fb0435f8e6d57d1cb493efeb68299c7979b5a0481ea2` | `0c2a8d542b93b4aa7d02fe1012bf90d22e6dedc472429c156943308ae2ab4733` |
| NUMBERS4 | 第1回～6436回（6,436件） | `b56f3294aecadd42555c1d1a53866a24443719efeda722c5b7e2529415689a46` | `3e275ae052c091cee2848f7e07ddde25a5b36c25f8493cfb9972f1b89b6ae202` |

### LOTO6入力形式

原本先頭行：`抽選回,本数字,,,,,,B数字,ｾｯﾄ,本数字 奇:偶,本数字計,全数字 奇:偶,全数字計,詳細表示`

- 第1回～2156回の2,156行＋ヘッダー＋最後の集計見出し
- 1～43の異なる本数字6個と、本数字と重複しないボーナス数字1個
- 構造検証では、**第2134回の本数字が1つ誤っていることを発見**：
  - 原本: `5,9,10,29,26,35`、ボーナス `18`、合計 `114`（誤記を含む）
  - 公表: `5,9,10,19,26,35`、ボーナス `18`、本数字合計 `104`
  - 訂正したのは番号 `29 → 19` の1箇所。残りの数字とボーナスは変更なし
  - 根拠: https://www.takarakuji-loto6.jp/LotoNumber/HistoryPartOutPut?pageNumber=2 （第2134回、2026-09-03）
- 取込用CSVでは本数字を昇順に揃えた。
- **原本に抽せん日は含まれない**。DBの `draw_date` はNULLのまま（捏造しない）。
- 最新第2156回（2026-11-19）の数字は公表結果と照合：
  https://www.takarakuji-loto6.jp/LotoNumber/History?pageNumber=1

### NUMBERS4入力形式

原本先頭行：`第1回～第6436回 抽選結果【8399】`

- 第1回～6436回の6,436行とヘッダー1行。
- `第3回,.0097,` のように、ドット接頭辞と4桁で記録される。ドットは表示形式、**本来の当せん番号は「0097」**。
- 先頭0のデータは**652件**。SQLでは`CHAR(4)`として保存し、整数化しない。
- 元CSVに抽せん日は含まれない。DBの`draw_date`はNULL。
- 第6436回は**2024-03-29の8399**と公表結果で照合済み：
  https://www.mizuhobank.co.jp/takarakuji/check/numbers/backnumber/detail.html?fromto=6421_6436&type=numbers
- **2026-11-19時点の第7118回まで682回分（第6437～7118回）が未収録**。このバンドルの登録は「全履歴最新まで取得済み」を意味しない。
  https://takarakuji.rakuten.co.jp/backnumber/numbers4
- 第1回は1149（公式みずほ）
  https://www.mizuhobank.co.jp/takarakuji/check/numbers/backnumber/num0001.html

## DBテーブル

3種で別テーブルを利用し、既存のLOTO7当せん履歴・予測履歴を変更しない。

| テーブル | 用途 |
|---|---|
| `draw_results` | 既存のLOTO7履歴。変更なし |
| `loto6_draw_results` | 回号、抽せん日NULL、本数字6個JSON、ボーナス1個、取込元 |
| `numbers4_draw_results` | 回号、抽せん日NULL、4桁の当せん番号 `CHAR(4)`、取込元 |
| `prediction_runs` | 既存のLOTO7予測履歴。変更なし |

## 初回取込手順

1. `main`へPRマージ後、Renderサービス環境変数 `LOTTERY_BOOTSTRAP_ADDITIONAL_GAMES=1` を一時的に追加。
2. 再デプロイの起動時に、バンドルされたgzipファイルのSHA-256を照合・展開。
3. LOTO6とNUMBERS4を別トランザクションでTiDBへ一括INSERT。先に既存回を確認し、内容不一致なら当該ゲームの全件INSERTをロールバック。
4. `GET /api/history/status/LOTO6` と `GET /api/history/status/NUMBERS4` で件数・欠落を検証。
5. 登録が成功したらRenderで `LOTTERY_BOOTSTRAP_ADDITIONAL_GAMES=0` に変更して再デプロイ。
6. 再デプロイ後も件数が維持されているか確認。

**本番の資格情報・MySQLホスト名はGitHubへ登録しない。**

## 機能範囲

このPRは「実績DBへの取込」と「履歴件数表示」まで。
既存の予測/深層学習/3AI判定は**LOTO7専用のまま**。LOTO6・NUMBERS4の予測モデルを、LOTO7の数字範囲・選択個数を流用して誤動作させない。

新たな抽せん回の増分取込は同じリポジトリに専用の認証付きCSVアップロードAPIを追加する段階で対応可能。現時点の公開サイトではLOTO7用アップロードだけが有効。
