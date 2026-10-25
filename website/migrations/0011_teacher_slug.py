# The teacher list no longer belongs to the landing page (both public pages
# read it), and every card now has a slug. Separate from 0010 so that no
# PostgreSQL transaction both updates rows and alters the table.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('website', '0010_seed_teachers'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='landingteacher',
            name='page',
        ),
        migrations.AlterField(
            model_name='landingteacher',
            name='slug',
            field=models.SlugField(allow_unicode=True, blank=True, help_text='اگر خالی باشد، از نام ساخته می\u200cشود و بعد از آن با تغییر نام عوض نمی\u200cشود. لینک مستقیم به این معلم: /teachers/#نامک', max_length=80, unique=True, verbose_name='نامک (برای لینک)'),
        ),
    ]
