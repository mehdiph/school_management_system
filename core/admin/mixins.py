"""
Shared admin behaviour for branch-scoped models.

Every admin whose rows belong to a branch mixes
:class:`BranchScopedAdminMixin` in, so the "which branches may this user
see" question is answered in exactly one place --
``core.services.access`` -- for list pages *and* for the foreign key
dropdowns on the change form. Superusers are never restricted.
"""

from django.contrib import admin

from core.services import access


class BranchScopedAdminMixin:
    """
    Restricts an admin's queryset and its foreign key dropdowns to the
    branches the logged-in user may see.

    Subclasses declare:

    ``branch_lookup``
        the ORM path from *this* model to ``school.Branch``
        (e.g. ``"branch"``, ``"school_class__branch"``).

    ``related_branch_lookups``
        ``{"<fk field name>": "<path from the related model to Branch>"}``
        for the dropdowns that must be narrowed too. ``""`` means the
        related model *is* ``Branch``.
    """

    branch_lookup = "branch"
    related_branch_lookups = {}

    def accessible_branch_ids(self, request):
        return access.get_accessible_branch_ids(request.user, request=request)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)

        if request.user.is_superuser:
            return queryset

        return queryset.filter(
            **{
                f"{self.branch_lookup}__in":
                    self.accessible_branch_ids(request)
            }
        ).distinct()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        lookup = self.related_branch_lookups.get(db_field.name)

        if lookup is not None and not request.user.is_superuser:
            queryset = kwargs.get("queryset")

            if queryset is None:
                queryset = db_field.remote_field.model._default_manager.all()

            filter_path = f"{lookup}__in" if lookup else "id__in"

            kwargs["queryset"] = queryset.filter(
                **{filter_path: self.accessible_branch_ids(request)}
            ).distinct()

        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class EffectiveBranchesMixin:
    """
    A read-only "شعبه‌های مؤثر" field showing the branches a person can
    actually reach and *why* (explicit access / teaching / supervising /
    studying), so an admin never has to guess where access came from.

    Subclasses implement :meth:`get_user_for_branch_access`.
    """

    def get_user_for_branch_access(self, obj):
        raise NotImplementedError

    @admin.display(description="شعبه‌های مؤثر")
    def effective_branches(self, obj):
        if obj is None or obj.pk is None:
            return "-"

        user = self.get_user_for_branch_access(obj)

        if user is None:
            return "-"

        rows = access.describe_branch_access(user)

        if not rows:
            return "بدون دسترسی"

        return " | ".join(
            f"{branch.name} ({'، '.join(sources)})"
            for branch, sources in rows
        )
