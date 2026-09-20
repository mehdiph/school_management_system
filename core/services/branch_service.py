from django.core.exceptions import PermissionDenied

from school.models import Branch
from staff.models import BranchAccess
from supervisor.models.supervisor_profile import SupervisorProfile


class BranchService:
    """
    Handles branch selection and branch access.
    """

    SESSION_KEY = "current_branch_id"

    @classmethod
    def get_available_branches(cls, user):
        """
        Returns all branches that the user can access.
        """

        if not user.is_authenticated:
            return Branch.objects.none()

        # -------------------------
        # Superuser
        # -------------------------

        if user.is_superuser:
            return Branch.objects.filter(
                is_active=True
            )

        # -------------------------
        # Supervisor
        # -------------------------

        supervisor_branch = cls.get_supervisor_branch(user)

        if supervisor_branch:
            return Branch.objects.filter(
                pk=supervisor_branch.pk,
                is_active=True,
            )

        # -------------------------
        # Staff
        # -------------------------

        try:
            staff = user.staff_profile

            return (
                Branch.objects
                .filter(
                    staff_accesses__staff=staff,
                    is_active=True,
                )
                .distinct()
            )

        except Exception:
            pass

        # -------------------------
        # Student
        # -------------------------

        try:
            student = user.student_profile

            return (
                Branch.objects
                .filter(
                    school_classes__enrollments__student=student,
                    school_classes__enrollments__status="active",
                    is_active=True,
                )
                .distinct()
            )

        except Exception:
            pass

        return Branch.objects.none()
    
    @classmethod
    def get_supervisor_branch(cls, user):
        try:
            supervisor = SupervisorProfile.objects.select_related(
                "branch"
            ).get(user=user)
        except SupervisorProfile.DoesNotExist:
            return None

        if supervisor.branch and supervisor.branch.is_active:
            return supervisor.branch

        return None


    @classmethod
    def get_user_default_branch(cls, user):
        """
        Returns user's default branch based on user type.
        """

        if not user.is_authenticated:
            return None

        # -------------------------
        # Superuser
        # -------------------------

        if user.is_superuser:
            return (
                Branch.objects
                .filter(is_active=True)
                .order_by("id")
                .first()
            )

        # -------------------------
        # Supervisor
        # -------------------------

        supervisor_branch = cls.get_supervisor_branch(user)

        if supervisor_branch:
            return supervisor_branch

        # -------------------------
        # Staff
        # -------------------------

        try:
            staff = user.staff_profile

            access = (
                BranchAccess.objects
                .select_related("branch")
                .filter(
                    staff=staff,
                    is_default=True,
                    branch__is_active=True,
                )
                .first()
            )

            if access:
                return access.branch

            access = (
                BranchAccess.objects
                .select_related("branch")
                .filter(
                    staff=staff,
                    branch__is_active=True,
                )
                .first()
            )

            if access:
                return access.branch

        except Exception:
            pass

        # -------------------------
        # Student
        # -------------------------

        try:
            student = user.student_profile

            enrollment = (
                student.enrollments
                .select_related(
                    "school_class__branch"
                )
                .filter(
                    status="active"
                )
                .first()
            )

            if enrollment:
                return enrollment.school_class.branch

        except Exception:
            pass

        return None


    @classmethod
    def get_default_branch(cls, user):
        """
        Backward compatible alias.
        """

        return cls.get_user_default_branch(user)



    @classmethod
    def get_current_branch(cls, request):
        """
        Returns currently selected branch.
        """

        if not request.user.is_authenticated:
            return None


        branch_id = request.session.get(
            cls.SESSION_KEY
        )


        if branch_id:

            branch = (
                cls.get_available_branches(
                    request.user
                )
                .filter(
                    id=branch_id
                )
                .first()
            )

            if branch:
                return branch



        branch = cls.get_user_default_branch(
            request.user
        )


        if branch:
            request.session[
                cls.SESSION_KEY
            ] = branch.id


        return branch



    @classmethod
    def change_branch(cls, request, branch_id):
        """
        Changes current branch.
        """

        branch = (
            cls.get_available_branches(
                request.user
            )
            .filter(
                id=branch_id
            )
            .first()
        )


        if branch is None:
            raise PermissionDenied(
                "You don't have access to this branch."
            )


        request.session[
            cls.SESSION_KEY
        ] = branch.id


        return branch



    @classmethod
    def has_access(cls, user, branch):
        """
        Returns True if user has access to branch.
        """

        return (
            cls.get_available_branches(user)
            .filter(
                id=branch.id
            )
            .exists()
        )