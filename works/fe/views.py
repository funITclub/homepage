"""FE 対策アプリのビュー。

学習の画面（ダッシュボード・ID の入力・1問1答・学習モード・分野別正答率・履歴・
このアプリについて）は React（frontend/fe）が描く。ここが出すのは、その入れ物のページ
（AppView）と、Django の画面のままのもの（問題の管理・メールのリンク・
問題メールの解答ページ・定期実行の入口・読み上げ音声）。React が呼ぶ API は api.py にある。
出題する問題の選定は fe.selection，成績の集計は fe.stats に分けてある。

成績は Learner（本アプリの中の ID）ごとに持つ。/fe/ を開くと ID なしの記録を
作ってセッションが覚える。ID で入る・作るのは /fe/id/ で、入ったあとも
ダッシュボードは /fe/ のまま（ID は URL に出さない。以前の /fe/mypage/ は /fe/ へ送る）。問題と技術解説は全 ID で共有し、
取り込みなどの管理は /fe/console/ で、編集画面にログインした人だけができる。学習の画面には
管理のページがあることを出さない。

hirahira_room の fe アプリからの移植。あちらは全画面がログイン必須だが、
こちらは誰でも使える公開アプリなので、LoginRequiredMiddleware の対象から
login_not_required で外している。例外は問題集の管理（/fe/console/）で、
編集画面（/edit/）と同じログインを求める（LoginRequiredMixin）。スタッフ権限は
問わない。共用の編集アカウントには /admin/ に入れる権限を持たせないため。
"""

import datetime
import logging

import hmac
import json
import re

from django.contrib import messages
from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import generic
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie

from .exam import EXAM, build_prompt
from .forms import QuestionUploadForm
from .importer import (ImportError_, needs_confirmation, parse,
                       preview, sync, validate)
from . import mail, speech
from .models import (Category, Learner, MailQuestion, Question, StudySession)
from .pageviews import summary as page_view_summary
from .slots import HOURLY_SLOTS, citation

logger = logging.getLogger(__name__)

# 直前に出した問題が続けて出ないようにするための履歴の長さ
RECENT_LIMIT = 12
SESSION_RECENT = 'fe_recent_question_ids'
SESSION_PENDING = 'fe_pending_question_id'
SESSION_SHOWN_AT = 'fe_question_shown_at'
# 入っている ID。ブラウザのセッションで持つ（編集画面のログインとは関係しない）。
SESSION_LEARNER = 'fe_learner_id'
# 入っている ID を、ブラウザを閉じたら消える Cookie にも持たせる。セッションは
# 閉じても2週間残る（編集画面のログインと同じ入れ物）ので、それだけだと
# 共用の端末で次の人が前の人の ID のまま入ってしまう。
LEARNER_COOKIE = 'fe_learner'
LEARNER_COOKIE_SALT = 'fe.learner'
# ダッシュボードの ID のポップアップで「次回から表示しない」に印を付けて ID で入ったときは、
# ブラウザを閉じても ID を保持する（Cookie に期限を付ける）。セッションは2週間で切れるので、
# 切れたあとは Cookie から入り直す（current_learner）。保持するのは ID を作った記録だけ。
LEARNER_KEEP_DAYS = 365


def _get_study_session(learner):
    session, _ = StudySession.objects.get_or_create(learner=learner)
    return session


def _enter(request, learner, keep=False):
    """その ID で入る。前の ID の出題途中の状態は持ち越さない。

    keep が真なら、ブラウザを閉じても ID を保持する（remember_entry が Cookie に期限を付ける）。
    偽なら、前に保持していた Cookie も、ブラウザを閉じたら消える Cookie で上書きされる。
    """
    for key in (SESSION_RECENT, SESSION_PENDING, SESSION_SHOWN_AT):
        request.session.pop(key, None)
    request.session[SESSION_LEARNER] = learner.pk
    # 応答を返すときに、ブラウザを閉じたら消える Cookie を置く（remember_entry）
    request.fe_entered = learner.pk
    request.fe_keep = keep


def remember_entry(request, response):
    """入ったばかりなら、Cookie に ID を置く。

    ふつうは期限を付けないので、ブラウザを閉じると消える。消えたら current_learner が
    セッションの ID も捨てるので、次に開いたときは入口からになる。
    保持するとき（fe_keep）は LEARNER_KEEP_DAYS の期限を付け、閉じても残す。
    """
    pk = getattr(request, 'fe_entered', None)
    if pk is not None:
        keep = getattr(request, 'fe_keep', False)
        response.set_signed_cookie(
            LEARNER_COOKIE, str(pk), salt=LEARNER_COOKIE_SALT,
            max_age=LEARNER_KEEP_DAYS * 24 * 60 * 60 if keep else None,
            httponly=True, samesite='Lax', secure=request.is_secure(),
        )
    return response


def current_learner(request):
    """セッションが覚えている記録。始めていなければ None。

    ID を登録した人も、履歴を残さずに使っている人も、同じようにここから取る。
    ブラウザを閉じて Cookie が消えていれば、セッションに残っていても入っていない
    扱いにする。
    セッションに無くても、保持している Cookie（期限付き）が ID を作った記録を指していれば、
    セッションに戻して入っている扱いにする（2週間でセッションが切れたあと）。
    """
    pk = request.session.get(SESSION_LEARNER)
    if pk is None:
        return _restore_kept(request)
    entered = getattr(request, 'fe_entered', None) == pk or request.get_signed_cookie(
        LEARNER_COOKIE, default=None, salt=LEARNER_COOKIE_SALT,
    ) == str(pk)
    if not entered:
        request.session.pop(SESSION_LEARNER, None)
        return None
    learner = Learner.objects.filter(pk=pk).first()
    if learner is None:
        request.session.pop(SESSION_LEARNER, None)
    return learner


def _restore_kept(request):
    """保持している Cookie から ID に入り直す。ID の無い記録は戻さない。"""
    value = request.get_signed_cookie(LEARNER_COOKIE, default=None, salt=LEARNER_COOKIE_SALT)
    if not value or not value.isdigit():
        return None
    learner = Learner.objects.filter(pk=int(value), code__isnull=False).first()
    if learner is not None:
        request.session[SESSION_LEARNER] = learner.pk
    return learner


def start_temporary(request):
    """履歴を残さずに始める。ID を持たない記録を作ってセッションに結び付ける。"""
    learner = Learner.objects.create(code=None)
    _enter(request, learner)
    return learner


def touch(learner):
    """最終利用日時を進める。使われなくなった一時的な記録を見分けるため。

    登録済みの ID は消さないので、一時的な記録のときだけ書き込む。
    """
    if learner.is_temporary:
        Learner.objects.filter(pk=learner.pk).update(last_seen_at=timezone.now())


class LearnerRequiredMixin:
    """始めている人向けの画面。始めていなければトップへ戻す。ログインは要らない。

    いまの記録は self.learner に置く。ヘッダーに出すため、
    request.fe_learner にも載せておく。
    """

    @method_decorator(login_not_required)
    def dispatch(self, request, *args, **kwargs):
        self.learner = current_learner(request)
        if self.learner is None:
            return redirect('fe:index')
        request.fe_learner = self.learner
        touch(self.learner)
        self.check_learner(self.learner)
        return super().dispatch(request, *args, **kwargs)

    def check_learner(self, learner):
        """入っている ID でこの画面を使えるか。使えなければ例外を投げる。"""


@method_decorator(ensure_csrf_cookie, name='dispatch')
@method_decorator(login_not_required, name='dispatch')
class AppView(generic.TemplateView):
    """学習の画面の入れ物。中身は React（frontend/fe。ビルドしたものは static/fe/app/）が描き、
    データは api.py から取る。作りは bk_houmu3・countdown と同じ。

    ensure_csrf_cookie で csrftoken の Cookie を必ず配る。React は書き込みのとき、
    その値を X-CSRFToken ヘッダーに載せて送る。

    entry で、開いたときの記録の扱いを分ける。
      'index'   入口（/fe/）。ID の有無にかかわらずダッシュボード。まだ始めていなければ、
                履歴を残さない記録をその場で作る
      'open'    始めていなくても開ける画面（ID の入力欄・このアプリについて）
      'start'   1問1答（/fe/quiz/）。問題メールの「1問1答を解く」からの案内先なので、まだ始めていなければ
                入口と同じく、履歴を残さない記録をその場で作ってそのまま解かせる
      'learner' 始めている人向けの画面。始めていなければ入口へ戻す（入口が記録を作る）

    ページビューは、画面を出したときに React が api/pageview/ で数える（画面の切りかえは
    React の中で行い、ここを通らないため）。
    """

    template_name = 'fe/app.html'
    entry = 'learner'

    def get(self, request, *args, **kwargs):
        learner = current_learner(request)
        if self.entry == 'index':
            if learner is None:
                learner = start_temporary(request)
        elif self.entry == 'start' and learner is None:
            learner = start_temporary(request)
        elif self.entry == 'learner' and learner is None:
            return redirect('fe:index')
        if learner is not None:
            touch(learner)
        # 入ったら、ブラウザを閉じたら消える Cookie を置く
        return remember_entry(request, super().get(request, *args, **kwargs))


# ================================================================ 問題の管理
# 問題は全 ID で共有し、JSON の取り込みが唯一の作成・更新経路。
# 画面に入力フォームを置かないので、手元の JSON と画面の内容がずれない。
# 一覧・取り込みは、編集画面のログインだけで使える。学習用の ID は問わない。
# 学習の画面からはリンクしない。


class ManageListView(LoginRequiredMixin, generic.ListView):
    """共有の問題の一覧。中身の確認だけを行う。"""

    template_name = 'fe/manage_list.html'
    context_object_name = 'questions'
    paginate_by = 25

    def get_queryset(self):
        queryset = (
            Question.objects.select_related('category', 'template')
            .annotate(attempt_count=Count('attempts'))
        )
        params = self.request.GET
        if params.get('subject') in (Question.SUBJECT_A, Question.SUBJECT_B):
            queryset = queryset.filter(subject=params['subject'])
        if params.get('category', '').isdigit():
            queryset = queryset.filter(category__code=params['category'])
        keyword = params.get('q', '').strip()
        if keyword:
            queryset = queryset.filter(stem__icontains=keyword)
        if params.get('generated') != 'on':
            queryset = queryset.filter(template__isnull=True)
        return queryset.order_by('category__code', 'id')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        mine = Question.objects.filter(template__isnull=True)
        context['categories'] = Category.objects.all()  # 一覧は両科目を横断して絞り込む
        context['filters'] = self.request.GET
        context['query_string'] = self.request.GET.urlencode()
        context['summary'] = {
            'total': mine.count(),
            'subject_a': mine.filter(subject=Question.SUBJECT_A).count(),
            'subject_b': mine.filter(subject=Question.SUBJECT_B).count(),
            'generated': Question.objects.filter(template__isnull=False).count(),
        }
        return context


class PageViewListView(LoginRequiredMixin, generic.TemplateView):
    """学習の画面のページビュー。直近30日の日別・画面別の件数（fe.pageviews）。"""

    template_name = 'fe/manage_pageviews.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['views'] = page_view_summary(days=30)
        return context


class QuestionUploadView(LoginRequiredMixin, generic.FormView):
    """JSON を取り込んで、共有の問題集を差し替える。"""

    template_name = 'fe/manage_upload.html'
    form_class = QuestionUploadForm
    success_url = reverse_lazy('fe:manage_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['exam'] = EXAM
        context['prompt'] = build_prompt()
        return context

    @staticmethod
    def _count_lines(result):
        """追加・更新・変更なし・削除の件数を、画面に出す文にする。"""
        lines = []
        for label, key in (('問題', 'questions'), ('解説', 'notes')):
            counts = result[key]
            if counts is None:
                lines.append('{}：変更なし（ファイルに{}が含まれていません）'.format(label, label))
                continue
            lines.append(
                '{}（{}）：追加 {} / 更新 {} / 変更なし {} / 削除 {}'.format(
                    label, '・'.join('科目' + s for s in counts['subjects']),
                    counts['added'], counts['updated'],
                    counts['unchanged'], counts['removed'],
                )
            )
        return lines

    def form_valid(self, form):
        # まず書き込まずに数える。削除が多いときは、確定の前に一度止める。
        counts = preview(form.records)
        if needs_confirmation(counts) and self.request.POST.get('confirm') != '1':
            return self.render_to_response(self.get_context_data(
                form=form, confirm=self._count_lines(counts),
                payload=json.dumps(form.records, ensure_ascii=False),
            ))

        result = sync(form.records)
        messages.success(self.request, '　'.join(self._count_lines(result)))
        return super().form_valid(form)

    def post(self, request, *args, **kwargs):
        """確認のあとの実行。ファイルを選び直さずに済むよう、内容を持ち回す。"""
        if request.POST.get('confirm') == '1' and 'payload' in request.POST:
            form = self.get_form()
            try:
                form.records = validate(parse(request.POST['payload']))
            except ImportError_ as exc:
                messages.error(request, str(exc))
                return redirect('fe:manage_upload')
            result = sync(form.records)
            messages.success(request, '　'.join(self._count_lines(result)))
            return redirect(self.success_url)
        return super().post(request, *args, **kwargs)


_RANGE = re.compile(r'^bytes=(\d*)-(\d*)$')


class NoteAudioView(LearnerRequiredMixin, generic.View):
    """技術解説の読み上げ音声を返す。

    iPhone の Safari は音声を「何バイト目から何バイト目まで」と区切って取りに来る
    （Range 要求）。これに 206 で応えないと、再生や途中への移動ができないことがある。
    ファイル名は本文から計算したハッシュで、中身が変わることはないので長く持たせる。
    """

    def get(self, request, name, *args, **kwargs):
        if not speech.NAME_PATTERN.match(name):
            raise Http404
        path = speech.audio_root() / name
        if not path.is_file():
            raise Http404
        size = path.stat().st_size
        match = _RANGE.match(request.headers.get('Range', ''))
        if match is None:
            response = FileResponse(open(path, 'rb'), content_type='audio/mpeg')
        else:
            first, last = match.groups()
            if first:
                start, end = int(first), int(last) if last else size - 1
            elif last:
                # 「末尾の n バイト」の形
                start, end = max(0, size - int(last)), size - 1
            else:
                start, end = 0, size - 1
            end = min(end, size - 1)
            if start > end:
                response = HttpResponse(status=416)
                response['Content-Range'] = 'bytes */{}'.format(size)
                return response
            with open(path, 'rb') as audio:
                audio.seek(start)
                data = audio.read(end - start + 1)
            response = HttpResponse(data, status=206, content_type='audio/mpeg')
            response['Content-Range'] = 'bytes {}-{}/{}'.format(start, end, size)
            response['Content-Length'] = str(len(data))
        response['Accept-Ranges'] = 'bytes'
        response['Cache-Control'] = 'private, max-age=31536000, immutable'
        return response


# ---- 問題メール（fe.mail） ----

@method_decorator(login_not_required, name='dispatch')
class MailConfirmView(generic.View):
    """確認のメールのリンク。開いただけでは登録せず、「受け取る」を押して登録する。

    メールソフトや迷惑メールの検査がリンクを先に開くことがあるため。
    別の端末で開くこともあるので、入っている ID は見ない。
    """

    template_name = 'fe/mail_link.html'

    def get(self, request, token):
        try:
            subscription = mail.read_confirm_token(token)
        except mail.LinkInvalid:
            return render(request, self.template_name, {'invalid': True, 'kind': 'confirm'})
        return render(request, self.template_name, {'kind': 'confirm', 'subscription': subscription})

    def post(self, request, token):
        try:
            subscription = mail.read_confirm_token(token)
        except mail.LinkInvalid:
            return render(request, self.template_name, {'invalid': True, 'kind': 'confirm'})
        mail.confirm(subscription)
        return render(request, self.template_name, {'done': True, 'kind': 'confirm', 'subscription': subscription})


@method_decorator(login_not_required, name='dispatch')
class MailStopView(generic.View):
    """解除のリンク。開いただけでは解除せず、「配信を止める」を押して解除する。"""

    template_name = 'fe/mail_link.html'

    def get(self, request, token):
        try:
            subscription = mail.read_stop_token(token)
        except mail.LinkInvalid:
            return render(request, self.template_name, {'invalid': True, 'kind': 'stop'})
        return render(request, self.template_name, {'kind': 'stop', 'subscription': subscription})

    def post(self, request, token):
        try:
            subscription = mail.read_stop_token(token)
        except mail.LinkInvalid:
            return render(request, self.template_name, {'invalid': True, 'kind': 'stop'})
        mail.stop(subscription)
        return render(request, self.template_name, {'done': True, 'kind': 'stop', 'subscription': subscription})


@method_decorator(login_not_required, name='dispatch')
@method_decorator(csrf_exempt, name='dispatch')
class SendMailsView(generic.View):
    """問題メールの送信を、GitHub Actions（.github/workflows/fe-mails.yml）の定期実行から起こす入口（9〜18時の毎時）。

    ログインの代わりに共有トークン（settings.FE_MAIL_TOKEN）で確かめ、時間帯（slot：h09〜h18）と
    予定の日付（date、YYYY-MM-DD。省略可）を受け取る。日付は今日の前後1日だけ受け付ける。
    """

    def post(self, request):
        expected = settings.FE_MAIL_TOKEN
        if not expected:
            logger.error('FE_MAIL_TOKEN が未設定のため、問題メールを送れません。')
            return JsonResponse({'detail': '問題メール用のトークンが未設定です。'}, status=503)
        provided = request.headers.get('X-Fe-Mail-Token', '')
        if not hmac.compare_digest(provided, expected):
            logger.warning('問題メールの送信が、不正なトークンで試みられました。')
            return JsonResponse({'detail': '認証できません。'}, status=403)
        slot = request.POST.get('slot') or request.GET.get('slot', '')
        if slot not in HOURLY_SLOTS:
            return JsonResponse({'detail': '時間帯（slot）が正しくありません。'}, status=400)
        date_text = request.POST.get('date') or request.GET.get('date', '')
        date = None
        if date_text:
            try:
                date = datetime.date.fromisoformat(date_text)
            except ValueError:
                return JsonResponse({'detail': '日付（date）が正しくありません。'}, status=400)
            if abs((date - timezone.localdate()).days) > 1:
                return JsonResponse({'detail': '日付（date）が今日から離れすぎています。'}, status=400)
        result = mail.send_slot(slot, today=date)
        logger.info('問題メール（%s）を送りました（%s）', slot, result)
        return JsonResponse(result)


@method_decorator(login_not_required, name='dispatch')
class MailAnswerView(generic.View):
    """問題メールの1問の解答ページ（/fe/m/<code>/）。ログインも ID の入力もなしで開ける。

    メールに載せた問題と選択肢をもう一度出し、選ぶと正誤・解説を出して、メールを送った
    ID の解答履歴と分野別の理解度に記録する（fe.mail.record_answer。1問につき1回だけ）。
    ID なしで登録したメールなら、みんなの集計にだけ数える。
    記号はランダムで、メールを受け取った人にしか分からない。画面は hirahira_room の X の解答ページと同じ作り。
    期限（FE_MAIL_KEEP_DAYS）を過ぎた問題と存在しない記号には、同じ案内ページを出す。
    """

    template_name = 'fe/mail_answer.html'

    def dispatch(self, request, code, *args, **kwargs):
        self.item = (
            MailQuestion.objects.filter(code=code)
            .select_related('question__category', 'subscription__learner').first()
        )
        if self.item is None or not mail.is_open(self.item):
            return render(request, self.template_name, self.base_context(None), status=404)
        return super().dispatch(request, code, *args, **kwargs)

    def base_context(self, question):
        return {
            'post': question,
            # 「対策を続ける」の行き先はダッシュボード（ユーザーの指示）
            'fe_url': settings.SITE_URL.rstrip('/') + reverse('fe:index'),
            'citation': citation(question.source) if question else '',
            'expired_text': 'メールの問題に答えるページは、送ってから{}日で公開を終えています。'.format(
                settings.FE_MAIL_KEEP_DAYS),
        }

    def answered_context(self):
        learner = self.item.subscription.learner
        context = self.base_context(self.item.question)
        context.update({
            'answered': True,
            'selected': self.item.selected_index,
            'is_correct': self.item.is_correct,
            'recorded_code': learner.code if learner else '',
            'recorded_open': learner is None,
        })
        return context

    def get(self, request, code):
        if self.item.selected_index is not None:
            return render(request, self.template_name, self.answered_context())
        return render(request, self.template_name, self.base_context(self.item.question))

    def post(self, request, code):
        question = self.item.question
        selected = request.POST.get('choice', '')
        if self.item.selected_index is None and (
                not selected.isdigit() or int(selected) >= len(question.choices)):
            context = self.base_context(question)
            context['error'] = '選択肢を選んでください。'
            return render(request, self.template_name, context)
        if self.item.selected_index is None:
            mail.record_answer(self.item, int(selected))
        # 答え直しても、最初の答えのまま見せる
        return render(request, self.template_name, self.answered_context())
