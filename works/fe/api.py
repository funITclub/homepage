"""基本情報（fe）の API。React の画面（frontend/fe）が呼ぶ。作りは bk_houmu3・countdown の API と同じ。

    GET    /fe/api/me/                    いま入っている記録（ID の有無）
    POST   /fe/api/enter/                 ID で入る・ID を作る
    POST   /fe/api/leave/                 ID から抜ける（ID の無い記録で使い続ける）
    POST   /fe/api/pageview/              画面を出したことを数える（fe.pageviews）
    GET    /fe/api/dashboard/             ダッシュボード（みんなの集計・合格の申告・収録問題数）
    GET    /fe/api/settings/              出題設定（モード・科目・分野）と、選べるものの一覧
    POST   /fe/api/settings/              出題設定を変える
    GET    /fe/api/quiz/next/             1問1答で次に出す問題
    POST   /fe/api/quiz/answer/           解答して、正誤と解説を受け取る
    GET    /fe/api/stats/                 分野別の正答率（?subject=A|B で科目を絞る）と直近14日の解答数
    GET    /fe/api/history/               解答履歴（正誤・分野で絞り込み、20件ずつ）
    GET    /fe/api/guide/                 このアプリについて（試験名・収録問題数）
    POST   /fe/api/pass/                  本番合格の申告（ID があるときだけ）
    DELETE /fe/api/pass/                  申告の取り消し
    GET    /fe/api/plan/                  学習計画（巡ごとの日程・結果・合格）
    POST   /fe/api/plan/                  受験日から学習計画を組む（作り直す）
    DELETE /fe/api/plan/                  学習計画をやめる
    GET    /fe/api/mail/                  問題メールの登録の様子
    POST   /fe/api/mail/                  問題メールの登録（確認のメールを送る）
    GET    /fe/api/learn/                 学習モードの入口（学習対象の一覧・読む時間・これまでのラウンド）
    POST   /fe/api/learn/                 ラウンドを始める（scope=category で中分類まるごと）
    GET    /fe/api/learn/<pk>/read/       読む段階（解説・残り時間）
    POST   /fe/api/learn/<pk>/read/       読み終えて解く段階へ進む
    POST   /fe/api/learn/<pk>/timer/      読む時間を止める・動かす（読み上げの再生中は止める）
    GET    /fe/api/learn/<pk>/quiz/       解く段階のいまの1問
    POST   /fe/api/learn/<pk>/quiz/       その1問に解答する
    POST   /fe/api/learn/<pk>/next/       次の1問へ進む
    POST   /fe/api/learn/<pk>/abandon/    途中のラウンドをやめる
    GET    /fe/api/learn/<pk>/result/     ラウンドの結果

編集画面のログインは求めない（学習の画面と同じ）。成績は、セッションが覚えている
fe の中の記録（Learner）に持つ（views.current_learner）。記録が無い（始めていない・ブラウザを
閉じて抜けた）ときは 401 を返し、React は入口（/fe/）を開き直す。入口が記録を作る。

ログインを求めないので、DRF の SessionAuthentication は使えない（あれはログインしている
ときにしか CSRF を確かめない）。下の CsrfOnly で、ログインの有無にかかわらず書き込みの
CSRF トークンを確かめる。React は入れ物のページ（views.AppView）が配る csrftoken の
Cookie を X-CSRFToken ヘッダーに載せて送る。

1問1答の「いま出している問題」と「直前に出した問題」は、これまでどおりセッションに持つ。
出した問題にだけ解答を受け付ける（二重送信やブラウザの戻る操作で二度採点しないため。409）。
解答の前に正解と解説は渡さない（画面の中を覗けば答えが分かってしまうため）。
"""

from datetime import datetime

from django.contrib.auth.decorators import login_not_required
from django.core.exceptions import ValidationError
from django.core.paginator import EmptyPage, Paginator
from django.core.validators import validate_email
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from rest_framework import status
from rest_framework.authentication import BaseAuthentication, CSRFCheck
from rest_framework.exceptions import NotAuthenticated, PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import mail, pageviews, plan, speech
from .exam import EXAM
from .forms import LearnerForm, PassReportForm
from .learning import current_item, focus_category, grade, note_menu, start_round
from .models import (Attempt, Category, CategoryProgress, LearningNote, LearningRound,
                     MailSubscription, PassReport, Question, QuestionTemplate, StudyPlan,
                     StudyPlanPass, StudySession)
from .selection import pick_question
from .stats import (categories_for, category_options, category_stats, daily_counts,
                    field_stats, overall_stats, record_progress, site_summary,
                    weak_categories)
from .views import (RECENT_LIMIT, SESSION_PENDING, SESSION_RECENT, SESSION_SHOWN_AT,
                    _enter, _get_study_session, current_learner, remember_entry, start_temporary,
                    touch)

# 解答してから記録する所要時間の上限。途中で離席したときに極端な値が入らないようにする
ELAPSED_LIMIT_MS = 30 * 60 * 1000
# 解答履歴の1ページの件数
HISTORY_PAGE_SIZE = 20


class CsrfOnly(BaseAuthentication):
    """ログインは見ず、書き込み（POST・DELETE など）の CSRF トークンだけを確かめる。

    DRF の APIView は Django の CSRF の中間処理を外す（csrf_exempt）。確かめるのは
    SessionAuthentication だけで、それもログインしているときに限る。fe の画面は
    ログインせずに使うので、ここで誰に対しても確かめる。食い違えば 403。
    """

    def authenticate(self, request):
        def dummy_get_response(request):  # pragma: no cover - CSRFCheck の作りに合わせるだけ
            return None

        check = CSRFCheck(dummy_get_response)
        check.process_request(request)
        reason = check.process_view(request, None, (), {})
        if reason:
            raise PermissionDenied('CSRF の確認に失敗しました。画面を開き直してください。')
        return None

    def authenticate_header(self, request):
        # これが値を返す認証方式でないと、DRF は 401（NotAuthenticated）を 403 に変えてしまう。
        # 記録が無いときの 401 と、CSRF の食い違いの 403 を React が見分けられるようにする
        # （countdown.api.SessionAuth と同じ）
        return 'Session'


@method_decorator(login_not_required, name='dispatch')
class FeAPI(APIView):
    """fe の API の土台。記録が要らない API（ID で入る・このアプリについて）にも使う。"""

    authentication_classes = [CsrfOnly]
    permission_classes = [AllowAny]

    def finalize_response(self, request, response, *args, **kwargs):
        # ID で入ったら、ID の Cookie を置く（views.remember_entry）
        response = super().finalize_response(request, response, *args, **kwargs)
        return remember_entry(request._request, response)


class LearnerAPI(FeAPI):
    """記録が要る API。self.learner にいまの記録を置く。始めていなければ 401。"""

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.learner = current_learner(request._request)
        if self.learner is None:
            raise NotAuthenticated('記録がありません。入口から開き直してください。')
        # ページビューの ID の有無に使う（fe.pageviews.record）
        request._request.fe_learner = self.learner
        touch(self.learner)
        self.check_learner(self.learner)

    def check_learner(self, learner):
        """この記録で使えるか。使えなければ例外を投げる。"""


class RegisteredAPI(LearnerAPI):
    """ID が要る API（合格の申告・問題メール）。履歴を残さない利用では 403。"""

    message = 'ID の登録が必要です。'

    def check_learner(self, learner):
        if learner.is_temporary:
            raise PermissionDenied(self.message)


# ---------------------------------------------------------------- 形をそろえる

LABELS = 'アイウエオカキクケコ'


def category_json(category):
    return {
        'code': category.code,
        'label': category.label,
        'name': category.name,
        'field': category.get_field_display(),
        'subject': category.subject,
        'exam_weight': category.exam_weight,
    }


def question_json(question):
    """問題を画面に出す分。正解と解説は入れない（解答してから answer_json で渡す）。"""
    category = question.category
    return {
        'id': question.id,
        'subject': question.subject,
        'subject_label': question.get_subject_display(),
        'field': category.get_field_display(),
        'category_code': category.code,
        'category_name': category.name,
        'category_label': category.label,
        'topic': question.topic,
        'stem': question.stem,
        'figures': question.figures or [],
        'choices': [
            {'label': label, 'text': text, 'figure': figure}
            for _index, label, text, figure in question.choice_rows()
        ],
        'origin_label': question.origin_label,
        'source': question.source_text if question.source else '',
    }


def answer_json(question):
    """解答のあとに見せる分（正解と解説）。"""
    return {
        'answer_index': question.answer_index,
        'answer_label': question.answer_label,
        'answer_text': question.answer_text,
        'answer_figure': question.answer_figure,
        'explanation': question.explanation,
    }


def progress_json(learner, category):
    """その中分類のいまの成績。1問1答の画面の下に出す。"""
    totals = CategoryProgress.objects.filter(learner=learner, category=category).aggregate(
        total=Sum('answered'), correct=Sum('correct')
    )
    total = totals['total'] or 0
    correct = totals['correct'] or 0
    return {
        'name': category.name,
        'total': total,
        'correct': correct,
        'rate_percent': round(correct / total * 100) if total else None,
    }


def me_json(learner):
    if learner is None:
        return {'entered': False, 'code': None, 'is_temporary': True}
    return {'entered': True, 'code': learner.code, 'is_temporary': learner.is_temporary}


def settings_json(learner):
    """出題設定と、画面の選択肢。

    分野の件数と選べるかどうかはモードで変わるので、全モードぶん（by_mode）を渡し、
    モードと科目を切り替えたときに画面の中で出し分ける（stats.category_options）。
    """
    session = _get_study_session(learner)
    return {
        'mode': session.mode,
        'mode_label': session.get_mode_display(),
        'subject': session.subject,
        'category': session.category.code if session.category else None,
        'modes': [{'value': value, 'label': label} for value, label in StudySession.MODE_CHOICES],
        'subjects': [
            {'value': Question.SUBJECT_A, 'label': '科目A（知識）'},
            {'value': Question.SUBJECT_B, 'label': '科目B（技能）'},
        ],
        'categories': [
            {
                'code': option['code'],
                'label': option['label'],
                'subject': option['subject'],
                'question_count': option['question_count'],
                'by_mode': option['by_mode'],
            }
            for option in category_options(learner, session.mode)
        ],
    }


def field_json(fields):
    return [
        {'label': f['field_label'], 'rate_percent': f['rate_percent'],
         'correct': f['correct'], 'total': f['total'], 'weight': f['weight']}
        for f in fields
    ]


def question_total():
    return Question.objects.active().filter(template__isnull=True).count()


# ---------------------------------------------------------------- ID・ページビュー

class MeAPI(FeAPI):
    """いま入っている記録。見出し（ID の表示）と、ダッシュボードの場所を決めるのに使う。"""

    def get(self, request):
        learner = current_learner(request._request)
        if learner is not None:
            touch(learner)
        return Response(me_json(learner))


class EnterAPI(FeAPI):
    """ID で入る（action=enter）・ID を作る（action=create）。

    打ち間違えた ID で新しく作ってしまわないよう、入ると作るを分ける（forms.LearnerForm）。
    履歴を残さずに使っていた分は引き継がない。放っておけば掃除で消える。
    """

    def post(self, request):
        creating = request.data.get('action') == 'create'
        form = LearnerForm({'code': request.data.get('code', '')}, creating=creating)
        if not form.is_valid():
            errors = form.errors.get('code') or ['ID を入力してください。']
            # not_found：形は正しいが、まだ無い ID で入ろうとした（ポップアップが作成の確認を出す）
            not_found = any(e.code == 'not_found' for e in form.errors.as_data().get('code', []))
            return Response({'detail': errors[0], 'errors': list(errors), 'not_found': not_found},
                            status=status.HTTP_400_BAD_REQUEST)
        if creating:
            from .models import Learner
            learner = Learner.objects.create(code=form.cleaned_data['code'])
            message = 'ID「{}」を作りました。これからの解答はこの ID に残ります。'.format(learner.code)
        else:
            learner = form.learner
            message = 'ID「{}」で入りました。'.format(learner.code)
        # keep：ダッシュボードのポップアップで「次回から表示しない」に印を付けて入った（views._enter）
        _enter(request._request, learner, keep=bool(request.data.get('keep')))
        return Response({**me_json(learner), 'message': message})


class LeaveAPI(FeAPI):
    """ID から抜ける。ID の無い記録（履歴を残さない利用）を新しく作って入り直す。

    ID の成績はその ID に残る。もう一度 ID を入れれば続きから使える。
    ブラウザを閉じたときと同じく、ID の無い記録で画面を使い続けられるようにする
    （記録が無いと API が 401 を返し、入口を開き直すことになるため）。
    """

    def post(self, request):
        learner = current_learner(request._request)
        if learner is None or learner.is_temporary:
            return Response({'detail': 'ID で入っていません。'}, status=status.HTTP_400_BAD_REQUEST)
        code = learner.code
        temporary = start_temporary(request._request)
        return Response({**me_json(temporary), 'message': 'ID「{}」から抜けました。'.format(code)})


class PageViewAPI(FeAPI):
    """画面を出したことを1件数える。画面の切りかえは React の中で行うので、画面から知らせる。

    数えるのは学習の画面だけ（pageviews.PAGES）。ID の有無で分けて数えるので、入って
    いれば記録を見る。巡回ロボットは pageviews.record が除く。
    """

    def post(self, request):
        learner = current_learner(request._request)
        if learner is not None:
            request._request.fe_learner = learner
        page = request.data.get('page')
        if page not in pageviews.PAGES:
            return Response({'detail': 'その画面は数えません。'}, status=status.HTTP_400_BAD_REQUEST)
        pageviews.record(request._request, page)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- ダッシュボード

class DashboardAPI(LearnerAPI):
    """ダッシュボード。ID があれば自分の成績（personal）、みんなの集計と合格の申告、収録問題数。

    自分の成績は、ID があるときだけ返す（履歴を残さない利用では null）。
    """

    def get(self, request):
        learner = self.learner
        summary = site_summary()
        report = PassReport.objects.filter(learner=learner).first()
        return Response({
            'question_total': question_total(),
            'summary': {
                'total': summary['total'],
                'correct': summary['correct'],
                'rate_percent': summary['rate_percent'],
                'learners': summary['learners'],
                'passers': summary['passers'],
            },
            # 合格の申告。履歴を残さない利用では申告できない（消える記録なので合格者数に数えない）
            'my_report': (
                {'passed_on': report.passed_on.isoformat()} if report else None
            ),
            'today': timezone.localdate().isoformat(),
            # 自分の成績。ID があるときだけ出す（履歴を残さない利用では出さない）
            'personal': None if learner.is_temporary else personal_json(learner),
        })


def personal_json(learner):
    """ダッシュボードに出す自分の成績。総合・直近・学習日数、苦手分野、未着手、分野別、直近14日。"""
    rows = category_stats(learner)
    overall = overall_stats(learner)
    return {
        'overall': {
            'rate_percent': overall['rate_percent'],
            'correct': overall['correct'],
            'total': overall['total'],
            'recent_days': overall['recent_days'],
            'recent_rate_percent': overall['recent_rate_percent'],
            'pass_line_percent': overall['pass_line_percent'],
            'study_days': overall['study_days'],
        },
        'template_total': QuestionTemplate.objects.filter(is_active=True).count(),
        'weak': [
            {**category_json(r['category']), 'rate_percent': r['rate_percent'],
             'correct': r['correct'], 'total': r['total']}
            for r in weak_categories(rows, limit=5)
        ],
        'untouched': [
            category_json(r['category']) for r in rows if r['is_untouched'] and r['question_count']
        ],
        'fields': field_json(field_stats(rows)),
        'daily': [
            {'date': d['date'].isoformat(), 'total': d['total'], 'correct': d['correct']}
            for d in daily_counts(learner, days=14)
        ],
    }



class GuideAPI(FeAPI):
    """このアプリについて。始めていなくても読める。"""

    def get(self, request):
        learner = current_learner(request._request)
        return Response({
            'exam_name': EXAM['name'],
            'question_total': question_total(),
            'template_total': QuestionTemplate.objects.filter(is_active=True).count(),
            'me': me_json(learner),
        })


# ---------------------------------------------------------------- 出題設定

class SettingsAPI(LearnerAPI):
    """出題モード・科目・分野。1問1答・学習モード（おまかせの範囲）・ダッシュボードで共有する。"""

    def get(self, request):
        return Response(settings_json(self.learner))

    def post(self, request):
        session = _get_study_session(self.learner)
        mode = request.data.get('mode')
        subject = request.data.get('subject')
        category_code = request.data.get('category')

        valid_modes = {value for value, _ in StudySession.MODE_CHOICES}
        if mode not in valid_modes:
            return Response({'detail': '出題モードを選んでください。'}, status=status.HTTP_400_BAD_REQUEST)
        if subject not in (Question.SUBJECT_A, Question.SUBJECT_B):
            return Response({'detail': '科目を選んでください。'}, status=status.HTTP_400_BAD_REQUEST)

        # 分野はどのモードでも選べる。選んだら、そのモードの出し方のまま
        # その分野の中だけから出す。選ばなければ全分野から出す。
        category = None
        if category_code not in (None, ''):
            category = Category.objects.filter(code=category_code, subject=subject).first()
            if category is None:
                return Response({'detail': 'その分野は選んだ科目にありません。'},
                                status=status.HTTP_400_BAD_REQUEST)
        if mode == StudySession.MODE_CATEGORY and category is None:
            return Response({'detail': '分野を選んでください。'}, status=status.HTTP_400_BAD_REQUEST)

        session.mode = mode
        session.subject = subject
        session.category = category
        session.save()
        # 設定を変えたら、直前に出した問題を避ける履歴はいったん空にする
        request.session[SESSION_RECENT] = []
        request.session.pop(SESSION_PENDING, None)
        request.session.pop(SESSION_SHOWN_AT, None)
        return Response(settings_json(self.learner))


# ---------------------------------------------------------------- 1問1答

class QuizNextAPI(LearnerAPI):
    """次に出す問題。出したことをセッションに覚え、その問題にだけ解答を受け付ける。"""

    def get(self, request):
        study_session = _get_study_session(self.learner)
        recent = request.session.get(SESSION_RECENT, [])
        question, reason = pick_question(self.learner, study_session, exclude_ids=recent)
        if question is None:
            request.session.pop(SESSION_PENDING, None)
            return Response({'question': None})

        request.session[SESSION_PENDING] = question.id
        request.session[SESSION_SHOWN_AT] = timezone.now().isoformat()
        return Response({
            'question': question_json(question),
            'reason': reason,
            'progress': progress_json(self.learner, question.category),
        })


class QuizAnswerAPI(LearnerAPI):
    """解答。いま出している問題でなければ受け付けない（409）。"""

    def post(self, request):
        pending_id = request.session.get(SESSION_PENDING)
        question_id = request.data.get('question_id')
        if not question_id or str(pending_id) != str(question_id):
            # 二重送信やブラウザの戻る操作。採点しない
            return Response({'detail': 'その問題は既に解答済みです。次の問題を表示します。'},
                            status=status.HTTP_409_CONFLICT)

        question = Question.objects.filter(id=pending_id).select_related('category').first()
        if question is None:
            request.session.pop(SESSION_PENDING, None)
            return Response({'detail': 'その問題はもうありません。次の問題を表示します。'},
                            status=status.HTTP_409_CONFLICT)

        selected = request.data.get('choice')
        if not isinstance(selected, int) or isinstance(selected, bool) \
                or not 0 <= selected < len(question.choices):
            return Response({'detail': '選択肢を選んでください。'}, status=status.HTTP_400_BAD_REQUEST)

        is_correct = selected == question.answer_index
        elapsed_ms = None
        shown_at = request.session.get(SESSION_SHOWN_AT)
        if shown_at:
            try:
                delta = timezone.now() - datetime.fromisoformat(shown_at)
                elapsed_ms = min(int(delta.total_seconds() * 1000), ELAPSED_LIMIT_MS)
            except ValueError:
                elapsed_ms = None

        Attempt.objects.create(
            learner=self.learner, question=question, category=question.category,
            selected_index=selected, is_correct=is_correct, elapsed_ms=elapsed_ms,
        )
        # 問題が入れ替わっても残る記録。分野別の正答率と苦手判定はこちらを見る。
        # plan&check から開いた 1問1答（画面が plan=true を添える）だけ、学習計画の結果にも足す
        record_progress(self.learner, question, is_correct, for_plan=request.data.get('plan') is True)

        # 採点済みなので保留を落とし、直前に出した問題に積む
        request.session.pop(SESSION_PENDING, None)
        request.session.pop(SESSION_SHOWN_AT, None)
        recent = request.session.get(SESSION_RECENT, [])
        recent.append(question.id)
        request.session[SESSION_RECENT] = recent[-RECENT_LIMIT:]

        return Response({
            'is_correct': is_correct,
            'selected': selected,
            'selected_label': Question.choice_label(selected),
            **answer_json(question),
            'elapsed_ms': elapsed_ms,
            'progress': progress_json(self.learner, question.category),
        })


# ---------------------------------------------------------------- 正答率・履歴

class StatsAPI(LearnerAPI):
    """中分類ごと・分野ごとの正答率と、直近14日の解答数。重点出題での重みも返す。"""

    def get(self, request):
        subject = request.query_params.get('subject')
        if subject not in (Question.SUBJECT_A, Question.SUBJECT_B):
            subject = None
        rows = category_stats(self.learner, subject=subject)
        # 「おまかせ（苦手を重点出題）」で次の1問がその分野から出る確率。
        # 本番の想定出題数を土台に、苦手なほど重くする（selection と同じ式）
        weights = {
            r['category'].id: r['category'].exam_weight * (0.3 + 2.0 * r['weakness'])
            for r in rows if r['question_count']
        }
        total_weight = sum(weights.values()) or 1
        return Response({
            'subject': subject,
            'subjects': [{'value': value, 'label': label} for value, label in Question.SUBJECT_CHOICES],
            'rows': [
                {
                    **category_json(r['category']),
                    'total': r['total'],
                    'correct': r['correct'],
                    'rate_percent': r['rate_percent'],
                    'question_count': r['question_count'],
                    'is_weak': r['is_weak'],
                    'is_untouched': r['is_untouched'],
                    'focus_share': (
                        round(weights[r['category'].id] / total_weight * 100, 1)
                        if r['category'].id in weights else 0.0
                    ),
                }
                for r in rows
            ],
            'fields': field_json(field_stats(rows)),
            'daily': [
                {'date': d['date'].isoformat(), 'total': d['total'], 'correct': d['correct']}
                for d in daily_counts(self.learner, days=14)
            ],
        })


class HistoryAPI(LearnerAPI):
    """解答履歴。新しい順に20件ずつ。result（wrong / correct）と category（中分類の番号）で絞る。"""

    def get(self, request):
        queryset = (
            Attempt.objects.filter(learner=self.learner)
            .select_related('question', 'category')
        )
        result = request.query_params.get('result', '')
        if result == 'wrong':
            queryset = queryset.filter(is_correct=False)
        elif result == 'correct':
            queryset = queryset.filter(is_correct=True)
        category_code = request.query_params.get('category', '')
        if category_code.isdigit():
            queryset = queryset.filter(category__code=category_code)

        paginator = Paginator(queryset, HISTORY_PAGE_SIZE)
        page_number = request.query_params.get('page', '1')
        try:
            page = paginator.page(int(page_number) if page_number.isdigit() else 1)
        except EmptyPage:
            page = paginator.page(paginator.num_pages)

        session = _get_study_session(self.learner)
        return Response({
            'results': [
                {
                    'id': attempt.id,
                    'is_correct': attempt.is_correct,
                    'category': attempt.category.label,
                    'topic': attempt.question.topic,
                    'answered_at': timezone.localtime(attempt.answered_at).isoformat(),
                    'stem': attempt.question.stem,
                    'answer_label': attempt.question.answer_label,
                    'selected_label': attempt.selected_label,
                }
                for attempt in page.object_list
            ],
            'count': paginator.count,
            'page': page.number,
            'num_pages': paginator.num_pages,
            'categories': [
                {'code': c.code, 'label': c.label} for c in categories_for(session.subject)
            ],
        })


# ---------------------------------------------------------------- 合格の申告

class PassReportAPI(RegisteredAPI):
    """本番合格の申告と取り消し。1人1件で、申告し直すと受験日を上書きする。

    履歴を残さない利用からは申告できない。消える記録なので、
    合格者数に数えると実態と合わなくなるため。
    """

    message = '合格の申告には ID の登録が必要です。履歴を残さない利用では申告できません。'

    def post(self, request):
        form = PassReportForm({'passed_on': request.data.get('passed_on', '')})
        if not form.is_valid():
            errors = form.errors.get('passed_on') or ['受験日を入れてください。']
            return Response({'detail': errors[0]}, status=status.HTTP_400_BAD_REQUEST)
        PassReport.objects.update_or_create(
            learner=self.learner, defaults={'passed_on': form.cleaned_data['passed_on']},
        )
        return Response({'message': '合格おめでとうございます。合格者数に数えました。'})

    def delete(self, request):
        PassReport.objects.filter(learner=self.learner).delete()
        return Response({'message': '合格の申告を取り消しました。'})


# ---------------------------------------------------------------- 学習計画（fe.plan）

class PlanAPI(RegisteredAPI):
    """学習計画。受験日を受け取って組み、巡ごとの日程・結果・合格を返す。

    結果を巡をまたいで残すので、ID が要る（履歴を残さない利用では 403）。
    """

    message = '学習計画には ID の登録が必要です。'

    def get(self, request):
        return Response(plan_response(self.learner))

    def post(self, request):
        try:
            exam_date = datetime.strptime(str(request.data.get('exam_date', '')), '%Y-%m-%d').date()
        except ValueError:
            return Response({'detail': '受験日を入れてください。'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            plan.create_plan(self.learner, exam_date, timezone.localdate())
        except plan.PlanError as error:
            return Response({'detail': str(error)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(plan_response(self.learner))

    def delete(self, request):
        StudyPlan.objects.filter(learner=self.learner).delete()
        return Response(plan_response(self.learner))


def plan_response(learner):
    today = timezone.localdate()
    study_plan = StudyPlan.objects.filter(learner=learner).first()
    overall = overall_stats(learner)
    return {
        'today': today.isoformat(),
        # 学習コーナーのトップの帯に出す総合正答率（ダッシュボードの「総合正答率」と同じ値）
        'overall': {
            'rate_percent': overall['rate_percent'],
            'correct': overall['correct'],
            'total': overall['total'],
        },
        'pass_percent': plan.PASS_PERCENT,
        'pass_min_answers': plan.PASS_MIN_ANSWERS,
        'pass_min_topic_answers': plan.PASS_MIN_TOPIC_ANSWERS,
        'plan': plan_json(study_plan, today) if study_plan else None,
    }


def plan_json(study_plan, today):
    """計画の画面に出すもの。中分類を学習モードの順に並べ、巡ごとの日程と結果、合格を添える。"""
    plan.ensure_rounds(study_plan, today)
    current = plan.round_of(study_plan, today)

    entries = {}
    for entry in study_plan.entries.all():
        dates = entries.setdefault((entry.round_no, entry.category_id), [])
        # 苦手の2日ぶんが同じ日に入ることがある（日数より枠が多いとき）。日付は1つにまとめる
        if entry.date.isoformat() not in dates:
            dates.append(entry.date.isoformat())
    results = {
        (row.round_no, row.category_id): row for row in study_plan.results.all()
    }
    # 小分類ごとの合否（中分類の合格は、どの小分類も基準に届いたとき。plan.topic_status）
    topics = plan.category_topics()
    topic_results = {}
    for row in study_plan.topic_results.all():
        topic_results.setdefault((row.round_no, row.category_id), {})[row.topic] = (row.answered, row.correct)
    passes = {
        row.category_id: row
        for row in StudyPlanPass.objects.filter(learner=study_plan.learner)
    }
    rounds = [
        {
            'no': number,
            'first': days[0].isoformat() if days else None,
            'last': days[-1].isoformat() if days else None,
            'built': any(key[0] == number for key in entries),
        }
        for number, days in plan.round_ranges(study_plan)
    ]

    def rate(correct, answered):
        return round(correct / answered * 100) if answered else None

    categories = plan.study_categories()
    # 学習対象から外れた中分類（問題が無くなったなど）でも、合格していれば行を残す
    shown = {c.id for c in categories}
    categories += [row.category for row in passes.values() if row.category_id not in shown]

    rows, today_list = [], []
    for category in categories:
        passed = passes.get(category.id)
        cells = []
        for number in range(1, plan.ROUNDS + 1):
            result = results.get((number, category.id))
            answered = result.answered if result else 0
            correct = result.correct if result else 0
            dates = entries.get((number, category.id), [])
            # 未実施：その巡の予定の日を過ぎても1問も解いていない。正答率は 0％ として出す
            # （次の巡の並べ替えでも、解いていない中分類は 0％ 扱い。plan.ensure_rounds）。
            # あとの巡で合格しても、その巡の未実施は残す（合格した中分類は、それより後の巡には
            # 日程が入らないので、合格のあとに未実施が増えることはない）
            missed = not answered and bool(dates) and min(dates) < today.isoformat()
            recorded = topic_results.get((number, category.id), {})
            # 小分類ごとに数え始める前に解いた分は、小分類の内訳が無い。内訳が無いセルでは
            # 小分類を出さない（解答はあるのに、どの小分類も「未」に見えてしまうため）
            topic_rows = plan.topic_status(topics.get(category.id, {}), recorded) if (recorded or not answered) else []
            cells.append({
                'dates': dates, 'answered': answered, 'correct': correct,
                'rate_percent': 0 if missed else rate(correct, answered),
                'missed': missed,
                'topics': topic_rows,
                'topics_passed': sum(1 for row in topic_rows if row['passed']),
            })
            if number == current and today.isoformat() in dates and not passed:
                today_list.append({**category_json(category), 'answered': answered,
                                   'correct': correct, 'rate_percent': rate(correct, answered)})
        rows.append({
            **category_json(category),
            'rounds': cells,
            'passed': {
                'round_no': passed.round_no,
                'passed_on': passed.passed_on.isoformat(),
                'rate_percent': rate(passed.correct, passed.answered),
            } if passed else None,
        })

    return {
        'exam_date': study_plan.exam_date.isoformat(),
        'start_date': study_plan.start_date.isoformat(),
        'days_left': (study_plan.exam_date - today).days,
        'current_round': current,
        'rounds': rounds,
        'today': today_list,
        'rows': rows,
        'passed_count': sum(1 for row in rows if row['passed']),
        'missed_count': sum(1 for row in rows for cell in row['rounds'] if cell['missed']),
    }


# ---------------------------------------------------------------- 問題メール（fe.mail）

# ID なしで登録したメールの登録の番号。ID が無いので、このブラウザのセッションで覚えておく
# （確認待ちの表示と、確認のメールを続けて送らせないために使う）
SESSION_MAIL = 'fe_mail_subscription_id'


def mail_json(subscription, learner):
    """問題メールの欄に要るもの。登録済みか（伏せたアドレス）、確認待ちか、ID に記録するか。"""
    mail.purge_pending()
    if subscription is not None:
        subscription = MailSubscription.objects.filter(pk=subscription.pk).first()
    registered = bool(subscription and subscription.email)
    return {
        'registered': registered,
        'masked_email': subscription.masked_email if registered else '',
        'pending': bool(subscription and not registered and subscription.pending_email),
        # ID で入っていれば、メールで答えた分をその ID に記録する。ID なしならみんなの集計にだけ数える
        'with_id': not learner.is_temporary,
    }


class MailAPI(LearnerAPI):
    """問題メールの登録。アドレスに確認のメールを送る（登録はリンクを開いて「受け取る」を押してから）。

    ID で入っていれば、その ID の登録になり、メールで答えた分をその ID の学習履歴に足す。
    ID なしなら、ID を持たない登録になり、メールで答えた分はみんなの集計にだけ数える
    （ID なしの記録はブラウザを閉じると使えなくなるので、それにはひも付けない）。
    送り方は1つだけ（9〜18時の毎時に3問）なので、選ぶものはない。登録したあとは、画面から
    アドレスを変えられない（解除はメールのリンクから）。
    """

    def subscription(self, request, create=False):
        if not self.learner.is_temporary:
            if create:
                return MailSubscription.objects.get_or_create(learner=self.learner)[0]
            return MailSubscription.objects.filter(learner=self.learner).first()
        subscription = MailSubscription.objects.filter(
            pk=request.session.get(SESSION_MAIL), learner__isnull=True,
        ).first()
        if subscription is None and create:
            subscription = MailSubscription.objects.create(learner=None)
            request.session[SESSION_MAIL] = subscription.pk
        return subscription

    def get(self, request):
        return Response(mail_json(self.subscription(request), self.learner))

    def post(self, request):
        subscription = self.subscription(request, create=True)
        if subscription.email:
            return Response({'detail': '問題メールは登録済みです。アドレスの変更と解除は、届いたメールのリンクからできます。'},
                            status=status.HTTP_400_BAD_REQUEST)
        email = str(request.data.get('email') or '').strip()
        try:
            validate_email(email)
        except ValidationError:
            return Response({'detail': 'メールアドレスの形が正しくありません。'},
                            status=status.HTTP_400_BAD_REQUEST)
        if not mail.can_send_link(subscription):
            return Response({'detail': '確認のメールは送ったばかりです。少し時間をおいてください。'},
                            status=status.HTTP_429_TOO_MANY_REQUESTS)
        subscription.pending_email = email
        subscription.link_sent_at = timezone.now()
        subscription.save()
        mail.send_confirmation(subscription)
        return Response({
            **mail_json(subscription, self.learner),
            'message': '確認のメールを送りました。メールのリンクを開いて「受け取る」を押すと登録されます。',
        })


# ---------------------------------------------------------------- 学習モード

def opened_categories(session, last):
    """一覧で開いておく中分類。次の2つを、重ねずに両方開く。

    ・ダッシュボードで指定した分野。おまかせはこの中から選ぶので、開いておくと
      何が対象か分かる。開かないと、分野をどう選び直しても一覧の開く先が変わらず、
      前に解き終えた中分類に固定されているように見えた。
    ・最後に解き終えたラウンドの中分類。学習した結果（学習回数）は小分類の行に
      出るので、閉じたままだと、学習したことが一覧に反映されていないように見える。

    どちらか一方だけにすると、学習モードで指定とは別の分野を解き終えたときに、
    ダッシュボードの指定と一覧の開く先がずれる。指定のほうを書き換えて合わせると、
    おまかせや1問1答の出題範囲まで変わってしまうので、両方を開いて済ませる。
    指定が今の科目のものでなければ（focus_category が None なら）使わない。
    """
    opened = []
    for category in (focus_category(session), last.note.category if last else None):
        if category is not None and category not in opened:
            opened.append(category)
    return opened


def round_json(round_):
    """ラウンドの見出しまわり。どの段階の画面でも使う。"""
    return {
        'id': round_.pk,
        'phase': round_.phase,
        'title': round_.title if round_.note else '',
        'has_note': round_.note is not None,
        'total': round_.total,
        'correct': round_.correct,
        'position': round_.position,
        'rate_percent': round_.rate_percent,
    }


class LearnStartAPI(LearnerAPI):
    """学習モードの入口。読む時間を決めてラウンドを始める。"""

    def get(self, request):
        session = _get_study_session(self.learner)
        finished = LearningRound.objects.filter(
            learner=self.learner, phase=LearningRound.PHASE_DONE
        )
        last = (
            finished.filter(subject=session.subject, note__isnull=False)
            .select_related('note__category').first()
        )
        opened = {category.code for category in opened_categories(session, last)}
        groups = []
        for group in note_menu(self.learner, session.subject):
            stats = group['stats'] or {}
            groups.append({
                'code': group['category'].code,
                'name': group['category'].name,
                'note_count': group['note_count'],
                'rate_percent': stats.get('rate_percent'),
                'is_weak': bool(stats.get('is_weak')),
                'question_count': stats.get('question_count', 0),
                'opened': group['category'].code in opened,
                'entries': [
                    {
                        'note': entry['note'].pk,
                        'topic': entry['note'].topic,
                        'titles': [note.title for note in entry['notes']],
                        'questions': entry['questions'],
                        'rounds': entry['rounds'],
                    }
                    for entry in group['notes']
                ],
            })
        return Response({
            'minute_choices': LearningRound.MINUTE_CHOICES,
            'default_minutes': LearningRound.DEFAULT_MINUTES,
            'count': LearningRound.QUESTION_COUNT,
            'groups': groups,
            'recent': [
                {
                    'id': r.pk,
                    'title': r.title if r.note else '',
                    'has_note': r.note is not None,
                    'correct': r.correct,
                    'total': r.total,
                    'started_at': timezone.localtime(r.started_at).isoformat(),
                }
                for r in finished.select_related('note')[:5]
            ],
        })

    def post(self, request):
        raw = request.data.get('minutes')
        minutes = raw if isinstance(raw, int) and not isinstance(raw, bool) else LearningRound.DEFAULT_MINUTES
        if minutes not in LearningRound.MINUTE_CHOICES:
            minutes = LearningRound.DEFAULT_MINUTES

        # 空なら「おまかせ」
        note = None
        chosen = request.data.get('note')
        if chosen not in (None, ''):
            if not str(chosen).isdigit():
                return Response({'detail': 'その解説は見つかりませんでした。'}, status=status.HTTP_400_BAD_REQUEST)
            note = LearningNote.objects.filter(pk=chosen).select_related('category').first()
            if note is None:
                return Response({'detail': 'その解説は見つかりませんでした。'}, status=status.HTTP_400_BAD_REQUEST)

        session = _get_study_session(self.learner)
        # scope=category：中分類まるごと（plan&check の「解説」。出題設定の中分類の解説をすべて読む）
        whole = request.data.get('scope') == 'category'
        round_ = start_round(self.learner, session, minutes, note=note, whole_category=whole)
        if round_ is None:
            if whole:
                detail = 'この中分類には、解説か出題できる問題がまだありません。'
            elif note is not None:
                detail = '「{}」に出題できる問題がありません。'.format(note.title)
            elif focus_category(session) is not None:
                detail = (
                    '{}には、出題できる問題のある技術解説がまだありません。'
                    'ダッシュボードの分野の指定を変えてください。'.format(focus_category(session).name)
                )
            else:
                detail = '解説がありません。'
            return Response({'detail': detail}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'round': round_json(round_)}, status=status.HTTP_201_CREATED)


class RoundAPI(LearnerAPI):
    """1つのラウンドを扱う API の土台。他人のラウンドは「無い」（404）と答える。"""

    def get_round(self, pk):
        round_ = LearningRound.objects.filter(pk=pk, learner=self.learner).select_related('note').first()
        if round_ is None:
            from rest_framework.exceptions import NotFound
            raise NotFound('そのラウンドはありません。')
        return round_

    def finish(self, round_):
        if round_.phase != LearningRound.PHASE_DONE:
            round_.phase = LearningRound.PHASE_DONE
            round_.finished_at = timezone.now()
            round_.save(update_fields=['phase', 'finished_at'])


class LearnReadAPI(RoundAPI):
    """読む段階。設問ではなく、同じ小分類の技術解説をまとめて出す。

    終わったラウンドの解説は、結果画面から読み返せるようにしておく。解く段階に
    進んだラウンドは読み返せない（phase を見て、画面が解く段階へ移る）。
    """

    def get(self, request, pk):
        round_ = self.get_round(pk)
        notes = []
        if round_.phase != LearningRound.PHASE_QUIZ:
            # 開き直した時点で読み上げは止まっているので、止めていた時間を動かす
            if round_.phase == LearningRound.PHASE_READING:
                round_.resume()
            for note in round_.notes:
                notes.append({
                    'id': note.pk,
                    'category_code': note.category.code,
                    'category_name': note.category.name,
                    'topic': note.topic,
                    'title': note.title,
                    'body': note.body,
                    'source': note.source,
                    'audio_url': (
                        reverse('fe:note_audio', args=[speech.audio_name(note)])
                        if speech.has_audio(note) else None
                    ),
                })
        return Response({
            'round': round_json(round_),
            'notes': notes,
            # 途中で再読み込みしても、残り時間は開始時刻から数え直す
            'remaining': round_.remaining_seconds(),
        })

    def post(self, request, pk):
        round_ = self.get_round(pk)
        if round_.phase == LearningRound.PHASE_READING:
            round_.phase = LearningRound.PHASE_QUIZ
            round_.save(update_fields=['phase'])
        return Response({'round': round_json(round_)})


class LearnTimerAPI(RoundAPI):
    """読む時間を止める・動かす。読み上げを再生している間は止める。

    残り時間はサーバーで数えているので、止めたこともサーバーに残す。画面の
    数字だけ止めると、再読み込みしたときに止めていた分が消える。
    """

    def post(self, request, pk):
        round_ = self.get_round(pk)
        if round_.phase == LearningRound.PHASE_READING:
            if request.data.get('state') == 'pause':
                round_.pause()
            else:
                round_.resume()
        return Response({'remaining': round_.remaining_seconds()})


def item_json(round_, item, answered):
    data = {
        'round': round_json(round_),
        'question': question_json(item.question),
        'answered': answered,
    }
    if answered:
        data.update({
            'is_correct': item.is_correct,
            'selected': item.selected_index,
            'selected_label': item.selected_label,
            **answer_json(item.question),
        })
    return data


class LearnQuizAPI(RoundAPI):
    """解く段階。読んだ範囲をそのまま1問1答で出す。

    解き終わっていれば（いまの1問が無ければ）ラウンドを終え、round.phase が done になる。
    """

    def get(self, request, pk):
        round_ = self.get_round(pk)
        if round_.phase != LearningRound.PHASE_QUIZ:
            return Response({'round': round_json(round_), 'question': None})
        item = current_item(round_)
        if item is None:
            self.finish(round_)
            return Response({'round': round_json(round_), 'question': None})
        # 解答してから「次へ」を押す前に開き直したら、採点結果のまま出す
        return Response(item_json(round_, item, item.is_correct is not None))

    def post(self, request, pk):
        round_ = self.get_round(pk)
        if round_.phase != LearningRound.PHASE_QUIZ:
            return Response({'detail': 'このラウンドは解く段階ではありません。'}, status=status.HTTP_409_CONFLICT)
        item = current_item(round_)
        if item is None:
            self.finish(round_)
            return Response({'detail': 'このラウンドは解き終わっています。'}, status=status.HTTP_409_CONFLICT)

        question = item.question
        selected = request.data.get('choice')
        if not isinstance(selected, int) or isinstance(selected, bool) \
                or not 0 <= selected < len(question.choices):
            return Response({'detail': '選択肢を選んでください。'}, status=status.HTTP_400_BAD_REQUEST)

        if item.is_correct is None:
            is_correct = grade(item, selected)
            # 演習と同じ記録に積む。学習モードで解いた分も理解度に反映する。
            Attempt.objects.create(
                learner=self.learner, question=question, category=question.category,
                selected_index=selected, is_correct=is_correct,
            )
            # plan&check の「解説」で始めた回（中分類まるごと）だけ、学習計画の結果にも足す
            record_progress(self.learner, question, is_correct, for_plan=round_.whole_category)
        return Response(item_json(round_, item, True))


class LearnNextAPI(RoundAPI):
    """採点結果を見てから次の1問へ進む。最後の1問なら終える。"""

    def post(self, request, pk):
        round_ = self.get_round(pk)
        item = current_item(round_)
        if item is not None and item.is_correct is not None:
            round_.position += 1
            round_.save(update_fields=['position'])
        if current_item(round_) is None:
            self.finish(round_)
        return Response({'round': round_json(round_)})


class LearnAbandonAPI(RoundAPI):
    """途中のラウンドをやめる。

    やめたラウンドは残さずに消す。続きから再開する道を用意しないので、
    残しても「解答中」のまま溜まるだけで、どこからも開けない記録になる。
    解いたぶんの解答履歴と分野別の理解度はラウンドとは別に積んであり、
    消しても失われない。終わったラウンドは結果を見返すためのものなので消さない。
    """

    def post(self, request, pk):
        round_ = self.get_round(pk)
        if round_.phase == LearningRound.PHASE_DONE:
            return Response({'round': round_json(round_), 'abandoned': False})
        round_.delete()
        return Response({
            'abandoned': True,
            'message': 'ラウンドを中断しました。解いたぶんの記録は残っています。',
        })


class LearnResultAPI(RoundAPI):
    """ラウンドの結果。解いた問題を、正解したものも含めて全問読み返せるようにする。"""

    def get(self, request, pk):
        round_ = self.get_round(pk)
        items = round_.items.select_related('question', 'question__category', 'question__template')
        return Response({
            'round': round_json(round_),
            'items': [
                {
                    'is_correct': item.is_correct,
                    'selected_label': item.selected_label,
                    'question': question_json(item.question),
                    **answer_json(item.question),
                }
                for item in items
            ],
        })
