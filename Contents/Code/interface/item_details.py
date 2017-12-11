# coding=utf-8
import os
import subprocess
import traceback

from babelfish import Language

from babelfish import Language

from sub_mod import SubtitleModificationsMenu
from menu_helpers import debounce, SubFolderObjectContainer, default_thumb, add_ignore_options, get_item_task_data, \
    set_refresh_menu_state, route

from refresh_item import RefreshItem
from subliminal_patch.subtitle import ModifiedSubtitle
from subzero.constants import PREFIX
from support.config import config
from support.helpers import timestamp, df, get_language, display_language, quote_args
from support.items import get_item_kind_from_rating_key, get_item, get_current_sub, get_item_title, refresh_item
from support.plex_media import get_plex_metadata
from support.scanning import scan_videos
from support.scheduler import scheduler
from support.storage import get_subtitle_storage, save_subtitles_to_file


# fixme: needs kwargs cleanup

@route(PREFIX + '/item/{rating_key}/actions')
@debounce
def ItemDetailsMenu(rating_key, title=None, base_title=None, item_title=None, randomize=None):
    """
    displays the item details menu of an item that doesn't contain any deeper tree, such as a movie or an episode
    :param rating_key:
    :param title:
    :param base_title:
    :param item_title:
    :param randomize:
    :return:
    """
    from interface.main import IgnoreMenu

    title = unicode(base_title) + " > " + unicode(title) if base_title else unicode(title)
    item = plex_item = get_item(rating_key)
    current_kind = get_item_kind_from_rating_key(rating_key)

    timeout = 30

    oc = SubFolderObjectContainer(title2=title, replace_parent=True)

    if not item:
        oc.add(DirectoryObject(
            key=Callback(ItemDetailsMenu, rating_key=rating_key, title=title, base_title=base_title,
                         item_title=item_title, randomize=timestamp()),
            title=u"Item not found: %s!" % item_title,
            summary="Plex didn't return any information about the item, please refresh it and come back later",
            thumb=default_thumb
        ))
        return oc

    # add back to season for episode
    if current_kind == "episode":
        from interface.menu import MetadataMenu
        show = get_item(item.show.rating_key)
        season = get_item(item.season.rating_key)

        oc.add(DirectoryObject(
            key=Callback(MetadataMenu, rating_key=season.rating_key, title=season.title, base_title=show.title,
                         previous_item_type="show", previous_rating_key=show.rating_key,
                         display_items=True, randomize=timestamp()),
            title=u"< Back to %s" % season.title,
            summary="Back to %s > %s" % (show.title, season.title),
            thumb=season.thumb or default_thumb
        ))

    oc.add(DirectoryObject(
        key=Callback(RefreshItem, rating_key=rating_key, item_title=item_title, randomize=timestamp(),
                     timeout=timeout * 1000),
        title=u"Refresh: %s" % item_title,
        summary="Refreshes the %s, possibly searching for missing and picking up new subtitles on disk" % current_kind,
        thumb=item.thumb or default_thumb
    ))
    oc.add(DirectoryObject(
        key=Callback(RefreshItem, rating_key=rating_key, item_title=item_title, force=True, randomize=timestamp(),
                     timeout=timeout * 1000),
        title=u"Force-find subtitles: %s" % item_title,
        summary="Issues a forced refresh, ignoring known subtitles and searching for new ones",
        thumb=item.thumb or default_thumb
    ))

    # get stored subtitle info for item id
    subtitle_storage = get_subtitle_storage()
    stored_subs = subtitle_storage.load_or_new(item)

    # look for subtitles for all available media parts and all of their languages
    has_multiple_parts = len(plex_item.media) > 1
    part_index = 0
    for media in plex_item.media:
        for part in media.parts:
            filename = os.path.basename(part.file)
            if not os.path.exists(part.file):
                continue

            part_id = str(part.id)
            part_index += 1

            part_index_addon = ""
            part_summary_addon = ""
            if has_multiple_parts:
                part_index_addon = u"File %s: " % part_index
                part_summary_addon = "%s " % filename

            if config.plex_transcoder:
                # embedded subtitles
                embedded_count = 0
                embedded_langs = []
                for stream in part.streams:
                    # subtitle stream
                    if stream.stream_type == 3 and not stream.stream_key and stream.codec == "srt": #("srt", "ass", "ssa"):
                        embedded_langs.append(Language.fromietf(stream.language_code))
                        embedded_count += 1

                if embedded_count:
                    oc.add(DirectoryObject(
                        key=Callback(ListEmbeddedSubsForItemMenu, rating_key=rating_key, part_id=part_id, title=title,
                                     item_type=plex_item.type, item_title=item_title, base_title=base_title,
                                     randomize=timestamp()),
                        title=u"%sEmbedded subtitles (%s)" % (part_index_addon, ", ".join(display_language(l) for l in
                                                                                          embedded_langs)),
                        summary=u"Manage (extract) embedded subtitle streams"
                    ))

            # iterate through all configured languages
            for lang in config.lang_list:
                # get corresponding stored subtitle data for that media part (physical media item), for language
                current_sub = stored_subs.get_any(part_id, lang)
                current_sub_id = None
                current_sub_provider_name = None

                summary = u"%sNo current subtitle in storage" % part_summary_addon
                current_score = None
                if current_sub:
                    current_sub_id = current_sub.id
                    current_sub_provider_name = current_sub.provider_name
                    current_score = current_sub.score

                    summary = u"%sCurrent subtitle: %s (added: %s, %s), Language: %s, Score: %i, Storage: %s" % \
                              (part_summary_addon, current_sub.provider_name, df(current_sub.date_added),
                               current_sub.mode_verbose, display_language(lang), current_sub.score,
                               current_sub.storage_type)

                    oc.add(DirectoryObject(
                        key=Callback(SubtitleOptionsMenu, rating_key=rating_key, part_id=part_id, title=title,
                                     item_title=item_title, language=lang, language_name=display_language(lang),
                                     current_id=current_sub_id,
                                     item_type=plex_item.type, filename=filename, current_data=summary,
                                     randomize=timestamp(), current_provider=current_sub_provider_name,
                                     current_score=current_score),
                        title=u"%sActions for %s subtitle" % (part_index_addon, display_language(lang)),
                        summary=summary
                    ))
                else:
                    oc.add(DirectoryObject(
                        key=Callback(ListAvailableSubsForItemMenu, rating_key=rating_key, part_id=part_id, title=title,
                                     item_title=item_title, language=lang, language_name=display_language(lang),
                                     current_id=current_sub_id,
                                     item_type=plex_item.type, filename=filename, current_data=summary,
                                     randomize=timestamp(), current_provider=current_sub_provider_name,
                                     current_score=current_score),
                        title=u"%sList %s subtitles" % (part_index_addon, display_language(lang)),
                        summary=summary
                    ))

    add_ignore_options(oc, "videos", title=item_title, rating_key=rating_key, callback_menu=IgnoreMenu)
    subtitle_storage.destroy()

    return oc


@route(PREFIX + '/item/current_sub/{rating_key}/{part_id}')
@debounce
def SubtitleOptionsMenu(**kwargs):
    oc = SubFolderObjectContainer(title2=unicode(kwargs["title"]), replace_parent=True)
    rating_key = kwargs["rating_key"]
    part_id = kwargs["part_id"]
    language = kwargs["language"]
    current_data = kwargs["current_data"]

    current_sub, stored_subs, storage = get_current_sub(rating_key, part_id, language)
    kwargs.pop("randomize")

    oc.add(DirectoryObject(
        key=Callback(ItemDetailsMenu, rating_key=kwargs["rating_key"], item_title=kwargs["item_title"],
                     title=kwargs["title"], randomize=timestamp()),
        title=u"< Back to %s" % kwargs["title"],
        summary=kwargs["current_data"],
        thumb=default_thumb
    ))
    oc.add(DirectoryObject(
        key=Callback(ListAvailableSubsForItemMenu, randomize=timestamp(), **kwargs),
        title=u"List %s subtitles" % kwargs["language_name"],
        summary=kwargs["current_data"]
    ))
    if current_sub:
        oc.add(DirectoryObject(
            key=Callback(SubtitleModificationsMenu, randomize=timestamp(), **kwargs),
            title=u"Modify %s subtitle" % kwargs["language_name"],
            summary=u"Currently applied mods: %s" % (", ".join(current_sub.mods) if current_sub.mods else "none")
        ))

        oc.add(DirectoryObject(
            key=Callback(BlacklistSubtitleMenu, randomize=timestamp(), **kwargs),
            title=u"Blacklist %s subtitle and search for a new one" % kwargs["language_name"],
            summary=current_data
        ))

        current_bl, subs = stored_subs.get_blacklist(part_id, language)
        if current_bl:
            oc.add(DirectoryObject(
                key=Callback(ManageBlacklistMenu, randomize=timestamp(), **kwargs),
                title=u"Manage blacklist (%s contained)" % len(current_bl),
                summary=u"Inspect currently blacklisted subtitles"
            ))

    storage.destroy()
    return oc


@route(PREFIX + '/item/blacklist_recent/{language}')
@route(PREFIX + '/item/blacklist_recent')
def BlacklistRecentSubtitleMenu(**kwargs):
    if "last_played_items" not in Dict or not Dict["last_played_items"]:
        return

    rating_key = Dict["last_played_items"][0]
    kwargs["rating_key"] = rating_key
    return BlacklistAllPartsSubtitleMenu(**kwargs)


@route(PREFIX + '/item/blacklist_all/{rating_key}/{language}')
@route(PREFIX + '/item/blacklist_all/{rating_key}')
def BlacklistAllPartsSubtitleMenu(**kwargs):
    rating_key = kwargs.get("rating_key")
    language = kwargs.get("language")
    if language:
        language = Language.fromietf(language)

    item = get_item(rating_key)

    if not item:
        return

    item_title = get_item_title(item)

    subtitle_storage = get_subtitle_storage()
    stored_subs = subtitle_storage.load_or_new(item)
    for part_id, languages in stored_subs.parts.iteritems():
        sub_dict = languages
        if language:
            key = str(language)
            if key not in sub_dict:
                continue

            sub_dict = {key: sub_dict[key]}

        for language, subs in sub_dict.iteritems():
            if "current" in subs:
                stored_subs.blacklist(part_id, language, subs["current"])
                Log.Info("Added %s to blacklist", subs["current"])

    subtitle_storage.save(stored_subs)
    subtitle_storage.destroy()

    return RefreshItem(rating_key=rating_key, item_title=item_title, force=True, randomize=timestamp(), timeout=30000)


def blacklist(rating_key, part_id, language):
    current_sub, stored_subs, storage = get_current_sub(rating_key, part_id, language)
    if not current_sub:
        return

    stored_subs.blacklist(part_id, language, current_sub.key)
    storage.save(stored_subs)
    storage.destroy()

    Log.Info("Added %s to blacklist", current_sub.key)

    return True


@route(PREFIX + '/item/blacklist/{rating_key}/{part_id}')
@debounce
def BlacklistSubtitleMenu(**kwargs):
    rating_key = kwargs["rating_key"]
    part_id = kwargs["part_id"]
    language = kwargs["language"]
    item_title = kwargs["item_title"]

    blacklist(rating_key, part_id, language)
    kwargs.pop("randomize")

    return RefreshItem(rating_key=rating_key, item_title=item_title, force=True, randomize=timestamp(), timeout=30000)


@route(PREFIX + '/item/manage_blacklist/{rating_key}/{part_id}', force=bool)
@debounce
def ManageBlacklistMenu(**kwargs):
    oc = SubFolderObjectContainer(title2=unicode(kwargs["title"]), replace_parent=True)
    rating_key = kwargs["rating_key"]
    part_id = kwargs["part_id"]
    language = kwargs["language"]
    remove_sub_key = kwargs.pop("remove_sub_key", None)

    current_sub, stored_subs, storage = get_current_sub(rating_key, part_id, language)
    current_bl, subs = stored_subs.get_blacklist(part_id, language)

    if remove_sub_key:
        remove_sub_key = tuple(remove_sub_key.split("__"))
        stored_subs.blacklist(part_id, language, remove_sub_key, add=False)
        storage.save(stored_subs)
        Log.Info("Removed %s from blacklist", remove_sub_key)

    kwargs.pop("randomize")

    oc.add(DirectoryObject(
        key=Callback(ItemDetailsMenu, rating_key=kwargs["rating_key"], item_title=kwargs["item_title"],
                     title=kwargs["title"], randomize=timestamp()),
        title=u"< Back to %s" % kwargs["title"],
        summary=kwargs["current_data"],
        thumb=default_thumb
    ))

    def sorter(pair):
        # thanks RestrictedModule parser for messing with lambda (x, y)
        return pair[1]["date_added"]

    for sub_key, data in sorted(current_bl.iteritems(), key=sorter, reverse=True):
        provider_name, subtitle_id = sub_key
        title = u"%s, %s (added: %s, %s), Language: " \
                u"%s, Score: %i, Storage: %s" % (provider_name, subtitle_id, df(data["date_added"]),
                                                 current_sub.get_mode_verbose(data["mode"]),
                                                 display_language(Language.fromietf(language)), data["score"],
                                                 data["storage_type"])
        oc.add(DirectoryObject(
            key=Callback(ManageBlacklistMenu, remove_sub_key="__".join(sub_key), randomize=timestamp(), **kwargs),
            title=title,
            summary=u"Remove subtitle from blacklist"
        ))

    storage.destroy()

    return oc


@route(PREFIX + '/item/search/{rating_key}/{part_id}', force=bool)
@debounce
def ListAvailableSubsForItemMenu(rating_key=None, part_id=None, title=None, item_title=None, filename=None,
                                 item_type="episode", language=None, language_name=None, force=False, current_id=None,
                                 current_data=None,
                                 current_provider=None, current_score=None, randomize=None):
    assert rating_key, part_id

    running = scheduler.is_task_running("AvailableSubsForItem")
    search_results = get_item_task_data("AvailableSubsForItem", rating_key, language)

    if (search_results is None or force) and not running:
        scheduler.dispatch_task("AvailableSubsForItem", rating_key=rating_key, item_type=item_type, part_id=part_id,
                                language=language)
        running = True

    oc = SubFolderObjectContainer(title2=unicode(title), replace_parent=True)
    oc.add(DirectoryObject(
        key=Callback(ItemDetailsMenu, rating_key=rating_key, item_title=item_title, title=title, randomize=timestamp()),
        title=u"< Back to %s" % title,
        summary=current_data,
        thumb=default_thumb
    ))

    metadata = get_plex_metadata(rating_key, part_id, item_type)
    plex_part = None
    if not config.low_impact_mode:
        scanned_parts = scan_videos([metadata], kind="series" if item_type == "episode" else "movie", ignore_all=True)

        if not scanned_parts:
            Log.Error("Couldn't list available subtitles for %s", rating_key)
            return oc

        video, plex_part = scanned_parts.items()[0]

        video_display_data = [video.format] if video.format else []
        if video.release_group:
            video_display_data.append(u"by %s" % video.release_group)
        video_display_data = " ".join(video_display_data)
    else:
        video_display_data = metadata["filename"]

    current_display = (u"Current: %s (%s) " % (current_provider, current_score) if current_provider else "")
    if not running:
        oc.add(DirectoryObject(
            key=Callback(ListAvailableSubsForItemMenu, rating_key=rating_key, item_title=item_title, language=language,
                         filename=filename, part_id=part_id, title=title, current_id=current_id, force=True,
                         current_provider=current_provider, current_score=current_score,
                         current_data=current_data, item_type=item_type, randomize=timestamp()),
            title=u"Search for %s subs (%s)" % (get_language(language).name, video_display_data),
            summary=u"%sFilename: %s" % (current_display, filename),
            thumb=default_thumb
        ))

        if search_results == "found_none":
            oc.add(DirectoryObject(
                key=Callback(ListAvailableSubsForItemMenu, rating_key=rating_key, item_title=item_title,
                             language=language, filename=filename, current_data=current_data, force=True,
                             part_id=part_id, title=title, current_id=current_id, item_type=item_type,
                             current_provider=current_provider, current_score=current_score,
                             randomize=timestamp()),
                title=u"No subtitles found",
                summary=u"%sFilename: %s" % (current_display, filename),
                thumb=default_thumb
            ))
    else:
        oc.add(DirectoryObject(
            key=Callback(ListAvailableSubsForItemMenu, rating_key=rating_key, item_title=item_title,
                         language=language, filename=filename, current_data=current_data,
                         part_id=part_id, title=title, current_id=current_id, item_type=item_type,
                         current_provider=current_provider, current_score=current_score,
                         randomize=timestamp()),
            title=u"Searching for %s subs (%s), refresh here ..." % (display_language(get_language(language)),
                                                                     video_display_data),
            summary=u"%sFilename: %s" % (current_display, filename),
            thumb=default_thumb
        ))

    if not search_results or search_results == "found_none":
        return oc

    current_sub, stored_subs, storage = get_current_sub(rating_key, part_id, language)
    current_bl, subs = stored_subs.get_blacklist(part_id, language)

    seen = []
    for subtitle in search_results:
        if subtitle.id in seen:
            continue

        bl_addon = ""
        if (str(subtitle.provider_name), str(subtitle.id)) in current_bl:
            bl_addon = "Blacklisted "

        wrong_fps_addon = ""
        if subtitle.wrong_fps:
            if plex_part:
                wrong_fps_addon = " (wrong FPS, sub: %s, media: %s)" % (subtitle.fps, plex_part.fps)
            else:
                wrong_fps_addon = " (wrong FPS, sub: %s, media: unknown, low impact mode)" % subtitle.fps

        oc.add(DirectoryObject(
            key=Callback(TriggerDownloadSubtitle, rating_key=rating_key, randomize=timestamp(), item_title=item_title,
                         subtitle_id=str(subtitle.id), language=language),
            title=u"%s%s: %s, score: %s%s" % (bl_addon, "Available" if current_id != subtitle.id else "Current",
                                              subtitle.provider_name, subtitle.score, wrong_fps_addon),
            summary=u"Release: %s, Matches: %s" % (subtitle.release_info, ", ".join(subtitle.matches)),
            thumb=default_thumb
        ))

        seen.append(subtitle.id)

    return oc


@route(PREFIX + '/download_subtitle/{rating_key}')
@debounce
def TriggerDownloadSubtitle(rating_key=None, subtitle_id=None, item_title=None, language=None, randomize=None):
    from interface.main import fatality

    set_refresh_menu_state("Downloading subtitle for %s" % item_title or rating_key)
    search_results = get_item_task_data("AvailableSubsForItem", rating_key, language)

    download_subtitle = None
    for subtitle in search_results:
        if str(subtitle.id) == subtitle_id:
            download_subtitle = subtitle
            break
    if not download_subtitle:
        Log.Error(u"Something went horribly wrong")

    else:
        scheduler.dispatch_task("DownloadSubtitleForItem", rating_key=rating_key, subtitle=download_subtitle)

    scheduler.clear_task_data("AvailableSubsForItem")

    return fatality(randomize=timestamp(), header=" ", replace_parent=True)


def get_part(plex_item, part_id):
    for media in plex_item.media:
        for part in media.parts:
            if part_id == str(part.id):
                return part


@route(PREFIX + '/item/embedded/{rating_key}/{part_id}')
def ListEmbeddedSubsForItemMenu(**kwargs):
    rating_key = kwargs["rating_key"]
    part_id = kwargs["part_id"]
    title = kwargs["title"]
    kwargs.pop("randomize")

    oc = SubFolderObjectContainer(title2=title, replace_parent=True)

    oc.add(DirectoryObject(
        key=Callback(ItemDetailsMenu, rating_key=kwargs["rating_key"], item_title=kwargs["item_title"],
                     base_title=kwargs["base_title"], title=kwargs["item_title"], randomize=timestamp()),
        title=u"< Back to %s" % kwargs["title"],
        thumb=default_thumb
    ))

    plex_item = get_item(rating_key)
    part = get_part(plex_item, part_id)

    if part:
        for stream in part.streams:
            # subtitle stream
            if stream.stream_type == 3 and not stream.stream_key and stream.codec in ("srt", "ass", "ssa"):
                lang_code = stream.language_code
                language = Language.fromietf(lang_code)
                forced = stream.forced
                oc.add(DirectoryObject(
                    key=Callback(ExtractEmbeddedSubForItemMenu, randomize=timestamp(), stream_index=str(stream.index),
                                 with_mods=True, **kwargs),
                    title=u"Extract stream %s, %s%s with default mods" % (stream.index, display_language(language),
                                                                          " (forced)" if forced else ""),
                ))
                oc.add(DirectoryObject(
                    key=Callback(ExtractEmbeddedSubForItemMenu, randomize=timestamp(), stream_index=str(stream.index),
                                 **kwargs),
                    title=u"Extract stream %s, %s%s" % (stream.index, display_language(language),
                                                        " (forced)" if forced else ""),
                ))
    return oc


@route(PREFIX + '/item/extract_embedded/{rating_key}/{part_id}/{stream_index}')
@debounce
def ExtractEmbeddedSubForItemMenu(**kwargs):
    rating_key = kwargs["rating_key"]
    part_id = kwargs.pop("part_id")
    stream_index = kwargs.pop("stream_index")
    item_type = kwargs.pop("item_type")
    with_mods = kwargs.pop("with_mods", False)

    plex_item = get_item(rating_key)
    part = get_part(plex_item, part_id)

    if part:
        for stream in part.streams:
            # subtitle stream
            if str(stream.index) == stream_index:
                lang_code = stream.language_code
                language = Language.fromietf(lang_code)
                forced = stream.forced

                Log.Info(u"Extracting stream %s (%s) of %s", stream_index, display_language(language),
                         os.path.basename(part.file))

                args = [
                    config.plex_transcoder, "-i", part.file, "-map", "0:%s" % stream_index, "-f", "srt", "-"
                ]
                output = None
                try:
                    output = subprocess.check_output(quote_args(args), stderr=subprocess.PIPE, shell=True)
                except:
                    Log.Error("Extraction failed: %s", traceback.format_exc())

                if output:
                    subtitle = ModifiedSubtitle(language, mods=config.default_mods if with_mods else None)
                    subtitle.content = output
                    subtitle.set_encoding("utf-8")

                    # fixme: speedup video; only video.name is needed
                    save_subtitles_to_file({part.file: [subtitle]}, tags=["embedded"], forced_tag=forced)
                    refresh_item(rating_key)

    kwargs.pop("randomize")
    kwargs["title"] = kwargs["item_title"]

    return ItemDetailsMenu(randomize=timestamp(), **kwargs)
