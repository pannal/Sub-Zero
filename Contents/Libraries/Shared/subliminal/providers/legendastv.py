# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import logging
import re, io, os, operator

from babelfish import Language
from requests import Session
from unrar import rarfile
from zipfile import ZipFile
from guessit import guess_episode_info, guess_movie_info

from . import ParserBeautifulSoup, Provider, get_version
from .. import __version__
from ..cache import SHOW_EXPIRATION_TIME, region
from ..exceptions import AuthenticationError, ConfigurationError, DownloadLimitExceeded
from ..subtitle import Subtitle, fix_line_ending, guess_matches, compute_score
from ..video import Episode, Movie

logger = logging.getLogger(__name__)

class LegendasTVSubtitle(Subtitle):
    provider_name = 'legendastv'

    def __init__(self, filename, language, page_link, video, hearing_impaired=False):
        super(LegendasTVSubtitle, self).__init__(language, hearing_impaired, page_link)
        self.filename = filename
        self.download_link = page_link
        self.video = video

    @property
    def id(self):
        return self.download_link

    def get_matches(self, video, hearing_impaired=False):
        matches = super(LegendasTVSubtitle, self).get_matches(video, hearing_impaired=hearing_impaired)

        # release_group 
        if video.release_group and video.release_group.lower() in self.filename.lower():
            matches.add('release_group')
        # resolution 
        if video.resolution and video.resolution.lower() in self.filename.lower():
            matches.add('resolution')
        # format 
        if video.format and video.format.lower() in self.filename.lower():
            matches.add('format')
            
        # remove ' from series to improve matches
        if isinstance(video, Episode) and video.series:
            video.series = video.series.replace("'", "")

        # prevent title from matching as it is counted as 0 for episodes
        if isinstance(video, Episode) and video.title:
            video.title = None

        # episode
        if isinstance(video, Episode):
            matches |= guess_matches(video, guess_episode_info(self.filename + '.mkv'))
        # movie
        elif isinstance(video, Movie):
            matches |= guess_matches(video, guess_movie_info(self.filename + '.mkv'))

        return matches

class LegendasTVProvider(Provider):
    languages = {Language('por', 'BR')} | {Language(l) for l in [
        'eng', 'por', 'spa'
    ]}
    server_url = 'http://legendas.tv/'

    def __init__(self, username=None, password=None, epScore=0):
        if username is not None and password is None or username is None and password is not None:
            raise ConfigurationError('Username and password must be specified')

        self.username = username
        self.password = password
        self.epScore = int(epScore)
        self.logged_in = False

    def initialize(self):
        self.session = Session()
        self.session.headers = {'User-Agent': 'Subliminal/%s' % get_version(__version__)}

        # login
        if self.username is not None and self.password is not None:
            logger.info('Logging in')
            data = {'data[User][username]': self.username, 'data[User][password]': self.password, 'Submit': 'Log in'}
            r = self.session.post(self.server_url + 'login', data, allow_redirects=False, timeout=10)

            if r.status_code != 302:
                raise AuthenticationError(self.username)

            logger.debug('Logged in')
            self.logged_in = True

    def terminate(self):
        # logout
        if self.logged_in:
            logger.info('Logging out')
            r = self.session.get(self.server_url + 'users/logout', timeout=10)
            r.raise_for_status()
            logger.debug('Logged out')
            self.logged_in = False

        self.session.close()

    @region.cache_on_arguments(expiration_time=SHOW_EXPIRATION_TIME)
    def query(self, video, languages):
        if isinstance(video, Episode):
          termo = video.series + ' S%02d' % video.season + 'E%02d' % video.episode
        else:
          termo = video.title
        url = self.server_url + 'legenda/busca/' + termo.replace("'", "*")
        logger.info('Opening search page: %r', url)
        r = self.session.get(url, params={}, timeout=10)
        r.raise_for_status()
        soup = ParserBeautifulSoup(r.content, ['lxml', 'html.parser'])

        # loop over subtitle rows
        subtitles = []
        for row in soup.select('.list_element article > div'):
            filename = row.a.text
            download = row.a['href'].replace('download', 'downloadarquivo')
            language = Language.fromlegendastv(row.img['title'])

            # save video as well in order to get best match inside archive
            subtitle = LegendasTVSubtitle(filename, language, download, video)
            logger.debug('Found subtitle %r', subtitle)
            subtitles.append(subtitle)

        return subtitles

    def list_subtitles(self, video, languages):
        return [s for s in self.query(video, languages)
                if s.language in languages]
    def download_subtitle(self, subtitle):
        # download the subtitle
        logger.info('Downloading subtitle %r', subtitle)
        r = self.session.get(self.server_url + subtitle.download_link, headers={'Referer': subtitle.page_link},
                             timeout=10)
        r.raise_for_status()

        subs = []
        if r.url.endswith('.rar'):
            with open('DataItems/tempsub.rar', 'wb') as fd:
                for chunk in r.iter_content(10):
                    fd.write(chunk)
                fd.close()
            archive = rarfile.RarFile('DataItems/tempsub.rar')
        elif r.url.endswith('.zip'):
            archive = ZipFile(io.BytesIO(r.content))

        for subarq in archive.namelist():
            if not '.srt' in subarq:
                logger.debug('Ignoring not SRT in archive')
                continue
            subs.append(LegendasTVSubtitle(subarq, '', '', ''))

        # get scores for matches in archive
        scored_subtitles = sorted([(s, compute_score(s.get_matches(subtitle.video), subtitle.video))
                                    for s in subs], key=operator.itemgetter(1), reverse=True)

        try:
            for sub, score in scored_subtitles:
                if isinstance(subtitle.video, Episode) and score < self.epScore:
                    logger.error('Discarding low score episode archive (%d < %d)', score, self.epScore)
                    subtitle.content = "!!!INVALID!!!"
                    break
                
                logger.info('Saving best match from archive: %r', sub.filename)
                if r.url.endswith('.rar'):
                    subtitle.content = fix_line_ending(archive.read_files(sub.filename)[0][1])
                elif r.url.endswith('.zip'):
                    subtitle.content = fix_line_ending(archive.read(sub.filename))
                break
        except:
            logger.error('Error saving .srt file')

        if r.url.endswith('.rar'):
            os.remove('DataItems/tempsub.rar')
