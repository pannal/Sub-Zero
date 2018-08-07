# coding=utf-8
import logging
import rarfile
from subliminal.exceptions import ConfigurationError

from subliminal.providers.legendastv import LegendasTVSubtitle as _LegendasTVSubtitle, \
    LegendasTVProvider as _LegendasTVProvider, Episode, Movie, guess_matches, guessit, sanitize

logger = logging.getLogger(__name__)


class LegendasTVSubtitle(_LegendasTVSubtitle):
    def __init__(self, language, type, title, year, imdb_id, season, archive, name):
        super(LegendasTVSubtitle, self).__init__(language, type, title, year, imdb_id, season, archive, name)
        self.archive.content = None
        self.release_info = archive.name
        self.page_link = archive.link

    def make_picklable(self):
        self.archive.content = None
        return self

    def get_matches(self, video, hearing_impaired=False):
        matches = set()

        # episode
        if isinstance(video, Episode) and self.type == 'episode':
            # series
            if video.series and (sanitize(self.title) in (
                    sanitize(name) for name in [video.series] + video.alternative_series)):
                matches.add('series')

            # year
            if video.original_series and self.year is None or video.year and video.year == self.year:
                matches.add('year')

            # imdb_id
            if video.series_imdb_id and self.imdb_id == video.series_imdb_id:
                matches.add('series_imdb_id')

        # movie
        elif isinstance(video, Movie) and self.type == 'movie':
            # title
            if video.title and (sanitize(self.title) in (
                    sanitize(name) for name in [video.title] + video.alternative_titles)):
                matches.add('title')

            # year
            if video.year and self.year == video.year:
                matches.add('year')

            # imdb_id
            if video.imdb_id and self.imdb_id == video.imdb_id:
                matches.add('imdb_id')

        # name
        matches |= guess_matches(video, guessit(self.name, {'type': self.type, 'single_value': True}))

        return matches


class LegendasTVProvider(_LegendasTVProvider):
    subtitle_class = LegendasTVSubtitle

    def __init__(self, username=None, password=None):

        # Provider needs UNRAR installed. If not available raise ConfigurationError
        try:
            rarfile.custom_check([rarfile.UNRAR_TOOL], True)
        except rarfile.RarExecError:
            raise ConfigurationError('UNRAR tool not available')

        if any((username, password)) and not all((username, password)):
            raise ConfigurationError('Username and password must be specified')

        self.username = username
        self.password = password
        self.logged_in = False
        self.session = None

    def download_subtitle(self, subtitle):
        super(LegendasTVProvider, self).download_subtitle(subtitle)
        subtitle.archive.content = None

    def get_archives(self, title_id, language_code, title_type, season, episode):
        return super(LegendasTVProvider, self).get_archives.original(self, title_id, language_code, title_type,
                                                                     season, episode)
