"""plan&check（学習計画）の状態の移り変わりを見るための確認用の ID を作る。開発環境だけで使う。

ID で入り直すだけで、計画の段階ごとの画面を見比べられるようにする。どれも
今日から逆算して日付を置くので、いつ流しても同じ段階になる（流し直すと作り直す）。

    ID              段階                    見えるもの
    demo-0-before   計画を立てる前          帯は総合正答率だけ。受験日の欄
    demo-1-start    計画を立てた日          Round 1 の初日。日程だけで結果は無い
    demo-2-round1   Round 1 の途中（9日目）  合格・正答率の色分け・未実施（0％）が混ざる
    demo-3-round2   Round 2 の途中（6日目）  Round 1 の結果で苦手が先頭・2日ぶん。合格は外れる
    demo-4-round3   Round 3 の途中（受験日まで10日）  合格が増え、残りは苦手だけ

どの計画も受験日の60日前に始めたことにする（Round はそれぞれ20日）。予定の日に
解いたかどうか・小分類ごとに何問正解したかは、中分類の番号と Round から決めた型に従う
（下の PATTERNS）。
型は Round が進むほど良くなるようにしてあり、合格が増えていくのが分かる。

解答は、問題を使わずに記録だけを積む（CategoryProgress・DailyProgress と plan.record）。
問題は取り込みで入れ替わるので、確認用のデータを問題に結び付けないため。そのため
解答履歴（履歴の画面）には出ない。

本番では使わない。settings.DEBUG が偽なら何もしない。作り直すときに消すのは
ID が「demo-」で始まる記録だけ。

    python manage.py seed_fe_plan_demo --settings=config.settings_dev
"""

from datetime import datetime, time, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from works.fe import plan
from works.fe.models import CategoryProgress, DailyProgress, Learner, StudyPlanEntry

PREFIX = 'demo-'
# 計画の長さ（受験日の何日前に始めたか）。3で割り切れるので Round は20日ずつ
PLAN_DAYS = 60

# 段階ごとの「今日が計画の何日目か」（0 が開始日）。None は計画を立てていない
STAGES = [
    ('demo-0-before', None),
    ('demo-1-start', 0),
    ('demo-2-round1', 8),
    ('demo-3-round2', 25),
    ('demo-4-round3', 50),
]

# 予定の日の解き方の型。小分類ごとに (解答数, 正解数)。(0, 0) は解かなかった（未実施）。
# 中分類の合格は、どの小分類も5問以上・80％ 以上（plan.topic_passed）
PASS = ((5, 4),)              # どの小分類も 80％ → 中分類が合格
PARTIAL = ((5, 5), (5, 2))    # 小分類を交互に 100％・40％ → 一部の小分類だけ合格（「小分類 3/5」など）
MIDDLE = ((5, 3),)            # どの小分類も 60％
WEAK = ((5, 1),)              # どの小分類も 20％ で苦手
MISSED = ((0, 0),)            # 未実施
# Round ごとの型の並び。中分類の番号で選ぶ。Round が進むほど合格が多く、未実施が少ない
PATTERNS = {
    1: [PASS, PARTIAL, WEAK, MISSED, MIDDLE],
    2: [PASS, PASS, PARTIAL, WEAK, MISSED],
    3: [PASS, PASS, PASS, PARTIAL, WEAK],
}


def pattern(round_no, category):
    kinds = PATTERNS[round_no]
    return kinds[(category.code + round_no) % len(kinds)]


def answer(learner, category, topic, is_correct, day):
    """1問ぶんを記録する。stats.record_progress と同じ積み方で、日付だけを指定する。"""
    progress, _ = CategoryProgress.objects.get_or_create(
        learner=learner, category=category, subject=category.subject,
    )
    CategoryProgress.objects.filter(pk=progress.pk).update(
        answered=F('answered') + 1,
        correct=F('correct') + (1 if is_correct else 0),
        last_answered_at=timezone.make_aware(datetime.combine(day, time(20, 0))),
    )
    daily, _ = DailyProgress.objects.get_or_create(learner=learner, date=day)
    DailyProgress.objects.filter(pk=daily.pk).update(
        answered=F('answered') + 1,
        correct=F('correct') + (1 if is_correct else 0),
    )
    plan.record(learner, category, topic, is_correct, day)


def simulate(learner, today, elapsed):
    """今日が計画の elapsed 日目になるように計画を立て、昨日までの予定を型どおりに解く。

    2巡目以降の日程は、その巡の初日に plan.ensure_rounds で組む（画面を開いたのと同じ）。
    そのため前の巡の結果で並びが決まり、合格した中分類は入らない。
    """
    start = today - timedelta(days=elapsed)
    # 小分類は、いま出題できる問題の topic（plan.category_topics）。無い中分類は小分類なしで解く
    topics = {category_id: sorted(names) for category_id, names in plan.category_topics().items()}
    study_plan = plan.create_plan(learner, start + timedelta(days=PLAN_DAYS), start)
    for round_no, days in plan.round_ranges(study_plan):
        if not days or days[0] > today:
            break
        plan.ensure_rounds(study_plan, days[0])
        # 中分類ごとに、その巡の最初の予定の日に型どおり解く。今日の分はまだ解いていない
        first_dates = {}
        for entry in StudyPlanEntry.objects.filter(
                plan=study_plan, round_no=round_no).select_related('category'):
            first_dates.setdefault(entry.category, entry.date)
        for category, day in first_dates.items():
            if day >= today:
                continue
            kinds = pattern(round_no, category)
            for number, topic in enumerate(topics.get(category.id) or ['']):
                answered, correct = kinds[number % len(kinds)]
                if not topic:
                    # 小分類が分からない中分類は、中分類全体の基準（10問）に合わせて倍解く
                    answered, correct = answered * 2, correct * 2
                for index in range(answered):
                    answer(learner, category, topic, index < correct, day)


class Command(BaseCommand):
    help = 'plan&check の状態を見比べるための確認用の ID（demo-…）を作り直す。開発環境だけ。'

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError('確認用のデータは開発環境（DEBUG）でだけ作ります。')

        today = timezone.localdate()
        with transaction.atomic():
            removed, _ = Learner.objects.filter(code__startswith=PREFIX).delete()
            for code, elapsed in STAGES:
                learner = Learner.objects.create(code=code)
                if elapsed is not None:
                    simulate(learner, today, elapsed)

        if removed:
            self.stdout.write('前の確認用データを消しました。')
        self.stdout.write('確認用の ID を作りました。/fe/id/ でこの ID を入れると、その段階の画面になります。')
        for code, elapsed in STAGES:
            stage = '計画を立てる前' if elapsed is None else '計画の {} 日目'.format(elapsed + 1)
            self.stdout.write('  {}  {}'.format(code, stage))
