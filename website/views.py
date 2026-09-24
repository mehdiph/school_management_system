from django.db.models import Prefetch, prefetch_related_objects
from django.shortcuts import render

from .models import FeatureCard, HeroSlide, LandingPage, LandingTeacher, LearningPoint


def website(request):
    page = LandingPage.load()

    # One query per enabled section; disabled sections cost nothing.
    sections = [
        ("show_hero_slider", "slides", HeroSlide.objects.all()),
        ("show_features", "features", FeatureCard.objects.all()),
        ("show_learning", "learning_points", LearningPoint.objects.all()),
        ("show_teachers", "teachers", LandingTeacher.objects.select_related("teacher__staff__user")),
    ]
    lookups = [
        Prefetch(relation, queryset=queryset.filter(is_active=True), to_attr=f"active_{relation}")
        for flag, relation, queryset in sections
        if getattr(page, flag)
    ]
    prefetch_related_objects([page], *lookups)

    context = {"page": page}
    for flag, relation, _ in sections:
        context[relation] = getattr(page, f"active_{relation}", [])

    return render(request, "website/index.html", context)
