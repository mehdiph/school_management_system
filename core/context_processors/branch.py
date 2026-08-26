from core.services.branch_service import BranchService


def branch_context(request):
    """
    Provides branch related data to all templates.
    """

    context = {
        "current_branch": None,
        "available_branches": [],
    }

    if not request.user.is_authenticated:
        return context

    context["current_branch"] = getattr(
        request,
        "branch",
        None
    )

    context["available_branches"] = (
        BranchService
        .get_available_branches(request.user)
    )

    return context