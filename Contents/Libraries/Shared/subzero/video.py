# coding=utf-8

import logging
import os

from babelfish.exceptions import LanguageError
from babelfish import Language
from subliminal_patch import scan_video, refine, search_external_subtitles

logger = logging.getLogger(__name__)


def has_external_subtitle(part_id, stored_subs, language):
    stored_sub = stored_subs.get_any(part_id, language)
    if stored_sub and stored_sub.storage_type == "filesystem":
        return True


def parse_video(fn, video_info, hints, external_subtitles=False, embedded_subtitles=False, known_embedded=None,
                forced_only=False, no_refining=False, dry_run=False, ignore_all=False, stored_subs=None):

    logger.debug("Parsing video: %s, hints: %s", os.path.basename(fn), hints)
    video = scan_video(fn, hints=hints, dont_use_actual_file=dry_run or no_refining)

    if no_refining:
        logger.debug("Taking parse_video shortcut")
        return video

    # refiners
    # fixme: add prefs for filebot, sonarr and radarr
    refine_kwargs = {
        "episode_refiners": ('filebot', 'tvdb', 'sz_omdb',),#('drone',),
        "movie_refiners": ('filebot', 'sz_omdb',),
        "embedded_subtitles": False,
        "sonarr": {
            "base_url": "http://127.0.0.1:8989/nzbdrone",
            "api_key": "xxxxxxxxxxxxxxxxxxxx"
        },

    }

    # our own metadata refiner :)
    if "stream" in video_info:
        for key, value in video_info["stream"].iteritems():
            if hasattr(video, key) and not getattr(video, key):
                logger.info(u"Adding stream %s info: %s", key, value)
                setattr(video, key, value)

    plex_title = video_info.get("original_title") or video_info.get("title")
    if hints["type"] == "episode":
        plex_title = video_info.get("original_title") or video_info.get("series")

    year = video_info.get("year")
    if not video.year and year:
        logger.info(u"Adding PMS year info: %s", year)
        video.year = year

    refine(video, **refine_kwargs)

    if hints["type"] == "movie" and not video.imdb_id:
        if plex_title:
            logger.info(u"Adding PMS title/original_title info: %s", plex_title)
            old_title = video.title
            video.title = plex_title.replace(" - ", " ").replace(" -", " ").replace("- ", " ")

            # re-refine with new info
            logger.info(u"Re-refining with movie title: '%s' instead of '%s'", plex_title, old_title)
            refine(video, **refine_kwargs)

        # still no match? add our own data
        if not video.imdb_id:
            video.imdb_id = video_info.get("imdb_id")
            if video.imdb_id:
                logger.info(u"Adding PMS imdb_id info: %s", video.imdb_id)

    if hints["type"] == "episode":
        if not video.series_tvdb_id and not video.tvdb_id and plex_title:
            # add our title
            logger.info(u"Adding PMS title/original_title info: %s", plex_title)
            old_title = video.series
            video.series = plex_title

            # re-refine with new info
            logger.info(u"Re-refining with series title: '%s' instead of '%s'", plex_title, old_title)
            refine(video, **refine_kwargs)

        # still no match? add our own data
        if not video.series_tvdb_id:
            logger.info(u"Adding PMS series_tvdb_id info: %s", video_info.get("series_tvdb_id"))
            video.series_tvdb_id = video_info.get("series_tvdb_id")

        if not video.tvdb_id:
            logger.info(u"Adding PMS tvdb_id info: %s", video_info.get("tvdb_id"))
            video.tvdb_id = video_info.get("tvdb_id")

    # did it match?
    if (hints["type"] == "episode" and not video.series_tvdb_id and not video.tvdb_id and
            not video.series_imdb_id) or (hints["type"] == "movie" and not video.imdb_id):
        logger.warning("Couldn't find corresponding series/movie in online databases, continuing")

    # scan for external subtitles
    external_langs_found = set(search_external_subtitles(video.name, forced_tag=forced_only).values())

    # found external subtitles should be considered?
    if external_subtitles:
        # |= is update, thanks plex
        video.subtitle_languages.update(external_langs_found)

    else:
        # did we already download subtitles for this?
        if not ignore_all and stored_subs and external_langs_found:
            for lang in external_langs_found:
                if has_external_subtitle(video_info["plex_part"].id, stored_subs, lang):
                    logger.info("Not re-downloading subtitle for language %s, it already exists on the filesystem",
                                lang)
                    video.subtitle_languages.add(lang)

    # add known embedded subtitles
    if embedded_subtitles and known_embedded:
        embedded_subtitle_languages = set()
        # mp4 and stuff, check burned in
        for language in known_embedded:
            try:
                embedded_subtitle_languages.add(Language.fromalpha3b(language))
            except LanguageError:
                logger.error('Embedded subtitle track language %r is not a valid language', language)
                embedded_subtitle_languages.add(Language('und'))

            logger.debug('Found embedded subtitle %r', embedded_subtitle_languages)
            video.subtitle_languages.update(embedded_subtitle_languages)

    # guess special
    if hints["type"] == "episode":
        if video.season == 0 or video.episode == 0:
            video.is_special = True
        else:
            # check parent folder name
            if os.path.dirname(fn).split(os.path.sep)[-1].lower() in ("specials", "season 00"):
                video.is_special = True

    return video
