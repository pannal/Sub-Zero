# coding=utf-8
import traceback

from support.config import config
from support.helpers import format_item
from support.lib import Plex


def item_discover_missing_subs(rating_key, kind="show", added_at=None, section_title=None, internal=False, external=True, languages=()):
    existing_subs = {"internal": [], "external": [], "count": 0}

    item_id = int(rating_key)
    item_container = Plex["library"].metadata(item_id)

    item = list(item_container)[0]

    if kind == "show":
        item_title = format_item(item, kind, parent=item.season, section_title=section_title, parent_title=item.show.title)
    else:
        item_title = format_item(item, kind, section_title=section_title)

    video = item.media

    for part in video.parts:
        for stream in part.streams:
            if stream.stream_type == 3:
                if stream.index:
                    key = "internal"
                else:
                    key = "external"

                existing_subs[key].append(Locale.Language.Match(stream.language_code or ""))
                existing_subs["count"] = existing_subs["count"] + 1

    missing = languages
    if existing_subs["count"]:
        existing_flat = (existing_subs["internal"] if internal else []) + (existing_subs["external"] if external else [])
        languages_set = set(languages)
        if languages_set.issubset(existing_flat) or (len(existing_flat) >= 1 and Prefs['subtitles.only_one']):
            # all subs found
            Log.Info(u"All subtitles exist for '%s'", item_title)
            return
        missing = languages_set - set(existing_flat)
        Log.Info(u"Subs still missing for '%s': %s", item_title, missing)

    if missing:
        return added_at, item_id, item_title, item['thumb']

def items_get_all_missing_subs(items):
    missing = []
    for added_at, kind, section_title, key in items:
        try:
            state = item_discover_missing_subs(
                key,
                kind=kind,
                added_at=added_at,
                section_title=section_title,
                languages=config.lang_list,
                internal=bool(Prefs["subtitles.scan.embedded"]),
                external=bool(Prefs["subtitles.scan.external"])
            )
            if state:
                # (added_at, item_id, title)
                missing.append(state)
        except:
            Log.Error("Something went wrong when getting the state of item %s: %s", key, traceback.format_exc())
    return missing


def refresh_item(item, title):
    Plex["library/metadata"].refresh(item)


def refresh_items(items):
    for item, title in items:
        refresh_item(item, title)
