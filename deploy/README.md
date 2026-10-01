# deploy/

Deployment helpers for ShionMusicBot.

* `env.enc` — AES-256-CBC (pbkdf2) encrypted production `.env`.
  Decrypt with the deployment key:
  `openssl enc -d -aes-256-cbc -pbkdf2 -pass pass:<KEY> -in deploy/env.enc -out .env`
