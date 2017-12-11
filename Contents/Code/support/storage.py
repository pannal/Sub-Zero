# coding=utf-8

import datetime
import os
import pprint
import copy
import types

from subliminal_patch.core import save_subtitles as subliminal_save_subtitles
from subzero.subtitle_storage import StoredSubtitlesManager

from subtitlehelpers import force_utf8
from config import config
from helpers import notify_executable, get_title_for_video_metadata, cast_bool, force_unicode
from plex_media import PMSMediaProxy
from support.items import get_item


def get_subtitle_storage():
    return StoredSubtitlesManager(Data, get_item)


def store_subtitle_info(scanned_video_part_map, downloaded_subtitles, storage_type, mode="a"):
    """
    stores information about downloaded subtitles in plex's Dict()
    """
    for video, video_subtitles in downloaded_subtitles.items():
        part = scanned_video_part_map[video]
        part_id = str(part.id)
        video_id = str(video.id)
        plex_item = get_item(video_id)
        metadata = video.plexapi_metadata
        title = get_title_for_video_metadata(metadata)

        subtitle_storage = get_subtitle_storage()
        stored_subs = subtitle_storage.load_or_new(plex_item)

        for subtitle in video_subtitles:
            lang = str(subtitle.language)
            subtitle.normalize()
            Log.Debug(u"Adding subtitle to storage: %s, %s, %s, %s" % (video_id, part_id, title,
                                                                       subtitle.guess_encoding()))
            ret_val = stored_subs.add(part_id, lang, subtitle, storage_type, mode=mode)

            if ret_val:
                Log.Debug("Subtitle stored")

            else:
                Log.Debug("Subtitle already existing in storage")

        Log.Debug("Saving subtitle storage for %s" % video_id)
        subtitle_storage.save(stored_subs)
        subtitle_storage.destroy()


def reset_storage(key):
    """
    resets the Dict[key] storage, thanks to https://docs.google.com/document/d/1hhLjV1pI-TA5y91TiJq64BdgKwdLnFt4hWgeOqpz1NA/edit#
    We can't use the nice Plex interface for this, as it calls get multiple times before set
    #Plex[":/plugins/*/prefs"].set("com.plexapp.agents.subzero", "reset_storage", False)
    """

    Log.Debug("resetting storage")
    Dict[key] = {}
    Dict.Save()


def log_storage(key):
    if not key:
        Log.Debug(pprint.pformat(getattr(Dict, "_dict")))
    if key in Dict:
        Log.Debug(pprint.pformat(Dict[key]))


def get_target_folder(file_path):
    fld = None
    fld_custom = Prefs["subtitles.save.subFolder.Custom"].strip() \
        if Prefs["subtitles.save.subFolder.Custom"] else None

    if fld_custom or Prefs["subtitles.save.subFolder"] != "current folder":
        # specific subFolder requested, create it if it doesn't exist
        fld_base = os.path.split(file_path)[0]
        if fld_custom:
            if fld_custom.startswith("/"):
                # absolute folder
                fld = fld_custom
            else:
                fld = os.path.join(fld_base, fld_custom)
        else:
            fld = os.path.join(fld_base, Prefs["subtitles.save.subFolder"])
        fld = force_unicode(fld)
        if not os.path.exists(fld):
            os.makedirs(fld)
    return fld


def save_subtitles_to_file(subtitles, tags=None, forced_tag=None):
    forced_tag = forced_tag or config.forced_only
    for video, video_subtitles in subtitles.items():
        if not video_subtitles:
            continue

        if not isinstance(video, types.StringTypes):
            file_path = video.name
        else:
            file_path = video

        fld = get_target_folder(video)
        subliminal_save_subtitles(file_path, video_subtitles, directory=fld, single=cast_bool(Prefs['subtitles.only_one']),
                                  chmod=config.chmod, forced_tag=forced_tag, path_decoder=force_unicode,
                                  debug_mods=config.debug_mods, formats=config.subtitle_formats, tags=tags)
    return True


def save_subtitles_to_metadata(videos, subtitles):
    for video, video_subtitles in subtitles.items():
        mediaPart = videos[video]
        for subtitle in video_subtitles:
            content = subtitle.get_modified_content(debug=config.debug_mods)

            if not isinstance(mediaPart, Framework.api.agentkit.MediaPart):
                # we're being handed a Plex.py model instance here, not an internal PMS MediaPart object.
                # get the correct one
                mp = PMSMediaProxy(video.id).get_part(mediaPart.id)
            else:
                mp = mediaPart
            mp.subtitles[Locale.Language.Match(subtitle.language.alpha2)][subtitle.id] = Proxy.Media(content, ext="srt")
    return True


def save_subtitles(scanned_video_part_map, downloaded_subtitles, mode="a", bare_save=False, mods=None):
    """
     
    :param scanned_video_part_map: 
    :param downloaded_subtitles: 
    :param mode: 
    :param bare_save: don't trigger anything; don't store information
    :param mods: enabled mods
    :return: 
    """
    meta_fallback = False
    save_successful = False

    # big fixme: scanned_video_part_map isn't needed to the current extent. rewrite.

    if mods:
        for video, video_subtitles in downloaded_subtitles.items():
            if not video_subtitles:
                continue

            for subtitle in video_subtitles:
                Log.Info("Applying mods: %s to %s", mods, subtitle)
                subtitle.mods = mods
                subtitle.plex_media_fps = video.fps

    storage = "metadata"
    save_to_fs = cast_bool(Prefs['subtitles.save.filesystem'])
    if save_to_fs:
        storage = "filesystem"
        try:
            Log.Debug("Using filesystem as subtitle storage")
            save_subtitles_to_file(downloaded_subtitles)
        except OSError:
            if cast_bool(Prefs["subtitles.save.metadata_fallback"]):
                meta_fallback = True
                storage = "metadata"
            else:
                raise
        else:
            save_successful = True

    if not save_to_fs or meta_fallback:
        if meta_fallback:
            Log.Debug("Using metadata as subtitle storage, because filesystem storage failed")
        else:
            Log.Debug("Using metadata as subtitle storage")
        save_successful = save_subtitles_to_metadata(scanned_video_part_map, downloaded_subtitles)

    if not bare_save and save_successful and config.notify_executable:
        notify_executable(config.notify_executable, scanned_video_part_map, downloaded_subtitles, storage)

    if not bare_save and save_successful:
        store_subtitle_info(scanned_video_part_map, downloaded_subtitles, storage, mode=mode)

    return save_successful

