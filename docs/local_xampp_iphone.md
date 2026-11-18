# ローカル発表：XAMPP／phpMyAdmin／iPhone接続ガイド

## 1. MySQLを準備
1. XAMPP Control Panelから **MySQL** を起動します（ApacheはphpMyAdmin利用時のみ必要）。
2. PCのブラウザで **http://localhost/phpmyadmin/** を開きます。
3. 「SQL」または「インポート」で `scripts/setup_local_mysql.sql` を実行します。
4. 「ユーザーアカウント」から `tre_lottery_app` を作成し、接続元は `127.0.0.1`（必要に応じて `localhost` も設定）に制限します。DB `tre_lottery` のみで SELECT / INSERT / UPDATE / CREATE 権限を与えます。
5. `config/local.env.cmd.example` を `config/local.env.cmd` にコピーし、ユーザー名・パスワード・DBポート（XAMPP設定値）を入力します。**本物のパスワードをGitHubにアップロードしないこと。**

## 2. ローカルAPIとUIを起動
コマンドプロンプトで：
```cmd
cd /d C:\Work\31_source\TRE_Lottery_AI_Assistant
python -m pip install -r requirements.txt
copy config\local.env.cmd.example config\local.env.cmd
notepad config\local.env.cmd
scripts\start_local.cmd
```
`http://localhost:8000/` を開くと、初期画面には中央の「AIハロ起動」ボタンだけ表示されます。
ボタンをクリックすると3AI画面が表示され、指定の日本語起動音声を合成します。
`http://localhost:8000/api/health` の `database.status` が `connected` ならMySQL接続成功です。
CSV取り込み後、phpMyAdminで `tre_lottery.draw_results` を確認してください。
予測を実行すると `tre_lottery.prediction_runs` に候補番号・学習結果・3AI判断が記録されます。
DBが空なら架空履歴の**デモ**です。実データは自動取得しません。

## 3. iPhoneで同じPCの画面へアクセス
1. iPhoneとPCを同じWi-Fi／同じLANにつなぎます（ゲストWi-FiやAP隔離は不可）。
2. Windowsコマンドプロンプトで `ipconfig` を実行し、Wi-Fiアダプターの **IPv4アドレス**を確認します。
3. Windows Defender Firewallでは、ポート **8000/TCP** の受信を **プライベートネットワーク／信頼できるLAN** のみに許可します。公開ネットワークには開放しません。
4. iPhone Safariで `http://<PCのIPv4アドレス>:8000/` を開きます。たとえばIPv4が `192.168.1.20` **の場合に限り** `http://192.168.1.20:8000/` となります。
5. 「AIハロ起動」をタップします。

※iPhone側の `localhost` はiPhone自身を指します。`localhost/phpmyadmin` をiPhoneから開こうとしないでください。
※HTTPによるLANアクセスは画面閲覧・ボタン操作用です。iOS/Safariの音声認識はSecure Context（HTTPS）が必要、または非対応の場合があります。音声認識が使えない場合はボタン操作を使用してください。音声合成の可用性も実機ブラウザに依存します。
※マイクを使う発表を確実に行いたい場合はローカルHTTPS＋iPhoneに信頼済み証明書を設定するか、Chrome on PC／公開HTTPSのRenderで音声認識を確認してください。
※PCのMySQLポート3306やphpMyAdmin管理画面はiPhone側・インターネットへ開放しないでください。
