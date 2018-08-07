# coding=utf-8

from subzero.constants import PREFIX
from menu_helpers import debounce, set_refresh_menu_state, route
from support.items import refresh_item
from support.helpers import timestamp
from support.i18n import _


@route(PREFIX + '/item/refresh/{rating_key}/force', force=True)
@route(PREFIX + '/item/refresh/{rating_key}')
@debounce
def RefreshItem(rating_key=None, came_from="/recent", item_title=None, force=False, refresh_kind=None,
                previous_rating_key=None, timeout=8000, randomize=None, trigger=True):
    assert rating_key
    from interface.main import fatality
    header = " "
    if trigger:
        t = u"Triggering refresh for %(title)s"
        if force:
            u"Triggering forced refresh for %(title)s"
        set_refresh_menu_state(_(t,
                                 title=item_title))
        Thread.Create(refresh_item, rating_key=rating_key, force=force, refresh_kind=refresh_kind,
                      parent_rating_key=previous_rating_key, timeout=int(timeout))

        t = u"Refresh of item %(item_id)s triggered"
        if force:
            t = u"Forced refresh of item %(item_id)s triggered"
        header = _(t,
                   item_id=rating_key)
    return fatality(randomize=timestamp(), header=header, replace_parent=True)
