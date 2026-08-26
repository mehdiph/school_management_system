from core.services.branch_service import BranchService


class BranchMiddleware:
    """
    Attaches the current branch to the request.

    request.branch -> Branch | None
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        request.branch = None

        if request.user.is_authenticated:
            request.branch = BranchService.get_current_branch(request)

        response = self.get_response(request)

        return response