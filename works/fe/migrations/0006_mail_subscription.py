# 問題メールの登録。hirahira_room では 0017〜0020 の4本（平文で作ってから暗号化へ移す）
# だが、こちらは平文の列を持ったことがないので、暗号文の列で作る1本にまとめてある。

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fe', '0005_learning_round_pause'),
    ]

    operations = [
        migrations.CreateModel(
            name='MailSubscription',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email_enc', models.TextField(blank=True, editable=False, verbose_name='配信先（暗号化）')),
                ('pending_email_enc', models.TextField(blank=True, editable=False, verbose_name='確認待ちのアドレス（暗号化）')),
                ('link_sent_at', models.DateTimeField(blank=True, null=True, verbose_name='確認・解除のメールを送った日時')),
                ('marathon', models.BooleanField(default=False, verbose_name='マラソン')),
                ('marathon_position', models.PositiveIntegerField(default=0, verbose_name='マラソンの次の位置')),
                ('marathon_laps', models.PositiveIntegerField(default=0, verbose_name='マラソンの周回数')),
                ('marathon_sent_on', models.DateField(blank=True, null=True, verbose_name='マラソンを最後に送った日')),
                ('training', models.BooleanField(default=False, verbose_name='特訓')),
                ('training_topics', models.JSONField(blank=True, default=list, verbose_name='特訓の小分類')),
                ('training_index', models.PositiveIntegerField(default=0, verbose_name='特訓の次の小分類')),
                ('training_offset', models.PositiveIntegerField(default=0, verbose_name='特訓の小分類の中の次の位置')),
                ('training_sent_on', models.DateField(blank=True, null=True, verbose_name='特訓を最後に送った日')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='作成日時')),
                ('learner', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='mail_subscription', to='fe.learner', verbose_name='ID')),
            ],
            options={
                'db_table': 'funitclub_fe_mail_subscription',
                'verbose_name': 'FE メール配信',
                'verbose_name_plural': 'FE メール配信',
            },
        ),
    ]
