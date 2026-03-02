
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
            'payin': payin_required_methods,
            'payout': payout_required_methods
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
class SpiritPaymentContext(RandomPlaceholdersMixin, BasePaymentContext):
    currency: str = None
    webhook_url: str = None
    payment_method: str = None
    merchant_id: str = None
    success_url: str = None
    fail_url: str = None

    def get_payin_payload(self) -> dict[str, Any]:
        return {
            "orderId": self.order_id,
            "merchantId": self.merchant_id,
            "amount": int(display_decimal(self.amount, 0)),
            "currency": self.currency,
            "method": self.payment_method,
            "callbackUri": self.webhook_url,
            "successUri": self.success_url,
            "failUri": self.fail_url,
            "payer": {
                "userId": str(uuid.uuid4()),
                "userIp": self._random_ip,
                "customerName": f'{self._random_last_name} {self._random_last_name}',
                "phone": self._random_phone,
                "email": self._random_email,
                "payments": {
                    "successful": 5,
                    "expired": 1
                }
            }
        }

    def parse_payin_response(self, response_data) -> dict[str, Any]:
        result = response_data.get('result', {})
        return {
            "id": result["id"],
            "requisites": result["address"],
            "recipient": result['recipient'],
            "bank": result['bank']
        }
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
        return settings.BASE_SITE_URL + '/dashboard/methods'

    @property
    def provider_method_name(self) -> str:
        module_file = Path(sys.modules[self.__class__.__module__].__file__)

        parts = module_file.parts
        try:
            idx = parts.index("providers") + 1
            rel_parts = parts[idx:]  # e.g. ['rub', 'bitwire', 'card.py']
        except ValueError:
            rel_parts = parts  # fallback if not found

        # Remove .py and join with underscores
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
            required_methods=required_methods
        )

    def _request_to_provider(self, url, headers, payload, request_type='post', timeout=10, **kwargs):
        response = None
        error_info = None

        try:
            payload_str = json.dumps(payload, separators=(",", ":"), ensure_ascii=False, sort_keys=True)

            response = None
            request_type_formatted = request_type.lower()

            if request_type_formatted == 'post':
                response = requests.post(
                    url=url,
                    headers=headers,
                    data=payload_str,
                    timeout=timeout
                )
            elif request_type_formatted == 'get':
                response = requests.get(
                    url=url,
                    headers=headers,
                    timeout=timeout
                )


            logger.debug(
                '',
                extra={
                    'provider': self.provider_method_name,
                    'response': response.text,
                    'status_code': response.status_code
                }
            )

            text = response.text.strip()
            if not text:
                raise self.RequisitesNotFound("Empty response from server (no JSON)")

            self.raise_for_not_found(response=response)
            response.raise_for_status()

            return self.check_empty_response(response_data=response.json())

        except (json.decoder.JSONDecodeError,
                RequestsJSONDecodeError,
                ValueError) as exp:
            error_info = {
                'error_type': 'ValueError',
                'error_message': str(exp)
            }

            logger.error('ValueError', extra=error_info)
            raise self.RequisitesNotFound(error_info)

        except requests.exceptions.HTTPError as exp:
            error_info = {
                'error_type': 'HTTPError',
                'error_message': str(exp)
            }

            logger.error('HTTPError', extra=error_info)
            raise self.RequestException(json.dumps(error_info))

        except requests.exceptions.RequestException as exp:
            error_info = {
                'error_type': 'RequestException',
                'error_message': str(exp)
            }

            logger.error('RequestException', extra=error_info)
            raise self.RequestException(json.dumps(error_info))

        except self.RequisitesNotFound as exp:
            error_info = {
                'error_type': 'RequisitesNotFound',
                'error_message': str(exp)
            }

            logger.error('RequisitesNotFound', extra=error_info)
            raise self.RequisitesNotFound()

        finally:
            response_data = {
                "data": safe_response_data(response),
                "response_code": response.status_code if response is not None else None,
                "error": error_info,
            }

            log_request_response(self.provider_method_name, url, headers, payload, response_data, **kwargs)
class BaseSpiritProvider(BaseProviderMixin):
    base_url = "https://spiritpay.club"

    _mid = os.environ['SPIRIT_MID']
    _secret_key = os.environ['SPIRIT_SECRET_KEY']
    _token = os.environ['SPIRIT_TOKEN']

    def _get_signature(self, data: dict):
        string = json.dumps(data, separators=(",", ":"), sort_keys=True)
        secret_key = bytes(self._secret_key, 'utf8')
        return hmac.new(
            secret_key,
            string.encode(),
            hashlib.sha256
        ).hexdigest()

    def _get_headers(self, data: dict) -> dict[str, str]:
        sign = self._get_signature(data)

        return {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self._token}',
            'Signature': sign
        }

    def raise_for_not_found(self, response: Response):
        if response.status_code in (400, 404, 500, 502):
            raise self.RequisitesNotFound()

    def check_empty_response(self, response_data: dict[str, Any]):
        if response_data.get('status', False) is True:
            return response_data

        raise self.RequestException(response_data)

    def _get_base_requisites(self, ctx: SpiritPaymentContext):
        url = self.base_url + '/api/v2/payments'
        ctx = ctx.update_from_object(SpiritPaymentContext(
            merchant_id=self._mid,
            success_url=self._success_url,
            fail_url=self._fail_url
        ))

        payload = ctx.get_payin_payload()
        headers = self._get_headers(payload)

        response_data = self._request_to_provider(url=url, headers=headers, payload=payload, timeout=15)
        return ctx.parse_payin_response(response_data)
class RubSpiritProvider(BaseSpiritProvider):
    @property
    def _webhook_url(self):
        return settings.BASE_SITE_URL + str(reverse_lazy('payment:rub_spirit_webhook'))

    def _get_rub_requisites(self, ctx: SpiritPaymentContext):
        ctx = ctx.update_from_object(SpiritPaymentContext(
            webhook_url=self._webhook_url,
            currency='RUB'
        ))

        return self._get_base_requisites(ctx)
class Provider(RubSpiritProvider):
    def get_requisites(self, amount, order_id, *args, **kwargs):
        ctx = SpiritPaymentContext(
            amount=amount,
            order_id=order_id,
            payment_method='c2c'
        )

        return self._get_rub_requisites(ctx)
