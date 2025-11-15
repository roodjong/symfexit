from django.utils.translation import gettext_lazy as _

from symfexit.emails._templates.base import WrapperLayout


class BaseLayout(WrapperLayout):
    label = _("layout")
    code = "Layout template"
