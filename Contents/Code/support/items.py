# coding=utf-8

import logging
import re
import traceback
import types
import os

import time

import datetime

from ignore import ignore_list
from helpers import is_recent, get_plex_item_display_title, query_plex, PartUnknownException
from lib import Plex, get_intent
from config import config, IGNORE_FN
from subliminal_patch.subtitle import ModifiedSubtitle
from subzero.modification import registry as mod_registry, SubtitleModifications
from socket import timeout

logger = logging.getLogger(__name__)

MI_KIND, MI_TITLE, MI_KEY, MI_DEEPER, MI_ITEM = 0, 1, 2, 3, 4

container_size_re = re.compile(ur'totalSize="(\d+)"')


def get_item(key):
    try:
        item_id = int(key)
    except ValueError:
        return

    try:
        item_container = Plex["library"].metadata(item_id)
    except timeout:
        Log.Debug("PMS API timed out when querying information about item %d", item_id)
        return

    try:
        return list(item_container)[0]
    except:
        pass


def get_item_kind(item):
    return type(item).__name__


PLEX_API_TYPE_MAP = {
    "Show": "series",
    "Season": "season",
    "Episode": "episode",
    "Movie": "movie",
}


def get_item_kind_from_rating_key(key):
    item = get_item(key)
    return PLEX_API_TYPE_MAP.get(get_item_kind(item))


def get_item_kind_from_item(item):
    return PLEX_API_TYPE_MAP.get(get_item_kind(item))


def get_item_title(item):
    kind = get_item_kind_from_item(item)
    if kind not in ("episode", "movie", "season", "series"):
        return

    if kind == "episode":
        return get_plex_item_display_title(item, "show", parent=item.season, section_title=None,
                                                 parent_title=item.show.title)
    elif kind == "season":
        return get_plex_item_display_title(item, "season", parent=item.show, section_title="Season",
                                           parent_title=item.show.title)
    else:
        return get_plex_item_display_title(item, kind, section_title=None)


def get_item_thumb(item):
    kind = get_item_kind(item)
    if kind == "Episode":
        return item.show.thumb
    elif kind == "Section":
        return item.art
    return item.thumb


def get_items_info(items):
    return items[0][MI_KIND], items[0][MI_DEEPER]


def get_kind(items):
    return items[0][MI_KIND]


def get_section_size(key):
    """
    quick query to determine the section size
    :param key:
    :return:
    """
    size = None
    url = "http://127.0.0.1:32400/library/sections/%s/all" % int(key)
    use_args = {
        "X-Plex-Container-Size": "0",
        "X-Plex-Container-Start": "0"
    }
    response = query_plex(url, use_args)
    matches = container_size_re.findall(response.content)
    if matches:
        size = int(matches[0])

    return size


def get_items(key="recently_added", base="library", value=None, flat=False, add_section_title=False):
    """
    try to handle all return types plex throws at us and return a generalized item tuple
    """
    items = []
    apply_value = None
    if value:
        if isinstance(value, types.ListType):
            apply_value = value
        else:
            apply_value = [value]
    result = getattr(Plex[base], key)(*(apply_value or []))

    for item in result:
        cls = getattr(getattr(item, "__class__"), "__name__")
        if hasattr(item, "scanner"):
            kind = "section"
        elif cls == "Directory":
            kind = "directory"
        else:
            kind = item.type

        # only return items for our enabled sections
        section_key = None
        if kind == "section":
            section_key = item.key
        else:
            if hasattr(item, "section_key"):
                section_key = getattr(item, "section_key")

        if section_key and section_key not in config.enabled_sections:
            continue

        if kind == "season":
            # fixme: i think this case is unused now
            if flat:
                # return episodes
                for child in item.children():
                    items.append(("episode", get_plex_item_display_title(child, "show", parent=item, add_section_title=add_section_title), int(item.rating_key),
                                  False, child))
            else:
                # return seasons
                items.append(("season", item.title, int(item.rating_key), True, item))

        elif kind == "directory":
            items.append(("directory", item.title, item.key, True, item))

        elif kind == "section":
            if item.type in ['movie', 'show']:
                item.size = get_section_size(item.key)
                items.append(("section", item.title, int(item.key), True, item))

        elif kind == "episode":
            items.append(
                (kind, get_plex_item_display_title(item, "show", parent=item.season, parent_title=item.show.title, section_title=item.section.title,
                                                   add_section_title=add_section_title), int(item.rating_key), False, item))

        elif kind in ("movie", "artist", "photo"):
            items.append((kind, get_plex_item_display_title(item, kind, section_title=item.section.title, add_section_title=add_section_title),
                          int(item.rating_key), False, item))

        elif kind == "show":
            items.append((
                kind, get_plex_item_display_title(item, kind, section_title=item.section.title, add_section_title=add_section_title), int(item.rating_key), True,
                item))

    return items


def get_recent_items():
    """
    actually get the recent items, not limited like /library/recentlyAdded
    :return:
    """
    args = {
        "sort": "addedAt:desc",
        "X-Plex-Container-Start": "0",
        "X-Plex-Container-Size": "%s" % config.max_recent_items_per_library
    }

    episode_re = re.compile(ur'(?su)ratingKey="(?P<key>\d+)"'
                            ur'.+?grandparentRatingKey="(?P<parent_key>\d+)"'
                            ur'.+?title="(?P<title>.*?)"'
                            ur'.+?grandparentTitle="(?P<parent_title>.*?)"'
                            ur'.+?index="(?P<episode>\d+?)"'
                            ur'.+?parentIndex="(?P<season>\d+?)".+?addedAt="(?P<added>\d+)"'
                            ur'.+?<Part.+? file="(?P<filename>[^"]+?)"')
    movie_re = re.compile(ur'(?su)ratingKey="(?P<key>\d+)".+?title="(?P<title>.*?)'
                          ur'".+?addedAt="(?P<added>\d+)"'
                          ur'.+?<Part.+? file="(?P<filename>[^"]+?)"')
    available_keys = ("key", "title", "parent_key", "parent_title", "season", "episode", "added", "filename")
    recent = []

    for section in Plex["library"].sections():
        if section.type not in ("movie", "show") \
                or section.key not in config.enabled_sections \
                or section.key in ignore_list.sections:
            Log.Debug(u"Skipping section: %s" % section.title)
            continue

        use_args = args.copy()
        plex_item_type = "Movie"
        if section.type == "show":
            use_args["type"] = "4"
            plex_item_type = "Episode"

        url = "http://127.0.0.1:32400/library/sections/%s/all" % int(section.key)
        response = query_plex(url, use_args)

        matcher = episode_re if section.type == "show" else movie_re
        matches = [m.groupdict() for m in matcher.finditer(response.content)]
        for match in matches:
            data = dict((key, match[key] if key in match else None) for key in available_keys)
            if section.type == "show" and data["parent_key"] in ignore_list.series:
                Log.Debug(u"Skipping series: %s" % data["parent_title"])
                continue
            if data["key"] in ignore_list.videos:
                Log.Debug(u"Skipping item: %s" % data["title"])
                continue
            if is_physically_ignored(data["filename"], plex_item_type):
                Log.Debug(u"Skipping item: %s" % data["title"])
                continue

            if is_recent(int(data["added"])):
                recent.append((int(data["added"]), section.type, section.title, data["key"]))

    return recent


def get_on_deck_items():
    return get_items(key="on_deck", add_section_title=True)


def get_recently_added_items():
    return get_items(key="recently_added", add_section_title=True, flat=False)


def get_all_items(key, base="library", value=None, flat=False):
    return get_items(key, base=base, value=value, flat=flat)


def is_ignored(rating_key, item=None):
    """
    check whether an item, its show/season/section is in the soft or the hard ignore list
    :param rating_key:
    :param item:
    :return:
    """
    # item in soft ignore list
    if ignore_list["videos"] and rating_key in ignore_list["videos"]:
        Log.Debug("Item %s is in the soft ignore list" % rating_key)
        return True

    item = item or get_item(rating_key)
    kind = get_item_kind(item)

    # show in soft ignore list
    if kind == "Episode" and ignore_list["series"] and item.show.rating_key in ignore_list["series"]:
        Log.Debug("Item %s's show is in the soft ignore list" % rating_key)
        return True

    # season in soft ignore list
    if kind == "Episode" and ignore_list["seasons"] and item.season.rating_key in ignore_list["seasons"]:
        Log.Debug("Item %s's season is in the soft ignore list" % rating_key)
        return True

    # section in soft ignore list
    if ignore_list["sections"] and item.section.key in ignore_list["sections"]:
        Log.Debug("Item %s's section is in the soft ignore list" % rating_key)
        return True

    # physical/path ignore
    if config.ignore_sz_files or config.ignore_paths:
        for media in item.media:
            for part in media.parts:
                if is_physically_ignored(part.file, kind):
                    return True

    return False


def is_physically_ignored(fn, kind):
    if config.ignore_sz_files or config.ignore_paths:
        # normally check current item folder and the library
        check_ignore_paths = [".", "../"]
        if kind == "Episode":
            # series/episode, we've got a season folder here, also
            check_ignore_paths.append("../../")

        if config.ignore_paths and config.is_path_ignored(fn):
            Log.Debug("Item %s's path is manually ignored" % fn)
            return True

        if config.ignore_sz_files:
            for sub_path in check_ignore_paths:
                if config.is_physically_ignored(os.path.normpath(os.path.join(os.path.dirname(fn), sub_path))):
                    Log.Debug("An ignore file exists in either the items or its parent folders")
                    return True


def refresh_item(rating_key, force=False, timeout=8000, refresh_kind=None, parent_rating_key=None):
    intent = get_intent()

    # timeout actually is the time for which the intent will be valid
    if force:
        Log.Debug("Setting intent for force-refresh of %s to timeout: %s", rating_key, timeout)
        intent.set("force", rating_key, timeout=timeout)

        # force Dict.Save()
        intent.store.save()

    refresh = [rating_key]

    if refresh_kind == "season":
        # season refresh, needs explicit per-episode refresh
        refresh = [item.rating_key for item in list(Plex["library/metadata"].children(int(rating_key)))]

    multiple = len(refresh) > 1
    for key in refresh:
        Log.Info("%s item %s", "Refreshing" if not force else "Forced-refreshing", key)
        Plex["library/metadata"].refresh(key)
        if multiple:
            Thread.Sleep(10.0)


def get_current_sub(rating_key, part_id, language, plex_item=None):
    from support.storage import get_subtitle_storage

    item = plex_item or get_item(rating_key)
    subtitle_storage = get_subtitle_storage()
    stored_subs = subtitle_storage.load_or_new(item)
    current_sub = stored_subs.get_any(part_id, language)
    return current_sub, stored_subs, subtitle_storage


def save_stored_sub(stored_subtitle, rating_key, part_id, language, item_type, plex_item=None, storage=None,
                    stored_subs=None):
    """
    in order for this to work, if the calling supplies stored_subs and storage, it has to trigger its saving and
    destruction explicitly
    :param stored_subtitle:
    :param rating_key:
    :param part_id:
    :param language:
    :param item_type:
    :param plex_item:
    :param storage:
    :param stored_subs:
    :return:
    """
    from support.plex_media import get_plex_metadata
    from support.scanning import scan_videos
    from support.storage import save_subtitles, get_subtitle_storage

    plex_item = plex_item or get_item(rating_key)

    stored_subs_was_provided = True
    if not stored_subs or not storage:
        storage = get_subtitle_storage()
        stored_subs = storage.load(plex_item.rating_key)
        stored_subs_was_provided = False

    if not all([plex_item, stored_subs]):
        return

    try:
        metadata = get_plex_metadata(rating_key, part_id, item_type, plex_item=plex_item)
    except PartUnknownException:
        return

    scanned_parts = scan_videos([metadata], ignore_all=True, skip_hashing=True)
    video, plex_part = scanned_parts.items()[0]

    subtitle = ModifiedSubtitle(language, mods=stored_subtitle.mods)
    subtitle.content = stored_subtitle.content
    if stored_subtitle.encoding:
        # thanks plex
        setattr(subtitle, "_guessed_encoding", stored_subtitle.encoding)

        if stored_subtitle.encoding != "utf-8":
            subtitle.normalize()
            stored_subtitle.content = subtitle.content
            stored_subtitle.encoding = "utf-8"
            storage.save(stored_subs)

    subtitle.plex_media_fps = plex_part.fps
    subtitle.page_link = stored_subtitle.id
    subtitle.language = language
    subtitle.id = stored_subtitle.id

    try:
        save_subtitles(scanned_parts, {video: [subtitle]}, mode="m", bare_save=True)
        Log.Debug("Modified %s subtitle for: %s:%s with: %s", language.name, rating_key, part_id,
                  ", ".join(stored_subtitle.mods) if stored_subtitle.mods else "none")
    except:
        Log.Error("Something went wrong when modifying subtitle: %s", traceback.format_exc())

    if subtitle.storage_path:
        stored_subtitle.last_mod = datetime.datetime.fromtimestamp(os.path.getmtime(subtitle.storage_path))

    if not stored_subs_was_provided:
        storage.save(stored_subs)
        storage.destroy()


def set_mods_for_part(rating_key, part_id, language, item_type, mods, mode="add"):
    plex_item = get_item(rating_key)

    if not plex_item:
        return

    current_sub, stored_subs, storage = get_current_sub(rating_key, part_id, language, plex_item=plex_item)
    if mode == "add":
        for mod in mods:
            identifier, args = SubtitleModifications.parse_identifier(mod)
            mod_class = SubtitleModifications.get_mod_class(identifier)

            if identifier not in mod_registry.mods_available:
                raise NotImplementedError("Mod unknown or not registered")

            # clean exclusive mods
            if mod_class.exclusive and current_sub.mods:
                for current_mod in current_sub.mods[:]:
                    if current_mod.startswith(identifier):
                        current_sub.mods.remove(current_mod)
                        Log.Info("Removing superseded mod %s" % current_mod)

            current_sub.add_mod(mod)
    elif mode == "clear":
        current_sub.add_mod(None)
    elif mode == "remove":
        for mod in mods:
            current_sub.mods.remove(mod)

    elif mode == "remove_last":
        if current_sub.mods:
            current_sub.mods.pop()
    else:
        raise NotImplementedError("Wrong mode given")

    save_stored_sub(current_sub, rating_key, part_id, language, item_type, plex_item=plex_item, storage=storage,
                    stored_subs=stored_subs)

    storage.save(stored_subs)
    storage.destroy()
