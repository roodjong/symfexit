from django.http import HttpResponseRedirect


def current_style(request):
    # Redirect to the currently applied style
    return HttpResponseRedirect(request.theme.get_absolute_url())
