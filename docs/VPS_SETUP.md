# VPSセットアップ手順（初心者向け）

このアプリを **VPS（Ubuntu 22.04 + PostgreSQL）** で動かし、
**Gmail / ChatWork の資料をストレージへ自動保存**するための手順です。

コマンドは上から順にコピペで実行できます。`<...>` は自分の値に置き換えてください。
分からない箇所は、この手順書ごとエンジニアに渡せば伝わるように書いています。

---

## 0. 前提

- Ubuntu 22.04 LTS のVPS（さくらのVPS / ConoHa / AWS Lightsail など）
- ドメイン（例: `app.example.com`）※無くてもIPで動作確認は可能
- SSHでログインできる状態

---

## 1. 必要なソフトを入れる

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip git postgresql nginx
```

## 2. PostgreSQL のデータベースを作る

```bash
sudo -u postgres psql <<'SQL'
CREATE DATABASE client_management;
CREATE USER appuser WITH PASSWORD '<好きなパスワード>';
GRANT ALL PRIVILEGES ON DATABASE client_management TO appuser;
ALTER DATABASE client_management OWNER TO appuser;
SQL
```

## 3. アプリを配置する

```bash
sudo mkdir -p /opt/app && sudo chown $USER:$USER /opt/app
cd /opt/app
git clone <このリポジトリのURL> .
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 4. 設定ファイル（.env）を作る

```bash
cat > /opt/app/.env <<'ENV'
SECRET_KEY=<ランダムな長い文字列>
DATABASE_URL=postgresql://appuser:<パスワード>@localhost:5432/client_management
TZ=Asia/Tokyo
ENV
```

> freee / マネーフォワード / ストレージ（Dropbox・GCS）の認証情報は
> **アプリ画面から設定**するため、.env には基本不要です。

## 5. 起動テスト

```bash
cd /opt/app && source venv/bin/activate
gunicorn wsgi:app --bind 127.0.0.1:8000
```
エラーが出なければ `Ctrl+C` で止めて次へ。

## 6. 常時起動にする（systemd）

`/etc/systemd/system/clientapp.service` を作成:

```ini
[Unit]
Description=Client Management App
After=network.target postgresql.service

[Service]
User=<あなたのユーザー名>
WorkingDirectory=/opt/app
EnvironmentFile=/opt/app/.env
ExecStart=/opt/app/venv/bin/gunicorn wsgi:app --bind 127.0.0.1:8000 --workers 2 --timeout 120
Restart=always

[Install]
WantedBy=multi-user.target
```

有効化:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now clientapp
sudo systemctl status clientapp   # activeならOK
```

## 7. 外からアクセスできるようにする（nginx）

`/etc/nginx/sites-available/clientapp` を作成:

```nginx
server {
    listen 80;
    server_name <あなたのドメイン or IP>;
    client_max_body_size 50M;   # 添付ファイル対応

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/clientapp /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

> HTTPS化（無料SSL）は後から `sudo apt install certbot python3-certbot-nginx && sudo certbot --nginx` で可能。
> **freee連携のコールバックURLはhttps推奨**なので、本番前にSSL化してください。

---

## 8. ★ 自動保存の定期実行（cron + flock）

ここが「自動で保存される」の心臓部です。**5分ごと**に受信→保存を実行します。

```bash
crontab -e
```

エディタが開いたら、最下部に次の1行を追加して保存:

```cron
*/5 * * * * /usr/bin/flock -n /tmp/integrations.lock -c 'cd /opt/app && /opt/app/venv/bin/python batch_integrations.py >> /opt/app/integrations.log 2>&1'
```

- `*/5` = 5分ごと（`*/10`にすれば10分ごと等、自由に変更可）
- `flock -n` = 前回の処理が終わっていなければスキップ（**多重起動を防ぐ**）
- ログは `/opt/app/integrations.log` に溜まります

会計ソフトへの自動アップロードも回す場合は、もう1行追加:
```cron
*/15 * * * * /usr/bin/flock -n /tmp/accounting.lock -c 'cd /opt/app && /opt/app/venv/bin/python batch_accounting.py >> /opt/app/accounting.log 2>&1'
```

### 動作確認
```bash
cd /opt/app && venv/bin/python batch_integrations.py   # 手動で1回実行して結果を見る
tail -f /opt/app/integrations.log                       # ログを眺める
```

---

## 9. 更新のしかた（コードを直したとき）

```bash
cd /opt/app
git pull
source venv/bin/activate && pip install -r requirements.txt
sudo systemctl restart clientapp
```

---

## トラブル時の確認

| 症状 | 確認コマンド |
|---|---|
| アプリが開かない | `sudo systemctl status clientapp` / `journalctl -u clientapp -n 50` |
| 自動保存されない | `tail -n 50 /opt/app/integrations.log` |
| DBに繋がらない | `.env` の DATABASE_URL、`sudo systemctl status postgresql` |
| 添付が大きくて失敗 | nginx の `client_max_body_size` を増やす |

---

## まとめ（VPSでの自動保存の流れ）

```
cron（5分ごと）
  → flock で多重起動を防ぎつつ
    → batch_integrations.py 実行
      → Gmail/ChatWork の新着を取得
        → 顧問先の指定フォルダ（Dropbox/GCS）へ自動保存
          → ログに記録
```
