# coding=utf-8

import os

import helpers
from items import get_item
from lib import Plex
from support.config import TEXT_SUBTITLE_EXTS, config


def get_metadata_dict(item, part, add):
    data = {
        "item": item,
        "section": item.section.title,
        "path": part.file,
        "folder": os.path.dirname(part.file),
        "filename": os.path.basename(part.file)
    }
    data.update(add)
    return data


imdb_guid_identifier = "com.plexapp.agents.imdb://"
tvdb_guid_identifier = "com.plexapp.agents.thetvdb://"


def get_plexapi_stream_info(plex_item, part_id=None):
    d = {"stream": {}}
    data = d["stream"]

    # find current part
    current_part = None
    current_media = None
    for media in plex_item.media:
        for part in media.parts:
            if not part_id or str(part.id) == part_id:
                current_part = part
                current_media = media
                break
        if current_part:
            break

    if not current_part:
        return d

    data["video_codec"] = current_media.video_codec
    if current_media.audio_codec:
        data["audio_codec"] = current_media.audio_codec.upper()

        if data["audio_codec"] == "DCA":
            data["audio_codec"] = "DTS"

    if current_media.audio_channels == 8:
        data["audio_channels"] = "7.1"

    elif current_media.audio_channels == 6:
        data["audio_channels"] = "5.1"
    else:
        data["audio_channels"] = "%s.0" % str(current_media.audio_channels)

    # iter streams
    for stream in current_part.streams:
        if stream.stream_type == 1:
            # video stream
            data["resolution"] = "%s%s" % (current_media.video_resolution,
                                           "i" if stream.scan_type != "progressive" else "p")
            break

    return d


def media_to_videos(media, kind="series"):
    """
    iterates through media and returns the associated parts (videos)
    :param media:
    :param kind:
    :return:
    """
    videos = []

    # this is a Show or a Movie object
    plex_item = get_item(media.id)
    year = plex_item.year
    original_title = plex_item.title_original

    if kind == "series":
        for season in media.seasons:
            season_object = media.seasons[season]
            for episode in media.seasons[season].episodes:
                ep = media.seasons[season].episodes[episode]

                tvdb_id = None
                series_tvdb_id = None
                if tvdb_guid_identifier in ep.guid:
                    tvdb_id = ep.guid[len(tvdb_guid_identifier):].split("?")[0]
                    series_tvdb_id = tvdb_id.split("/")[0]

                # get plex item via API for additional metadata
                plex_episode = get_item(ep.id)
                stream_info = get_plexapi_stream_info(plex_episode)

                for item in media.seasons[season].episodes[episode].items:
                    for part in item.parts:
                        videos.append(
                            get_metadata_dict(plex_episode, part,
                                              dict(stream_info, **{"plex_part": part, "type": "episode",
                                                                    "title": ep.title,
                                                                    "series": media.title, "id": ep.id, "year": year,
                                                                    "series_id": media.id,
                                                                    "season_id": season_object.id,
                                                                    "imdb_id": None, "series_tvdb_id": series_tvdb_id,
                                                                    "tvdb_id": tvdb_id,
                                                                    "original_title": original_title,
                                                                    "episode": plex_episode.index,
                                                                    "season": plex_episode.season.index,
                                                                    "section": plex_episode.section.title
                                                                    })
                                              )
                        )
    else:
        stream_info = get_plexapi_stream_info(plex_item)
        imdb_id = None
        if imdb_guid_identifier in media.guid:
            imdb_id = media.guid[len(imdb_guid_identifier):].split("?")[0]
        for item in media.items:
            for part in item.parts:
                videos.append(
                    get_metadata_dict(plex_item, part, dict(stream_info, **{"plex_part": part, "type": "movie",
                                                                             "title": media.title, "id": media.id,
                                                                             "series_id": None, "year": year,
                                                                             "season_id": None, "imdb_id": imdb_id,
                                                                             "original_title": original_title,
                                                                             "series_tvdb_id": None, "tvdb_id": None,
                                                                             "section": plex_item.section.title})
                                      )
                )
    return videos


IGNORE_FN = ("subzero.ignore", ".subzero.ignore", ".nosz")


def get_stream_fps(streams):
    """
    accepts a list of plex streams or a list of the plex api streams
    """
    for stream in streams:
        # video
        stream_type = getattr(stream, "type", getattr(stream, "stream_type", None))
        if stream_type == 1:
            return getattr(stream, "frameRate", getattr(stream, "frame_rate", "25.000"))
    return "25.000"


def get_media_item_ids(media, kind="series"):
    # fixme: does this work correctly for full series force-refreshes and its intents?
    ids = [media.id]
    if kind == "series":
        for season in media.seasons:
            for episode in media.seasons[season].episodes:
                ids.append(media.seasons[season].episodes[episode].id)

    return ids


def get_all_parts(plex_item):
    parts = []
    for media in plex_item.media:
        parts += media.parts

    return parts


def get_embedded_subtitle_streams(part, requested_language=None, skip_duplicate_unknown=True, get_forced=None):
    streams = []
    has_unknown = False
    for stream in part.streams:
        # subtitle stream
        if stream.stream_type == 3 and not stream.stream_key and stream.codec in TEXT_SUBTITLE_EXTS:
            language = helpers.get_language_from_stream(stream.language_code)
            is_unknown = False
            found_requested_language = requested_language and requested_language == language
            is_forced = helpers.is_stream_forced(stream)

            if get_forced is not None:
                if (get_forced and not is_forced) or (not get_forced and is_forced):
                    continue

            if not language and config.treat_und_as_first:
                # only consider first unknown subtitle stream
                if has_unknown and skip_duplicate_unknown:
                    continue

                language = list(config.lang_list)[0]
                is_unknown = True
                has_unknown = True

            if not requested_language or found_requested_language or has_unknown:
                streams.append({"stream": stream, "is_unknown": is_unknown, "language": language,
                                "is_forced": is_forced})

                if found_requested_language:
                    break

    return streams


def get_part(plex_item, part_id):
    for media in plex_item.media:
        for part in media.parts:
            if str(part.id) == str(part_id):
                return part


def get_plex_metadata(rating_key, part_id, item_type, plex_item=None):
    """
    uses the Plex 3rd party API accessor to get metadata information

    :param rating_key: movie or episode
    :param part_id:
    :param item_type:
    :return:
    """

    if not plex_item:
        plex_item = get_item(rating_key)

    if not plex_item:
        return

    # find current part
    current_part = get_part(plex_item, part_id)

    if not current_part:
        raise helpers.PartUnknownException("Part unknown")

    stream_info = get_plexapi_stream_info(plex_item, part_id)

    # get normalized metadata
    # fixme: duplicated logic of media_to_videos
    if item_type == "episode":
        show = list(Plex["library"].metadata(plex_item.show.rating_key))[0]
        year = show.year
        tvdb_id = None
        series_tvdb_id = None
        original_title = show.title_original
        if tvdb_guid_identifier in plex_item.guid:
            tvdb_id = plex_item.guid[len(tvdb_guid_identifier):].split("?")[0]
            series_tvdb_id = tvdb_id.split("/")[0]
        metadata = get_metadata_dict(plex_item, current_part,
                                     dict(stream_info,
                                          **{"plex_part": current_part, "type": "episode", "title": plex_item.title,
                                             "series": plex_item.show.title, "id": plex_item.rating_key,
                                             "series_id": plex_item.show.rating_key,
                                             "season_id": plex_item.season.rating_key,
                                             "imdb_id": None,
                                             "year": year,
                                             "tvdb_id": tvdb_id,
                                             "series_tvdb_id": series_tvdb_id,
                                             "original_title": original_title,
                                             "season": plex_item.season.index,
                                             "episode": plex_item.index
                                             })
                                     )
    else:
        imdb_id = None
        original_title = plex_item.title_original
        if imdb_guid_identifier in plex_item.guid:
            imdb_id = plex_item.guid[len(imdb_guid_identifier):].split("?")[0]
        metadata = get_metadata_dict(plex_item, current_part,
                                     dict(stream_info, **{"plex_part": current_part, "type": "movie",
                                                           "title": plex_item.title, "id": plex_item.rating_key,
                                                           "series_id": None,
                                                           "season_id": None,
                                                           "imdb_id": imdb_id,
                                                           "year": plex_item.year,
                                                           "tvdb_id": None,
                                                           "series_tvdb_id": None,
                                                           "original_title": original_title,
                                                           "season": None,
                                                           "episode": None,
                                                           "section": plex_item.section.title})
                                     )
    return metadata


def get_blacklist_from_part_map(video_part_map, languages):
    from support.storage import get_subtitle_storage
    subtitle_storage = get_subtitle_storage()
    blacklist = []
    for video, part in video_part_map.iteritems():
        stored_subs = subtitle_storage.load_or_new(video.plexapi_metadata["item"])
        for language in languages:
            current_bl, subs = stored_subs.get_blacklist(part.id, language)
            if not current_bl:
                continue

            blacklist = blacklist + [(str(a), str(b)) for a, b in current_bl.keys()]

    subtitle_storage.destroy()

    return blacklist


class PMSMediaProxy(object):
    """
    Proxy object for getting data from a mediatree items "internally" via the PMS

    note: this could be useful later on: Media.TV_Show(getattr(Metadata, "_access_point"), id=XXXXXX)
    """

    def __init__(self, media_id):
        self.mediatree = Media.TreeForDatabaseID(media_id)

    def get_part(self, part_id=None):
        """
        walk the mediatree until the given part was found; if no part was given, return the first one
        :param part_id:
        :return:
        """
        m = self.mediatree
        while 1:
            if m.items:
                media_item = m.items[0]
                if not part_id:
                    return media_item.parts[0] if media_item.parts else None

                for part in media_item.parts:
                    if str(part.id) == str(part_id):
                        return part
                break

            if not m.children:
                break

            m = m.children[0]

    def get_all_parts(self):
        """
        walk the mediatree until the given part was found; if no part was given, return the first one
        :param part_id:
        :return:
        """
        m = self.mediatree
        parts = []
        while 1:
            if m.items:
                media_item = m.items[0]
                for part in media_item.parts:
                    parts.append(part)
                break

            if not m.children:
                break

            m = m.children[0]
        return parts
