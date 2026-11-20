# クラウドMySQL接続とロト7履歴取込手順（XAMPP不要）

## 目的・現在の実装

TRE-Lottery AI AssistantはFastAPIとMySQL 8互換DBで当せん履歴・予測結果を永続化する。
既存のハロ高速GIF UI・3AI判定・ディープラーニングは維持する。

**このリポジトリにはDBの認証情報も実際の抽せん履歴も含めない。**
接続先MySQLの作成と資格情報のRender登録を行った後に接続できる。
まだDBを用意していない状態で `/api/health` に `connected` と出ることはない。

## 1. クラウドDBの用意

選択肢A: RenderのプライベートMySQLサービス。Renderの公式ガイド:
https://render.com/docs/deploy-mysql

- Webサービスと**同じRenderワークスペース**にプライベートサービスを作成する。
- MySQL 8のイメージを使用する。環境変数 `MYSQL_DATABASE=tre_lottery`、`MYSQL_USER`、`MYSQL_PASSWORD`、`MYSQL_ROOT_PASSWORD` を設定。
- **永続ディスク**を `/var/lib/mysql` にマウントする。ディスクなしでDBを稼働させるとデータ消失の危険がある。
- DBサービスの内部ホスト名（例: `mysql-private`）とポート3306を控える。
- **プライベートMySQLと永続ディスクは有料構成になる可能性があります。金額を確認し、利用者自身が承認してから作成してください。**
- Renderプライベートネットワーク内のMySQLでTLSを提供しない場合に限り、`LOTTERY_DB_SSL_MODE=disabled` を明示指定する。**外部公開ネットワークでは必ずTLS検証を有効**にする。

選択肢B: 外部のクラウドMySQL（Aiven/MySQL互換DB等）。接続URL・CA証明書・外部接続許可を取得する。
外部DBの場合 `LOTTERY_DB_SSL_MODE=verify` が既定。ホスト名と証明書を検証し、接続情報をソースに記載しない。
**MySQLとPostgreSQLは異なるDBです。RenderのマネージドPostgresへはこのコードのまま接続できません。**

## 2. RenderのWebサービス側の環境変数

Render Dashboard → 対象Webサービス → Environment → Add Environment Variable。
Render公式: https://render.com/docs/configure-environment-variables

**分割指定（RenderプライベートMySQL）**

| 変数 | 例・意味 |
|---|---|
| `LOTTERY_DB_BACKEND` | `mysql`（これがないとメモリデモ） |
| `LOTTERY_DB_HOST` | `mysql-private`（DB内部ホスト名に置き換える） |
| `LOTTERY_DB_PORT` | `3306` |
| `LOTTERY_DB_NAME` | `tre_lottery` |
| `LOTTERY_DB_USER` | DBサービスに作成したアプリ用ユーザー |
| `LOTTERY_DB_PASSWORD` | DBサービスのユーザーパスワード |
| `LOTTERY_DB_SSL_MODE` | `disabled` ※Render内部のTLS未対応MySQL限定 |
| `LOTTERY_ADMIN_TOKEN` | 32バイト以上の安全なランダムトークン |

**外部のクラウドMySQLでは**分割指定の代わりに
`LOTTERY_MYSQL_URL=mysql+pymysql://USER:ENCODED_PASSWORD@DB_HOST:3306/tre_lottery`
を使用できる。URLを使う場合 `LOTTERY_DB_HOST` などより優先される。
`LOTTERY_DB_SSL_MODE=verify` を指定し、提供元から必要とされた場合は
`LOTTERY_DB_SSL_CA=/path/to/ca.pem` でCA証明書を指定する。
アプリ用DBユーザーの権限はDB `tre_lottery` の SELECT / INSERT / CREATE（必要ならUPDATE）のみに限定する。

管理トークン生成方法（生成結果をGitHubやチャットへ貼らない）:

```cmd
python -c "import secrets; print(secrets.token_urlsafe(36))"
```

Webサービスは `uvicorn app:app --host 0.0.0.0 --port $PORT` のまま。
Renderサービス側の参照ブランチが `main` またはこのPRのブランチになっていることを確認する。
※既存の `tre-lottery-ai-assistant` は旧開発ブランチを参照しているため、GitHubのマージだけでは変わらない。

## 3. 実際のロト7当せん履歴CSVを取り込む

信頼する当せん番号ソースを確認する:
- みずほ銀行 公式: https://www.mizuhobank.co.jp/takarakuji/check/loto/backnumber/index.html
- 公式当せん番号ページにはプログラム自動取得を制限する実例があるため、**アクセス制限の迂回は実装しない**。
- 元の資料からCSVを作る場合は公式発表の回号・日付・本数字7個・ボーナス数字2個を検証する。
- 出典未確認の第三者CSVを「公式データ」と表示しない。

CSVの必須列:
```csv
draw_no,draw_date,n1,n2,n3,n4,n5,n6,n7,b1,b2
```
※ボーナス数字 `b1,b2` は省略可。実際の当せん番号を記入して取り込むこと。
文字コード UTF-8（BOM可）または CP932。日付は
`2013-04-05`, `2013/4/5`, `2013年4月5日` 形式に対応し、
DBにはISO日付として保存。CSVの回号が重複していたり本数字が範囲外、
ボーナス数字が重複していたり日付が不正なら登録しない。

**Web画面からの操作（推奨）**

1. ブラウザでアプリを開き、「AIハロ起動」を押す。
2. DRAW HISTORY / CSV IMPORTのMySQL接続状態を確認。
3. 管理者トークン欄にRenderに設定した `LOTTERY_ADMIN_TOKEN` を入力。
4. CSVを指定して「CSV取込」を押す。
5. 初回は全履歴、次回以降は直近1回分だけのCSVでも取込可能。**既存回はスキップし、番号・日付が矛盾する場合は409で拒否**。
6. 認証情報はブラウザの保存領域に記憶しない。入力欄は送信後にクリア。
7. ロト7予測時には、MySQLに登録された**20回以上の実履歴**が用いられる。未登録では409エラーを返し、人工データへは自動で切り替えない。

**CLIから取込（DBへアクセスできる管理端末で実行する場合）**

```sh
python -m lottery_ai.cloud_import --csv loto7_history.csv --dry-run
python -m lottery_ai.cloud_import --csv loto7_history.csv
```

CLIは `LOTTERY_MYSQL_URL` または分割DB環境変数を使う。
Render内部専用DBに一般のPCから直接アクセスできない場合は、ブラウザの管理者CSVアップロードを使う。

## 4. 接続・取込の検証

`GET /api/health`

```json
{
  "database": {
    "backend": "mysql",
    "status": "connected",
    "draw_count": 0,
    "first_draw": null,
    "last_draw": null
  },
  "history_mode": "MYSQL_WAITING"
}
```

これは **接続成功・未登録** の例。実際の件数はCSV登録後に変化する。
`GET /api/history/status` で `first_draw`, `last_draw`, `last_date`, `missing_count` を点検可能。
登録済み20件以上になった場合、`history_mode=MYSQL` となる。
予測を行うと `prediction_runs` に結果が保存される。

`backend=memory`: `LOTTERY_DB_BACKEND=mysql` が設定されていない。
`status=unavailable`: DBサービス停止、ホスト/ポート/認証/TLSを確認（APIはDB秘密を返さない）。
`history_mode=MYSQL_WAITING`: DBへの接続が失敗したか、実データが20件未満。
画面の履歴件数が0でも `connected` と `unavailable` は異なる。

## 5. 運用と安全性

- CSVのWebアップロードは `LOTTERY_ADMIN_TOKEN` がない場合503、誤った場合401/403。
- 一般ユーザーの閲覧・予測はトークン不要。
- 事実に反する既存回のCSVでDBを上書きしない。途中で矛盾が見つかった場合は全件ロールバック。
- 毎週の実データ更新には、正式な取得元CSVを用意し同じ画面から追加する。公式サイトへの無許可の自動スクレイピングは行わない。
- RenderディスクのスナップショットだけでDBバックアップを代用しない。MySQLの `mysqldump` によるバックアップを別途用意する。
- 公開WebサービスからDBへ接続する場合、ポート3306をインターネットへ無制限公開しない。
