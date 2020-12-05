# -*- coding: utf-8 -*-
from requests import Session
import logging
from subzero.language import Language
from guessit import guessit

from subliminal_patch.providers import Provider
from subliminal.providers import Episode, Movie
from subliminal_patch.utils import sanitize
from subliminal_patch.subtitle import Subtitle, guess_matches
from subliminal.subtitle import fix_line_ending

from io import BytesIO
from zipfile import ZipFile

__author__ = "Dor Nizar"

logger = logging.getLogger(__name__)


class WizdomSubtitle(Subtitle):
    provider_name = 'wizdom'

    def __init__(self, language, title_id, subtitle_id, series, season, episode, release, year, page_link):
        super(WizdomSubtitle, self).__init__(language, subtitle_id)
        self.title_id = title_id
        self.subtitle_id = subtitle_id
        self.series = series
        self.season = season
        self.episode = episode
        self.release = release
        self.year = year
        self.page_link = page_link

    def get_matches(self, video):
        matches = set()
        logger.debug("[{}]\n{}".format(self.__class__.__name__, self.__dict__))

        # episode
        if isinstance(video, Episode):
            # series
            if video.series and sanitize(self.series) == sanitize(video.series):
                matches.add('series')
            # season
            if video.season and self.season == video.season:
                matches.add('season')
            # episode
            if video.episode and self.episode == video.episode:
                matches.add('episode')
            # guess
            matches |= guess_matches(video, guessit(self.release, {'type': 'episode'}))
        # movie
        elif isinstance(video, Movie):
            # title
            if video.title and (sanitize(self.series) in (
                    sanitize(name) for name in [video.title] + video.alternative_titles)):
                matches.add('title')
            # year
            if video.year and self.year == video.year:
                matches.add('year')
            # guess
            matches |= guess_matches(video, guessit(self.release, {'type': 'movie'}))

        logger.debug("Wizdom subtitle criteria match:\n{}".format(matches))
        return matches

    @property
    def id(self):
        return self.subtitle_id


class WizdomProvider(Provider):
    subtitle_class = WizdomSubtitle
    languages = {Language.fromalpha2(lng) for lng in ['he']}
    URL_JSON_SERVER = 'https://json.wizdom.xyz/'
    URL_DOWNLOAD_SERVER = 'https://zip.wizdom.xyz/'
    URL_WIZDOM_PAGELINK = 'https://wizdom.xyz/{}/{}'

    URL_SEARCH = URL_JSON_SERVER + "search.php?search={}"
    URL_INFO = URL_JSON_SERVER + "{}.json"
    URL_DOWNLOAD_SUBTITLE = URL_DOWNLOAD_SERVER + "{}.zip"

    def __init__(self):
        self.session = None

    def initialize(self):
        logger.info("Wizdom initialize")
        self.session = Session()
        self.session.headers[
            'User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; ' \
                            'Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/77.0.3865.90 Safari/537.36'
        return True

    def terminate(self):
        logger.info("Wizdom terminate")
        self.session.close()

    def _search_series(self, title, movie=False):
        logger.debug("Searching '{}'".format(title))
        r = self.session.get(self.URL_SEARCH.format(title))
        if not r.ok:
            logger.error("Bad response from server while searching: '{}']".format(title))
            return []
        try:
            found = r.json()
        except ValueError:
            logger.error("Could not extract JSON from response")
            return []

        if movie:
            series_list = [x for x in found if 'type' in x and x['type'] == 'movie']
        else:
            series_list = [x for x in found if 'type' in x and x['type'] == 'tv']

        logger.debug("Found the following titles: {}".format([x['title_en'] for x in series_list if 'title_en' in x]))
        return series_list

    def _search_subtitles(self, title_id, season=None, episode=None):
        r = self.session.get(self.URL_INFO.format(title_id))

        if not r.ok:
            logger.error("Bad response from server while searching subtitles [title_id={}]".format(title_id))
            return []
        if not r.content:
            return []
        try:
            results = r.json()
        except ValueError:
            return []

        if 'subs' not in results:
            return []

        if season and episode:
            s_season = str(season)
            s_episode = str(episode)
            if s_season in results['subs'] and s_episode in results['subs'][s_season]:
                return results['subs'][s_season][s_episode]
        else:
            return results['subs']
        return []

    def query(self, title, season=None, episode=None, year=None):
        subtitles = []
        if season and episode:
            logger.debug("Searching for:\nTitle: {}\nSeason: {}\nEpisode: {}\nYear: {}".format(title, season,
                                                                                               episode, year))
            titles = self._search_series(title)
        else:
            logger.debug("Searching for:\nTitle: {}\nYear: {}\n".format(title, year))
            titles = self._search_series(title, movie=True)

        for title in titles:
            title_name = title['title_en']
            title_id = title['imdb']
            if season and episode:
                results = self._search_subtitles(title_id, season, episode)
                page_link = self.URL_WIZDOM_PAGELINK.format("tv", title_id)
            else:
                results = self._search_subtitles(title_id)
                page_link = self.URL_WIZDOM_PAGELINK.format("movie", title_id)

            if not results:
                logger.info("No subtitles found for: {}".format(title_name))
                continue

            for result in results:
                subtitle_id, release = result['id'], result['version']
                subtitles.append(self.subtitle_class(next(iter(self.languages)), title_id, subtitle_id,
                                                     title_name, season, episode, release, year, page_link))

        if subtitles:
            logger.debug("Found Subtitle Candidates: {}".format([x.release for x in subtitles]))
        return subtitles

    def list_subtitles(self, video, languages):
        season = episode = year = title = None

        if isinstance(video, Episode):
            logger.info("list_subtitles Series: {}, season: {}, episode: {}".format(video.series,
                                                                                    video.season,
                                                                                    video.episode))
            title = video.series
            season = video.season
            if video.episode == 0:
                episode = 1
            else:
                episode = video.episode
        elif isinstance(video, Movie):
            logger.info("list_subtitles Movie: {}, year: {}".format(video.title, video.year))
            title = video.title
            year = video.year

        return [s for s in self.query(title, season, episode, year) if s.language in languages]

    def _download_subtitles(self, subtitle_id):
        logger.debug("Downloading subtitle id - {}".format(subtitle_id))
        r = self.session.get(self.URL_DOWNLOAD_SUBTITLE.format(subtitle_id))

        if not r.ok:
            logger.error("Bad response from server while downloding zip [id={}]".format(subtitle_id))
            return None
        if not r.content:
            logger.error("Unable to download zip [id={}]".format(subtitle_id))
            return None

        return r.content

    def download_subtitle(self, subtitle):
        # type: (WizdomSubtitle) -> None

        logger.info('Downloading subtitle from WizdomSubs: %r', subtitle)

        content = None
        zip_content = self._download_subtitles(subtitle.subtitle_id)
        if not zip_content:
            return None
        if not zip_content[:2] == "PK":
            logger.warning("Response did not contain zip file")
            return None

        zfile = ZipFile(BytesIO(zip_content))
        if not len(zfile.namelist()):
            logger.warning("Response did not contain files inside the zip archive")
            return None

        sub_files = [x for x in zfile.namelist() if x.endswith(('.srt', '.idx', '.sub'))]
        if sub_files:
            content = zfile.open(sub_files[0]).read()

        if not content:
            logger.warning("File inside zip is empty")
            return None
        subtitle.content = fix_line_ending(content)
        logger.info("Downloaded {} successfuly!".format(subtitle))
