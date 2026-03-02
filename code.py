import hashlib
import hmac
import inspect
import json
from abc import ABC
from dataclasses import dataclass, asdict
from decimal import Decimal
from typing import Any

import requests
from django.conf import settings
from django.urls import reverse_lazy

class RequiredMethodsMixin:
    @classmethod
    def check_required_methods(cls, class_name, required_methods: dict[str, Any]):
        if class_name in cls.__bases__:
            for method_name, expected_params in required_methods.items():
                func = cls.__dict__.get(method_name)
                if func is None:
                    raise TypeError(f"{cls.__name__} must implement {method_name}{tuple(expected_params)}")

                sig = inspect.signature(func)
                actual_params = list(sig.parameters.keys())

                if actual_params != expected_params:
                    raise TypeError(
                        f"{cls.__name__}.{method_name} must have parameters {expected_params}, "
                        f"but has {actual_params}"
                    )

@dataclass
class BasePaymentContext(ABC, RequiredMethodsMixin):
    amount: Decimal = None
    order_id: str = None
    payout_id: str = None

    @staticmethod
    def raise_value_error(output_type):
        raise ValueError(f"Unsupported output_type: {output_type}")

    def update_from_object(self, context_object):
        if not isinstance(context_object, self.__class__):
            raise TypeError(
                f"Expected {self.__class__.__name__}, got {context_object.__class__.__name__}"
            )

        updates = {
            k: v
            for k, v in asdict(context_object).items()
            if v is not None
        }
        for key, value in updates.items():
            setattr(self, key, value)
        return self

# --- Секция Cryptura ---

@dataclass
class CrypturaPaymentContext(BasePaymentContext):
    """
    Контекст для работы с Cryptura API v1.
    """
    currency: str = None
    callback_url: str = None
    success_url: str = None
    fail_url: str = None
    description: str = "Payment for order"

    def __post_init__(self):
        self.check_required_methods(
            class_name='CrypturaPaymentContext',
            required_methods={
                'get_payin_payload': ['self'],
                'parse_payin_response': ['self', 'response_data']
            }
        )

    def get_payin_payload(self) -> dict:
        """Формирует JSON согласно документации Cryptura /v1/invoices/create"""
        return {
            "amount": str(self.amount),
            "currency": self.currency,
            "order_id": str(self.order_id),
            "callback_url": self.callback_url,
            "success_url": self.success_url,
            "fail_url": self.fail_url,
            "description": self.description
        }

    def parse_payin_response(self, response_data: dict[str, Any]):
        """Извлекает checkout_url из ответа Cryptura"""
        data = response_data.get('data', {})
        return {
            'payment_id': data.get('id'),
            'pay_url': data.get('checkout_url'), # URL платежной формы
            'status': response_data.get('status')
        }

class BaseProvider(ABC, RequiredMethodsMixin):
    def __post_init__(self):
        self.check_required_methods(
            class_name='BaseProvider',
            required_methods={
                'check_empty_response': ['self', 'response_data'],
            }
        )

    class RequestException(Exception):
        pass

    def _request_to_provider(self, url, headers, payload, timeout=15):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=timeout)
            response.raise_for_status()
            response_data = response.json()
        except (requests.RequestException, ValueError) as e:
            raise self.RequestException(f"Provider request failed: {str(e)}")

        return self.check_empty_response(response_data)

class BaseCrypturaProvider(BaseProvider):
    """
    Базовая логика для Cryptura: заголовки и базовый URL.
    """
    base_url = "https://api.cryptura.io" # Согласно документации

    def __init__(self, api_key: str):
        self._api_key = api_key
        super().__post_init__()

    def _get_headers(self):
        """Cryptura использует Bearer Token или API Key в заголовках"""
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    def check_empty_response(self, response_data: dict[str, Any]):
        # В Cryptura успех обычно помечается статус-кодом или полем status: True/success
        if response_data.get('status') in [True, 'success']:
            return response_data
        raise self.RequestException(response_data)

    def _get_base_requisites(self, ctx: CrypturaPaymentContext):
        url = f"{self.base_url}/v1/invoices/create"
        
        # Обновляем контекст стандартными URL, если нужно
        ctx = ctx.update_from_object(CrypturaPaymentContext(
            success_url=settings.BASE_SITE_URL + "/payment/success",
            fail_url=settings.BASE_SITE_URL + "/payment/fail"
        ))

        payload = ctx.get_payin_payload()
        headers = self._get_headers()

        response_data = self._request_to_provider(url=url, headers=headers, payload=payload)
        return ctx.parse_payin_response(response_data)

class CryptoCrypturaProvider(BaseCrypturaProvider):
    """
    Провайдер для крипто-платежей Cryptura.
    """
    @property
    def _webhook_url(self):
        return settings.BASE_SITE_URL + str(reverse_lazy('payment:cryptura_webhook'))

    def get_payment_link(self, amount: Decimal, order_id: str, currency: str = 'USDT'):
        ctx = CrypturaPaymentContext(
            amount=amount,
            order_id=order_id,
            currency=currency,
            callback_url=self._webhook_url
        )
        return self._get_base_requisites(ctx)

# Финальный класс-обертка
class Provider(CryptoCrypturaProvider):
    def __init__(self):
        # Берем ключ из настроек
        super().__init__(api_key=settings.CRYPTURA_API_KEY)

    def get_requisites(self, amount, order_id, currency='USDT'):
        """
        Метод для получения ссылки на оплату.
        """
        return self.get_payment_link(amount=amount, order_id=order_id, currency=currency)