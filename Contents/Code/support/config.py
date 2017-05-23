# coding=utf-8

import os
import re
import inspect

import datetime

import subliminal
import subliminal_patch
from babelfish import Language
from subzero.lib.io import FileIO, get_viable_encoding
from subzero.constants import PLUGIN_NAME, PLUGIN_IDENTIFIER, MOVIE, SHOW
from lib import Plex
from helpers import check_write_permissions, cast_bool

SUBTITLE_EXTS = ['utf', 'utf8', 'utf-8', 'srt', 'smi', 'rt', 'ssa', 'aqt', 'jss', 'ass', 'idx', 'sub', 'txt', 'psb']
VIDEO_EXTS = ['3g2', '3gp', 'asf', 'asx', 'avc', 'avi', 'avs', 'bivx', 'bup', 'divx', 'dv', 'dvr-ms', 'evo', 'fli',
              'flv',
              'm2t', 'm2ts', 'm2v', 'm4v', 'mkv', 'mov', 'mp4', 'mpeg', 'mpg', 'mts', 'nsv', 'nuv', 'ogm', 'ogv', 'tp',
              'pva', 'qt', 'rm', 'rmvb', 'sdp', 'svq3', 'strm', 'ts', 'ty', 'vdr', 'viv', 'vob', 'vp3', 'wmv', 'wpl',
              'wtv', 'xsp', 'xvid',
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
    server_log_path = None
    app_support_path = None
    universal_plex_token = None

    enable_channel = True
    enable_agent = True
    pin = None
    lock_menu = False
    lock_advanced_menu = False
    locked = False
    pin_valid_minutes = 10
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
    exotic_ext = False
    treat_und_as_first = False
    ext_match_strictness = False
    use_activities = False
    activity_mode = None

    initialized = False

    def initialize(self):
        self.fs_encoding = get_viable_encoding()
        self.version = self.get_version()
        self.full_version = u"%s %s" % (PLUGIN_NAME, self.version)
        self.server_log_path = self.get_server_log_path()
        self.app_support_path = Core.app_support_path
        self.universal_plex_token = self.get_universal_plex_token()

        self.set_plugin_mode()
        self.set_plugin_lock()
        self.set_activity_modes()

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
        self.exotic_ext = cast_bool(Prefs["subtitles.scan.exotic_ext"])
        self.treat_und_as_first = cast_bool(Prefs["subtitles.language.treat_und_as_first"])
        self.ext_match_strictness = self.determine_ext_sub_strictness()
        self.initialized = True

    def get_server_log_path(self):
        # find log handler
        for handler in Core.log.handlers:
            if getattr(getattr(handler, "__class__"), "__name__") in (
                    'FileHandler', 'RotatingFileHandler', 'TimedRotatingFileHandler'):
                plugin_log_file = handler.baseFilename

                if plugin_log_file:
                    server_log_file = os.path.realpath(os.path.join(plugin_log_file, "../../Plex Media Server.log"))
                    if os.path.isfile(server_log_file):
                        return server_log_file

    def get_universal_plex_token(self):
        # thanks to: https://forums.plex.tv/discussion/247136/read-current-x-plex-token-in-an-agent-ensure-that-a-http-request-gets-executed-exactly-once#latest
        pref_path = os.path.join(self.app_support_path, "Preferences.xml")
        if os.path.exists(pref_path):
            try:
                global_prefs = Core.storage.load(pref_path)
                return XML.ElementFromString(global_prefs).xpath('//Preferences/@PlexOnlineToken')[0]
            except:
                Log.Warn("Couldn't determine Plex Token")
        else:
            Log("Did NOT find Preferences file - please check logfile and hierarchy. Aborting!")

    def set_plugin_mode(self):
        if Prefs["plugin_mode"] == "only agent":
            self.enable_channel = False
        elif Prefs["plugin_mode"] == "only channel":
            self.enable_agent = False

    def set_plugin_lock(self):
        if Prefs["plugin_pin_mode"] in ("channel menu", "advanced menu"):
            # check pin
            pin = Prefs["plugin_pin"]
            if not pin or not len(pin):
                Log.Warn("PIN enabled but not set, disabling PIN!")
                return

            pin = pin.strip()
            try:
                int(pin)
            except ValueError:
                Log.Warn("PIN has to be an integer (0-9)")
            self.pin = pin
            self.lock_advanced_menu = Prefs["plugin_pin_mode"] == "advanced menu"
            self.lock_menu = Prefs["plugin_pin_mode"] == "channel menu"

            try:
                self.pin_valid_minutes = int(Prefs["plugin_pin_valid_for"].strip())
            except ValueError:
                pass

    @property
    def pin_correct(self):
        if isinstance(Dict["pin_correct_time"], datetime.datetime) \
                and Dict["pin_correct_time"] + datetime.timedelta(
                    minutes=self.pin_valid_minutes) > datetime.datetime.now():
            return True

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

        fld_custom = Prefs["subtitles.save.subFolder.Custom"].strip() if cast_bool(
            Prefs["subtitles.save.subFolder.Custom"]) else None
        return fld_custom or (
        Prefs["subtitles.save.subFolder"] if Prefs["subtitles.save.subFolder"] != "current folder" else None)

    def get_providers(self):
        providers = {'opensubtitles': cast_bool(Prefs['provider.opensubtitles.enabled']),
                     # 'thesubdb': Prefs['provider.thesubdb.enabled'],
                     'podnapisi': cast_bool(Prefs['provider.podnapisi.enabled']),
                     'addic7ed': cast_bool(Prefs['provider.addic7ed.enabled']),
                     'tvsubtitles': cast_bool(Prefs['provider.tvsubtitles.enabled']),
					 'legendastv': cast_bool(Prefs['provider.legendastv.enabled'])
                     }

        # ditch non-forced-subtitles-reporting providers
        if cast_bool(Prefs['subtitles.only_foreign']):
            providers["addic7ed"] = False
            providers["tvsubtitles"] = False

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
                             'legendastv': {'username': Prefs['provider.legendastv.username'],
											'password': Prefs['provider.legendastv.password'],
											'epScore': Prefs['provider.legendastv.epScore']
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
            Log.Warn("Chmod setting ignored, please use only 4-digit integers with leading 0 (e.g.: 775)")

    def determine_ext_sub_strictness(self):
        val = Prefs["subtitles.scan.filename_strictness"]
        if val == "any":
            return "any"
        elif val.startswith("loose"):
            return "loose"
        return "strict"

    def set_activity_modes(self):
        val = Prefs["activity.on_playback"]
        if val == "never":
            self.use_activities = False
            return

        self.use_activities = True
        if val == "current media item":
            self.activity_mode = "refresh"
        elif val == "hybrid: current item or next episode":
            self.activity_mode = "hybrid"
        else:
            self.activity_mode = "next_episode"

    def init_subliminal_patches(self):
        # configure custom subtitle destination folders for scanning pre-existing subs
        Log.Debug("Patching subliminal ...")
        dest_folder = self.subtitle_destination_folder
        subliminal_patch.patch_video.CUSTOM_PATHS = [dest_folder] if dest_folder else []
        subliminal_patch.patch_video.INCLUDE_EXOTIC_SUBS = self.exotic_ext
        subliminal_patch.patch_provider_pool.DOWNLOAD_TRIES = int(Prefs['subtitles.try_downloads'])
        subliminal.video.Episode.scores["addic7ed_boost"] = int(Prefs['provider.addic7ed.boost_by'])


config = Config()
config.initialize()
