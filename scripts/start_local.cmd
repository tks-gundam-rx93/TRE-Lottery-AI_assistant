@echo off
setlocal
rem Windows/XAMPP用: このファイルをダブルクリックしても起動可能です。
cd /d "%~dp0.."
if not exist "config\local.env.cmd" (
    echo [ERROR] config\local.env.cmd がありません。
    echo config\local.env.cmd.example をコピーしてDB設定を編集してください。
    exit /b 1
)
call "config\local.env.cmd"
rem 同じWi-Fi内のiPhoneから接続するためLAN側にもHTTPを待ち受ける。
rem DB接続自体は引き続き127.0.0.1のみ。ポート8000の許可は私用ネットワークに限定。
python -m uvicorn app:app --host 0.0.0.0 --port 8000
