# wgjoin/http.py
#
# Google・GitHub の API を呼ぶための小さな HTTP の道具。標準ライブラリだけで書く。

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

TIMEOUT = 15


class ServiceError(Exception):
    """外部のサービスが使えなかった（通信の失敗・想定外の応答）。"""


def call(method, url, *, headers=None, json_body=None, form=None, params=None):
    """API を呼び、(ステータス, JSON の中身) を返す。

    4xx / 5xx も例外にせず返す（呼ぶ側がステータスで判断する）。
    通信できなかったときと、中身が JSON でないときは ServiceError。
    """
    if params:
        url = f'{url}?{urlencode(params)}'
    headers = {'Accept': 'application/json', **(headers or {})}
    data = None
    if json_body is not None:
        data = json.dumps(json_body).encode()
        headers['Content-Type'] = 'application/json'
    elif form is not None:
        data = urlencode(form).encode()
        headers['Content-Type'] = 'application/x-www-form-urlencoded'

    # 例外の文言（＝ログ）にはホスト名だけを出す。パスにユーザー名が入る API があるため。
    host = urlparse(url).netloc
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=TIMEOUT) as response:
            status, body = response.status, response.read()
    except HTTPError as e:
        status, body = e.code, e.read()
    except (URLError, TimeoutError, OSError) as e:
        raise ServiceError(f'{method} {host} に接続できませんでした') from e

    if not body:
        return status, {}
    try:
        return status, json.loads(body)
    except ValueError as e:
        raise ServiceError(f'{method} {host} の応答を読めませんでした（{status}）') from e
