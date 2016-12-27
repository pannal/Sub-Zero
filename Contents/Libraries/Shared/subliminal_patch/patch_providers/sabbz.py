# coding=utf-8

from babelfish import Language
import logging
from mixins import ProviderRetryMixin
from mixins import PunctuationMixin
import re
from subliminal.cache import SHOW_EXPIRATION_TIME
from subliminal.cache import region
from subliminal.providers import ParserBeautifulSoup
from subliminal.providers.sabbz import SabbzProvider
from subliminal.providers.sabbz import SabbzSubtitle

logger = logging.getLogger(__name__)

class PatchedSabbzSubtitle(SabbzSubtitle):
    def __init__(self, language, page_link, subtitle_id, series, season, episode, year, rip, release):
        super(PatchedSabbzSubtitle, self).__init__(language, page_link, subtitle_id, series, season, episode,
                                                   year, rip, release)
        self.release_info = u"%s, %s" % (rip, release)


class PatchedSabbzProvider(PunctuationMixin, ProviderRetryMixin, SabbzProvider):
    @region.cache_on_arguments(expiration_time=SHOW_EXPIRATION_TIME)
    def search_show_id(self, series, year=None):
        """Search the show id from the `series` and `year`.
        :param string series: series of the episode.
        :param year: year of the series, if any.
        :type year: int or None
        :return: the show id, if any.
        :rtype: int or None
        """
        # make the search
        series_clean = self.clean_punctuation(series).lower()
        logger.info('Searching show id for %r', series_clean)
        r = self.retry(lambda: self.session.get(self.server_url + 'index.php', params={'act': 'search', 'movie': series, 'select-language':1}, timeout=10))
        r.raise_for_status()
        
        # get the series out of the suggestions
        soup = ParserBeautifulSoup(r.content, ['lxml', 'html.parser'])
        show_id = None
        
        for suggestion in soup.select('div.left li div a[href^="/tvshow-"]'):
            show_id = int(suggestion['href'][8:-5])
            logger.debug('Found show id %d', show_id)
            break
        return show_id

    def query(self, series, season, episode, year=None):
        logger.debug('PACETO Dumps series %s', series);
        logger.debug('PACETO Dumps season %s', season);
        logger.debug('PACETO Dumps episode %s', episode);   

        #episode_ids = [];
        # get the episode page
        
        movie = str(series) + ' ' + str(season) + ' ' + str(episode)
        r = self.retry(lambda: self.session.get(self.server_url + 'index.php', params={'act': 'search', 'movie': movie, 'select-language':2}, timeout=10))
        r.raise_for_status()
        
        # get the series out of the suggestions
        soup = ParserBeautifulSoup(r.content, ['lxml', 'html.parser'])        

        # loop over subtitles rows
        subtitles = []
        for row in soup.select('.c2field'):            
            
            # read the item
            language = Language.fromsabbz('bg')
            subtitle_id = int(re.match('.*?([0-9]+)$', row.find('a')['href']).group(1))             
            page_link = row.find('a')['href']
            rip = None
            release = None
            
            logger.info('PACETO Dumps Language %r', language)
            logger.info('PACETO Dumps subtitle_id  %r', subtitle_id)
            logger.info('PACETO Dumps page_link  %r', page_link)
            logger.info('PACETO Dumps rip  %r', rip)
            logger.info('PACETO Dumps release  %r', release)

            subtitle = PatchedSabbzSubtitle(language, page_link, subtitle_id, series, season, episode, year, rip,
                                            release)
            logger.info('Found subtitle %s', subtitle)
            subtitles.append(subtitle)

        return subtitles
