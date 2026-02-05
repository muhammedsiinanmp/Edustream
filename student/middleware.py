
class PublicAccessMiddleware:
    def __init__(self,get_response):
        self.get_response = get_response

        self.PUBLIC_PATHS = [
            '/',
            '/student/login/',
            '/student/register/'
        ]

        self.PUBLIC_PREFIXES = [
            '/static/',
            '/media/',
            '/admin/',
        ]

    def __call__(self, request):
        path = request.path

        for prefix in self.PUBLIC_PREFIXES:
            if path.startswith(prefix):
                return self.get_response(request)
            
        if not request.user.is_authenticated:
            if path not in self.PUBLIC_PATHS:
                from django.shortcuts import redirect
                return redirect('/')
        
        return self.get_response(request)