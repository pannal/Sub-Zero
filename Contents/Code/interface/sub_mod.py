# coding=utf-8

import traceback
import types

from subzero.language import Language

from menu_helpers import debounce, SubFolderObjectContainer, default_thumb, route
from subzero.modification import registry as mod_registry, SubtitleModifications
from subzero.constants import PREFIX
from support.plex_media import get_plex_metadata
from support.scanning import scan_videos
from support.helpers import timestamp, pad_title
from support.items import get_current_sub, set_mods_for_part
from support.i18n import _


@route(PREFIX + '/item/sub_mods/{rating_key}/{part_id}', force=bool)
def SubtitleModificationsMenu(**kwargs):
    rating_key = kwargs["rating_key"]
    part_id = kwargs["part_id"]
    language = kwargs["language"]
    lang_instance = Language.fromietf(language)
    current_sub, stored_subs, storage = get_current_sub(rating_key, part_id, language)
    kwargs.pop("randomize")

    current_mods = current_sub.mods or []

    oc = SubFolderObjectContainer(title2=kwargs["title"], replace_parent=True)

    from interface.item_details import SubtitleOptionsMenu
    oc.add(DirectoryObject(
        key=Callback(SubtitleOptionsMenu, randomize=timestamp(), **kwargs),
        title=_(u"< Back to subtitle options for: %s", kwargs["title"]),
        summary=unicode(kwargs["current_data"]),
        thumb=default_thumb
    ))

    for identifier, mod in mod_registry.mods.iteritems():
        if mod.advanced:
            continue

        if mod.exclusive and identifier in current_mods:
            continue

        if mod.languages and lang_instance not in mod.languages:
            continue

        oc.add(DirectoryObject(
            key=Callback(SubtitleSetMods, mods=identifier, mode="add", randomize=timestamp(), **kwargs),
            title=pad_title(_(mod.description)), summary=_(mod.long_description) or ""
        ))

    fps_mod = SubtitleModifications.get_mod_class("change_FPS")
    oc.add(DirectoryObject(
        key=Callback(SubtitleFPSModMenu, randomize=timestamp(), **kwargs),
        title=pad_title(_(fps_mod.description)), summary=_(fps_mod.long_description) or ""
    ))

    shift_mod = SubtitleModifications.get_mod_class("shift_offset")
    oc.add(DirectoryObject(
        key=Callback(SubtitleShiftModUnitMenu, randomize=timestamp(), **kwargs),
        title=pad_title(_(shift_mod.description)), summary=_(shift_mod.long_description) or ""
    ))

    color_mod = SubtitleModifications.get_mod_class("color")
    oc.add(DirectoryObject(
        key=Callback(SubtitleColorModMenu, randomize=timestamp(), **kwargs),
        title=pad_title(_(color_mod.description)), summary=_(color_mod.long_description) or ""
    ))

    if current_mods:
        oc.add(DirectoryObject(
            key=Callback(SubtitleSetMods, mods=None, mode="remove_last", randomize=timestamp(), **kwargs),
            title=pad_title(_("Remove last applied mod (%s)", current_mods[-1])),
            summary=_(u"Currently applied mods: %(mod_list)s", mod_list=", ".join(current_mods) if current_mods else _("none"))
        ))
        oc.add(DirectoryObject(
            key=Callback(SubtitleListMods, randomize=timestamp(), **kwargs),
            title=pad_title(_("Manage applied mods")),
            summary=_(u"Currently applied mods: %(mod_list)s", mod_list=", ".join(current_mods))
        ))
        oc.add(DirectoryObject(
            key=Callback(SubtitleReapplyMods, randomize=timestamp(), **kwargs),
            title=pad_title(_("Reapply applied mods")),
            summary=_(u"Currently applied mods: %(mod_list)s", mod_list=", ".join(current_mods) if current_mods else _("none"))
        ))

    oc.add(DirectoryObject(
        key=Callback(SubtitleSetMods, mods=None, mode="clear", randomize=timestamp(), **kwargs),
        title=pad_title(_("Restore original version")),
        summary=_(u"Currently applied mods: %(mod_list)s", mod_list=", ".join(current_mods) if current_mods else _("none"))
    ))

    storage.destroy()

    return oc


@route(PREFIX + '/item/sub_mod_fps/{rating_key}/{part_id}', force=bool)
def SubtitleFPSModMenu(**kwargs):
    rating_key = kwargs["rating_key"]
    part_id = kwargs["part_id"]
    item_type = kwargs["item_type"]

    kwargs.pop("randomize")

    oc = SubFolderObjectContainer(title2=kwargs["title"], replace_parent=True)

    oc.add(DirectoryObject(
        key=Callback(SubtitleModificationsMenu, randomize=timestamp(), **kwargs),
        title=_("< Back to subtitle modification menu")
    ))

    metadata = get_plex_metadata(rating_key, part_id, item_type)
    scanned_parts = scan_videos([metadata], ignore_all=True, skip_hashing=True)
    video, plex_part = scanned_parts.items()[0]

    target_fps = plex_part.fps

    for fps in ["23.980", "23.976", "24.000", "25.000", "29.970", "30.000", "50.000", "59.940", "60.000"]:
        if float(fps) == float(target_fps):
            continue

        if float(fps) > float(target_fps):
            indicator = _("subs constantly getting faster")
        else:
            indicator = _("subs constantly getting slower")

        mod_ident = SubtitleModifications.get_mod_signature("change_FPS", **{"from": fps, "to": target_fps})
        oc.add(DirectoryObject(
            key=Callback(SubtitleSetMods, mods=mod_ident, mode="add", randomize=timestamp(), **kwargs),
            title=_("%(from_fps)s fps -> %(to_fps)s fps (%(slower_or_faster_indicator)s)",
                    from_fps=fps,
                    to_fps=target_fps,
                    slower_or_faster_indicator=indicator)
        ))

    return oc


POSSIBLE_UNITS = (("ms", "milliseconds"), ("s", "seconds"), ("m", "minutes"), ("h", "hours"))
POSSIBLE_UNITS_D = dict(POSSIBLE_UNITS)


@route(PREFIX + '/item/sub_mod_shift_unit/{rating_key}/{part_id}', force=bool)
def SubtitleShiftModUnitMenu(**kwargs):
    oc = SubFolderObjectContainer(title2=kwargs["title"], replace_parent=True)

    kwargs.pop("randomize")

    oc.add(DirectoryObject(
        key=Callback(SubtitleModificationsMenu, randomize=timestamp(), **kwargs),
        title=_("< Back to subtitle modifications")
    ))

    for unit, title in POSSIBLE_UNITS:
        oc.add(DirectoryObject(
            key=Callback(SubtitleShiftModMenu, unit=unit, randomize=timestamp(), **kwargs),
            title=_("Adjust by %(time_and_unit)s", time_and_unit=title)
        ))

    return oc


@route(PREFIX + '/item/sub_mod_shift/{rating_key}/{part_id}/{unit}', force=bool)
def SubtitleShiftModMenu(unit=None, **kwargs):
    if unit not in POSSIBLE_UNITS_D:
        raise NotImplementedError

    kwargs.pop("randomize")

    oc = SubFolderObjectContainer(title2=kwargs["title"], replace_parent=True)

    oc.add(DirectoryObject(
        key=Callback(SubtitleShiftModUnitMenu, randomize=timestamp(), **kwargs),
        title=_("< Back to unit selection")
    ))

    rng = []
    if unit == "h":
        rng = list(reversed(range(-10, 0))) + list(reversed(range(1, 11)))
    elif unit in ("m", "s"):
        rng = list(reversed(range(-15, 0))) + list(reversed(range(1, 16)))
    elif unit == "ms":
        rng = list(reversed(range(-900, 0, 100))) + list(reversed(range(100, 1000, 100)))

    for i in rng:
        if i == 0:
            continue

        mod_ident = SubtitleModifications.get_mod_signature("shift_offset", **{unit: i})
        oc.add(DirectoryObject(
            key=Callback(SubtitleSetMods, mods=mod_ident, mode="add", randomize=timestamp(), **kwargs),
            title="%s %s" % (("%s" if i < 0 else "+%s") % i, unit)
        ))

    return oc


@route(PREFIX + '/item/sub_mod_colors/{rating_key}/{part_id}', force=bool)
def SubtitleColorModMenu(**kwargs):
    kwargs.pop("randomize")

    color_mod = SubtitleModifications.get_mod_class("color")

    oc = SubFolderObjectContainer(title2=kwargs["title"], replace_parent=True)

    oc.add(DirectoryObject(
        key=Callback(SubtitleModificationsMenu, randomize=timestamp(), **kwargs),
        title=_("< Back to subtitle modification menu")
    ))

    for color, code in color_mod.colors.iteritems():
        mod_ident = SubtitleModifications.get_mod_signature("color", **{"name": color})
        oc.add(DirectoryObject(
            key=Callback(SubtitleSetMods, mods=mod_ident, mode="add", randomize=timestamp(), **kwargs),
            title="%s (%s)" % (color, code)
        ))

    return oc


@route(PREFIX + '/item/sub_set_mods/{rating_key}/{part_id}/{mods}/{mode}', force=bool)
@debounce
def SubtitleSetMods(mods=None, mode=None, **kwargs):
    if not isinstance(mods, types.ListType) and mods:
        mods = [mods]

    rating_key = kwargs["rating_key"]
    part_id = kwargs["part_id"]
    lang_a2 = kwargs["language"]
    item_type = kwargs["item_type"]

    language = Language.fromietf(lang_a2)

    set_mods_for_part(rating_key, part_id, language, item_type, mods, mode=mode)

    kwargs.pop("randomize")
    return SubtitleModificationsMenu(randomize=timestamp(), **kwargs)


@route(PREFIX + '/item/sub_reapply_mods/{rating_key}/{part_id}', force=bool)
@debounce
def SubtitleReapplyMods(**kwargs):
    rating_key = kwargs["rating_key"]
    part_id = kwargs["part_id"]
    lang_a2 = kwargs["language"]
    item_type = kwargs["item_type"]

    language = Language.fromietf(lang_a2)

    set_mods_for_part(rating_key, part_id, language, item_type, [], mode="add")

    kwargs.pop("randomize")
    return SubtitleModificationsMenu(randomize=timestamp(), **kwargs)


@route(PREFIX + '/item/sub_list_mods/{rating_key}/{part_id}', force=bool)
@debounce
def SubtitleListMods(**kwargs):
    rating_key = kwargs["rating_key"]
    part_id = kwargs["part_id"]
    language = kwargs["language"]
    current_sub, stored_subs, storage = get_current_sub(rating_key, part_id, language)

    kwargs.pop("randomize")

    oc = SubFolderObjectContainer(title2=kwargs["title"], replace_parent=True)

    oc.add(DirectoryObject(
        key=Callback(SubtitleModificationsMenu, randomize=timestamp(), **kwargs),
        title=_("< Back to subtitle modifications")
    ))

    for identifier in current_sub.mods:
        oc.add(DirectoryObject(
            key=Callback(SubtitleSetMods, mods=identifier, mode="remove", randomize=timestamp(), **kwargs),
            title=_("Remove: %(mod_name)s", mod_name=identifier)
        ))

    storage.destroy()

    return oc