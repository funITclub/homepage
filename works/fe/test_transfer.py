"""hirahira_room から成績を持ってくる仕組み（fe.transfer）のテスト。

fe/tests.py は hirahira_room のものと差分を合わせ続けるので、funitclub にしか
無いこの仕組みのテストは、別のファイルに分けてある。

読む側のデータベースは用意できないので、こちらのテーブルを「読む側」に見立てて
読む（テーブル名を差し替えられるようにしてある）。読んだ内容を、消したり変えたり
したあとのこちらへ書き戻して、元に戻ることを確かめる。
"""

import datetime
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connections
from django.test import TestCase
from django.utils import timezone

from . import transfer
from .importer import sync, validate
from .learning import start_round
from .models import (Attempt, Category, CategoryProgress, DailyProgress, Learner,
                     LearningItem, LearningNote, LearningRound, PassReport,
                     Question, StudySession)
from .tests import answer, build_notes, build_questions, make_learner, seed_masters
from .transfer import TransferError, apply, read_source

CODE = 'hirahiratriangle'

# こちらのテーブルを「読む側」に見立てる
LOCAL_TABLES = {
    'learner': Learner._meta.db_table,
    'category': Category._meta.db_table,
    'question': Question._meta.db_table,
    'attempt': Attempt._meta.db_table,
    'progress': CategoryProgress._meta.db_table,
    'daily': DailyProgress._meta.db_table,
    'session': StudySession._meta.db_table,
    'note': LearningNote._meta.db_table,
    'round': LearningRound._meta.db_table,
    'item': LearningItem._meta.db_table,
    'pass_report': PassReport._meta.db_table,
}


def read(code=CODE):
    return read_source('default', code, tables=LOCAL_TABLES)


def snapshot(learner):
    """その ID の成績を、主キーに依らない形で写し取る。前後を比べるのに使う。"""
    return {
        'attempts': list(
            Attempt.objects.filter(learner=learner).order_by('answered_at', 'id')
            .values_list('question__stem', 'category__code', 'selected_index',
                         'is_correct', 'elapsed_ms', 'answered_at')
        ),
        'progress': list(
            CategoryProgress.objects.filter(learner=learner).order_by('category__code', 'subject')
            .values_list('category__code', 'subject', 'answered', 'correct', 'last_answered_at')
        ),
        'daily': list(
            DailyProgress.objects.filter(learner=learner).order_by('date')
            .values_list('date', 'answered', 'correct')
        ),
        'session': list(
            StudySession.objects.filter(learner=learner)
            .values_list('mode', 'subject', 'category__code')
        ),
        'pass_report': list(
            PassReport.objects.filter(learner=learner).values_list('passed_on', 'reported_at')
        ),
        'rounds': [
            (r.note.title if r.note else None, r.subject, r.reading_seconds, r.phase,
             r.position, r.started_at, r.finished_at,
             list(r.items.values_list('question__stem', 'order', 'selected_index', 'is_correct')))
            for r in LearningRound.objects.filter(learner=learner).order_by('started_at', 'id')
        ],
    }


class TransferTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_masters()
        build_questions()
        sync(validate({'questions': None, 'notes': build_notes()}))

    def setUp(self):
        """運営の ID に、ひととおりの成績を作る。"""
        self.learner = make_learner(CODE, is_admin=True)
        questions = list(Question.objects.filter(subject='A')[:6])
        for index, question in enumerate(questions):
            attempt = answer(self.learner, question, correct=index % 2 == 0)
            # 解いた日時は過去のもの。持ってきたあとも、流した時刻に化けないこと
            Attempt.objects.filter(pk=attempt.pk).update(
                answered_at=timezone.now() - datetime.timedelta(days=10 - index),
                elapsed_ms=1000 + index,
            )
        session, _ = StudySession.objects.get_or_create(learner=self.learner)
        session.mode = StudySession.MODE_CATEGORY
        session.category = Category.objects.get(code=11)
        session.save()
        PassReport.objects.create(learner=self.learner, passed_on=datetime.date(2026, 6, 1))

        note = LearningNote.objects.filter(category__code=11).first()
        self.round = start_round(self.learner, session, 5, note=note)
        item = self.round.items.first()
        item.selected_index = 0
        item.is_correct = False
        item.save()
        LearningRound.objects.filter(pk=self.round.pk).update(
            started_at=timezone.now() - datetime.timedelta(days=3)
        )

    def test_the_grades_come_back_as_they_were(self):
        """読んだ内容を書き戻すと、消したり変えたりする前の成績に戻る。"""
        before = snapshot(self.learner)
        self.assertTrue(before['attempts'] and before['progress'] and before['daily'])
        self.assertTrue(before['rounds'] and before['rounds'][0][7])
        payload = read()

        # こちらの成績が、あちらと食い違った状態にする
        Attempt.objects.filter(learner=self.learner).delete()
        CategoryProgress.objects.filter(learner=self.learner).update(answered=99, correct=99)
        DailyProgress.objects.filter(learner=self.learner).delete()
        LearningRound.objects.filter(learner=self.learner).delete()
        PassReport.objects.filter(learner=self.learner).delete()
        StudySession.objects.filter(learner=self.learner).update(mode=StudySession.MODE_FOCUS)

        counts = apply(payload)

        self.assertEqual(snapshot(self.learner), before)
        self.assertEqual(counts['attempts'], len(before['attempts']))
        self.assertEqual(counts['attempts_skipped'], 0)
        self.assertEqual(counts['rounds'], 1)

    def test_running_it_twice_does_not_count_twice(self):
        payload = read()
        apply(payload)
        once = snapshot(self.learner)
        apply(payload)
        self.assertEqual(snapshot(self.learner), once)

    def test_other_ids_are_not_touched(self):
        """ほかの ID の成績にも、全員で共有する問題・技術解説にも触らない。"""
        other = make_learner('someone_else')
        temporary = Learner.objects.create(code=None)
        for learner in (other, temporary):
            for question in Question.objects.filter(subject='A')[:3]:
                answer(learner, question, correct=True)
            StudySession.objects.create(learner=learner, mode=StudySession.MODE_RANDOM)
        PassReport.objects.create(learner=other, passed_on=datetime.date(2026, 5, 1))
        start_round(other, StudySession.objects.get(learner=other), 5,
                    note=LearningNote.objects.filter(category__code=11).first())

        others_before = {l.pk: snapshot(l) for l in (other, temporary)}
        learners_before = list(Learner.objects.order_by('pk').values_list(
            'pk', 'code', 'is_admin', 'created_at', 'last_seen_at'))
        questions_before = list(Question.objects.order_by('pk').values_list('pk', 'updated_at'))
        notes_before = list(LearningNote.objects.order_by('pk').values_list('pk', 'title'))

        apply(read())

        for learner in (other, temporary):
            self.assertEqual(snapshot(learner), others_before[learner.pk])
        self.assertEqual(list(Learner.objects.order_by('pk').values_list(
            'pk', 'code', 'is_admin', 'created_at', 'last_seen_at')), learners_before)
        self.assertEqual(
            list(Question.objects.order_by('pk').values_list('pk', 'updated_at')),
            questions_before)
        self.assertEqual(
            list(LearningNote.objects.order_by('pk').values_list('pk', 'title')), notes_before)

    def test_only_the_allowed_id_can_be_pulled(self):
        """決めた ID 以外は、読むことも書くこともしない。"""
        other = make_learner('someone_else')
        answer(other, Question.objects.first(), correct=True)
        before = snapshot(other)

        with self.assertRaises(TransferError):
            read('someone_else')

        payload = read()
        payload['code'] = 'someone_else'
        with self.assertRaises(TransferError):
            apply(payload)
        self.assertEqual(snapshot(other), before)

    def test_the_command_refuses_other_ids_before_opening_the_database(self):
        make_learner('someone_else')
        with self.assertRaises(CommandError) as raised:
            call_command('fe_pull_learner', 'someone_else', '--source-db', 'whatever',
                         stdout=StringIO())
        self.assertIn('持ってこられません', str(raised.exception))
        self.assertNotIn(transfer.SOURCE_ALIAS, connections.settings)

    def test_the_command_needs_the_source_database_name(self):
        with self.assertRaises(CommandError) as raised:
            call_command('fe_pull_learner', CODE, '--source-db', '', stdout=StringIO())
        self.assertIn('--source-db', str(raised.exception))

    def test_dry_run_writes_nothing(self):
        payload = read()
        Attempt.objects.filter(learner=self.learner).delete()
        before = snapshot(self.learner)

        counts = apply(payload, dry_run=True)

        self.assertEqual(snapshot(self.learner), before)
        self.assertEqual(counts['attempts'], len(payload['attempts']))
        self.assertEqual(counts['rounds'], 1)

    def test_dry_run_does_not_create_the_id(self):
        payload = read()
        Learner.objects.filter(code=CODE).delete()
        apply(payload, dry_run=True)
        self.assertFalse(Learner.objects.filter(code=CODE).exists())

    def test_the_id_is_created_when_missing(self):
        """こちらに ID がまだ無ければ作る。管理用の印は付けない。"""
        payload = read()
        Learner.objects.filter(code=CODE).delete()

        apply(payload)

        learner = Learner.objects.get(code=CODE)
        self.assertFalse(learner.is_admin)
        self.assertEqual(
            Attempt.objects.filter(learner=learner).count(), len(payload['attempts']))

    def test_the_admin_mark_is_kept(self):
        apply(read())
        self.assertTrue(Learner.objects.get(code=CODE).is_admin)

    def test_answers_to_questions_missing_here_are_skipped(self):
        """こちらに無い問題への解答は移さない。問題も足さない。理解度は移る。"""
        payload = read()
        payload['attempts'][0]['question'] = ('A', 11, 'こちらには無い問題文')
        payload['rounds'][0]['items'][0]['question'] = ('A', 11, 'こちらには無い問題文')
        question_total = Question.objects.count()

        counts = apply(payload)

        self.assertEqual(counts['attempts_skipped'], 1)
        self.assertEqual(counts['attempts'], len(payload['attempts']) - 1)
        self.assertEqual((counts['rounds'], counts['rounds_skipped']), (0, 1))
        self.assertEqual(counts['progress'], len(payload['progress']))
        self.assertEqual(Question.objects.count(), question_total)
        self.assertFalse(LearningRound.objects.filter(learner=self.learner).exists())

    def test_a_missing_id_in_the_source_is_reported(self):
        Learner.objects.filter(code=CODE).delete()
        with self.assertRaises(TransferError) as raised:
            read()
        self.assertIn('読む側に', str(raised.exception))

    def test_the_source_is_the_same_server_with_another_database_name(self):
        """読む側は、こちらと同じ接続でデータベース名だけが違う。settings には残さない。"""
        try:
            alias = transfer.open_source('another_database')
            config = connections.settings[alias]
            self.assertEqual(config['NAME'], 'another_database')
            self.assertEqual(config['ENGINE'], connections.settings['default']['ENGINE'])
            self.assertNotEqual(connections.settings['default']['NAME'], 'another_database')
        finally:
            connections.settings.pop(transfer.SOURCE_ALIAS, None)
