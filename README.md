# Optimus AI — Ad Agent Prototype

Самооптимизирующий рекламный агент: собирает метрики, принимает решения как маркетолог и подкручивает ставки. Первая версия работает на **реалистичном моке Яндекс Директ** — без API-ключей.

## Быстрый старт

Требуется **Python 3.10+** (рекомендуется 3.11).

```bash
cd "Optimus AI"
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Создать кампанию
optimus init --name "Тест CPA" --budget 5000 --target-cpa 800

# Прогнать 48 «часов» симуляции
optimus run --ticks 48

# Посмотреть KPI и решения
optimus status

# Веб-дашборд
optimus serve
# → http://127.0.0.1:8000
```

## CLI

| Команда | Описание |
|---------|----------|
| `optimus init` | Создать mock-кампанию |
| `optimus run --ticks N` | Запустить N тиков агента |
| `optimus status` | KPI + последние решения |
| `optimus reset` | Сбросить метрики симуляции |
| `optimus serve` | API + дашборд |

## API

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/campaigns` | GET/POST | Список / создание |
| `/campaigns/{id}` | GET | KPI кампании |
| `/agent/tick` | POST | Один тик агента |
| `/agent/run` | POST | N тиков (`{"ticks": 12}`) |
| `/metrics/{id}` | GET | Снимки метрик |
| `/decisions/{id}` | GET | Лента решений |

## Архитектура

```
CLI / Dashboard → AgentLoop → OptimizerEngine (Rules + Bandit)
                     ↓
              AdPlatformAdapter → MockYandexAdapter → MarketSimulator
                     ↓
                 SQLite (metrics, decisions, bandit state)
```

Цикл агента: **Observe → Diagnose → Decide → Act → Learn**

- **Rules** — маркетинговые эвристики (CPA, CTR, бюджет)
- **Bandit** — Thompson Sampling запоминает, какие изменения ставки работают
- **Simulator** — аукцион, спрос по часам, конкуренция, шоки рынка

Подробнее: [BUILD.md](BUILD.md)

## Тесты

```bash
pytest
```

## Расширение на живые API

Реализуйте `AdPlatformAdapter` в `src/optimus/adapters/` — заготовка `YandexDirectAdapter` уже есть в `base.py`.
