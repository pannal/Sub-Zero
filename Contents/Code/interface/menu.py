# coding=utf-8
import logging
import logger

from menu_helpers import add_ignore_options, dig_tree, set_refresh_menu_state, should_display_ignore, enable_channel_wrapper
from subzero.constants import TITLE, ART, ICON, PREFIX, PLUGIN_IDENTIFIER, DEPENDENCY_MODULE_NAMES
from support.background import scheduler
from support.config import config
from support.helpers import pad_title, timestamp
from support.ignore import ignore_list
from support.items import get_on_deck_items, refresh_item, get_all_items
from support.items import get_recent_items, get_items_info
from support.lib import Plex
from support.missing_subtitles import items_get_all_missing_subs
from support.storage import reset_storage, log_storage, get_subtitle_info
from support.plex_media import scan_parts

# init GUI
ObjectContainer.art = R(ART)
ObjectContainer.no_cache = True

# noinspection PyUnboundLocalVariable
route = enable_channel_wrapper(route)
# noinspection PyUnboundLocalVariable
handler = enable_channel_wrapper(handler)
# default thumb
thumb=R(ICON)


@handler(PREFIX, TITLE, art=ART, thumb=ICON)
@route(PREFIX)
def fatality(randomize=None, force_title=None, header=None, message=None, only_refresh=False, no_history=False, replace_parent=False):
    """
    subzero main menu
    """
    title = force_title if force_title is not None else config.full_version
    oc = ObjectContainer(title1=title, title2=None, header=unicode(header) if header else header, message=message, no_history=no_history,
                         replace_parent=replace_parent, no_cache=True)

    if not config.permissions_ok:
        for title, path in config.missing_permissions:
            oc.add(DirectoryObject(
                key=Callback(fatality, randomize=timestamp()),
                title=pad_title("Insufficient permissions"),
                summary="Insufficient permissions on library %s, folder: %s" % (title, path),
                thumb=thumb
            ))
        return oc

    if not only_refresh:
        if Dict["current_refresh_state"]:
            oc.add(DirectoryObject(
                key=Callback(fatality, force_title=" ", randomize=timestamp()),
                title=pad_title("Working ... refresh here"),
                thumb=thumb,
                summary="Current state: %s; Last state: %s" % (
                    (Dict["current_refresh_state"] or "Idle") if "current_refresh_state" in Dict else "Idle",
                    (Dict["last_refresh_state"] or "None") if "last_refresh_state" in Dict else "None"
                )
            ))

        oc.add(DirectoryObject(
            key=Callback(OnDeckMenu),
            title=pad_title("On Deck items"),
            thumb=thumb,
            summary="Shows the current on deck items and allows you to individually (force-) refresh their metadata/subtitles."
        ))
        oc.add(DirectoryObject(
            key=Callback(RecentlyAddedMenu),
            title="Items with missing subtitles",
            thumb=thumb,
            summary="Shows the items honoring the configured 'Item age to be considered recent'-setting (%s)"
                    " and allowing you to individually (force-) refresh their metadata/subtitles. " % Prefs["scheduler.item_is_recent_age"]
        ))
        oc.add(DirectoryObject(
            key=Callback(SectionsMenu),
            title="Browse all items",
            thumb=thumb,
            summary="Go through your whole library and manage your ignore list. You can also "
                    "(force-) refresh the metadata/subtitles of individual items."
        ))

        task_name = "searchAllRecentlyAddedMissing"
        task = scheduler.task(task_name)

        if task.ready_for_display:
            task_state = "Running: %s/%s (%s%%)" % (len(task.items_done), len(task.items_searching), task.percentage)
        else:
            task_state = "Last scheduler run: %s; Next scheduled run: %s; Last runtime: %s" % (scheduler.last_run(task_name) or "never",
                                                                                               scheduler.next_run(task_name) or "never",
                                                                                               str(task.last_run_time).split(".")[0])

        oc.add(DirectoryObject(
            key=Callback(RefreshMissing),
            title="Search for missing subtitles (in recently-added items, max-age: %s)" % Prefs["scheduler.item_is_recent_age"],
            thumb=thumb,
            summary="Automatically run periodically by the scheduler, if configured. %s" % task_state
        ))

        oc.add(DirectoryObject(
            key=Callback(IgnoreListMenu),
            title="Display ignore list (%d)" % len(ignore_list),
            thumb=thumb,
            summary="Show the current ignore list (mainly used for the automatic tasks)"
        ))

    oc.add(DirectoryObject(
        key=Callback(fatality, force_title=" ", randomize=timestamp()),
        title=pad_title("Refresh"),
        thumb=thumb,
        summary="Current state: %s; Last state: %s" % (
            (Dict["current_refresh_state"] or "Idle") if "current_refresh_state" in Dict else "Idle",
            (Dict["last_refresh_state"] or "None") if "last_refresh_state" in Dict else "None"
        )
    ))

    if not only_refresh:
        oc.add(DirectoryObject(
            key=Callback(AdvancedMenu),
            title=pad_title("Advanced functions"),
            thumb=thumb,
            summary="Use at your own risk"
        ))

    return oc


@route(PREFIX + '/on_deck')
def OnDeckMenu(message=None):
    """
    displays the items on deck
    :param message:
    :return:
    """
    return mergedItemsMenu(title="Items On Deck", base_title="Items On Deck", itemGetter=get_on_deck_items)


@route(PREFIX + '/recent')
def RecentlyAddedMenu(message=None):
    """
    displays the recently added items with missing subtitles
    :param message:
    :return:
    """
    return recentItemsMenu(title="Missing Subtitles", base_title="Missing Subtitles")


def recentItemsMenu(title, base_title=None):
    oc = ObjectContainer(title2=title, no_cache=True, no_history=True)
    recent_items = get_recent_items()
    if recent_items:
        missing_items = items_get_all_missing_subs(recent_items)
        if missing_items:
            for added_at, item_id, title in missing_items:
                oc.add(DirectoryObject(
                    key=Callback(ItemDetailsMenu, title=base_title + " > " + title, item_title=title, thumb=thumb, rating_key=item_id), title=title
                ))

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
    oc = ObjectContainer(title2=title, no_cache=True, no_history=True)
    items = itemGetter(*args, **kwargs)

    for kind, title, item_id, deeper, item in items:
        oc.add(DirectoryObject(
            title=title,
            thumb=thumb,
            key=Callback(ItemDetailsMenu, title=base_title + " > " + title, item_title=title, rating_key=item_id)
        ))

    return oc


def determine_section_display(kind, item):
    """
    returns the menu function for a section based on the size of it (amount of items)
    :param kind:
    :param item:
    :return:
    """
    if item.size > 200:
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
        oc = ObjectContainer(no_history=True, replace_parent=True, title1="%s %s %s %s the ignore list" % (
            "Add" if not is_ignored else "Remove", ignore_list.verbose(kind), title, "to" if not is_ignored else "from"), title2="Are you sure?")
        oc.add(DirectoryObject(
            key=Callback(IgnoreMenu, kind=kind, rating_key=rating_key, title=title, sure=True, todo="add" if not is_ignored else "remove"),
            title=pad_title("Are you sure?"),
            thumb=thumb
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
def SectionsMenu():
    """
    displays the menu for all sections
    :return:
    """
    items = get_all_items("sections")

    return dig_tree(ObjectContainer(title2="Sections", no_cache=True, no_history=True), items, None,
                    menu_determination_callback=determine_section_display, pass_kwargs={"base_title": "Sections"},
                    fill_args={"title": "section_title"})


@route(PREFIX + '/section', ignore_options=bool)
def SectionMenu(rating_key, title=None, base_title=None, section_title=None, ignore_options=True):
    """
    displays the contents of a section
    :param rating_key:
    :param title:
    :param base_title:
    :param section_title:
    :param ignore_options:
    :return:
    """
    items = get_all_items(key="all", value=rating_key, base="library/sections")

    kind, deeper = get_items_info(items)
    title = unicode(title)
    section_title = title
    title = base_title + " > " + title
    oc = ObjectContainer(title2=title, no_cache=True, no_history=True)
    if ignore_options:
        add_ignore_options(oc, "sections", title=section_title, rating_key=rating_key, callback_menu=IgnoreMenu)

    return dig_tree(oc, items, MetadataMenu,
                    pass_kwargs={"base_title": title, "display_items": deeper, "previous_item_type": "section",
                                 "previous_rating_key": rating_key})


@route(PREFIX + '/section/firstLetter', deeper=bool)
def SectionFirstLetterMenu(rating_key, title=None, base_title=None, section_title=None):
    """
    displays the contents of a section indexed by its first char (A-Z, 0-9...)
    :param rating_key:
    :param title:
    :param base_title:
    :param section_title:
    :return:
    """
    items = get_all_items(key="first_character", value=rating_key, base="library/sections")

    kind, deeper = get_items_info(items)

    title = unicode(title)
    oc = ObjectContainer(title2=section_title, no_cache=True, no_history=True)
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
    oc = ObjectContainer(title2=title, no_cache=True, no_history=True)

    items = get_all_items(key="first_character", value=[rating_key, key], base="library/sections", flat=False)
    kind, deeper = get_items_info(items)
    dig_tree(oc, items, MetadataMenu,
             pass_kwargs={"base_title": title, "display_items": deeper, "previous_item_type": kind, "previous_rating_key": rating_key})
    return oc


@route(PREFIX + '/section/contents', display_items=bool)
def MetadataMenu(rating_key, title=None, base_title=None, display_items=False, previous_item_type=None, previous_rating_key=None):
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
    oc = ObjectContainer(title2=title, no_cache=True, no_history=True)

    if display_items:
        items = get_all_items(key="children", value=rating_key, base="library/metadata")
        kind, deeper = get_items_info(items)
        dig_tree(oc, items, MetadataMenu,
                 pass_kwargs={"base_title": title, "display_items": deeper, "previous_item_type": kind, "previous_rating_key": rating_key})
        # we don't know exactly where we are here, only add ignore option to series
        if should_display_ignore(items, previous=previous_item_type):
            add_ignore_options(oc, "series", title=item_title, rating_key=rating_key, callback_menu=IgnoreMenu)

        # add refresh
        oc.add(DirectoryObject(
            key=Callback(RefreshItem, rating_key=rating_key, item_title=item_title, refresh_kind=kind, previous_rating_key=previous_rating_key,
                         timeout=16000),
            title=u"Refresh: %s" % item_title,
            thumb=thumb,
            summary="Refreshes the item, possibly picking up new subtitles on disk"
        ))
        oc.add(DirectoryObject(
            key=Callback(RefreshItem, rating_key=rating_key, item_title=item_title, force=True, refresh_kind=kind,
                         previous_rating_key=previous_rating_key, timeout=16000),
            title=u"Force-Refresh: %s" % item_title,
            thumb=thumb,
            summary="Issues a forced refresh, ignoring known subtitles and searching for new ones"
        ))
    else:
        return ItemDetailsMenu(rating_key=rating_key, title=title, item_title=item_title)

    return oc


@route(PREFIX + '/ignore_list')
def IgnoreListMenu():
    oc = ObjectContainer(title2="Ignore list", replace_parent=True)
    for key in ignore_list.key_order:
        values = ignore_list[key]
        for value in values:
            add_ignore_options(oc, key, title=ignore_list.get_title(key, value), rating_key=value, callback_menu=IgnoreMenu)
    return oc


@route(PREFIX + '/item/{rating_key}/actions')
def ItemDetailsMenu(rating_key, title=None, base_title=None, item_title=None, randomize=None, thumb=thumb):
    """
    displays the item details menu of an item that doesn't contain any deeper tree, such as a movie or an episode
    :param rating_key:
    :param title:
    :param base_title:
    :param item_title:
    :param randomize:
    :param thumb:
    :return:
    """
    title = unicode(base_title) + " > " + unicode(title) if base_title else unicode(title)
    oc = ObjectContainer(title2=title, replace_parent=True)
    oc.add(DirectoryObject(
        key=Callback(RefreshItem, rating_key=rating_key, item_title=item_title),
        title=u"Refresh: %s" % item_title,
        thumb=thumb,
        summary="Refreshes the item, possibly picking up new subtitles on disk"
    ))
    oc.add(DirectoryObject(
        key=Callback(RefreshItem, rating_key=rating_key, item_title=item_title, force=True),
        title=u"Force-Refresh: %s" % item_title,
        thumb=thumb,
        summary="Issues a forced refresh, ignoring known subtitles and searching for new ones"
    ))
    add_ignore_options(oc, "videos", title=item_title, rating_key=rating_key, callback_menu=IgnoreMenu)

    return oc


@route(PREFIX + '/item/{rating_key}')
def RefreshItem(rating_key=None, came_from="/recent", item_title=None, force=False, refresh_kind=None, previous_rating_key=None, timeout=8000):
    assert rating_key
    set_refresh_menu_state(u"Triggering %sRefresh for %s" % ("Force-" if force else "", item_title))
    Thread.Create(refresh_item, rating_key=rating_key, force=force, refresh_kind=refresh_kind, parent_rating_key=previous_rating_key,
                  timeout=int(timeout))
    return fatality(randomize=timestamp(), header=u"%s of item %s triggered" % ("Refresh" if not force else "Forced-refresh", rating_key),
                    replace_parent=True)


@route(PREFIX + '/missing/refresh')
def RefreshMissing(randomize=None):
    Thread.CreateTimer(1.0, lambda: scheduler.run_task("searchAllRecentlyAddedMissing"))
    return fatality(header="Refresh of recently added items with missing subtitles triggered", replace_parent=True)


@route(PREFIX + '/advanced')
def AdvancedMenu(randomize=None, header=None, message=None):
    oc = ObjectContainer(header=header or "Internal stuff, pay attention!", message=message, no_cache=True, no_history=True,
                         replace_parent=True, title2="Advanced")

    oc.add(DirectoryObject(
        key=Callback(TriggerRestart),
        title=pad_title("Restart the plugin"),
        thumb=thumb
    ))
    oc.add(DirectoryObject(
        key=Callback(LogStorage, key="tasks", randomize=timestamp()),
        title=pad_title("Log the plugin's scheduled tasks state storage"),
        thumb=thumb
    ))
    oc.add(DirectoryObject(
        key=Callback(LogStorage, key="subs", randomize=timestamp()),
        title=pad_title("Log the plugin's internal subtitle information storage")
    ))
    oc.add(DirectoryObject(
        key=Callback(LogStorage, key="ignore", randomize=timestamp()),
        title=pad_title("Log the plugin's internal ignorelist storage"),
        thumb=thumb
    ))
    oc.add(DirectoryObject(
        key=Callback(ResetStorage, key="tasks", randomize=timestamp()),
        title=pad_title("Reset the plugin's scheduled tasks state storage"),
        thumb=thumb
    ))
    oc.add(DirectoryObject(
        key=Callback(ResetStorage, key="subs", randomize=timestamp()),
        title=pad_title("Reset the plugin's internal subtitle information storage")
    ))
    oc.add(DirectoryObject(
        key=Callback(ResetStorage, key="ignore", randomize=timestamp()),
        title=pad_title("Reset the plugin's internal ignorelist storage")
    ))
    return oc


@route(PREFIX + '/ValidatePrefs', enforce_route=True)
def ValidatePrefs():
    Core.log.setLevel(logging.DEBUG)
    Log.Debug("Validate Prefs called.")

    # cache the channel state
    update_dict = False
    restart = False
    if "channel_enabled" not in Dict:
        update_dict = True

    elif Dict["channel_enabled"] != Prefs["enable_channel"]:
        Log.Debug("Channel features %s, restarting plugin", "enabled" if Prefs["enable_channel"] else "disabled")
        update_dict = True
        restart = True

    if update_dict:
        Dict["channel_enabled"] = Prefs["enable_channel"]
        Dict.Save()

    if restart:
        DispatchRestart()

    config.initialize()
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
def TriggerRestart(randomize=None):
    set_refresh_menu_state("Restarting the plugin")
    DispatchRestart()
    return fatality(header="Restart triggered, please wait about 5 seconds", force_title=" ", only_refresh=True, replace_parent=True,
                    no_history=True)


@route(PREFIX + '/advanced/restart/execute')
def Restart():
    Plex[":/plugins"].restart(PLUGIN_IDENTIFIER)


@route(PREFIX + '/storage/reset', sure=bool)
def ResetStorage(key, randomize=None, sure=False):
    if not sure:
        oc = ObjectContainer(no_history=True, title1="Reset subtitle storage", title2="Are you sure?")
        oc.add(DirectoryObject(
            key=Callback(ResetStorage, key=key, sure=True, randomize=timestamp()),
            title=pad_title("Are you really sure?"),
            thumb=thumb
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
