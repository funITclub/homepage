# WG のチケット管理を活動ページに移したので、使われなくなったテーブルを落とす。
#
# wg-protein・wg-welfare は、資料と <WG>_tracker を活動ページ <WG>_activity に
# まとめた（funITclub/claude-plugins の wg-activity）。チケットのデータは引き継がず、
# funitclub_<WG>_activity_* で作り直したので、古い funitclub_<WG>_tracker_* は誰も使わない。
#
# 本番の DB は VNet の中にあって外から触れないので、起動時に走るマイグレーション
# （startup.sh の migrate）で落とす（0002 と同じ）。
#
# 念のため、古いアプリがまだ読み込まれているときは、そのアプリの分は何もしない。
# 本番ではアプリが wg.<名前> として入るので、名前ではなく呼び名（label）で見る。

from django.db import migrations

# 呼び名 → 落とすテーブル（参照している側の issue から先に）
OLD_APPS = {
    'protein_tracker': ['funitclub_protein_tracker_issue', 'funitclub_protein_tracker_project'],
    'welfare_tracker': ['funitclub_welfare_tracker_issue', 'funitclub_welfare_tracker_project'],
}


def drop_old_tables(apps, schema_editor):
    from django.apps import apps as registry

    loaded = {config.label for config in registry.get_app_configs()}
    with schema_editor.connection.cursor() as cursor:
        for label, tables in OLD_APPS.items():
            if label in loaded:
                print(f'  {label} アプリがまだ入っているので、古いテーブルは落としません')
                continue
            for table in tables:
                cursor.execute(f'DROP TABLE IF EXISTS {table}')
            # 古いアプリの記録も消す（showmigrations や権限の一覧に残らないように）
            cursor.execute('DELETE FROM django_migrations WHERE app = %s', [label])
            cursor.execute(
                'DELETE FROM auth_permission WHERE content_type_id IN '
                '(SELECT id FROM django_content_type WHERE app_label = %s)', [label])
            cursor.execute('DELETE FROM django_content_type WHERE app_label = %s', [label])


class Migration(migrations.Migration):

    dependencies = [
        ('home', '0002_drop_old_tracker_tables'),
        ('auth', '0012_alter_user_first_name_max_length'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.RunPython(drop_old_tables, migrations.RunPython.noop),
    ]
