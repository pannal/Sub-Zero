# coding=utf-8
from wraptor.decorators import throttle
from config import config
from items import get_item, get_item_kind_from_item, refresh_item

Activity = None
try:
    from plex_activity import Activity
except ImportError:
    pass


class PlexActivityManager(object):
    def start(self):
        activity_sources_enabled = None

        if not Activity:
            return

        if config.plex_token:
            from plex import Plex
            Plex.configuration.defaults.authentication(config.plex_token)
            activity_sources_enabled = ["websocket"]
            Activity.on('websocket.playing', self.on_playing)

        if activity_sources_enabled:
            Activity.start(activity_sources_enabled)

    @throttle(5, instance_method=True)
    def on_playing(self, info):
        # ignore non-playing states and anything too far in
        if info["state"] != "playing" or info["viewOffset"] > 60000:
            return

        # don't trigger on the first hit ever
        if "last_played_items" not in Dict:
            Dict["last_played_items"] = []
            Dict.Save()
            return

        rating_key = info["ratingKey"]

        # only use integer based rating keys
        try:
            int(rating_key)
        except ValueError:
            return

        if rating_key in Dict["last_played_items"] and rating_key != Dict["last_played_items"][0]:
            # shift last played
            Dict["last_played_items"].insert(0,
                                             Dict["last_played_items"].pop(Dict["last_played_items"].index(rating_key)))
            Dict.Save()

        elif rating_key not in Dict["last_played_items"]:
            # new playing; store last X recently played items
            Dict["last_played_items"].insert(0, rating_key)
            Dict["last_played_items"] = Dict["last_played_items"][:config.store_recently_played_amount]

            Dict.Save()

            if not config.react_to_activities:
                return

            debug_msg = "Started playing %s. Refreshing it." % rating_key

            # todo: cleanup debug messages for hybrid-plus

            keys_to_refresh = []
            if config.activity_mode in ["refresh", "next_episode", "hybrid", "hybrid-plus"]:
                # next episode or next episode and current movie
                if config.activity_mode in ["next_episode", "hybrid", "hybrid-plus"]:
                    plex_item = get_item(rating_key)
                    if not plex_item:
                        Log.Warn("Can't determine media type of %s, skipping" % rating_key)
                        return

                    if get_item_kind_from_item(plex_item) == "episode":
                        next_ep = self.get_next_episode(rating_key)
                        if config.activity_mode == "hybrid-plus":
                            keys_to_refresh.append(rating_key)
                        if next_ep:
                            keys_to_refresh.append(next_ep.rating_key)
                            debug_msg = "Started playing %s. Refreshing next episode (%s, S%02iE%02i)." % \
                                        (rating_key, next_ep.rating_key, int(next_ep.season.index), int(next_ep.index))

                    else:
                        if config.activity_mode == "hybrid":
                            keys_to_refresh.append(rating_key)
                elif config.activity_mode == "refresh":
                    keys_to_refresh.append(rating_key)

                if keys_to_refresh:
                    Log.Debug(debug_msg)
                    Log.Debug("Refreshing %s", keys_to_refresh)
                    for key in keys_to_refresh:
                        refresh_item(key)

    def get_next_episode(self, rating_key):
        plex_item = get_item(rating_key)
        if not plex_item:
            return

        if get_item_kind_from_item(plex_item) == "episode":
            # get season
            season = get_item(plex_item.season.rating_key)
            if not season:
                return

            # determine next episode
            # next episode is in the same season
            if plex_item.index < season.episode_count:
                # get next ep
                for ep in season.children():
                    if ep.index == plex_item.index + 1:
                        return ep

            # it's not, try getting the first episode of the next season
            else:
                # get show
                show = get_item(plex_item.show.rating_key)
                # is there a next season?
                if season.index < show.season_count:
                    for other_season in show.children():
                        if other_season.index == season.index + 1:
                            next_season = other_season
                            for ep in next_season.children():
                                if ep.index == 1:
                                    return ep


activity = PlexActivityManager()
