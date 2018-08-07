# coding=utf-8
import traceback
import types
import datetime
import subprocess
import os
import operator

from func import enable_channel_wrapper, route_wrapper, register_route_function
from subzero.language import Language
from support.i18n import is_localized_string, _
from support.items import get_kind, get_item_thumb, get_item, get_item_kind_from_item, refresh_item
from support.helpers import get_video_display_title, pad_title, display_language, quote_args, is_stream_forced
from support.ignore import ignore_list
from support.lib import get_intent
from support.config import config
from subzero.constants import ICON_SUB, ICON
from support.plex_media import get_part, get_plex_metadata
from support.scheduler import scheduler
from support.scanning import scan_videos
from support.storage import save_subtitles

from subliminal_patch.subtitle import ModifiedSubtitle

default_thumb = R(ICON_SUB)
main_icon = ICON if not config.is_development else "icon-dev.jpg"

# noinspection PyUnboundLocalVariable
route = route_wrapper
# noinspection PyUnboundLocalVariable
handler = enable_channel_wrapper(handler)


def add_ignore_options(oc, kind, callback_menu=None, title=None, rating_key=None, add_kind=True):
    """

    :param oc: oc to add our options to
    :param kind: movie, show, episode ... - gets translated to the ignore key (sections, series, items)
    :param callback_menu: menu to inject
    :param title:
    :param rating_key:
    :return:
    """
    # try to translate kind to the ignore key
    use_kind = kind
    if kind not in ignore_list:
        use_kind = ignore_list.translate_key(kind)
    if not use_kind or use_kind not in ignore_list:
        return

    in_list = rating_key in ignore_list[use_kind]

    t = u"Ignore %(kind)s \"%(title)s\""
    if in_list:
        t = u"Un-ignore %(kind)s \"%(title)s\""

    oc.add(DirectoryObject(
        key=Callback(callback_menu, kind=use_kind, sure=False, todo="not_set", rating_key=rating_key, title=title),
        title=_(t,
                kind=ignore_list.verbose(kind) if add_kind else "",
                title=unicode(title))
    )
    )


def dig_tree(oc, items, menu_callback, menu_determination_callback=None, force_rating_key=None, fill_args=None,
             pass_kwargs=None, thumb=default_thumb):
    for kind, title, key, dig_deeper, item in items:
        thumb = get_item_thumb(item) or thumb

        add_kwargs = {}
        if fill_args:
            add_kwargs = dict((name, getattr(item, k)) for k, name in fill_args.iteritems() if item and hasattr(item, k))
        if pass_kwargs:
            add_kwargs.update(pass_kwargs)

        # force details view for show/season
        summary = " " if kind in ("show", "season") else None

        oc.add(DirectoryObject(
            key=Callback(menu_callback or menu_determination_callback(kind, item, pass_kwargs=pass_kwargs), title=title,
                         rating_key=force_rating_key or key, **add_kwargs),
            title=pad_title(title) if kind in ("show", "season") else title, thumb=thumb, summary=summary
        ))
    return oc


def set_refresh_menu_state(state_or_media, media_type="movies"):
    """

    :param state_or_media: string, None, or Media argument from Agent.update()
    :param media_type: movies or series
    :return:
    """
    if not state_or_media:
        # store it in last state and remove the current
        Dict["last_refresh_state"] = Dict["current_refresh_state"]
        Dict["current_refresh_state"] = None
        return

    if isinstance(state_or_media, types.StringTypes) or is_localized_string(state_or_media):
        Dict["current_refresh_state"] = unicode(state_or_media)
        return

    media = state_or_media
    media_id = media.id
    title = None
    if media_type == "series":
        for season in media.seasons:
            for episode in media.seasons[season].episodes:
                ep = media.seasons[season].episodes[episode]
                media_id = ep.id
                title = get_video_display_title(_("show"), ep.title, parent_title=media.title, season=int(season), episode=int(episode))
    else:
        title = get_video_display_title(_("movie"), media.title)

    intent = get_intent()
    force_refresh = intent.get("force", media_id)

    t = u"Refreshing %(title)s"
    if force_refresh:
        t = u"Force-refreshing %(title)s"

    Dict["current_refresh_state"] = unicode(_(t,
                                              title=unicode(title)))


def get_item_task_data(task_name, rating_key, language):
    task_data = scheduler.get_task_data(task_name)
    search_results = task_data.get(rating_key, {}) if task_data else {}
    return search_results.get(language)


def debounce(func):
    """
    prevent func from being called twice with the same arguments
    :param func:
    :return:
    """

    func.debounce = True

    return func


def extract_embedded_sub(**kwargs):
    rating_key = kwargs["rating_key"]
    part_id = kwargs.pop("part_id")
    stream_index = kwargs.pop("stream_index")
    with_mods = kwargs.pop("with_mods", False)
    language = Language.fromietf(kwargs.pop("language"))
    refresh = kwargs.pop("refresh", True)
    set_current = kwargs.pop("set_current", True)

    plex_item = kwargs.pop("plex_item", get_item(rating_key))
    item_type = get_item_kind_from_item(plex_item)
    part = kwargs.pop("part", get_part(plex_item, part_id))
    scanned_videos = kwargs.pop("scanned_videos", None)

    any_successful = False

    if part:
        if not scanned_videos:
            metadata = get_plex_metadata(rating_key, part_id, item_type, plex_item=plex_item)
            scanned_videos = scan_videos([metadata], ignore_all=True, skip_hashing=True)

        for stream in part.streams:
            # subtitle stream
            if str(stream.index) == stream_index:
                is_forced = is_stream_forced(stream)
                bn = os.path.basename(part.file)

                set_refresh_menu_state(_(u"Extracting subtitle %(stream_index)s of %(filename)s",
                                         stream_index=stream_index,
                                         filename=bn))
                Log.Info(u"Extracting stream %s (%s) of %s", stream_index, display_language(language), bn)

                out_codec = stream.codec if stream.codec != "mov_text" else "srt"

                args = [
                    config.plex_transcoder, "-i", part.file, "-map", "0:%s" % stream_index, "-f", out_codec, "-"
                ]
                output = None
                try:
                    output = subprocess.check_output(quote_args(args), stderr=subprocess.PIPE, shell=True)
                except:
                    Log.Error("Extraction failed: %s", traceback.format_exc())

                if output:
                    subtitle = ModifiedSubtitle(language, mods=config.default_mods if with_mods else None)
                    subtitle.content = output
                    subtitle.provider_name = "embedded"
                    subtitle.id = "stream_%s" % stream_index
                    subtitle.score = 0
                    subtitle.set_encoding("utf-8")

                    # fixme: speedup video; only video.name is needed
                    save_successful = save_subtitles(scanned_videos, {scanned_videos.keys()[0]: [subtitle]}, mode="m",
                                                     set_current=set_current, is_forced=is_forced)
                    set_refresh_menu_state(None)

                    if save_successful and refresh:
                        refresh_item(rating_key)

                    any_successful = True

    return any_successful


class SZObjectContainer(ObjectContainer):
    def __init__(self, *args, **kwargs):
        skip_pin_lock = kwargs.pop("skip_pin_lock", False)

        super(SZObjectContainer, self).__init__(*args, **kwargs)

        if (config.lock_menu or config.lock_advanced_menu) and not config.pin_correct and not skip_pin_lock:
            config.locked = True

    def add(self, *args, **kwargs):
        # disable self.add if we're in lockdown
        container = args[0]
        current_menu_target = container.key.split("?")[0]
        is_pin_menu = current_menu_target.endswith("/pin")

        if config.locked and config.lock_menu and not is_pin_menu:
            return
        return super(SZObjectContainer, self).add(*args, **kwargs)


OriginalObjectContainer = ObjectContainer
ObjectContainer = SZObjectContainer


class SubFolderObjectContainer(ObjectContainer):
    def __init__(self, *args, **kwargs):
        super(SubFolderObjectContainer, self).__init__(*args, **kwargs)
        from interface.menu import fatality
        from support.helpers import pad_title, timestamp
        self.add(DirectoryObject(
            key=Callback(fatality, force_title=" ", randomize=timestamp()),
            title=pad_title(_("<< Back to home")),
            summary=_("Current state: %s; Last state: %s",
                (Dict["current_refresh_state"] or _("Idle")) if "current_refresh_state" in Dict else _("Idle"),
                (Dict["last_refresh_state"] or _("None")) if "last_refresh_state" in Dict else _("None")
            )
        ))


ObjectClass = getattr(getattr(Redirect, "_object_class"), "__bases__")[0]


class ZipObject(ObjectClass):
    def __init__(self, data):
        ObjectClass.__init__(self, "")
        self.zipdata = data
        self.SetHeader("Content-Type", "application/zip")

    def Content(self):
        self.SetHeader("Content-Disposition",
                       'attachment; filename="' + datetime.datetime.now().strftime("Logs_%y%m%d_%H-%M-%S.zip")
                       + '"')
        return self.zipdata
