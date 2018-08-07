# coding=utf-8

import inspect

from support.config import config


core = getattr(Data, "_core")


# get original localization module in order to access its base classes later on
def get_localization_module():
    cls = getattr(core.localization, "__class__")
    return inspect.getmodule(cls)


plex_i18n_module = get_localization_module()


def old_style_placeholders_count(s):
    # fixme: incomplete, use regex
    return sum(s.count(c) for c in ["%s", "%d", "%r", "%f", "%i"])


def check_old_style_placeholders(k, args):
    # replace escaped %'s?
    k = k.__str__().replace("%%", "")

    if "%(" in k:
        Log.Error(u"%r defines named placeholders for formatting" % k)
        return "NEEDS NAMED ARGUMENTS"

    placeholders_found = old_style_placeholders_count(k)
    if placeholders_found and not args:
        Log.Error(u"%r requires a arguments for formatting" % k)
        return "NEEDS FORMAT ARGUMENTS"

    elif not placeholders_found and args:
        Log.Error(u"%r doesn't define placeholders for formatting" % k)
        return "HAS NO FORMAT ARGUMENTS"

    elif placeholders_found and placeholders_found != len(args):
        Log.Error(u"%r wrong amount of arguments supplied for formatting" % k)
        return "WRONG FORMAT ARGUMENT COUNT"


class SmartLocalStringFormatter(plex_i18n_module.LocalStringFormatter):
    """
    this allows the use of dictionaries for string formatting, also does some sanity checking on the keys and values
    """
    def __init__(self, string1, string2, locale=None):
        if isinstance(string2, tuple):
            # dictionary passed
            if len(string2) == 1 and hasattr(string2[0], "iteritems"):
                string2 = string2[0]
                if config.debug_i18n:
                    if "%(" not in string1.__str__().replace("%%", ""):
                        Log.Error(u"%r: dictionary for non-named format string supplied" % string1.__str__())
                        string1 = "%s"
                        string2 = "NO NAMED ARGUMENTS"

            # arguments
            elif len(string2) >= 1 and config.debug_i18n:
                msg = check_old_style_placeholders(string1, string2)
                if msg:
                    string1 = "%s"
                    string2 = msg

        setattr(self, "_string1", string1)
        setattr(self, "_string2", string2)
        setattr(self, "_locale", locale)


def local_string_with_optional_format(key, *args, **kwargs):
    if kwargs:
        args = (kwargs,)
    else:
        args = tuple(args)

    if args:
        # fixme: may not be the best idea as this evaluates the string early
        try:
            return unicode(SmartLocalStringFormatter(plex_i18n_module.LocalString(core, key, Locale.CurrentLocale), args))
        except TypeError:
            Log.Exception("Broken translation!")
            return unicode(SmartLocalStringFormatter(plex_i18n_module.LocalString(core, key, "en"), args))

    # check string instances for arguments
    if config.debug_i18n:
        msg = check_old_style_placeholders(key, args)
        if msg:
            return msg

    try:
        return unicode(plex_i18n_module.LocalString(core, key, Locale.CurrentLocale))

    except TypeError:
        Log.Exception("Broken translation!")
        return unicode(plex_i18n_module.LocalString(core, key, "en"))


_ = local_string_with_optional_format


def is_localized_string(s):
    return hasattr(s, "localize")
