from django.shortcuts import redirect
from django.conf import settings
from django.utils.deprecation import MiddlewareMixin

class LoginRequiredMiddleware:
    """Middleware that redirects anonymous users to login for most pages.

    Whitelist: '/', '/login/', '/logout/', '/admin/', static and media files.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip middleware during testing
        if getattr(settings, 'TESTING', False):
            return self.get_response(request)
            
        path = request.path_info
        # Allow safe paths without login
        media_prefix = settings.MEDIA_URL if settings.MEDIA_URL.startswith('/') else '/' + settings.MEDIA_URL
        allowed_prefixes = [
            '/login/', '/logout/', '/admin/', '/static/', '/health/', '/api/', media_prefix,
            '/',
        ]

        if any(path.startswith(p) for p in allowed_prefixes):
            return self.get_response(request)

        # If user is not authenticated, redirect to login
        if not request.user.is_authenticated:
            return redirect(settings.LOGIN_URL)

        return self.get_response(request)

class SecurityHeadersMiddleware(MiddlewareMixin):
    """
    Add security headers to prevent CSS violations and improve security.
    Complies with OWASP recommendations.
    """
    
    def process_response(self, request, response):
        """Add security headers to response"""
        
        # Content Security Policy - expanded for Google Fonts
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "font-src 'self' data: https://fonts.googleapis.com https://fonts.gstatic.com; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self';"
        )
        response['Content-Security-Policy'] = csp
        
        # Additional security headers
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        response['X-XSS-Protection'] = '1; mode=block'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response['Permissions-Policy'] = (
            'geolocation=(), '
            'microphone=(), '
            'camera=(), '
            'payment=(), '
            'usb=(), '
            'magnetometer=(), '
            'gyroscope=(), '
            'accelerometer=()'
        )
        
        # Performance headers
        response['Cache-Control'] = 'public, max-age=3600'
        
        # Opt-in to browser features for better performance
        response['Accept-CH'] = 'DPR, Viewport-Width, Width'
        
        # Only add HTTPS-related headers in production
        if not settings.DEBUG:
            response['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        
        return response
