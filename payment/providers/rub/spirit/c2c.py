from payment.providers.rub.spirit import RubSpiritProvider
from payment.providers.types import SpiritPaymentContext


class Provider(RubSpiritProvider):
    def get_requisites(self, amount, order_id, *args, **kwargs):
        ctx = SpiritPaymentContext(
            amount=amount,
            order_id=order_id,
            payment_method="c2c",
        )
        return self._get_rub_requisites(ctx)
