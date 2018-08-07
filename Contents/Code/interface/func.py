# coding=utf-8

import datetime
import operator

from support.config import config
from support.helpers import timestamp


def enable_channel_wrapper(func):
    """
    returns the original wrapper :func: (route or handler) if applicable, else the plain to-be-wrapped function
    :param func: original wrapper
    :return: original wrapper or wrapped function
    """
    def noop(*args, **kwargs):
        def inner(*a, **k):
            """
            :param a: args
            :param k: kwargs
            :return: originally to-be-wrapped function
            """
            return a[0]

        return inner

    def wrap(*args, **kwargs):
        enforce_route = kwargs.pop("enforce_route", None)
        return (func if (config.enable_channel or enforce_route) else noop)(*args, **kwargs)

    return wrap


ROUTE_REGISTRY = {}


def get_func_name(args):
    return list(args).pop(0).__name__


def get_lookup_key(f, args, kwargs):
    return tuple([f.__name__, tuple(args), tuple([(key, value) for key, value in kwargs.iteritems()])])


def should_debounce(f, key, kw):
    return getattr(f, "debounce", False) and "randomize" in kw and key in Dict["menu_history"]


def register_route_function(f):
    fn = f.__name__
    if fn != "ValidatePrefs" and fn not in ROUTE_REGISTRY:
        ROUTE_REGISTRY[fn] = f
    return f


def main_menu_fallback():
    key = get_lookup_key(ROUTE_REGISTRY["fatality"], [], {})
    Dict["last_menu_item"] = key
    add_to_menu_history(key)

    return ROUTE_REGISTRY["fatality"](randomize=timestamp())


def add_to_menu_history(key):
    # add function to menu history
    mh = Dict["menu_history"]
    if key in mh:
        del mh[key]

    mh[key] = datetime.datetime.now() + datetime.timedelta(hours=6)

    # limit to 25 items
    Dict["menu_history"] = dict(sorted(sorted(mh.items(), key=operator.itemgetter(1),
                                              reverse=True)[:25]))

    try:
        Dict.Save()
    except TypeError:
        Log.Error("Can't save menu history for: %r", key)
        del Dict["menu_history"][key]


def route_wrapper(*args, **kwargs):
    def wrap(f):
        already_wrapped = getattr(f, "orig_f", False)

        register_route_function(f)

        def inner(*a, **kw):
            if "menu_history" not in Dict:
                Dict["menu_history"] = {}

            if "last_menu_item" not in Dict:
                Dict["last_menu_item"] = None

            key = get_lookup_key(f, list(a), kw)

            ret_f = f
            ret_a = a
            ret_kw = kw
            # mh = Dict["menu_history"]
            # mh_keys = [k for k, v in sorted(mh.items(), key=operator.itemgetter(1))]
            #
            # fallback_needed = False
            # fallback_found = False

            if should_debounce(ret_f, key, kw):
                # special case for TriggerRestart
                if ret_f.__name__ in ("TriggerRestart", "Restart"):
                    Log.Debug("Don't trigger a re-restart, falling back to main menu")
                else:
                    Log.Debug("not triggering %s twice with %s, %s, returning to main menu" %
                              (f.__name__, a, kw))

                return main_menu_fallback()
                #
                # fallback_needed = True
                #
                # # try to find a suitable fallback route in case we've encountered an already visited
                # # debounced route
                # fallbacks = []
                # current_last_visit = mh[key]
                # last_menu_item = Dict["last_menu_item"]
                # direction_backwards = True
                #
                # if last_menu_item and last_menu_item in mh and key in mh:
                #     last_mi_pos = mh_keys.index(last_menu_item)
                #     current_mi_pos = mh_keys.index(key)
                #     if current_mi_pos > -1 and last_mi_pos > -1:
                #         print "SHEKEL", current_mi_pos, last_mi_pos, current_mi_pos < last_mi_pos

                # only consider items in menu history that have an older timestamp than the current
                # for key_, last_visit in sorted(mh.items(), key=operator.itemgetter(1),
                #                                reverse=True):
                #     if last_visit < current_last_visit:
                #         fallbacks.append(key_)
                #
                # for key_ in fallbacks:
                #     # old data structure
                #     if not len(key_) == 3 or not (isinstance(key_[1], tuple) and isinstance(key_[2], tuple)):
                #         continue
                #
                #     old_f, old_a, old_kw = key_
                #     if old_f == "ValidatePrefs":
                #         continue
                #
                #     possible_fallback = ROUTE_REGISTRY[old_f]
                #
                #     # non-debounced function found
                #     if not getattr(possible_fallback, "debounce", False):
                #         ret_kw = dict(old_kw)
                #         ret_a = old_a
                #         if "randomize" in ret_kw:
                #             ret_kw["randomize"] = timestamp()
                #
                #         ret_f = possible_fallback
                #         key = get_lookup_key(ret_f, list(ret_a), ret_kw)
                #         fallback_found = True
                #
                #         Log.Debug("not triggering %s twice with %s, %s, returning to %s, %s, %s" %
                #                   (f.__name__, a, kw, ret_f.__name__, ret_a, ret_kw))
                #
                #         break
                #
                # if not fallback_found:
                #     Log.Debug("No fallback found in menu history for %s, falling back to main menu", f)
                #     return main_menu_fallback()

            # if not fallback_needed:
            #     add_to_menu_history(key)
            #     if ret_f.__name__ != "ValidatePrefs":
            #         Dict["last_menu_item"] = key
            #
            add_to_menu_history(key)
            Dict["last_menu_item"] = key
            return ret_f(*ret_a, **ret_kw)

        # @route may be used multiple times
        if not already_wrapped:
            inner.orig_f = f

            return enable_channel_wrapper(route(*args, **kwargs))(inner)
        return enable_channel_wrapper(route(*args, **kwargs))(f)

    return wrap
