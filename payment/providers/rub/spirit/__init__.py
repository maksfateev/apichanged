from django.conf import settings
from django.urls import reverse_lazy

from payment.providers.mixins import BaseSpiritProvider
from payment.providers.types import SpiritPaymentContext


class RubSpiritProvider(BaseSpiritProvider):
    @property
    def _webhook_url(self):
        return settings.BASE_SITE_URL + str(reverse_lazy("payment:rub_spirit_webhook"))

    def _get_rub_requisites(self, ctx: SpiritPaymentContext):
        ctx = ctx.update_from_object(
            SpiritPaymentContext(
                webhook_url=self._webhook_url,
                currency="RUB",
            )
        )

        return self._get_base_requisites(ctx)
