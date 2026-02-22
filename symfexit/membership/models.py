from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _


class MembershipType(models.Model):
    enabled = models.BooleanField(_("enabled"), default=True)
    name = models.CharField(_("name"), max_length=100)
    description = models.TextField(_("description"), blank=True)
    slug = models.SlugField(_("slug"), unique=True)
    allow_custom_amount = models.BooleanField(_("allow custom amount"), default=False)
    custom_amount_product = models.ForeignKey(
        "payments.Product",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_("custom amount product"),
        help_text=_(
            "Product used when a member chooses a custom amount. Required when custom amount is allowed."
        ),
    )
    position = models.PositiveIntegerField(_("position"), default=0)

    class Meta:
        ordering = ["position", "name"]
        verbose_name = _("membership type")
        verbose_name_plural = _("membership types")

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.allow_custom_amount and not self.custom_amount_product:
            raise ValidationError(
                {
                    "custom_amount_product": _(
                        "This field is required when custom amount is allowed."
                    ),
                }
            )


class MembershipTier(models.Model):
    membership_type = models.ForeignKey(
        MembershipType,
        on_delete=models.CASCADE,
        related_name="tiers",
        verbose_name=_("membership type"),
    )
    enabled = models.BooleanField(_("enabled"), default=True)
    name = models.CharField(_("name"), max_length=255)
    product = models.OneToOneField(
        "payments.Product",
        on_delete=models.PROTECT,
        verbose_name=_("product"),
    )
    position = models.PositiveIntegerField(_("position"), default=0)

    class Meta:
        ordering = ["membership_type", "position"]
        verbose_name = _("membership tier")
        verbose_name_plural = _("membership tiers")

    def __str__(self):
        return self.name

    def price_cents(self):
        return self.product.price_cents()

    def price_euros(self):
        return self.product.price_euros
