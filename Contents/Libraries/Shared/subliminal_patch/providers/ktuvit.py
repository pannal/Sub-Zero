# -*- coding: utf-8 -*-
import re
from requests import Session
from requests.cookies import RequestsCookieJar
import json
import logging
from subzero.language import Language
from bs4 import BeautifulSoup
from guessit import guessit

from subliminal_patch.providers import Provider
from subliminal.providers import Episode, Movie
from subliminal_patch.utils import sanitize
from subliminal_patch.subtitle import Subtitle, guess_matches
from subliminal.subtitle import fix_line_ending
from subliminal.exceptions import ConfigurationError, AuthenticationError

from string import hexdigits
from collections import defaultdict
import pbkdf2
from base64 import b64decode, b64encode
from hashlib import sha256
import pyaes

__author__ = "Dor Nizar"

logger = logging.getLogger(__name__)


class KtuvitSubtitle(Subtitle):
    provider_name = 'ktuvit'

    def __init__(self, language, title_id, subtitle_id, series, season, episode, release, year):
        super(KtuvitSubtitle, self).__init__(language, subtitle_id)
        self.title_id = title_id
        self.subtitle_id = subtitle_id
        self.series = series
        self.season = season
        self.episode = episode
        self.release = release
        self.year = year

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

        logger.debug("Ktuvit subtitle criteria match:\n{}".format(matches))
        return matches

    @property
    def id(self):
        return self.subtitle_id


class KtuvitProvider(Provider):
    subtitle_class = KtuvitSubtitle
    languages = {Language.fromalpha2(l) for l in ['he']}
    URL_SERVER = 'https://www.ktuvit.me/'

    URI_LOGIN = 'Login.aspx'
    URI_LOGIN_POST = 'Services/MembershipService.svc/Login'
    URI_SEARCH_TITLE = 'Services/ContentProvider.svc/GetSearchForecast'
    URI_SEARCH_SERIES_SUBTITLE = 'Services/GetModuleAjax.ashx'
    URI_SEARCH_MOVIE_SUBTITLE = "MovieInfo.aspx"
    URI_REQ_SUBTITLE_ID = "Services/ContentProvider.svc/RequestSubtitleDownload"
    URI_DOWNLOAD_SUBTITLE = "Services/DownloadFile.ashx"

    def __init__(self, username=None, password=None):
        if not all((username, password)):
            raise ConfigurationError('Username and password must be specified')

        self.session = None
        self.username = username
        self.password = password
        self.encrypted_password = None
        self.salt = None

    def encrypt_password(self):
        logger.debug("password: {}".format(self.password))
        encrypted_password = KtuvitEncryptor(self.username, self.password, self.salt).encrypt()
        if not encrypted_password:
            logger.error("Could not encrypt password")
            return False
        self.encrypted_password = encrypted_password
        return True

    def get_encryption_salt(self):
        p = re.compile(r"var encryptionSalt = '(.*)';")
        r = self.session.get(self.URL_SERVER + self.URI_LOGIN)
        r.raise_for_status()

        logger.debug("Searching for encryptionSalt...")
        script_list = [i for i in BeautifulSoup(r.content, 'html.parser').select('div#navbar script') if i.contents]
        for item in script_list:
            search_salt = p.search(item.contents[0])
            if search_salt:
                self.salt = search_salt.group(1)
                return True
        logger.error("Could not get encryptionSalt")
        return False

    def login(self):
        if not self.get_encryption_salt():
            return False
        if not self.encrypt_password():
            return False
        data = {
            "request": {
                "Email": self.username,
                "Password": self.encrypted_password
            }
        }
        logger.debug("Trying to log in using: {}".format(json.dumps(data)))
        r = self.session.post(self.URL_SERVER + self.URI_LOGIN_POST, json=data)
        r_result = r.json()
        login_results = ""
        if 'd' in r_result:
            try:
                login_results = json.loads(r_result['d'])
            except ValueError:
                logger.error("Could not process JSON from login response")
                return False

        if 'IsSuccess' not in login_results:
            logger.error("Login response is different than expected")
            return False

        if not login_results['IsSuccess']:
            logger.error("Wrong username or password!")
            raise AuthenticationError('Wrong username or password!')
            return False

        if not r.cookies or type(r.cookies) is not RequestsCookieJar:
            logger.error("Could not get the cookie response of the login")
            return False

        if 'Login' not in r.cookies.keys():
            logger.error("Could not found login cookie!")
            return False

        logger.info("Connected successfully to Ktuvit!")
        return True

    def initialize(self):
        logger.debug("Ktuvit initialize")
        self.session = Session()
        self.session.headers[
            'User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; ' \
                            'Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/77.0.3865.90 Safari/537.36'

        if not self.login():
            return False

    def terminate(self):
        logger.debug("Ktuvit terminate")
        self.session.close()

    def _search_series(self, title):
        logger.debug("Searching '{}'".format(title))
        title_request = {
            "request": {
                "SearchString": title,
                "SearchType": "Film"
            }
        }
        r = self.session.post(self.URL_SERVER + self.URI_SEARCH_TITLE, json=title_request, allow_redirects=False,
                              timeout=10)
        r.raise_for_status()
        series_found = r.json()
        if 'd' in series_found:
            try:
                series_found = json.loads(series_found['d'])
            except ValueError:
                series_found = None
        if 'Items' in series_found:
            return series_found['Items']
        return []

    def _search_subtitles(self, title_id, season=None, episode=None):
        if season and episode:
            params = {
                'moduleName': 'SubtitlesList',
                'SeriesID': title_id,
                'Season': season,
                'Episode': episode
            }
            r = self.session.get(url=self.URL_SERVER + self.URI_SEARCH_SERIES_SUBTITLE, params=params)
        else:
            params = {
                'ID': title_id,
            }
            r = self.session.get(url=self.URL_SERVER + self.URI_SEARCH_MOVIE_SUBTITLE, params=params)

        r.raise_for_status()
        results = r.content
        if not results:
            return []
        subtitles = BeautifulSoup(results, 'html.parser').select('a.fa')
        logger.debug("[BS4] Elements found:\n{}".format(subtitles))
        subtitle_list = []
        for i in subtitles:
            subtitle_id = i.attrs['data-subtitle-id']
            release = i.findParent().findParent().text.strip().split('\n')[0]
            subtitle_list.append((subtitle_id, release))

        return subtitle_list  # [(Subtitle ID, name), (....)]

    def _req_download_identifier(self, title_id, subtitle_id):
        logger.debug("Request subtitle identifier for: title id: {}, subtitle id: {}".format(title_id, subtitle_id))
        data = {
            'request': {
                'FilmID': title_id,
                'SubtitleID': subtitle_id,
                'FontSize': 0,
                'FontColor': "",
                'PredefinedLayout': -1
            }
        }

        r = self.session.post(self.URL_SERVER + self.URI_REQ_SUBTITLE_ID, json=data, allow_redirects=False,
                              timeout=10)
        r.raise_for_status()
        try:
            r = json.loads(r.json()['d'])
        except ValueError:
            r = {}

        if 'DownloadIdentifier' not in r:
            logger.error("Download Identifier not found")
            return None
        return r['DownloadIdentifier']

    def _download_subtitles(self, download_id):
        logger.debug("Downloading subtitles by download identifier - {}".format(download_id))
        data = {'DownloadIdentifier': download_id}
        r = self.session.get(self.URL_SERVER + self.URI_DOWNLOAD_SUBTITLE, params=data,
                             timeout=10)
        r.raise_for_status()
        if not r.content:
            logger.debug("Download subtitle failed")
            return None

        logger.debug("Download subtitle success")
        return r.content

    def query(self, title, season=None, episode=None, year=None):
        subtitles = []
        titles = self._search_series(title)
        if season and episode:
            logger.debug("Searching for:\nTitle: {}\nSeason: {}\nEpisode: {}\nYear: {}".format(title, season,
                                                                                               episode, year))
        else:
            logger.debug("Searching for:\nTitle: {}\nYear: {}\n".format(title, year))
        for title in titles:
            logger.debug("Title Candidate: {}".format(title))
            title_id = title['ID']
            if season and episode:
                result = self._search_subtitles(title_id, season, episode)
            else:
                result = self._search_subtitles(title_id)

            if not result:
                continue

            for subtitle_id, release in result:
                subtitles.append(self.subtitle_class(next(iter(self.languages)), title_id, subtitle_id,
                                                     title['EngName'], season, episode, release, year))

        if subtitles:
            logger.debug("Found Subtitle Candidates: {}".format(subtitles))
        return subtitles

    def list_subtitles(self, video, languages):
        season = episode = year = title = None

        if isinstance(video, Episode):
            logger.info("list_subtitles Series: {}, season: {}, episode: {}".format(video.series,
                                                                                    video.season,
                                                                                    video.episode))
            title = video.series
            season = video.season
            episode = video.episode
        elif isinstance(video, Movie):
            logger.info("list_subtitles Movie: {}, year: {}".format(video.title, video.year))
            title = video.title
            year = video.year

        return [s for s in self.query(title, season, episode, year) if s.language in languages]

    def download_subtitle(self, subtitle):
        # type: (KtuvitSubtitle) -> None

        logger.info('Downloading subtitle from Ktuvit: %r', subtitle)
        download_id = self._req_download_identifier(subtitle.title_id, subtitle.subtitle_id)
        if not download_id:
            logger.debug('Unable to retrieve download identifier')
            return None

        content = self._download_subtitles(download_id)
        if not content:
            logger.debug('Unable to download subtitle')
            return None

        subtitle.content = fix_line_ending(content)


class KtuvitEncryptor:
    def __init__(self, username, password, salt):
        if not all((username, password, salt)):
            raise Exception("Encryptor did not get all required arguments")

        self.encrypted_password = None
        self.username = username
        self.password = password
        self.salt = salt

    @staticmethod
    def rshift(val, n):
        return (val % 0x100000000) >> n

    @staticmethod
    def js_parseint(s, rad=10):
        digits = ''
        for c in str(s).strip():
            if c not in hexdigits:
                break
            digits += c

        return int(digits, rad) if digits else 0

    @staticmethod
    def to_signed32(n):
        n = n & 0xffffffff
        return n | (-(n & 0x80000000))

    def stringify(self, words, length):
        sigbytes = int(length / 2) + int((length % 2) > 0)
        hex_chars = list()

        for i in xrange(0, sigbytes):
            bite = self.rshift(words[self.rshift(i, 2)], (24 - (i % 4) * 8)) & 0xff
            hex_chars.append(format(self.rshift(bite, 4), 'x'))
            hex_chars.append(format(bite & 0x0f, 'x'))
        return ''.join(hex_chars)

    def cryptojs_hexparse(self, s):
        words = defaultdict(int)
        for i in range(0, len(s), 2):
            tmp1 = (self.js_parseint(s[i:i + 2], 16))
            tmp2 = (24 - (i % 8) * 4)
            tmp3 = self.to_signed32(tmp1 << tmp2)
            words[self.rshift(i, 3)] |= tmp3
        return self.stringify(words, len(s))

    def cryptojs_pad_iv(self, iv):
        return str.ljust(self.cryptojs_hexparse(iv), 32, '0').decode('hex')

    @staticmethod
    def pbkdf2_encrypt(key, salt):
        a = pbkdf2.PBKDF2(salt, key, 3000)
        return a.read(16)

    @staticmethod
    def pad(m):
        return m + chr(16 - len(m) % 16) * (16 - len(m) % 16)

    def aes_encrypt(self, msg, key, iv):
        if len(iv) != 16:
            logger.error("iv (Len: {}) - {} is not 16 length".format(len(iv), iv))
            return False
        msg = self.pad(msg)

        aes = pyaes.AESModeOfOperationCBC(key, iv=iv[:16])
        return b64encode(aes.encrypt(msg))

    def encrypt(self):
        if not self.salt:
            logger.error("No salt was instantiated!")
            return False
        msg = self.password.encode('utf-8')
        iv = self.cryptojs_pad_iv(self.username)
        key = self.pbkdf2_encrypt(self.username, self.salt.encode('utf-8'))

        cipher = self.aes_encrypt(msg, key, iv)
        if not cipher:
            return False

        hash_sha256 = sha256(b64decode(cipher))
        self.encrypted_password = b64encode(hash_sha256.digest())
        logger.debug("Encrypted password: {}".format(self.encrypted_password))
        logger.debug("Original password: {}".format(self.password))
        return self.encrypted_password
