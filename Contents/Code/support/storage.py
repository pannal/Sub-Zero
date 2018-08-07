# coding=utf-8

import datetime
import os
import pprint
import copy
import traceback
import types

from subliminal_patch.core import save_subtitles as subliminal_save_subtitles
from subzero.subtitle_storage import StoredSubtitlesManager
from subzero.lib.io import FileIO

from subtitlehelpers import force_utf8
from config import config
from helpers import notify_executable, get_title_for_video_metadata, cast_bool, force_unicode
from plex_media import PMSMediaProxy
from support.items import get_item


def get_subtitle_storage():
    return StoredSubtitlesManager(Data, Thread, get_item)


def store_subtitle_info(scanned_video_part_map, downloaded_subtitles, storage_type, mode="a", set_current=True):
    """
    stores information about downloaded subtitles in plex's Dict()
    """
    subtitle_storage = get_subtitle_storage()
    for video, video_subtitles in downloaded_subtitles.items():
        part = scanned_video_part_map[video]
        part_id = str(part.id)
        video_id = str(video.id)
        plex_item = get_item(video_id)
        if not plex_item:
            Log.Warning("Plex item not found: %s", video_id)
            continue

        metadata = video.plexapi_metadata
        title = get_title_for_video_metadata(metadata)

        stored_subs = subtitle_storage.load(video_id)
        is_new = False
        if not stored_subs:
            is_new = True
            Log.Debug(u"Creating new subtitle storage: %s, %s", video_id, part_id)
            stored_subs = subtitle_storage.new(plex_item)

        for subtitle in video_subtitles:
            lang = str(subtitle.language)
            subtitle.normalize()
            Log.Debug(u"Adding subtitle to storage: %s, %s, %s, %s, %s" % (video_id, part_id, lang, title,
                                                                           subtitle.guess_encoding()))

            last_mod = None
            if subtitle.storage_path:
                last_mod = datetime.datetime.fromtimestamp(os.path.getmtime(subtitle.storage_path))

            ret_val = stored_subs.add(part_id, lang, subtitle, storage_type, mode=mode, last_mod=last_mod,
                                      set_current=set_current)

            if ret_val:
                Log.Debug("Subtitle stored")

            else:
                Log.Debug("Subtitle already existing in storage")

        if is_new or video_subtitles:
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

        fld = get_target_folder(file_path)
        subliminal_save_subtitles(file_path, video_subtitles, directory=fld, single=cast_bool(Prefs['subtitles.only_one']),
                                  chmod=config.chmod, forced_tag=forced_tag, path_decoder=force_unicode,
                                  debug_mods=config.debug_mods, formats=config.subtitle_formats, tags=tags)
    return True


def save_subtitles_to_metadata(videos, subtitles, is_forced=False):
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
            pm = Proxy.Media(content, ext="srt", forced="1" if is_forced else None)
            lang = Locale.Language.Match(subtitle.language.alpha2)
            mp.subtitles[lang].validate_keys({})
            mp.subtitles[lang]["subzero"] = pm
    return True


def save_subtitles(scanned_video_part_map, downloaded_subtitles, mode="a", bare_save=False, mods=None,
                   set_current=True, is_forced=False):
    """
     
    :param set_current: save the subtitle as the current one
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

    if set_current:
        if save_to_fs:
            try:
                Log.Debug("Using filesystem as subtitle storage")
                save_subtitles_to_file(downloaded_subtitles, forced_tag=is_forced)
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
            save_successful = save_subtitles_to_metadata(scanned_video_part_map, downloaded_subtitles,
                                                         is_forced=is_forced)

        if not bare_save and save_successful and config.notify_executable:
            notify_executable(config.notify_executable, scanned_video_part_map, downloaded_subtitles, storage)

    if not bare_save and save_successful or not set_current:
        store_subtitle_info(scanned_video_part_map, downloaded_subtitles, storage, mode=mode, set_current=set_current)

    return save_successful


def get_pack_id(subtitle):
    return "%s_%s" % (subtitle.provider_name, subtitle.numeric_id)


def get_pack_data(subtitle):
    subtitle_id = get_pack_id(subtitle)

    archive = os.path.join(config.pack_cache_dir, subtitle_id + ".archive")
    if os.path.isfile(archive):
        Log.Info("Loading archive from pack cache: %s", subtitle_id)
        try:
            data = FileIO.read(archive, 'rb')

            return data
        except:
            Log.Error("Couldn't load archive from pack cache: %s: %s", subtitle_id, traceback.format_exc())


def store_pack_data(subtitle, data):
    subtitle_id = get_pack_id(subtitle)

    archive = os.path.join(config.pack_cache_dir, subtitle_id + ".archive")

    Log.Info("Storing archive in pack cache: %s", subtitle_id)
    try:
        FileIO.write(archive, data, 'wb')

    except:
        Log.Error("Couldn't store archive in pack cache: %s: %s", subtitle_id, traceback.format_exc())
