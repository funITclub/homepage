# home/views.py
#
# 認証なしの公開サイト。掲載内容は編集画面（/edit/）で編集し、
# ここでは DB から読んで表示するだけ。各WGのサブアプリはまだ無いため、
# リンク先が未設定のものは「作成中」ページへ集約する。
#
# LoginRequiredMiddleware で全ビューが既定ログイン必須になっているため、
# このファイルのビューだけ login_not_required で公開している。

import logging
import smtplib
import time
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_not_required
from django.core.cache import cache
from django.core.mail import BadHeaderError
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.generic import FormView, TemplateView

from catalog.models import Wg, Work
from news.models import News

from .forms import JoinForm
from .models import BlockedIp
from .netutils import client_ip
from .notifications import send_block_notification

logger = logging.getLogger(__name__)


def detect_and_block_burst_submissions(request):
    """同一IPからの連続送信を数え、settings.JOIN_BURST_RULES を超えたら**そのIPを遮断する**。

    参加フォームは入力されたアドレスの持ち主を確認していないため、第三者あてに
    自動返信を送らせる踏み台にできる。1件ずつでは正規の申し込みと区別できないので、
    数と間隔で異常を拾う。

    遮断は home.BlockedIp に記録され、以降そのIPからのアクセスは
    config.middleware.BlockedIpMiddleware が 403 で止める。**期限は無く、
    admin から消すまで続く**。

    ログにはメールアドレスを出さず、IP と件数だけを残す。
    数えるだけの機能なので、キャッシュが使えなくても申し込みは通す。
    """
    ip = client_ip(request)
    if not ip:
        return

    now = time.time()
    for limit, seconds in settings.JOIN_BURST_RULES:
        key = f'join-burst:{seconds}:{ip}'
        try:
            # (件数, 窓の開始時刻) を持つ。開始時刻から seconds 過ぎたら数え直す。
            # incr は backend によって有効期限の扱いが違うので使わない。
            entry = cache.get(key)
            if entry and now - entry[1] < seconds:
                count, started = entry[0] + 1, entry[1]
            else:
                count, started = 1, now
            cache.set(key, (count, started), seconds)
        except Exception:
            logger.debug('連続送信の計測に失敗しました', exc_info=True)
            return

        if count > limit:
            logger.warning(
                '参加フォームの連続送信を検知しました: %s分間に%s件（上限%s件） IP=%s',
                seconds // 60, count, limit, ip,
            )
            block_ip(ip, f'参加フォームの連続送信（{seconds // 60}分間に{count}件）')
            return


def block_ip(ip, reason):
    """IP を遮断する。繰り返しているほど期間を延ばす（settings.IP_BLOCK_DURATIONS）。

    期限切れの行は消さずに残してあるので、再犯なら回数を引き継いで重くできる。
    遮断できなくても申し込み自体は通す（付加機能のために本筋を止めない）。
    """
    try:
        blocked, created = BlockedIp.objects.get_or_create(ip=ip)
        if not created:
            blocked.block_count += 1

        durations = settings.IP_BLOCK_DURATIONS
        seconds = durations[min(blocked.block_count, len(durations)) - 1]

        blocked.reason = reason
        blocked.expires_at = (
            None if seconds is None else timezone.now() + timedelta(seconds=seconds)
        )
        blocked.save()
    except Exception:
        logger.exception('IP の遮断に失敗しました: IP=%s', ip)
        return

    logger.warning(
        'IP を遮断しました: IP=%s %s回目 解除予定=%s 理由=%s',
        ip, blocked.block_count, blocked.expires_at or '恒久', reason,
    )

    # middleware は home.models を読むので、循環を避けてここで import する
    from config.middleware import BlockedIpMiddleware
    BlockedIpMiddleware.forget_cache()

    send_block_notification(blocked)


class NavMixin:
    """テンプレートでナビの現在地を判定するための識別子を渡す。"""

    nav = ''

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['nav'] = self.nav
        return context


@method_decorator(login_not_required, name='dispatch')
class IndexView(NavMixin, TemplateView):
    """TOP。ヒーロー・活動サマリ・お知らせ。

    活動サマリの件数は、公開中のWG（活動中のみ）と成果物の登録数に連動する。
    """

    #: TOP に載せるお知らせの件数
    news_limit = 5

    template_name = 'home/index.html'
    nav = 'top'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['news_list'] = News.objects.published()[:self.news_limit]
        context['active_wg_count'] = Wg.objects.published().filter(status=Wg.ACTIVE).count()
        context['work_count'] = Work.objects.published().count()
        return context


@method_decorator(login_not_required, name='dispatch')
class WgListView(NavMixin, TemplateView):
    """WG一覧。"""

    template_name = 'home/wg_list.html'
    nav = 'wg'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['wg_list'] = Wg.objects.published()
        return context


@method_decorator(login_not_required, name='dispatch')
class WorkListView(NavMixin, TemplateView):
    """成果物一覧。"""

    template_name = 'home/work_list.html'
    nav = 'works'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['work_list'] = Work.objects.published()
        return context


@method_decorator(login_not_required, name='dispatch')
class JoinView(NavMixin, TemplateView):
    """参加する。活動の案内と、申し込みページへの導線だけを持つ。"""

    template_name = 'home/join.html'
    nav = 'join'


@method_decorator(login_not_required, name='dispatch')
class JoinApplyView(NavMixin, FormView):
    """参加を申し込む。案内（/join/）とは別ページにして、フォームだけを置く。

    申し込みは DB に残さず、事務局（edit.Administrator）へのメールと申込者への
    自動返信で完結する（hirahira_room のお問い合わせと同じ作り）。
    """

    template_name = 'home/join_apply.html'
    nav = 'join'
    form_class = JoinForm
    #: 送信後はこのページに戻さず、完了ページへ送る（JoinDoneView の説明を参照）
    success_url = reverse_lazy('home:join_apply_done')

    def form_valid(self, form):
        detect_and_block_burst_submissions(self.request)

        try:
            form.send_email()
        except (smtplib.SMTPException, OSError, BadHeaderError):
            # SMTP の設定漏れや送信障害で 500 にせず、フォームに戻して知らせる。
            # BadHeaderError は氏名などに改行を入れられたときに出る（Django が
            # ヘッダインジェクションを阻止した結果）。これも 500 にしない。
            logger.exception('参加フォームのメール送信に失敗しました')
            form.add_error(None, 'メールの送信に失敗しました。'
                                 'お手数ですが時間をおいて再度お試しください。')
            return self.form_invalid(form)

        # 受付の知らせは完了ページ（JoinDoneView）に持たせているので、
        # ここでメッセージは出さない。
        #
        # 申込者のメールアドレスはログに残さない（ログの閲覧権限を持つ全員に
        # 個人情報が見えてしまうため）。内容はメールで事務局に届いている。
        logger.info('参加申し込みを受け付けました')
        return super().form_valid(form)


@method_decorator(login_not_required, name='dispatch')
class JoinDoneView(NavMixin, TemplateView):
    """申し込みの完了ページ。**フォームを置かないこと**が目的のページ。

    以前は送信後に申し込みページ自身へ戻していたが、それだと完了メッセージの下に
    空のフォームと「申し込む」ボタンが並ぶ。送れたのか分からず押し直した人は、
    detect_and_block_burst_submissions() の上限（settings.JOIN_BURST_RULES、
    既定で10分に3件）を超えて遮断されうる。大学の構内ネットワークは出口IPを
    共有しているため、巻き添えで同じ回線の他の人まで 403 になる。

    直接開かれることもある（ブックマーク・戻る操作）ので、申し込みの有無は問わず
    同じ内容を出す。個人情報は載せない。
    """

    template_name = 'home/join_done.html'
    nav = 'join'


@method_decorator(login_not_required, name='dispatch')
class ComingSoonView(NavMixin, TemplateView):
    """サブアプリ（WGごとのWebアプリ・成果物ページ）の作成中プレースホルダ。

    どこから来たかを ?from= で受け取り、戻るボタンを元の一覧に向ける。
    直接開かれたときや想定外の値のときは TOP に戻す。値は下の対応表に
    載っているものしか見ないので、任意の URL には飛ばせない。
    """

    template_name = 'home/coming_soon.html'
    nav = ''

    #: ?from= の値 -> (ボタンの文言, URL名, ナビの現在地)
    back_links = {
        'wg': ('WG一覧へ戻る', 'home:wg_list', 'wg'),
        'works': ('成果物へ戻る', 'home:work_list', 'works'),
    }
    default_back = ('TOPへ戻る', 'home:index', '')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        label, url_name, nav = self.back_links.get(
            self.request.GET.get('from'), self.default_back)
        context['back_label'] = label
        context['back_url'] = reverse(url_name)
        context['nav'] = nav
        return context
