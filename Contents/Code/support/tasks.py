# coding=utf-8
import glob
import os
import datetime
import operator
import traceback
from urllib2 import URLError

from subliminal_patch.score import compute_score
from subliminal_patch.core import download_subtitles
from subliminal import list_subtitles as list_all_subtitles, region as subliminal_cache_region
from subzero.language import Language
from subzero.video import refine_video

from missing_subtitles import items_get_all_missing_subs, refresh_item
from scheduler import scheduler
from storage import save_subtitles, get_subtitle_storage
from support.config import config
from support.items import get_recent_items, get_item, is_ignored, get_item_title
from support.helpers import track_usage, get_title_for_video_metadata, cast_bool, PartUnknownException
from support.plex_media import get_plex_metadata
from support.scanning import scan_videos
from support.i18n import _
from download import download_best_subtitles, pre_download_hook, post_download_hook, language_hook


class Task(object):
    name = None
    scheduler = None
    periodic = False
    running = False
    time_start = None
    data = None

    PROVIDER_SLACK = 30
    DL_PROVIDER_SLACK = 30

    stored_attributes = ("last_run", "last_run_time", "running")
    default_data = {"last_run": None, "last_run_time": None, "running": False, "data": {}}

    # task ready for being status-displayed?
    ready_for_display = False

    def __init__(self):
        self.name = self.get_class_name()
        self.ready_for_display = False
        self.time_start = None
        self.setup_defaults()

        self.running = False

    def get_class_name(self):
        return getattr(getattr(self, "__class__"), "__name__")

    def __getattribute__(self, name):
        if name in object.__getattribute__(self, "stored_attributes"):
            return Dict["tasks"].get(self.name, {}).get(name, None)

        return object.__getattribute__(self, name)

    def __setattr__(self, name, value):
        if name in object.__getattribute__(self, "stored_attributes"):
            Dict["tasks"][self.name][name] = value
            Dict.Save()
            return

        object.__setattr__(self, name, value)

    def setup_defaults(self):
        if self.name not in Dict["tasks"]:
            Dict["tasks"][self.name] = self.default_data.copy()
            return

        sd = Dict["tasks"][self.name]

        # forward-migration
        for key, def_value in self.default_data.iteritems():
            hasval = key in sd
            if not hasval:
                sd[key] = def_value

    def signal(self, *args, **kwargs):
        raise NotImplementedError

    def prepare(self, *args, **kwargs):
        return

    def run(self):
        Log.Info(u"Task: running: %s", self.name)
        self.time_start = datetime.datetime.now()

    def post_run(self, data_holder):
        self.running = False
        self.last_run = datetime.datetime.now()
        if self.time_start and self.last_run:
            self.last_run_time = self.last_run - self.time_start
        self.time_start = None
        Log.Info(u"Task: ran: %s", self.name)


class SubtitleListingMixin(object):
    def list_subtitles(self, rating_key, item_type, part_id, language, skip_wrong_fps=True, metadata=None,
                       scanned_parts=None, air_date_cutoff=None):

        if not metadata:
            metadata = get_plex_metadata(rating_key, part_id, item_type)

        if not metadata:
            return

        providers = config.get_providers(media_type="series" if item_type == "episode" else "movies")
        if not scanned_parts:
            scanned_parts = scan_videos([metadata], ignore_all=True, providers=providers)
            if not scanned_parts:
                Log.Error(u"%s: Couldn't list available subtitles for %s", self.name, rating_key)
                return

        video, plex_part = scanned_parts.items()[0]
        refine_video(video, refiner_settings=config.refiner_settings)

        if air_date_cutoff is not None and metadata["item"].year and \
            metadata["item"].year + air_date_cutoff < datetime.date.today().year:
            Log.Debug("Skipping searching for subtitles: %s, it aired over %s year(s) ago.", rating_key,
                      air_date_cutoff)
            return

        config.init_subliminal_patches()

        provider_settings = config.provider_settings
        if not skip_wrong_fps:
            provider_settings["opensubtitles"]["skip_wrong_fps"] = False

        if item_type == "episode":
            min_score = 240
            if video.is_special:
                min_score = 180
        else:
            min_score = 60

        languages = {Language.fromietf(language)}

        available_subs = list_all_subtitles([video], languages,
                                            providers=providers,
                                            provider_configs=provider_settings,
                                            pool_class=config.provider_pool,
                                            throttle_callback=config.provider_throttle,
                                            language_hook=language_hook)

        use_hearing_impaired = Prefs['subtitles.search.hearingImpaired'] in ("prefer", "force HI")

        # sort subtitles by score
        unsorted_subtitles = []
        for s in available_subs[video]:
            Log.Debug(u"%s: Starting score computation for %s", self.name, s)
            try:
                matches = s.get_matches(video)
            except AttributeError:
                Log.Error(u"%s: Match computation failed for %s: %s", self.name, s, traceback.format_exc())
                continue

            # skip wrong season/episodes
            if item_type == "episode":
                can_verify_series = True
                if not s.hash_verifiable and "hash" in matches:
                    can_verify_series = False

                if can_verify_series and not {"series", "season", "episode"}.issubset(matches):
                    Log.Debug(u"%s: Skipping %s, because it doesn't match our series/episode", self.name, s)
                    continue

            unsorted_subtitles.append(
                (s, compute_score(matches, s, video, hearing_impaired=use_hearing_impaired), matches))
        scored_subtitles = sorted(unsorted_subtitles, key=operator.itemgetter(1), reverse=True)

        subtitles = []
        for subtitle, score, matches in scored_subtitles:
            # check score
            if score < min_score:
                Log.Info(u'%s: Score %d is below min_score (%d)', self.name, score, min_score)
                continue
            subtitle.score = score
            subtitle.matches = matches
            subtitle.part_id = part_id
            subtitle.item_type = item_type
            subtitles.append(subtitle)
        return subtitles


class DownloadSubtitleMixin(object):
    def download_subtitle(self, subtitle, rating_key, mode="m"):
        from interface.menu_helpers import set_refresh_menu_state

        item_type = subtitle.item_type
        part_id = subtitle.part_id
        metadata = get_plex_metadata(rating_key, part_id, item_type)
        providers = config.get_providers(media_type="series" if item_type == "episode" else "movies")
        scanned_parts = scan_videos([metadata], ignore_all=True, providers=providers)
        video, plex_part = scanned_parts.items()[0]

        pre_download_hook(subtitle)

        # downloaded_subtitles = {subliminal.Video: [subtitle, subtitle, ...]}
        download_subtitles([subtitle], providers=providers,
                           provider_configs=config.provider_settings,
                           pool_class=config.provider_pool, throttle_callback=config.provider_throttle)

        post_download_hook(subtitle)

        # may be redundant
        subtitle.pack_data = None

        download_successful = False

        if subtitle.content:
            try:
                save_subtitles(scanned_parts, {video: [subtitle]}, mode=mode, mods=config.default_mods)
                if mode == "m":
                    Log.Debug(u"%s: Manually downloaded subtitle for: %s", self.name, rating_key)
                    track_usage("Subtitle", "manual", "download", 1)
                elif mode == "b":
                    Log.Debug(u"%s: Downloaded better subtitle for: %s", self.name, rating_key)
                    track_usage("Subtitle", "better", "download", 1)
                download_successful = True
                refresh_item(rating_key)

            except:
                Log.Error(u"%s: Something went wrong when downloading specific subtitle: %s",
                          self.name, traceback.format_exc())
            finally:
                set_refresh_menu_state(None)

                if download_successful:
                    # store item in history
                    from support.history import get_history
                    item_title = get_title_for_video_metadata(metadata, add_section_title=False)
                    history = get_history()
                    history.add(item_title, video.id, section_title=video.plexapi_metadata["section"],
                                subtitle=subtitle,
                                mode=mode)
                    history.destroy()

                    # clear missing subtitles menu data
                    if not scheduler.is_task_running("MissingSubtitles"):
                        scheduler.clear_task_data("MissingSubtitles")
        else:
            set_refresh_menu_state(_(u"%(class_name)s: Subtitle download failed (%(item_id)s)",
                                     class_name=self.name,
                                     item_id=rating_key))
        return download_successful


class AvailableSubsForItem(SubtitleListingMixin, Task):
    item_type = None
    part_id = None
    language = None
    rating_key = None

    def prepare(self, *args, **kwargs):
        self.item_type = kwargs.get("item_type")
        self.part_id = kwargs.get("part_id")
        self.language = kwargs.get("language")
        self.rating_key = kwargs.get("rating_key")

    def setup_defaults(self):
        super(AvailableSubsForItem, self).setup_defaults()

        # reset any previous data
        Dict["tasks"][self.name]["data"] = {}

    def run(self):
        super(AvailableSubsForItem, self).run()
        self.running = True
        try:
            track_usage("Subtitle", "manual", "list", 1)
        except:
            Log.Error("Something went wrong with track_usage: %s", traceback.format_exc())

        Log.Debug("Listing available subtitles for: %s", self.rating_key)
        subs = self.list_subtitles(self.rating_key, self.item_type, self.part_id, self.language, skip_wrong_fps=False)
        if not subs:
            self.data = "found_none"
            return

        # we can't have nasty unpicklable stuff like ZipFile, BytesIO etc in self.data
        self.data = [s.make_picklable() for s in subs]

    def post_run(self, task_data):
        super(AvailableSubsForItem, self).post_run(task_data)
        # clean old data
        for key in task_data.keys():
            if key != self.rating_key:
                del task_data[key]
        task_data.update({self.rating_key: {self.language: self.data}})


class DownloadSubtitleForItem(DownloadSubtitleMixin, Task):
    subtitle = None
    rating_key = None

    def prepare(self, *args, **kwargs):
        self.subtitle = kwargs["subtitle"]
        self.rating_key = kwargs["rating_key"]

    def run(self):
        super(DownloadSubtitleForItem, self).run()
        self.running = True
        self.download_subtitle(self.subtitle, self.rating_key)
        self.running = False


class MissingSubtitles(Task):
    rating_key = None
    item_type = None
    part_id = None
    language = None

    def run(self):
        super(MissingSubtitles, self).run()
        self.running = True
        self.data = []
        recent_items = get_recent_items()
        if recent_items:
            self.data = items_get_all_missing_subs(recent_items)

    def post_run(self, task_data):
        super(MissingSubtitles, self).post_run(task_data)
        task_data["missing_subtitles"] = self.data


class SearchAllRecentlyAddedMissing(Task):
    periodic = True

    items_done = None
    items_searching = None
    percentage = 0

    def __init__(self):
        super(SearchAllRecentlyAddedMissing, self).__init__()
        self.items_done = None
        self.items_searching = None
        self.percentage = 0

    def signal_updated_metadata(self, *args, **kwargs):
        return True

    def prepare(self):
        self.items_done = 0
        self.items_searching = 0
        self.percentage = 0
        self.ready_for_display = True

    def run(self):
        super(SearchAllRecentlyAddedMissing, self).run()

        self.running = True
        self.prepare()

        from support.history import get_history
        history = get_history()

        now = datetime.datetime.now()
        min_score_series = int(Prefs["subtitles.search.minimumTVScore2"].strip())
        min_score_movies = int(Prefs["subtitles.search.minimumMovieScore2"].strip())
        series_providers = config.get_providers(media_type="series")
        movie_providers = config.get_providers(media_type="movies")

        is_recent_str = Prefs["scheduler.item_is_recent_age"]
        num, ident = is_recent_str.split()

        max_search_days = 0
        if ident == "days":
            max_search_days = int(num)
        elif ident == "weeks":
            max_search_days = int(num) * 7

        subtitle_storage = get_subtitle_storage()
        recent_files = subtitle_storage.get_recent_files(age_days=max_search_days)

        self.items_searching = len(recent_files)

        download_count = 0
        videos_with_downloads = 0

        config.init_subliminal_patches()

        Log.Info(u"%s: Searching for subtitles for %s items", self.name, self.items_searching)

        def skip_item():
            self.items_searching = self.items_searching - 1
            self.percentage = int(self.items_done * 100 / self.items_searching) if self.items_searching > 0 else 100

        # search for subtitles in viable items
        try:
            for fn in recent_files:
                stored_subs = subtitle_storage.load(filename=fn)
                if not stored_subs:
                    Log.Debug("Skipping item %s because storage is empty", fn)
                    skip_item()
                    continue

                video_id = stored_subs.video_id

                # added_date <= max_search_days?
                if stored_subs.added_at + datetime.timedelta(days=max_search_days) <= now:
                    Log.Debug("Skipping item %s because it's too old", video_id)
                    skip_item()
                    continue

                if stored_subs.item_type == "episode":
                    min_score = min_score_series
                    providers = series_providers
                else:
                    min_score = min_score_movies
                    providers = movie_providers

                parts = []
                plex_item = get_item(video_id)

                if not plex_item:
                    Log.Info(u"%s: Item %s unknown, skipping", self.name, video_id)
                    skip_item()
                    continue

                if is_ignored(video_id, item=plex_item):
                    skip_item()
                    continue

                for media in plex_item.media:
                    parts += media.parts

                downloads_per_video = 0
                hit_providers = False
                for part in parts:
                    part_id = part.id

                    try:
                        metadata = get_plex_metadata(video_id, part_id, stored_subs.item_type)
                    except PartUnknownException:
                        Log.Info(u"%s: Part %s:%s unknown, skipping", self.name, video_id, part_id)
                        continue

                    if not metadata:
                        Log.Info(u"%s: Part %s:%s unknown, skipping", self.name, video_id, part_id)
                        continue

                    Log.Debug(u"%s: Looking for missing subtitles: %s", self.name, get_item_title(plex_item))
                    scanned_parts = scan_videos([metadata], providers=providers)

                    downloaded_subtitles = download_best_subtitles(scanned_parts, min_score=min_score,
                                                                   providers=providers)
                    hit_providers = downloaded_subtitles is not None
                    download_successful = False

                    if downloaded_subtitles:
                        downloaded_any = any(downloaded_subtitles.values())
                        if not downloaded_any:
                            continue

                        try:
                            save_subtitles(scanned_parts, downloaded_subtitles, mode="a", mods=config.default_mods)
                            Log.Debug(u"%s: Downloaded subtitle for item with missing subs: %s", self.name, video_id)
                            download_successful = True
                            refresh_item(video_id)
                            track_usage("Subtitle", "manual", "download", 1)
                        except:
                            Log.Error(u"%s: Something went wrong when downloading specific subtitle: %s", self.name,
                                      traceback.format_exc())
                        finally:
                            scanned_parts = None
                            try:
                                item_title = get_title_for_video_metadata(metadata, add_section_title=False)
                                if download_successful:
                                    # store item in history
                                    for video, video_subtitles in downloaded_subtitles.items():
                                        if not video_subtitles:
                                            continue

                                        for subtitle in video_subtitles:
                                            downloads_per_video += 1
                                            history.add(item_title, video.id, section_title=metadata["section"],
                                                        subtitle=subtitle,
                                                        mode="a")

                                    downloaded_subtitles = None
                            except:
                                Log.Error(u"%s: DEBUG HIT: %s", self.name, traceback.format_exc())

                        Log.Debug(u"%s: Waiting %s seconds before continuing", self.name, self.PROVIDER_SLACK)
                        Thread.Sleep(self.PROVIDER_SLACK)

                download_count += downloads_per_video

                if downloads_per_video:
                    videos_with_downloads += 1

                self.items_done = self.items_done + 1
                self.percentage = int(self.items_done * 100 / self.items_searching) if self.items_searching > 0 else 100

                stored_subs = None

                if downloads_per_video:
                    Log.Debug(u"%s: Subtitles have been downloaded, "
                              u"waiting %s seconds before continuing", self.name, self.DL_PROVIDER_SLACK)
                    Thread.Sleep(self.DL_PROVIDER_SLACK)
                else:
                    if hit_providers:
                        Log.Debug(u"%s: Waiting %s seconds before continuing", self.name, self.PROVIDER_SLACK)
                        Thread.Sleep(self.PROVIDER_SLACK)
        finally:
            subtitle_storage.destroy()
            history.destroy()

        if download_count:
            Log.Debug(u"%s: done. Missing subtitles found for %s/%s items (%s subs downloaded)", self.name,
                      videos_with_downloads, self.items_searching, download_count)
        else:
            Log.Debug(u"%s: done. No subtitles found for %s items", self.name, self.items_searching)

    def post_run(self, task_data):
        super(SearchAllRecentlyAddedMissing, self).post_run(task_data)
        self.ready_for_display = False
        self.percentage = 0
        self.items_done = None
        self.items_searching = None


class LegacySearchAllRecentlyAddedMissing(Task):
    periodic = True
    frequency = "never"
    items_done = None
    items_searching = None
    items_searching_ids = None
    items_failed = None
    percentage = 0

    stall_time = 30

    def __init__(self):
        super(LegacySearchAllRecentlyAddedMissing, self).__init__()
        self.items_done = None
        self.items_searching = None
        self.items_searching_ids = None
        self.items_failed = None
        self.percentage = 0

    def signal(self, signal_name, *args, **kwargs):
        handler = getattr(self, "signal_%s" % signal_name)
        return handler(*args, **kwargs) if handler else None

    def signal_updated_metadata(self, *args, **kwargs):
        item_id = int(args[0])

        if self.items_searching_ids is not None and item_id in self.items_searching_ids:
            self.items_done.append(item_id)
            return True

    def prepare(self, *args, **kwargs):
        self.items_done = []
        recent_items = get_recent_items()
        missing = items_get_all_missing_subs(recent_items, sleep_after_request=0.2)
        ids = set([id for added_at, id, title, item, missing_languages in missing if not is_ignored(id, item=item)])
        self.items_searching = missing
        self.items_searching_ids = ids
        self.items_failed = []
        self.percentage = 0
        self.ready_for_display = True

    def run(self):
        super(LegacySearchAllRecentlyAddedMissing, self).run()
        self.running = True
        missing_count = len(self.items_searching)
        items_done_count = 0

        for added_at, item_id, title, item, missing_languages in self.items_searching:
            Log.Debug(u"Task: %s, triggering refresh for %s (%s)", self.name, title, item_id)
            try:
                refresh_item(item_id)
            except URLError:
                # timeout
                pass
            search_started = datetime.datetime.now()
            tries = 1
            while 1:
                if item_id in self.items_done:
                    items_done_count += 1
                    self.percentage = int(items_done_count * 100 / missing_count) if missing_count > 0 else 100
                    Log.Debug(u"Task: %s, item %s done (%s%%, %s/%s)", self.name, item_id, self.percentage,
                              items_done_count, missing_count)
                    break

                # item considered stalled after self.stall_time seconds passed after last refresh
                if (datetime.datetime.now() - search_started).total_seconds() > self.stall_time:
                    if tries > 3:
                        self.items_failed.append(item_id)
                        Log.Debug(u"Task: %s, item stalled for %s times: %s, skipping", self.name, tries, item_id)
                        break

                    Log.Debug(u"Task: %s, item stalled for %s seconds: %s, retrying", self.name, self.stall_time,
                              item_id)
                    tries += 1
                    try:
                        refresh_item(item_id)
                    except URLError:
                        pass
                    search_started = datetime.datetime.now()
                    Thread.Sleep(1)
                Thread.Sleep(0.1)
            # we can't hammer the PMS, otherwise requests will be stalled
            Thread.Sleep(5)

        Log.Debug("Task: %s, done (%s%%, %s/%s). Failed items: %s", self.name, self.percentage,
                  items_done_count, missing_count, self.items_failed)

    def post_run(self, task_data):
        super(LegacySearchAllRecentlyAddedMissing, self).post_run(task_data)
        self.ready_for_display = False
        self.percentage = 0
        self.items_done = None
        self.items_failed = None
        self.items_searching = None
        self.items_searching_ids = None


class FindBetterSubtitles(DownloadSubtitleMixin, SubtitleListingMixin, Task):
    periodic = True

    # TV: episode, format, series, year, season, video_codec, release_group, hearing_impaired, resolution
    series_cutoff = 357

    # movies: format, title, release_group, year, video_codec, resolution, hearing_impaired
    movies_cutoff = 117

    def signal_updated_metadata(self, *args, **kwargs):
        return True

    def run(self):
        super(FindBetterSubtitles, self).run()
        self.running = True
        better_found = 0
        try:
            max_search_days = int(Prefs["scheduler.tasks.FindBetterSubtitles.max_days_after_added"].strip())
        except ValueError:
            Log.Error(u"Please only put numbers into the FindBetterSubtitles.max_days_after_added setting. Exiting")
            return
        else:
            if max_search_days > 30:
                Log.Error(u"%s: FindBetterSubtitles.max_days_after_added is too big. Max is 30 days.", self.name)
                return

        now = datetime.datetime.now()
        min_score_series = int(Prefs["subtitles.search.minimumTVScore2"].strip())
        min_score_movies = int(Prefs["subtitles.search.minimumMovieScore2"].strip())
        min_score_extracted_series = config.advanced.find_better_as_extracted_tv_score or 352
        min_score_extracted_movies = config.advanced.find_better_as_extracted_movie_score or 82
        overwrite_manually_modified = cast_bool(
            Prefs["scheduler.tasks.FindBetterSubtitles.overwrite_manually_modified"])
        overwrite_manually_selected = cast_bool(
            Prefs["scheduler.tasks.FindBetterSubtitles.overwrite_manually_selected"])

        air_date_cutoff_pref = Prefs["scheduler.tasks.FindBetterSubtitles.air_date_cutoff"]
        if air_date_cutoff_pref == "don't limit":
            air_date_cutoff = None
        else:
            air_date_cutoff = int(air_date_cutoff_pref.split()[0])

        subtitle_storage = get_subtitle_storage()
        viable_item_count = 0

        try:
            for fn in subtitle_storage.get_recent_files(age_days=max_search_days):
                stored_subs = subtitle_storage.load(filename=fn)
                if not stored_subs:
                    continue

                video_id = stored_subs.video_id

                if stored_subs.item_type == "episode":
                    cutoff = self.series_cutoff
                    min_score = min_score_series
                    min_score_extracted = min_score_extracted_series
                else:
                    cutoff = self.movies_cutoff
                    min_score = min_score_movies
                    min_score_extracted = min_score_extracted_movies

                # don't search for better subtitles until at least 30 minutes have passed
                if stored_subs.added_at + datetime.timedelta(minutes=30) > now:
                    Log.Debug(u"%s: Item %s too new, skipping", self.name, video_id)
                    continue

                # added_date <= max_search_days?
                if stored_subs.added_at + datetime.timedelta(days=max_search_days) <= now:
                    continue

                viable_item_count += 1
                ditch_parts = []

                # look through all stored subtitle data
                for part_id, languages in stored_subs.parts.iteritems():
                    part_id = str(part_id)

                    # all languages
                    for language, current_subs in languages.iteritems():
                        current_key = current_subs.get("current")
                        current = current_subs.get(current_key)

                        # currently got subtitle?
                        # fixme: check for existence
                        if not current:
                            continue
                        current_score = current.score
                        current_mode = current.mode

                        # late cutoff met? skip
                        if current_score >= cutoff:
                            Log.Debug(u"%s: Skipping finding better subs, "
                                      u"cutoff met (current: %s, cutoff: %s): %s (%s)",
                                      self.name, current_score, cutoff, stored_subs.title, video_id)
                            continue

                        # got manual subtitle but don't want to touch those?
                        if current_mode == "m" and not overwrite_manually_selected:
                            Log.Debug(u"%s: Skipping finding better subs, "
                                      u"had manual: %s (%s)", self.name, stored_subs.title, video_id)
                            continue

                        # subtitle modifications different from default
                        if not overwrite_manually_modified and current.mods \
                                and set(current.mods).difference(set(config.default_mods)):
                            Log.Debug(u"%s: Skipping finding better subs, it has manual modifications: %s (%s)",
                                      self.name, stored_subs.title, video_id)
                            continue

                        try:
                            subs = self.list_subtitles(video_id, stored_subs.item_type, part_id, language,
                                                       air_date_cutoff=air_date_cutoff)
                        except PartUnknownException:
                            Log.Info(u"%s: Part %s unknown/gone; ditching subtitle info", self.name, part_id)
                            ditch_parts.append(part_id)
                            continue

                        hit_providers = subs is not None

                        if subs:
                            # subs are already sorted by score
                            better_downloaded = False
                            better_tried_download = 0
                            better_visited = 0
                            for sub in subs:
                                if sub.score > current_score and sub.score > min_score:
                                    if current.provider_name == "embedded" and sub.score < min_score_extracted:
                                        Log.Debug(u"%s: Not downloading subtitle for %s, we've got an active extracted "
                                                  u"embedded sub and the min score %s isn't met (%s).",
                                                  self.name, video_id, min_score_extracted, sub.score)
                                        better_visited += 1
                                        break

                                    Log.Debug(u"%s: Better subtitle found for %s, downloading", self.name, video_id)
                                    better_tried_download += 1
                                    ret = self.download_subtitle(sub, video_id, mode="b")
                                    if ret:
                                        better_found += 1
                                        better_downloaded = True
                                        break
                                    else:
                                        Log.Debug(u"%s: Couldn't download/save subtitle. "
                                                  u"Continuing to the next one", self.name)
                                        Log.Debug(u"%s: Waiting %s seconds before continuing",
                                                  self.name, self.DL_PROVIDER_SLACK)
                                        Thread.Sleep(self.DL_PROVIDER_SLACK)
                                better_visited += 1

                            if better_tried_download and not better_downloaded:
                                Log.Debug(u"%s: Tried downloading better subtitle for %s, "
                                          u"but every try failed.", self.name, video_id)

                            elif better_downloaded:
                                Log.Debug(u"%s: Better subtitle downloaded for %s", self.name, video_id)

                            if better_tried_download or better_downloaded:
                                Log.Debug(u"%s: Waiting %s seconds before continuing", self.name, self.DL_PROVIDER_SLACK)
                                Thread.Sleep(self.DL_PROVIDER_SLACK)

                            elif better_visited:
                                Log.Debug(u"%s: Waiting %s seconds before continuing", self.name, self.PROVIDER_SLACK)
                                Thread.Sleep(self.PROVIDER_SLACK)

                            subs = None

                        elif hit_providers:
                            # hit the providers but didn't try downloading? wait.
                            Log.Debug(u"%s: Waiting %s seconds before continuing", self.name, self.PROVIDER_SLACK)
                            Thread.Sleep(self.PROVIDER_SLACK)

                if ditch_parts:
                    for part_id in ditch_parts:
                        try:
                            del stored_subs.parts[part_id]
                        except KeyError:
                            pass
                    subtitle_storage.save(stored_subs)
                    ditch_parts = None

                stored_subs = None

                Thread.Sleep(1)
        finally:
            subtitle_storage.destroy()

        if better_found:
            Log.Debug(u"%s: done. Better subtitles found for %s/%s items", self.name, better_found,
                      viable_item_count)
        else:
            Log.Debug(u"%s: done. No better subtitles found for %s items", self.name, viable_item_count)


class SubtitleStorageMaintenance(Task):
    periodic = True
    frequency = "every 7 days"

    def run(self):
        super(SubtitleStorageMaintenance, self).run()
        self.running = True
        Log.Info(u"%s: Running subtitle storage maintenance", self.name)
        storage = get_subtitle_storage()
        deleted_items = storage.delete_missing(wanted_languages=set(str(l) for l in config.lang_list))
        if deleted_items:
            Log.Info(u"%s: Subtitle information for %d non-existant videos have been cleaned up",
                     self.name, len(deleted_items))
            Log.Debug(u"%s: Videos: %s", self.name, deleted_items)
        else:
            Log.Info(u"%s: Nothing to do", self.name)

        storage.destroy()


class MenuHistoryMaintenance(Task):
    periodic = True
    frequency = "every 7 days"

    def run(self):
        super(MenuHistoryMaintenance, self).run()
        self.running = True
        Log.Info(u"%s: Running menu history maintenance", self.name)
        now = datetime.datetime.now()
        if "menu_history" in Dict:
            for key, timeout in Dict["menu_history"].copy().items():
                if now > timeout:
                    try:
                        del Dict["menu_history"][key]
                    except:
                        pass


class MigrateSubtitleStorage(Task):
    periodic = False
    frequency = None

    def run(self):
        super(MigrateSubtitleStorage, self).run()
        self.running = True
        Log.Info(u"%s: Running subtitle storage migration", self.name)
        storage = get_subtitle_storage()
        for fn in storage.get_all_files():
            if fn.endswith(".json.gz"):
                continue
            Log.Debug(u"%s: Migrating %s", self.name, fn)
            storage.load(None, fn)

        storage.destroy()


class CacheMaintenance(Task):
    periodic = True
    frequency = "every 1 days"

    main_cache_validity = 14  # days
    pack_cache_validity = 4  # days

    def run(self):
        super(CacheMaintenance, self).run()
        self.running = True
        Log.Info(u"%s: Running cache maintenance", self.name)
        now = datetime.datetime.now()

        def remove_expired(path, expiry):
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(path))
            if mtime + datetime.timedelta(days=expiry) < now:
                try:
                    os.remove(path)
                except (IOError, OSError):
                    Log.Debug("Couldn't remove cache file: %s", os.path.basename(path))

        # main cache
        if config.new_style_cache:
            for fn in subliminal_cache_region.backend.all_filenames:
                remove_expired(fn, self.main_cache_validity)

        # archive cache
        for fn in glob.iglob(os.path.join(config.pack_cache_dir, "*.archive")):
            remove_expired(fn, self.pack_cache_validity)


scheduler.register(LegacySearchAllRecentlyAddedMissing)
scheduler.register(SearchAllRecentlyAddedMissing)
scheduler.register(AvailableSubsForItem)
scheduler.register(DownloadSubtitleForItem)
scheduler.register(MissingSubtitles)
scheduler.register(FindBetterSubtitles)
scheduler.register(SubtitleStorageMaintenance)
scheduler.register(MigrateSubtitleStorage)
scheduler.register(MenuHistoryMaintenance)
scheduler.register(CacheMaintenance)
