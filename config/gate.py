# config/gate.py
#
# サブアプリ（works/ と wg/ の配下）は、ホームページの一覧から辿って使ってもらう。
# URL を直に開いた人は、そのアプリが載っている一覧へ送り返し、入口を funitclub に集める。
#
#   works/ 配下（公表した成果物）  → 成果物一覧 /works/ へ
#   wg/    配下（作っている途中）  → WG一覧 /wg/ へ
#
# しくみは通行証（署名付きの一時トークン）で、Referer は見ない。Referer は
# ブラウザや拡張機能に消されることがあり、偽装も簡単なので判定に使えない。
#
#   1. ホームページが一覧のリンクに ?from=<通行証> を付ける（link() で作る）
#   2. アプリの入口で検証し、通ったらセッションに印を付け、通行証を落とした
#      URL へ 1 回だけ転送する（アドレス欄にトークンを残さない）
#   3. 以後そのブラウザでは、リロードもアプリ内の移動も素通り
#   4. 印も通行証も無ければ一覧へリダイレクト（そこから入り直せる）
#
# 守りではなく導線の仕掛けである。一度入った人がその後どう使うかは縛らない。

from urllib.parse import urlsplit, urlunsplit

from django.core import signing
from django.shortcuts import redirect
from django.urls import reverse

SALT = 'app.gate'
PARAM = 'from'
SESSION_KEY = 'app_gate'


def _exempt(settings):
    return tuple(settings.GATE_EXEMPT)


def prefix_for(path, settings):
    """path が通行証の要るアプリなら、その接頭辞を返す。"""
    for prefix in settings.GATE_BACK:
        if path.startswith(prefix):
            return prefix
    return None


def is_exempt(path, settings):
    """別の鍵（署名付きリンク・ログイン・トークン）で守られている入口か。"""
    return path.startswith(_exempt(settings))


def make_token(prefix):
    return signing.dumps(prefix, salt=SALT)


def read_token(token, prefix, settings):
    """通行証がこのアプリのもので、期限内ならTrue。"""
    try:
        value = signing.loads(token, salt=SALT, max_age=settings.GATE_MAX_AGE)
    except signing.BadSignature:
        return False
    return value == prefix


def link(url, settings):
    """一覧に出すリンク。自サイトのサブアプリなら通行証を付ける。

    外部の URL や、通行証の要らない URL はそのまま返す。
    """
    parts = urlsplit(url)
    prefix = prefix_for(parts.path, settings)
    if not prefix or is_exempt(parts.path, settings):
        return url
    query = f'{PARAM}={make_token(prefix)}'
    return urlunsplit((parts.scheme, parts.netloc, parts.path,
                       f'{parts.query}&{query}' if parts.query else query, parts.fragment))


class GateMiddleware:
    """サブアプリを、ホームページの一覧経由でだけ開けるようにする。"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.conf import settings

        path = request.path
        prefix = prefix_for(path, settings)
        # 通行証の要らないところ（ホームページ自身・編集画面・素通しの入口）。
        # 素通しでは印を付けない。メールのリンクを開いた人が、そのままアプリ全体に
        # 入れてしまわないようにするため。
        if not prefix or is_exempt(path, settings):
            return self.get_response(request)

        if prefix in request.session.get(SESSION_KEY, []):
            return self.get_response(request)

        token = request.GET.get(PARAM, '')
        if token and read_token(token, prefix, settings):
            passed = request.session.get(SESSION_KEY, [])
            request.session[SESSION_KEY] = [*passed, prefix]
            # 通行証を落とした URL へ転送する（共有・ブックマークされないように）
            query = request.GET.copy()
            query.pop(PARAM, None)
            rest = query.urlencode()
            return redirect(f'{path}?{rest}' if rest else path)

        return redirect(reverse(settings.GATE_BACK[prefix]))
