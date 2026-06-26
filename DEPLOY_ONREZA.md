# Деплой Optimus AI на ONREZA через Git

## 1. Подключить GitHub к ONREZA

1. Зайди на [onreza.ru](https://onreza.ru) → **Workspace → Settings → Git**
2. Нажми **Install GitHub App** и дай доступ репозиторию `come2me2/optimusai-`

## 2. Создать проект

1. **New Project** → источник **GitHub**
2. Выбери репозиторий `come2me2/optimusai-`
3. Ветка production: `main`

## 3. Build Settings

В **Project → Settings → Build & Deployment** укажи:

| Поле | Значение |
|------|----------|
| Framework Preset | **Other** |
| Install Command | `pip install .` |
| Build Command | `npm run build` |
| Output Directory | `onreza-output` |

Эти значения уже продублированы в [`onreza.toml`](onreza.toml) в корне репозитория.

## 4. Deploy settings

| Поле | Значение |
|------|----------|
| Compute type | **process** |
| Entry point | `server.cjs` |
| Health check | `/health` |

## 5. Environment variables (опционально)

| Переменная | Значение | Зачем |
|------------|----------|-------|
| `OPTIMUS_DATA_DIR` | `/tmp/optimus-data` | Путь для SQLite (writable) |
| `HOST` | `0.0.0.0` | Слушать все интерфейсы |

`PORT` ONREZA подставит сам.

## 6. Деплой

После сохранения настроек:

- нажми **Deploy** вручную, или
- сделай `git push` в `main` — сработает автодеплой

```bash
git push origin main
```

## 7. Проверка

Открой URL деплоя в ONREZA:

- `GET /health` → `{"status":"ok"}`
- `/` → веб-дашборд

## Локальная проверка перед пушем

```bash
pip install .
OPTIMUS_DATA_DIR=/tmp/optimus-data PORT=8000 python3 server.py
```

## Если сборка падает

ONREZA в первую очередь заточен под Node.js. Если `pip install` не находит Python:

1. Убедись, что **Install Command** задан явно (`pip install .`), а не `npm install`
2. Напиши в поддержку ONREZA про Python `process` deploy
3. Альтернатива — деплой через CLI: `nrz deploy --prod --compute process`
