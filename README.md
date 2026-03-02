# apichanged

Ниже — полное описание всех ключевых мест кода из `assas.py` с опорой на официальную документацию Python и `requests`.

## Ссылка на документацию

- Python docs (основной индекс): https://docs.python.org/3/
- `dataclasses`: https://docs.python.org/3/library/dataclasses.html
- `abc` (абстрактные базовые классы): https://docs.python.org/3/library/abc.html
- `inspect.signature`: https://docs.python.org/3/library/inspect.html#inspect.signature
- `requests` API и исключения: https://requests.readthedocs.io/en/latest/

---

## Полная карта кода (`assas.py`)

### 1) `RequiredMethodsMixin`

**Что делает:**
- Предоставляет `check_required_methods`, который проверяет наличие и сигнатуры методов у дочерних классов.
- Логика основана на `inspect.signature`: берутся имена параметров и сравниваются с ожидаемым списком.

**Зачем нужно:**
- Это «ранняя валидация контрактов»: ошибки в реализации обнаруживаются при объявлении класса, а не в runtime при первом вызове.

---

### 2) `BasePaymentContext(ABC, RequiredMethodsMixin)`

**Роль:**
- Базовый контекст платежа/выплаты.
- Содержит общие поля (`amount`, `order_id`, `payout_id`) и единый интерфейс для построения payload/парсинга ответов.

**Ключевые элементы:**
- `raise_value_error(output_type)` — вспомогательный статический метод для единообразной ошибки по неподдерживаемому типу.
- `update_from_object(context_object)`:
  - Проверяет тип входного объекта.
  - Мержит `dataclass`-поля: если у текущего объекта поле `None`, а у переданного — заполнено, значение подтягивается.
  - Возвращает новый экземпляр через `replace` (иммутабельный стиль обновления).
- Абстрактные/контрактные методы:
  - `get_payin_payload`
  - `parse_payin_response`
  - `get_payout_payload`
  - `parse_payout_response`

**Контроль реализации (`__init_subclass__`)**:
- Проверяется, что дочерний класс реализует **минимум один контракт**:
  - PAYIN: `get_payin_payload`, `parse_payin_response`
  - PAYOUT: `get_payout_payload`, `parse_payout_response`
- Если не реализован ни один — `TypeError`.

---

### 3) `SpiritPaymentContext(RandomPlaceholdersMixin, BasePaymentContext)`

**Назначение:**
- Специализированный контекст под Spirit API для входящих платежей (payin).

**Добавленные поля:**
- `currency`, `webhook_url`, `payment_method`, `merchant_id`, `success_url`, `fail_url`.

**Реализованные методы:**
- `get_payin_payload`:
  - Собирает JSON payload для API `/api/v2/payments`.
  - Использует базовые данные заказа и случайные данные плательщика (через `RandomPlaceholdersMixin`).
- `parse_payin_response`:
  - Достаёт `result` из ответа провайдера.
  - Нормализует структуру к внутреннему формату: `id`, `requisites`, `recipient`, `bank`.

---

### 4) `BaseProviderMixin(ABC, RequiredMethodsMixin)`

**Роль:**
- Общий сетевой и контрактный слой для провайдеров.

**Вложенные исключения:**
- `RequisitesNotFound`
- `PayoutNotPossible`
- `RequestException`

**Декоратор `provider_operation`:**
- Сохраняет текущую операцию в `self._current_operation` на время выполнения метода.

**Сервисные свойства:**
- `_success_url`, `_fail_url` — строятся от `settings.BASE_SITE_URL`.
- `provider_method_name`:
  - Автоматически формирует имя провайдера из пути файла модуля (часть после `providers`).

**Контракт класса (`__init_subclass__`)**:
- Требует реализацию:
  - `raise_for_not_found(self, response)`
  - `check_empty_response(self, response_data)`

**Ключевой сетевой метод `_request_to_provider(...)`:**
- Сериализует payload в JSON.
- Выполняет `POST`/`GET` через `requests`.
- Пишет debug/error-логи.
- Обрабатывает группы ошибок:
  - JSON decode / ValueError
  - HTTPError
  - RequestException
  - `RequisitesNotFound`
- В `finally` всегда логирует запрос/ответ через `log_request_response`.

---

### 5) `BaseSpiritProvider(BaseProviderMixin)`

**Роль:**
- Реализация общих правил именно для Spirit.

**Конфигурация:**
- `base_url = "https://spiritpay.club"`
- Секреты/ключи берутся из env:
  - `SPIRIT_MID`
  - `SPIRIT_SECRET_KEY`
  - `SPIRIT_TOKEN`

**Ключевая логика:**
- `_get_signature(data)` — HMAC SHA-256 подпись JSON-строки.
- `_get_headers(data)` — формирует заголовки (`Authorization`, `Signature`, `Content-Type`).
- `raise_for_not_found(response)` — на кодах `400/404/500/502` бросает `RequisitesNotFound`.
- `check_empty_response(response_data)` — проверяет `status == True`, иначе `RequestException`.
- `_get_base_requisites(ctx)`:
  - Подмешивает в контекст `merchant_id`, `success_url`, `fail_url`.
  - Готовит payload + headers.
  - Вызывает `_request_to_provider`.
  - Нормализует ответ через `ctx.parse_payin_response`.

---

### 6) `RubSpiritProvider(BaseSpiritProvider)`

**Роль:**
- RUB-специфичный слой.

**Что добавляет:**
- `_webhook_url` — URL для webhook через `reverse_lazy('payment:rub_spirit_webhook')`.
- `_get_rub_requisites(ctx)`:
  - Подмешивает `webhook_url` и `currency='RUB'`.
  - Делегирует выполнение в `_get_base_requisites`.

---

### 7) `Provider(RubSpiritProvider)`

**Роль:**
- Финальная точка входа, которую, вероятнее всего, использует внешний код.

**Метод:**
- `get_requisites(amount, order_id, *args, **kwargs)`:
  - Создаёт `SpiritPaymentContext` с `payment_method='c2c'`.
  - Запрашивает RUB-реквизиты через `_get_rub_requisites`.

---

## Поток данных (end-to-end)

1. Внешний код вызывает `Provider.get_requisites(amount, order_id)`.
2. Создаётся `SpiritPaymentContext`.
3. В RUB-слое добавляются `currency` и `webhook`.
4. В базовом Spirit-слое добавляются merchant/success/fail.
5. Формируется payload и подпись.
6. Выполняется HTTP-запрос к `/api/v2/payments`.
7. Ответ валидируется и нормализуется.
8. Возвращается словарь с реквизитами.

---

## Важные замечания по текущему состоянию файла

- В показанном фрагменте кода используются внешние сущности (`Any`, `inspect`, `dataclass`, `Decimal`, `requests`, `Response`, `settings`, `reverse_lazy`, `logger` и др.), но их импорты не видны в этом же файле. Для рабочей версии они должны быть определены/импортированы.
- В `BasePaymentContext` объявлены методы payout-контракта, но в Spirit-реализации в текущем файле реализован только payin-сценарий.

---

## Краткая «карта ответственности»

- **Контракты и проверка сигнатур:** `RequiredMethodsMixin`, `BasePaymentContext.__init_subclass__`, `BaseProviderMixin.__init_subclass__`.
- **Контекст и трансформация данных:** `BasePaymentContext`, `SpiritPaymentContext`.
- **Сеть и обработка ошибок:** `BaseProviderMixin._request_to_provider`.
- **Provider-specific (Spirit):** `BaseSpiritProvider`.
- **Валютная специализация (RUB):** `RubSpiritProvider`.
- **Публичная точка входа:** `Provider.get_requisites`.
