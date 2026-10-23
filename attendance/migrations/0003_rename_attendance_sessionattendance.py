"""
The teacher's per-session attendance becomes the archive ``SessionAttendance``.

State only: the table name is pinned to ``attendance_attendance`` first, so
``RenameModel`` renames nothing in the database, and the other changes
(reverse names, verbose names) are not database changes. Every row stays
as it is.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0002_initial'),
        ('student', '0001_initial'),
        ('teaching', '0001_initial'),
    ]

    operations = [
        migrations.AlterModelTable(
            name='attendance',
            table='attendance_attendance',
        ),
        migrations.RenameModel(
            old_name='Attendance',
            new_name='SessionAttendance',
        ),
        migrations.AlterModelOptions(
            name='sessionattendance',
            options={
                'ordering': ['-session__date', 'student_enrollment__student__user__last_name', 'student_enrollment__student__user__first_name'],
                'verbose_name': 'حضور و غیاب جلسه (بایگانی)',
                'verbose_name_plural': 'حضور و غیاب جلسه‌ها (بایگانی)',
            },
        ),
        migrations.AlterField(
            model_name='sessionattendance',
            name='session',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='session_attendances', to='teaching.schoolsession', verbose_name='جلسه'),
        ),
        migrations.AlterField(
            model_name='sessionattendance',
            name='student_enrollment',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='session_attendances', to='student.studentenrollment', verbose_name='ثبت‌نام دانش‌آموز'),
        ),
    ]
