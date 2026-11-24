"""FE 対策アプリのテスト。

このアプリで壊れると痛いのは次の3点なので、そこを重点的に確かめる。
  ・重点出題が本当に苦手分野へ寄るか（統計的に検証する）
  ・問題が ID ごとに分かれ、他人の問題が混ざらないか
  ・一括差し替えをしても解答履歴と分野別の正答率が残るか
"""

import io
import json
import random
import tempfile
from pathlib import Path
from unittest import mock
import html
import re
from urllib.parse import urlsplit

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import Sum
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from django.urls import reverse

from . import speech
from .exam import EXAM, build_prompt
from .generators import REGISTRY, generate_question
from .importer import (ImportError_, needs_confirmation, parse, preview, sync,
                       validate)
from .learning import note_menu, pick_note
from .models import (Attempt, Category, CategoryProgress, DailyProgress, Learner,
                     LearningNote, LearningRound, OpenProgress, PageViewCount, PassReport,
                     Question, QuestionTemplate, StudySession)
from .selection import (REVIEW_DUE_GAP, _due_for_review,
                        _last_result_map, _recent_answer_times, pick_question)
from .stats import (WEAK_MIN_ATTEMPTS, category_options, category_stats,
                    overall_stats,
                    record_progress, site_summary, smoothed_rate, weak_categories)
from django.core.signing import get_cookie_signer

from .views import LEARNER_COOKIE, LEARNER_COOKIE_SALT, SESSION_LEARNER


# このアプリ自身のテストでは、一覧からの導線（config/gate.py）を外す。
# 通行証はホームページの一覧から辿る仕掛けで、アプリの振る舞いとは別物のため
# （導線そのものは config/tests.py で確かめる）。
_gate_off = override_settings(GATE_BACK={})


def setUpModule():
    _gate_off.enable()


def tearDownModule():
    _gate_off.disable()



# React の画面（frontend/fe）のソース。画面の文言や部品の並びは、ここを読んで確かめる
FRONTEND = Path(__file__).resolve().parents[2] / 'frontend' / 'fe' / 'src'
FRONTEND_FILES = sorted(p.name for p in FRONTEND.glob('*.ts*'))


def frontend_source(name):
    return (FRONTEND / name).read_text(encoding='utf-8')


def api_get(client, name, *args, **params):
    """React の画面が呼ぶ API（fe:api_…）を GET する。"""
    return client.get(reverse('fe:' + name, args=args), params)


def api_post(client, name, data=None, *args):
    """React の画面が呼ぶ API（fe:api_…）に JSON を POST する。"""
    return client.post(reverse('fe:' + name, args=args), data or {}, content_type='application/json')


def put_learner(client, pk):
    """その ID で入った状態にする。セッションと、ブラウザを閉じたら消える Cookie の両方。"""
    session = client.session
    session[SESSION_LEARNER] = pk
    session.save()
    client.cookies[LEARNER_COOKIE] = get_cookie_signer(
        salt=LEARNER_COOKIE + LEARNER_COOKIE_SALT
    ).sign(str(pk))

def seed_masters():
    """中分類と問題テンプレートだけを投入する（問題は入らない）。"""
    call_command('seed_fe', verbosity=0)


def make_learner(code, is_admin=False):
    return Learner.objects.create(code=code, is_admin=is_admin)


def enter(client, learner):
    """その ID で入った状態にする。ID はアカウントとつながないので、ログインはしない。"""
    put_learner(client, learner.pk)


def login_editor(client):
    """問題の管理（/fe/console/）を開けるよう、編集画面のアカウントでログインする。ID は問わない。"""
    account, _ = get_user_model().objects.get_or_create(username='editor')
    client.force_login(account)


def dashboard(learner):
    """ダッシュボードの場所。ID の有無にかかわらず /fe/。URL に ID は出さない。"""
    return reverse('fe:index')


def build_questions(per_category=4):
    """テスト用の問題を全分類に作る。

    アプリは問題を同梱しないので、テストも配布物に依存させない。
    分類は科目ごとに別なので、その分類の科目に合わせて作る。
    科目Bは本番同様6択にする。
    """
    records = []
    for category in Category.objects.all():
        for i in range(per_category):
            is_subject_b = category.subject == Question.SUBJECT_B
            size = 6 if is_subject_b else 4
            records.append({
                'category': category.code,
                'subject': category.subject,
                'topic': category.name,
                'difficulty': 2,
                'stem': '{}の問題{}'.format(category.name, i),
                'choices': [
                    '選択肢{}-{}-{}'.format(j, category.code, i) for j in range(size)
                ],
                'answer': 0,
                'explanation': '解説',
                'source': 'テスト用',
            })
    return sync(validate({'questions': records, 'notes': None}))


def build_notes(codes=(9, 11), topic=None):
    """テスト用の技術解説。問題とは別に、概念を説明した文章として持たせる。"""
    notes = []
    for code in codes:
        category = Category.objects.get(code=code)
        notes.append({
            'category': code,
            'topic': topic if topic is not None else category.name,
            'title': '{}のしくみ'.format(category.name),
            'body': '{}について、定義からしくみまでを説明した文章。'.format(category.name),
            'source': 'シラバス',
        })
    return notes


def answer(learner, question, correct):
    """1問解いた状態を作る（解答ログと理解度の両方を更新する）。"""
    attempt = Attempt.objects.create(
        learner=learner, question=question, category=question.category,
        selected_index=question.answer_index if correct else 0, is_correct=correct,
    )
    record_progress(learner, question, correct)
    return attempt


class GeneratorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_masters()
        cls.learner = make_learner('gen')

    def test_all_templates_generate_valid_questions(self):
        for template in QuestionTemplate.objects.all():
            with self.subTest(template=template.key):
                rng = random.Random(template.key)
                for _ in range(30):
                    question = generate_question(template, rng=rng)
                    self.assertIsNotNone(question)
                    self.assertEqual(len(question.choices), 4)
                    self.assertEqual(len(set(question.choices)), 4)
                    self.assertEqual(question.category_id, template.category_id)

    def test_same_parameters_reuse_the_same_question(self):
        template = QuestionTemplate.objects.get(key='calc-availability-mtbf')
        first = generate_question(template, rng=random.Random(1))
        second = generate_question(template, rng=random.Random(1))
        self.assertEqual(first.id, second.id, '同じ数値なら同じ問題を使い回す')

    def test_generated_questions_are_shared_by_every_id(self):
        """問題は全 ID の共有なので、同じ数値なら誰が引いても同じ1問になる。"""
        template = QuestionTemplate.objects.get(key='calc-availability-mtbf')
        generate_question(template, rng=random.Random(2))
        generate_question(template, rng=random.Random(2))
        self.assertEqual(Question.objects.filter(template=template).count(), 1)

    def test_registry_and_templates_match(self):
        self.assertEqual(
            set(REGISTRY), set(QuestionTemplate.objects.values_list('key', flat=True))
        )


class StatsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_masters()
        cls.learner = make_learner('stats')
        build_questions()

    def test_smoothing_pulls_small_samples_toward_the_prior(self):
        self.assertAlmostEqual(smoothed_rate(0, 1), 3.0 / 6.0)
        self.assertGreater(smoothed_rate(0, 1), 0.4)
        self.assertLess(smoothed_rate(0, 100), 0.05)

    def test_weak_categories_need_a_minimum_number_of_attempts(self):
        security = Category.objects.get(code=11)
        question = Question.objects.filter(category=security).first()
        answer(self.learner, question, correct=False)
        rows = category_stats(self.learner)
        self.assertEqual(weak_categories(rows), [], '1問だけでは苦手判定しない')

    def test_category_stats_counts_correctly(self):
        security = Category.objects.get(code=11)
        questions = list(Question.objects.filter(category=security)[:4])
        for index, question in enumerate(questions):
            answer(self.learner, question, correct=index == 0)
        row = next(r for r in category_stats(self.learner) if r['category'] == security)
        self.assertEqual(row['total'], 4)
        self.assertEqual(row['correct'], 1)
        self.assertEqual(row['rate_percent'], 25)
        self.assertTrue(row['is_weak'])

    def test_other_ids_answers_do_not_count(self):
        """問題は共有でも、成績は ID ごと。ほかの ID の解答は数えない。"""
        other = make_learner('stats_other')
        security = Category.objects.get(code=11)
        answer(other, Question.objects.filter(category=security).first(), correct=True)
        row = next(r for r in category_stats(self.learner) if r['category'] == security)
        self.assertEqual(row['total'], 0)
        self.assertEqual(overall_stats(self.learner)['total'], 0)


class SelectionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_masters()
        cls.learner = make_learner('picker')
        build_questions()

    def _answer(self, category, correct, count):
        questions = list(Question.objects.filter(category=category)[:count])
        self.assertGreaterEqual(len(questions), 1)
        for index in range(count):
            answer(self.learner, questions[index % len(questions)], correct)

    def _session(self, mode, subject=Question.SUBJECT_A):
        session, _ = StudySession.objects.get_or_create(learner=self.learner)
        session.mode, session.subject, session.category = mode, subject, None
        session.save()
        return session

    def test_ipa_mode_serves_only_questions_published_by_ipa(self):
        """IPA公開問題のモードでは、自作も自動生成も出さない。"""
        category = Category.objects.get(code=4)
        sources = ['令和7年度 科目A 問2', 'サンプル問題 科目A 問8']
        for i, source in enumerate(sources):
            Question.objects.create(
                subject=Question.SUBJECT_A, category=category, topic=category.name,
                stem='IPA の問題{}'.format(i), choices=['あ', 'い', 'う', 'え'],
                answer_index=0, source=source,
            )
        session = self._session(StudySession.MODE_IPA)

        seen, exclude = set(), []
        for _ in range(12):
            question, _reason = pick_question(self.learner, session, exclude_ids=exclude)
            self.assertIsNotNone(question)
            self.assertIn(question.source, sources)
            self.assertFalse(question.is_generated)
            seen.add(question.source)
            exclude = [question.id]
        self.assertEqual(seen, set(sources))

    def test_restricting_mode_stays_inside_the_chosen_category(self):
        """IPA のモードで分野を選んだら、その分野の IPA の問題だけを出す。"""
        inside = Category.objects.get(code=4)
        outside = Category.objects.get(code=5)
        wanted = Question.objects.create(
            subject=Question.SUBJECT_A, category=inside, topic=inside.name,
            stem='分野の中の IPA の問題', choices=['あ', 'い', 'う', 'え'],
            answer_index=0, source='令和7年度 科目A 問2',
        )
        Question.objects.create(
            subject=Question.SUBJECT_A, category=outside, topic=outside.name,
            stem='別の分野の IPA の問題', choices=['あ', 'い', 'う', 'え'],
            answer_index=0, source='令和7年度 科目A 問3',
        )
        session = self._session(StudySession.MODE_IPA)
        session.category = inside
        session.save()

        for _ in range(6):
            question, _reason = pick_question(self.learner, session, exclude_ids=[wanted.id])
            self.assertEqual(question, wanted)

        # その分野に IPA の問題が無ければ、ほかへ広げずに「出せる問題なし」にする
        session.category = Category.objects.get(code=6)
        session.save()
        self.assertEqual(pick_question(self.learner, session), (None, None))

    def test_every_mode_stays_inside_the_chosen_category(self):
        """どのモードでも、分野を選んだらその分野の問題だけを出す。"""
        inside = Category.objects.get(code=4)
        for mode in (StudySession.MODE_FOCUS, StudySession.MODE_RANDOM,
                     StudySession.MODE_CATEGORY):
            with self.subTest(mode=mode):
                session = self._session(mode)
                session.category = inside
                session.save()
                exclude = []
                for _ in range(8):
                    question, _reason = pick_question(self.learner, session, exclude_ids=exclude)
                    self.assertIsNotNone(question)
                    self.assertEqual(question.category, inside)
                    exclude = [question.id]

    def test_weak_mode_without_weak_categories_serves_nothing(self):
        """苦手と判定した分野がまだ無ければ、おまかせに切り替えずに何も出さない。"""
        session = self._session(StudySession.MODE_WEAK)
        self.assertEqual(pick_question(self.learner, session), (None, None))

        # 苦手と判定された分野ができたら、その分野だけから出す。未着手の分野は出さない
        weak = Category.objects.get(code=4)
        self._answer(weak, False, WEAK_MIN_ATTEMPTS)
        for _ in range(8):
            question, _reason = pick_question(self.learner, session)
            self.assertEqual(question.category, weak)

    def test_review_without_misses_serves_nothing(self):
        """まちがえた問題が無ければ、おまかせに切り替えずに何も出さない。"""
        session = self._session(StudySession.MODE_REVIEW)
        self.assertEqual(pick_question(self.learner, session), (None, None))

        answer(self.learner, Question.objects.filter(category__code=4).first(), True)
        self.assertEqual(pick_question(self.learner, session), (None, None))

        missed = Question.objects.filter(category__code=5).first()
        answer(self.learner, missed, False)
        question, _reason = pick_question(self.learner, session, exclude_ids=[missed.id])
        self.assertEqual(question, missed)

    def test_weak_mode_serves_nothing_from_a_category_not_judged_weak(self):
        """苦手分野だけで分野を選んでも、苦手と判定していない分野からは出さない。"""
        inside = Category.objects.get(code=4)
        session = self._session(StudySession.MODE_WEAK)
        session.category = inside
        session.save()
        self.assertEqual(pick_question(self.learner, session), (None, None))

        # 苦手と判定されたら、その分野から出す
        self._answer(inside, False, WEAK_MIN_ATTEMPTS)
        for _ in range(6):
            question, _reason = pick_question(self.learner, session)
            self.assertEqual(question.category, inside)

    def test_review_serves_nothing_from_a_category_without_misses(self):
        """復習で分野を選び、その分野にまちがえた問題が無ければ、何も出さない。"""
        inside = Category.objects.get(code=4)
        answer(self.learner, Question.objects.filter(category=inside).first(), True)
        answer(self.learner, Question.objects.filter(category__code=5).first(), False)
        session = self._session(StudySession.MODE_REVIEW)
        session.category = inside
        session.save()
        self.assertEqual(pick_question(self.learner, session), (None, None))

    def test_review_in_a_category_serves_only_misses_from_it(self):
        """復習で分野を選んだら、その分野でまちがえた問題だけを復習する。"""
        inside = Category.objects.get(code=4)
        outside = Category.objects.get(code=5)
        missed_in = Question.objects.filter(category=inside).first()
        missed_out = Question.objects.filter(category=outside).first()
        answer(self.learner, missed_in, False)
        answer(self.learner, missed_out, False)

        session = self._session(StudySession.MODE_REVIEW)
        session.category = inside
        session.save()
        for _ in range(6):
            # 直前に出した問題として除外されていても、ほかへ広げずに同じ問題を出す
            question, reason = pick_question(self.learner, session, exclude_ids=[missed_in.id])
            self.assertEqual(question, missed_in)
            self.assertEqual(reason, '前回まちがえた問題')

    def test_ipa_mode_has_nothing_to_serve_without_ipa_questions(self):
        session = self._session(StudySession.MODE_IPA)
        self.assertEqual(pick_question(self.learner, session), (None, None))

    def test_calculation_is_told_from_the_shape_of_the_choices(self):
        """数量の形をした選択肢だけを計算問題とみなす。番号の付いた名前は当てない。"""
        stem = '稼働率 0.9 の装置 2 台を並列に接続したときの稼働率はどれか。'
        cases = [
            (['0.81', '0.90', '0.95', '0.99'], True),
            (['約 0.8', '約 2.3', '約 6.3', '約 18.9'], True),
            (['毎秒 25M バイト', '毎秒 100M バイト', '毎秒 400M バイト', '毎秒 4G バイト'], True),
            (['n(n−1)', 'n−1', 'n(n−1)/2', 'n の 2 乗'], True),
            (['RAID0', 'RAID1', 'RAID5', 'RAID6'], False),
            (['レベル1', 'レベル2', 'レベル3', 'レベル4'], False),
            (['第1正規形', '第2正規形', '第3正規形', '第4正規形'], False),
            (['2 台の装置に同じ内容を書き込む', '0.81', '0.90', '0.99'], False),
        ]
        for choices, expected in cases:
            self.assertEqual(
                Question(stem=stem, choices=choices).is_calculation, expected, choices
            )
        # 問題文に数字が無ければ、選択肢が数字でも計算問題とはみなさない
        self.assertFalse(
            Question(stem='適切なものはどれか。', choices=['1', '2', '3', '4']).is_calculation
        )

    def test_calc_mode_serves_only_calculation_questions(self):
        """計算問題のモードでは、数値で答える問題と自動生成だけを出す。"""
        category = Category.objects.get(code=4)
        Question.objects.create(
            subject=Question.SUBJECT_A, category=category, topic=category.name,
            stem='稼働率 0.9 の装置 2 台を直列に接続したときの稼働率はどれか。',
            choices=['0.81', '0.90', '0.95', '0.99'], answer_index=0, source='テスト用',
        )
        session = self._session(StudySession.MODE_CALC)

        exclude = []
        for _ in range(12):
            question, _reason = pick_question(self.learner, session, exclude_ids=exclude)
            self.assertIsNotNone(question)
            self.assertEqual(question.subject, Question.SUBJECT_A)
            self.assertTrue(question.is_calculation, question.stem)
            exclude = [question.id]

    def test_calc_mode_follows_the_chosen_subject(self):
        """科目Bを選んでいれば、科目Bの数値で答える問題だけを出す。自動生成は混ぜない。"""
        category = Category.objects.filter(subject=Question.SUBJECT_B).first()
        made = Question.objects.create(
            subject=Question.SUBJECT_B, category=category, topic=category.name,
            stem='関数 f(3) を呼び出したときの戻り値はどれか。',
            choices=['6', '7', '8', '9', '10', '11'], answer_index=0, source='テスト用',
        )
        session = self._session(StudySession.MODE_CALC, subject=Question.SUBJECT_B)
        for _ in range(6):
            question, _reason = pick_question(self.learner, session)
            self.assertEqual(question, made)

    def test_a_missed_question_is_not_repeated_immediately(self):
        """まちがえた直後に同じ問題を出さない。答えを覚えているだけになる。"""
        category = Category.objects.get(code=9)
        missed = Question.objects.filter(category=category).first()
        answer(self.learner, missed, correct=False)

        session = StudySession.objects.create(
            learner=self.learner, mode=StudySession.MODE_CATEGORY,
            subject=Question.SUBJECT_A, category=category,
        )
        random.seed(20260908)
        for _ in range(30):
            question, _reason = pick_question(self.learner, session)
            self.assertNotEqual(question.id, missed.id, '間をあけずに戻ってきた')

    def test_a_missed_question_comes_back_before_unseen_ones(self):
        """間隔があけば、未出題が残っていても復習が優先される。"""
        category = Category.objects.get(code=9)
        questions = list(Question.objects.filter(category=category))
        self.assertGreaterEqual(len(questions), 4)
        missed = questions[0]
        answer(self.learner, missed, correct=False)
        # ほかの問題を解いて間隔をあける
        for question in questions[1:]:
            answer(self.learner, question, correct=True)
        for _ in range(REVIEW_DUE_GAP):
            answer(self.learner, questions[1], correct=True)

        session = StudySession.objects.create(
            learner=self.learner, mode=StudySession.MODE_CATEGORY,
            subject=Question.SUBJECT_A, category=category,
        )
        random.seed(20260908)
        reasons = set()
        for _ in range(60):
            question, reason = pick_question(self.learner, session)
            if question.id == missed.id:
                reasons.add(reason)
        self.assertIn('まちがえた問題の復習', reasons, '間隔をあけても戻ってこなかった')

    def test_repeated_misses_shorten_the_interval(self):
        """何度も落とした問題ほど、短い間隔で戻す。"""
        category = Category.objects.get(code=9)
        questions = list(Question.objects.filter(category=category))
        once, twice = questions[0], questions[1]
        # 2回落とした方を先に、1回だけの方をあとに解く。
        # あとに解いたほうが間隔は短いので、間隔だけで並ぶなら once は戻らない。
        answer(self.learner, twice, correct=False)
        answer(self.learner, twice, correct=False)
        answer(self.learner, once, correct=False)
        for question in questions[2:]:
            answer(self.learner, question, correct=True)
        answer(self.learner, questions[2], correct=True)

        history = _last_result_map(self.learner, [once.id, twice.id])
        times = _recent_answer_times(self.learner)
        due = dict(
            (q.id, over) for q, over in
            _due_for_review([once, twice], history, times)
        )
        # 2回落とした方が先に期限を迎える
        self.assertIn(twice.id, due, '2回落とした問題は短い間隔で戻るべき')
        self.assertNotIn(once.id, due, '1回だけの問題はまだ間隔が足りない')

    def test_a_well_answered_category_is_not_listed_as_weak(self):
        """よく解けている分野は、何問解いていても苦手分野に並べない。"""
        good, bad = Category.objects.filter(subject='A')[:2]
        for category, results in ((good, [True] * 10), (bad, [False] * 4)):
            question = Question.objects.filter(category=category).first()
            for correct in results:
                answer(self.learner, question, correct)

        listed = [r['category'] for r in weak_categories(category_stats(self.learner))]
        self.assertEqual(listed, [bad])

    def test_focus_mode_favours_weak_categories(self):
        database = Category.objects.get(code=9)
        network = Category.objects.get(code=10)
        self._answer(database, correct=False, count=10)
        self._answer(network, correct=True, count=10)

        session = StudySession.objects.create(
            learner=self.learner, mode=StudySession.MODE_FOCUS, subject=Question.SUBJECT_A
        )
        random.seed(20260906)
        counts = {}
        for _ in range(600):
            question, _reason = pick_question(self.learner, session)
            counts[question.category.code] = counts.get(question.category.code, 0) + 1

        self.assertGreater(
            counts.get(9, 0), counts.get(10, 0),
            '想定出題数が少なくても、苦手なデータベースの方が多く出るべき',
        )

    def test_random_mode_follows_the_exam_ratio(self):
        session = StudySession.objects.create(
            learner=self.learner, mode=StudySession.MODE_RANDOM, subject=Question.SUBJECT_A
        )
        random.seed(11)
        counts = {}
        for _ in range(800):
            question, _reason = pick_question(self.learner, session)
            counts[question.category.code] = counts.get(question.category.code, 0) + 1
        self.assertGreater(counts.get(11, 0), counts.get(23, 0) * 2)

    def test_category_mode_stays_in_the_selected_category(self):
        database = Category.objects.get(code=9)
        session = StudySession.objects.create(
            learner=self.learner, mode=StudySession.MODE_CATEGORY,
            subject=Question.SUBJECT_A, category=database,
        )
        for _ in range(30):
            question, _reason = pick_question(self.learner, session)
            self.assertEqual(question.category_id, database.id)

    def test_subject_b_mode_only_returns_subject_b_questions(self):
        session = StudySession.objects.create(
            learner=self.learner, mode=StudySession.MODE_FOCUS, subject=Question.SUBJECT_B
        )
        for _ in range(30):
            question, _reason = pick_question(self.learner, session)
            self.assertEqual(question.subject, Question.SUBJECT_B)
            self.assertEqual(question.category.subject, Question.SUBJECT_B)
            self.assertIn(question.category.code, range(101, 106))

    def test_review_mode_returns_previously_wrong_questions(self):
        database = Category.objects.get(code=9)
        questions = list(Question.objects.filter(category=database)[:3])
        for question in questions:
            answer(self.learner, question, correct=False)
        session = StudySession.objects.create(
            learner=self.learner, mode=StudySession.MODE_REVIEW, subject=Question.SUBJECT_A
        )
        wrong_ids = {q.id for q in questions}
        for _ in range(20):
            question, _reason = pick_question(self.learner, session)
            self.assertIn(question.id, wrong_ids)

    def test_recently_shown_questions_are_avoided(self):
        session = StudySession.objects.create(
            learner=self.learner, mode=StudySession.MODE_FOCUS, subject=Question.SUBJECT_A
        )
        first, _ = pick_question(self.learner, session)
        for _ in range(20):
            question, _reason = pick_question(self.learner, session, exclude_ids=[first.id])
            self.assertNotEqual(question.id, first.id)

    def test_every_id_is_served_from_the_shared_set(self):
        other = make_learner('picker_other')
        session = StudySession.objects.create(
            learner=other, mode=StudySession.MODE_FOCUS, subject=Question.SUBJECT_A
        )
        question, _reason = pick_question(other, session)
        self.assertIsNotNone(question)

    def test_no_questions_yields_nothing_instead_of_crashing(self):
        Question.objects.all().delete()
        empty = make_learner('picker_empty')
        session = StudySession.objects.create(
            learner=empty, mode=StudySession.MODE_FOCUS, subject=Question.SUBJECT_B
        )
        question, reason = pick_question(empty, session)
        self.assertIsNone(question)
        self.assertIsNone(reason)


class ViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_masters()
        cls.learner = make_learner('viewer')
        build_questions()

    def setUp(self):
        enter(self.client, self.learner)

    def test_unsupported_formats_are_stated_up_front(self):
        """対応していない問題形式の注意書きは、「このアプリについて」に畳まずに出す（React の画面）。"""
        source = frontend_source('GuidePage.tsx')
        for word in ('このアプリが対応していない問題・問題形式', '図を見ないと解けない問題（自作の分）',
                     '本番どおりの模擬試験', '記述・入力・並べ替え'):
            with self.subTest(word=word):
                self.assertIn(word, source)

    def test_import_screen_states_what_cannot_be_rendered(self):
        """取り込み画面では、作る側が踏む制約も併せて示す。"""
        login_editor(self.client)
        html = self.client.get(reverse('fe:manage_upload')).content.decode('utf-8')
        self.assertIn('このアプリで出せない問題', html)
        for word in ('図は公開問題を転記するときだけ使えます', '上付き', '組合せを1つの選択肢'):
            self.assertIn(word, html)

    def test_prompt_states_unsupported_formats(self):
        """利用者が AI に渡すプロンプトにも、扱えない形式を書いておく。"""
        from .exam import build_prompt
        prompt = build_prompt()
        self.assertIn('【このアプリが扱えないもの】', prompt)
        for word in ('図は公開問題を転記するときだけ使う', '2のn乗', 'ルビ', '複数正解や部分点はない'):
            self.assertIn(word, prompt)

    def test_index_renders(self):
        """入れ物のページは、React の画面を読み込む。"""
        response = self.client.get(dashboard(self.learner))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="fe-root"')
        self.assertContains(response, 'fe/app/app.js')
        self.assertContains(response, 'data-api-url="/fe/api/"')

    def test_settings_offer_every_category_with_its_subject(self):
        """出題設定の API は、両科目の分類を科目つきで渡す。画面は選んだ科目のぶんだけ並べる。"""
        data = api_get(self.client, 'api_settings').json()
        self.assertEqual(len(data['categories']), Category.objects.count())
        subjects = {c['code']: c['subject'] for c in data['categories']}
        self.assertEqual(subjects[11], 'A')
        self.assertEqual(subjects[103], 'B')
        self.assertEqual({m['value'] for m in data['modes']},
                         {value for value, _ in StudySession.MODE_CHOICES})
        self.assertEqual([s['value'] for s in data['subjects']], ['A', 'B'])

    def test_category_options_carry_the_subject(self):
        """分類は科目ごとに別。画面で出し分けられるよう科目を添えている。"""
        options = {o['code']: o for o in category_options(self.learner)}
        self.assertEqual(options[11]['subject'], Question.SUBJECT_A, 'セキュリティは科目A')
        self.assertEqual(options[103]['subject'], Question.SUBJECT_B)
        self.assertFalse(
            set(range(1, 24)) & set(range(101, 106)),
            '科目Aと科目Bの分類番号は重ならない',
        )
        self.assertGreater(options[103]['question_count'], 0)

    def test_the_saved_category_is_returned_in_every_mode(self):
        """保存してある分野は、どのモードでもそのまま返す（どのモードでも分野が効くので）。"""
        session, _ = StudySession.objects.get_or_create(learner=self.learner)
        session.subject = Question.SUBJECT_A
        session.category = Category.objects.get(code=2)
        for mode, _label in StudySession.MODE_CHOICES:
            with self.subTest(mode=mode):
                session.mode = mode
                session.save()
                self.assertEqual(api_get(self.client, 'api_settings').json()['category'], 2)

        session.category = None
        session.save()
        self.assertIsNone(api_get(self.client, 'api_settings').json()['category'])

    def test_saving_returns_the_new_settings(self):
        """保存したら、変えたあとの設定を返す。画面はそれを映す（ダッシュボードはその場に留まる）。"""
        response = api_post(self.client, 'api_settings', {
            'mode': StudySession.MODE_RANDOM, 'subject': 'A', 'category': None,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['mode'], StudySession.MODE_RANDOM)
        self.assertEqual(response.json()['mode_label'], '本番の出題比率どおり')

    def test_a_category_from_the_other_subject_is_refused(self):
        """科目に無い分野を指定されたら受け付けず、設定も変えない。"""
        response = api_post(self.client, 'api_settings', {
            'mode': StudySession.MODE_CATEGORY, 'subject': 'A', 'category': 103,
        })
        self.assertEqual(response.status_code, 400)
        session = StudySession.objects.get(learner=self.learner)
        self.assertIsNone(session.category)
        self.assertEqual(session.mode, StudySession.MODE_FOCUS)

    def test_the_category_mode_needs_a_category(self):
        """「分野を指定」は分野が無いと成り立たないので、分野なしでは保存しない。"""
        response = api_post(self.client, 'api_settings', {
            'mode': StudySession.MODE_CATEGORY, 'subject': 'A', 'category': None,
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(StudySession.objects.get(learner=self.learner).mode, StudySession.MODE_FOCUS)

    def test_the_two_subjects_have_separate_categories(self):
        """科目Aだけの分類と科目Bだけの分類に分かれ、重なりが無いこと。"""
        a = set(Category.objects.filter(subject='A').values_list('code', flat=True))
        b = set(Category.objects.filter(subject='B').values_list('code', flat=True))
        self.assertEqual(len(a), 23)
        self.assertEqual(len(b), 5)
        self.assertFalse(a & b)
        self.assertEqual(
            sum(c.exam_weight for c in Category.objects.filter(subject='A')), 60,
            '科目Aの想定出題数の合計は本番の60問',
        )
        self.assertEqual(
            sum(c.exam_weight for c in Category.objects.filter(subject='B')), 20,
            '科目Bの想定出題数の合計は本番の20問',
        )

    def test_quiz_shows_a_question_and_grades_the_answer(self):
        data = api_get(self.client, 'api_quiz_next').json()
        question = Question.objects.get(pk=data['question']['id'])
        # 解答の前に正解と解説は渡さない
        self.assertNotIn('answer_index', data['question'])
        self.assertNotIn('explanation', data['question'])
        self.assertEqual([c['label'] for c in data['question']['choices']][:4], ['ア', 'イ', 'ウ', 'エ'])

        response = api_post(self.client, 'api_quiz_answer', {
            'question_id': question.id, 'choice': question.answer_index,
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['is_correct'])
        self.assertEqual(response.json()['answer_label'], question.answer_label)

        attempt = Attempt.objects.get(learner=self.learner, question=question)
        self.assertTrue(attempt.is_correct)
        self.assertEqual(attempt.category_id, question.category_id)

    def test_wrong_answer_is_recorded_and_explained(self):
        data = api_get(self.client, 'api_quiz_next').json()
        question = Question.objects.get(pk=data['question']['id'])
        wrong = (question.answer_index + 1) % len(question.choices)
        result = api_post(self.client, 'api_quiz_answer', {
            'question_id': question.id, 'choice': wrong,
        }).json()
        self.assertFalse(result['is_correct'])
        self.assertEqual(result['explanation'], '解説')
        self.assertEqual(result['selected_label'], Question.choice_label(wrong))
        self.assertFalse(Attempt.objects.get(learner=self.learner).is_correct)

    def test_double_submission_is_not_counted_twice(self):
        data = api_get(self.client, 'api_quiz_next').json()
        question = Question.objects.get(pk=data['question']['id'])
        payload = {'question_id': question.id, 'choice': question.answer_index}
        self.assertEqual(api_post(self.client, 'api_quiz_answer', payload).status_code, 200)
        self.assertEqual(api_post(self.client, 'api_quiz_answer', payload).status_code, 409)
        self.assertEqual(Attempt.objects.filter(learner=self.learner).count(), 1)

    def test_an_answer_outside_the_choices_is_refused(self):
        data = api_get(self.client, 'api_quiz_next').json()
        for choice in (None, '0', 99, True):
            with self.subTest(choice=choice):
                response = api_post(self.client, 'api_quiz_answer', {
                    'question_id': data['question']['id'], 'choice': choice,
                })
                self.assertEqual(response.status_code, 400)
        self.assertFalse(Attempt.objects.exists())

    def test_settings_change_the_study_session(self):
        response = api_post(self.client, 'api_settings', {
            'mode': StudySession.MODE_CATEGORY, 'subject': 'A', 'category': 11,
        })
        self.assertEqual(response.status_code, 200)
        session = StudySession.objects.get(learner=self.learner)
        self.assertEqual(session.mode, StudySession.MODE_CATEGORY)
        self.assertEqual(session.category.code, 11)

    def test_stats_and_history_render(self):
        for name in ('stats', 'history'):
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse('fe:' + name)).status_code, 200)
                self.assertEqual(api_get(self.client, 'api_' + name).status_code, 200)

    def test_stats_can_be_narrowed_to_a_subject(self):
        rows = api_get(self.client, 'api_stats', subject='B').json()['rows']
        self.assertEqual({r['subject'] for r in rows}, {'B'})
        rows = api_get(self.client, 'api_stats').json()['rows']
        self.assertEqual(len(rows), Category.objects.count())

    def test_history_lists_attempts_and_filters(self):
        questions = list(Question.objects.filter(category__code=11)[:2])
        answer(self.learner, questions[0], True)
        answer(self.learner, questions[1], False)
        data = api_get(self.client, 'api_history').json()
        self.assertEqual(data['count'], 2)
        wrong = api_get(self.client, 'api_history', result='wrong').json()['results']
        self.assertEqual([r['is_correct'] for r in wrong], [False])
        self.assertEqual(api_get(self.client, 'api_history', category='1').json()['count'], 0)

    def test_login_is_not_required_to_study(self):
        """学習の画面と API は、編集画面にログインしていなくても使える。"""
        self.client.logout()
        self.assertEqual(self.client.get(reverse('fe:index')).status_code, 200)
        for name in ('fe:index', 'fe:id_entry', 'fe:quiz', 'fe:learn_start',
                     'fe:stats', 'fe:history', 'fe:about'):
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        for name in ('api_me', 'api_dashboard', 'api_settings', 'api_quiz_next', 'api_stats',
                     'api_history', 'api_learn', 'api_guide'):
            with self.subTest(api=name):
                self.assertEqual(api_get(self.client, name).status_code, 200)

    def test_without_a_record_the_api_answers_401(self):
        """記録が無ければ 401。React は入口を開き直し、入口が記録を作る。"""
        client = self.client_class()
        for name in ('api_dashboard', 'api_settings', 'api_quiz_next', 'api_stats', 'api_history',
                     'api_learn', 'api_mail'):
            with self.subTest(api=name):
                self.assertEqual(api_get(client, name).status_code, 401)
        # 始めていなくても読めるもの
        self.assertEqual(api_get(client, 'api_me').json()['entered'], False)
        self.assertEqual(api_get(client, 'api_guide').status_code, 200)

    def test_pages_without_a_record_go_back_to_the_entrance(self):
        client = self.client_class()
        for name in ('fe:learn_start', 'fe:stats', 'fe:history'):
            with self.subTest(page=name):
                self.assertRedirects(client.get(reverse(name)), reverse('fe:index'),
                                     fetch_redirect_response=False)
        for name in ('fe:id_entry', 'fe:about'):
            with self.subTest(page=name):
                self.assertEqual(client.get(reverse(name)).status_code, 200)

    def test_old_guide_url_moves_to_about(self):
        """「このアプリについて」は /fe/about/。以前の /fe/guide/ は新しい URL へ送る。"""
        client = self.client_class()
        self.assertEqual(reverse('fe:about'), '/fe/about/')
        self.assertRedirects(client.get('/fe/guide/'), '/fe/about/', status_code=301,
                             fetch_redirect_response=False)

    def test_the_quiz_starts_without_a_record(self):
        """1問1答は問題メールからの案内先。始めていなければ、ID なしの記録を作ってそのまま開く。"""
        client = self.client_class()
        response = client.get(reverse('fe:quiz'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(LEARNER_COOKIE, response.cookies)
        learner = Learner.objects.get(code__isnull=True)
        self.assertEqual(client.session[SESSION_LEARNER], learner.pk)
        self.assertIsNotNone(api_get(client, 'api_quiz_next').json()['question'])
        # 開き直しても記録は増えない。ID で入っている人はその ID のまま
        client.get(reverse('fe:quiz'))
        self.assertEqual(Learner.objects.filter(code__isnull=True).count(), 1)
        self.assertEqual(self.client.get(reverse('fe:quiz')).status_code, 200)
        self.assertEqual(api_get(self.client, 'api_me').json()['code'], 'viewer')

    def test_the_dashboard_shows_my_records_only_with_an_id(self):
        """ID があれば、ダッシュボードに自分の成績（総合・苦手分野・未着手・分野別・直近14日）を出す。
        ID なしでは出さない。「1問1答」「学習モード」のボタンは、集計の下に置く。"""
        security = Question.objects.filter(category__code=11)[:3]
        for question in security:
            answer(self.learner, question, False)
        personal = api_get(self.client, 'api_dashboard').json()['personal']
        self.assertEqual(personal['overall']['total'], 3)
        self.assertEqual([w['code'] for w in personal['weak']], [11])
        self.assertNotIn(11, [c['code'] for c in personal['untouched']])
        self.assertEqual(len(personal['daily']), 14)
        self.assertEqual(sum(f['total'] for f in personal['fields']), 3)

        client = self.client_class()
        client.get(reverse('fe:index'))
        self.assertIsNone(api_get(client, 'api_dashboard').json()['personal'])

        source = frontend_source('Dashboard.tsx')
        self.assertLess(source.index('<PersonalStats'), source.index('<Summary'))
        self.assertLess(source.index('<Summary'), source.index('<MailSection'))

    def test_the_dashboard_has_no_quiz_or_learning_buttons(self):
        """ダッシュボードには出題設定も「1問1答」「学習モード」のボタンも置かない
        （plan&check の計画の中分類か、ヘッダーのメニューから開く）。
        出題設定は1問1答の画面の上の「出題設定」から開く右のサイドバーにある。"""
        source = frontend_source('Dashboard.tsx')
        for word in ('SettingsForm', 'to="/quiz/"', 'to="/learn/"'):
            with self.subTest(word=word):
                self.assertNotIn(word, source)
        quiz = frontend_source('QuizPage.tsx')
        # 出題設定は、上の「出題設定」から開く右のサイドバー（Drawer）にある
        self.assertIn('<Drawer open={setting}', quiz)
        self.assertIn('onClick={() => setSetting(true)}', quiz)

    def test_writing_needs_the_csrf_token(self):
        """ログインしていなくても、書き込みは CSRF トークンを確かめる。"""
        client = self.client_class(enforce_csrf_checks=True)
        enter(client, self.learner)
        response = api_post(client, 'api_settings', {'mode': StudySession.MODE_RANDOM, 'subject': 'A'})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(StudySession.objects.filter(
            learner=self.learner, mode=StudySession.MODE_RANDOM).exists())

        # 入れ物のページが配る csrftoken を載せれば通る
        client.get(reverse('fe:quiz'))
        token = client.cookies['csrftoken'].value
        response = client.post(
            reverse('fe:api_settings'), {'mode': StudySession.MODE_RANDOM, 'subject': 'A'},
            content_type='application/json', headers={'X-CSRFToken': token},
        )
        self.assertEqual(response.status_code, 200)

    def test_login_is_still_required_to_manage(self):
        """ログインしていなければ管理画面は開けず、ログイン画面へ送る。"""
        self.client.logout()
        for name in ('fe:manage_list', 'fe:manage_upload'):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse('edit:login'), response['Location'])
        self.assertEqual(self.client.post(reverse('fe:manage_upload'), {}).status_code, 302)


class NewModeSettingsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_masters()
        cls.learner = make_learner('modes')
        build_questions()

    def setUp(self):
        enter(self.client, self.learner)

    def save(self, mode, subject='A', category=None):
        return api_post(self.client, 'api_settings', {'mode': mode, 'subject': subject, 'category': category})

    def test_calc_mode_keeps_the_chosen_subject(self):
        """計算問題のモードでも、科目はAとBのどちらも選べる。"""
        for subject in ('B', 'A'):
            self.save(StudySession.MODE_CALC, subject)
            session = StudySession.objects.get(learner=self.learner)
            self.assertEqual(session.mode, StudySession.MODE_CALC)
            self.assertEqual(session.subject, subject)

    def test_ipa_mode_keeps_the_chosen_subject(self):
        self.save(StudySession.MODE_IPA, 'B')
        session = StudySession.objects.get(learner=self.learner)
        self.assertEqual(session.mode, StudySession.MODE_IPA)
        self.assertEqual(session.subject, Question.SUBJECT_B)

    def test_restricting_modes_keep_the_chosen_category(self):
        """対象を絞る2つのモードでは、分野も選べる。選ばなくてもよい。"""
        for mode in (StudySession.MODE_IPA, StudySession.MODE_CALC):
            self.save(mode, 'A', 4)
            session = StudySession.objects.get(learner=self.learner)
            self.assertEqual((session.mode, session.category.code), (mode, 4))

            self.save(mode, 'A', '')
            session = StudySession.objects.get(learner=self.learner)
            self.assertEqual((session.mode, session.category), (mode, None))

    def test_every_mode_keeps_the_chosen_category(self):
        """分野はどのモードでも保存される。選ばなければ保存されない。"""
        for mode, _label in StudySession.MODE_CHOICES:
            with self.subTest(mode=mode):
                self.save(mode, 'A', 4)
                session = StudySession.objects.get(learner=self.learner)
                self.assertEqual((session.mode, session.category.code), (mode, 4))

        self.save(StudySession.MODE_FOCUS, 'A', None)
        self.assertIsNone(StudySession.objects.get(learner=self.learner).category)

    def test_category_counts_follow_the_mode(self):
        """分野の件数は、そのモードで出せる問題の数にする。"""
        category = Category.objects.get(code=4)
        Question.objects.create(
            subject=Question.SUBJECT_A, category=category, topic=category.name,
            stem='稼働率 0.9 の装置 2 台を直列に接続したときの稼働率はどれか。',
            choices=['0.81', '0.90', '0.95', '0.99'], answer_index=0,
            source='令和7年度 科目A 問9',
        )
        option = next(
            o for o in category_options(self.learner, StudySession.MODE_IPA) if o['code'] == 4
        )
        self.assertEqual((option['count'], option['selectable']), (1, True))
        self.assertEqual(option['by_mode'][StudySession.MODE_CALC][0], 1)
        self.assertGreater(option['question_count'], 1)

        # 画面は by_mode から、いまのモードの件数を出す
        options = {c['code']: c for c in api_get(self.client, 'api_settings').json()['categories']}
        self.assertEqual(options[4]['by_mode'][StudySession.MODE_IPA], [1, True])

    def test_categories_with_nothing_to_serve_cannot_be_chosen(self):
        """そのモードで出せる問題が無い分野は、分野の欄で選べなくする。"""
        ipa_category = Category.objects.get(code=4)
        Question.objects.create(
            subject=Question.SUBJECT_A, category=ipa_category, topic=ipa_category.name,
            stem='IPA の問題', choices=['あ', 'い', 'う', 'え'], answer_index=0,
            source='令和7年度 科目A 問9',
        )
        missed = Question.objects.filter(category__code=5).first()
        answer(self.learner, missed, False)
        weak = Category.objects.get(code=6)
        for question in list(Question.objects.filter(category=weak)[:WEAK_MIN_ATTEMPTS]):
            answer(self.learner, question, False)

        def selectable(mode):
            return {
                o['code'] for o in category_options(self.learner, mode)
                if o['selectable'] and o['subject'] == Question.SUBJECT_A
            }

        self.assertEqual(selectable(StudySession.MODE_IPA), {4})
        self.assertEqual(selectable(StudySession.MODE_REVIEW), {5, 6})
        self.assertEqual(selectable(StudySession.MODE_WEAK), {6})
        self.assertEqual(len(selectable(StudySession.MODE_FOCUS)), 23)

        # API も、選べるかどうかをモードごとに渡す（画面は選べない分野を disabled にする）
        categories = api_get(self.client, 'api_settings').json()['categories']
        open_codes = [c['code'] for c in categories
                      if c['subject'] == 'A' and c['by_mode'][StudySession.MODE_IPA][1]]
        self.assertEqual(open_codes, [4])

    def test_both_modes_are_offered(self):
        labels = [m['label'] for m in api_get(self.client, 'api_settings').json()['modes']]
        self.assertIn('IPA公開問題（過去問・サンプル）からおまかせ', labels)
        self.assertIn('計算問題をおまかせ', labels)


class LearnerIdTests(TestCase):
    """本アプリの ID。/fe/id/ で入る・作る。ダッシュボードは ID の有無にかかわらず /fe/。ID は URL に出さない。
    ID はアカウントとつながないので、ログインせずに確かめる。"""

    @classmethod
    def setUpTestData(cls):
        seed_masters()

    def _post(self, code, action):
        return api_post(self.client, 'api_enter', {'code': code, 'action': action})

    def test_the_entrance_says_how_the_records_are_used(self):
        """記録を本人の機能以外に何に使うかを、「このアプリについて」に書いておく。"""
        source = frontend_source('GuidePage.tsx')
        self.assertIn('ID ごとの成績が分からない形に集計して', source)
        self.assertIn('クラブの活動紹介に使います。', source)
        self.assertIn('運営は ID ごとの記録を見られます。', source)

    def test_the_id_is_forgotten_when_the_browser_is_closed(self):
        """入った ID は、ブラウザを閉じたら消える Cookie にも置く。消えたら入口に戻る。

        セッションはブラウザを閉じても残るので、それだけだと共用の端末で
        次の人が前の人の ID のまま入ってしまう。
        """
        Learner.objects.create(code='closer')
        response = self._post('closer', 'enter')
        self.assertEqual(response.status_code, 200)
        cookie = response.cookies[LEARNER_COOKIE]
        self.assertEqual(cookie['max-age'], '')
        self.assertEqual(cookie['expires'], '')
        self.assertTrue(cookie['httponly'])

        # ブラウザを閉じると、期限の無い Cookie だけが消え、セッションは残る
        del self.client.cookies[LEARNER_COOKIE]
        response = self.client.get(reverse('fe:stats'))
        self.assertRedirects(response, reverse('fe:index'), fetch_redirect_response=False)
        self.assertNotIn(SESSION_LEARNER, self.client.session)

    def test_keep_holds_the_id_after_the_browser_is_closed(self):
        """ポップアップで「次回から表示しない」に印を付けて入ると（keep）、閉じても ID を保持する。

        Cookie に期限が付き、セッションが切れても Cookie から入り直す。
        """
        learner = Learner.objects.create(code='keeper')
        response = api_post(self.client, 'api_enter', {'code': 'keeper', 'action': 'enter', 'keep': True})
        self.assertEqual(response.status_code, 200)
        cookie = response.cookies[LEARNER_COOKIE]
        self.assertNotEqual(cookie['max-age'], '')

        # セッションが切れても、Cookie が残っていれば入り直す
        session = self.client.session
        session.pop(SESSION_LEARNER)
        session.save()
        self.assertEqual(self.client.get(reverse('fe:stats')).status_code, 200)
        self.assertEqual(self.client.session[SESSION_LEARNER], learner.pk)

    def test_without_keep_entering_again_drops_the_kept_cookie(self):
        """保持していても、印を付けずに入り直せば、閉じたら消える Cookie に戻る。"""
        Learner.objects.create(code='keeper')
        api_post(self.client, 'api_enter', {'code': 'keeper', 'action': 'enter', 'keep': True})
        response = self._post('keeper', 'enter')
        self.assertEqual(response.cookies[LEARNER_COOKIE]['max-age'], '')

    def test_starting_without_an_id_is_also_forgotten(self):
        """履歴を残さずに始めた場合も同じ。閉じたら入口からになる。"""
        response = self.client.get(reverse('fe:index'))
        self.assertIn(LEARNER_COOKIE, response.cookies)
        self.assertEqual(self.client.get(reverse('fe:quiz')).status_code, 200)
        del self.client.cookies[LEARNER_COOKIE]
        self.assertRedirects(
            self.client.get(reverse('fe:stats')), reverse('fe:index'), fetch_redirect_response=False
        )
        self.assertEqual(api_get(self.client, 'api_dashboard').status_code, 401)

    def test_without_an_id_the_dashboard_opens_at_once(self):
        """ID なしが基本。入口を開くと、選ばせずにそのままダッシュボードになる。"""
        response = self.client.get(reverse('fe:index'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'fe/app.html')
        learner = Learner.objects.get(code__isnull=True)
        self.assertTrue(learner.is_temporary)
        self.assertEqual(api_get(self.client, 'api_me').json(),
                         {'entered': True, 'code': None, 'is_temporary': True})
        # 開き直しても記録は増えない
        self.client.get(reverse('fe:index'))
        self.assertEqual(Learner.objects.filter(code__isnull=True).count(), 1)

    def test_dashboard_without_an_id_shows_the_id_popup(self):
        """ID なしのダッシュボードを開くと、ID の入力のポップアップを出す（IdPopup.tsx）。
        「入室」「ID なしで入室」と「次回から表示しない」。無い ID なら「新規作成しますか？」。問題メールの欄は ID なしでも出す。"""
        source = frontend_source('Dashboard.tsx')
        self.assertIn("{me.is_temporary && <IdPopup", source)
        self.assertIn("      <MailSection />", source)
        popup = frontend_source('IdPopup.tsx')
        for label in ('>入室</button>', '>ID なしで入室</button>', '次回から表示しない', '新規作成しますか？'):
            self.assertIn(label, popup)
        self.client.get(reverse('fe:index'))
        self.assertEqual(api_get(self.client, 'api_mail').json()['with_id'], False)

    def test_temporary_use_can_answer_and_keeps_stats_while_in_use(self):
        """使っている間は、ふつうに解けて成績も積み上がる。"""
        build_questions()
        self.client.get(reverse('fe:index'))
        learner = Learner.objects.get(code__isnull=True)
        question = Question.objects.first()
        answer(learner, question, correct=True)
        self.assertEqual(
            CategoryProgress.objects.get(learner=learner, category=question.category).answered, 1
        )
        self.assertEqual(self.client.get(reverse('fe:quiz')).status_code, 200)
        self.assertIsNotNone(api_get(self.client, 'api_quiz_next').json()['question'])

    def test_registering_an_id_later_starts_from_zero(self):
        """履歴なしで使ったあとに ID を登録しても、それまでの解答は引き継がない。"""
        build_questions()
        self.client.get(reverse('fe:index'))
        temp = Learner.objects.get(code__isnull=True)
        answer(temp, Question.objects.first(), correct=True)

        self._post('later_id', 'create')
        named = Learner.objects.get(code='later_id')
        self.assertEqual(CategoryProgress.objects.filter(learner=named).count(), 0)
        # 一時的な記録はそのまま残り、掃除の対象になる
        self.assertTrue(Learner.objects.filter(pk=temp.pk).exists())

    def test_temporary_use_is_excluded_from_the_site_summary(self):
        """消える記録は全体集計に数えない。"""
        build_questions()
        self.client.get(reverse('fe:index'))
        temp = Learner.objects.get(code__isnull=True)
        answer(temp, Question.objects.first(), correct=True)
        self.assertEqual(site_summary()['total'], 0)

        named = make_learner('counted')
        answer(named, Question.objects.first(), correct=True)
        self.assertEqual(site_summary()['total'], 1)

    def test_temporary_use_cannot_report_a_pass(self):
        """履歴を残さない利用からは合格申告できない。"""
        self.client.get(reverse('fe:index'))
        response = api_post(self.client, 'api_pass', {'passed_on': '2026-04-01'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(PassReport.objects.count(), 0)

    def test_purge_removes_only_stale_temporary_records(self):
        """掃除は、使われなくなった一時的な記録だけを消す。"""
        from django.utils import timezone
        fresh = Learner.objects.create(code=None)
        stale = Learner.objects.create(code=None)
        Learner.objects.filter(pk=stale.pk).update(
            last_seen_at=timezone.now() - timezone.timedelta(days=90)
        )
        named = make_learner('keep_me')

        call_command('purge_temp_learners', verbosity=0)
        self.assertFalse(Learner.objects.filter(pk=stale.pk).exists())
        self.assertTrue(Learner.objects.filter(pk=fresh.pk).exists())
        self.assertTrue(Learner.objects.filter(pk=named.pk).exists())

    def test_create_opens_the_new_dashboard(self):
        response = self._post('Hira_01', 'create')
        self.assertEqual(response.status_code, 200)
        # 大文字小文字は区別せず、小文字にそろえる
        created = Learner.objects.get(code='hira_01')
        self.assertEqual(response.json()['code'], 'hira_01')
        self.assertIn('を作りました', response.json()['message'])
        # 入ったあとは、その ID の記録を使う（URL に ID は出ない）
        self.assertEqual(api_get(self.client, 'api_me').json()['code'], created.code)
        # 入口（/fe/）がそのまま、その ID のダッシュボードになる。記録は増えない
        self.assertEqual(self.client.get(reverse('fe:index')).status_code, 200)
        self.assertEqual(api_get(self.client, 'api_me').json()['code'], 'hira_01')
        self.assertFalse(Learner.objects.filter(code__isnull=True).exists())

    def test_create_refuses_a_taken_or_bad_id(self):
        make_learner('taken')
        for code in ('taken', 'TAKEN', 'quiz', 'enter', 'ab', 'ひらがな', 'a b', 'x' * 31):
            with self.subTest(code=code):
                response = self._post(code, 'create')
                self.assertEqual(response.status_code, 400)
                self.assertTrue(response.json()['detail'])
        self.assertEqual(Learner.objects.count(), 1)

    def test_enter_needs_an_existing_id(self):
        response = self._post('nobody', 'enter')
        self.assertEqual(response.status_code, 400)
        self.assertIn('その ID はまだありません', response.json()['detail'])
        # ダッシュボードのポップアップは not_found を見て「新規作成しますか？」を出す
        self.assertTrue(response.json()['not_found'])
        self.assertFalse(Learner.objects.exists())

    def test_a_bad_id_is_not_offered_to_be_created(self):
        """形の正しくない ID は、作成の確認を出さずにそのまま誤りを返す。"""
        response = self._post('ab', 'enter')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['not_found'])

    def test_anyone_with_the_id_can_enter(self):
        """合言葉は無い。ID を入力した人を本人として扱う。"""
        shared = make_learner('shared')
        self.assertEqual(self._post('shared', 'enter').status_code, 200)
        self.assertEqual(self.client.session[SESSION_LEARNER], shared.pk)

    def test_the_id_entry_opens_without_an_id(self):
        """ID で入っていなくても、ID の入力欄（/fe/id/）は開ける。古い入口は無い。"""
        self.assertEqual(reverse('fe:id_entry'), '/fe/id/')
        response = self.client.get(reverse('fe:id_entry'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'fe/app.html')
        self.assertEqual(api_get(self.client, 'api_me').json()['entered'], False)
        self.assertEqual(self.client.get('/fe/enter/').status_code, 404)
        # ヘッダーの「ID で入る」の先も、ポップアップと同じ「入室」と新規作成の確認。説明文は出さない
        enter = frontend_source('EnterPage.tsx')
        self.assertIn('>入室</button>', enter)
        self.assertIn('を新規作成しますか？', enter)
        self.assertNotIn('作った ID で入る', enter)
        self.assertNotIn('<p>', enter)

    def test_the_old_mypage_goes_to_the_dashboard(self):
        """以前の ID ありの入口（/fe/mypage/）は無くした。ブックマーク用に /fe/ へ送る。"""
        self.assertRedirects(self.client.get('/fe/mypage/'), reverse('fe:index'),
                             fetch_redirect_response=False)
        self.assertNotIn('mypage/', ''.join(frontend_source(n) for n in FRONTEND_FILES)
                         .replace("'mypage'", ''))

    def test_the_id_never_appears_in_the_url(self):
        """ID は URL に使わない。ID ありのダッシュボードも /fe/ で、/fe/<ID>/ は無い。"""
        mine = make_learner('mine')
        enter(self.client, mine)
        response = self.client.get(reverse('fe:index'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'mine')
        for url in ('/fe/mine/', '/fe/MINE/', '/fe/nobody/'):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_without_an_id_other_pages_go_to_the_entrance(self):
        for name in ('fe:stats', 'fe:history', 'fe:learn_start'):
            with self.subTest(page=name):
                self.assertRedirects(
                    self.client.get(reverse(name)), reverse('fe:index'),
                    fetch_redirect_response=False,
                )

    def test_the_enter_page_switches_ids_any_time(self):
        """入ったあとでも別の ID を入力すれば、何度でも切り替わる（画面は /id/?switch）。"""
        first, second = make_learner('first'), make_learner('second')
        enter(self.client, first)
        self.assertEqual(api_get(self.client, 'api_me').json()['code'], 'first')
        self.assertEqual(self._post('second', 'enter').json()['code'], 'second')
        self.assertEqual(api_get(self.client, 'api_me').json()['code'], 'second')
        self.assertEqual(self._post('first', 'enter').json()['code'], 'first')
        self.assertEqual(self._post('third', 'create').json()['code'], 'third')
        self.assertEqual(self.client.session[SESSION_LEARNER], Learner.objects.get(code='third').pk)
        self.assertIn("'/id/?switch'", frontend_source('App.tsx').replace('"', "'"))

    def test_ids_are_separate(self):
        """ID が違えば成績は別。問題集は共有。"""
        first, second = make_learner('first'), make_learner('second')
        build_questions()
        answer(first, Question.objects.all().first(), correct=True)
        enter(self.client, second)
        self.assertEqual(api_get(self.client, 'api_dashboard').json()['question_total'],
                         Question.objects.count())
        rows = api_get(self.client, 'api_stats').json()['rows']
        self.assertEqual(sum(r['total'] for r in rows), 0)

    def test_managing_is_a_separate_page(self):
        """問題の管理は /fe/console/ の下の別ページ。"""
        build_questions()
        login_editor(self.client)
        self.assertEqual(reverse('fe:manage_list'), '/fe/console/questions/')
        self.assertEqual(reverse('fe:manage_upload'), '/fe/console/upload/')
        self.assertRedirects(self.client.get('/fe/console/'), reverse('fe:manage_list'))

    def test_learning_pages_do_not_reveal_the_console(self):
        """ログインしていても、学習の画面には管理のページがあることを出さない。"""
        build_questions()
        learner = make_learner('hider')
        enter(self.client, learner)
        login_editor(self.client)
        for url in (dashboard(learner), reverse('fe:quiz'), reverse('fe:learn_start'),
                    reverse('fe:stats'), reverse('fe:history'), reverse('fe:about'),
                    reverse('fe:id_entry')):
            with self.subTest(url=url):
                html = self.client.get(url).content.decode('utf-8')
                self.assertNotIn('/fe/console/', html)
                self.assertNotIn('問題の管理', html)
        for name in FRONTEND_FILES:
            with self.subTest(source=name):
                source = frontend_source(name)
                self.assertNotIn('console', source)
                self.assertNotIn('問題の管理', source)
                self.assertNotIn('取り込', source)


class ManageTests(TestCase):
    """問題の一括差し替え。JSON が唯一の登録経路になっている。"""

    @classmethod
    def setUpTestData(cls):
        seed_masters()
        cls.learner = make_learner('owner')
        cls.other = make_learner('stranger')

    def setUp(self):
        login_editor(self.client)

    def _upload(self, n=3, prefix='問題'):
        """取り込みは JSON ファイルだけなので、テストもファイルで投げる。"""
        return {'questions_a_file': SimpleUploadedFile(
            'q.json', self._payload(n, prefix).encode('utf-8'),
            content_type='application/json',
        )}

    def _post_upload(self, data):
        """取り込みを最後まで通す。削除が多くて確認が出たら、承認して続ける。"""
        response = self.client.post(reverse('fe:manage_upload'), data)
        if response.status_code == 200 and '削除が多いので' in response.content.decode('utf-8'):
            payload = re.search(
                r'name="payload" value="(.*?)">', response.content.decode('utf-8'), re.S
            ).group(1)
            response = self.client.post(reverse('fe:manage_upload'), {
                'confirm': '1', 'payload': html.unescape(payload),
            })
        return response

    def _json_upload(self, records, field='questions_a_file'):
        return {field: SimpleUploadedFile(
            'q.json', json.dumps(records, ensure_ascii=False).encode('utf-8'),
            content_type='application/json',
        )}

    def _upload_with_notes(self, n=3, codes=(9, 11), topic=None):
        return {
            **self._json_upload({'questions': json.loads(self._payload(n))}),
            **self._json_upload(
                {'notes': build_notes(codes=codes, topic=topic)}, 'notes_a_file'),
        }

    def _payload(self, n=3, prefix='問題'):
        return json.dumps([
            {
                'category': 11, 'subject': 'A', 'topic': '情報セキュリティ', 'difficulty': 2,
                'stem': '{}{}'.format(prefix, i),
                'choices': ['ア{}'.format(i), 'イ{}'.format(i), 'ウ{}'.format(i), 'エ{}'.format(i)],
                'answer': 0, 'explanation': '解説', 'source': 'テスト',
            }
            for i in range(n)
        ], ensure_ascii=False)

    def test_empty_state_is_shown_before_any_upload(self):
        response = self.client.get(reverse('fe:manage_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'まだ問題がありません')

    def test_upload_by_file_creates_the_question_set(self):
        response = self.client.post(reverse('fe:manage_upload'), self._upload(3))
        self.assertRedirects(response, reverse('fe:manage_list'))
        questions = Question.objects.all()
        self.assertEqual(questions.count(), 3)

    def test_pasting_is_not_offered(self):
        """取り込み経路はファイル1本。貼り付け欄は置かない。"""
        response = self.client.get(reverse('fe:manage_upload'))
        self.assertNotIn('payload', response.context['form'].fields)
        self.assertNotContains(response, 'id_payload')
        self.assertNotContains(response, '<textarea')

    def test_a_large_file_is_accepted(self):
        """解説を添えると 1MB を超えるので、その大きさで通ること。"""
        records = json.loads(self._payload(200, '大きな問題'))
        notes = [
            {
                'category': 11, 'topic': '情報セキュリティ',
                'title': '解説{}'.format(i), 'body': 'あ' * 8000, 'source': 'テスト',
            }
            for i in range(120)
        ]
        payload = json.dumps({'notes': notes}, ensure_ascii=False).encode('utf-8')
        # 小分類ぶんの解説を厚く書いた実運用の大きさを想定する。
        self.assertGreater(len(payload), 2 * 1024 * 1024, '2MB を超える前提のテスト')

        response = self.client.post(reverse('fe:manage_upload'), {
            **self._json_upload({'questions': records}),
            'notes_a_file': SimpleUploadedFile('big.json', payload,
                                               content_type='application/json'),
        })
        self.assertRedirects(response, reverse('fe:manage_list'))
        self.assertEqual(Question.objects.all().count(), 200)
        self.assertEqual(LearningNote.objects.all().count(), 120)

    def test_upload_is_required(self):
        response = self.client.post(reverse('fe:manage_upload'), {})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)

    def test_upload_deletes_the_old_set_and_its_logs(self):
        self._post_upload(self._upload(3, '旧'))
        old = list(Question.objects.all())
        old_ids = [q.id for q in old]
        answer(self.learner, old[0], correct=True)
        answer(self.other, old[1], correct=False)

        self._post_upload(self._upload(2, '新'))

        self.assertEqual(
            Question.objects.all().count(), 2,
            '古い問題は削除され、データが増え続けない',
        )
        self.assertFalse(Question.objects.filter(id__in=old_ids).exists())
        self.assertEqual(
            Attempt.objects.count(), 0,
            '全 ID の解答ログが問題と一緒に消える',
        )

    def test_understanding_survives_the_replacement(self):
        """問題を入れ替えても、分野ごとの理解度は残る。"""
        self.client.post(reverse('fe:manage_upload'), self._upload(3, '旧'))
        security = Category.objects.get(code=11)
        questions = list(Question.objects.all())
        answer(self.learner, questions[0], correct=True)
        answer(self.learner, questions[1], correct=False)

        self.client.post(reverse('fe:manage_upload'), self._upload(2, '新'))

        row = next(r for r in category_stats(self.learner) if r['category'] == security)
        self.assertEqual(row['total'], 2, '解答数は残る')
        self.assertEqual(row['correct'], 1, '正解数も残る')
        self.assertEqual(row['rate_percent'], 50)

        overall = overall_stats(self.learner)
        self.assertEqual(overall['total'], 2)
        self.assertEqual(overall['study_days'], 1, '学習した日数も残る')

    def test_progress_is_kept_per_account(self):
        build_questions()
        self.client.post(reverse('fe:manage_upload'), self._upload(2))
        mine = Question.objects.all().first()
        theirs = Question.objects.all().first()
        answer(self.learner, mine, correct=True)
        answer(self.other, theirs, correct=False)

        self.assertEqual(overall_stats(self.learner)['correct'], 1)
        self.assertEqual(overall_stats(self.other)['correct'], 0)
        self.assertEqual(
            CategoryProgress.objects.filter(learner=self.learner).count(), 1,
            '他人の解答が自分の理解度に混ざらない',
        )

    def test_upload_replaces_the_set_for_every_id(self):
        build_questions()
        self._post_upload(self._upload(2))
        self.assertEqual(
            Question.objects.filter(template__isnull=True, subject='A').count(), 2,
            '問題集は共有なので、取り込むと全員の問題集が入れ替わる',
        )

    def test_broken_json_is_rejected_without_touching_anything(self):
        self.client.post(reverse('fe:manage_upload'), self._upload(2))
        before = list(Question.objects.all().values_list('id', flat=True))
        response = self.client.post(reverse('fe:manage_upload'), {'questions_a_file': SimpleUploadedFile(
            'q.json', b'{ not json', content_type='application/json')})
        self.assertEqual(response.status_code, 200)
        after = list(Question.objects.all().values_list('id', flat=True))
        self.assertEqual(before, after, '取り込みに失敗したら既存の問題は変わらない')

    def test_invalid_records_are_rejected_with_a_reason(self):
        cases = {
            '中分類が存在しない': [{'category': 99, 'stem': 'x', 'choices': ['a', 'b'], 'answer': 0}],
            '正解が範囲外': [{'category': 11, 'stem': 'x', 'choices': ['a', 'b'], 'answer': 5}],
            '選択肢が1つ': [{'category': 11, 'stem': 'x', 'choices': ['a'], 'answer': 0}],
            '選択肢が重複': [{'category': 11, 'stem': 'x', 'choices': ['a', 'a'], 'answer': 0}],
            '問題文が空': [{'category': 11, 'stem': '  ', 'choices': ['a', 'b'], 'answer': 0}],
        }
        for label, records in cases.items():
            with self.subTest(label=label):
                response = self.client.post(
                    reverse('fe:manage_upload'), self._json_upload(records))
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['form'].errors)
                self.assertEqual(Question.objects.all().count(), 0)

    def test_export_is_not_offered(self):
        """正は手元の JSON なので、アプリから書き出す道は置かない。"""
        response = self.client.get(reverse('fe:manage_list'))
        self.assertNotContains(response, '書き出す')
        self.assertNotContains(response, 'manage/export')

    def test_choice_labels_cover_a_long_answer_group(self):
        """選択肢が多くても記号が割り当たること。"""
        self.client.post(reverse('fe:manage_upload'), self._json_upload([{
            'category': 103, 'subject': 'B', 'stem': 'x',
            'choices': ['選択肢{}'.format(i) for i in range(9)], 'answer': 8,
            'explanation': '解説',
        }], 'questions_b_file'))
        question = Question.objects.get(template__isnull=True)
        labels = [label for _, label, _ in question.labeled_choices()]
        self.assertEqual(labels, list('アイウエオカキクケ'))
        self.assertEqual(question.answer_label, 'ケ')

    def test_list_shows_the_shared_set(self):
        self.client.post(reverse('fe:manage_upload'), self._upload(3))
        response = self.client.get(reverse('fe:manage_list'))
        self.assertEqual(response.context['summary']['total'], 3)


class ImportNotesTests(TestCase):
    """技術解説つき JSON の取り込み。"""

    @classmethod
    def setUpTestData(cls):
        seed_masters()
        cls.learner = make_learner('reader')

    def test_object_form_imports_notes_and_questions(self):
        payload = {
            'notes': build_notes(),
            'questions': [{
                'category': 11, 'stem': 'x', 'choices': ['a', 'b', 'c', 'd'], 'answer': 0,
            }],
        }
        result = sync(validate(parse(json.dumps(payload, ensure_ascii=False))))
        self.assertEqual(result['questions']['added'], 1)
        self.assertEqual(result['notes']['added'], 2)
        self.assertEqual(LearningNote.objects.all().count(), 2)

    def test_plain_array_still_works(self):
        """解説を持たない、いままでの形の JSON もそのまま取り込める。"""
        payload = json.dumps(
            [{'category': 11, 'stem': 'x', 'choices': ['a', 'b'], 'answer': 0}],
            ensure_ascii=False,
        )
        result = sync(validate(parse(payload)))
        self.assertEqual(result['questions']['added'], 1)
        self.assertIsNone(result['notes'], '解説を含まないファイルは解説に触れない')

    def test_notes_only_file_is_accepted(self):
        """解説だけのファイルも取り込める。問題には触らない。"""
        build_questions(per_category=1)
        before = Question.objects.count()
        result = sync(validate(parse(json.dumps(
            {'notes': build_notes()}, ensure_ascii=False
        ))))
        self.assertEqual(result['notes']['added'], 2)
        self.assertIsNone(result['questions'], '問題を含まないファイルは問題に触れない')
        self.assertEqual(Question.objects.count(), before)

    def test_sync_keeps_unchanged_rows_and_their_history(self):
        """変わっていない問題は作り直さない。解答履歴が切れないため。"""
        build_questions(per_category=1)
        question = Question.objects.first()
        learner = make_learner('synced')
        answer(learner, question, correct=True)

        records = [{
            'category': q.category.code, 'subject': q.subject, 'topic': q.topic,
            'stem': q.stem, 'choices': q.choices, 'answer': q.answer_index,
            'explanation': q.explanation, 'difficulty': q.difficulty,
            'source': q.source,
        } for q in Question.objects.filter(template__isnull=True)]
        result = sync(validate({'questions': records, 'notes': None}))

        self.assertEqual(result['questions']['added'], 0)
        self.assertEqual(result['questions']['removed'], 0)
        self.assertEqual(result['questions']['unchanged'], len(records))
        self.assertTrue(Attempt.objects.filter(learner=learner).exists())
        self.assertEqual(Question.objects.filter(pk=question.pk).count(), 1)

    def test_sync_updates_in_place_and_removes_missing(self):
        """解説や正解だけ直したら更新、ファイルから消えたら削除。"""
        build_questions(per_category=2)
        kept = Question.objects.filter(template__isnull=True).first()
        total = Question.objects.filter(template__isnull=True, subject=kept.subject).count()
        records = [{
            'category': kept.category.code, 'subject': kept.subject,
            'stem': kept.stem, 'choices': kept.choices, 'answer': kept.answer_index,
            'explanation': '書き直した解説',
        }]
        result = sync(validate({'questions': records, 'notes': None}))
        self.assertEqual(result['questions']['updated'], 1)
        self.assertEqual(result['questions']['removed'], total - 1)
        kept.refresh_from_db()
        self.assertEqual(kept.explanation, '書き直した解説')

    def test_both_files_can_be_uploaded_at_once(self):
        """問題と解説を別々の欄で選んで、1回で取り込める。"""
        login_editor(self.client)
        questions = json.dumps({'questions': [
            {'category': 11, 'stem': 'まとめて取り込む問題',
             'choices': ['a', 'b', 'c', 'd'], 'answer': 0},
        ]}, ensure_ascii=False)
        notes = json.dumps({'notes': build_notes()}, ensure_ascii=False)

        response = self.client.post(reverse('fe:manage_upload'), {
            'questions_a_file': SimpleUploadedFile('q.json', questions.encode('utf-8')),
            'notes_a_file': SimpleUploadedFile('n.json', notes.encode('utf-8')),
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Question.objects.filter(template__isnull=True).count(), 1)
        self.assertEqual(LearningNote.objects.count(), 2)

    def test_notes_file_alone_is_accepted_from_the_screen(self):
        """解説の欄だけ選んでも取り込める。問題には触らない。"""
        build_questions(per_category=1)
        before = Question.objects.count()
        login_editor(self.client)
        notes = json.dumps({'notes': build_notes()}, ensure_ascii=False)

        response = self.client.post(reverse('fe:manage_upload'), {
            'notes_a_file': SimpleUploadedFile('n.json', notes.encode('utf-8')),
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(LearningNote.objects.count(), 2)
        self.assertEqual(Question.objects.count(), before, '問題はそのまま')

    def test_upload_needs_at_least_one_file(self):
        """どの欄も選ばずに送ったら、理由を添えて止める。"""
        login_editor(self.client)
        response = self.client.post(reverse('fe:manage_upload'), {})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '取り込むファイルを1つ以上選んでください')

    def test_a_file_in_the_wrong_slot_is_rejected(self):
        """欄と中身の側・科目が合わないファイルは、取り込む前に止める。"""
        build_questions(per_category=1)
        before = Question.objects.count()
        login_editor(self.client)
        a_questions = json.dumps({'questions': [
            {'category': 11, 'subject': 'A', 'stem': 'x', 'choices': ['a', 'b'], 'answer': 0},
        ]}, ensure_ascii=False).encode('utf-8')
        a_notes = json.dumps({'notes': build_notes()}, ensure_ascii=False).encode('utf-8')
        both = json.dumps({
            'questions': json.loads(a_questions)['questions'], 'notes': build_notes(),
        }, ensure_ascii=False).encode('utf-8')
        cases = {
            '科目Aの問題を科目Bの欄に': ('questions_b_file', a_questions, '科目Bではありません'),
            '科目Aの解説を科目Bの欄に': ('notes_b_file', a_notes, '科目Bではありません'),
            '解説を問題の欄に': ('questions_a_file', a_notes, '技術解説が入っています'),
            '問題を解説の欄に': ('notes_a_file', a_questions, '問題が入っています'),
            '両方入りのファイル': ('questions_a_file', both, '技術解説が入っています'),
        }
        for label, (field, payload, message) in cases.items():
            with self.subTest(label=label):
                response = self.client.post(reverse('fe:manage_upload'), {
                    field: SimpleUploadedFile('x.json', payload),
                })
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, message)
                self.assertEqual(Question.objects.count(), before, '何も変わらない')

    def test_one_subject_leaves_the_other_subject_alone(self):
        """科目Aのファイルだけを取り込んでも、科目Bの問題と解説は消えない。

        問題も解説も科目ごとに別のファイルにしているので、ファイルに出てこない
        科目まで同期の対象にすると、片方を取り込むたびにもう片方が全部消える。
        """
        build_questions(per_category=1)
        b_note = Category.objects.filter(subject='B').first()
        sync(validate({'questions': None, 'notes': build_notes() + [{
            'category': b_note.code, 'topic': b_note.name, 'title': '科目Bの解説', 'body': '本文',
        }]}))
        b_questions = Question.objects.filter(template__isnull=True, subject='B').count()
        self.assertTrue(b_questions)

        result = sync(validate({'questions': [
            {'category': 11, 'subject': 'A', 'stem': '科目Aだけ', 'choices': ['a', 'b'], 'answer': 0},
        ], 'notes': build_notes(codes=(9,))}))

        self.assertEqual(result['questions']['subjects'], ['A'])
        self.assertEqual(result['notes']['subjects'], ['A'])
        self.assertEqual(
            Question.objects.filter(template__isnull=True, subject='B').count(), b_questions,
            '科目Bの問題はそのまま',
        )
        self.assertEqual(
            Question.objects.filter(template__isnull=True, subject='A').count(), 1,
            '科目Aはファイルの内容に揃う',
        )
        self.assertTrue(LearningNote.objects.filter(title='科目Bの解説').exists(), '科目Bの解説も残る')
        self.assertEqual(LearningNote.objects.filter(category__subject='A').count(), 1)

    def test_four_files_can_be_uploaded_at_once(self):
        """4つの欄をまとめて選んで、1回で取り込める。"""
        login_editor(self.client)
        b = Category.objects.filter(subject='B').first()
        files = {
            'questions_a_file': {'questions': [
                {'category': 11, 'subject': 'A', 'stem': 'A問', 'choices': ['a', 'b'], 'answer': 0}]},
            'questions_b_file': {'questions': [
                {'category': b.code, 'subject': 'B', 'stem': 'B問', 'choices': ['a', 'b'], 'answer': 1}]},
            'notes_a_file': {'notes': build_notes()},
            'notes_b_file': {'notes': [
                {'category': b.code, 'topic': b.name, 'title': 'B解説', 'body': '本文'}]},
        }
        response = self.client.post(reverse('fe:manage_upload'), {
            field: SimpleUploadedFile(field + '.json', json.dumps(data, ensure_ascii=False).encode('utf-8'))
            for field, data in files.items()
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Question.objects.filter(template__isnull=True).count(), 2)
        self.assertEqual(LearningNote.objects.count(), 3)

    def test_preview_counts_without_writing(self):
        """下見は数えるだけで、1件も書き込まない。"""
        build_questions(per_category=1)
        before = Question.objects.count()
        counts = preview(validate({
            'questions': [{
                'category': 11, 'subject': 'A', 'stem': '新しい問題',
                'choices': ['a', 'b', 'c', 'd'], 'answer': 0,
            }],
            'notes': None,
        }))
        self.assertEqual(counts['questions']['added'], 1)
        self.assertEqual(Question.objects.count(), before, '下見では書き込まない')

    def test_large_removal_needs_confirmation(self):
        """削除が既存の3割を超えたら、確定の前に止める。"""
        build_questions(per_category=1)
        kept = Question.objects.filter(template__isnull=True).first()
        # 同期はファイルに出てくる科目の中だけなので、数えるのも同じ科目
        total = Question.objects.filter(template__isnull=True, subject=kept.subject).count()
        one = [{
            'category': kept.category.code, 'subject': kept.subject, 'stem': kept.stem,
            'choices': kept.choices, 'answer': kept.answer_index,
            'source': kept.source, 'topic': kept.topic,
        }]
        counts = preview(validate({'questions': one, 'notes': None}))
        self.assertEqual(counts['questions']['removed'], total - 1)
        self.assertTrue(needs_confirmation(counts))

        # 3割以下なら止めない
        few = Question.objects.filter(template__isnull=True, subject=kept.subject)[:total - 1]
        records = [{
            'category': q.category.code, 'subject': q.subject, 'stem': q.stem,
            'choices': q.choices, 'answer': q.answer_index,
            'source': q.source, 'topic': q.topic,
        } for q in few]
        self.assertFalse(needs_confirmation(
            preview(validate({'questions': records, 'notes': None}))
        ))

    def test_upload_screen_stops_before_a_large_removal(self):
        """画面でも、削除が多いファイルは一度で取り込まれない。"""
        build_questions(per_category=1)
        login_editor(self.client)
        before = Question.objects.count()
        kept = Question.objects.filter(template__isnull=True).first()
        payload = json.dumps({'questions': [{
            'category': kept.category.code, 'subject': kept.subject, 'stem': kept.stem,
            'choices': kept.choices, 'answer': kept.answer_index,
        }]}, ensure_ascii=False)

        response = self.client.post(reverse('fe:manage_upload'), {
            'questions_a_file': SimpleUploadedFile('q.json', payload.encode('utf-8')),
        })
        self.assertEqual(response.status_code, 200, '遷移せず確認画面を出す')
        self.assertContains(response, '削除が多いので、一度止めました')
        self.assertEqual(Question.objects.count(), before, 'まだ消えていない')

        # 確認したうえで実行すると、取り込まれる
        response = self.client.post(reverse('fe:manage_upload'), {
            'confirm': '1', 'payload': payload,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            Question.objects.filter(template__isnull=True, subject=kept.subject).count(), 1)

    def test_duplicate_keys_in_one_file_are_rejected(self):
        """同じ鍵が1つのファイルに2件あると、どちらが勝つか不定なので止める。"""
        payload = json.dumps({'questions': [
            {'category': 11, 'stem': '同じ問題', 'choices': ['a', 'b'], 'answer': 0},
            {'category': 11, 'stem': '  同じ問題  ', 'choices': ['c', 'd'], 'answer': 1},
        ]}, ensure_ascii=False)
        with self.assertRaises(ImportError_):
            validate(parse(payload))

    def test_empty_side_is_rejected(self):
        """空の配列は、キーごと外すのと区別して弾く。取り違えの事故を防ぐため。"""
        for payload in ('{"questions": []}', '{"notes": []}', '{}'):
            with self.subTest(payload=payload):
                with self.assertRaises(ImportError_):
                    parse(payload)

    def test_questions_only_file_leaves_the_notes_alone(self):
        """問題だけのファイルを入れても、解説は消えない。

        問題と解説は更新の頻度が違うので別のファイルで渡せる。入っていない
        側に触ると、問題を1問足すだけで解説が全部消えることになる。
        """
        sync(validate(parse(json.dumps({
            'notes': build_notes(),
            'questions': [{'category': 11, 'stem': 'x', 'choices': ['a', 'b'], 'answer': 0}],
        }, ensure_ascii=False))))
        self.assertEqual(LearningNote.objects.all().count(), 2)

        sync(validate(parse(json.dumps(
            [{'category': 11, 'stem': 'y', 'choices': ['a', 'b'], 'answer': 0}],
            ensure_ascii=False,
        ))))
        self.assertEqual(LearningNote.objects.all().count(), 2, '解説はそのまま残る')

    def test_a_broken_note_is_rejected(self):
        cases = {
            '本文が空': [{'category': 11, 'title': 'x', 'body': '  '}],
            '見出しが無い': [{'category': 11, 'body': 'x'}],
            '中分類が無い': [{'category': 99, 'title': 'x', 'body': 'y'}],
        }
        for label, notes in cases.items():
            with self.subTest(label=label):
                payload = json.dumps({
                    'notes': notes,
                    'questions': [{
                        'category': 11, 'stem': 'x', 'choices': ['a', 'b'], 'answer': 0,
                    }],
                }, ensure_ascii=False)
                with self.assertRaises(ImportError_):
                    validate(parse(payload))
                self.assertEqual(Question.objects.all().count(), 0)


class LearningModeTests(TestCase):
    """学習モード。解説を読んでから、その範囲を解く。"""

    @classmethod
    def setUpTestData(cls):
        seed_masters()
        cls.learner = make_learner('learner')

    def setUp(self):
        enter(self.client, self.learner)

    @staticmethod
    def _checked_notes(response):
        """学習対象のうち、最初から選ばれている行。React の画面は何も選ばずに始める（おまかせ）。"""
        return []

    @staticmethod
    def _add_questions(category, topic, count):
        """小分類を指定して問題を足す。build_questions は中分類名を小分類にするため。"""
        return [
            Question.objects.create(
                subject=category.subject, category=category, topic=topic,
                stem='{}の問題{}'.format(topic, i),
                choices=['ア', 'イ', 'ウ', 'エ'], answer_index=0,
            )
            for i in range(count)
        ]

    def _prepare(self, topic=None):
        build_questions(per_category=12)
        LearningNote.objects.all().delete()
        for note in build_notes(codes=(9,), topic=topic):
            LearningNote.objects.create(
                category=Category.objects.get(code=note['category']),
                topic=note['topic'], title=note['title'],
                body=note['body'], source=note['source'],
            )

    def test_whole_category_round_reads_every_note_and_asks_each_topic(self):
        """中分類まるごとのラウンド（plan&check の「解説」）は、その中分類の解説をすべて読み、
        小分類ごとに5問ずつ（少なければあるだけ）出す。"""
        self._prepare()   # データベース（9）の小分類「データベース」に12問と解説1本
        category = Category.objects.get(code=9)
        self._add_questions(category, '正規化', 3)
        LearningNote.objects.create(category=category, topic='正規化', title='正規化のしくみ', body='本文')
        api_post(self.client, 'api_settings', {'mode': 'category', 'subject': 'A', 'category': 9})
        response = api_post(self.client, 'api_learn', {'minutes': None, 'note': None, 'scope': 'category'})
        self.assertEqual(response.status_code, 201)
        round_ = LearningRound.objects.get(learner=self.learner)
        self.assertTrue(round_.whole_category)
        self.assertEqual(len(round_.notes), 2)
        self.assertIn('データベース（解説 2 本）', round_.title)
        topics = sorted(item.question.topic for item in round_.items.select_related('question'))
        self.assertEqual(topics.count('データベース'), 5)
        self.assertEqual(topics.count('正規化'), 3)
        # 読む画面は、両方の解説を出す
        read = api_get(self.client, 'api_learn_read', round_.pk).json()
        self.assertEqual([n['title'] for n in read['notes']], [n.title for n in round_.notes])

    def test_whole_category_round_needs_a_category(self):
        """中分類を指定していなければ、中分類まるごとのラウンドは始められない。"""
        self._prepare()
        response = api_post(self.client, 'api_learn', {'scope': 'category'})
        self.assertEqual(response.status_code, 400)

    def test_a_round_needs_a_note(self):
        """解説が無ければ始められず、「解説がありません。」とだけ伝える。ログインしていても同じ。"""
        build_questions()
        enter(self.client, make_learner('curator'))
        login_editor(self.client)
        response = api_post(self.client, 'api_learn', {'minutes': 5})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['detail'], '解説がありません。')
        self.assertEqual(LearningRound.objects.count(), 0)

    def test_reading_phase_shows_the_note_not_the_questions(self):
        """読む段階では、設問も選択肢も見せない。"""
        self._prepare()
        response = api_post(self.client, 'api_learn', {'minutes': 5})
        self.assertEqual(response.status_code, 201)
        round_ = LearningRound.objects.get(learner=self.learner)
        self.assertEqual(response.json()['round']['id'], round_.pk)
        self.assertEqual(round_.reading_seconds, 300)

        response = api_get(self.client, 'api_learn_read', round_.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([n['title'] for n in response.json()['notes']], [round_.note.title])
        self.assertLessEqual(response.json()['remaining'], 300)
        body = response.content.decode()
        for item in round_.items.all():
            self.assertNotIn(item.question.stem, body)

    def test_questions_come_from_the_note_s_category(self):
        self._prepare()
        api_post(self.client, 'api_learn', {'minutes': 5})
        round_ = LearningRound.objects.get(learner=self.learner)
        self.assertEqual(round_.total, LearningRound.QUESTION_COUNT)
        for item in round_.items.select_related('question'):
            self.assertEqual(
                item.question.category_id, round_.note.category_id,
                '読んだ解説と別の分野が出題された',
            )

    def test_only_questions_of_the_note_s_topic_are_asked(self):
        """出題は解説と同じ小分類だけ。足りなくても中分類からは補わない。"""
        self._prepare()
        database = Category.objects.get(code=9)
        note = LearningNote.objects.get(category=database)
        # 同じ中分類で、解説とは別の小分類の問題。混ざってはいけない。
        other = self._add_questions(database, '別の小分類', 5)
        mine = Question.objects.filter(category=database, topic=note.topic)

        api_post(self.client, 'api_learn', {'minutes': 5, 'note': note.pk})
        round_ = LearningRound.objects.get(learner=self.learner)
        asked = {item.question_id for item in round_.items.all()}
        self.assertTrue(asked <= set(mine.values_list('id', flat=True)))
        self.assertFalse(asked & {q.id for q in other})

    def test_a_round_is_short_when_the_topic_has_few_questions(self):
        """対応する問題が{}問に足りなければ、その数だけ出す。""".format(
            LearningRound.QUESTION_COUNT
        )
        Question.objects.all().delete()
        LearningNote.objects.all().delete()
        law = Category.objects.get(code=23)
        self._add_questions(law, '知的財産権', 3)
        note = LearningNote.objects.create(
            category=law, topic='知的財産権', title='著作権と産業財産権', body='本文',
        )

        api_post(self.client, 'api_learn', {'minutes': 5, 'note': note.pk})
        round_ = LearningRound.objects.get(learner=self.learner)
        self.assertEqual(round_.total, 3)

    def test_origin_label_tells_ipa_questions_from_original_ones(self):
        """出典の書き出しから、IPA の出題そのものか自作かを見分ける。"""
        cases = [
            ('令和6年度 科目A 問3', 'IPA公開問題'),
            ('令和3年度 春期 午前 問2', 'IPA公開問題'),
            ('サンプル問題 科目A 問12', 'IPAサンプル問題'),
            ('シラバス Ver.8.0 中分類1 応用数学（3）数値解析', '自作'),
            ('試験要綱 科目B', '自作'),
            ('自作（令和6年度秋 午前 問5 を基に作成）', '自作'),
            ('', ''),
        ]
        for source, label in cases:
            self.assertEqual(Question(source=source).origin_label, label)

    def test_source_text_does_not_repeat_the_label(self):
        """ラベルと同じ言葉で始まる source は、その言葉を落として出す。"""
        cases = [
            ('サンプル問題 科目A 問12', '科目A 問12'),
            ('令和6年度 科目A 問3', '令和6年度 科目A 問3'),
            ('シラバス Ver.8.0 中分類1 応用数学（3）数値解析',
             'シラバス Ver.8.0 中分類1 応用数学（3）数値解析'),
        ]
        for source, text in cases:
            self.assertEqual(Question(source=source).source_text, text)

        template = QuestionTemplate.objects.first()
        generated = Question(
            template=template, source='テンプレート「{}」による自動生成'.format(template.title),
        )
        self.assertEqual(generated.source_text, '計算問題：{}'.format(template.title))

    def test_learning_quiz_shows_the_source_with_the_question(self):
        """学習モードでは、出典と出題元の区別を答える前から渡す。解説は答えてから。"""
        self._prepare()
        api_post(self.client, 'api_learn', {'minutes': 5})
        round_ = LearningRound.objects.get(learner=self.learner)
        api_post(self.client, 'api_learn_read', {}, round_.pk)

        item = round_.items.get(order=0)
        question = item.question
        question.source = 'シラバス 中分類1 テスト用の項目'
        question.explanation = 'テスト用の解説'
        question.save()

        before = api_get(self.client, 'api_learn_quiz', round_.pk).json()
        self.assertFalse(before['answered'])
        self.assertEqual(before['question']['source'], 'シラバス 中分類1 テスト用の項目')
        self.assertEqual(before['question']['origin_label'], '自作')
        self.assertNotIn('explanation', before)

        after = api_post(self.client, 'api_learn_quiz', {'choice': question.answer_index}, round_.pk).json()
        self.assertTrue(after['answered'])
        self.assertEqual(after['question']['source'], 'シラバス 中分類1 テスト用の項目')
        self.assertEqual(after['explanation'], 'テスト用の解説')
        # 出典は選択肢の下、解説はその下に出す
        source = frontend_source('LearnQuizPage.tsx')
        self.assertLess(source.index('<Choices'), source.index('<Source'))
        self.assertLess(source.index('<Source'), source.index('item.explanation &&'))

    def test_quiz_shows_the_source_with_the_question(self):
        """1問1答でも、出典は答える前から渡し、選択肢の下に出す。解説は答えてから。"""
        self._prepare()
        # その場で作られる計算問題は出典が別なので、この確認では出さない
        QuestionTemplate.objects.update(is_active=False)
        Question.objects.update(source='シラバス 中分類1 テスト用の項目', explanation='テスト用の解説')

        before = api_get(self.client, 'api_quiz_next').json()
        self.assertEqual(before['question']['source'], 'シラバス 中分類1 テスト用の項目')
        self.assertNotIn('explanation', before['question'])
        question = Question.objects.get(pk=before['question']['id'])

        after = api_post(self.client, 'api_quiz_answer', {
            'question_id': question.id, 'choice': question.answer_index,
        }).json()
        self.assertEqual(after['explanation'], 'テスト用の解説')
        source = frontend_source('QuizPage.tsx')
        self.assertLess(source.index('<Choices'), source.index('<Source'))
        self.assertLess(source.index('<Source'), source.index('<Explanation'))

    def test_answering_records_progress(self):
        """学習モードで解いた分も、分野ごとの理解度に積む。"""
        self._prepare()
        api_post(self.client, 'api_learn', {'minutes': 5})
        round_ = LearningRound.objects.get(learner=self.learner)
        api_post(self.client, 'api_learn_read', {}, round_.pk)

        item = round_.items.get(order=0)
        response = api_post(self.client, 'api_learn_quiz', {'choice': item.question.answer_index}, round_.pk)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['is_correct'])
        # 二度送っても二度は数えない
        api_post(self.client, 'api_learn_quiz', {'choice': item.question.answer_index}, round_.pk)

        item.refresh_from_db()
        self.assertTrue(item.is_correct)
        self.assertEqual(Attempt.objects.filter(learner=self.learner).count(), 1)
        self.assertEqual(
            CategoryProgress.objects.filter(learner=self.learner).aggregate(
                n=Sum('answered'))['n'], 1,
        )

    def test_a_round_runs_to_the_result_screen(self):
        self._prepare()
        api_post(self.client, 'api_learn', {'minutes': 3})
        round_ = LearningRound.objects.get(learner=self.learner)
        # 読む段階のうちは、解く API は問題を出さない（画面は読む画面へ戻す）
        self.assertIsNone(api_get(self.client, 'api_learn_quiz', round_.pk).json()['question'])
        self.assertEqual(api_post(self.client, 'api_learn_read', {}, round_.pk).json()['round']['phase'], 'quiz')

        for _ in range(round_.total):
            item = round_.items.get(order=round_.position)
            api_post(self.client, 'api_learn_quiz', {'choice': item.question.answer_index}, round_.pk)
            api_post(self.client, 'api_learn_next', {}, round_.pk)
            round_.refresh_from_db()

        self.assertEqual(round_.phase, LearningRound.PHASE_DONE)
        self.assertEqual(round_.correct, round_.total)
        response = api_get(self.client, 'api_learn_result', round_.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([i for i in response.json()['items'] if i['is_correct'] is False], [])
        self.assertEqual(self.client.get(reverse('fe:learn_result', args=[round_.pk])).status_code, 200)

    def test_the_result_lists_every_question_with_its_source(self):
        """結果には、正解した問題も含めて全問を出典つきで並べる。"""
        self._prepare()
        api_post(self.client, 'api_learn', {'minutes': 3})
        round_ = LearningRound.objects.get(learner=self.learner)
        api_post(self.client, 'api_learn_read', {}, round_.pk)

        for order in range(round_.total):
            item = round_.items.get(order=order)
            question = item.question
            question.source = 'シラバス 中分類1 テスト用の項目{}'.format(order)
            question.save()
            # 1問目だけまちがえ、残りは正解する
            choice = question.answer_index
            if order == 0:
                choice = (choice + 1) % len(question.choices)
            api_post(self.client, 'api_learn_quiz', {'choice': choice}, round_.pk)
            api_post(self.client, 'api_learn_next', {}, round_.pk)

        items = api_get(self.client, 'api_learn_result', round_.pk).json()['items']
        self.assertEqual(len(items), round_.total)
        self.assertEqual([i['is_correct'] for i in items].count(False), 1)
        self.assertEqual(
            [i['question']['source'] for i in items],
            ['シラバス 中分類1 テスト用の項目{}'.format(order) for order in range(round_.total)],
        )
        self.assertEqual(items[0]['selected_label'],
                         Question.choice_label((round_.items.get(order=0).question.answer_index + 1) % 4))

    def test_the_menu_groups_notes_by_category(self):
        """学習対象は、中分類でまとめて小分類（解説）を並べる。"""
        build_questions(per_category=12)
        LearningNote.objects.all().delete()
        for code, topic in ((9, 'データベース設計'), (9, 'データベース方式'), (11, '情報セキュリティ')):
            category = Category.objects.get(code=code)
            LearningNote.objects.create(
                category=category, topic=topic,
                title='{}の解説'.format(topic), body='本文', source='テスト',
            )

        groups = api_get(self.client, 'api_learn').json()['groups']
        self.assertEqual([g['code'] for g in groups], [9, 11])
        self.assertEqual(len(groups[0]['entries']), 2)
        self.assertEqual(
            [e['topic'] for e in groups[0]['entries']],
            ['データベース方式', 'データベース設計'],
        )

    def test_notes_of_one_topic_are_read_together(self):
        """同じ小分類に解説が2本あれば、1行にまとめ、続けて読んでから解く。

        出題は小分類ごとなので、1本だけ読ませると読んでいない内容の問題が混ざる。
        """
        self._prepare(topic='データベース方式')
        category = Category.objects.get(code=9)
        first = LearningNote.objects.get(category=category)
        second = LearningNote.objects.create(
            category=category, topic='データベース方式',
            title='二本目の解説', body='二本目の本文', source='シラバス',
        )
        Question.objects.filter(category=category).update(topic='データベース方式')

        group = api_get(self.client, 'api_learn').json()['groups'][0]
        self.assertEqual(group['note_count'], 2)
        self.assertEqual(len(group['entries']), 1)
        self.assertEqual(group['entries'][0]['titles'], [first.title, second.title])

        # 2本目を指定して始めても、読むのは2本とも。学習回数は小分類で数える。
        api_post(self.client, 'api_learn', {'minutes': 5, 'note': second.pk})
        round_ = LearningRound.objects.get(learner=self.learner)
        notes = api_get(self.client, 'api_learn_read', round_.pk).json()['notes']
        self.assertEqual([n['id'] for n in notes], [first.pk, second.pk])
        self.assertEqual(notes[1]['body'], '二本目の本文')

        group = api_get(self.client, 'api_learn').json()['groups'][0]
        self.assertEqual(group['entries'][0]['rounds'], 1)

    def test_notes_follow_the_syllabus_order(self):
        """中分類の中はシラバスの小分類の順。取り込んだ順でも文字順でもない。

        文字順にすると「プロジェクトのコスト」が「プロジェクトマネジメント」より
        先に来てしまい、シラバスとは逆になる。
        """
        build_questions(per_category=12)
        LearningNote.objects.all().delete()
        pm = Category.objects.get(code=14)
        # わざとシラバスと違う順で取り込む
        for topic in ('プロジェクトのコスト', 'プロジェクトマネジメント', 'プロジェクトの資源'):
            LearningNote.objects.create(
                category=pm, topic=topic, title='{}の解説'.format(topic), body='本文',
            )

        groups = note_menu(self.learner, Question.SUBJECT_A)
        self.assertEqual(
            [n['note'].topic for n in groups[0]['notes']],
            ['プロジェクトマネジメント', 'プロジェクトの資源', 'プロジェクトのコスト'],
        )

    def test_a_topic_outside_the_syllabus_goes_last(self):
        """シラバスに無い小分類は末尾に回す。並びの正はシラバスに置く。"""
        build_questions(per_category=12)
        LearningNote.objects.all().delete()
        law = Category.objects.get(code=23)
        for topic in ('独自の小分類', '標準化関連', '知的財産権'):
            LearningNote.objects.create(
                category=law, topic=topic, title='{}の解説'.format(topic), body='本文',
            )

        groups = note_menu(self.learner, Question.SUBJECT_A)
        self.assertEqual(
            [n['note'].topic for n in groups[0]['notes']],
            ['知的財産権', '標準化関連', '独自の小分類'],
        )

    def test_choosing_a_note_uses_that_note(self):
        """選んだ解説がそのまま読む対象になる。"""
        self._prepare()
        database = Category.objects.get(code=9)
        chosen = LearningNote.objects.create(
            category=database, topic='正規化',
            title='正規化の解説', body='本文', source='テスト',
        )
        self._add_questions(database, '正規化', 4)
        api_post(self.client, 'api_learn', {'minutes': 5, 'note': chosen.pk})
        round_ = LearningRound.objects.get(learner=self.learner)
        self.assertEqual(round_.note_id, chosen.pk)
        for item in round_.items.select_related('question'):
            self.assertEqual(item.question.category_id, database.pk)

    def test_an_unknown_note_is_not_accepted(self):
        self._prepare()
        for note in (999999, 'abc'):
            with self.subTest(note=note):
                response = api_post(self.client, 'api_learn', {'minutes': 5, 'note': note})
                self.assertEqual(response.status_code, 400)
        self.assertEqual(LearningRound.objects.count(), 0)

    def test_a_note_without_questions_is_reported(self):
        """解説はあるが、その分野の問題が無いとき。"""
        LearningNote.objects.all().delete()
        note = LearningNote.objects.create(
            category=Category.objects.get(code=23),
            topic='法務', title='法務の解説', body='本文',
        )
        response = api_post(self.client, 'api_learn', {'minutes': 5, 'note': note.pk})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['detail'], '「法務の解説」に出題できる問題がありません。')
        self.assertEqual(LearningRound.objects.count(), 0)

    def test_a_note_without_questions_is_never_picked_automatically(self):
        """おまかせは、出題できる問題を持つ解説だけから選ぶ。

        持たない解説を選ぶと、読ませたあとに出題できず、始められないため。
        """
        self._prepare()
        empty = LearningNote.objects.create(
            category=Category.objects.get(code=23),
            topic='出題のない小分類', title='法務の解説', body='本文',
        )
        for _ in range(20):
            self.assertNotEqual(pick_note(self.learner, Question.SUBJECT_A), empty)

    def test_the_menu_tells_how_many_questions_each_note_has(self):
        """解説ごとに出題できる問数を添える。0問の解説は選べないと分かるように。"""
        self._prepare()
        database = Category.objects.get(code=9)
        LearningNote.objects.create(
            category=database, topic='出題のない小分類',
            title='まだ問題のない解説', body='本文',
        )
        groups = {
            g['category'].code: g for g in note_menu(self.learner, Question.SUBJECT_A)
        }
        counts = {
            e['note'].title: e['questions'] for e in groups[9]['notes']
        }
        self.assertEqual(counts['まだ問題のない解説'], 0)
        self.assertEqual(counts['データベースのしくみ'], 12)

    def test_notes_are_offered_per_subject(self):
        """解説も科目で絞る。科目Aの回で科目Bの解説が出てはいけない。"""
        self._prepare()
        b = Category.objects.filter(subject='B').first()
        LearningNote.objects.create(
            category=b, topic=b.name,
            title='科目Bの解説', body='本文', source='テスト',
        )

        a_menu = note_menu(self.learner, Question.SUBJECT_A)
        b_menu = note_menu(self.learner, Question.SUBJECT_B)
        self.assertNotIn(b.id, [g['category'].id for g in a_menu])
        self.assertEqual([g['category'].id for g in b_menu], [b.id])

        for _ in range(20):
            note = pick_note(self.learner, Question.SUBJECT_A)
            self.assertEqual(note.category.subject, Question.SUBJECT_A)

    def test_a_note_from_the_other_subject_is_refused(self):
        self._prepare()
        b = Category.objects.filter(subject='B').first()
        theirs = LearningNote.objects.create(
            category=b, topic=b.name,
            title='科目Bの解説', body='本文',
        )
        response = api_post(self.client, 'api_learn', {'minutes': 5, 'note': theirs.pk})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(LearningRound.objects.count(), 0)

    def _set_category(self, category):
        session, _ = StudySession.objects.get_or_create(learner=self.learner)
        session.mode = StudySession.MODE_CATEGORY
        session.category = category
        session.save()
        return session

    def _finish_round(self, note):
        """その解説のラウンドを、最後まで解いて終わらせる。"""
        api_post(self.client, 'api_learn', {'minutes': 5, 'note': note.pk})
        round_ = LearningRound.objects.filter(learner=self.learner).first()
        api_post(self.client, 'api_learn_read', {}, round_.pk)
        for _ in range(round_.total):
            item = round_.items.get(order=round_.position)
            api_post(self.client, 'api_learn_quiz', {'choice': item.question.answer_index}, round_.pk)
            api_post(self.client, 'api_learn_next', {}, round_.pk)
            round_.refresh_from_db()
        return round_

    def _opened_codes(self, response=None):
        """学習モードの一覧で、最初から開いておく中分類の番号。"""
        groups = api_get(self.client, 'api_learn').json()['groups']
        return sorted(g['code'] for g in groups if g['opened'])

    def test_the_dashboard_category_is_opened(self):
        """まだ学習していなければ、ダッシュボードで指定した分野を開く。選んだ状態にはしない。"""
        self._prepare()
        self._set_category(Category.objects.get(code=9))
        self.assertEqual(self._opened_codes(), [9])
        self.assertIn('useState<number | null>(null)', frontend_source('LearnStartPage.tsx'))

    def test_the_dashboard_category_follows_a_new_choice(self):
        """解き終えたあとで分野を指定し直せば、指定し直した分野も開く。

        前は直前に解き終えた中分類だけを開いていたので、一度コンピュータ構成要素を
        解き終えると、ダッシュボードで分野をどう選び直しても、学習モードのトップは
        そこだけが開いたまま変わらなかった。
        """
        self._prepare()
        hardware = Category.objects.get(code=3)
        note = LearningNote.objects.create(
            category=hardware, topic=hardware.name, title='構成要素の解説', body='本文',
        )
        security = Category.objects.get(code=11)
        LearningNote.objects.create(
            category=security, topic=security.name, title='セキュリティの解説', body='本文',
        )
        self._finish_round(note)
        self.assertEqual(self._opened_codes(), [3])

        for code in (9, 11, 9):
            self._set_category(Category.objects.get(code=code))
            self.assertEqual(self._opened_codes(), [3, code])

        # 指定した分野を解き終えたなら、同じ中分類なので1つだけ開く
        self._set_category(hardware)
        self.assertEqual(self._opened_codes(), [3])

    def test_the_last_studied_category_is_opened(self):
        """指定とは別の分野を解き終えたら、指定した分野と、解き終えた中分類の両方を開く。

        学習回数は小分類の行に出るので、閉じたままだと学習したことが見えない。
        指定した分野も閉じないので、ダッシュボードの指定と一覧の開く先がずれない。
        """
        self._prepare()
        security = Category.objects.get(code=11)
        note = LearningNote.objects.create(
            category=security, topic=security.name, title='セキュリティの解説', body='本文',
        )
        self._set_category(Category.objects.get(code=9))
        self._finish_round(note)
        self.assertEqual(self._opened_codes(), [9, 11])

        # 途中のラウンドは数えない。終わったものだけが「直前に学習した」になる。
        api_post(self.client, 'api_learn',
                 {'minutes': 5, 'note': LearningNote.objects.get(category__code=9).pk})
        self._set_category(None)
        self.assertEqual(self._opened_codes(), [11])

    def test_the_auto_pick_stays_inside_the_dashboard_category(self):
        """分野を指定していれば、おまかせもその分野の中から選ぶ。"""
        self._prepare()
        database = Category.objects.get(code=9)
        for code in (11, 23):
            other = Category.objects.get(code=code)
            LearningNote.objects.create(
                category=other, topic=other.name,
                title='{}の解説'.format(other.name), body='本文',
            )
        self._set_category(database)

        for _ in range(10):
            api_post(self.client, 'api_learn', {'minutes': 5})
            round_ = LearningRound.objects.get(learner=self.learner)
            self.assertEqual(round_.note.category_id, database.pk)

    def test_the_auto_pick_covers_every_field_without_a_category(self):
        """分野を指定していなければ、おまかせは全分野から選ぶ。"""
        self._prepare()
        for code in (11, 23):
            other = Category.objects.get(code=code)
            LearningNote.objects.create(
                category=other, topic=other.name,
                title='{}の解説'.format(other.name), body='本文',
            )
        seen = set()
        for _ in range(30):
            api_post(self.client, 'api_learn', {'minutes': 5})
            seen.add(LearningRound.objects.get(learner=self.learner).note.category.code)
        self.assertGreater(len(seen), 1)

    def test_a_category_without_notes_is_reported(self):
        """指定した分野に出題できる解説が無ければ、始めずに知らせる。"""
        self._prepare()
        self._set_category(Category.objects.get(code=23))

        response = api_post(self.client, 'api_learn', {'minutes': 5})
        self.assertEqual(response.status_code, 400)
        self.assertIn('ダッシュボードの分野の指定を変えてください', response.json()['detail'])
        self.assertEqual(LearningRound.objects.count(), 0)

    def test_nothing_is_opened_without_a_category(self):
        """まだ学習していなければ、どの中分類も開かない。"""
        self._prepare()
        self.assertEqual(self._opened_codes(), [])

    def test_a_category_of_the_other_subject_is_not_used(self):
        """科目を切り替えたあとの指定は引き継がない。その科目には無い分類のため。"""
        self._prepare()
        self._set_category(Category.objects.filter(subject='B').first())
        # おまかせの範囲も絞らない。絞ると科目Aでは1本も選べなくなる。
        api_post(self.client, 'api_learn', {'minutes': 5})
        round_ = LearningRound.objects.get(learner=self.learner)
        self.assertEqual(round_.note.category.subject, Question.SUBJECT_A)

    def test_a_round_can_be_abandoned_from_the_quiz(self):
        """解答の途中でやめて学習モードトップへ戻れる。ラウンドは残さない。"""
        self._prepare()
        api_post(self.client, 'api_learn', {'minutes': 5})
        round_ = LearningRound.objects.get(learner=self.learner)
        api_post(self.client, 'api_learn_read', {}, round_.pk)

        # 1問だけ解いてからやめる
        item = round_.items.get(order=0)
        api_post(self.client, 'api_learn_quiz', {'choice': item.question.answer_index}, round_.pk)
        response = api_post(self.client, 'api_learn_abandon', {}, round_.pk)
        self.assertTrue(response.json()['abandoned'])
        self.assertEqual(LearningRound.objects.count(), 0)

        # 解いたぶんの記録は残る。ラウンドとは別に積んでいるため。
        self.assertEqual(Attempt.objects.filter(learner=self.learner).count(), 1)
        self.assertEqual(
            CategoryProgress.objects.filter(learner=self.learner).aggregate(
                n=Sum('answered'))['n'], 1,
        )

    def test_a_finished_round_is_not_deleted(self):
        """終わったラウンドは結果を見返すためのものなので、中断では消さない。"""
        self._prepare()
        api_post(self.client, 'api_learn', {'minutes': 5})
        round_ = LearningRound.objects.get(learner=self.learner)
        round_.phase = LearningRound.PHASE_DONE
        round_.save(update_fields=['phase'])

        response = api_post(self.client, 'api_learn_abandon', {}, round_.pk)
        self.assertFalse(response.json()['abandoned'])
        self.assertEqual(LearningRound.objects.count(), 1)

    def test_starting_a_new_round_clears_the_left_over_one(self):
        """画面を離れて置き去りになったラウンドは、次を始めるときに片づける。"""
        self._prepare()
        api_post(self.client, 'api_learn', {'minutes': 5})
        left_over = LearningRound.objects.get(learner=self.learner)

        api_post(self.client, 'api_learn', {'minutes': 5})
        rounds = LearningRound.objects.filter(learner=self.learner)
        self.assertEqual(rounds.count(), 1)
        self.assertNotEqual(rounds.first().pk, left_over.pk)

    def test_a_finished_round_survives_the_next_one(self):
        """終わったラウンドは、次を始めても残る。結果を見返せなくなるため。"""
        self._prepare()
        api_post(self.client, 'api_learn', {'minutes': 5})
        done = LearningRound.objects.get(learner=self.learner)
        done.phase = LearningRound.PHASE_DONE
        done.save(update_fields=['phase'])

        api_post(self.client, 'api_learn', {'minutes': 5})
        self.assertEqual(LearningRound.objects.filter(learner=self.learner).count(), 2)
        self.assertTrue(LearningRound.objects.filter(pk=done.pk).exists())

    def test_another_account_cannot_abandon_the_round(self):
        self._prepare()
        api_post(self.client, 'api_learn', {'minutes': 5})
        round_ = LearningRound.objects.get(learner=self.learner)

        enter(self.client, make_learner('stranger3'))
        response = api_post(self.client, 'api_learn_abandon', {}, round_.pk)
        self.assertEqual(response.status_code, 404)
        self.assertTrue(LearningRound.objects.filter(pk=round_.pk).exists())

    def test_another_account_cannot_open_the_round(self):
        self._prepare()
        api_post(self.client, 'api_learn', {'minutes': 5})
        round_ = LearningRound.objects.get(learner=self.learner)

        enter(self.client, make_learner('stranger2'))
        for name in ('api_learn_read', 'api_learn_quiz', 'api_learn_result'):
            with self.subTest(api=name):
                self.assertEqual(api_get(self.client, name, round_.pk).status_code, 404)
        for name in ('api_learn_read', 'api_learn_quiz', 'api_learn_next', 'api_learn_timer'):
            with self.subTest(api=name):
                self.assertEqual(api_post(self.client, name, {'choice': 0}, round_.pk).status_code, 404)


class SiteSummaryTests(TestCase):
    """ダッシュボードの「みんなの集計」。全利用者の合計と、合格の申告。"""

    @classmethod
    def setUpTestData(cls):
        seed_masters()
        cls.alice = make_learner('alice')
        cls.bob = make_learner('bob')
        make_learner('idle')  # 1問も解いていない人は「学習した人」に数えない
        build_questions()
        build_questions()

    def setUp(self):
        enter(self.client, self.alice)

    def _question(self, learner, code):
        return Question.objects.filter(category__code=code).first()

    def test_counts_every_users_answers_by_category(self):
        answer(self.alice, self._question(self.alice, 11), True)
        answer(self.alice, self._question(self.alice, 11), False)
        answer(self.bob, self._question(self.bob, 11), True)
        answer(self.bob, self._question(self.bob, 101), False)

        summary = site_summary()
        self.assertEqual(summary['total'], 4)
        self.assertEqual(summary['correct'], 2)
        self.assertEqual(summary['learners'], 2)

        subject_a, subject_b = summary['subjects']
        security = next(r for r in subject_a['rows'] if r['category'].code == 11)
        self.assertEqual((security['total'], security['correct']), (3, 2))
        self.assertEqual(security['share_percent'], 100.0)
        self.assertEqual(subject_b['total'], 1)
        # 分野の内訳は科目Aだけに付く
        self.assertTrue(subject_a['fields'])
        self.assertEqual(subject_b['fields'], [])

    def test_total_survives_reimport(self):
        """のべ解答数は、問題を取り込み直しても減らない。

        取り込みは同期なので、変わっていない問題はそのまま残り、解答履歴も
        切れない。仮に問題が入れ替わっても、のべ数は消えない CategoryProgress
        から数えているので減らない。
        """
        answer(self.alice, self._question(self.alice, 11), True)
        build_questions()
        self.assertTrue(
            Attempt.objects.filter(learner=self.alice).exists(),
            '同じ内容を取り込み直しただけなら、解答履歴は残る',
        )
        self.assertEqual(site_summary()['total'], 1)

    def test_dashboard_shows_summary(self):
        """みんなの集計は、ダッシュボードの後半に出す。他人の名前は出さない。"""
        answer(self.bob, self._question(self.bob, 11), True)
        response = api_get(self.client, 'api_dashboard')
        self.assertEqual(response.json()['summary']['total'], 1)
        self.assertEqual(response.json()['summary']['learners'], 1)
        self.assertNotContains(response, 'bob')
        self.assertIn('みんなの集計', frontend_source('Dashboard.tsx'))

    def test_report_and_withdraw_pass(self):
        response = api_post(self.client, 'api_pass', {'passed_on': '2026-06-01'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(site_summary()['passers'], 1)
        self.assertEqual(api_get(self.client, 'api_dashboard').json()['my_report'],
                         {'passed_on': '2026-06-01'})

        # 申告し直しても1人は1件のまま
        api_post(self.client, 'api_pass', {'passed_on': '2026-07-01'})
        self.assertEqual(PassReport.objects.count(), 1)
        self.assertEqual(str(PassReport.objects.get().passed_on), '2026-07-01')

        self.client.delete(reverse('fe:api_pass'))
        self.assertEqual(site_summary()['passers'], 0)
        self.assertIsNone(api_get(self.client, 'api_dashboard').json()['my_report'])

    def test_future_date_is_rejected(self):
        for value in ('2999-01-01', '', 'きのう'):
            with self.subTest(value=value):
                response = api_post(self.client, 'api_pass', {'passed_on': value})
                self.assertEqual(response.status_code, 400)
        self.assertFalse(PassReport.objects.exists())

    def test_pass_report_requires_login(self):
        """ID で入っていなければ申告できない（ブラウザを閉じて抜けたときなど）。"""
        client = self.client_class()
        response = api_post(client, 'api_pass', {'passed_on': '2026-06-01'})
        self.assertEqual(response.status_code, 401)
        self.assertFalse(PassReport.objects.exists())


class SeedCommandTests(TestCase):
    def test_seed_loads_masters_but_no_questions(self):
        """アプリは問題を同梱しないので、コマンドでも問題は入らない。"""
        seed_masters()
        self.assertEqual(Category.objects.filter(subject='A').count(), 23)
        self.assertEqual(Category.objects.filter(subject='B').count(), 5)
        self.assertEqual(QuestionTemplate.objects.count(), len(REGISTRY))
        self.assertEqual(Question.objects.count(), 0)


class ExamDefinitionTests(TestCase):
    """試験ごとにアプリを作る前提なので、対象試験と必要資料は1か所で定義する。"""

    @classmethod
    def setUpTestData(cls):
        seed_masters()

    def test_required_materials_are_declared(self):
        self.assertTrue(EXAM['name'])
        self.assertTrue(EXAM['url'])
        self.assertTrue(EXAM['materials'], '必要な資料が1つも書かれていない')
        for material in EXAM['materials']:
            with self.subTest(name=material.get('name')):
                self.assertTrue(material['name'])
                self.assertTrue(material['purpose'], '何に使う資料かを書く')

    def test_prompt_lists_the_required_materials(self):
        """資料を見ずに推測で作らせないよう、プロンプトに資料名を並べる。"""
        prompt = build_prompt()
        for material in EXAM['materials']:
            self.assertIn(material['name'], prompt)
        self.assertIn('推測で作らないでください', prompt)

    def test_prompt_lists_every_category(self):
        """分野を増やしてもプロンプトが追随すること。"""
        prompt = build_prompt()
        for category in Category.objects.all():
            with self.subTest(category=category.name):
                self.assertIn(category.name, prompt)

    def test_weights_add_up_to_the_real_exam(self):
        """想定出題数の合計は、本番の出題数と一致させる。

        1分野でも足し忘れると、重み付き抽選が本番の比率からずれる。
        """
        for subject, expected in ((Question.SUBJECT_A, 60), (Question.SUBJECT_B, 20)):
            with self.subTest(subject=subject):
                total = sum(
                    Category.objects.filter(subject=subject)
                    .values_list('exam_weight', flat=True)
                )
                self.assertEqual(total, expected)

    def test_every_category_can_be_drawn(self):
        """どの中分類にも最低1問の重みを置く。0 だと永久に出題されない。"""
        for category in Category.objects.all():
            with self.subTest(category=category.name):
                self.assertGreaterEqual(category.exam_weight, 1)

    def test_weights_follow_the_published_exams_not_syllabus_volume(self):
        """配分はシラバスの分量ではなく、公開問題の実測に沿わせる。

        小分類の数で按分すると実態と逆向きになる（セキュリティが薄く、
        プロジェクトマネジメントが厚くなる）。取り違えを防ぐために固定する。
        """
        weight = dict(Category.objects.values_list('code', 'exam_weight'))
        # セキュリティは本番で最も多く出る中分類
        self.assertEqual(weight[11], max(
            w for c, w in weight.items() if c < 100
        ))
        # プロジェクトマネジメントは小分類が11と最多だが、出題は少ない
        self.assertLess(weight[14], weight[11])

    def test_upload_screen_shows_the_materials(self):
        login_editor(self.client)
        response = self.client.get(reverse('fe:manage_upload'))
        self.assertEqual(response.status_code, 200)
        for material in EXAM['materials']:
            self.assertContains(response, material['name'])
        self.assertContains(response, EXAM['url'])

    def test_dashboard_has_no_materials(self):
        """問題を作る資料の案内は取り込み画面にだけ置き、ダッシュボードには出さない。"""
        learner = make_learner('materials_dash')
        enter(self.client, learner)
        response = api_get(self.client, 'api_dashboard')
        self.assertNotContains(response, '問題を作るのに必要な資料')
        self.assertEqual(response.json()['question_total'], 0)
        source = frontend_source('Dashboard.tsx')
        self.assertNotIn('問題を作るのに必要な資料', source)
        self.assertIn('問題集はまだ用意されていません', source)


class ManageNeedsLoginTests(TestCase):
    """問題の管理は、編集画面のログインだけが要る。スタッフ権限も学習用の ID も問わない。"""

    PAGES = ('fe:manage_list', 'fe:manage_upload')

    @classmethod
    def setUpTestData(cls):
        seed_masters()

    def _login_as(self, username):
        account = get_user_model().objects.create_user(username=username, password='pass12345')
        self.client.force_login(account)

    def test_learning_pages_do_not_reveal_the_console(self):
        """ダッシュボードや問題の画面には、管理ページの存在を出さない。"""
        build_questions()
        learner = make_learner('hidden')
        enter(self.client, learner)
        for url in (dashboard(learner), reverse('fe:quiz'), reverse('fe:learn_start'),
                    reverse('fe:stats'), reverse('fe:history'), reverse('fe:about'),
                    reverse('fe:id_entry')):
            with self.subTest(url=url):
                html = self.client.get(url).content.decode('utf-8')
                self.assertNotIn('/fe/console/', html)
                self.assertNotIn('問題の管理', html)
                self.assertNotIn('取り込', html)

    def test_an_ordinary_account_can_manage_without_any_id(self):
        """スタッフ権限のない共用の編集アカウントで使える。"""
        self._login_as('shared')
        for name in self.PAGES:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_an_ordinary_account_stays_out_of_admin(self):
        """問題の管理を使えても、/admin/ には入れない。"""
        self._login_as('shared')
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response['Location'])



def png_uri(width=1, extra=b''):
    """テスト用の小さな PNG を data URI にする。extra で大きさを水増しできる。"""
    import base64, struct, zlib

    def chunk(kind, data):
        body = kind + data
        return struct.pack('>I', len(data)) + body + struct.pack('>I', zlib.crc32(body))

    raw = b''.join(b'\x00' + b'\xff' * width for _ in range(1))
    png = (b'\x89PNG\r\n\x1a\n'
           + chunk(b'IHDR', struct.pack('>IIBBBBB', width, 1, 8, 0, 0, 0, 0))
           + chunk(b'IDAT', zlib.compress(raw))
           + (chunk(b'tEXt', extra) if extra else b'')
           + chunk(b'IEND', b''))
    return 'data:image/png;base64,' + base64.b64encode(png).decode('ascii')


class FigureTests(TestCase):
    """図のある問題。公開問題の図を PNG の data URI で持ち、画面に出す。"""

    @classmethod
    def setUpTestData(cls):
        seed_masters()

    def _record(self, **extra):
        record = {
            'category': 2, 'subject': 'A', 'topic': 'データ構造',
            'stem': '図の木構造は2分探索木である。', 'choices': ['ア案', 'イ案', 'ウ案', 'エ案'],
            'answer': 1, 'source': '令和7年度 科目A 問3',
        }
        record.update(extra)
        return record

    def _sync(self, *records):
        return sync(validate({'questions': list(records), 'notes': None}))

    def test_figures_are_imported_and_kept(self):
        figure = {'src': png_uri(), 'alt': '根が a の2分木'}
        self._sync(self._record(figures=[figure], choice_figures=[png_uri(), None, png_uri(2), None]))
        question = Question.objects.get(template__isnull=True)
        self.assertEqual(question.figures, [figure])
        self.assertIsNone(question.choice_figure(1), '図の無い選択肢は null のまま')
        self.assertEqual(question.answer_figure, None)
        self.assertEqual(question.choice_rows()[2][3], png_uri(2))

    def test_questions_without_figures_still_import(self):
        self._sync(self._record())
        question = Question.objects.get(template__isnull=True)
        self.assertEqual(question.figures, [])
        self.assertIsNone(question.choice_figures)

    def test_changing_a_figure_is_an_update_and_keeps_the_history(self):
        """図は鍵に入らない。図を差し替えても同じ問題のままで、解答履歴は切れない。"""
        self._sync(self._record(figures=[{'src': png_uri(), 'alt': '旧'}]))
        question = Question.objects.get(template__isnull=True)
        answer(make_learner('figure'), question, correct=True)

        result = self._sync(self._record(figures=[{'src': png_uri(3), 'alt': '新'}]))
        self.assertEqual(result['questions']['updated'], 1)
        self.assertEqual(result['questions']['removed'], 0)
        self.assertTrue(Attempt.objects.filter(question=question).exists())
        question.refresh_from_db()
        self.assertEqual(question.figures[0]['alt'], '新')

    def test_broken_figures_are_rejected(self):
        ok = {'src': png_uri(), 'alt': '図'}
        jpeg = 'data:image/jpeg;base64,' + png_uri().split(',', 1)[1]
        not_png = 'data:image/png;base64,' + __import__('base64').b64encode(b'GIF89a....').decode()
        cases = {
            '配列でない': {'figures': ok},
            'src が画像でない': {'figures': [{'src': 'javascript:alert(1)', 'alt': '図'}]},
            'PNG 以外の形式': {'figures': [{'src': jpeg, 'alt': '図'}]},
            '中身が PNG でない': {'figures': [{'src': not_png, 'alt': '図'}]},
            'base64 が壊れている': {'figures': [{'src': 'data:image/png;base64,@@@', 'alt': '図'}]},
            '大きすぎる': {'figures': [{'src': png_uri(extra=b'x' * (301 * 1024)), 'alt': '図'}]},
            'alt が空': {'figures': [{'src': png_uri(), 'alt': ' '}]},
            '余計なキー': {'figures': [dict(ok, title='x')]},
            '選択肢の図の数が違う': {'choice_figures': [png_uri()]},
            '選択肢の図が画像でない': {'choice_figures': ['x', None, None, None]},
        }
        for label, extra in cases.items():
            with self.subTest(label=label):
                with self.assertRaises(ImportError_):
                    validate({'questions': [self._record(**extra)], 'notes': None})

    def test_source_longer_than_the_column_is_rejected(self):
        """SQLite は長さを見ないので、検査しないと手元で通って本番で落ちる。"""
        long = 'シラバス Ver.8.0 中分類2 データ構造' + '（1）項目' * 60
        with self.assertRaises(ImportError_):
            validate({'questions': [self._record(source=long)], 'notes': None})
        with self.assertRaises(ImportError_):
            validate({'questions': None, 'notes': [
                {'category': 2, 'topic': 'データ構造', 'title': 't', 'body': 'b', 'source': long}]})
        # 項目まで書いた転記の出典は通る
        validate({'questions': [self._record(
            source='令和7年度 科目A 問3（中分類2 データ構造（2）木構造）')], 'notes': None})

    def test_quiz_shows_the_figures(self):
        self._sync(self._record(
            figures=[{'src': png_uri(), 'alt': '根が a の2分木'}],
            choice_figures=[png_uri(4), None, None, None],
        ))
        # テンプレートが生成する計算問題が選ばれないよう、その問題だけにする。
        # 生成済みの問題を消すだけでは、出題のときにテンプレートから作り直されて
        # ときどきそちらが出るので、テンプレートも止める。
        Question.objects.filter(template__isnull=False).delete()
        QuestionTemplate.objects.update(is_active=False)
        enter(self.client, make_learner('seer'))
        data = api_get(self.client, 'api_quiz_next').json()['question']
        self.assertEqual(data['figures'], [{'src': png_uri(), 'alt': '根が a の2分木'}])
        self.assertEqual(data['choices'][0]['figure'], png_uri(4))
        self.assertIsNone(data['choices'][1]['figure'])

        question = Question.objects.get(pk=data['id'])
        result = api_post(self.client, 'api_quiz_answer', {
            'question_id': question.id, 'choice': question.answer_index,
        }).json()
        self.assertEqual(result['answer_figure'], None)
        # 画面は答えた後も同じ問題（図つき）を出したまま、正誤と解説を足す
        self.assertIn('<Stem question={q} />', frontend_source('QuizPage.tsx'))


class NoteAudioTests(TestCase):
    """技術解説の読み上げ。音声は解説ごとに一度だけ作り、読んでいる間は時間を止める。"""

    @classmethod
    def setUpTestData(cls):
        seed_masters()
        cls.learner = make_learner('listener')

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        override = override_settings(FE_AUDIO_ROOT=folder.name)
        override.enable()
        self.addCleanup(override.disable)
        self.root = Path(folder.name)
        enter(self.client, self.learner)

    def _start_round(self):
        build_questions(per_category=12)
        LearningNote.objects.all().delete()
        for note in build_notes(codes=(9,)):
            LearningNote.objects.create(
                category=Category.objects.get(code=note['category']),
                topic=note['topic'], title=note['title'],
                body=note['body'], source=note['source'],
            )
        api_post(self.client, 'api_learn', {'minutes': 5})
        return LearningRound.objects.get(learner=self.learner)

    def _put_audio(self, note, data=b'0123456789'):
        (self.root / speech.audio_name(note)).write_bytes(data)

    def test_spoken_text_reads_symbols_as_words(self):
        self.assertEqual(speech.spoken_text('n×(n−1)÷2'), 'nかける(nひく1)わる2')
        self.assertEqual(speech.spoken_text('相関係数は−1から1'), '相関係数はマイナス1から1')
        self.assertEqual(speech.spoken_text('30＋22、P＝10'), '30たす22、Pイコール10')
        self.assertEqual(speech.spoken_text('JavaやC++'), 'Javaやシープラスプラス')

    def test_long_text_is_split_at_paragraphs(self):
        text = '\n\n'.join(['あ' * 500, 'い' * 500, 'う' * 500])
        parts = speech.chunks(text)
        self.assertEqual(parts, ['あ' * 500 + '\n' + 'い' * 500, 'う' * 500])

    def test_name_changes_only_when_the_body_changes(self):
        note = LearningNote(title='見出し', body='本文')
        same = LearningNote(title='別の見出し', body='本文')
        edited = LearningNote(title='見出し', body='直した本文')
        self.assertEqual(speech.audio_name(note), speech.audio_name(same))
        self.assertNotEqual(speech.audio_name(note), speech.audio_name(edited))
        self.assertRegex(speech.audio_name(note), speech.NAME_PATTERN)

    def test_player_appears_only_when_the_audio_exists(self):
        round_ = self._start_round()
        notes = api_get(self.client, 'api_learn_read', round_.pk).json()['notes']
        self.assertIsNone(notes[0]['audio_url'])

        self._put_audio(round_.note)
        notes = api_get(self.client, 'api_learn_read', round_.pk).json()['notes']
        self.assertEqual(
            notes[0]['audio_url'], reverse('fe:note_audio', args=[speech.audio_name(round_.note)]),
        )
        # 画面は audio_url があるときだけ再生バーを出す
        self.assertIn('{note.audio_url && (', frontend_source('LearnReadPage.tsx'))

    def test_audio_answers_range_requests(self):
        """iPhone の Safari は Range 要求で取りに来るので、206 で一部だけ返す。"""
        round_ = self._start_round()
        self._put_audio(round_.note)
        url = reverse('fe:note_audio', args=[speech.audio_name(round_.note)])

        whole = self.client.get(url)
        self.assertEqual(whole.status_code, 200)
        self.assertEqual(b''.join(whole.streaming_content), b'0123456789')
        self.assertEqual(whole['Accept-Ranges'], 'bytes')

        part = self.client.get(url, HTTP_RANGE='bytes=0-1')
        self.assertEqual(part.status_code, 206)
        self.assertEqual(part.content, b'01')
        self.assertEqual(part['Content-Range'], 'bytes 0-1/10')

        tail = self.client.get(url, HTTP_RANGE='bytes=-3')
        self.assertEqual(tail.content, b'789')
        self.assertEqual(self.client.get(url, HTTP_RANGE='bytes=4-').content, b'456789')
        self.assertEqual(self.client.get(url, HTTP_RANGE='bytes=20-').status_code, 416)

    def test_audio_rejects_other_names_and_strangers(self):
        self.assertEqual(
            self.client.get(reverse('fe:note_audio', args=['db.sqlite3'])).status_code, 404
        )
        self.assertEqual(
            self.client.get(reverse('fe:note_audio', args=['0' * 20 + '.mp3'])).status_code, 404
        )
        round_ = self._start_round()
        self._put_audio(round_.note)
        stranger = self.client_class()
        response = stranger.get(reverse('fe:note_audio', args=[speech.audio_name(round_.note)]))
        self.assertRedirects(response, reverse('fe:index'), fetch_redirect_response=False)

    def test_time_spent_listening_is_not_counted(self):
        round_ = self._start_round()
        now = timezone.now()
        LearningRound.objects.filter(pk=round_.pk).update(
            started_at=now - timezone.timedelta(seconds=200),
            paused_at=now - timezone.timedelta(seconds=150),
        )
        round_.refresh_from_db()
        # 200秒前に始め、150秒前から止めている。進んだのは50秒だけ
        self.assertEqual(round_.remaining_seconds(now), 250)
        round_.resume(now)
        self.assertEqual(round_.paused_seconds, 150)
        self.assertEqual(round_.remaining_seconds(now), 250)

    def test_timer_endpoint_pauses_and_resumes(self):
        round_ = self._start_round()
        response = api_post(self.client, 'api_learn_timer', {'state': 'pause'}, round_.pk)
        self.assertIn('remaining', response.json())
        round_.refresh_from_db()
        self.assertIsNotNone(round_.paused_at)

        api_post(self.client, 'api_learn_timer', {'state': 'resume'}, round_.pk)
        round_.refresh_from_db()
        self.assertIsNone(round_.paused_at)

    def test_reloading_while_paused_starts_the_timer_again(self):
        """開き直すと読み上げは止まっているので、止めたままにしない。"""
        round_ = self._start_round()
        LearningRound.objects.filter(pk=round_.pk).update(
            paused_at=timezone.now() - timezone.timedelta(seconds=30),
        )
        api_get(self.client, 'api_learn_read', round_.pk)
        round_.refresh_from_db()
        self.assertIsNone(round_.paused_at)
        self.assertGreaterEqual(round_.paused_seconds, 30)

    def test_command_makes_only_missing_audio(self):
        round_ = self._start_round()
        notes = list(LearningNote.objects.all())
        self._put_audio(notes[0])
        calls = []

        def fake(text, key, region):
            calls.append(text)
            return b'mp3'

        with mock.patch.object(speech, 'synthesize', fake), \
                mock.patch.object(speech, 'REQUEST_INTERVAL', 0), \
                mock.patch.dict('os.environ', {'AZURE_SPEECH_KEY': 'k', 'AZURE_SPEECH_REGION': 'r'}):
            call_command('make_note_audio', stdout=io.StringIO())
        self.assertEqual(len(calls), len(notes) - 1)
        for note in notes:
            self.assertTrue(speech.has_audio(note))

        (self.root / ('f' * 20 + '.mp3')).write_bytes(b'old')
        call_command('make_note_audio', '--prune', stdout=io.StringIO())
        self.assertEqual(
            sorted(p.name for p in self.root.iterdir()),
            sorted(speech.audio_name(n) for n in notes),
        )

    def test_only_subject_a_notes_are_read_aloud(self):
        """科目Bの解説には音声を作らず、ファイルがあっても再生ボタンを出さない。"""
        round_ = self._start_round()
        b_category = Category.objects.filter(subject=Question.SUBJECT_B).first()
        b_note = LearningNote.objects.create(
            category=b_category, topic='擬似言語', title='科目Bの解説', body='科目Bの本文',
        )
        self.assertFalse(speech.speaks(b_note))
        self._put_audio(b_note)
        self.assertFalse(speech.has_audio(b_note))

        with mock.patch.object(speech, 'synthesize', return_value=b'mp3') as fake, \
                mock.patch.object(speech, 'REQUEST_INTERVAL', 0), \
                mock.patch.dict('os.environ', {'AZURE_SPEECH_KEY': 'k', 'AZURE_SPEECH_REGION': 'r'}):
            call_command('make_note_audio', stdout=io.StringIO())
        texts = [c.args[0] for c in fake.call_args_list]
        self.assertFalse(any('科目Bの本文' in t for t in texts))
        self.assertTrue(speech.has_audio(round_.note))

        LearningRound.objects.filter(pk=round_.pk).update(note=b_note)
        notes = api_get(self.client, 'api_learn_read', round_.pk).json()['notes']
        self.assertIsNone(notes[0]['audio_url'])


class MailTests(TestCase):
    """問題メール。確認のメールを経た登録、メールのリンクからだけの解除、
    9〜18時の毎時に3問（IPA 公開問題・おまかせ）、1問ごとの解答ページでの記録。"""

    @classmethod
    def setUpTestData(cls):
        seed_masters()

    def setUp(self):
        from django.core import mail as outbox
        self.outbox = outbox
        self.learner = make_learner('mailer')
        enter(self.client, self.learner)

    def _sync(self, counts, source='令和6年度 科目A 問{}'):
        """{(中分類番号, 小分類): 問数} の問題を作る。出典は既定で IPA の公開問題。

        取り込みは科目ごとの一括差し替えなので、出典を変えて混ぜたいときは
        _sync_groups でまとめて取り込む。
        """
        return self._sync_groups([(counts, source)])

    def _sync_groups(self, groups):
        records = []
        serial = 0
        for counts, source in groups:
            records += self._records(counts, source, serial)
            serial += len(records)
        return sync(validate({'questions': records, 'notes': None}))

    def _records(self, counts, source, serial):
        records = []
        for (code, topic), n in counts.items():
            category = Category.objects.get(code=code)
            for i in range(n):
                serial += 1
                records.append({
                    'category': code, 'subject': category.subject, 'topic': topic,
                    'stem': '{}の問題{}'.format(topic, i),
                    'choices': ['選択肢{}-{}'.format(j, i) for j in range(6 if code > 100 else 4)],
                    'answer': 1, 'explanation': '{}の解説{}'.format(topic, i),
                    'source': source.format(serial) if '{}' in source else source,
                })
        return records

    def _subscribe(self, email='me@example.com', **fields):
        from .models import MailSubscription
        subscription, _ = MailSubscription.objects.get_or_create(learner=self.learner)
        subscription.email = email
        for key, value in fields.items():
            setattr(subscription, key, value)
        subscription.save()
        return subscription

    def _link(self, message):
        return urlsplit(re.search(r'http://\S+/fe/mail/\S+/', message.body).group(0)).path

    def _answer_links(self, message):
        return [url.split('8010', 1)[1] for url in re.findall(r'http://\S+/fe/m/\w+/', message.body)]

    # ---- 登録と解除 ----

    def test_address_is_saved_only_after_pressing_receive(self):
        from .models import MailSubscription
        response = api_post(self.client, 'api_mail', {'email': 'me@example.com'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['pending'])
        self.assertEqual(len(self.outbox.outbox), 1)
        self.assertEqual(self.outbox.outbox[0].to, ['me@example.com'])
        self.assertIn('9時から18時まで毎時', self.outbox.outbox[0].body)
        subscription = MailSubscription.objects.get(learner=self.learner)
        self.assertEqual(subscription.email, '')

        link = self._link(self.outbox.outbox[0])
        self.client.logout()  # 別の端末で開いても使える
        self.assertContains(self.client.get(link), '受け取る')
        subscription.refresh_from_db()
        self.assertEqual(subscription.email, '', '開いただけでは登録しない')
        self.assertContains(self.client.post(link), '登録しました')
        subscription.refresh_from_db()
        self.assertEqual(subscription.email, 'me@example.com')
        self.assertContains(self.client.post(link), 'このリンクは使えません')

    def test_old_confirm_link_dies_when_another_address_is_requested(self):
        api_post(self.client, 'api_mail', {'email': 'a@example.com'})
        old = self._link(self.outbox.outbox[0])
        with override_settings(FE_MAIL_LINK_INTERVAL=0):
            api_post(self.client, 'api_mail', {'email': 'b@example.com'})
        self.assertContains(self.client.post(old), 'このリンクは使えません')
        self.assertContains(self.client.post(self._link(self.outbox.outbox[1])), '登録しました')

    def test_confirmation_mails_are_throttled(self):
        api_post(self.client, 'api_mail', {'email': 'a@example.com'})
        response = api_post(self.client, 'api_mail', {'email': 'b@example.com'})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(len(self.outbox.outbox), 1)

    def test_a_bad_address_is_refused(self):
        response = api_post(self.client, 'api_mail', {'email': 'not-an-address'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(self.outbox.outbox), 0)

    def test_registered_address_cannot_be_changed_from_the_screen(self):
        self._subscribe()
        response = api_post(self.client, 'api_mail', {'email': 'attacker@example.com'})
        self.assertEqual(response.status_code, 400)
        subscription = self.learner.mail_subscription
        subscription.refresh_from_db()
        self.assertEqual(subscription.email, 'me@example.com')
        self.assertEqual(len(self.outbox.outbox), 0)
        data = api_get(self.client, 'api_mail').json()
        self.assertEqual(data, {'registered': True, 'masked_email': 'm***@example.com', 'pending': False,
                                'with_id': True})

    def test_stop_only_from_the_mailed_link(self):
        """解除は、届いた問題メールの末尾のリンクからだけ（ID のあり・なしとも。画面からは解除しない）。"""
        from .mail import send_slot
        self._sync({(11, '情報セキュリティ'): 3})
        subscription = self._subscribe()
        send_slot('h09')
        self.assertEqual(self.outbox.outbox[0].to, ['me@example.com'])
        link = self._link(self.outbox.outbox[0])
        self.assertIn('/fe/mail/stop/', link)
        self.assertNotIn('解除用のメール', frontend_source('MailSection.tsx'))
        self.client.get(link)
        subscription.refresh_from_db()
        self.assertEqual(subscription.email, 'me@example.com', '開いただけでは解除しない')
        self.assertContains(self.client.post(link), '配信を止めました')
        subscription.refresh_from_db()
        self.assertEqual(subscription.email, '')

    def test_addresses_are_encrypted_in_the_db(self):
        from django.db import connection
        api_post(self.client, 'api_mail', {'email': 'secret@example.com'})
        with connection.cursor() as cursor:
            cursor.execute('SELECT email_enc, pending_email_enc FROM funitclub_fe_mail_subscription')
            rows = cursor.fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], '')
        self.assertNotIn('secret', rows[0][1])
        self.assertEqual(self.learner.mail_subscription.pending_email, 'secret@example.com')

        self.client.post(self._link(self.outbox.outbox[0]))
        with connection.cursor() as cursor:
            cursor.execute('SELECT email_enc, pending_email_enc FROM funitclub_fe_mail_subscription')
            email_enc, pending_enc = cursor.fetchone()
        self.assertNotIn('secret', email_enc)
        self.assertEqual(pending_enc, '')
        self.learner.mail_subscription.refresh_from_db()
        self.assertEqual(self.learner.mail_subscription.email, 'secret@example.com')

    def test_unreadable_address_counts_as_unregistered(self):
        """SECRET_KEY を替えて読めなくなった宛先には送らない。"""
        from .mail import send_slot
        self._sync({(11, '情報セキュリティ'): 3})
        self._subscribe()
        with override_settings(SECRET_KEY='another-key-' + 'x' * 40, SECRET_KEY_FALLBACKS=[]):
            self.assertEqual(self.learner.mail_subscription.email, '')
            self.assertEqual(send_slot('h09')['sent'], 0)

    def test_pending_address_is_purged_after_the_deadline(self):
        from .mail import purge_pending
        api_post(self.client, 'api_mail', {'email': 'late@example.com'})
        subscription = self.learner.mail_subscription
        link = self._link(self.outbox.outbox[0])
        sent_at = subscription.link_sent_at
        self.assertEqual(purge_pending(sent_at + timezone.timedelta(minutes=59)), 0)
        self.assertEqual(purge_pending(sent_at + timezone.timedelta(minutes=61)), 1)
        subscription.refresh_from_db()
        self.assertEqual(subscription.pending_email, '')
        self.assertContains(self.client.post(link), 'このリンクは使えません')

    def test_dashboard_and_each_run_purge_expired_pending(self):
        from .mail import send_slot
        from .models import MailSubscription
        api_post(self.client, 'api_mail', {'email': 'late@example.com'})
        MailSubscription.objects.update(link_sent_at=timezone.now() - timezone.timedelta(hours=2))
        self.assertFalse(api_get(self.client, 'api_mail').json()['pending'])
        self.assertEqual(MailSubscription.objects.exclude(pending_email_enc='').count(), 0)

        MailSubscription.objects.update(pending_email_enc='x', link_sent_at=None)
        send_slot('h09')
        self.assertEqual(MailSubscription.objects.exclude(pending_email_enc='').count(), 0)

    def _subscribe_without_id(self, email='anon@example.com'):
        """ID なしで入ったブラウザから登録し、確認のリンクで確定する。"""
        from .models import MailSubscription
        client = self.client_class()
        client.get(reverse('fe:index'))
        response = api_post(client, 'api_mail', {'email': email})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['with_id'], False)
        self.assertTrue(response.json()['pending'])
        client.post(self._link(self.outbox.outbox[-1]))
        subscription = MailSubscription.objects.get(learner__isnull=True)
        self.assertEqual(subscription.email, email)
        self.assertTrue(api_get(client, 'api_mail').json()['registered'])
        return client, subscription

    def test_mail_can_be_received_without_an_id(self):
        """ID なしでも登録できる。ID の記録（ブラウザを閉じると使えなくなる）にはひも付けない。"""
        client, subscription = self._subscribe_without_id()
        self.assertIsNone(subscription.learner)
        self.assertNotIn('ID「', self.outbox.outbox[0].body)
        self.assertIn('みんなの集計にだけ数えます', self.outbox.outbox[0].body)

    def test_answers_without_an_id_go_only_to_the_site_summary(self):
        """ID なしのメールで答えた分は、みんなの集計にだけ足す。個人の記録には残さない。"""
        from .mail import send_slot
        from .models import MailQuestion
        self._sync({(11, '情報セキュリティ'): 5})
        self._subscribe_without_id()
        self.assertEqual(send_slot('h09')['sent'], 1)
        message = self.outbox.outbox[-1]
        self.assertIn('みんなの集計にだけ数えます', message.body)
        self.assertNotIn('あなたの分野別正答率', message.body)
        self.assertEqual(len(self._answer_links(message)), 3)

        item = MailQuestion.objects.order_by('number').first()
        before = site_summary()['total']
        page = self.client_class().post(reverse('fe:mail_answer', args=[item.code]),
                                        {'choice': item.question.answer_index})
        self.assertContains(page, '正解')
        self.assertContains(page, 'みんなの集計に数えました')
        self.assertEqual(site_summary()['total'], before + 1)
        self.assertEqual(OpenProgress.objects.get(category=item.question.category).correct, 1)
        self.assertFalse(Attempt.objects.exists())
        self.assertFalse(CategoryProgress.objects.exists())
        # 二重には数えない
        self.client_class().post(reverse('fe:mail_answer', args=[item.code]), {'choice': 0})
        self.assertEqual(site_summary()['total'], before + 1)

    def test_one_address_has_one_registration(self):
        """同じアドレスで別の登録を確定したら、前の登録は止める（ID あり→ID なしでも、その逆でも）。"""
        from .models import MailSubscription
        mine = self._subscribe(email='same@example.com')
        _client, anonymous = self._subscribe_without_id(email='same@example.com')
        mine.refresh_from_db()
        self.assertEqual(mine.email, '')
        self.assertEqual(anonymous.email, 'same@example.com')
        self.assertEqual(MailSubscription.objects.exclude(email_enc='').count(), 1)

    def test_empty_registrations_without_an_id_are_removed(self):
        """ID なしの登録は、確認の期限が切れたり解除したりしてアドレスが無くなったら消す。"""
        from .mail import purge_pending
        from .models import MailSubscription
        client = self.client_class()
        client.get(reverse('fe:index'))
        api_post(client, 'api_mail', {'email': 'late@example.com'})
        self.assertEqual(MailSubscription.objects.filter(learner__isnull=True).count(), 1)
        MailSubscription.objects.update(link_sent_at=timezone.now() - timezone.timedelta(hours=2))
        purge_pending()
        self.assertFalse(MailSubscription.objects.filter(learner__isnull=True).exists())
        # 期限が切れたら、また登録し直せる
        self.assertEqual(api_post(client, 'api_mail', {'email': 'late@example.com'}).status_code, 200)

    def test_the_screen_has_nothing_to_choose(self):
        """送り方は1つだけ。画面はアドレスを入れて受け取るだけ（解除は届いたメールのリンクから）。"""
        source = frontend_source('MailSection.tsx')
        self.assertNotIn('マラソン', source)
        self.assertNotIn('特訓', source)
        self.assertIn('9時から18時まで毎時', source)
        self.assertNotIn('TopicPicker.tsx', FRONTEND_FILES)

    # ---- 送り方 ----

    def test_each_hour_sends_three_ipa_questions_without_answers(self):
        from .mail import send_slot
        from .models import MailQuestion
        self._sync_groups([
            ({(11, '情報セキュリティ'): 6}, '令和6年度 科目A 問{}'),
            ({(2, 'データ構造'): 6}, 'シラバス Ver.8.0 中分類2 データ構造'),  # 自作は送らない
            ({(101, 'アルゴリズム'): 4}, '令和6年度 科目B 問{}'),  # 科目Bは送らない
        ])
        self._subscribe()
        day = timezone.localdate()

        result = send_slot('h09', today=day)
        self.assertEqual(result['sent'], 1)
        sent = MailQuestion.objects.filter(subscription__learner=self.learner)
        self.assertEqual(sent.count(), 3)
        self.assertEqual({q.question.category.code for q in sent}, {11})
        self.assertEqual(len({q.question_id for q in sent}), 3, '1通の中で同じ問題は出さない')

        message = self.outbox.outbox[0]
        self.assertIn('{}/{}'.format(day.month, day.day), message.subject)
        self.assertIn('9時の問題（3問）', message.subject)
        self.assertEqual(len(self._answer_links(message)), 3)
        self.assertNotIn('情報セキュリティの解説', message.body, '解答と解説はメールに載せない')
        self.assertNotIn('正解 イ', message.body)
        self.assertIn('出典：令和6年度 基本情報技術者試験 科目A 問', message.body)
        self.assertIn('/fe/mail/stop/', message.body)
        self.assertIn('/fe/quiz/', message.body)

    def test_the_same_hour_is_sent_once_and_the_next_hour_again(self):
        from .mail import send_slot
        self._sync({(11, '情報セキュリティ'): 10})
        self._subscribe()
        day = timezone.localdate()
        self.assertEqual(send_slot('h09', today=day)['sent'], 1)
        self.assertEqual(send_slot('h09', today=day), {'sent': 0, 'already': 1, 'failed': 0, 'purged': 0})
        self.assertEqual(send_slot('h10', today=day)['sent'], 1)
        self.assertEqual(len(self.outbox.outbox), 2)
        # 直近に送った問題は避ける（問題が足りていれば、続く2通で問題が重ならない）
        first, second = (set(self._answer_links(m)) for m in self.outbox.outbox)
        from .models import MailQuestion
        by_slot = {
            slot: set(MailQuestion.objects.filter(slot=slot).values_list('question_id', flat=True))
            for slot in ('h09', 'h10')
        }
        self.assertFalse(by_slot['h09'] & by_slot['h10'])

    def test_only_registered_ids_get_mail(self):
        from .mail import send_slot
        self._sync({(11, '情報セキュリティ'): 3})
        self._subscribe(email='')
        self.assertEqual(send_slot('h09')['sent'], 0)

    def test_a_failed_send_is_retried_next_time(self):
        from .mail import send_slot
        from .models import MailQuestion
        self._sync({(11, '情報セキュリティ'): 3})
        self._subscribe()
        with mock.patch('django.core.mail.EmailMessage.send', side_effect=OSError):
            self.assertEqual(send_slot('h09')['failed'], 1)
        self.assertFalse(MailQuestion.objects.exists())
        self.assertEqual(send_slot('h09')['sent'], 1)

    def test_the_mail_is_text_only_and_figures_are_on_the_answer_page(self):
        """メールはテキストだけ（HTML にしない）。図はテキストに載せられないので、解答ページで見てもらう。"""
        from .mail import send_slot
        from .models import MailQuestion
        self._sync({(11, '情報セキュリティ'): 1})
        question = Question.objects.get(template__isnull=True)
        question.figures = [{'src': png_uri(), 'alt': '構成図'}]
        question.save()
        self._subscribe()
        send_slot('h09')
        message = self.outbox.outbox[0]
        self.assertFalse(getattr(message, 'alternatives', []), 'HTML の版は付けない')
        self.assertFalse(message.attachments)
        self.assertNotIn('<', message.body)
        self.assertIn('図が 1 点あります。図は「この問題に答える」のページで見られます', message.body)
        item = MailQuestion.objects.get()
        self.assertContains(self.client.get(reverse('fe:mail_answer', args=[item.code])), png_uri())

    # ---- 解答ページ ----

    def _mailed(self):
        from .mail import send_slot
        from .models import MailQuestion
        self._sync({(11, '情報セキュリティ'): 3})
        self._subscribe()
        send_slot('h09')
        return MailQuestion.objects.order_by('number').first()

    def test_answering_from_the_mail_records_it_for_the_id(self):
        item = self._mailed()
        url = reverse('fe:mail_answer', args=[item.code])
        stranger = self.client_class()  # メールを開いたのは、ID で入っていないブラウザでもよい
        page = stranger.get(url)
        self.assertContains(page, item.question.stem)
        self.assertNotContains(page, '情報セキュリティの解説')

        wrong = (item.question.answer_index + 1) % 4
        page = stranger.post(url, {'choice': wrong})
        self.assertContains(page, '不正解')
        self.assertContains(page, item.question.explanation)
        self.assertContains(page, 'ID「mailer」の成績に記録しました')
        attempt = Attempt.objects.get(learner=self.learner)
        self.assertEqual((attempt.question_id, attempt.is_correct), (item.question_id, False))
        self.assertEqual(
            CategoryProgress.objects.get(learner=self.learner, category=item.question.category).answered, 1,
        )

        # 答え直しても、最初の答えのまま。二重には数えない
        page = stranger.post(url, {'choice': item.question.answer_index})
        self.assertContains(page, '不正解')
        self.assertEqual(Attempt.objects.filter(learner=self.learner).count(), 1)
        self.assertContains(stranger.get(url), '不正解')

    def test_the_answer_page_needs_a_choice(self):
        item = self._mailed()
        page = self.client.post(reverse('fe:mail_answer', args=[item.code]), {'choice': '9'})
        self.assertContains(page, '選択肢を選んでください')
        self.assertFalse(Attempt.objects.exists())

    def test_old_and_unknown_pages_show_the_notice(self):
        from .mail import purge_old
        item = self._mailed()
        self.assertEqual(self.client.get(reverse('fe:mail_answer', args=['nothing12'])).status_code, 404)
        type(item).objects.filter(pk=item.pk).update(date=timezone.localdate() - timezone.timedelta(days=30))
        page = self.client.get(reverse('fe:mail_answer', args=[item.code]))
        self.assertContains(page, '送ってから30日で公開を終えています', status_code=404)
        self.assertContains(page, 'href="http://localhost:8010/fe/" class="x-cta"', status_code=404)
        self.assertEqual(purge_old(), 1)

    # ---- 起動口 ----

    def test_task_endpoint_needs_the_token_and_a_slot(self):
        url = reverse('fe:send_mails')
        self.client.logout()
        with override_settings(FE_MAIL_TOKEN=''):
            self.assertEqual(self.client.post(url).status_code, 503)
        with override_settings(FE_MAIL_TOKEN='secret'):
            self.assertEqual(self.client.post(url, HTTP_X_FE_MAIL_TOKEN='wrong').status_code, 403)
            self.assertEqual(self.client.post(url, HTTP_X_FE_MAIL_TOKEN='secret').status_code, 400)
            for slot in ('none', 'morning', 'h08', 'h19'):
                with self.subTest(slot=slot):
                    response = self.client.post(url, {'slot': slot}, HTTP_X_FE_MAIL_TOKEN='secret')
                    self.assertEqual(response.status_code, 400)
            far = (timezone.localdate() + timezone.timedelta(days=3)).isoformat()
            response = self.client.post(url, {'slot': 'h09', 'date': far}, HTTP_X_FE_MAIL_TOKEN='secret')
            self.assertEqual(response.status_code, 400)
            response = self.client.post(url, {'slot': 'h09'}, HTTP_X_FE_MAIL_TOKEN='secret')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {'sent': 0, 'already': 0, 'failed': 0, 'purged': 0})

    def test_command_sends_a_slot(self):
        self._sync({(11, '情報セキュリティ'): 3})
        self._subscribe()
        out = io.StringIO()
        call_command('send_fe_mails', '--slot', 'h12', stdout=out)
        self.assertIn('1 通を送りました', out.getvalue())
        self.assertIn('12時の問題', self.outbox.outbox[0].subject)


class SlotTests(TestCase):
    """問題メールの時間帯と出典の書き方（fe.slots）。hirahira_room の XPostTests の同じ確かめ。"""

    def test_citation_follows_ipa_form(self):
        from .slots import citation
        self.assertEqual(
            citation('令和7年度 科目A 問2 ／ シラバス Ver.8.0 中分類1 応用数学'),
            '出典：令和7年度 基本情報技術者試験 科目A 問2',
        )
        self.assertEqual(
            citation('サンプル問題 科目A 問12'),
            '出典：基本情報技術者試験 サンプル問題 科目A 問12',
        )
        self.assertEqual(citation('シラバス Ver.8.0 中分類10'), '')

    def test_hourly_slots_from_9_to_18(self):
        import datetime
        from zoneinfo import ZoneInfo
        from .slots import HOURLY_SLOTS, slot_date
        self.assertEqual(HOURLY_SLOTS, ['h09', 'h10', 'h11', 'h12', 'h13',
                                        'h14', 'h15', 'h16', 'h17', 'h18'])
        tokyo = ZoneInfo('Asia/Tokyo')
        at = lambda h: datetime.datetime(2026, 11, 12, h, 5, tzinfo=tokyo)
        # 18時の枠が日付をまたいで1時に届いたら、前の日の18時の枠
        self.assertEqual(slot_date('h18', at(1)), datetime.date(2026, 11, 11))
        self.assertEqual(slot_date('h18', at(18)), datetime.date(2026, 11, 12))
        self.assertEqual(slot_date('h09', at(1)), datetime.date(2026, 11, 12))
        self.assertEqual(slot_date('h09', at(9)), datetime.date(2026, 11, 12))


class PageViewTests(TestCase):
    """学習の画面のページビュー。日付・画面・ID の有無ごとの件数だけを数える。"""

    BROWSER = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1'

    @classmethod
    def setUpTestData(cls):
        seed_masters()
        build_questions()

    def _count(self, page, with_id):
        row = PageViewCount.objects.filter(page=page, with_id=with_id).first()
        return row.count if row else 0

    def test_counts_each_page_by_id(self):
        """画面が出たときに React が api/pageview/ で知らせ、ここで数える。"""
        self.client.get(reverse('fe:index'), HTTP_USER_AGENT=self.BROWSER)
        self.assertFalse(PageViewCount.objects.exists(), '入れ物のページを開いただけでは数えない')
        for page in ('index', 'index', 'quiz'):
            self.view(page)
        self.assertEqual(self._count('index', False), 2)
        self.assertEqual(self._count('quiz', False), 1)

        enter(self.client, make_learner('counted'))
        self.view('mypage')
        self.view('stats')
        self.assertEqual(self._count('mypage', True), 1)
        self.assertEqual(self._count('stats', True), 1)
        # 1回ごとの行は作らない
        self.assertEqual(PageViewCount.objects.count(), 4)
        # 数えない画面の名前は断る
        self.assertEqual(self.view('console').status_code, 400)

    def view(self, page, agent=None):
        return self.client.post(reverse('fe:api_pageview'), {'page': page}, content_type='application/json',
                                HTTP_USER_AGENT=self.BROWSER if agent is None else agent)

    def test_every_page_reports_its_view(self):
        """React の各画面が、pageviews.PAGES の名前で知らせる。"""
        from .pageviews import PAGES
        sources = ''.join(frontend_source(name) for name in FRONTEND_FILES)
        for page in PAGES:
            with self.subTest(page=page):
                self.assertTrue(
                    "usePageView('{}')".format(page) in sources or 'page="{}"'.format(page) in sources
                    or "'{}'".format(page) in sources.split('<DashboardWithView page={', 1)[-1][:60],
                )

    def test_robots_and_redirects_are_not_counted(self):
        for agent in ('', 'Googlebot/2.1 (+http://www.google.com/bot.html)', 'bingbot/2.0',
                      'python-requests/2.32', 'curl/8.7.1'):
            with self.subTest(agent=agent):
                self.view('index', agent)
        self.assertFalse(PageViewCount.objects.exists())

    def test_console_is_not_counted_and_shows_the_table(self):
        self.view('guide')
        login_editor(self.client)
        response = self.client.get(reverse('fe:manage_pageviews'), HTTP_USER_AGENT=self.BROWSER)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['views']['grand_total'], 1)
        self.assertEqual(len(response.context['views']['daily']), 30)
        self.assertContains(response, 'このアプリについて')
        self.assertEqual(PageViewCount.objects.count(), 1)

    def test_console_needs_a_login(self):
        self.assertEqual(self.client.get(reverse('fe:manage_pageviews')).status_code, 302)
        account = get_user_model().objects.create_user(username='plain', password='pass12345')
        self.client.force_login(account)
        self.assertEqual(self.client.get(reverse('fe:manage_pageviews')).status_code, 200)


class StudyPlanTests(TestCase):
    """学習計画（fe.plan）：3巡の組み方、巡ごとの結果、80％ の合格。"""

    @classmethod
    def setUpTestData(cls):
        seed_masters()
        build_questions()

    def setUp(self):
        from datetime import date
        self.today = date(2026, 11, 21)
        self.learner = make_learner('planner')
        enter(self.client, self.learner)

    def make(self, days=30):
        from datetime import timedelta
        from .plan import create_plan
        return create_plan(self.learner, self.today + timedelta(days=days), self.today)

    def answer_on(self, day, category, correct, times=1, topic=None):
        """小分類を指定しなければ、テスト用の問題と同じ小分類（中分類の名前）で解く。"""
        from .plan import record
        for _ in range(times):
            record(self.learner, category, topic or category.name, correct, day)

    def test_rounds_split_days_into_three(self):
        """受験日の前日までを3つの巡に分け、端数は前の巡に足す。"""
        from .plan import round_ranges
        plan = self.make(days=31)
        sizes = [len(days) for _, days in round_ranges(plan)]
        self.assertEqual(sizes, [11, 10, 10])
        self.assertEqual(round_ranges(plan)[0][1][0], self.today)

    def test_first_round_follows_learning_order(self):
        """1巡目は学習モードの順（科目A の番号順 → 科目B）に、日付が進む。"""
        from .models import StudyPlanEntry
        plan = self.make()
        entries = list(StudyPlanEntry.objects.filter(plan=plan, round_no=1).select_related('category'))
        codes = [e.category.code for e in entries]
        self.assertEqual(codes, sorted(codes))
        self.assertEqual(len(codes), Category.objects.count())
        self.assertEqual([e.date for e in entries], sorted(e.date for e in entries))

    def test_later_round_puts_weak_first_and_twice(self):
        """2巡目は1巡目の正答率が低い順で、60％ 未満は2日ぶん。"""
        from datetime import timedelta
        from .models import StudyPlanEntry
        from .plan import ensure_rounds, round_ranges
        plan = self.make()
        good = Category.objects.get(code=1)
        weak = Category.objects.get(code=2)
        # 正解を先に積むと、小分類の問題数（テスト用は4問）に届いた時点で 100％ の合格になるので、間違いを先にする
        self.answer_on(self.today, good, False, times=3)
        self.answer_on(self.today, good, True, times=7)    # 70％
        self.answer_on(self.today, weak, False, times=5)   # 0％
        # 2巡目はその巡が始まるまで組まない
        ensure_rounds(plan, self.today)
        self.assertFalse(StudyPlanEntry.objects.filter(plan=plan, round_no=2).exists())

        second_start = round_ranges(plan)[1][1][0]
        ensure_rounds(plan, second_start)
        entries = list(StudyPlanEntry.objects.filter(plan=plan, round_no=2).select_related('category'))
        codes = [e.category.code for e in entries]
        self.assertEqual(codes[:2], [weak.code, weak.code])
        self.assertEqual(codes.count(good.code), 1)
        # 解いていない中分類（0％ 扱い）は 70％ の中分類より先
        self.assertEqual(codes[-1], good.code)
        self.assertTrue(all(second_start <= e.date < second_start + timedelta(days=10) for e in entries))

    def test_pass_when_every_topic_reaches_80_percent(self):
        """中分類の合格は、その巡でどの小分類も5問以上・80％ 以上になったとき。
        合格した中分類は後の巡に入らない。"""
        from .models import StudyPlanEntry, StudyPlanPass
        from .plan import ensure_rounds, round_ranges
        plan = self.make()
        category = Category.objects.get(code=3)
        topics = {category.id: {'記憶装置': 10, 'プロセッサ': 10}}
        with mock.patch('works.fe.plan.category_topics', return_value=topics):
            self.answer_on(self.today, category, True, times=10, topic='記憶装置')
            # 1つの小分類だけでは、何問解いても合格にならない
            self.assertFalse(StudyPlanPass.objects.exists())
            self.answer_on(self.today, category, True, times=3, topic='プロセッサ')
            self.answer_on(self.today, category, False, times=1, topic='プロセッサ')
            # 4問ではまだ足りない（3/4 = 75％ でもある）
            self.assertFalse(StudyPlanPass.objects.exists())
            self.answer_on(self.today, category, True, times=1, topic='プロセッサ')   # 4/5 = 80％
        passed = StudyPlanPass.objects.get(learner=self.learner)
        self.assertEqual((passed.category, passed.round_no, passed.correct, passed.answered),
                         (category, 1, 14, 15))

        ensure_rounds(plan, round_ranges(plan)[1][1][0])
        self.assertFalse(StudyPlanEntry.objects.filter(plan=plan, round_no=2, category=category).exists())

    def test_topic_pass_rule(self):
        """小分類は5問以上・80％ 以上で合格。問題が5問に満たない小分類は、その数を解けばよい。"""
        from .plan import topic_passed
        self.assertTrue(topic_passed(5, 4, 10))
        self.assertFalse(topic_passed(5, 3, 10))
        self.assertFalse(topic_passed(4, 4, 10))
        self.assertTrue(topic_passed(3, 3, 3))
        self.assertFalse(topic_passed(3, 2, 3))

    def test_plan_shows_topics_in_each_cell(self):
        """表のセルに、小分類ごとの合否と、基準に届いた小分類の数を出す。"""
        from .api import plan_json
        plan = self.make()
        category = Category.objects.get(code=6)
        topics = {category.id: {'A': 10, 'B': 10}}
        self.answer_on(self.today, category, True, times=5, topic='A')
        with mock.patch('works.fe.plan.category_topics', return_value=topics):
            row = {r['code']: r for r in plan_json(plan, self.today)['rows']}[6]
        cell = row['rounds'][0]
        self.assertEqual(cell['topics_passed'], 1)
        self.assertEqual([(t['topic'], t['passed']) for t in cell['topics']], [('A', True), ('B', False)])
        self.assertIsNone(row['passed'])

    def test_rate_below_80_does_not_pass(self):
        from .models import StudyPlanPass
        self.make()
        category = Category.objects.get(code=4)
        self.answer_on(self.today, category, False, times=3)
        self.answer_on(self.today, category, True, times=7)
        self.assertFalse(StudyPlanPass.objects.exists())

    def test_only_study_corner_answers_count_for_the_plan(self):
        """学習計画の結果に数えるのは学習コーナーで解いた分だけ。ヘッダーから開いた
        1問1答（plan を添えない）の分は、分野別の記録には入るが計画には入らない。"""
        from datetime import timedelta
        from .models import StudyPlanResult
        from .plan import create_plan
        from .views import SESSION_PENDING
        today = timezone.localdate()
        create_plan(self.learner, today + timedelta(days=30), today)
        question = Question.objects.filter(subject='A').first()

        def answer_by_api(plan):
            session = self.client.session
            session[SESSION_PENDING] = question.id
            session.save()
            data = {'question_id': question.id, 'choice': question.answer_index}
            if plan:
                data['plan'] = True
            return api_post(self.client, 'api_quiz_answer', data)

        self.assertEqual(answer_by_api(plan=False).status_code, 200)
        self.assertFalse(StudyPlanResult.objects.exists())
        self.assertEqual(CategoryProgress.objects.get(learner=self.learner, category=question.category).answered, 1)

        self.assertEqual(answer_by_api(plan=True).status_code, 200)
        result = StudyPlanResult.objects.get(plan__learner=self.learner)
        self.assertEqual((result.round_no, result.category, result.answered, result.correct),
                         (1, question.category, 1, 1))
        # 画面は、学習コーナーのときだけ plan を添える
        self.assertIn('api.quizAnswer(next.question.id, choice, corner !== null)', frontend_source('QuizPage.tsx'))

    def test_learning_mode_counts_only_whole_category_rounds(self):
        """学習モードは、plan&check の「解説」で始めた回（中分類まるごと）だけ計画に数える。"""
        from datetime import timedelta
        from .models import StudyPlanResult
        from .plan import create_plan
        today = timezone.localdate()
        create_plan(self.learner, today + timedelta(days=30), today)
        category = Category.objects.get(code=9)
        LearningNote.objects.create(category=category, topic=category.name, title='解説', body='本文')
        api_post(self.client, 'api_settings', {'mode': 'category', 'subject': 'A', 'category': 9})

        def solve_one(scope):
            body = {'minutes': 5}
            if scope:
                body['scope'] = scope
            round_id = api_post(self.client, 'api_learn', body).json()['round']['id']
            api_post(self.client, 'api_learn_read', None, round_id)
            api_post(self.client, 'api_learn_quiz', {'choice': 0}, round_id)

        solve_one(scope=None)          # ヘッダーから開いた学習モード（小分類1つ）
        self.assertFalse(StudyPlanResult.objects.exists())
        solve_one(scope='category')    # plan&check の「解説」
        self.assertEqual(StudyPlanResult.objects.get(plan__learner=self.learner).answered, 1)

    def test_remake_keeps_passes(self):
        """組み直すと結果は消えるが、合格は残り、1巡目にも入らない。"""
        from .models import StudyPlanEntry, StudyPlanPass, StudyPlanResult
        self.make()
        category = Category.objects.get(code=5)
        self.answer_on(self.today, category, True, times=10)
        plan = self.make(days=20)
        self.assertTrue(StudyPlanPass.objects.filter(category=category).exists())
        self.assertFalse(StudyPlanResult.objects.exists())
        self.assertFalse(StudyPlanEntry.objects.filter(plan=plan, category=category).exists())

    def test_api(self):
        from datetime import timedelta
        today = timezone.localdate()
        self.assertIsNone(api_get(self.client, 'api_plan').json()['plan'])
        bad = api_post(self.client, 'api_plan', {'exam_date': (today + timedelta(days=2)).isoformat()})
        self.assertEqual(bad.status_code, 400)
        response = api_post(self.client, 'api_plan', {'exam_date': (today + timedelta(days=30)).isoformat()})
        data = response.json()['plan']
        self.assertEqual(data['current_round'], 1)
        self.assertEqual(data['days_left'], 30)
        self.assertTrue(data['today'])
        self.assertEqual(len(data['rows'][0]['rounds']), 3)
        self.assertEqual(response.json()['overall']['total'], 0)

    def test_dashboard_card_opens_plan_and_study_from_each_row(self):
        """plan&check はヘッダーに出さず、ダッシュボードの総合正答率の下の「はじめる」のカードから開く。
        計画の中分類（今日の欄・表の各行）から学習モードと1問1答を開ける。"""
        dashboard_source = frontend_source('Dashboard.tsx')
        self.assertIn('to="/planandcheck/"', dashboard_source)
        self.assertNotIn('PlanCard', dashboard_source)
        stats = dashboard_source[dashboard_source.index('function PersonalStats'):]
        self.assertLess(stats.index('総合正答率'), stats.index('<StartCard />'))
        self.assertLess(stats.index('<StartCard />'), stats.index('苦手分野'))
        # 「はじめる」は ID ありのとき（PersonalStats の中）だけ。ID なしで plan&check を開いてもダッシュボードへ戻す
        self.assertEqual(dashboard_source.count('<StartCard />'), 1)
        self.assertNotIn('/id/', frontend_source('PlanPage.tsx'))
        self.assertIn('<Navigate to="/" replace />', frontend_source('PlanPage.tsx'))
        self.assertNotIn('planandcheck', frontend_source('App.tsx').split('const MENU')[1])
        plan_source = frontend_source('PlanPage.tsx')
        # ボタンは今日の欄だけ。Round ごとの結果の表は表示だけ
        self.assertEqual(plan_source.count('<StudyButtons '), 1)

    def test_study_corner_fixes_the_category_and_has_back_buttons(self):
        """学習コーナー（計画の中分類から開いた 1問1答・学習モード）は、その中分類に固定して
        選択肢を出さず、各画面に戻るボタンを出す。plan&check はダッシュボードへ戻る。"""
        plan = frontend_source('PlanPage.tsx')
        self.assertIn('setCorner({ subject, code, label })', plan)
        # トップ（plan&check）は帯に総合正答率を出し、戻るボタンを置かない
        self.assertNotIn('CornerBack', plan)
        self.assertIn('<Band data={data} />', plan)
        self.assertIn('総合正答率', plan)
        # 学習モードは入口を通さず、すぐラウンドを始めて読む画面へ
        self.assertIn("api.startRound(null, null, 'category')", plan)
        quiz = frontend_source('QuizPage.tsx')
        self.assertIn('const settingsDrawer = !corner && settings', quiz)
        self.assertIn('<CornerBack to="/planandcheck/"', quiz)
        start = frontend_source('LearnStartPage.tsx')
        self.assertNotIn('CornerStart', start)
        self.assertIn('useEffect(clearCorner, [])', start)
        self.assertIn('<OneMoreRound />', frontend_source('LearnResultPage.tsx'))
        # 「解説」で学習モードを始め、読む段階は時間を数えず「問題へ進む」で進む
        self.assertIn(">解説</button>", plan)
        self.assertNotIn(">学習モード</button>", plan)
        read = frontend_source('LearnReadPage.tsx')
        self.assertIn("if (finished || paused || untimed) return", read)
        self.assertIn(">問題へ進む</button>", read)
        self.assertNotIn("解答に進む", read)
        for name in ('LearnReadPage.tsx', 'LearnQuizPage.tsx', 'LearnResultPage.tsx'):
            with self.subTest(page=name):
                self.assertIn('<CornerBackIfAny />', frontend_source(name))
        # メニューとダッシュボードへ移ったら、学習コーナーを抜ける
        self.assertIn('onClick={clearCorner}', frontend_source('App.tsx'))
        self.assertIn('useEffect(clearCorner, [])', frontend_source('Dashboard.tsx'))

    def test_missed_day_is_marked_and_counted_as_zero(self):
        """予定の日を過ぎても1問も解いていない中分類は「未実施」で、正答率は 0％。持ち越さない。"""
        from datetime import timedelta
        from .api import plan_json
        from .models import StudyPlanEntry
        plan = self.make()
        later = self.today + timedelta(days=3)
        data = plan_json(plan, later)
        first_day = {e.category.code for e in StudyPlanEntry.objects.filter(plan=plan, date=self.today)}
        rows = {row['code']: row for row in data['rows']}
        for code in first_day:
            cell = rows[code]['rounds'][0]
            self.assertTrue(cell['missed'])
            self.assertEqual(cell['rate_percent'], 0)
        # 今日の欄には持ち越さない
        self.assertFalse(first_day & {row['code'] for row in data['today']})
        self.assertGreaterEqual(data['missed_count'], len(first_day))

        # 1問でも解けば未実施ではない
        code = next(iter(first_day))
        self.answer_on(self.today, Category.objects.get(code=code), True)
        cell = {row['code']: row for row in plan_json(plan, later)['rows']}[code]['rounds'][0]
        self.assertFalse(cell['missed'])
        self.assertEqual(cell['rate_percent'], 100)

    def test_leave_the_id(self):
        """ID から抜けると、ID の無い記録で使い続ける。ID の記録はそのまま残る。"""
        response = api_post(self.client, 'api_leave')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['code'], None)
        self.assertTrue(response.json()['is_temporary'])
        self.assertEqual(api_get(self.client, 'api_me').json()['code'], None)
        self.assertTrue(Learner.objects.filter(code='planner').exists())
        # ID なしで抜けようとしても何もしない
        self.assertEqual(api_post(self.client, 'api_leave').status_code, 400)
        self.assertIn('ID から抜ける', frontend_source('EnterPage.tsx'))

    @override_settings(DEBUG=True)
    def test_demo_data_shows_each_stage(self):
        """確認用の ID（seed_fe_plan_demo）は、計画の段階ごとに作られ、Round が進むほど合格が増える。"""
        from .api import plan_json
        from .models import StudyPlan
        call_command('seed_fe_plan_demo', stdout=io.StringIO())
        today = timezone.localdate()
        self.assertFalse(StudyPlan.objects.filter(learner__code='demo-0-before').exists())
        stages = {}
        for code in ('demo-1-start', 'demo-2-round1', 'demo-3-round2', 'demo-4-round3'):
            stages[code] = plan_json(StudyPlan.objects.get(learner__code=code), today)
        self.assertEqual([stages[c]['current_round'] for c in stages], [1, 1, 2, 3])
        passed = [stages[c]['passed_count'] for c in stages]
        self.assertEqual(passed, sorted(passed))
        self.assertGreater(stages['demo-2-round1']['missed_count'], 0)
        # 流し直しても増えない
        call_command('seed_fe_plan_demo', stdout=io.StringIO())
        self.assertEqual(Learner.objects.filter(code__startswith='demo-').count(), 5)

    @override_settings(DEBUG=False)
    def test_demo_data_is_only_for_development(self):
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            call_command('seed_fe_plan_demo', stdout=io.StringIO())

    def test_missed_round_stays_after_a_later_pass(self):
        """過ぎた巡で1問も解いていなければ、あとの巡で合格しても、その巡は「未実施」のまま。"""
        from .api import plan_json
        from .plan import ensure_rounds, round_ranges
        plan = self.make()
        category = Category.objects.get(code=1)
        second = round_ranges(plan)[1][1][0]
        ensure_rounds(plan, second)
        self.answer_on(second, category, True, times=5)   # Round 2 で合格（テスト用の小分類は1つ）
        row = {r['code']: r for r in plan_json(plan, second)['rows']}[1]
        self.assertIsNotNone(row['passed'])
        self.assertTrue(row['rounds'][0]['missed'])
        self.assertEqual(row['rounds'][0]['rate_percent'], 0)
        # 行の色は合格の緑を先にする（未実施の赤は、合格していない行だけ）
        self.assertIn("row.passed ? 'fe-row-pass' : row.rounds.some((c) => c.missed) ? 'fe-row-missed'",
                      frontend_source('PlanPage.tsx'))

    def test_answers_without_topic_breakdown_hide_topics(self):
        """小分類ごとに数え始める前に解いた分（中分類の結果だけある）は、小分類を出さない。"""
        from .api import plan_json
        from .models import StudyPlanResult
        plan = self.make()
        category = Category.objects.get(code=2)
        StudyPlanResult.objects.create(plan=plan, round_no=1, category=category, answered=1, correct=1)
        cell = {r['code']: r for r in plan_json(plan, self.today)['rows']}[2]['rounds'][0]
        self.assertEqual((cell['answered'], cell['rate_percent']), (1, 100))
        self.assertEqual(cell['topics'], [])

    def test_api_needs_id(self):
        temporary = Learner.objects.create(code=None)
        enter(self.client, temporary)
        self.assertEqual(api_get(self.client, 'api_plan').status_code, 403)
