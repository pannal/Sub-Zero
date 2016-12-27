# coding=utf-8

import os
import re
import inspect

import subliminal
import subliminal_patch
from babelfish import Language
from subzero.lib.io import FileIO, get_viable_encoding
from subzero.constants import PLUGIN_NAME, PLUGIN_IDENTIFIER, MOVIE, SHOW
from lib import Plex
from helpers import check_write_permissions, cast_bool

SUBTITLE_EXTS = ['utf', 'utf8', 'utf-8', 'srt', 'smi', 'rt', 'ssa', 'aqt', 'jss', 'ass', 'idx', 'sub', 'txt', 'psb']
VIDEO_EXTS = ['3g2', '3gp', 'asf', 'asx', 'avc', 'avi', 'avs', 'bivx', 'bup', 'divx', 'dv', 'dvr-ms', 'evo', 'fli', 'flv',
              'm2t', 'm2ts', 'm2v', 'm4v', 'mkv', 'mov', 'mp4', 'mpeg', 'mpg', 'mts', 'nsv', 'nuv', 'ogm', 'ogv', 'tp',
              'pva', 'qt', 'rm', 'rmvb', 'sdp', 'svq3', 'strm', 'ts', 'ty', 'vdr', 'viv', 'vob', 'vp3', 'wmv', 'wpl', 'wtv', 'xsp', 'xvid',
              'webm']

IGNORE_FN = ("subzero.ignore", ".subzero.ignore", ".nosz")

VERSION_RE = re.compile(ur'CFBundleVersion.+?<string>([0-9\.]+)</string>', re.DOTALL)


def int_or_default(s, default):
    try:
        return int(s)
    except ValueError:
        return default


class Config(object):
    version = None
    full_version = None
    lang_list = None
    subtitle_destination_folder = None
    providers = None
    provider_settings = None
    max_recent_items_per_library = 200
    permissions_ok = False
    missing_permissions = None
    ignore_sz_files = False
    ignore_paths = None
    fs_encoding = None
    notify_executable = None
    sections = None
    enabled_sections = None
    enforce_encoding = False
    chmod = None
    forced_only = False

    initialized = False

    def initialize(self):
        self.fs_encoding = get_viable_encoding()
        self.version = self.get_version()
        self.full_version = u"%s %s" % (PLUGIN_NAME, self.version)
        self.lang_list = self.get_lang_list()
        self.subtitle_destination_folder = self.get_subtitle_destination_folder()
        self.providers = self.get_providers()
        self.provider_settings = self.get_provider_settings()
        self.max_recent_items_per_library = int_or_default(Prefs["scheduler.max_recent_items_per_library"], 2000)
        self.sections = list(Plex["library"].sections())
        self.missing_permissions = []
        self.ignore_sz_files = cast_bool(Prefs["subtitles.ignore_fs"])
        self.ignore_paths = self.parse_ignore_paths()
        self.enabled_sections = self.check_enabled_sections()
        self.permissions_ok = self.check_permissions()
        self.notify_executable = self.check_notify_executable()
        self.enforce_encoding = cast_bool(Prefs['subtitles.enforce_encoding'])
        self.chmod = self.check_chmod()
        self.forced_only = cast_bool(Prefs["subtitles.only_foreign"])
        self.initialized = True

    def refresh_permissions_status(self):
        self.permissions_ok = self.check_permissions()

    def check_permissions(self):
        if not Prefs["subtitles.save.filesystem"] or not Prefs["check_permissions"]:
            return True

        self.missing_permissions = []
        use_ignore_fs = Prefs["subtitles.ignore_fs"]
        all_permissions_ok = True
        for section in self.sections:
            if section.key not in self.enabled_sections:
                continue

            title = section.title
            for location in section:
                path_str = location.path
                if isinstance(path_str, unicode):
                    path_str = path_str.encode(self.fs_encoding)

                if use_ignore_fs:
                    # check whether we've got an ignore file inside the section path
                    if self.is_physically_ignored(path_str):
                        continue

                if self.is_path_ignored(path_str):
                    # is the path in our ignored paths setting?
                    continue

                # section not ignored, check for write permissions
                if not check_write_permissions(path_str):
                    # not enough permissions
                    self.missing_permissions.append((title, location.path))
                    all_permissions_ok = False

        return all_permissions_ok

    def get_version(self):
        curDir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
        info_file_path = os.path.abspath(os.path.join(curDir, "..", "..", "Info.plist"))
        data = FileIO.read(info_file_path)
        result = VERSION_RE.search(data)
        if result:
            return result.group(1)

    def parse_ignore_paths(self):
        paths = Prefs["subtitles.ignore_paths"]
        if paths:
            try:
                return [path.strip() for path in paths.split(",")]
            except:
                Log.Error("Couldn't parse your ignore paths settings: %s" % paths)
        return []

    def is_physically_ignored(self, folder):
        # check whether we've got an ignore file inside the path
        for ifn in IGNORE_FN:
            if os.path.isfile(os.path.join(folder, ifn)):
                Log.Info(u'Ignoring "%s" because "%s" exists', folder, ifn)
                return True

        return False

    def is_path_ignored(self, fn):
        for path in self.ignore_paths:
            if fn.startswith(path):
                return True
        return False

    def check_notify_executable(self):
        fn = Prefs["notify_executable"]
        if not fn:
            return

        splitted_fn = fn.split()
        exe_fn = splitted_fn[0]
        arguments = [arg.strip() for arg in splitted_fn[1:]]

        if os.path.isfile(exe_fn) and os.access(exe_fn, os.X_OK):
            return exe_fn, arguments
        Log.Error("Notify executable not existing or not executable: %s" % exe_fn)

    def refresh_enabled_sections(self):
        self.enabled_sections = self.check_enabled_sections()

    def check_enabled_sections(self):
        enabled_for_primary_agents = []
        enabled_sections = {}

        # find which agents we're enabled for
        for agent in Plex.agents():
            if not agent.primary:
                continue

            for t in list(agent.media_types):
                if t.media_type in (MOVIE, SHOW):
                    related_agents = Plex.primary_agent(agent.identifier, t.media_type)
                    for a in related_agents:
                        if a.identifier == PLUGIN_IDENTIFIER and a.enabled:
                            enabled_for_primary_agents.append(agent.identifier)

        # find the libraries that use them
        for library in self.sections:
            if library.agent in enabled_for_primary_agents:
                enabled_sections[library.key] = library

        Log.Debug(u"I'm enabled for: %s" % [lib.title for key, lib in enabled_sections.iteritems()])
        return enabled_sections

    # Prepare a list of languages we want subs for
    def get_lang_list(self):
        l = {Language.fromietf(Prefs["langPref1"])}
        lang_custom = Prefs["langPrefCustom"].strip()

        if Prefs['subtitles.only_one']:
            return l

        if Prefs["langPref2"] != "None":
            l.update({Language.fromietf(Prefs["langPref2"])})

        if Prefs["langPref3"] != "None":
            l.update({Language.fromietf(Prefs["langPref3"])})

        if len(lang_custom) and lang_custom != "None":
            for lang in lang_custom.split(u","):
                lang = lang.strip()
                try:
                    real_lang = Language.fromietf(lang)
                except:
                    try:
                        real_lang = Language.fromname(lang)
                    except:
                        continue
                l.update({real_lang})

        return l

    def get_subtitle_destination_folder(self):
        if not Prefs["subtitles.save.filesystem"]:
            return

        fld_custom = Prefs["subtitles.save.subFolder.Custom"].strip() if cast_bool(Prefs["subtitles.save.subFolder.Custom"]) else None
        return fld_custom or (Prefs["subtitles.save.subFolder"] if Prefs["subtitles.save.subFolder"] != "current folder" else None)

    def get_providers(self):
        providers = {'opensubtitles': cast_bool(Prefs['provider.opensubtitles.enabled']),
                     #'thesubdb': Prefs['provider.thesubdb.enabled'],
                     'podnapisi': cast_bool(Prefs['provider.podnapisi.enabled']),
                     'addic7ed': cast_bool(Prefs['provider.addic7ed.enabled']),
                     'tvsubtitles': cast_bool(Prefs['provider.tvsubtitles.enabled']),
                     'sabbz': cast_bool(Prefs['provider.sabbz.enabled'])
                     }

        # ditch non-forced-subtitles-reporting providers
        if cast_bool(Prefs['subtitles.only_foreign']):
            providers["addic7ed"] = False
            providers["tvsubtitles"] = False
            providers["sabbz"] = False

        return filter(lambda prov: providers[prov], providers)

    def get_provider_settings(self):
        provider_settings = {'addic7ed': {'username': Prefs['provider.addic7ed.username'],
                                          'password': Prefs['provider.addic7ed.password'],
                                          'use_random_agents': cast_bool(Prefs['provider.addic7ed.use_random_agents']),
                                          },
                             'opensubtitles': {'username': Prefs['provider.opensubtitles.username'],
                                               'password': Prefs['provider.opensubtitles.password'],
                                               'use_tag_search': cast_bool(Prefs['provider.opensubtitles.use_tags']),
                                               'only_foreign': cast_bool(Prefs['subtitles.only_foreign'])
                                               },
                             'podnapisi': {
                                 'only_foreign': cast_bool(Prefs['subtitles.only_foreign'])
                             },
                             }

        return provider_settings

    def check_chmod(self):
        val = Prefs["subtitles.save.chmod"]
        if not val or not len(val):
            return

        wrong_chmod = False
        if len(val) != 4:
            wrong_chmod = True

        try:
            return int(val, 8)
        except ValueError:
            wrong_chmod = True

        if wrong_chmod:
            Log.Warning("Chmod setting ignored, please use only 4-digit integers with leading 0 (e.g.: 775)")

    def init_subliminal_patches(self):
        # configure custom subtitle destination folders for scanning pre-existing subs
        Log.Debug("Patching subliminal ...")
        dest_folder = self.subtitle_destination_folder
        subliminal_patch.patch_video.CUSTOM_PATHS = [dest_folder] if dest_folder else []
        subliminal_patch.patch_video.INCLUDE_EXOTIC_SUBS = cast_bool(Prefs["subtitles.scan.exotic_ext"])
        subliminal_patch.patch_provider_pool.DOWNLOAD_TRIES = int(Prefs['subtitles.try_downloads'])
        subliminal.video.Episode.scores["addic7ed_boost"] = int(Prefs['provider.addic7ed.boost_by'])


config = Config()
