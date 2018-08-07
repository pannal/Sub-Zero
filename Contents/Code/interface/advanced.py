# coding=utf-8
import datetime
import StringIO
import glob
import os
import traceback
import urlparse

from zipfile import ZipFile, ZIP_DEFLATED

from subzero.language import Language

from subzero.lib.io import FileIO
from subzero.constants import PREFIX, PLUGIN_IDENTIFIER
from menu_helpers import SubFolderObjectContainer, debounce, set_refresh_menu_state, ZipObject, ObjectContainer, route
from main import fatality
from support.helpers import timestamp, pad_title
from support.config import config
from support.lib import Plex
from support.storage import reset_storage, log_storage, get_subtitle_storage
from support.scheduler import scheduler
from support.items import set_mods_for_part, get_item_kind_from_rating_key
from support.i18n import _


@route(PREFIX + '/advanced')
def AdvancedMenu(randomize=None, header=None, message=None):
    oc = SubFolderObjectContainer(
            header=header or _("Internal stuff, pay attention!"),
            message=message,
            no_cache=True,
            no_history=True,
            replace_parent=False,
            title2=_("Advanced"))

    if config.lock_advanced_menu and not config.pin_correct:
        oc.add(DirectoryObject(
            key=Callback(
                    PinMenu,
                    randomize=timestamp(),
                    success_go_to=_("advanced")),
            title=pad_title(_("Enter PIN")),
            summary=_("The owner has restricted the access to this menu. Please enter the correct pin"),
        ))
        return oc

    oc.add(DirectoryObject(
        key=Callback(TriggerRestart, randomize=timestamp()),
        title=pad_title(_("Restart the plugin")),
    ))
    oc.add(DirectoryObject(
        key=Callback(GetLogsLink),
        title=_("Get my logs (copy the appearing link and open it in your browser, please)"),
        summary=_("Copy the appearing link and open it in your browser, please"),
    ))
    oc.add(DirectoryObject(
        key=Callback(TriggerBetterSubtitles, randomize=timestamp()),
        title=pad_title(_("Trigger find better subtitles")),
    ))
    oc.add(DirectoryObject(
        key=Callback(SkipFindBetterSubtitles, randomize=timestamp()),
        title=pad_title(_("Skip next find better subtitles (sets last run to now)")),
    ))
    oc.add(DirectoryObject(
        key=Callback(TriggerStorageMaintenance, randomize=timestamp()),
        title=pad_title(_("Trigger subtitle storage maintenance")),
    ))
    oc.add(DirectoryObject(
        key=Callback(TriggerStorageMigration, randomize=timestamp()),
        title=pad_title(_("Trigger subtitle storage migration (expensive)")),
    ))
    oc.add(DirectoryObject(
        key=Callback(TriggerCacheMaintenance, randomize=timestamp()),
        title=pad_title(_("Trigger cache maintenance (refiners, providers and packs/archives)")),
    ))
    oc.add(DirectoryObject(
        key=Callback(ApplyDefaultMods, randomize=timestamp()),
        title=pad_title(_("Apply configured default subtitle mods to all (active) stored subtitles")),
    ))
    oc.add(DirectoryObject(
        key=Callback(ReApplyMods, randomize=timestamp()),
        title=pad_title(_("Re-Apply mods of all stored subtitles")),
    ))
    oc.add(DirectoryObject(
        key=Callback(LogStorage, key="tasks", randomize=timestamp()),
        title=pad_title(_("Log the plugin's scheduled tasks state storage")),
    ))
    oc.add(DirectoryObject(
        key=Callback(LogStorage, key="ignore", randomize=timestamp()),
        title=pad_title(_("Log the plugin's internal ignorelist storage")),
    ))
    oc.add(DirectoryObject(
        key=Callback(LogStorage, key=None, randomize=timestamp()),
        title=pad_title(_("Log the plugin's complete state storage")),
    ))
    oc.add(DirectoryObject(
        key=Callback(ResetStorage, key="tasks", randomize=timestamp()),
        title=pad_title(_("Reset the plugin's scheduled tasks state storage")),
    ))
    oc.add(DirectoryObject(
        key=Callback(ResetStorage, key="ignore", randomize=timestamp()),
        title=pad_title(_("Reset the plugin's internal ignorelist storage")),
    ))
    oc.add(DirectoryObject(
        key=Callback(ResetStorage, key="menu_history", randomize=timestamp()),
        title=pad_title("Reset the plugin's menu history storage"),
    ))
    oc.add(DirectoryObject(
        key=Callback(InvalidateCache, randomize=timestamp()),
        title=pad_title(_("Invalidate Sub-Zero metadata caches (subliminal)")),
    ))
    oc.add(DirectoryObject(
        key=Callback(ResetProviderThrottle, randomize=timestamp()),
        title=pad_title(_("Reset provider throttle states")),
    ))
    return oc


def DispatchRestart():
    Thread.CreateTimer(1.0, Restart)


@route(PREFIX + '/advanced/restart/trigger')
@debounce
def TriggerRestart(randomize=None):
    set_refresh_menu_state(_("Restarting the plugin"))
    DispatchRestart()
    return fatality(
            header=_("Restart triggered, please wait about 5 seconds"),
            force_title=" ",
            only_refresh=True,
            replace_parent=True,
            no_history=True,
            randomize=timestamp())


@route(PREFIX + '/advanced/restart/execute')
@debounce
def Restart(randomize=None):
    Plex[":/plugins"].restart(PLUGIN_IDENTIFIER)


@route(PREFIX + '/storage/reset', sure=bool)
@debounce
def ResetStorage(key, randomize=None, sure=False):
    if not sure:
        oc = SubFolderObjectContainer(
                no_history=True,
                title1=_("Reset subtitle storage"),
                title2=_("Are you sure?"))
        oc.add(DirectoryObject(
            key=Callback(
                    ResetStorage,
                    key=key,
                    sure=True,
                    randomize=timestamp()),
            title=pad_title(_("Are you really sure?")),

        ))
        return oc

    reset_storage(key)

    if key == "tasks":
        # reinitialize the scheduler
        scheduler.init_storage()
        scheduler.setup_tasks()

    return AdvancedMenu(
        randomize=timestamp(),
        header=_("Success"),
        message=_("Information Storage (%s) reset", key)
    )


@route(PREFIX + '/storage/log')
def LogStorage(key, randomize=None):
    log_storage(key)
    return AdvancedMenu(
        randomize=timestamp(),
        header=_("Success"),
        message=_("Information Storage (%s) logged", key)
    )


@route(PREFIX + '/triggerbetter')
@debounce
def TriggerBetterSubtitles(randomize=None):
    scheduler.dispatch_task("FindBetterSubtitles")
    return AdvancedMenu(
        randomize=timestamp(),
        header=_("Success"),
        message=_("FindBetterSubtitles triggered")
    )


@route(PREFIX + '/skipbetter')
@debounce
def SkipFindBetterSubtitles(randomize=None):
    task = scheduler.task("FindBetterSubtitles")
    task.last_run = datetime.datetime.now()

    return AdvancedMenu(
        randomize=timestamp(),
        header=_("Success"),
        message=_("FindBetterSubtitles skipped")
    )


@route(PREFIX + '/triggermaintenance')
@debounce
def TriggerStorageMaintenance(randomize=None):
    scheduler.dispatch_task("SubtitleStorageMaintenance")
    return AdvancedMenu(
        randomize=timestamp(),
        header=_("Success"),
        message=_("SubtitleStorageMaintenance triggered")
    )


@route(PREFIX + '/triggerstoragemigration')
@debounce
def TriggerStorageMigration(randomize=None):
    scheduler.dispatch_task("MigrateSubtitleStorage")
    return AdvancedMenu(
        randomize=timestamp(),
        header=_("Success"),
        message=_("MigrateSubtitleStorage triggered")
    )


@route(PREFIX + '/triggercachemaintenance')
@debounce
def TriggerCacheMaintenance(randomize=None):
    scheduler.dispatch_task("CacheMaintenance")
    return AdvancedMenu(
        randomize=timestamp(),
        header=_("Success"),
        message=_("TriggerCacheMaintenance triggered")
    )


def apply_default_mods(reapply_current=False):
    storage = get_subtitle_storage()
    subs_applied = 0
    for fn in storage.get_all_files():
        data = storage.load(None, filename=fn)
        if data:
            video_id = data.video_id
            item_type = get_item_kind_from_rating_key(video_id)
            if not item_type:
                continue

            for part_id, part in data.parts.iteritems():
                for lang, subs in part.iteritems():
                    current_sub = subs.get("current")
                    if not current_sub:
                        continue
                    sub = subs[current_sub]

                    if not sub.content:
                        continue

                    current_mods = sub.mods or []
                    if not reapply_current:
                        add_mods = list(set(config.default_mods).difference(set(current_mods)))
                        if not add_mods:
                            continue
                    else:
                        if not current_mods:
                            continue
                        add_mods = []

                    try:
                        set_mods_for_part(video_id, part_id, Language.fromietf(lang), item_type, add_mods, mode="add")
                    except:
                        Log.Error("Couldn't set mods for %s:%s: %s", video_id, part_id, traceback.format_exc())
                        continue

                    subs_applied += 1
    storage.destroy()
    Log.Debug("Applied mods to %i items" % subs_applied)


@route(PREFIX + '/applydefaultmods')
@debounce
def ApplyDefaultMods(randomize=None):
    Thread.CreateTimer(1.0, apply_default_mods)
    return AdvancedMenu(
        randomize=timestamp(),
        header=_("Success"),
        message=_("This may take some time ...")
    )


@route(PREFIX + '/reapplyallmods')
@debounce
def ReApplyMods(randomize=None):
    Thread.CreateTimer(1.0, apply_default_mods, reapply_current=True)
    return AdvancedMenu(
        randomize=timestamp(),
        header=_("Success"),
        message=_("This may take some time ...")
    )


@route(PREFIX + '/get_logs_link')
def GetLogsLink():
    if not config.plex_token:
        oc = ObjectContainer(
                title2=_("Download Logs"),
                no_cache=True,
                no_history=True,
                header=_("Sorry, feature unavailable"),
                message=_("Universal Plex token not available"))
        return oc

    # try getting the link base via the request in context, first, otherwise use the public ip
    req_headers = Core.sandbox.context.request.headers
    get_external_ip = True
    link_base = ""

    if "Origin" in req_headers:
        link_base = req_headers["Origin"]
        Log.Debug("Using origin-based link_base")
        get_external_ip = False

    elif "Referer" in req_headers:
        parsed = urlparse.urlparse(req_headers["Referer"])
        link_base = "%s://%s%s" % (parsed.scheme, parsed.hostname, (":%s" % parsed.port) if parsed.port else "")
        Log.Debug("Using referer-based link_base")
        get_external_ip = False

    if get_external_ip or "plex.tv" in link_base:
        ip = Core.networking.http_request("http://www.plexapp.com/ip.php", cacheTime=7200).content.strip()
        link_base = "https://%s:32400" % ip
        Log.Debug("Using ip-based fallback link_base")

    logs_link = "%s%s?X-Plex-Token=%s" % (link_base, PREFIX + '/logs', config.plex_token)
    oc = ObjectContainer(
            title2=logs_link,
            no_cache=True,
            no_history=True,
            header=_("Copy this link and open this in your browser, please"),
            message=logs_link)
    return oc


@route(PREFIX + '/logs')
def DownloadLogs():
    buff = StringIO.StringIO()
    zip_archive = ZipFile(buff, mode='w', compression=ZIP_DEFLATED)

    logs = sorted(glob.glob(config.plugin_log_path + '*')) + [config.server_log_path]
    for path in logs:
        data = StringIO.StringIO()
        data.write(FileIO.read(path))
        zip_archive.writestr(os.path.basename(path), data.getvalue())

    zip_archive.close()

    return ZipObject(buff.getvalue())


@route(PREFIX + '/invalidatecache')
@debounce
def InvalidateCache(randomize=None):
    from subliminal.cache import region
    if config.new_style_cache:
        region.backend.clear()
    else:
        region.invalidate()
    return AdvancedMenu(
        randomize=timestamp(),
        header=_("Success"),
        message=_("Cache invalidated")
    )


@route(PREFIX + '/pin')
def PinMenu(pin="", randomize=None, success_go_to="channel"):
    oc = ObjectContainer(
            title2=_("Enter PIN number ") + str(len(pin) + 1),
            no_cache=True,
            no_history=True,
            skip_pin_lock=True)

    if pin == config.pin:
        Dict["pin_correct_time"] = datetime.datetime.now()
        config.locked = False
        if success_go_to == "channel":
            return fatality(
                force_title=_("PIN correct"),
                header=_("PIN correct"),
                no_history=True)
        elif success_go_to == "advanced":
            return AdvancedMenu(randomize=timestamp())

    for i in range(10):
        oc.add(DirectoryObject(
            key=Callback(
                    PinMenu,
                    randomize=timestamp(),
                    pin=pin + str(i),
                    success_go_to=success_go_to),
            title=pad_title(str(i)),
        ))
    oc.add(DirectoryObject(
        key=Callback(
                PinMenu,
                randomize=timestamp(),
                success_go_to=success_go_to),
        title=pad_title(_("Reset")),
    ))
    return oc


@route(PREFIX + '/pin_lock')
def ClearPin(randomize=None):
    Dict["pin_correct_time"] = None
    config.locked = True
    return fatality(force_title=_("Menu locked"), header=" ", no_history=True)


@route(PREFIX + '/reset_throttle')
def ResetProviderThrottle(randomize=None):
    Dict["provider_throttle"] = {}
    Dict.Save()
    return AdvancedMenu(
        randomize=timestamp(),
        header=_("Success"),
        message=_("Provider throttles reset")
    )
