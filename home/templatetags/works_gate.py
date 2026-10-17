# home/templatetags/works_gate.py
#
# 一覧のリンクに、成果物のアプリの通行証を付けるフィルタ（works/gate.py）。
# 外部の URL や通行証の要らない URL は、そのまま返る。

from django import template
from django.conf import settings

from works import gate

register = template.Library()


@register.filter
def works_link(url):
    return gate.link(url, settings)
