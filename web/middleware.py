from django.contrib.auth.middleware import LoginRequiredMiddleware
from django.core.exceptions import PermissionDenied


class SuperuserRequiredMiddleware(LoginRequiredMiddleware):
    def process_view(self, request, view_func, view_args, view_kwargs):
        if (
            request.user.is_authenticated
            and getattr(view_func, 'login_required', True)
            and not (request.user.is_active and request.user.is_superuser)
        ):
            raise PermissionDenied('Доступ разрешен только администраторам.')
        return super().process_view(request, view_func, view_args, view_kwargs)
