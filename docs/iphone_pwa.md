# iPhoneからPWAとして起動

既存の公開先： https://tre-lottery-ai-assistant.onrender.com/

この変更を公開サービスへ反映した後、次の手順で利用します。GitHubへ保存しただけでは公開済みになりません。

1. iPhoneのSafariで上のHTTPS URLを開く。
2. Safariの共有ボタンを押し「ホーム画面に追加」を選ぶ。
3. 名前を確認して「追加」を押す。
4. ホーム画面の「TRE Lottery」アイコンから起動する。
5. 「AIハロ起動」をタップ。マイク入力は画面のマイク操作で許可する。

「ホーム画面に追加」が見えない場合は共有メニューの項目を下へスクロールし、必要なら「アクションを編集」を確認する。アプリ内ブラウザではSafariで開き直す。

## 動作範囲

- HTTPS同一オリジンで画面と既存APIを配信。iPhoneのlocalhostへ接続しない。
- manifestのstart_url/scope/idは `/`。共有URLのutmパラメーターはアプリの識別・起動URLへ引き継がない。
- 独立表示、iPhoneのsafe-area、Apple touch icon、192/512pxアイコンとmaskableアイコンを備える。
- インストール後は、最初にオンラインで画面を取得しておけばオフラインでも起動画面・ハロのUIを表示できる。
- 予測・CSV取込・サーバー状態確認は通信が必要。オフラインで予測成功を装わない。
- CSVの内容・セッションID・予測結果・APIレスポンスはService Workerのキャッシュに保存しない。CSVの保持期間は従来どおり1時間またはサーバー再起動まで。
- 新しい版を検出すると更新ボタンを表示。ユーザーが押した時だけ画面を再読み込みする。
- マイク・日本語音声認識・合成音声はiOSのバージョンと端末設定に依存する。実機で確認が必要。未対応/許可拒否時は文字・ボタンを利用する。
- 起動ボタンを押すまでマイクを要求しない。既存の起動音声とハロの動きは維持。

## Render既存サービス

既存Python Web Serviceを更新し、新規サービス・DB・有料プランは追加しない。build/startコマンドは従来どおり：

```text
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port $PORT
```

`GET /api/health` の成功と、`/manifest.webmanifest`、`/sw.js`、各アイコンの200応答を確認する。RenderのデプロイがliveになってからiPhoneで起動する。

無料インスタンスはアイドル後に休止するため、サーバー初回応答が遅れる場合がある。画面は10秒経過で待機を通知、90秒でタイムアウトし再試行を案内する。勝手にPOSTを再送しない。データの永続性は従来の仕様を変えない。

## 検証

Python31件PASS（既存26件＋PWA関連5件）。manifestとアイコンの配信、shell更新ポリシー、API no-store、非公開データ非配信を確認。

Chromiumの375/390/430/1280幅で起動画面・Safari向け追加案内・画面はみ出しを検査し、390幅ではオフライン再読込、起動ボタン操作、API実行拒否、CacheStorageにAPIがないことを検証する。これはiPhone実機やSafari実音声の検証とは区別する。
