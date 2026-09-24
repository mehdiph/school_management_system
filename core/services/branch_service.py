"""
Branch selection (which branch is the user *currently looking at*).

"Which branches may this user see at all" is not decided here -- that is
``core.services.access``, the single source of truth. This class only
sits on top of it: it remembers the picked branch in the session and
validates any branch change against the accessible set.
"""

from django.core.exceptions import PermissionDenied

from core.services import access


class BranchService:
    """
    Handles branch selection and branch access.
    """

    SESSION_KEY = "current_branch_id"

    @classmethod
    def get_available_branches(cls, user, request=None):
        """
        Returns all branches that the user can access.
        """

        return access.get_accessible_branches(user, request=request)

    @classmethod
    def get_user_default_branch(cls, user, request=None):
        """
        Returns user's default branch based on user type.
        """

        return access.get_default_branch(user, request=request)

    @classmethod
    def get_default_branch(cls, user, request=None):
        """
        Backward compatible alias.
        """

        return cls.get_user_default_branch(user, request=request)

    @classmethod
    def get_current_branch(cls, request):
        """
        Returns currently selected branch.
        """

        if not request.user.is_authenticated:
            return None

        branch_id = request.session.get(cls.SESSION_KEY)

        if branch_id:

            branch = (
                cls.get_available_branches(request.user, request=request)
                .filter(id=branch_id)
                .first()
            )

            if branch:
                return branch

        branch = cls.get_user_default_branch(request.user, request=request)

        if branch:
            request.session[cls.SESSION_KEY] = branch.id

        return branch

    @classmethod
    def change_branch(cls, request, branch_id):
        """
        Changes current branch.
        """

        branch = (
            cls.get_available_branches(request.user, request=request)
            .filter(id=branch_id)
            .first()
        )

        if branch is None:
            raise PermissionDenied(
                "You don't have access to this branch."
            )

        request.session[cls.SESSION_KEY] = branch.id

        return branch

    @classmethod
    def has_access(cls, user, branch, request=None):
        """
        Returns True if user has access to branch.
        """

        return access.has_branch_access(user, branch, request=request)
