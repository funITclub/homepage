"""countdown の API。React の画面（frontend/countdown）が呼ぶ。

一覧の場所（ID の一覧 /countdown/<ID>/、共有ボード /countdown/events/）の下に api/ を置く。

    GET    <一覧>/api/          その置き場の予定・出来事（これからの予定／過ぎた出来事に分けて）
    POST   <一覧>/api/          登録
    GET    <一覧>/api/<番号>/   1件
    PATCH  <一覧>/api/<番号>/   更新（送った欄だけ書きかえる）
    DELETE <一覧>/api/<番号>/   削除

hirahira_room の countdown の API（DRF）と同じ形の JSON を返す。こちらには DRF が無いので、
Django のビューで書き、入力の確かめは画面のころと同じ CountEventForm に任せる
（欄ごとのメッセージの形 {欄: [メッセージ]} も DRF と同じにしてある）。

ログインはない。置き場は URL の ID で決まり（BoardMixin）、ほかの置き場のものは番号を
言い当てても「無い」（404）と答える。書き込みには CSRF トークンが要る
（入れ物のページ AppView が ensure_csrf_cookie で Cookie を配る）。
"""

import json
import logging

from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views import View

from .forms import CountEventForm
from .models import CountEvent
from .views import BoardMixin

logger = logging.getLogger(__name__)

# 画面から書きかえられる欄
FIELDS = ('name', 'date', 'memo', 'notify')


def event_json(event):
    """1件。日数の計算は画面（derive.ts）がサーバーの today を使ってする。"""
    return {
        'id': event.pk,
        'name': event.name,
        'date': event.date.isoformat(),
        'memo': event.memo,
        # 共有ボードでは通知を使わない
        'notify': bool(event.board_id and event.notify),
        # 画面のリング（登録した日から当日までの進み具合）に使う。日本時間で返す
        'created_at': timezone.localtime(event.created_at).isoformat(),
    }


def read_body(request):
    """JSON の本文を読む。読めなければ None。"""
    try:
        data = json.loads(request.body or b'{}')
    except (ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def bad_body():
    return JsonResponse({'detail': '送られた内容を読めませんでした。'}, status=400)


class ApiView(BoardMixin, View):
    """API の共通部分。置き場は BoardMixin が URL から決める。"""

    def save(self, data, instance=None, status=200):
        """欄を CountEventForm で確かめて保存する。まちがいは 400 と {欄: [メッセージ]}。"""
        if instance is not None:
            # PATCH は送った欄だけを書きかえる。送らなかった欄は今の値で埋める
            current = {
                'name': instance.name, 'date': instance.date.isoformat(),
                'memo': instance.memo, 'notify': instance.notify,
            }
            data = {**current, **{k: v for k, v in data.items() if k in FIELDS}}
        if 'notify' in data:
            # チェックボックスの Form は、値があるかで真偽を見る。false を送ったら外す
            data = {**data, 'notify': 'on' if data['notify'] is True else ''}
        form = CountEventForm(data, instance=instance, board=self.board)
        if not form.is_valid():
            return JsonResponse(
                {field: list(messages) for field, messages in form.errors.items()}, status=400)
        form.instance.board = self.board
        event = form.save()
        return JsonResponse(event_json(event), status=status)


class EventsAPI(ApiView):
    """一覧と登録。"""

    http_method_names = ['get', 'post']

    def get(self, request, *args, **kwargs):
        """並べ方もここで決める（これからの予定は近い順、過ぎた出来事は新しい順）。

        today は「今日」をブラウザの時計ではなくサーバーにそろえるために使う。
        """
        today = timezone.localdate()
        events = list(self.get_queryset())
        upcoming = sorted((e for e in events if e.date >= today), key=lambda e: e.date)
        past = sorted((e for e in events if e.date < today), key=lambda e: e.date, reverse=True)
        return JsonResponse({
            'today': today.isoformat(),
            'upcoming': [event_json(e) for e in upcoming],
            'past': [event_json(e) for e in past],
        })

    def post(self, request, *args, **kwargs):
        data = read_body(request)
        if data is None:
            return bad_body()
        return self.save(data, status=201)


class EventAPI(ApiView):
    """1件の読み出し・書きかえ・削除。"""

    http_method_names = ['get', 'patch', 'delete']

    def get_object(self):
        return get_object_or_404(self.get_queryset(), pk=self.kwargs['pk'])

    def get(self, request, *args, **kwargs):
        return JsonResponse(event_json(self.get_object()))

    def patch(self, request, *args, **kwargs):
        event = self.get_object()
        data = read_body(request)
        if data is None:
            return bad_body()
        return self.save(data, instance=event)

    def delete(self, request, *args, **kwargs):
        self.get_object().delete()
        return HttpResponse(status=204)
