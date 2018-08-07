# coding=utf-8
import traceback
import helpers
from babelfish.exceptions import LanguageError

from support.lib import Plex, get_intent
from support.plex_media import get_stream_fps
from support.storage import get_subtitle_storage
from support.config import config, TEXT_SUBTITLE_EXTS

from subzero.video import parse_video, set_existing_languages
from subzero.language import language_from_stream


def scan_video(pms_video_info, ignore_all=False, hints=None, rating_key=None, providers=None, skip_hashing=False):
    """
    returnes a subliminal/guessit-refined parsed video
    :param pms_video_info:
    :param ignore_all:
    :param hints:
    :param rating_key:
    :return:
    """
    embedded_subtitles = not ignore_all and Prefs['subtitles.scan.embedded']
    external_subtitles = not ignore_all and Prefs['subtitles.scan.external']

    plex_part = pms_video_info["plex_part"]

    if ignore_all:
        Log.Debug("Force refresh intended.")

    Log.Debug("Scanning video: %s, external_subtitles=%s, embedded_subtitles=%s" % (
        plex_part.file, external_subtitles, embedded_subtitles))

    known_embedded = []
    parts = []
    for media in list(Plex["library"].metadata(rating_key))[0].media:
        parts += media.parts

    plexpy_part = None
    for part in parts:
        if int(part.id) == int(plex_part.id):
            plexpy_part = part

    # embedded subtitles
    # fixme: skip the whole scanning process if known_embedded == wanted languages?
    if plexpy_part:
        if embedded_subtitles:
            for stream in plexpy_part.streams:
                # subtitle stream
                if stream.stream_type == 3:
                    is_forced = helpers.is_stream_forced(stream)

                    if (config.forced_only and is_forced) or \
                            (not config.forced_only and not is_forced):

                        # embedded subtitle
                        # fixme: tap into external subtitles here instead of scanning for ourselves later?
                        if stream.codec and getattr(stream, "index", None):
                            if config.exotic_ext or stream.codec.lower() in config.text_based_formats:
                                lang = None
                                try:
                                    lang = language_from_stream(stream.language_code)
                                except LanguageError:
                                    Log.Debug("Couldn't detect embedded subtitle stream language: %s", stream.language_code)

                                # treat unknown language as lang1?
                                if not lang and config.treat_und_as_first:
                                    lang = list(config.lang_list)[0]

                                if lang:
                                    known_embedded.append(lang.alpha3)
    else:
        Log.Warn("Part %s missing of %s, not able to scan internal streams", plex_part.id, rating_key)

    Log.Debug("Known embedded: %r", known_embedded)

    subtitle_storage = get_subtitle_storage()
    stored_subs = subtitle_storage.load(rating_key)
    subtitle_storage.destroy()

    try:
        # get basic video info scan (filename)
        video = parse_video(plex_part.file, hints, skip_hashing=config.low_impact_mode or skip_hashing,
                            providers=providers)

        if not ignore_all:
            set_existing_languages(video, pms_video_info, external_subtitles=external_subtitles,
                                   embedded_subtitles=embedded_subtitles, known_embedded=known_embedded,
                                   forced_only=config.forced_only, stored_subs=stored_subs, languages=config.lang_list,
                                   only_one=config.only_one)

        # add video fps info
        video.fps = plex_part.fps
        return video

    except ValueError:
        Log.Warn("File could not be guessed: %s: %s", plex_part.file, traceback.format_exc())


def scan_videos(videos, ignore_all=False, providers=None, skip_hashing=False):
    """
    receives a list of videos containing dictionaries returned by media_to_videos
    :param videos:
    :param kind: series or movies
    :return: dictionary of subliminal.video.scan_video, key=subliminal scanned video, value=plex file part
    """
    ret = {}
    for video in videos:
        intent = get_intent()
        force_refresh = intent.get("force", video["id"], video["series_id"], video["season_id"])
        Log.Debug("Determining force-refresh (video: %s, series: %s, season: %s), result: %s"
                  % (video["id"], video["series_id"], video["season_id"], force_refresh))

        hints = helpers.get_item_hints(video)
        video["plex_part"].fps = get_stream_fps(video["plex_part"].streams)
        p = providers or config.get_providers(media_type="series" if video["type"] == "episode" else "movies")
        scanned_video = scan_video(video, ignore_all=force_refresh or ignore_all, hints=hints,
                                   rating_key=video["id"], providers=p,
                                   skip_hashing=skip_hashing)

        if not scanned_video:
            continue

        scanned_video.id = video["id"]
        part_metadata = video.copy()
        del part_metadata["plex_part"]
        scanned_video.plexapi_metadata = part_metadata
        scanned_video.ignore_all = force_refresh
        ret[scanned_video] = video["plex_part"]
    return ret
