from django.urls import path

from .feeds import LatestPostsFeed, SectionPostsFeed
from .views import public

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
]
