"""hirahira_room の fe から、運営の ID の成績を持ってきて、こちらの同じ ID を置き換える。

画面からは使えない。運営が App Service の SSH から手で流す（手元からは DB に届かない）。
hirahira_room のデータベースは読むだけで、書き込まない。

    python manage.py fe_pull_learner hirahiratriangle --source-db <hirahira_room の DB 名> --dry-run
    python manage.py fe_pull_learner hirahiratriangle --source-db <hirahira_room の DB 名>

持ってこられる ID は fe.transfer.ALLOWED_CODES にあるものだけ。ほかの ID は読まず、
こちらのほかの ID の成績にも、全員で共有する問題・技術解説にも触らない。

--source-db の代わりに、環境変数 FE_SOURCE_DB に入れておいてもよい。
こちらの同じ ID の成績は、丸ごと置き換わる（こちらで解いたぶんは消える）。
先に --dry-run で件数を確かめること。くわしくは fe/transfer.py と fe/README.md。
"""

import os

from django.core.management.base import BaseCommand, CommandError

from fe.transfer import TransferError, apply, check_code, open_source, read_source


class Command(BaseCommand):
    help = 'hirahira_room の fe から、運営の ID の成績を持ってきて置き換える。'

    def add_arguments(self, parser):
        parser.add_argument('code', help='持ってくる ID。両方のアプリで同じ ID を使う。')
        parser.add_argument(
            '--source-db', default=os.environ.get('FE_SOURCE_DB', ''),
            help='hirahira_room のデータベース名（既定は環境変数 FE_SOURCE_DB）。',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='書き込まずに、移る件数だけを表示する。',
        )

    def handle(self, *args, **options):
        code = options['code'].strip().lower()
        try:
            # データベースを開く前に断る
            check_code(code)
        except TransferError as exc:
            raise CommandError(str(exc))

        source_db = options['source_db']
        if not source_db:
            raise CommandError(
                'hirahira_room のデータベース名を --source-db で指定してください。'
            )

        try:
            payload = read_source(open_source(source_db), code)
        except TransferError as exc:
            raise CommandError(str(exc))

        dry_run = options['dry_run']
        counts = apply(payload, dry_run=dry_run)

        self.stdout.write('ID「{}」（読む側のデータベース: {}）'.format(code, source_db))
        self.stdout.write('  分野別の理解度   {} 件'.format(counts['progress']))
        self.stdout.write('  日別の学習記録   {} 件'.format(counts['daily']))
        self.stdout.write('  解答履歴         {} 件（こちらに無い問題のため移せないもの {} 件）'.format(
            counts['attempts'], counts['attempts_skipped']))
        self.stdout.write('  学習モード       {} ラウンド（問題がそろわず移せないもの {} ラウンド）'.format(
            counts['rounds'], counts['rounds_skipped']))
        self.stdout.write('  合格の申告       {} 件'.format(counts['pass_report']))

        if dry_run:
            self.stdout.write('書き込んでいません。--dry-run を外すと、この内容で置き換えます。')
        else:
            self.stdout.write(self.style.SUCCESS('この内容で、こちらの成績を置き換えました。'))
