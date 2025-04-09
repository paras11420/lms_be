from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse
from django.conf import settings
from django.conf.urls.static import static

def home(request):
    return HttpResponse("Welcome to the Library Management System!")

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('library.urls')),  # All API URLs start with /api/
    path('', home),  # Optional: A simple home page
]

# Serve media files during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
