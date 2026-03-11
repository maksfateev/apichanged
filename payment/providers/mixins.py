import hashlib
import hmac
import json
import os
import sys
from abc import ABC, abstractmethod
from functools import wraps
from pathlib import Path
from typing import Any

import requests
from django.conf import settings
from requests import Response
from requests.exceptions import JSONDecodeError as RequestsJSONDecodeError

from payment.providers.types import RequiredMethodsMixin, SpiritPaymentContext
from payment.utils import log_request_response, safe_response_data


class BaseProviderMixin(ABC, RequiredMethodsMixin):
    class RequisitesNotFound(Exception):
        pass

    class PayoutNotPossible(Exception):
        pass

    class RequestException(Exception):
        pass

    def provider_operation(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            self._current_operation = func.__name__
            try:
                return func(self, *args, **kwargs)
            finally:
                self._current_operation = None

        return wrapper

    @property
    def _success_url(self):
        return settings.BASE_SITE_URL

    @property
    def _fail_url(self):
        return settings.BASE_SITE_URL + "/dashboard/methods"

    @property
    def provider_method_name(self) -> str:
        module_file = Path(sys.modules[self.__class__.__module__].__file__)

        parts = module_file.parts
        try:
            idx = parts.index("providers") + 1
            rel_parts = parts[idx:]
        except ValueError:
            rel_parts = parts

        name_parts = [p.replace(".py", "") for p in rel_parts]
        return "_".join(name_parts)

    @abstractmethod
    def raise_for_not_found(self, response: Response):
        pass

    @abstractmethod
    def check_empty_response(self, response_data: dict[str, Any]):
        pass

    def __init_subclass__(cls):
        super().__init_subclass__()

        required_methods = {
            "raise_for_not_found": ["self", "response"],
            "check_empty_response": ["self", "response_data"],
        }

        cls.check_required_methods(
            class_name=BaseProviderMixin,
            required_methods=required_methods,
        )

    def _request_to_provider(self, url, headers, payload, request_type="post", timeout=10, **kwargs):
        response = None
        error_info = None

        try:
            payload_str = json.dumps(payload, separators=(",", ":"), ensure_ascii=False, sort_keys=True)
            request_type_formatted = request_type.lower()

            if request_type_formatted == "post":
                response = requests.post(url=url, headers=headers, data=payload_str, timeout=timeout)
            elif request_type_formatted == "get":
                response = requests.get(url=url, headers=headers, timeout=timeout)

            text = response.text.strip()
            if not text:
                raise self.RequisitesNotFound("Empty response from server (no JSON)")

            self.raise_for_not_found(response=response)
            response.raise_for_status()

            return self.check_empty_response(response_data=response.json())

        except (json.decoder.JSONDecodeError, RequestsJSONDecodeError, ValueError) as exp:
            error_info = {"error_type": "ValueError", "error_message": str(exp)}
            raise self.RequisitesNotFound(error_info)

        except requests.exceptions.HTTPError as exp:
            error_info = {"error_type": "HTTPError", "error_message": str(exp)}
            raise self.RequestException(json.dumps(error_info))

        except requests.exceptions.RequestException as exp:
            error_info = {"error_type": "RequestException", "error_message": str(exp)}
            raise self.RequestException(json.dumps(error_info))

        except self.RequisitesNotFound as exp:
            error_info = {"error_type": "RequisitesNotFound", "error_message": str(exp)}
            raise self.RequisitesNotFound()

        finally:
            response_data = {
                "data": safe_response_data(response),
                "response_code": response.status_code if response is not None else None,
                "error": error_info,
            }
            log_request_response(self.provider_method_name, url, headers, payload, response_data, **kwargs)


class BaseSpiritProvider(BaseProviderMixin):
    base_url = os.getenv("CRYPTURA_BASE_URL", "https://api.cryptura.pro")
    payin_endpoint = os.getenv("CRYPTURA_PAYIN_ENDPOINT", "/api/v1/payments")

    _mid = os.environ["CRYPTURA_MERCHANT_ID"]
    _secret_key = os.environ["CRYPTURA_SECRET_KEY"]
    _token = os.environ["CRYPTURA_API_KEY"]

    def _get_signature(self, data: dict):
        string = json.dumps(data, separators=(",", ":"), sort_keys=True)
        secret_key = bytes(self._secret_key, "utf8")
        return hmac.new(secret_key, string.encode(), hashlib.sha256).hexdigest()

    def _get_headers(self, data: dict) -> dict[str, str]:
        sign = self._get_signature(data)
        return {
            "Content-Type": "application/json",
            "X-API-KEY": self._token,
            "X-SIGNATURE": sign,
            "Authorization": f"Bearer {self._token}",
        }

    def raise_for_not_found(self, response: Response):
        if response.status_code in (400, 401, 403, 404, 422, 500, 502):
            raise self.RequisitesNotFound()

    def check_empty_response(self, response_data: dict[str, Any]):
        status = response_data.get("status")
        if status is True or status in {"success", "ok"}:
            return response_data
        if response_data.get("success") is True:
            return response_data
        raise self.RequestException(response_data)

    def _get_base_requisites(self, ctx: SpiritPaymentContext):
        url = self.base_url + self.payin_endpoint
        ctx = ctx.update_from_object(
            SpiritPaymentContext(
                merchant_id=self._mid,
                success_url=self._success_url,
                fail_url=self._fail_url,
            )
        )

        payload = ctx.get_payin_payload()
        headers = self._get_headers(payload)

        response_data = self._request_to_provider(url=url, headers=headers, payload=payload, timeout=15)
        return ctx.parse_payin_response(response_data)
