# coding=utf-8
import traceback
import time

import os

from babelfish import LanguageReverseError

from support.config import config, TEXT_SUBTITLE_EXTS
from support.helpers import get_plex_item_display_title, cast_bool, get_language_from_stream
from support.items import get_item
from support.lib import Plex
from support.storage import get_subtitle_storage
from subzero.video import has_external_subtitle
from subzero.language import Language


def item_discover_missing_subs(rating_key, kind="show", added_at=None, section_title=None, internal=False, external=True, languages=()):
    item_id = int(rating_key)
    item = get_item(rating_key)

    if kind == "show":
        item_title = get_plex_item_display_title(item, kind, parent=item.season, section_title=section_title, parent_title=item.show.title)
    else:
        item_title = get_plex_item_display_title(item, kind, section_title=section_title)

    subtitle_storage = get_subtitle_storage()
    stored_subs = subtitle_storage.load(rating_key)
    subtitle_storage.destroy()

    subtitle_target_dir, tdir_is_absolute = config.subtitle_sub_dir

    missing = set()
    languages_set = set([Language.fromietf(str(l)) for l in languages])
    for media in item.media:
        existing_subs = {"internal": [], "external": [], "own_external": [], "count": 0}
        for part in media.parts:

            # did we already download an external subtitle before?
            if subtitle_target_dir and stored_subs:
                for language in languages_set:
                    if has_external_subtitle(part.id, stored_subs, language):
                        # check the existence of the actual subtitle file

                        # get media filename without extension
                        part_basename = os.path.splitext(os.path.basename(part.file))[0]

                        # compute target directory for subtitle
                        # fixme: move to central location
                        if tdir_is_absolute:
                            possible_subtitle_path_base = subtitle_target_dir
                        else:
                            possible_subtitle_path_base = os.path.join(os.path.dirname(part.file), subtitle_target_dir)

                        possible_subtitle_path_base = os.path.realpath(possible_subtitle_path_base)

                        # folder actually exists?
                        if not os.path.isdir(possible_subtitle_path_base):
                            continue

                        found_any = False
                        for ext in config.subtitle_formats:
                            if cast_bool(Prefs['subtitles.only_one']):
                                possible_subtitle_path = os.path.join(possible_subtitle_path_base,
                                                                      u"%s.%s" % (part_basename, ext))
                            else:
                                possible_subtitle_path = os.path.join(possible_subtitle_path_base,
                                                                      u"%s.%s.%s" % (part_basename, language, ext))

                            # check for subtitle existence
                            if os.path.isfile(possible_subtitle_path):
                                found_any = True
                                Log.Debug(u"Found: %s", possible_subtitle_path)
                                break

                        if found_any:
                            existing_subs["own_external"].append(language)
                            existing_subs["count"] = existing_subs["count"] + 1

            for stream in part.streams:
                if stream.stream_type == 3:
                    if stream.index:
                        key = "internal"
                    else:
                        key = "external"

                    if not config.exotic_ext and stream.codec.lower() not in TEXT_SUBTITLE_EXTS:
                        continue

                    # treat unknown language as lang1?
                    if not stream.language_code and config.treat_und_as_first:
                        lang = Language.fromietf(str(list(config.lang_list)[0]))

                    # we can't parse empty language codes
                    elif not stream.language_code or not stream.codec:
                        continue

                    else:
                        # parse with internal language parser first
                        try:
                            lang = get_language_from_stream(stream.language_code)
                            if not lang:
                                if config.treat_und_as_first:
                                    lang = Language.fromietf(str(list(config.lang_list)[0]))
                                else:
                                    continue

                        except (ValueError, LanguageReverseError):
                            continue

                    if lang:
                        # Log.Debug("Found babelfish language: %r", lang)
                        existing_subs[key].append(lang)
                        existing_subs["count"] = existing_subs["count"] + 1

        missing_from_part = set([Language.fromietf(str(l)) for l in languages])
        if existing_subs["count"]:

            # fixme: this is actually somewhat broken with IETF, as Plex doesn't store the country portion
            # (pt instead of pt-BR) inside the database. So it might actually download pt-BR if there's a local pt-BR
            # subtitle but not our own.
            existing_flat = set((existing_subs["internal"] if internal else [])
                                + (existing_subs["external"] if external else [])
                                + existing_subs["own_external"])

            check_languages = set([Language.fromietf(str(l)) for l in languages])
            alpha3_map = {}
            if config.ietf_as_alpha3:
                for language in existing_flat:
                    if language.country:
                        alpha3_map[language.alpha3] = language.country
                        language.country = None

                for language in check_languages:
                    if language.country:
                        alpha3_map[language.alpha3] = language.country
                        language.country = None

            # compare sets of strings, not sets of different Language instances
            check_languages_str = set(str(l) for l in check_languages)
            existing_flat_str = set(str(l) for l in existing_flat)

            if check_languages_str.issubset(existing_flat_str) or \
                    (len(existing_flat) >= 1 and Prefs['subtitles.only_one']):
                # all subs found
                #Log.Info(u"All subtitles exist for '%s'", item_title)
                continue

            missing_from_part = set(Language.fromietf(l) for l in check_languages_str - existing_flat_str)
            if config.ietf_as_alpha3:
                for language in missing_from_part:
                    language.country = alpha3_map.get(language.alpha3, None)

        if missing_from_part:
            Log.Info(u"Subs still missing for '%s' (%s: %s): %s", item_title, rating_key, media.id,
                     missing_from_part)
            missing.update(missing_from_part)

    if missing:
        # deduplicate
        missing = set(Language.fromietf(la) for la in set(str(l) for l in missing))
        return added_at, item_id, item_title, item, missing


def items_get_all_missing_subs(items, sleep_after_request=False):
    missing = []
    for added_at, kind, section_title, key in items:
        try:
            state = item_discover_missing_subs(
                key,
                kind=kind,
                added_at=added_at,
                section_title=section_title,
                languages=config.lang_list.copy(),
                internal=cast_bool(Prefs["subtitles.scan.embedded"]),
                external=cast_bool(Prefs["subtitles.scan.external"])
            )
            if state:
                # (added_at, item_id, title, item, missing_languages)
                missing.append(state)
        except:
            Log.Error("Something went wrong when getting the state of item %s: %s", key, traceback.format_exc())
        if sleep_after_request:
            time.sleep(sleep_after_request)
    return missing


def refresh_item(item):
    if not config.no_refresh:
        Plex["library/metadata"].refresh(item)


