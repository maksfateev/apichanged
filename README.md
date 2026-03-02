# apichanged

Ниже — описание кода интеграции платежного провайдера.

## Документация

- Cryptura Docs: https://cryptura.gitbook.io/cryptura-docs
- Python docs: https://docs.python.org/3/
- requests: https://requests.readthedocs.io/en/latest/

## Что изменено для перехода на другой API

- Сохранена прежняя архитектура: `Context -> BaseProviderMixin -> конкретный провайдер -> Provider`.
- `SpiritPaymentContext` переведён на формат payload/response для Cryptura (snake_case поля, более универсальный разбор ответа).
- Добавлены совместимые алиасы (`SpiritPaymentContext`, `BaseSpiritProvider`, `RubSpiritProvider`) чтобы не ломать внешние импорты.
- Провайдер использует переменные окружения Cryptura:
  - `CRYPTURA_BASE_URL`
  - `CRYPTURA_PAYIN_ENDPOINT`
  - `CRYPTURA_MERCHANT_ID`
  - `CRYPTURA_SECRET_KEY`
  - `CRYPTURA_API_KEY`
- Подпись запроса оставлена через HMAC SHA-256, заголовки переключены на API-key/signature формат.

## Пример минимальной конфигурации

```bash
export CRYPTURA_BASE_URL="https://api.cryptura.pro"
export CRYPTURA_PAYIN_ENDPOINT="/api/v1/payments"
export CRYPTURA_MERCHANT_ID="your_merchant_id"
export CRYPTURA_SECRET_KEY="your_secret"
export CRYPTURA_API_KEY="your_api_key"
```

## Важно

Т.к. в репозитории отсутствует полный runtime-контекст проекта (импорты/вспомогательные функции/настройки), изменения сделаны максимально совместимыми со старой структурой и текущим интерфейсом `Provider.get_requisites(...)`.
