from django.urls import path

from .feeds import LatestPostsFeed, SectionPostsFeed
from .views import public, studio

app_name = "blog"

urlpatterns = [
    path("", public.home, name="home"),
    path("feed/", LatestPostsFeed(), name="feed"),
    path("search/", public.search, name="search"),
    path("post/<str:slug>/", public.post, name="post"),
    path("preview/<int:pk>/", public.preview, name="preview"),
    path("section/<str:section>/", public.section, name="section"),
    path("section/<str:section>/feed/", SectionPostsFeed(), name="section_feed"),
    path("section/<str:section>/<str:category>/", public.category, name="category"),
    path("tag/<str:tag>/", public.tag, name="tag"),
    path("author/<str:author>/", public.author, name="author"),
    # «نوشته‌های من»: the authoring area (blog/views/studio.py).
    path("write/", studio.write_list, name="write"),
    path("write/new/", studio.write_new, name="write_new"),
    path("write/profile/", studio.write_profile, name="write_profile"),
    path("write/<int:pk>/", studio.write_edit, name="write_edit"),
    path("write/<int:pk>/image/", studio.write_image, name="write_image"),
    path("write/<int:pk>/<slug:action>/", studio.write_action, name="write_action"),
]
