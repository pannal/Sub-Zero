# coding=utf-8
import logging

import datetime

import logger
import os

from menu_helpers import add_ignore_options, dig_tree, set_refresh_menu_state, \
    should_display_ignore, enable_channel_wrapper, default_thumb, debounce, ObjectContainer, SubFolderObjectContainer
from subzero.constants import TITLE, ART, ICON, PREFIX, PLUGIN_IDENTIFIER, DEPENDENCY_MODULE_NAMES
from subzero.history_storage import mode_map
from support.background import scheduler
from support.config import config
from support.helpers import pad_title, timestamp, get_language, df, cast_bool
from support.ignore import ignore_list
from support.items import get_item, get_on_deck_items, refresh_item, get_all_items, get_items_info, \
    get_item_thumb, get_item_kind_from_rating_key
from support.lib import Plex
from support.missing_subtitles import items_get_all_missing_subs
from support.plex_media import get_plex_metadata, scan_videos
from support.storage import reset_storage, log_storage, get_subtitle_info

# init GUI
ObjectContainer.art = R(ART)
ObjectContainer.no_cache = True

# default thumb for DirectoryObjects
DirectoryObject.thumb = default_thumb


# noinspection PyUnboundLocalVariable
route = enable_channel_wrapper(route)
# noinspection PyUnboundLocalVariable
handler = enable_channel_wrapper(handler)


@handler(PREFIX, TITLE, art=ART, thumb=ICON)
@route(PREFIX)
def fatality(randomize=None, force_title=None, header=None, message=None, only_refresh=False, no_history=False, replace_parent=False):
    """
    subzero main menu
    """
    title = config.full_version#force_title if force_title is not None else config.full_version
    oc = ObjectContainer(title1=title, title2=title, header=unicode(header) if header else title, message=message, no_history=no_history,
                         replace_parent=replace_parent, no_cache=True)

    # always re-check permissions
    config.refresh_permissions_status()

    # always re-check enabled sections
    config.refresh_enabled_sections()

    if config.lock_menu and not config.pin_correct:
        oc.add(DirectoryObject(
            key=Callback(PinMenu, randomize=timestamp()),
            title=pad_title("Enter PIN"),
            summary="The owner has restricted the access to this menu. Please enter the correct pin",
        ))
        return oc

    if not config.permissions_ok and config.missing_permissions:
        for title, path in config.missing_permissions:
            oc.add(DirectoryObject(
                key=Callback(fatality, randomize=timestamp()),
                title=pad_title("Insufficient permissions"),
                summary="Insufficient permissions on library %s, folder: %s" % (title, path),
            ))
        return oc

    if not config.enabled_sections:
        oc.add(DirectoryObject(
            key=Callback(fatality, randomize=timestamp()),
            title=pad_title("I'm not enabled!"),
            summary="Please enable me for some of your libraries in your server settings; currently I do nothing",
        ))
        return oc

    if not only_refresh:
        if Dict["current_refresh_state"]:
            oc.add(DirectoryObject(
                key=Callback(fatality, force_title=" ", randomize=timestamp()),
                title=pad_title("Working ... refresh here"),
                summary="Current state: %s; Last state: %s" % (
                    (Dict["current_refresh_state"] or "Idle") if "current_refresh_state" in Dict else "Idle",
                    (Dict["last_refresh_state"] or "None") if "last_refresh_state" in Dict else "None"
                )
            ))

        oc.add(DirectoryObject(
            key=Callback(OnDeckMenu),
            title="On Deck items",
            summary="Shows the current on deck items and allows you to individually (force-) refresh their metadata/"
                    "subtitles."
        ))
        oc.add(DirectoryObject(
            key=Callback(RecentlyAddedMenu),
            title="Recently Added items",
            summary="Shows the recently added items per section."
        ))
        oc.add(DirectoryObject(
            key=Callback(RecentMissingSubtitlesMenu, randomize=timestamp()),
            title="Items with missing subtitles",
            summary="Shows the items honoring the configured 'Item age to be considered recent'-setting (%s)"
                    " and allowing you to individually (force-) refresh their metadata/subtitles. " %
                    Prefs["scheduler.item_is_recent_age"]
        ))
        oc.add(DirectoryObject(
            key=Callback(SectionsMenu),
            title="Browse all items",
            summary="Go through your whole library and manage your ignore list. You can also "
                    "(force-) refresh the metadata/subtitles of individual items."
        ))

        task_name = "SearchAllRecentlyAddedMissing"
        task = scheduler.task(task_name)

        if task.ready_for_display:
            task_state = "Running: %s/%s (%s%%)" % (len(task.items_done), len(task.items_searching), task.percentage)
        else:
            task_state = "Last scheduler run: %s; Next scheduled run: %s; Last runtime: %s" % (df(scheduler.last_run(task_name)) or "never",
                                                                                               df(scheduler.next_run(task_name)) or "never",
                                                                                               str(task.last_run_time).split(".")[0])

        oc.add(DirectoryObject(
            key=Callback(RefreshMissing, randomize=timestamp()),
            title="Search for missing subtitles (in recently-added items, max-age: %s)" % Prefs["scheduler.item_is_recent_age"],
            summary="Automatically run periodically by the scheduler, if configured. %s" % task_state
        ))

        oc.add(DirectoryObject(
            key=Callback(IgnoreListMenu),
            title="Display ignore list (%d)" % len(ignore_list),
            summary="Show the current ignore list (mainly used for the automatic tasks)"
        ))

        oc.add(DirectoryObject(
            key=Callback(HistoryMenu),
            title="History",
            summary="Show the last %i downloaded subtitles" % int(Prefs["history_size"])
        ))

    oc.add(DirectoryObject(
        key=Callback(fatality, force_title=" ", randomize=timestamp()),
        title=pad_title("Refresh"),
        summary="Current state: %s; Last state: %s" % (
            (Dict["current_refresh_state"] or "Idle") if "current_refresh_state" in Dict else "Idle",
            (Dict["last_refresh_state"] or "None") if "last_refresh_state" in Dict else "None"
        )
    ))

    # add re-lock after pin unlock
    if config.pin:
        oc.add(DirectoryObject(
            key=Callback(ClearPin, randomize=timestamp()),
            title=pad_title("Re-lock menu(s)"),
            summary="Enabled the PIN again for menu(s)"
        ))

    if not only_refresh:
        oc.add(DirectoryObject(
            key=Callback(AdvancedMenu),
            title=pad_title("Advanced functions"),
            summary="Use at your own risk"
        ))

    return oc


@route(PREFIX + '/pin')
def PinMenu(pin="", randomize=None, success_go_to="channel"):
    oc = ObjectContainer(title2="Enter PIN number %s" % (len(pin) + 1), no_cache=True, no_history=True,
                         skip_pin_lock=True)

    if pin == config.pin:
        Dict["pin_correct_time"] = datetime.datetime.now()
        config.locked = False
        if success_go_to == "channel":
            return fatality(force_title="PIN correct", header="PIN correct", no_history=True)
        elif success_go_to == "advanced":
            return AdvancedMenu(randomize=timestamp())

    for i in range(10):
        oc.add(DirectoryObject(
            key=Callback(PinMenu, randomize=timestamp(), pin=pin + str(i),success_go_to=success_go_to),
            title=pad_title(str(i)),
        ))
    oc.add(DirectoryObject(
        key=Callback(PinMenu, randomize=timestamp(),success_go_to=success_go_to),
        title=pad_title("Reset"),
    ))
    return oc


@route(PREFIX + '/pin_lock')
def ClearPin(randomize=None):
    Dict["pin_correct_time"] = None
    config.locked = True
    return fatality(force_title="Menu locked", header=" ", no_history=True)


@route(PREFIX + '/on_deck')
def OnDeckMenu(message=None):
    """
    displays the items on deck
    :param message:
    :return:
    """
    return mergedItemsMenu(title="Items On Deck", base_title="Items On Deck", itemGetter=get_on_deck_items)


@route(PREFIX + '/recently_added')
def RecentlyAddedMenu(message=None):
    """
    displays the items recently added per section
    :param message:
    :return:
    """
    return SectionsMenu(base_title="Recently added", section_items_key="recently_added", ignore_options=False)


@route(PREFIX + '/recent', force=bool)
@debounce
def RecentMissingSubtitlesMenu(force=False, randomize=None):
    title="Items with missing subtitles"
    oc = SubFolderObjectContainer(title2=title, no_cache=True, no_history=True)

    running = scheduler.is_task_running("MissingSubtitles")
    task_data = scheduler.get_task_data("MissingSubtitles")
    missing_items = task_data["missing_subtitles"] if task_data else None

    if ((missing_items is None) or force) and not running:
        scheduler.dispatch_task("MissingSubtitles")
        running = True

    if not running:
        oc.add(DirectoryObject(
            key=Callback(RecentMissingSubtitlesMenu, force=True, randomize=timestamp()),
            title=u"Get items with missing subtitles",
            thumb=default_thumb
        ))
    else:
        oc.add(DirectoryObject(
            key=Callback(RecentMissingSubtitlesMenu, force=False, randomize=timestamp()),
            title=u"Updating, refresh here ...",
            thumb=default_thumb
        ))

    if missing_items is not None:
        for added_at, item_id, item_title, item, missing_languages in missing_items:
            oc.add(DirectoryObject(
                key=Callback(ItemDetailsMenu, title=title + " > " + item_title, item_title=item_title, rating_key=item_id),
                title=item_title,
                summary="Missing: %s" % ", ".join(l.name for l in missing_languages),
                thumb=get_item_thumb(item) or default_thumb
            ))

        scheduler.clear_task_data("MissingSubtitles")

    return oc


def mergedItemsMenu(title, itemGetter, itemGetterKwArgs=None, base_title=None, *args, **kwargs):
    """
    displays an item list of dynamic kinds of items
    :param title:
    :param itemGetter:
    :param itemGetterKwArgs:
    :param base_title:
    :param args:
    :param kwargs:
    :return:
    """
    oc = SubFolderObjectContainer(title2=title, no_cache=True, no_history=True)
    items = itemGetter(*args, **kwargs)

    for kind, title, item_id, deeper, item in items:
        oc.add(DirectoryObject(
            title=title,
            key=Callback(ItemDetailsMenu, title=base_title + " > " + title, item_title=title, rating_key=item_id),
            thumb=get_item_thumb(item) or default_thumb
        ))

    return oc


def determine_section_display(kind, item, pass_kwargs=None):
    """
    returns the menu function for a section based on the size of it (amount of items)
    :param kind:
    :param item:
    :return:
    """
    if pass_kwargs and pass_kwargs.get("section_items_key", "all") != "all":
        return SectionMenu
    if item.size > 80:
        return SectionFirstLetterMenu
    return SectionMenu


@route(PREFIX + '/ignore/set/{kind}/{rating_key}/{todo}/sure={sure}', kind=str, rating_key=str, todo=str, sure=bool)
def IgnoreMenu(kind, rating_key, title=None, sure=False, todo="not_set"):
    """
    displays the ignore options for a menu
    :param kind:
    :param rating_key:
    :param title:
    :param sure:
    :param todo:
    :return:
    """
    is_ignored = rating_key in ignore_list[kind]
    if not sure:
        oc = SubFolderObjectContainer(no_history=True, replace_parent=True, title1="%s %s %s %s the ignore list" % (
            "Add" if not is_ignored else "Remove", ignore_list.verbose(kind), title, "to" if not is_ignored else "from"), title2="Are you sure?")
        oc.add(DirectoryObject(
            key=Callback(IgnoreMenu, kind=kind, rating_key=rating_key, title=title, sure=True, todo="add" if not is_ignored else "remove"),
            title=pad_title("Are you sure?"),
        ))
        return oc

    rel = ignore_list[kind]
    dont_change = False
    if todo == "remove":
        if not is_ignored:
            dont_change = True
        else:
            rel.remove(rating_key)
            Log.Info("Removed %s (%s) from the ignore list", title, rating_key)
            ignore_list.remove_title(kind, rating_key)
            ignore_list.save()
            state = "removed from"
    elif todo == "add":
        if is_ignored:
            dont_change = True
        else:
            rel.append(rating_key)
            Log.Info("Added %s (%s) to the ignore list", title, rating_key)
            ignore_list.add_title(kind, rating_key, title)
            ignore_list.save()
            state = "added to"
    else:
        dont_change = True

    if dont_change:
        return fatality(force_title=" ", header="Didn't change the ignore list", no_history=True)

    return fatality(force_title=" ", header="%s %s the ignore list" % (title, state), no_history=True)


@route(PREFIX + '/sections')
def SectionsMenu(base_title="Sections", section_items_key="all", ignore_options=True):
    """
    displays the menu for all sections
    :return:
    """
    items = get_all_items("sections")

    return dig_tree(SubFolderObjectContainer(title2="Sections", no_cache=True, no_history=True), items, None,
                    menu_determination_callback=determine_section_display, pass_kwargs={"base_title": base_title,
                                                                                        "section_items_key": section_items_key,
                                                                                        "ignore_options": ignore_options},
                    fill_args={"title": "section_title"})


@route(PREFIX + '/section', ignore_options=bool)
def SectionMenu(rating_key, title=None, base_title=None, section_title=None, ignore_options=True,
                section_items_key="all"):
    """
    displays the contents of a section
    :param section_items_key:
    :param rating_key:
    :param title:
    :param base_title:
    :param section_title:
    :param ignore_options:
    :return:
    """
    items = get_all_items(key=section_items_key, value=rating_key, base="library/sections")

    kind, deeper = get_items_info(items)
    title = unicode(title)

    section_title = title
    title = base_title + " > " + title
    oc = SubFolderObjectContainer(title2=title, no_cache=True, no_history=True)
    if ignore_options:
        add_ignore_options(oc, "sections", title=section_title, rating_key=rating_key, callback_menu=IgnoreMenu)

    return dig_tree(oc, items, MetadataMenu,
                    pass_kwargs={"base_title": title, "display_items": deeper, "previous_item_type": "section",
                                 "previous_rating_key": rating_key})


@route(PREFIX + '/section/firstLetter', deeper=bool)
def SectionFirstLetterMenu(rating_key, title=None, base_title=None, section_title=None, ignore_options=True,
                           section_items_key="all"):
    """
    displays the contents of a section indexed by its first char (A-Z, 0-9...)
    :param ignore_options: ignored
    :param section_items_key: ignored
    :param rating_key:
    :param title:
    :param base_title:
    :param section_title:
    :return:
    """
    items = get_all_items(key="first_character", value=rating_key, base="library/sections")

    kind, deeper = get_items_info(items)

    title = unicode(title)
    oc = SubFolderObjectContainer(title2=section_title, no_cache=True, no_history=True)
    title = base_title + " > " + title
    add_ignore_options(oc, "sections", title=section_title, rating_key=rating_key, callback_menu=IgnoreMenu)

    oc.add(DirectoryObject(
        key=Callback(SectionMenu, title="All", base_title=title, rating_key=rating_key, ignore_options=False),
        title="All"
    )
    )
    return dig_tree(oc, items, FirstLetterMetadataMenu, force_rating_key=rating_key, fill_args={"key": "key"},
                    pass_kwargs={"base_title": title, "display_items": deeper, "previous_rating_key": rating_key})


@route(PREFIX + '/section/firstLetter/key', deeper=bool)
def FirstLetterMetadataMenu(rating_key, key, title=None, base_title=None, display_items=False, previous_item_type=None,
                            previous_rating_key=None):
    """
    displays the contents of a section filtered by the first letter
    :param rating_key: actually is the section's key
    :param key: the firstLetter wanted
    :param title: the first letter, or #
    :param deeper:
    :return:
    """
    title = base_title + " > " + unicode(title)
    oc = SubFolderObjectContainer(title2=title, no_cache=True, no_history=True)

    items = get_all_items(key="first_character", value=[rating_key, key], base="library/sections", flat=False)
    kind, deeper = get_items_info(items)
    dig_tree(oc, items, MetadataMenu,
             pass_kwargs={"base_title": title, "display_items": deeper, "previous_item_type": kind, "previous_rating_key": rating_key})
    return oc


@route(PREFIX + '/section/contents', display_items=bool)
def MetadataMenu(rating_key, title=None, base_title=None, display_items=False, previous_item_type=None,
                 previous_rating_key=None):
    """
    displays the contents of a section based on whether it has a deeper tree or not (movies->movie (item) list; series->series list)
    :param rating_key:
    :param title:
    :param base_title:
    :param display_items:
    :param previous_item_type:
    :param previous_rating_key:
    :return:
    """
    title = unicode(title)
    item_title = title
    title = base_title + " > " + title
    oc = SubFolderObjectContainer(title2=title, no_cache=True, no_history=True)

    current_kind = get_item_kind_from_rating_key(rating_key)

    if display_items:
        items = get_all_items(key="children", value=rating_key, base="library/metadata")
        kind, deeper = get_items_info(items)
        dig_tree(oc, items, MetadataMenu,
                 pass_kwargs={"base_title": title, "display_items": deeper, "previous_item_type": kind, "previous_rating_key": rating_key})
        # we don't know exactly where we are here, only add ignore option to series
        if should_display_ignore(items, previous=previous_item_type):
            add_ignore_options(oc, "series", title=item_title, rating_key=rating_key, callback_menu=IgnoreMenu)

        timeout = 30
        if current_kind == "season":
            timeout = 360
        elif current_kind == "series":
            timeout = 1800

        # add refresh
        oc.add(DirectoryObject(
            key=Callback(RefreshItem, rating_key=rating_key, item_title=title, refresh_kind=current_kind,
                         previous_rating_key=previous_rating_key, timeout=timeout*1000, randomize=timestamp()),
            title=u"Refresh: %s" % item_title,
            summary="Refreshes the %s, possibly searching for missing and picking up new subtitles on disk" % current_kind
        ))
        oc.add(DirectoryObject(
            key=Callback(RefreshItem, rating_key=rating_key, item_title=title, force=True,
                         refresh_kind=current_kind, previous_rating_key=previous_rating_key, timeout=timeout*1000,
                         randomize=timestamp()),
            title=u"Auto-Find subtitles: %s" % item_title,
            summary="Issues a forced refresh, ignoring known subtitles and searching for new ones"
        ))
    else:
        return ItemDetailsMenu(rating_key=rating_key, title=title, item_title=item_title)

    return oc


@route(PREFIX + '/ignore_list')
def IgnoreListMenu():
    oc = SubFolderObjectContainer(title2="Ignore list", replace_parent=True)
    for key in ignore_list.key_order:
        values = ignore_list[key]
        for value in values:
            add_ignore_options(oc, key, title=ignore_list.get_title(key, value), rating_key=value, callback_menu=IgnoreMenu)
    return oc


@route(PREFIX + '/history')
def HistoryMenu():
    from support.history import get_history
    history = get_history()
    oc = SubFolderObjectContainer(title2="History", replace_parent=True)

    for item in history.history_items:
        oc.add(DirectoryObject(
            key=Callback(ItemDetailsMenu, title=item.title, item_title=item.item_title,
                         rating_key=item.rating_key),
            title=u"%s (%s)" % (item.item_title, item.mode_verbose),
            summary=u"%s in %s (%s, score: %s), %s" % (item.lang_name, item.section_title,
                                                       item.provider_name, item.score, df(item.time))
        ))

    return oc


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
    title = unicode(base_title) + " > " + unicode(title) if base_title else unicode(title)
    item = get_item(rating_key)
    current_kind = get_item_kind_from_rating_key(rating_key)

    timeout = 30

    oc = SubFolderObjectContainer(title2=title, replace_parent=True)
    oc.add(DirectoryObject(
        key=Callback(RefreshItem, rating_key=rating_key, item_title=item_title, randomize=timestamp(),
                     timeout=timeout*1000),
        title=u"Refresh: %s" % item_title,
        summary="Refreshes the %s, possibly searching for missing and picking up new subtitles on disk" % current_kind,
        thumb=item.thumb or default_thumb
    ))
    oc.add(DirectoryObject(
        key=Callback(RefreshItem, rating_key=rating_key, item_title=item_title, force=True, randomize=timestamp(),
                     timeout=timeout*1000),
        title=u"Auto-search: %s" % item_title,
        summary="Issues a forced refresh, ignoring known subtitles and searching for new ones",
        thumb=item.thumb or default_thumb
    ))

    # get stored subtitle info for item id
    current_subtitle_info = get_subtitle_info(rating_key)

    # get the plex item
    plex_item = list(Plex["library"].metadata(rating_key))[0]

    # get current media info for that item
    media = plex_item.media

    # look for subtitles for all available media parts and all of their languages
    for part in media.parts:
        filename = os.path.basename(part.file)
        part_id = str(part.id)

        # get corresponding stored subtitle data for that media part (physical media item)
        sub_part_data = current_subtitle_info.get(part_id, {}) if current_subtitle_info else {}

        # iterate through all configured languages
        for lang in config.lang_list:
            lang_a2 = lang.alpha2
            # ietf lang?
            if cast_bool(Prefs["subtitles.language.ietf"]) and "-" in lang_a2:
                lang_a2 = lang_a2.split("-")[0]

            sub_data_for_lang = sub_part_data.get(lang_a2, {})

            # try getting current subtitle information for that language
            current_subtitle_key = sub_data_for_lang.get("current", (None, None))
            current_sub_provider_name, current_sub_id = current_subtitle_key

            summary = u"No current subtitle in storage"
            current_score = None
            if current_sub_provider_name:
                current_subtitle = sub_part_data[lang_a2][current_subtitle_key]
                current_score = current_subtitle["score"]

                summary = u"Current subtitle: %s (added: %s, %s), Language: %s, Score: %i, Storage: %s" % \
                          (current_sub_provider_name,
                           df(current_subtitle["date_added"]), mode_map.get(current_subtitle.get("mode", "a")), lang,
                           current_subtitle["score"], current_subtitle["storage"])

            oc.add(DirectoryObject(
                key=Callback(ListAvailableSubsForItemMenu, rating_key=rating_key, part_id=part_id, title=title,
                             item_title=item_title, language=lang, current_id=current_sub_id,
                             item_type=plex_item.type, filename=filename, current_data=summary,
                             randomize=timestamp(), current_provider=current_sub_provider_name,
                             current_score=current_score),
                title=u"List %s subtitles" % lang.name,
                summary=summary
            ))

    add_ignore_options(oc, "videos", title=item_title, rating_key=rating_key, callback_menu=IgnoreMenu)

    return oc


def get_item_task_data(task_name, rating_key, language):
    task_data = scheduler.get_task_data(task_name)
    search_results = task_data.get(rating_key, {}) if task_data else {}
    return search_results.get(language)


@route(PREFIX + '/item/search/{rating_key}/{part_id}', force=bool)
@debounce
def ListAvailableSubsForItemMenu(rating_key=None, part_id=None, title=None, item_title=None, filename=None,
                                 item_type="episode", language=None, force=False, current_id=None, current_data=None,
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
        title=u"Back to: %s" % title,
        summary=current_data,
        thumb=default_thumb
    ))

    metadata = get_plex_metadata(rating_key, part_id, item_type)
    scanned_parts = scan_videos([metadata], kind="series" if item_type == "episode" else "movie", ignore_all=True)

    if not scanned_parts:
        Log.Error("Couldn't list available subtitles for %s", rating_key)
        return oc

    video, plex_part = scanned_parts.items()[0]

    video_display_data = [video.format] if video.format else []
    if video.release_group:
        video_display_data.append(u"by %s" % video.release_group)
    video_display_data = " ".join(video_display_data)

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
    else:
        oc.add(DirectoryObject(
            key=Callback(ListAvailableSubsForItemMenu, rating_key=rating_key, item_title=item_title,
                         language=language, filename=filename, current_data=current_data,
                         part_id=part_id, title=title, current_id=current_id, item_type=item_type,
                         current_provider=current_provider, current_score=current_score,
                         randomize=timestamp()),
            title=u"Searching for %s subs (%s), refresh here ..." % (get_language(language).name, video_display_data),
            summary=u"%sFilename: %s" % (current_display, filename),
            thumb=default_thumb
        ))

    if not search_results:
        return oc

    for subtitle in search_results:
        oc.add(DirectoryObject(
            key=Callback(TriggerDownloadSubtitle, rating_key=rating_key, randomize=timestamp(), item_title=item_title,
                         subtitle_id=str(subtitle.id), language=language),
            title=u"%s: %s, score: %s" % ("Available" if current_id != subtitle.id else "Current",
                                    subtitle.provider_name, subtitle.score),
            summary=u"Release: %s, Matches: %s" % (subtitle.release_info, ", ".join(subtitle.matches)),
            thumb=default_thumb
        ))

    return oc


@route(PREFIX + '/download_subtitle/{rating_key}')
@debounce
def TriggerDownloadSubtitle(rating_key=None, subtitle_id=None, item_title=None, language=None, randomize=None):
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

    return fatality(randomize=timestamp(), header=" ", replace_parent=True)


@route(PREFIX + '/item/{rating_key}')
@debounce
def RefreshItem(rating_key=None, came_from="/recent", item_title=None, force=False, refresh_kind=None,
                previous_rating_key=None, timeout=8000, randomize=None, trigger=True):
    assert rating_key
    header = " "
    if trigger:
        set_refresh_menu_state(u"Triggering %sRefresh for %s" % ("Force-" if force else "", item_title))
        Thread.Create(refresh_item, rating_key=rating_key, force=force, refresh_kind=refresh_kind,
                      parent_rating_key=previous_rating_key, timeout=int(timeout))

        header = u"%s of item %s triggered" % ("Refresh" if not force else "Forced-refresh", rating_key)
    return fatality(randomize=timestamp(), header=header, replace_parent=True)


@route(PREFIX + '/missing/refresh')
@debounce
def RefreshMissing(randomize=None):
    scheduler.dispatch_task("SearchAllRecentlyAddedMissing")
    header = "Refresh of recently added items with missing subtitles triggered"
    return fatality(header=header, replace_parent=True)


@route(PREFIX + '/advanced')
def AdvancedMenu(randomize=None, header=None, message=None):
    oc = SubFolderObjectContainer(header=header or "Internal stuff, pay attention!", message=message, no_cache=True, no_history=True,
                                  replace_parent=False, title2="Advanced")

    if config.lock_advanced_menu and not config.pin_correct:
        oc.add(DirectoryObject(
            key=Callback(PinMenu, randomize=timestamp(), success_go_to="advanced"),
            title=pad_title("Enter PIN"),
            summary="The owner has restricted the access to this menu. Please enter the correct pin",
        ))
        return oc

    oc.add(DirectoryObject(
        key=Callback(TriggerRestart, randomize=timestamp()),
        title=pad_title("Restart the plugin"),
    ))
    oc.add(DirectoryObject(
        key=Callback(TriggerBetterSubtitles, randomize=timestamp()),
        title=pad_title("Trigger find better subtitles"),
    ))
    oc.add(DirectoryObject(
        key=Callback(LogStorage, key="tasks", randomize=timestamp()),
        title=pad_title("Log the plugin's scheduled tasks state storage"),
    ))
    oc.add(DirectoryObject(
        key=Callback(LogStorage, key="subs", randomize=timestamp()),
        title=pad_title("Log the plugin's internal subtitle information storage"),
    ))
    oc.add(DirectoryObject(
        key=Callback(LogStorage, key="ignore", randomize=timestamp()),
        title=pad_title("Log the plugin's internal ignorelist storage"),
    ))
    oc.add(DirectoryObject(
        key=Callback(LogStorage, key="history", randomize=timestamp()),
        title=pad_title("Log the plugin's internal history storage"),
    ))
    oc.add(DirectoryObject(
        key=Callback(ResetStorage, key="tasks", randomize=timestamp()),
        title=pad_title("Reset the plugin's scheduled tasks state storage"),
    ))
    oc.add(DirectoryObject(
        key=Callback(ResetStorage, key="subs", randomize=timestamp()),
        title=pad_title("Reset the plugin's internal subtitle information storage"),
    ))
    oc.add(DirectoryObject(
        key=Callback(ResetStorage, key="ignore", randomize=timestamp()),
        title=pad_title("Reset the plugin's internal ignorelist storage"),
    ))
    oc.add(DirectoryObject(
        key=Callback(ResetStorage, key="history", randomize=timestamp()),
        title=pad_title("Reset the plugin's internal history storage"),
    ))
    return oc


@route(PREFIX + '/ValidatePrefs', enforce_route=True)
def ValidatePrefs():
    Core.log.setLevel(logging.DEBUG)
    Log.Debug("Validate Prefs called.")

    # cache the channel state
    update_dict = False
    restart = False

    # reset pin
    Dict["pin_correct_time"] = None

    config.initialize()
    if "channel_enabled" not in Dict:
        update_dict = True

    elif Dict["channel_enabled"] != config.enable_channel:
        Log.Debug("Channel features %s, restarting plugin", "enabled" if config.enable_channel else "disabled")
        update_dict = True
        restart = True

    if update_dict:
        Dict["channel_enabled"] = config.enable_channel
        Dict.Save()

    if restart:
        DispatchRestart()

    scheduler.setup_tasks()
    set_refresh_menu_state(None)

    if Prefs["log_console"]:
        Core.log.addHandler(logger.console_handler)
        Log.Debug("Logging to console from now on")
    else:
        Core.log.removeHandler(logger.console_handler)
        Log.Debug("Stop logging to console")

    Log.Debug("Setting log-level to %s", Prefs["log_level"])
    logger.register_logging_handler(DEPENDENCY_MODULE_NAMES, level=Prefs["log_level"])
    Core.log.setLevel(logging.getLevelName(Prefs["log_level"]))

    return


def DispatchRestart():
    Thread.CreateTimer(1.0, Restart)


@route(PREFIX + '/advanced/restart/trigger')
@debounce
def TriggerRestart(randomize=None):
    set_refresh_menu_state("Restarting the plugin")
    DispatchRestart()
    return fatality(header="Restart triggered, please wait about 5 seconds", force_title=" ", only_refresh=True, replace_parent=True,
                    no_history=True, randomize=timestamp())


@route(PREFIX + '/advanced/restart/execute')
def Restart():
    Plex[":/plugins"].restart(PLUGIN_IDENTIFIER)


@route(PREFIX + '/storage/reset', sure=bool)
def ResetStorage(key, randomize=None, sure=False):
    if not sure:
        oc = SubFolderObjectContainer(no_history=True, title1="Reset subtitle storage", title2="Are you sure?")
        oc.add(DirectoryObject(
            key=Callback(ResetStorage, key=key, sure=True, randomize=timestamp()),
            title=pad_title("Are you really sure?"),

        ))
        return oc

    reset_storage(key)

    if key == "tasks":
        # reinitialize the scheduler
        scheduler.init_storage()
        scheduler.setup_tasks()

    return AdvancedMenu(
        randomize=timestamp(),
        header='Success',
        message='Information Storage (%s) reset' % key
    )


@route(PREFIX + '/storage/log')
def LogStorage(key, randomize=None):
    log_storage(key)
    return AdvancedMenu(
        randomize=timestamp(),
        header='Success',
        message='Information Storage (%s) logged' % key
    )


@route(PREFIX + '/triggerbetter')
def TriggerBetterSubtitles(randomize=None):
    scheduler.dispatch_task("FindBetterSubtitles")
    return AdvancedMenu(
        randomize=timestamp(),
        header='Success',
        message='FindBetterSubtitles triggered'
    )