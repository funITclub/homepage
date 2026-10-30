# 学習の画面のページビュー（PageViewCount）。hirahira_room の 0022 にあたる。
# 0021（X 投稿）は funitclub では取り込んでいない。

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fe', '0006_mail_subscription'),
    ]

    operations = [
        migrations.CreateModel(
            name='PageViewCount',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(verbose_name='日付')),
                ('page', models.CharField(max_length=30, verbose_name='画面')),
                ('with_id', models.BooleanField(verbose_name='ID あり')),
                ('count', models.PositiveIntegerField(default=0, verbose_name='件数')),
            ],
            options={
                'verbose_name': 'FE ページビュー',
                'verbose_name_plural': 'FE ページビュー',
                'db_table': 'funitclub_fe_page_view_count',
                'ordering': ['-date', 'page'],
                'constraints': [models.UniqueConstraint(fields=('date', 'page', 'with_id'), name='funitclub_fe_unique_pageview')],
            },
        ),
    ]
