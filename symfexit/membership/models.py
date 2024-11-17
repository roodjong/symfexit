from django.utils import formats, timezone
from django.utils.translation import gettext_lazy as _

from symfexit.payments.models import Subscription


class Membership(Subscription):
    class Meta:
        verbose_name = _("membership")
        verbose_name_plural = _("memberships")

    @classmethod
    def current_for_user(cls, user):
        return cls.objects.filter(user=user, active_from_to__contains=timezone.now()).first()

    def new_order(self, *, initial, return_url, description=None):
        from signup.models import ApplicationPayment

        if description is None:
            description = f"Membership fee for {self.address.name}"
            if not initial:
                description += " (initial payment)"

        order = super().new_order(initial=initial, return_url=return_url, description=description)
        appl_pay = ApplicationPayment(order_ptr=order)
        appl_pay.save_base(raw=True)
        if initial:
            from signup.models import MembershipApplication

            appl = MembershipApplication.objects.filter(_subscription=self).first()
            assert appl is not None
            appl._order = appl_pay
            appl.save()
        return order

    def __str__(self):
        text = "{} is a member starting at {}".format(
            self.user or "Unknown (new?) user",
            formats.date_format(self.active_from_to.lower),
        )
        if self.active_from_to.upper is not None:
            text += f" stopped at {formats.date_format(self.active_from_to.upper)}"
        else:
            text += " (active)"
        return text
