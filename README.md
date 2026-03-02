# apichanged

Тестовый репозиторий с примером интеграции провайдера платежей.

## Ссылка на документацию API

Для кода в `assas.py` ориентиром служит документация API SpiritPay:
- https://spiritpay.club (базовый URL в коде: `https://spiritpay.club`)

## Полное описание всех мест кода (`assas.py`)

Ниже — разбор каждого логического блока файла.

### 1) `RequiredMethodsMixin`

Назначение: контроль «контрактов» у наследников на этапе создания класса.

- Метод `check_required_methods(cls, class_name, required_methods)`:
  - Проверяет, что класс-наследник действительно наследуется от указанного базового класса.
  - Для каждого обязательного метода проверяет:
    1. что метод реализован в `__dict__` класса;
    2. что список параметров сигнатуры совпадает с ожидаемым.
  - При нарушении бросает `TypeError` с понятным текстом.

Идея блока: не допускать «полу-реализованные» провайдеры/контексты, которые не соблюдают API-контракт.

### 2) `BasePaymentContext`

Назначение: базовый контекст платежной операции (общие поля + интерфейс для payload/response).

Поля:
- `amount: Decimal`
- `order_id: str`
- `payout_id: str`

Основные методы:
- `raise_value_error(output_type)` — единообразный `ValueError` для неподдерживаемых форматов.
- `update_from_object(context_object)`:
  - Принимает объект того же класса.
  - Копирует только непустые (`is not None`) значения в те поля, где у текущего экземпляра `None`.
  - Возвращает новый объект через `dataclasses.replace`.
- Контрактные методы (должны быть реализованы наследниками):
  - `get_payin_payload`
  - `parse_payin_response`
  - `get_payout_payload`
  - `parse_payout_response`

`__init_subclass__`:
- Проверяет, что наследник реализовал хотя бы один набор контракта:
  - **PAYIN**: `get_payin_payload`, `parse_payin_response`
  - **PAYOUT**: `get_payout_payload`, `parse_payout_response`
- Если ни один контракт не выполнен — `TypeError`.

### 3) `SpiritPaymentContext`

Назначение: конкретный контекст для провайдера Spirit.

Дополнительные поля:
- `currency`, `webhook_url`, `payment_method`, `merchant_id`, `success_url`, `fail_url`

Реализация payin-контракта:
- `get_payin_payload()` формирует тело запроса на создание платежа:
  - `orderId`, `merchantId`, `amount`, `currency`, `method`, callback/success/fail URL;
  - блок `payer` с техническими/рандомными данными клиента.
- `parse_payin_response(response_data)` извлекает из `result`:
  - `id`, `address` (как `requisites`), `recipient`, `bank`.

### 4) `BaseProviderMixin`

Назначение: общий каркас HTTP-взаимодействия с провайдерами и обработки ошибок.

Что внутри:
- Пользовательские исключения:
  - `RequisitesNotFound`
  - `PayoutNotPossible`
  - `RequestException`
- Декоратор `provider_operation`:
  - Проставляет имя текущей операции в `_current_operation` на время вызова метода.
- Сервисные URL:
  - `_success_url` → `settings.BASE_SITE_URL`
  - `_fail_url` → `settings.BASE_SITE_URL + '/dashboard/methods'`
- `provider_method_name`:
  - Строит имя провайдера из пути файла модуля (часть после `providers`).
- Контракт для наследников:
  - `raise_for_not_found(response)`
  - `check_empty_response(response_data)`

`_request_to_provider(...)` — ключевой метод HTTP-обмена:
- Сериализует `payload` в JSON.
- Делает `POST` или `GET`.
- Логирует ответ провайдера.
- Проверяет:
  - пустой body;
  - условия `not found` через `raise_for_not_found`;
  - HTTP-ошибки `raise_for_status`;
  - валидность бизнес-ответа через `check_empty_response`.
- Нормализует и логирует ошибки разных типов.
- В `finally` всегда пишет `log_request_response(...)`.

### 5) `BaseSpiritProvider`

Назначение: общая реализация для всех Spirit-провайдеров.

Ключевые части:
- `base_url = "https://spiritpay.club"`
- Секреты/токены берутся из переменных окружения:
  - `SPIRIT_MID`, `SPIRIT_SECRET_KEY`, `SPIRIT_TOKEN`
- `_get_signature(data)`:
  - Сортированный JSON → HMAC-SHA256 по `secret_key`.
- `_get_headers(data)`:
  - `Content-Type`, `Authorization: Bearer ...`, `Signature`.
- `raise_for_not_found(response)`:
  - Для `400/404/500/502` поднимает `RequisitesNotFound`.
- `check_empty_response(response_data)`:
  - Если `status == True`, возвращает ответ;
  - иначе `RequestException`.
- `_get_base_requisites(ctx)`:
  1. Дополняет контекст `merchant_id`, `success_url`, `fail_url`;
  2. Собирает payload;
  3. Подписывает запрос и отправляет в `/api/v2/payments`;
  4. Парсит и возвращает реквизиты через `ctx.parse_payin_response(...)`.

### 6) `RubSpiritProvider`

Назначение: специализация Spirit-провайдера для RUB.

- `_webhook_url` строит URL через `reverse_lazy('payment:rub_spirit_webhook')`.
- `_get_rub_requisites(ctx)`:
  - дополняет контекст `webhook_url` и `currency='RUB'`;
  - делегирует в `_get_base_requisites(...)`.

### 7) `Provider`

Назначение: конечная точка использования в системе.

- `get_requisites(amount, order_id, ...)`:
  - Создает `SpiritPaymentContext` с `payment_method='c2c'`;
  - вызывает `_get_rub_requisites(...)`;
  - возвращает реквизиты для оплаты.

## Поток данных (коротко)

1. Вызывается `Provider.get_requisites(...)`.
2. Собирается контекст `SpiritPaymentContext`.
3. Контекст дополняется RUB-настройками и URL-ами.
4. Формируется payload по контракту payin.
5. В `BaseSpiritProvider` считается подпись и заголовки.
6. `_request_to_provider` отправляет запрос и проводит валидацию ответа.
7. Ответ парсится в унифицированный словарь реквизитов.

## Что важно проверить перед запуском

- Доступность переменных окружения:
  - `SPIRIT_MID`
  - `SPIRIT_SECRET_KEY`
  - `SPIRIT_TOKEN`
- Корректность `settings.BASE_SITE_URL`.
- Наличие маршрута `payment:rub_spirit_webhook`.
- Что внешние функции/объекты (`display_decimal`, `safe_response_data`, `log_request_response`, `RandomPlaceholdersMixin`, `requests`, `Response`, `settings`) импортированы и доступны в окружении.
