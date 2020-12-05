# coding=utf-8
import copy
import json
import os
import re
import inspect
import sys
import rarfile
import jstyleson
import datetime
import stat
import traceback

import subliminal
import subliminal_patch
import subzero.constants
import lib
from subliminal.exceptions import ServiceUnavailable, DownloadLimitExceeded, AuthenticationError, \
    DownloadLimitPerDayExceeded
from subliminal_patch.core import is_windows_special_path
from whichdb import whichdb

from subliminal_patch.exceptions import TooManyRequests, APIThrottled
from subzero.language import Language
from subliminal.cli import MutexLock
from subzero.lib.io import FileIO, get_viable_encoding
from subzero.lib.dict import Dicked
from subzero.lib.which import find_executable
from subzero.util import get_root_path
from subzero.constants import PLUGIN_NAME, PLUGIN_IDENTIFIER, MOVIE, SHOW, MEDIA_TYPE_TO_STRING
from subzero.prefs import get_user_prefs, update_user_prefs
from dogpile.cache.region import register_backend as register_cache_backend
from lib import Plex
from helpers import check_write_permissions, cast_bool, cast_int, mswindows

register_cache_backend(
    "subzero.cache.file", "subzero.cache_backends.file", "SZFileBackend")

SUBTITLE_EXTS_BASE = ['utf', 'utf8', 'utf-8', 'srt', 'smi', 'rt', 'ssa', 'aqt', 'jss', 'ass', 'idx', 'sub', 'psb',
                      'vtt']
SUBTITLE_EXTS = SUBTITLE_EXTS_BASE + ["txt"]

TEXT_SUBTITLE_EXTS = ("srt", "ass", "ssa", "vtt", "mov_text")
VIDEO_EXTS = ['3g2', '3gp', 'asf', 'asx', 'avc', 'avi', 'avs', 'bivx', 'bup', 'divx', 'dv', 'dvr-ms', 'evo', 'fli',
              'flv',
              'm2t', 'm2ts', 'm2v', 'm4v', 'mkv', 'mov', 'mp4', 'mpeg', 'mpg', 'mts', 'nsv', 'nuv', 'ogm', 'ogv', 'tp',
              'pva', 'qt', 'rm', 'rmvb', 'sdp', 'svq3', 'strm', 'ts', 'ty', 'vdr', 'viv', 'vob', 'vp3', 'wmv', 'wpl',
              'wtv', 'xsp', 'xvid',
              'webm']

EXCLUDE_FN = ("subzero.ignore", ".subzero.ignore", "subzero.exclude", ".subzero.exclude", ".nosz")
INCLUDE_FN = ("subzero.include", ".subzero.include", ".sz")

VERSION_RE = re.compile(ur'CFBundleVersion.+?<string>([0-9\.]+)</string>', re.DOTALL)
DEV_RE = re.compile(ur'PlexPluginDevMode.+?<string>([01]+)</string>', re.DOTALL)


def int_or_default(s, default):
    try:
        return int(s)
    except ValueError:
        return default


VALID_THROTTLE_EXCEPTIONS = (TooManyRequests, DownloadLimitExceeded, DownloadLimitPerDayExceeded,
                             ServiceUnavailable, APIThrottled)

PROVIDER_THROTTLE_MAP = {
    "default": {
        TooManyRequests: (datetime.timedelta(hours=1), "1 hour"),
        DownloadLimitExceeded: (datetime.timedelta(hours=3), "3 hours"),
        DownloadLimitPerDayExceeded: (datetime.timedelta(hours=4), "4 hours"),
        ServiceUnavailable: (datetime.timedelta(minutes=20), "20 minutes"),
        APIThrottled: (datetime.timedelta(minutes=10), "10 minutes"),
        AuthenticationError: (datetime.timedelta(hours=2), "2 hours"),
    },
    "opensubtitles": {
        TooManyRequests: (datetime.timedelta(hours=3), "3 hours"),
        DownloadLimitExceeded: (datetime.timedelta(hours=6), "6 hours"),
        APIThrottled: (datetime.timedelta(seconds=15), "15 seconds"),
    },
    "addic7ed": {
        DownloadLimitExceeded: (datetime.timedelta(hours=3), "3 hours"),
        TooManyRequests: (datetime.timedelta(minutes=5), "5 minutes"),
        AuthenticationError: (datetime.timedelta(hours=24), "24 hours"),
    }
}


class Config(object):
    config_version = 3
    libraries_root = None
    plugin_info = ""
    version = None
    full_version = None
    plugin_log_path = None
    server_log_path = None
    app_support_path = None
    data_path = None
    data_items_path = None
    universal_plex_token = None
    plex_token = None
    is_development = False
    dbm_supported = False
    pms_request_timeout = 15
    low_impact_mode = False
    new_style_cache = False
    pack_cache_dir = None
    advanced = None
    debug_i18n = False

    normal_subs = False
    forced_also = False
    forced_only = False
    include = False
    enable_channel = True
    enable_agent = True
    pin = None
    lock_menu = False
    lock_advanced_menu = False
    locked = False
    pin_valid_minutes = 10
    subtitle_destination_folder = None
    subtitle_formats = None
    max_recent_items_per_library = 200
    permissions_ok = False
    missing_permissions = None
    include_exclude_sz_files = False
    include_exclude_paths = None
    fs_encoding = None
    notify_executable = None
    sections = None
    enabled_sections = None
    remove_hi = False
    remove_tags = False
    fix_ocr = False
    fix_common = False
    fix_upper = False
    reverse_rtl = False
    colors = ""
    chmod = None
    exotic_ext = False
    treat_und_as_first = False
    subtitle_sub_dir = None, None
    ext_match_strictness = False
    default_mods = None
    debug_mods = False
    react_to_activities = False
    activity_mode = None
    no_refresh = False
    plex_transcoder = None
    refiner_settings = None
    exact_filenames = False
    only_one = False
    any_language_is_enough = False
    embedded_auto_extract = False
    ietf_as_alpha3 = False
    unrar = None
    adv_cfg_path = None
    use_custom_dns = None
    anticaptcha_token = None
    anticaptcha_cls = None
    has_anticaptcha = False
    mediainfo_bin = None

    store_recently_played_amount = 40

    initialized = False

    def initialize(self):
        self.libraries_root = os.path.abspath(os.path.join(get_root_path(), ".."))
        self.init_libraries()

        if is_windows_special_path:
            Log.Warn("The Plex metadata folder is residing inside a folder with special characters. "
                     "Multithreading and playback activities will be disabled.")

        self.fs_encoding = get_viable_encoding()
        self.plugin_info = self.get_plugin_info()
        self.is_development = self.get_dev_mode()
        self.version = self.get_version()
        self.full_version = u"%s %s" % (PLUGIN_NAME, self.version)
        self.set_log_paths()
        self.app_support_path = Core.app_support_path
        self.data_path = getattr(Data, "_core").storage.data_path
        self.data_items_path = os.path.join(self.data_path, "DataItems")
        self.universal_plex_token = self.get_universal_plex_token()
        self.plex_token = os.environ.get("PLEXTOKEN", self.universal_plex_token)
        self.new_style_cache = cast_bool(Prefs['new_style_cache'])
        self.pack_cache_dir = self.get_pack_cache_dir()
        try:
            self.migrate_prefs()
        except:
            Log.Exception("Catastrophic failure when running prefs migration")

        subzero.constants.DEFAULT_TIMEOUT = lib.DEFAULT_TIMEOUT = self.pms_request_timeout = \
            min(cast_int(Prefs['pms_request_timeout'], 15), 45)
        self.low_impact_mode = cast_bool(Prefs['low_impact_mode'])
        self.advanced = self.get_advanced_config()
        self.debug_i18n = self.advanced.debug_i18n

        os.environ["SZ_USER_AGENT"] = self.get_user_agent()
        os.environ["ANTICAPTCHA_ACCOUNT_KEY"] = self.anticaptcha_token = str(Prefs["anticaptcha.api_key"]) or ""
        acs = str(Prefs["anticaptcha.service"])
        if acs and acs != "none":
            os.environ["ANTICAPTCHA_CLASS"] = self.anticaptcha_cls = acs
        self.has_anticaptcha = self.anticaptcha_token and self.anticaptcha_cls

        self.setup_proxies()
        self.set_plugin_mode()
        self.set_plugin_lock()
        self.set_activity_modes()
        self.parse_rename_mode()

        self.normal_subs = Prefs["subtitles.when"] != "Never"
        self.forced_also = self.normal_subs and Prefs["subtitles.when_forced"] != "Never"
        self.forced_only = not self.normal_subs and Prefs["subtitles.when_forced"] != "Never"
        self.include = \
            Prefs["subtitles.include_exclude_mode"] == "disable SZ for all items by default, use include lists"
        self.subtitle_destination_folder = self.get_subtitle_destination_folder()
        self.subtitle_formats = self.get_subtitle_formats()
        self.max_recent_items_per_library = int_or_default(Prefs["scheduler.max_recent_items_per_library"], 2000)
        self.sections = list(Plex["library"].sections())
        self.missing_permissions = []
        self.include_exclude_sz_files = cast_bool(Prefs["subtitles.include_exclude_fs"])
        self.include_exclude_paths = self.parse_include_exclude_paths()
        self.enabled_sections = self.check_enabled_sections()
        self.permissions_ok = self.check_permissions()
        self.notify_executable = self.check_notify_executable()
        self.remove_hi = cast_bool(Prefs['subtitles.remove_hi'])
        self.remove_tags = cast_bool(Prefs['subtitles.remove_tags'])
        self.fix_ocr = cast_bool(Prefs['subtitles.fix_ocr'])
        self.fix_common = cast_bool(Prefs['subtitles.fix_common'])
        self.fix_upper = cast_bool(Prefs['subtitles.fix_only_uppercase'])
        self.reverse_rtl = cast_bool(Prefs['subtitles.reverse_rtl'])
        self.colors = Prefs['subtitles.colors'] if Prefs['subtitles.colors'] != "don't change" else None
        self.chmod = self.check_chmod()
        self.exotic_ext = cast_bool(Prefs["subtitles.scan.exotic_ext"])
        self.treat_und_as_first = cast_bool(Prefs["subtitles.language.treat_und_as_first"])
        self.subtitle_sub_dir = self.get_subtitle_sub_dir()
        self.ext_match_strictness = self.determine_ext_sub_strictness()
        self.default_mods = self.get_default_mods()
        self.debug_mods = cast_bool(Prefs['log_debug_mods'])
        self.no_refresh = os.environ.get("SZ_NO_REFRESH", False)
        self.plex_transcoder = self.get_plex_transcoder()
        self.only_one = cast_bool(Prefs['subtitles.only_one'])
        self.any_language_is_enough = Prefs['subtitles.any_language_is_enough']
        self.embedded_auto_extract = cast_bool(Prefs["subtitles.embedded.autoextract"])
        self.ietf_as_alpha3 = cast_bool(Prefs["subtitles.language.ietf_normalize"])
        self.use_custom_dns = self.parse_custom_dns()
        if not self.advanced.dont_use_mediainfo_mp4:
            self.mediainfo_bin = self.advanced.mediainfo_bin or find_executable("mediainfo")
        self.initialized = True

    def migrate_prefs(self):
        config_version = 0 if "config_version" not in Dict else Dict["config_version"]
        if config_version < self.config_version:
            user_prefs = get_user_prefs(Prefs, Log)
            if user_prefs:
                update_prefs = {}
                for i in range(config_version, self.config_version):
                    version = i+1
                    func = "migrate_prefs_to_%i" % version
                    if hasattr(self, func):
                        Log.Info("Migrating user prefs to version %i" % version)
                        try:
                            mig_result = getattr(self, func)(user_prefs, from_version=config_version,
                                                             to_version=version,
                                                             current_version=self.config_version,
                                                             migrated_prefs=update_prefs)
                            update_prefs.update(mig_result)
                            Dict["config_version"] = version
                            Dict.Save()
                            Log.Info("User prefs migrated to version %i" % version)
                        except:
                            Log.Exception("User prefs migration from %i to %i failed" % (self.config_version, version))
                            break

                if update_prefs:
                    update_user_prefs(update_prefs, Prefs, Log)
            else:
                Dict["config_version"] = self.config_version
                Dict.Save()

    def migrate_prefs_to_1(self, user_prefs, **kwargs):
        update_prefs = {}
        if "subtitles.only_foreign" in user_prefs and user_prefs["subtitles.only_foreign"] == "true":
            update_prefs["subtitles.when_forced"] = "1"
            update_prefs["subtitles.when"] = "0"

        return update_prefs

    def migrate_prefs_to_2(self, user_prefs, **kwargs):
        update_prefs = {}
        if "subtitles.ignore_fs" in user_prefs and user_prefs["subtitles.ignore_fs"] == "true":
            update_prefs["subtitles.include_exclude_fs"] = "true"

        if "subtitles.ignore_paths" in user_prefs and user_prefs["subtitles.ignore_paths"]:
            update_prefs["subtitles.include_exclude_paths"] = user_prefs["subtitles.ignore_paths"]

        return update_prefs

    def migrate_prefs_to_3(self, user_prefs, **kwargs):
        if config.new_style_cache:
            self.init_cache()
            try:
                subliminal.region.backend.clear()
            except:
                pass
        return {}

    def init_libraries(self):
        try_executables = []
        custom_unrar = os.environ.get("SZ_UNRAR_TOOL")
        if custom_unrar:
            if os.path.isfile(custom_unrar):
                try_executables.append(custom_unrar)

        unrar_exe = None
        if Core.runtime.os == "Windows":
            unrar_exe = os.path.abspath(os.path.join(self.libraries_root, "Windows", "i386", "UnRAR", "UnRAR.exe"))

        elif Core.runtime.os == "MacOSX":
            unrar_exe = os.path.abspath(os.path.join(self.libraries_root, "MacOSX", "i386", "UnRAR", "unrar"))

        elif Core.runtime.os == "Linux":
            unrar_exe = os.path.abspath(os.path.join(self.libraries_root, "Linux", Core.runtime.cpu, "UnRAR", "unrar"))

        if unrar_exe and os.path.isfile(unrar_exe):
            try_executables.append(unrar_exe)

        try_executables.append("unrar")

        for exe in try_executables:
            rarfile.UNRAR_TOOL = exe
            rarfile.ORIG_UNRAR_TOOL = exe
            if os.path.isfile(exe) and not os.access(exe, os.X_OK):
                st = os.stat(exe)
                try:
                    Log.Debug("setting generic executable permissions for %s", exe)
                    # fixme: too broad?
                    os.chmod(exe, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                except:
                    Log.Debug("failed setting generic executable permissions for %s: %s", exe, traceback.format_exc())
                    try:
                        Log.Debug("setting executable permissions for %s", exe)
                        os.chmod(exe, st.st_mode | stat.S_IEXEC)
                    except:
                        Log.Debug("failed setting executable permissions for %s: %s", exe, traceback.format_exc())
            try:
                rarfile.custom_check([rarfile.UNRAR_TOOL], True)
            except:
                Log.Debug("custom check failed for: %s", exe)
                continue

            rarfile.OPEN_ARGS = rarfile.ORIG_OPEN_ARGS
            rarfile.EXTRACT_ARGS = rarfile.ORIG_EXTRACT_ARGS
            rarfile.TEST_ARGS = rarfile.ORIG_TEST_ARGS
            Log.Info("Using UnRAR from: %s", exe)
            self.unrar = exe
            return

        Log.Warn("UnRAR not found")

    def init_cache(self):
        if self.new_style_cache:
            subliminal.region.configure('subzero.cache.file', expiration_time=datetime.timedelta(days=180),
                                        arguments={'appname': "sz_cache",
                                                   'app_cache_dir': self.data_path},
                                        replace_existing_backend=True)
            Log.Info("Using new style file based cache!")
            return

        names = ['dbhash', 'gdbm', 'dbm']
        dbfn = None
        self.dbm_supported = False

        # try importing dbm modules
        if Core.runtime.os != "Windows":
            impawrt = None
            try:
                impawrt = getattr(sys.modules['__main__'], "__builtins__").get("__import__")
            except:
                pass

            if impawrt:
                for name in names:
                    try:
                        impawrt(name)
                    except:
                        continue
                    if not self.dbm_supported:
                        self.dbm_supported = name
                        break

                if self.dbm_supported:
                    # anydbm checks; try guessing the format and importing the correct module
                    dbfn = os.path.join(config.data_items_path, 'subzero.dbm')
                    db_which = whichdb(dbfn)
                    if db_which is not None and db_which != "":
                        try:
                            impawrt(db_which)
                        except ImportError:
                            self.dbm_supported = False

        if self.dbm_supported:
            try:
                subliminal.region.configure('dogpile.cache.dbm', expiration_time=datetime.timedelta(days=30),
                                            arguments={'filename': dbfn,
                                                       'lock_factory': MutexLock},
                                            replace_existing_backend=True)
                Log.Info("Using file based cache!")
                return
            except:
                self.dbm_supported = False

        Log.Warn("Not using file based cache!")
        subliminal.region.configure('dogpile.cache.memory', replace_existing_backend=True)

    def sync_cache(self):
        if not self.new_style_cache:
            return
        Log.Debug("Syncing cache")
        subliminal.region.backend.sync()

    def get_pack_cache_dir(self):
        pack_cache_dir = os.path.join(config.data_path, "pack_cache")
        if not os.path.isdir(pack_cache_dir):
            os.makedirs(pack_cache_dir)

        return pack_cache_dir

    def get_advanced_config(self):
        paths = []
        if Prefs['path_to_advanced_settings']:
            paths = [
                Prefs['path_to_advanced_settings'],
                os.path.join(Prefs['path_to_advanced_settings'], "advanced_settings.json")
            ]

        paths.append(os.path.join(config.data_path, "advanced_settings.json"))

        for path in paths:
            if os.path.isfile(path):
                data = FileIO.read(path, "r")

                d = Dicked(**jstyleson.loads(data))
                self.adv_cfg_path = path
                Log.Info(u"Using advanced settings from: %s", path)
                return d

        return Dicked()

    def set_log_paths(self):
        # find log handler
        for handler in Core.log.handlers:
            cls_name = getattr(getattr(handler, "__class__"), "__name__")
            if cls_name in ('FileHandler', 'RotatingFileHandler', 'TimedRotatingFileHandler'):
                plugin_log_file = handler.baseFilename
                if cls_name in ("RotatingFileHandler", "TimedRotatingFileHandler"):
                    handler.backupCount = int_or_default(Prefs['log_rotate_keep'], 5)

                if os.path.isfile(os.path.realpath(plugin_log_file)):
                    self.plugin_log_path = plugin_log_file

                if plugin_log_file:
                    server_log_file = os.path.realpath(os.path.join(plugin_log_file, "../../Plex Media Server.log"))
                    if os.path.isfile(server_log_file):
                        self.server_log_path = server_log_file

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
            Log.Warn("Did NOT find Preferences file - most likely Windows OS. Otherwise please check logfile and hierarchy.")

        # fixme: windows

    def set_plugin_mode(self):
        self.enable_agent = True
        self.enable_channel = True

        # any provider enabled?
        if not self.providers_enabled:
            self.enable_agent = False
            self.enable_channel = False
            Log.Warn("No providers enabled, disabling agent and interface!")
            return

        if Prefs["plugin_mode2"] == "only agent":
            self.enable_channel = False
        elif Prefs["plugin_mode2"] == "only interface":
            self.enable_agent = False

    def set_plugin_lock(self):
        if Prefs["plugin_pin_mode2"] in ("interface", "advanced menu"):
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
            self.lock_advanced_menu = Prefs["plugin_pin_mode2"] == "advanced menu"
            self.lock_menu = Prefs["plugin_pin_mode2"] == "interface"

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
        if not cast_bool(Prefs["subtitles.save.filesystem"]) or not cast_bool(Prefs["check_permissions"]):
            return True

        self.missing_permissions = []
        use_include_exclude_fs = self.include_exclude_sz_files
        all_permissions_ok = True
        for section in self.sections:
            if section.key not in self.enabled_sections:
                continue

            title = section.title
            for location in section:
                path_str = location.path
                if isinstance(path_str, unicode):
                    path_str = path_str.encode(self.fs_encoding)

                if not os.path.exists(path_str):
                    continue

                if use_include_exclude_fs:
                    # check whether we've got an ignore file inside the section path
                    if not self.is_physically_wanted(path_str):
                        continue

                if not self.is_path_wanted(path_str):
                    # is the path in our ignored paths setting?
                    continue

                # section not ignored, check for write permissions
                if not check_write_permissions(path_str):
                    # not enough permissions
                    self.missing_permissions.append((title, location.path))
                    all_permissions_ok = False

        return all_permissions_ok

    def get_version(self):
        return self.get_bare_version() + ("" if not self.is_development else " DEV")

    def get_bare_version(self):
        result = VERSION_RE.search(self.plugin_info)

        if result:
            return result.group(1)
        return "2.x.x.x"

    def get_user_agent(self):
        return "Sub-Zero/%s" % (self.get_bare_version() + ("" if not self.is_development else "-dev"))

    def get_dev_mode(self):
        dev = DEV_RE.search(self.plugin_info)
        if dev and dev.group(1) == "1":
            return True

    def get_plugin_info(self):
        curDir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
        info_file_path = os.path.abspath(os.path.join(curDir, "..", "..", "Info.plist"))
        return FileIO.read(info_file_path)

    def parse_include_exclude_paths(self):
        paths = Prefs["subtitles.include_exclude_paths"]
        if paths and paths != "None":
            try:
                return [p for p in [path.strip() for path in paths.split(",")]
                        if p != "None" and os.path.exists(p)]
            except:
                Log.Error("Couldn't parse your include/exclude paths settings: %s" % paths)
        return []

    def is_physically_wanted(self, folder, ref_fn=None):
        # check whether we've got an ignore file inside the path
        ret_val = self.include
        ref_list = INCLUDE_FN if self.include else EXCLUDE_FN
        for ifn in ref_list:
            if os.path.isfile(os.path.join(folder, ifn)):
                if ref_fn:
                    Log.Info(u'%s "%s" because "%s" exists in "%s"', "Including" if self.include else "Ignoring",
                             ref_fn, ifn, folder)
                else:
                    Log.Info(u'%s "%s" because "%s" exists', "Including" if self.include else "Ignoring", folder, ifn)

                return ret_val

        return not ret_val

    def is_path_wanted(self, fn):
        ret_val = self.include
        for path in self.include_exclude_paths:
            if fn.startswith(path):
                return ret_val
        return not ret_val

    def check_notify_executable(self):
        fn = Prefs["notify_executable"]
        if not fn:
            return

        got_args = "%(" in fn
        if got_args:
            first_arg_pos = fn.index("%(")
            exe_fn = fn[:first_arg_pos].strip()
            arguments = [arg.strip() for arg in fn[first_arg_pos:].split()]
        else:
            exe_fn = fn
            arguments = []

        if os.path.isfile(exe_fn) and os.access(exe_fn, os.X_OK):
            return exe_fn, arguments

        # try finding the executable itself, the path might contain spaces and there might have been other arguments
        fn_split = exe_fn.split(u" ")
        tmp_exe_fn = fn_split[0]

        for offset in range(1, len(fn_split)+1):
            if os.path.isfile(tmp_exe_fn) and os.access(tmp_exe_fn, os.X_OK):
                exe_fn = tmp_exe_fn.strip()
                arguments = [arg.strip() for arg in fn_split[offset:]] + arguments
                return exe_fn, arguments

            tmp_exe_fn = u" ".join(fn_split[:offset+1])

        Log.Error("Notify executable not existing or not executable: %s" % exe_fn)

    def refresh_enabled_sections(self):
        self.enabled_sections = self.check_enabled_sections()

    def check_enabled_sections(self):
        enabled_for_primary_agents = {"movie": [], "show": []}
        enabled_sections = {}

        # find which agents we're enabled for
        for agent in Plex.agents():
            if not agent.primary:
                continue

            media_types = [t.media_type for t in list(agent.media_types)]

            # the new movie agent doesn't populate its media types, workaround
            if not media_types and agent.identifier == "tv.plex.agents.movie":
                media_types = [MOVIE]

            for media_type in media_types:
                if media_type in (MOVIE, SHOW):
                    related_agents = Plex.primary_agent(agent.identifier, media_type)
                    for a in related_agents:
                        if a.identifier == PLUGIN_IDENTIFIER and a.enabled:
                            enabled_for_primary_agents[MEDIA_TYPE_TO_STRING[media_type]].append(agent.identifier)

        # find the libraries that use them
        for library in self.sections:
            if library.agent in enabled_for_primary_agents.get(library.type, []):
                enabled_sections[library.key] = library

        Log.Debug(u"I'm enabled for: %s" % [lib.title for key, lib in enabled_sections.iteritems()])
        return enabled_sections

    # Prepare a list of languages we want subs for
    def get_lang_list(self, provider=None, ordered=False):
        # advanced settings
        if provider and self.advanced.providers and provider in self.advanced.providers:
            adv_languages = self.advanced.providers[provider].get("languages", None)
            if adv_languages:
                adv_out = set()
                for adv_lang in adv_languages:
                    adv_lang = adv_lang.strip()
                    try:
                        real_lang = Language.fromietf(adv_lang)
                    except:
                        try:
                            real_lang = Language.fromname(adv_lang)
                        except:
                            continue
                    adv_out.update({real_lang})

                # fallback to default languages if no valid language was found in advanced settings
                if adv_out:
                    return adv_out

        l = [Language.fromietf(Prefs["langPref1a"])]
        lang_custom = Prefs["langPrefCustom"].strip()

        if Prefs['subtitles.only_one']:
            return set(l) if not ordered else l

        if Prefs["langPref2a"] != "None":
            try:
                l.append(Language.fromietf(Prefs["langPref2a"]))
            except:
                pass

        if Prefs["langPref3a"] != "None":
            try:
                l.append(Language.fromietf(Prefs["langPref3a"]))
            except:
                pass

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
                l.append(real_lang)

        if self.forced_also:
            if Prefs["subtitles.when_forced"] == "Always":
                for lang in list(l):
                    l.append(Language.rebuild(lang, forced=True))

            else:
                for (setting, index) in (("Only for Subtitle Language (1)", 0),
                                         ("Only for Subtitle Language (2)", 1),
                                         ("Only for Subtitle Language (3)", 2)):
                    if Prefs["subtitles.when_forced"] == setting:
                        try:
                            l.append(Language.rebuild(list(l)[index], forced=True))
                            break
                        except:
                            pass

        elif self.forced_only:
            for lang in l:
                lang.forced = True

        if not self.normal_subs:
            for lang in l[:]:
                if not lang.forced:
                    l.remove(lang)

        return set(l) if not ordered else l

    lang_list = property(get_lang_list)

    def get_subtitle_destination_folder(self):
        if not Prefs["subtitles.save.filesystem"]:
            return

        fld_custom = Prefs["subtitles.save.subFolder.Custom"].strip() if cast_bool(
            Prefs["subtitles.save.subFolder.Custom"]) else None
        return fld_custom or (
            Prefs["subtitles.save.subFolder"] if Prefs["subtitles.save.subFolder"] != "current folder" else None)

    def get_subtitle_formats(self):
        formats = Prefs["subtitles.save.formats"]
        out = []
        if "SRT" in formats:
            out.append("srt")
        if "VTT" in formats:
            out.append("vtt")
        return out

    @property
    def providers_by_prefs(self):
        return {'opensubtitles': cast_bool(Prefs['provider.opensubtitles.enabled']),
                     # 'thesubdb': Prefs['provider.thesubdb.enabled'],
                     'podnapisi': cast_bool(Prefs['provider.podnapisi.enabled']),
                     'napisy24': cast_bool(Prefs['provider.napisy24.enabled']),
                     'titlovi': cast_bool(Prefs['provider.titlovi.enabled']),
                     'addic7ed': cast_bool(Prefs['provider.addic7ed.enabled']) and self.has_anticaptcha,
                     'tvsubtitles': cast_bool(Prefs['provider.tvsubtitles.enabled']),
                     'legendastv': cast_bool(Prefs['provider.legendastv.enabled']),
                     'napiprojekt': cast_bool(Prefs['provider.napiprojekt.enabled']),
                     'hosszupuska': cast_bool(Prefs['provider.hosszupuska.enabled']),
                     'supersubtitles': cast_bool(Prefs['provider.supersubtitles.enabled']),
                     'shooter': False,
                     'subscene': cast_bool(Prefs['provider.subscene.enabled']),
                     'argenteam': cast_bool(Prefs['provider.argenteam.enabled']),
                     'subscenter': False,
                     'assrt': cast_bool(Prefs['provider.assrt.enabled']),
                     'bsplayer': cast_bool(Prefs['provider.bsplayer.enabled']),
                     'ktuvit': cast_bool(Prefs['provider.ktuvit.enabled']),
                     'wizdom': cast_bool(Prefs['provider.wizdom.enabled']),
                }

    @property
    def providers_enabled(self):
        return filter(lambda prov: self.providers_by_prefs[prov], self.providers_by_prefs)

    def get_providers(self, media_type="series"):
        providers = self.providers_by_prefs
        providers_by_prefs = copy.deepcopy(providers)

        # disable subscene for movies by default
        if media_type == "movies":
            providers["subscene"] = False

        # ditch non-forced-subtitles-reporting providers
        providers_forced_off = {}
        if self.forced_only:
            providers["addic7ed"] = False
            providers["tvsubtitles"] = False
            providers["legendastv"] = False
            providers["napiprojekt"] = False
            providers["shooter"] = False
            providers["hosszupuska"] = False
            providers["supersubtitles"] = False
            providers["titlovi"] = False
            providers["argenteam"] = False
            providers["assrt"] = False
            providers["subscene"] = False
            providers["napisy24"] = False
            providers["bsplayer"] = False
            providers["ktuvit"] = False
            providers["wizdom"] = False
            providers_forced_off = dict(providers)

        if not self.unrar and providers["legendastv"]:
            providers["legendastv"] = False
            Log.Info("Disabling LegendasTV, because UnRAR wasn't found")

        # advanced settings
        if media_type and self.advanced.providers:
            for provider, data in self.advanced.providers.iteritems():
                if provider not in providers or not providers_by_prefs[provider] or provider in providers_forced_off:
                    continue

                if data["enabled_for"] is not None:
                    providers[provider] = media_type in data["enabled_for"]

        if "provider_throttle" not in Dict:
            Dict["provider_throttle"] = {}

        changed = False
        for provider, enabled in dict(providers).iteritems():
            reason, until, throttle_desc = Dict["provider_throttle"].get(provider, (None, None, None))
            if reason:
                now = datetime.datetime.now()
                if now < until:
                    Log.Info("Not using %s until %s, because of: %s", provider,
                             until.strftime("%y/%m/%d %H:%M"), reason)
                    providers[provider] = False
                else:
                    Log.Info("Using %s again after %s, (disabled because: %s)", provider, throttle_desc, reason)
                    del Dict["provider_throttle"][provider]
                    changed = True

        if changed:
            Dict.Save()

        return filter(lambda prov: providers[prov], providers)

    providers = property(get_providers)

    def get_provider_settings(self):
        os_use_https = self.advanced.providers.opensubtitles.get("use_https", True)
        os_skip_wrong_fps = self.advanced.providers.opensubtitles.get("skip_wrong_fps", True)

        provider_settings = {'addic7ed': {'username': Prefs['provider.addic7ed.username'],
                                          'password': Prefs['provider.addic7ed.password'],
                                          'is_vip': cast_bool(Prefs['provider.addic7ed.is_vip']),
                                          },
                             'opensubtitles': {'username': Prefs['provider.opensubtitles.username'],
                                               'password': Prefs['provider.opensubtitles.password'],
                                               'use_tag_search': self.exact_filenames,
                                               'only_foreign': self.forced_only,
                                               'also_foreign': self.forced_also,
                                               'is_vip': cast_bool(Prefs['provider.opensubtitles.is_vip']),
                                               'use_ssl': os_use_https,
                                               'timeout': self.advanced.providers.opensubtitles.timeout or 15,
                                               'skip_wrong_fps': os_skip_wrong_fps,
                                               },
                             'podnapisi': {
                                 'only_foreign': self.forced_only,
                                 'also_foreign': self.forced_also,
                             },
                             'titlovi': {
                                 'username': Prefs['provider.titlovi.username'],
                                 'password': Prefs['provider.titlovi.password'],
                             },
                             'napisy24': {
                                 'username': Prefs['provider.napisy24.username'],
                                 'password': Prefs['provider.napisy24.password'],
                             },
                             'subscene': {
                                 'only_foreign': self.forced_only,
                                 'username': Prefs['provider.subscene.username'],
                                 'password': Prefs['provider.subscene.password'],
                             },
                             'legendastv': {'username': Prefs['provider.legendastv.username'],
                                            'password': Prefs['provider.legendastv.password'],
                                            },
                             'assrt': {'token': Prefs['provider.assrt.token'], },
                             'ktuvit': {
                                 'username': Prefs['provider.ktuvit.username'],
                                 'password': Prefs['provider.ktuvit.password'],
                             },
                             }

        return provider_settings

    provider_settings = property(get_provider_settings)

    def provider_throttle(self, name, exception):
        """
        throttle a provider :name: for X hours based on the :exception: type
        :param name:
        :param exception:
        :return:
        """
        cls = getattr(exception, "__class__")
        cls_name = getattr(cls, "__name__")
        if cls not in VALID_THROTTLE_EXCEPTIONS:
            for valid_cls in VALID_THROTTLE_EXCEPTIONS:
                if isinstance(cls, valid_cls):
                    cls = valid_cls

        throttle_data = PROVIDER_THROTTLE_MAP.get(name, PROVIDER_THROTTLE_MAP["default"]).get(cls, None) or \
            PROVIDER_THROTTLE_MAP["default"].get(cls, None)

        if throttle_data:
            throttle_delta, throttle_description = throttle_data
        else:
            throttle_delta, throttle_description = datetime.timedelta(minutes=10), "10 minutes"

        if "provider_throttle" not in Dict:
            Dict["provider_throttle"] = {}

        throttle_until = datetime.datetime.now() + throttle_delta
        Dict["provider_throttle"][name] = (cls_name, throttle_until, throttle_description)

        Log.Info("Throttling %s for %s, until %s, because of: %s. Exception info: %r", name, throttle_description,
                 throttle_until.strftime("%y/%m/%d %H:%M"), cls_name, exception.message)
        Dict.Save()

    @property
    def provider_pool(self):
        if cast_bool(Prefs['providers.multithreading']):
            return subliminal_patch.core.SZAsyncProviderPool
        return subliminal_patch.core.SZProviderPool

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

    def get_subtitle_sub_dir(self):
        """

        :return: folder, is_absolute
        """
        if not cast_bool(Prefs['subtitles.save.filesystem']):
            return None, None

        if Prefs["subtitles.save.subFolder.Custom"]:
            return Prefs["subtitles.save.subFolder.Custom"], os.path.isabs(Prefs["subtitles.save.subFolder.Custom"])

        if Prefs["subtitles.save.subFolder"] == "current folder":
            return ".", False

        return Prefs["subtitles.save.subFolder"], False

    def determine_ext_sub_strictness(self):
        val = Prefs["subtitles.scan.filename_strictness"]
        if val == "any":
            return "any"
        elif val.startswith("loose"):
            return "loose"
        return "strict"

    def get_default_mods(self):
        mods = []
        if self.remove_hi:
            mods.append("remove_HI")
        if self.remove_tags:
            mods.append("remove_tags")
        if self.fix_ocr:
            mods.append("OCR_fixes")
        if self.fix_common:
            mods.append("common")
        if self.fix_upper:
            mods.append("fix_uppercase")
        if self.colors:
            mods.append("color(name=%s)" % self.colors)
        if self.reverse_rtl:
            mods.append("reverse_rtl")

        return mods

    def setup_proxies(self):
        proxy = Prefs["proxy"]
        if proxy:
            os.environ["SZ_HTTP_PROXY"] = proxy.strip()
            Log.Debug("Using HTTP Proxy: %s", proxy)

    def set_activity_modes(self):
        val = Prefs["activity.on_playback"]
        if val == "never":
            self.react_to_activities = False
            return

        self.react_to_activities = True
        if val == "current media item":
            self.activity_mode = "refresh"
        elif val == "hybrid: current item or next episode":
            self.activity_mode = "hybrid"
        elif val == "hybrid-plus: current item and next episode":
            self.activity_mode = "hybrid-plus"
        else:
            self.activity_mode = "next_episode"

    def get_plex_transcoder(self):
        paths = []
        base_path = os.environ.get("PLEX_MEDIA_SERVER_HOME", None)
        if base_path:
            paths.append(base_path)

        bundle_path = os.environ.get("PLEXBUNDLEDPLUGINSPATH", None)
        if bundle_path:
            paths.append(os.path.normpath(os.path.join(bundle_path, "..", "..")))

        paths.append(self.app_support_path)

        bns = []
        if sys.platform == "darwin":
            bns.append(("MacOS", "Plex Transcoder"))
        elif mswindows:
            bns = [("plextranscoder.exe",), ("plex transcoder.exe",)]
        else:
            bns.append(("Plex Transcoder",))

        for path in paths:
            for bn in bns:
                fn = os.path.join(path, *bn)

                if os.path.isfile(fn):
                    return fn

            # look inside Resources folder as fallback, as well
            for vbn in ("Plex Transcoder", "plextranscoder.exe", "plex transcoder.exe"):
                fn = os.path.join(path, "Resources", vbn)
                if os.path.isfile(fn):
                    return fn

    def parse_rename_mode(self):
        # fixme: exact_filenames should be determined via callback combined with info about the current video
        # (original_name)

        mode = str(Prefs["media_rename1"])
        self.refiner_settings = {}

        if cast_bool(Prefs['use_file_info_file']):
            self.refiner_settings["file_info_file"] = True
            self.exact_filenames = True

        if mode == "none of the above":
            return

        elif mode == "Symlink to original file":
            self.refiner_settings["symlinks"] = True
            self.exact_filenames = True
            return

        elif mode == "I keep the original filenames":
            self.exact_filenames = True
            return

        if mode in ("Filebot", "Sonarr/Radarr/Filebot"):
            self.refiner_settings["filebot"] = True

        if mode in ("Sonarr/Radarr (fill api info below)", "Sonarr/Radarr/Filebot"):
            if Prefs["drone_api.sonarr.url"] and Prefs["drone_api.sonarr.api_key"]:
                self.refiner_settings["sonarr"] = {
                    "base_url": Prefs["drone_api.sonarr.url"],
                    "api_key": Prefs["drone_api.sonarr.api_key"],
                }
                if self.advanced.refiners.sonarr:
                    self.refiner_settings["sonarr"].update(self.advanced.refiners.sonarr)

                self.exact_filenames = True

            if Prefs["drone_api.radarr.url"] and Prefs["drone_api.radarr.api_key"]:
                self.refiner_settings["radarr"] = {
                    "base_url": Prefs["drone_api.radarr.url"],
                    "api_key": Prefs["drone_api.radarr.api_key"]
                }
                if self.advanced.refiners.radarr:
                    self.refiner_settings["radarr"].update(self.advanced.refiners.radarr)

                self.exact_filenames = True

    @property
    def text_based_formats(self):
        return self.advanced.text_subtitle_formats or TEXT_SUBTITLE_EXTS

    def parse_custom_dns(self):
        custom_dns = Prefs['use_custom_dns2'].strip()
        os.environ["dns_resolvers"] = ""

        if custom_dns and custom_dns != "system":
            ips = filter(lambda x: x, [d.strip() for d in custom_dns.split(",")])
            if ips:
                os.environ["dns_resolvers"] = json.dumps(ips)
            return os.environ["dns_resolvers"]

    def init_subliminal_patches(self):
        # configure custom subtitle destination folders for scanning pre-existing subs
        Log.Debug("Patching subliminal ...")
        dest_folder = self.subtitle_destination_folder
        subliminal_patch.core.CUSTOM_PATHS = [dest_folder] if dest_folder else []
        subliminal_patch.core.INCLUDE_EXOTIC_SUBS = self.exotic_ext

        subliminal_patch.core.DOWNLOAD_TRIES = int(Prefs['subtitles.try_downloads'])
        subliminal.score.episode_scores["addic7ed_boost"] = int(Prefs['provider.addic7ed.boost_by2'])


config = Config()
config.initialize()
