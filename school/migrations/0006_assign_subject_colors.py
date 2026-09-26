"""
Gives every existing subject its own colour.

Subjects whose slug the old stylesheet knew (``.class-math`` ...) keep
the hue they were shown in; the rest get the next unused palette colour,
in id order. The palette is copied here on purpose so this migration
keeps doing the same thing if ``school.colors`` changes later.

Reversing is a no-op: 0005 removes the column itself.
"""

from django.db import migrations

PALETTE = (
    "#2563eb", "#15803d", "#c2410c", "#7c3aed", "#db2777", "#0f766e", "#a16207",
    "#dc2626", "#0e7490", "#4f46e5", "#4d7c0f", "#b45309", "#9333ea", "#475569",
)

KNOWN_SLUGS = {
    "math": "#2563eb",
    "science": "#15803d",
    "oloom": "#15803d",
    "farsi": "#c2410c",
    "computer": "#7c3aed",
    "art": "#db2777",
    "honar": "#db2777",
    "varzesh": "#0f766e",
    "qoran": "#a16207",
    "motaleat": "#9333ea",
    "negaresh": "#dc2626",
}


def assign_colors(apps, schema_editor):
    Subject = apps.get_model("school", "Subject")
    subjects = list(Subject.objects.order_by("id"))

    used = set()
    for subject in subjects:
        color = KNOWN_SLUGS.get(subject.slug)
        if color and color not in used:
            subject.color = color
            used.add(color)
        else:
            subject.color = None

    free = [c for c in PALETTE if c not in used]
    for i, subject in enumerate(s for s in subjects if s.color is None):
        # Once all 14 are taken, cycle -- still valid, just not unique.
        subject.color = free[i] if i < len(free) else PALETTE[i % len(PALETTE)]

    Subject.objects.bulk_update(subjects, ["color"])


class Migration(migrations.Migration):

    dependencies = [
        ("school", "0005_subject_color"),
    ]

    operations = [
        migrations.RunPython(assign_colors, migrations.RunPython.noop),
    ]
