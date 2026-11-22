"""学習計画（StudyPlan）の割り振りと、巡ごとの結果の記録。

計画の立て方
    0. 準備：受験日を決めると、今日から受験日の前日までを3つの巡に等分し、
       1巡目の日程を中分類で組む。
    1. 1巡目：学習モードの順番どおり（中分類の番号順。科目A の 1〜23 → 科目B の 101〜105）。
       学習対象の中分類を、1巡目の日数に均して並べる。
    2. 2巡目以降：苦手を先に。前の巡の正答率が低い順に並べ、正答率が WEAK_RATE 未満
       （前の巡で解いていないものも含む）の中分類は2日ぶん取る。前の巡の結果で並びが
       決まるので、その巡が始まってから組む（ensure_rounds）。

結果の記録
    1. 解答するたびに、その日が入る巡の中分類と小分類の解答数・正解数を足す（record）。
       数えるのは学習コーナー（plan&check から開いた 1問1答と、「解説」で始めた学習モード）で
       解いた分だけ。ヘッダーから開いた 1問1答・学習モードと問題メールの分は数えない
       （stats.record_progress の for_plan）。
    2. 中分類の合格（StudyPlanPass）は、その巡の中で、中分類のどの小分類も
       PASS_MIN_TOPIC_ANSWERS 問以上（小分類の問題がそれより少なければその数）解き、
       正答率が PASS_PERCENT％ 以上になったとき（topic_status）。合格した中分類は、
       それより後の巡の日程に入れない。小分類は、その中分類にいま出題できる問題の topic。
       小分類が無い中分類（問題が無いなど）は、中分類全体で PASS_MIN_ANSWERS 問以上・
       PASS_PERCENT％ 以上で合格にする。
    3. 合格は計画の画面に出す（api.plan_json）。

計画を作り直す（受験日を変える）と、日程と巡ごとの結果は消して今日から組み直す。
合格だけは残し、新しい計画でも学習対象から外したままにする。
"""

from django.db import transaction
from django.db.models import Count, F

from .models import (Category, LearningNote, Question, StudyPlan, StudyPlanEntry,
                     StudyPlanPass, StudyPlanResult, StudyPlanTopicResult)

ROUNDS = StudyPlan.ROUNDS
PASS_PERCENT = StudyPlanPass.PASS_PERCENT
PASS_MIN_ANSWERS = StudyPlanPass.PASS_MIN_ANSWERS
PASS_MIN_TOPIC_ANSWERS = StudyPlanPass.PASS_MIN_TOPIC_ANSWERS

# 2巡目以降で2日ぶん取る、前の巡の正答率の上限。苦手判定（stats.WEAK_THRESHOLD）と同じ 60％
WEAK_RATE = 0.6
# 2巡目以降で苦手な中分類に取る日数
WEAK_SLOTS = 2

# 受験日は、3巡を1日ずつでも組めるよう今日から3日以上先、長くても1年先まで
MIN_DAYS = ROUNDS
MAX_DAYS = 366


class PlanError(ValueError):
    """受験日が計画を組めない日のとき。メッセージはそのまま画面に出す。"""


def _days(plan):
    """計画の日（開始日から受験日の前日まで）。"""
    from datetime import timedelta
    count = (plan.exam_date - plan.start_date).days
    return [plan.start_date + timedelta(days=i) for i in range(count)]


def round_ranges(plan):
    """巡ごとの日の並び。日数を3つに分け、割り切れない分は前の巡に1日ずつ足す。

    返り値は [(巡, [日, ...]), ...]。
    """
    days = _days(plan)
    base, extra = divmod(len(days), ROUNDS)
    ranges, start = [], 0
    for number in range(1, ROUNDS + 1):
        size = base + (1 if number <= extra else 0)
        ranges.append((number, days[start:start + size]))
        start += size
    return ranges


def round_of(plan, day):
    """その日が入る巡。計画の外（開始前・受験日から後）なら None。"""
    for number, days in round_ranges(plan):
        if days and days[0] <= day <= days[-1]:
            return number
    return None


def study_categories():
    """学習対象の中分類を、学習モードの順（科目A → 科目B、それぞれ番号順）で返す。

    技術解説か問題のどちらかがある中分類に限る。どちらも無い中分類は、日程に入れても
    取り組みようがない。どの中分類にも無いとき（取り込み前）は全中分類を並べる。
    """
    with_material = set(LearningNote.objects.values_list('category_id', flat=True))
    with_material |= set(Question.objects.active().values_list('category_id', flat=True))
    categories = sorted(
        Category.objects.all(),
        key=lambda c: (c.subject != Category.SUBJECT_A, c.code),
    )
    usable = [c for c in categories if c.id in with_material]
    return usable or categories


def _passed_ids(learner):
    return set(StudyPlanPass.objects.filter(learner=learner).values_list('category_id', flat=True))


def _spread(plan, number, slots, days):
    """中分類の並び（slots）を巡の日に均して置く。日より中分類が多ければ1日に複数置く。"""
    if not days:
        return
    StudyPlanEntry.objects.bulk_create([
        StudyPlanEntry(
            plan=plan, round_no=number, category=category,
            date=days[index * len(days) // len(slots)],
        )
        for index, category in enumerate(slots)
    ])


@transaction.atomic
def create_plan(learner, exam_date, today):
    """受験日から計画を組む。前の計画があれば作り直す（合格は残す）。"""
    days = (exam_date - today).days
    if days < MIN_DAYS:
        raise PlanError('受験日は{}日後以降にしてください。'.format(MIN_DAYS))
    if days > MAX_DAYS:
        raise PlanError('受験日は1年以内にしてください。')

    StudyPlan.objects.filter(learner=learner).delete()
    plan = StudyPlan.objects.create(learner=learner, exam_date=exam_date, start_date=today)

    passed = _passed_ids(learner)
    slots = [c for c in study_categories() if c.id not in passed]
    _spread(plan, 1, slots, round_ranges(plan)[0][1])
    return plan


def _rates(plan, number):
    """その巡の中分類ごとの正答率（解いていなければ入らない）。"""
    return {
        row.category_id: row.correct / row.answered
        for row in StudyPlanResult.objects.filter(plan=plan, round_no=number, answered__gt=0)
    }


def ensure_rounds(plan, today):
    """始まった巡のうち、まだ日程の無いもの（2巡目以降）を前の巡の結果で組む。

    前の巡で解いていない中分類は、正答率 0 と同じに扱って先頭に寄せる。
    """
    built = set(plan.entries.values_list('round_no', flat=True).distinct())
    for number, days in round_ranges(plan):
        if number == 1 or number in built or not days or days[0] > today:
            continue
        rates = _rates(plan, number - 1)
        passed = _passed_ids(plan.learner)
        categories = [c for c in study_categories() if c.id not in passed]
        # 正答率の低い順。同じなら学習モードの順のまま（sorted は安定）
        categories.sort(key=lambda c: rates.get(c.id, 0.0))
        slots = []
        for category in categories:
            weak = rates.get(category.id, 0.0) < WEAK_RATE
            slots.extend([category] * (WEAK_SLOTS if weak else 1))
        _spread(plan, number, slots, days)


def category_topics(categories=None):
    """中分類ごとの小分類と、その小分類の問題の数。{中分類の id: {小分類: 問題数}}。

    いま出題できる問題の topic から数える。topic が空の問題は小分類に数えない。
    """
    queryset = Question.objects.active().exclude(topic='')
    if categories is not None:
        queryset = queryset.filter(category__in=categories)
    topics = {}
    for row in queryset.values('category', 'topic').annotate(n=Count('id')):
        topics.setdefault(row['category'], {})[row['topic']] = row['n']
    return topics


def topic_passed(answered, correct, available):
    """小分類1つが合格の基準に届いたか。問題が少ない小分類は、その数を解けばよい。"""
    need = min(PASS_MIN_TOPIC_ANSWERS, available) if available else PASS_MIN_TOPIC_ANSWERS
    return answered >= need and correct * 100 >= PASS_PERCENT * answered


def topic_status(topics, results):
    """小分類ごとの合否。topics は {小分類: 問題数}、results は {小分類: (解答数, 正解数)}。

    返り値は小分類の名前順の [{topic, answered, correct, rate_percent, passed}]。
    """
    rows = []
    for topic in sorted(topics):
        answered, correct = results.get(topic, (0, 0))
        rows.append({
            'topic': topic,
            'answered': answered,
            'correct': correct,
            'rate_percent': round(correct / answered * 100) if answered else None,
            'passed': topic_passed(answered, correct, topics[topic]),
        })
    return rows


def _category_passed(plan, number, category, result):
    """その巡で中分類が合格の基準に届いたか。小分類が分からなければ中分類全体で見る。"""
    topics = category_topics([category]).get(category.id, {})
    if not topics:
        return (result.answered >= PASS_MIN_ANSWERS
                and result.correct * 100 >= PASS_PERCENT * result.answered)
    results = {
        row.topic: (row.answered, row.correct)
        for row in StudyPlanTopicResult.objects.filter(plan=plan, round_no=number, category=category)
    }
    return all(row['passed'] for row in topic_status(topics, results))


def record(learner, category, topic, is_correct, day):
    """1問の解答を、その日が入る巡の中分類・小分類の結果に足す。合格に届いたら合格にする。"""
    plan = StudyPlan.objects.filter(learner=learner).first()
    if plan is None:
        return
    number = round_of(plan, day)
    if number is None:
        return

    increment = {
        'answered': F('answered') + 1,
        'correct': F('correct') + (1 if is_correct else 0),
    }
    result, _ = StudyPlanResult.objects.get_or_create(
        plan=plan, round_no=number, category=category,
    )
    StudyPlanResult.objects.filter(pk=result.pk).update(**increment)
    result.refresh_from_db()
    topic_result, _ = StudyPlanTopicResult.objects.get_or_create(
        plan=plan, round_no=number, category=category, topic=topic or '',
    )
    StudyPlanTopicResult.objects.filter(pk=topic_result.pk).update(**increment)

    if StudyPlanPass.objects.filter(learner=learner, category=category).exists():
        return
    if _category_passed(plan, number, category, result):
        StudyPlanPass.objects.create(
            learner=learner, category=category, round_no=number,
            answered=result.answered, correct=result.correct, passed_on=day,
        )
