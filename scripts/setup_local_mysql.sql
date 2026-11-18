-- TRE-Lottery AI Assistant / 発表用MySQLデータベース
-- XAMPPのphpMyAdmin →「SQL」タブで管理者権限で実行。
-- MariaDB / MySQL双方で扱えるテーブル定義です。
CREATE DATABASE IF NOT EXISTS tre_lottery CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE tre_lottery;

-- 本数字・ボーナス数字をJSON文字列として保存。lottery_typeと回号で重複防止。
CREATE TABLE IF NOT EXISTS draw_results (
    lottery_type VARCHAR(16) NOT NULL,
    draw_no INTEGER NOT NULL,
    draw_date VARCHAR(64) NOT NULL,
    numbers_json TEXT NOT NULL,
    bonus_json TEXT NOT NULL,
    source VARCHAR(32) NOT NULL,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (lottery_type, draw_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3AIの判断と分析候補を丸ごと保存。予測ごとに一意なIDを採番。
CREATE TABLE IF NOT EXISTS prediction_runs (
    run_id CHAR(32) NOT NULL PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    lottery_type VARCHAR(16) NOT NULL,
    mode VARCHAR(32) NOT NULL,
    target_draw INTEGER NULL,
    result_json LONGTEXT NOT NULL,
    INDEX idx_prediction_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- DBログインユーザーはphpMyAdminの「ユーザーアカウント」で別途作成します。
-- app専用ユーザーにtre_lotteryのみの権限（SELECT/INSERT/UPDATE/CREATE）を付与。
-- GitHubにパスワードを記述しないでください。
