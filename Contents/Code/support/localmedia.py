# coding=utf-8

import os

import config
import helpers
import subtitlehelpers

from config import config as sz_config


SECONDARY_TAGS = ['forced', 'normal', 'default', 'embedded', 'embedded-forced', 'custom', 'hi', 'cc', 'sdh']


def find_subtitles(part):
    lang_sub_map = {}
    part_filename = helpers.unicodize(part.file)
    part_basename = os.path.splitext(os.path.basename(part_filename))[0]
    use_filesystem = helpers.cast_bool(Prefs["subtitles.save.filesystem"])
    sub_dir_custom = Prefs["subtitles.save.subFolder.Custom"].strip() \
        if Prefs["subtitles.save.subFolder.Custom"] else None

    use_sub_subfolder = Prefs["subtitles.save.subFolder"] != "current folder" and not sub_dir_custom
    sub_subfolder = None
    paths = [os.path.dirname(part_filename)] if use_filesystem else []

    global_folders = []

    if use_filesystem:
        # Check for local subtitles subdirectory
        sub_dir_base = paths[0]
        sub_dir_list = []

        if use_sub_subfolder:
            # got selected subfolder
            sub_subfolder = os.path.join(sub_dir_base, Prefs["subtitles.save.subFolder"])
            sub_dir_list.append(sub_subfolder)
            sub_subfolder = os.path.normpath(helpers.unicodize(sub_subfolder))

        if sub_dir_custom:
            # got custom subfolder
            sub_dir_custom = os.path.normpath(sub_dir_custom)
            if os.path.isdir(sub_dir_custom) and os.path.isabs(sub_dir_custom):
                # absolute folder
                sub_dir_list.append(sub_dir_custom)
                global_folders.append(sub_dir_custom)
            else:
                # relative folder
                fld = os.path.join(sub_dir_base, sub_dir_custom)
                sub_dir_list.append(fld)

        for sub_dir in sub_dir_list:
            if os.path.isdir(sub_dir):
                paths.append(sub_dir)

        # Check for a global subtitle location
        global_subtitle_folder = os.path.join(Core.app_support_path, 'Subtitles')
        if os.path.exists(global_subtitle_folder):
            paths.append(global_subtitle_folder)
            global_folders.append(global_subtitle_folder)

    # normalize all paths
    paths = [os.path.normpath(helpers.unicodize(path)) for path in paths]

    # We start by building a dictionary of files to their absolute paths. We also need to know
    # the number of media files that are actually present, in case the found local media asset
    # is limited to a single instance per media file.
    #
    file_paths = {}
    total_media_files = 0
    media_files = []
    for path in paths:
        for file_path_listing in os.listdir(path.encode(sz_config.fs_encoding)):
            # When using os.listdir with a unicode path, it will always return a string using the
            # NFD form. However, we internally are using the form NFC and therefore need to convert
            # it to allow correct regex / comparisons to be performed.
            #
            file_path_listing = helpers.unicodize(file_path_listing)
            if os.path.isfile(os.path.join(path, file_path_listing).encode(sz_config.fs_encoding)):
                file_paths[file_path_listing.lower()] = os.path.join(path, file_path_listing)

            # If we've found an actual media file, we should record it.
            (root, ext) = os.path.splitext(file_path_listing)
            if ext.lower()[1:] in config.VIDEO_EXTS:
                total_media_files += 1

                # collect found media files
                media_files.append(root)

    # cleanup any leftover subtitle if no associated media file was found
    if use_filesystem and helpers.cast_bool(Prefs["subtitles.autoclean"]):
        for path in paths:
            # only housekeep in sub_subfolder if sub_subfolder is used
            if use_sub_subfolder and path != sub_subfolder and not sz_config.advanced.thorough_cleaning:
                continue

            # we can't housekeep the global subtitle folders as we don't know about *all* media files
            # in a library; skip them
            skip_path = False
            for fld in global_folders:
                if path.startswith(fld):
                    Log.Info("Skipping housekeeping of folder: %s", path)
                    skip_path = True
                    break

            if skip_path:
                continue

            for file_path_listing in os.listdir(path.encode(sz_config.fs_encoding)):
                file_path_listing = helpers.unicodize(file_path_listing)
                enc_fn = os.path.join(path, file_path_listing).encode(sz_config.fs_encoding)

                if os.path.isfile(enc_fn):
                    (root, ext) = os.path.splitext(file_path_listing)
                    # it's a subtitle file
                    if ext.lower()[1:] in config.SUBTITLE_EXTS_BASE:
                        # get fn without forced/default/normal tag
                        split_tag = root.rsplit(".", 1)
                        if len(split_tag) > 1 and split_tag[1].lower() in SECONDARY_TAGS:
                            root = split_tag[0]

                        # get associated media file name without language
                        sub_fn = subtitlehelpers.ENDSWITH_LANGUAGECODE_RE.sub("", root)

                        # subtitle basename and basename without possible language tag  not found in collected
                        # media files? kill.
                        if root not in media_files and sub_fn not in media_files:
                            Log.Info("Removing leftover subtitle: %s", os.path.join(path, file_path_listing))
                            try:
                                os.remove(enc_fn)
                            except (OSError, IOError):
                                Log.Error("Removing failed")

    Log('Looking for subtitle media in %d paths with %d media files.', len(paths), total_media_files)
    Log('Paths: %s', ", ".join([helpers.unicodize(p) for p in paths]))

    for file_path in file_paths.values():
        local_filename = os.path.basename(file_path)
        bn, ext = os.path.splitext(local_filename)
        local_basename = helpers.unicodize(bn)

        # get fn without forced/default/normal tag
        split_tag = local_basename.rsplit(".", 1)
        has_additional_tag = False
        if len(split_tag) > 1 and split_tag[1].lower() in SECONDARY_TAGS:
            local_basename = split_tag[0]
            has_additional_tag = True

        # split off possible language tag
        local_basename2 = local_basename.rsplit('.', 1)[0]
        filename_matches_part = local_basename == part_basename or local_basename2 == part_basename
        filename_contains_part = part_basename in local_basename

        if not ext.lower()[1:] in config.SUBTITLE_EXTS:
            continue

        # if the file is located within the global subtitle folders and its name doesn't match exactly, ignore it
        if global_folders and not filename_matches_part:
            skip_path = False
            for fld in global_folders:
                if file_path.startswith(fld):
                    skip_path = True
                    break

            if skip_path:
                continue

        # determine whether to pick up the subtitle based on our match strictness
        if not filename_matches_part:
            if sz_config.ext_match_strictness == "strict" or (
                            sz_config.ext_match_strictness == "loose" and not filename_contains_part):
                # Log.Debug("%s doesn't match %s, skipping" % (helpers.unicodize(local_filename),
                #                                             helpers.unicodize(part_basename)))
                continue

        subtitle_helper = subtitlehelpers.subtitle_helpers(file_path)
        if subtitle_helper is not None:
            local_lang_map = subtitle_helper.process_subtitles(part)
            for new_language, subtitles in local_lang_map.items():

                # Add the possible new language along with the located subtitles so that we can validate them
                # at the end...
                #
                if not lang_sub_map.has_key(new_language):
                    lang_sub_map[new_language] = []
                lang_sub_map[new_language] = lang_sub_map[new_language] + subtitles

    # add known metadata subs to our sub list
    if not use_filesystem:
        for language, sub_list in subtitlehelpers.get_subtitles_from_metadata(part).iteritems():
            if sub_list:
                if language not in lang_sub_map:
                    lang_sub_map[language] = []
                lang_sub_map[language] = lang_sub_map[language] + sub_list

    # Now whack subtitles that don't exist anymore.
    for language in lang_sub_map.keys():
        part.subtitles[language].validate_keys(lang_sub_map[language])

    # Now whack the languages that don't exist anymore.
    for language in list(set(part.subtitles.keys()) - set(lang_sub_map.keys())):
        part.subtitles[language].validate_keys({})
