# PWA化（mainベース）— インストール手順

この変更は、既存の`main`ブランチを出発点として作成しています。
UIは緑・橙・紫のハロを含む現行のGIF方式で、ロト7予測、音声応答、CSV読込、MySQLの処理は変更しません。

## PWA化で追加したもの

- `web/manifest.webmanifest`：アプリ名、アイコン、起動URL、standaloneモード
- `web/service-worker.js`：ホーム画面起動用の静的UIキャッシュ。オフライン時に最後に取得した画面を表示
- `web/offline.html`：キャッシュが使えないときのオフライン案内
- `web/icons/`：PNG 192×192、512×512、maskable、Apple専用180×180
- `app.py`：PWAファイルを同じURL（HTTPSオリジン）から配信
- `web/index.html`：iPhone用メタタグ、Service Worker登録、インストール案内

**注意**：Service WorkerはWeb UIの静的データだけをキャッシュします。
`/api/`の通信、履歴CSV、MySQLデータ、LLM判定、予測結果は保存・キャッシュしません。
通信が切れている状態では新しい予測を実行できません。

## iPhoneのホーム画面へ追加

1. iPhoneの**Safari**で、この変更が反映された**HTTPSのPWA公開URL**を開く
2. 必要なら「AIハロ起動」を押し、アプリの画面を確認
3. Safariの **共有**（四角から上向きの矢印）をタップ
4. **「ホーム画面に追加」**を選ぶ
5. **「Webアプリとして開く」**が表示される場合はオンにする
6. 名前（推奨：`TRE Lottery`）を確認して**「追加」**を押す
7. ホーム画面の3体ハロのアイコンをタップして起動する

Safariはブラウザからホーム画面への登録をプログラムで自動実行できません。**手順4～6は端末の使用者が操作**します。

## Android・Windows

Chrome/Edgeなどの対応ブラウザでHTTPS URLを開き、「アプリをインストール」を実行します。
対応端末・ブラウザではページ内に「インストール」ボタンが表示されます。

## ローカル発表環境の注意

Windows PCでは`http://localhost:8000/`は「信頼できるオリジン」として扱われるため、
Service Workerの開発・確認が可能です。

ただし、iPhoneから同じPCへ`http://192.168.x.x:8000/`のようにHTTP接続した場合は、
PWA機能／マイクなどの一部APIが**HTTPS必須**のため動作が制限されます。
iPhoneへPWAとして追加する場合は**HTTPS公開URL**で操作することを推奨します。

## 最低限の動作確認

- `GET /manifest.webmanifest` → 200 / `application/manifest+json`
- `GET /service-worker.js` → 200 / JavaScript / キャッシュ無効
- `GET /icons/icon-192.png`, `icon-512.png`, `apple-touch-icon.png` → PNG
- `GET /` → 「AIハロ起動」ボタンを含む既存UI
- Chrome DevTools → Application → Manifest / Service Workers
- オフライン状態 → キャッシュ済みUIまたはオフラインページ。API予測は接続エラーになる
- iPhone Safari → 「ホーム画面に追加」→ アイコンの表示と起動
