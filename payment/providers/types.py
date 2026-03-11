import inspect
import uuid
from abc import ABC
from dataclasses import asdict, dataclass, replace
from decimal import Decimal
from typing import Any

from payment.utils import display_decimal


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
            if v is not None and getattr(self, k) is None
        }
        return replace(self, **updates)

    def get_payin_payload(self) -> dict[str, Any]:
        pass

    def parse_payin_response(self, response_data) -> dict[str, Any]:
        pass

    def get_payout_payload(self) -> dict[str, Any]:
        pass

    def parse_payout_response(self, response_data) -> dict[str, Any]:
        pass

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        payin_required_methods = {
            "get_payin_payload": ["self"],
            "parse_payin_response": ["self", "response_data"],
        }
        payout_required_methods = {
            "get_payout_payload": ["self"],
            "parse_payout_response": ["self", "response_data"],
        }

        required_methods = {
            "payin": payin_required_methods,
            "payout": payout_required_methods,
        }

        implemented = []
        for name, methods in required_methods.items():
            try:
                cls.check_required_methods(
                    class_name=BasePaymentContext,
                    required_methods=methods,
                )
                implemented.append(name)
            except TypeError:
                pass

        if not implemented:
            raise TypeError(
                f"{cls.__name__} must implement either PAYIN or PAYOUT contract"
            )


@dataclass
class SpiritPaymentContext(BasePaymentContext):
    currency: str = None
    webhook_url: str = None
    payment_method: str = None
    merchant_id: str = None
    success_url: str = None
    fail_url: str = None
    client_id: str = None

    @property
    def _random_ip(self):
        return "127.0.0.1"

    @property
    def _random_last_name(self):
        return "Doe"

    @property
    def _random_phone(self):
        return "+10000000000"

    @property
    def _random_email(self):
        return "test@example.com"

    def get_payin_payload(self) -> dict[str, Any]:
        amount = display_decimal(self.amount, 2)
        return {
            "order_id": self.order_id,
            "merchant_id": self.merchant_id,
            "amount": str(amount),
            "currency": self.currency,
            "method": self.payment_method,
            "callback_url": self.webhook_url,
            "success_url": self.success_url,
            "fail_url": self.fail_url,
            "client": {
                "id": self.client_id or str(uuid.uuid4()),
                "ip": self._random_ip,
                "name": f"{self._random_last_name} {self._random_last_name}",
                "phone": self._random_phone,
                "email": self._random_email,
                "stats": {"successful": 5, "expired": 1},
            },
        }

    def parse_payin_response(self, response_data) -> dict[str, Any]:
        result = response_data.get("data") or response_data.get("result") or response_data
        return {
            "id": result.get("id") or result.get("payment_id") or result.get("invoice_id"),
            "requisites": result.get("address") or result.get("requisites") or result.get("payment_url"),
            "recipient": result.get("recipient") or result.get("holder") or result.get("merchant"),
            "bank": result.get("bank") or result.get("provider"),
        }
