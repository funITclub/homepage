# countdown/views.py
#
# 誰でも使える公開アプリ。会員登録もログインも持たないため、
# LoginRequiredMiddleware の対象から login_not_required で外している。
# 公開サイト（/）とは相互にリンクせず、成果物ページに URL を載せて辿る想定。
#
# 出来事・予定は、本アプリの中の ID（Board）ごとに分けて持つ。/countdown/<ID>/ が
# その ID の一覧で、ID を知っている人なら誰でも読み書きできる（合言葉はない）。
# ID を使わない人には、誰でも読み書きできる共有ボード（/countdown/events/）がある。
# どちらも同じビューで、URL に ID があるかどうかだけが違う。
# 一覧は React の画面（AppView が入れ物を返し、データは countdown/api.py から読む）。
#
# メール通知は ID の一覧でだけ使える（countdown/notify.py）。

import hmac
import logging
import smtplib

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_not_required
from django.core.mail import BadHeaderError
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import generic
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie

from edit.models import public_contact_email
from home.netutils import client_ip

from . import notify
from .forms import BoardForm, CountEventForm, NotifyEmailForm
from .models import Board, CountEvent, board_url

logger = logging.getLogger(__name__)


@method_decorator(login_not_required, name='dispatch')
class IndexView(generic.TemplateView):
    """アプリの紹介ページ。"""

    template_name = 'countdown/index.html'
    extra_context = {'nav': 'index'}


@method_decorator(login_not_required, name='dispatch')
class EnterView(generic.FormView):
    """ID で入る、または新しく作る。"""

    template_name = 'countdown/enter.html'
    form_class = BoardForm
    extra_context = {'nav': 'enter'}

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['creating'] = self.request.POST.get('action') == 'create'
        return kwargs

    def form_valid(self, form):
        if form.creating:
            board = Board.objects.create(code=form.cleaned_data['code'])
            messages.success(
                self.request,
                f'ID「{board.code}」を作りました。このページの URL から、いつでも開けます。',
            )
        else:
            board = form.board
        return redirect(board_url(board, 'list'))


@method_decorator(login_not_required, name='dispatch')
class BoardMixin:
    """URL の ID から置き場を決める。ID がなければ共有ボード（self.board は None）。

    扱う出来事・予定をその置き場のものに絞るので、ほかの ID のものは
    番号を言い当てても開けない（404）。
    """

    def dispatch(self, request, *args, **kwargs):
        code = kwargs.get('code')
        self.board = get_object_or_404(Board, code=code.lower()) if code else None
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return CountEvent.objects.filter(board=self.board)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if issubclass(self.get_form_class(), CountEventForm):
            kwargs['board'] = self.board
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['board'] = self.board
        context['list_url'] = self.list_url
        context['create_url'] = board_url(self.board, 'create')
        return context

    @property
    def list_url(self):
        return board_url(self.board, 'list')

    def get_success_url(self):
        return self.list_url


@method_decorator(ensure_csrf_cookie, name='dispatch')
class AppView(BoardMixin, generic.TemplateView):
    """一覧の画面（React）の入れ物。中身は React（frontend/countdown）が描く。

    一覧・登録・編集・削除の URL はどれも同じ入れ物を返し、何を描くかは React が
    アドレスを見て決める（登録・編集は一覧の上にパネルを開く。削除は一覧の「削除」ですぐ行い、
    以前の削除確認の URL は一覧へ戻す）。データは React が API（countdown/api.py）から読む。

    編集・削除の URL は、その置き場に無い番号なら 404 にする（ほかの ID のものを
    番号で言い当てても開けない。画面のころと同じ）。
    書き込みは API が受けるので、ここは GET だけ。CSRF の Cookie はここで配る。
    """

    template_name = 'countdown/app.html'
    http_method_names = ['get', 'head']
    extra_context = {'nav': 'list'}

    def get(self, request, *args, **kwargs):
        if 'pk' in kwargs:
            get_object_or_404(self.get_queryset(), pk=kwargs['pk'])
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if kwargs.get('pk') is None and self.request.resolver_match.url_name.endswith('_create'):
            context['nav'] = 'create'
        # ID を作ったときなどの知らせは、React がトーストで出す
        context['notices'] = [str(m) for m in messages.get_messages(self.request)]
        return context


class MailSettingsView(BoardMixin, generic.FormView):
    """その ID の通知先。

    登録は確認のメールを経る。通知先がある間は、画面からは変更も解除もできない
    （ID を知っている人が止めたり、自分のアドレスに差し替えたりできないように）。
    解除は登録されたアドレスに届くメールのリンクからだけで、ここからはそのメールを送れる。
    """

    template_name = 'countdown/mail_settings.html'
    form_class = NotifyEmailForm
    extra_context = {'nav': 'mail'}

    def get_success_url(self):
        return self.board.mail_url

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['contact'] = public_contact_email()
        return context

    def _error(self, message, status, form=None):
        form = form or self.get_form_class()()
        return self.render_to_response(
            self.get_context_data(form=form, mail_error=message), status=status)

    def _send(self, email, send, form=None):
        """送りすぎと送信の失敗を確かめながら送る。だめなら、その画面を返す。"""
        if not notify.allow_send(client_ip(self.request), email):
            return self._error(
                '短い時間に何度も送られています。しばらく時間をおいてから、もう一度お試しください。', 429, form)
        try:
            send()
        except (smtplib.SMTPException, OSError, BadHeaderError) as e:
            # 例外の文言には宛先のアドレスが入ることがあるので、種類だけ残す
            logger.error('カウントダウンのメールを送れませんでした（%s）', type(e).__name__)
            return self._error('メールを送れませんでした。時間をおいて、もう一度お試しください。', 502, form)
        return None

    def post(self, request, *args, **kwargs):
        registered = self.board.notify_email
        if request.POST.get('action') == 'stop':
            if not registered:
                return redirect(self.get_success_url())
            url = request.build_absolute_uri(
                reverse('countdown:notify_stop', args=[notify.make_stop_token(self.board)]))
            failed = self._send(registered, lambda: notify.send_stop_link(self.board, url))
            if failed:
                return failed
            messages.success(
                request, '登録されているアドレスに、解除用のメールを送りました。メールのリンクから解除できます。')
            return redirect(self.get_success_url())
        if registered:
            return self._error(
                '通知先はすでに登録されています。変えるときは、いちど解除してから登録し直してください。', 409)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        email = form.cleaned_data['email']
        url = self.request.build_absolute_uri(
            reverse('countdown:notify_confirm', args=[notify.make_confirm_token(self.board, email)])
        )
        failed = self._send(email, lambda: notify.send_confirmation(self.board, email, url), form)
        if failed:
            return failed
        messages.success(
            self.request,
            '確認のメールを送りました。メールのリンクを開くと登録されます（{}分以内）。'.format(
                settings.COUNTDOWN_CONFIRM_MAX_AGE // 60
            ),
        )
        return super().form_valid(form)


class NotifyLinkView(generic.View):
    """メールのリンクから開く画面。開いただけでは何もせず、ボタンを押したときに実行する。

    メールの中のリンクは、受信側の検査で自動的に開かれることがあるため。
    """

    template_name = 'countdown/notify_link.html'
    http_method_names = ['get', 'post']
    action = None

    def read(self, token, consume=False):
        raise NotImplementedError

    def apply(self, board, email):
        raise NotImplementedError

    @method_decorator(login_not_required)
    def dispatch(self, request, token, *args, **kwargs):
        if request.method.lower() not in self.http_method_names:
            return self.http_method_not_allowed(request)
        try:
            board, email = self.read(token, consume=request.method == 'POST')
        except notify.LinkInvalid:
            return render(request, self.template_name, {'action': 'invalid'}, status=400)
        if request.method == 'POST':
            messages.success(request, self.apply(board, email))
            return redirect(board.mail_url)
        return render(request, self.template_name, {
            'action': self.action, 'board': board, 'contact': public_contact_email()})


class NotifyConfirmView(NotifyLinkView):
    """確認のメールのリンク。押すと、そのアドレスが通知先になる。"""

    action = 'confirm'

    def read(self, token, consume=False):
        return notify.read_confirm_token(token, consume=consume)

    def apply(self, board, email):
        board.set_notify_email(email)
        return 'メール通知の通知先を登録しました。'


class NotifyStopView(NotifyLinkView):
    """通知のメールに付けた解除のリンク。押すと、アドレスを消す。"""

    action = 'stop'

    def read(self, token, consume=False):
        return notify.read_stop_token(token), None

    def apply(self, board, email):
        board.set_notify_email('')
        return 'メール通知を止め、登録されていたアドレスを消しました。'


@method_decorator([csrf_exempt, login_not_required], name='dispatch')
class NotifyRunView(generic.View):
    """今日の分の通知を送る。毎日0時に GitHub Actions から呼ばれる。

    App Service には常設のスケジューラが無く、DB は VNet の中にあって外からコマンドを
    流せないので、送信のきっかけだけを外から受け取る。COUNTDOWN_NOTIFY_TOKEN を
    知っている呼び出しだけを受け付け、未設定のときは入口ごと閉じる（404）。
    """

    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        expected = settings.COUNTDOWN_NOTIFY_TOKEN
        given = request.headers.get('Authorization', '')
        if not expected or not hmac.compare_digest(given.encode(), f'Bearer {expected}'.encode()):
            raise Http404
        sent = notify.send_daily()
        logger.info('カウントダウンの通知を %s 通送りました', sent)
        return JsonResponse({'sent': sent})
