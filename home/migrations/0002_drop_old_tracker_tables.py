# WG のアプリの名前を変えたときに、使われなくなったテーブルを落とす。
#
# wg-protein のチケット管理は tracker から protein_tracker に改名した（ほかの WG にも
# tracker があると、アプリ名・テンプレート・URL がぶつかって起動できないため）。
# 新しい名前でテーブルを作り直したので、古い funitclub_tracker_* は誰も使わない。
#
# 本番の DB は VNet の中にあって外から触れないので、起動時に走るマイグレーション
# （startup.sh の migrate）で落とす。
#
# 念のため、古いアプリがまだ読み込まれているときは何もしない。取り込みの順番が
# 入れ替わっても、動いているテーブルを消さないため。

from django.db import migrations

# 参照している側（issue）から先に落とす
OLD_TABLES = ['funitclub_tracker_issue', 'funitclub_tracker_project']


def drop_old_tables(apps, schema_editor):
    from django.apps import apps as registry

    if registry.is_installed('tracker'):
        print('  tracker アプリがまだ入っているので、古いテーブルは落としません')
        return

    with schema_editor.connection.cursor() as cursor:
        for table in OLD_TABLES:
            cursor.execute(f'DROP TABLE IF EXISTS {table}')
        # 改名前のアプリの記録も消す（showmigrations に残らないように）
        cursor.execute("DELETE FROM django_migrations WHERE app = 'tracker'")


class Migration(migrations.Migration):

    dependencies = [('home', '0001_initial')]

    operations = [
        migrations.RunPython(drop_old_tables, migrations.RunPython.noop),
    ]
