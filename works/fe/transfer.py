"""hirahira_room の fe アプリから、運営の ID の成績を持ってくる。

funitclub の fe は hirahira_room の fe の移植で、データベースは別だが、同じ
PostgreSQL サーバーの上にあり、接続のユーザーも同じ。そこで、hirahira_room の
データベースを読み取り専用で開き、決まった ID の成績を読んで、こちらの同じ ID の
成績を丸ごと置き換える。

画面からは使えない。運営が manage.py fe_pull_learner で手で流す。
何度流しても同じ結果になる（足し込まずに置き換えるので、二重に数えない）。
こちらで解いたぶんは消える。

**持ってこられる ID は ALLOWED_CODES に書いたものだけ。** ほかの ID は読まず、
こちらのほかの ID の成績にも、全員で共有する問題・技術解説にも触らない。
書き込むのは、その ID に紐づく行だけである。

内部の番号（主キー）は2つのデータベースで別なので、番号では突き合わせない。
  ・分類は分類番号（Category.code）
  ・問題は取り込みと同じ鍵（科目・分類番号・問題文。importer.question_key）
  ・技術解説も取り込みと同じ鍵（分類番号・見出し。importer.note_key）
こちらに無い問題への解答は移せないので、件数を数えて知らせる（問題は足さない）。
分野別の理解度と日別の学習記録は問題に依らないので、問題集が違っていても移る。
"""

import datetime

from django.db import connections, transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from .importer import note_key, question_key
from .models import (Attempt, Category, CategoryProgress, DailyProgress, Learner,
                     LearningItem, LearningNote, LearningRound, PassReport,
                     Question, StudySession)

# 持ってきてよい ID。運営が両方のアプリで使っている ID だけを書く。
# ID には合言葉がなく、同じ文字列でも別の人のことがあるので、広げない。
ALLOWED_CODES = frozenset({'hirahiratriangle'})

# 読む側の接続の名前。settings.DATABASES には書かず、流すときだけ足す。
SOURCE_ALIAS = 'fe_source'

# hirahira_room の fe のテーブル名。あちらは db_table を指定していないので、
# Django の既定の名前（アプリ名_モデル名）になっている。
SOURCE_TABLES = {
    'learner': 'fe_learner',
    'category': 'fe_category',
    'question': 'fe_question',
    'attempt': 'fe_attempt',
    'progress': 'fe_categoryprogress',
    'daily': 'fe_dailyprogress',
    'session': 'fe_studysession',
    'note': 'fe_learningnote',
    'round': 'fe_learninground',
    'item': 'fe_learningitem',
    'pass_report': 'fe_passreport',
}


class TransferError(Exception):
    """持ってこられなかった理由。コマンドがそのまま表示する。"""


def check_code(code):
    if code not in ALLOWED_CODES:
        raise TransferError(
            'ID「{}」は持ってこられません。持ってこられるのは {} だけです。'.format(
                code, '・'.join(sorted(ALLOWED_CODES))
            )
        )


def open_source(name):
    """同じサーバーの別のデータベースを、読み取り専用で開く。

    接続の情報はこちらの default と同じで、データベース名だけを差し替える。
    PostgreSQL では、書き込みを接続の側でも禁じておく（こちらのコードは
    SELECT しか出さないが、取り違えても書けないようにするため）。
    """
    config = dict(connections.settings['default'])
    config['NAME'] = name
    if config['ENGINE'].endswith('postgresql'):
        options = dict(config.get('OPTIONS') or {})
        options['options'] = '-c default_transaction_read_only=on'
        config['OPTIONS'] = options
    connections.settings[SOURCE_ALIAS] = config
    return SOURCE_ALIAS


def _rows(alias, sql, params):
    with connections[alias].cursor() as cursor:
        cursor.execute(sql, params)
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _datetime(value):
    """日時の列。SQLite は文字列で、タイムゾーンなしの UTC で返す。"""
    if isinstance(value, str):
        value = parse_datetime(value)
    if value is not None and timezone.is_naive(value):
        value = timezone.make_aware(value, datetime.timezone.utc)
    return value


def _date(value):
    return parse_date(value) if isinstance(value, str) else value


def _bool(value):
    return None if value is None else bool(value)


def read_source(alias, code, tables=SOURCE_TABLES):
    """読む側のデータベースから、その ID の成績を主キーに依らない形で取り出す。

    どの問い合わせも、その ID の learner_id で絞る。ほかの ID の行は読まない。
    """
    check_code(code)
    t = tables
    learners = _rows(alias, 'SELECT id FROM {learner} WHERE code = %s'.format(**t), [code])
    if not learners:
        raise TransferError('読む側に ID「{}」がありません。'.format(code))
    learner_id = learners[0]['id']

    # 問題を突き合わせる鍵（科目・分類番号・問題文）
    question_columns = 'q.subject AS q_subject, qc.code AS q_category, q.stem AS q_stem'
    question_joins = (
        'JOIN {question} q ON q.id = x.question_id '
        'JOIN {category} qc ON qc.id = q.category_id'
    ).format(**t)

    def question(row):
        return (row['q_subject'], row['q_category'], row['q_stem'])

    attempts = _rows(alias, (
        'SELECT x.selected_index, x.is_correct, x.elapsed_ms, x.answered_at, '
        'c.code AS category, ' + question_columns + ' '
        'FROM {attempt} x JOIN {category} c ON c.id = x.category_id ' + question_joins + ' '
        'WHERE x.learner_id = %s ORDER BY x.answered_at, x.id'
    ).format(**t), [learner_id])

    progress = _rows(alias, (
        'SELECT c.code AS category, p.subject, p.answered, p.correct, p.last_answered_at '
        'FROM {progress} p JOIN {category} c ON c.id = p.category_id '
        'WHERE p.learner_id = %s ORDER BY c.code, p.subject'
    ).format(**t), [learner_id])

    daily = _rows(alias, (
        'SELECT date, answered, correct FROM {daily} WHERE learner_id = %s ORDER BY date'
    ).format(**t), [learner_id])

    sessions = _rows(alias, (
        'SELECT s.mode, s.subject, c.code AS category '
        'FROM {session} s LEFT JOIN {category} c ON c.id = s.category_id '
        'WHERE s.learner_id = %s'
    ).format(**t), [learner_id])

    reports = _rows(alias, (
        'SELECT passed_on, reported_at FROM {pass_report} WHERE learner_id = %s'
    ).format(**t), [learner_id])

    rounds = _rows(alias, (
        'SELECT r.id, r.subject, r.reading_seconds, r.phase, r.position, '
        'r.started_at, r.finished_at, nc.code AS note_category, n.title AS note_title '
        'FROM {round} r LEFT JOIN {note} n ON n.id = r.note_id '
        'LEFT JOIN {category} nc ON nc.id = n.category_id '
        'WHERE r.learner_id = %s ORDER BY r.started_at, r.id'
    ).format(**t), [learner_id])

    items = _rows(alias, (
        'SELECT x.round_id, x."order" AS position, x.selected_index, x.is_correct, '
        + question_columns + ' '
        'FROM {item} x JOIN {round} r ON r.id = x.round_id ' + question_joins + ' '
        'WHERE r.learner_id = %s ORDER BY x.round_id, x."order"'
    ).format(**t), [learner_id])
    items_by_round = {}
    for row in items:
        items_by_round.setdefault(row['round_id'], []).append({
            'order': row['position'],
            'selected_index': row['selected_index'],
            'is_correct': _bool(row['is_correct']),
            'question': question(row),
        })

    return {
        'code': code,
        'session': sessions[0] if sessions else None,
        'progress': [{
            'category': row['category'], 'subject': row['subject'],
            'answered': row['answered'], 'correct': row['correct'],
            'last_answered_at': _datetime(row['last_answered_at']),
        } for row in progress],
        'daily': [{
            'date': _date(row['date']), 'answered': row['answered'], 'correct': row['correct'],
        } for row in daily],
        'pass_report': {
            'passed_on': _date(reports[0]['passed_on']),
            'reported_at': _datetime(reports[0]['reported_at']),
        } if reports else None,
        'attempts': [{
            'category': row['category'],
            'selected_index': row['selected_index'],
            'is_correct': bool(row['is_correct']),
            'elapsed_ms': row['elapsed_ms'],
            'answered_at': _datetime(row['answered_at']),
            'question': question(row),
        } for row in attempts],
        'rounds': [{
            'subject': row['subject'],
            'reading_seconds': row['reading_seconds'],
            'phase': row['phase'],
            'position': row['position'],
            'started_at': _datetime(row['started_at']),
            'finished_at': _datetime(row['finished_at']),
            'note': (row['note_category'], row['note_title']) if row['note_title'] else None,
            'items': items_by_round.get(row['id'], []),
        } for row in rounds],
    }


def apply(payload, dry_run=False):
    """読んだ成績で、こちらの同じ ID の成績を置き換える。件数を返す。

    書き込むのは、その ID に紐づく行だけ。ID が無ければ作る。管理用の印
    （is_admin）はこちらのものを保ち、あちらからは持ってこない。
    dry_run なら数えるだけで、何も書かない。
    """
    check_code(payload['code'])
    with transaction.atomic():
        counts = _apply(payload, write=not dry_run)
    return counts


def _apply(payload, write):
    code = payload['code']
    categories = {c.code: c for c in Category.objects.all()}
    questions = {
        question_key(q.subject, q.category.code, q.stem): q
        for q in Question.objects.select_related('category')
    }
    notes = {
        note_key(n.category.code, n.title): n
        for n in LearningNote.objects.select_related('category')
    }

    def find_question(key):
        return questions.get(question_key(*key))

    counts = {
        'attempts': 0, 'attempts_skipped': 0,
        'progress': 0, 'daily': 0,
        'rounds': 0, 'rounds_skipped': 0,
        'pass_report': 0,
    }

    learner = None
    if write:
        learner, _created = Learner.objects.get_or_create(code=code)
        # 置き換え。足し込むと、流すたびに二重に数えてしまう。
        # どれも learner で絞ってあり、ほかの ID の行には届かない。
        Attempt.objects.filter(learner=learner).delete()
        CategoryProgress.objects.filter(learner=learner).delete()
        DailyProgress.objects.filter(learner=learner).delete()
        LearningRound.objects.filter(learner=learner).delete()
        PassReport.objects.filter(learner=learner).delete()
        StudySession.objects.filter(learner=learner).delete()

    for row in payload['progress']:
        category = categories.get(row['category'])
        if category is None:
            continue
        counts['progress'] += 1
        if write:
            CategoryProgress.objects.create(
                learner=learner, category=category, subject=row['subject'],
                answered=row['answered'], correct=row['correct'],
                last_answered_at=row['last_answered_at'],
            )

    for row in payload['daily']:
        counts['daily'] += 1
        if write:
            DailyProgress.objects.create(
                learner=learner, date=row['date'],
                answered=row['answered'], correct=row['correct'],
            )

    session = payload['session']
    if session and write:
        valid_modes = {choice[0] for choice in StudySession.MODE_CHOICES}
        StudySession.objects.create(
            learner=learner,
            mode=session['mode'] if session['mode'] in valid_modes else StudySession.MODE_FOCUS,
            subject=session['subject'],
            category=categories.get(session['category']),
        )

    report = payload['pass_report']
    if report:
        counts['pass_report'] = 1
        if write:
            PassReport.objects.create(learner=learner, passed_on=report['passed_on'])
            # reported_at は auto_now_add なので、作ってから書き戻す
            PassReport.objects.filter(learner=learner).update(reported_at=report['reported_at'])

    for row in payload['attempts']:
        question = find_question(row['question'])
        category = categories.get(row['category'])
        if question is None or category is None:
            counts['attempts_skipped'] += 1
            continue
        counts['attempts'] += 1
        if write:
            attempt = Attempt.objects.create(
                learner=learner, question=question, category=category,
                selected_index=row['selected_index'], is_correct=row['is_correct'],
                elapsed_ms=row['elapsed_ms'],
            )
            # answered_at は auto_now_add なので、作ってから書き戻す
            Attempt.objects.filter(pk=attempt.pk).update(answered_at=row['answered_at'])

    for row in payload['rounds']:
        found = [(item, find_question(item['question'])) for item in row['items']]
        # ラウンドは「読んだ範囲をそのまま解く」ひとまとまり。1問でも欠けると
        # 結果の画面の問数が合わなくなるので、そろわないラウンドは移さない。
        if any(question is None for _item, question in found):
            counts['rounds_skipped'] += 1
            continue
        counts['rounds'] += 1
        if not write:
            continue
        note = notes.get(note_key(*row['note'])) if row['note'] else None
        round_ = LearningRound.objects.create(
            learner=learner, note=note, subject=row['subject'],
            reading_seconds=row['reading_seconds'], phase=row['phase'],
            position=row['position'], finished_at=row['finished_at'],
        )
        LearningRound.objects.filter(pk=round_.pk).update(started_at=row['started_at'])
        LearningItem.objects.bulk_create([
            LearningItem(
                round=round_, question=question, order=item['order'],
                selected_index=item['selected_index'], is_correct=item['is_correct'],
            )
            for item, question in found
        ])

    return counts
