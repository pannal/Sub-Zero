# coding=utf-8

import logging

import chardet
import pysrt
import pysubs2
from bs4 import UnicodeDammit
from subliminal.video import Episode, Movie
from subliminal import Subtitle

logger = logging.getLogger(__name__)


def compute_score(matches, video, scores=None):
    """Compute the score of the `matches` against the `video`.
    Some matches count as much as a combination of others in order to level the final score:
      * `hash` removes everything else
      * For :class:`~subliminal.video.Episode`
        * `imdb_id` removes `series`, `tvdb_id`, `season`, `episode`, `title` and `year`
        * `tvdb_id` removes `series` and `year`
        * `title` removes `season` and `episode`
    :param video: the video to get the score with.
    :type video: :class:`~subliminal.video.Video`
    :param dict scores: scores to use, if `None`, the :attr:`~subliminal.video.Video.scores` from the video are used.
    :return: score of the subtitle.
    :rtype: int

    # patch: remove score cap for enabling individual boost
    """
    final_matches = matches.copy()
    scores = scores or video.scores

    logger.info('Computing score for matches %r and %r', matches, video)

    is_episode = isinstance(video, Episode)

    episode_hash_valid_if = {"series", "season", "episode", "format"}
    movie_hash_valid_if = {"video_codec", "format"}

    # remove equivalent match combinations
    if 'hash' in final_matches:
        # hash is error-prone, try to fix that
        hash_valid_if = episode_hash_valid_if if is_episode else movie_hash_valid_if

        if hash_valid_if <= set(final_matches):
            # series, season and episode matched, hash is valid
            logger.debug('Using valid hash, as %s are correct (%r) and (%r)', hash_valid_if, matches, video)
            final_matches &= {'hash', 'hearing_impaired'}
        else:
            # no match, invalidate hash
            logger.debug('Ignoring hash as other matches are wrong (missing: %r) and (%r)', hash_valid_if - matches, video)
            final_matches -= {"hash"}

    elif is_episode:
        if 'imdb_id' in final_matches:
            final_matches -= {'series', 'tvdb_id', 'season', 'episode', 'title', 'year'}
        if 'tvdb_id' in final_matches:
            final_matches -= {'series', 'year'}

    # compute score
    logger.debug('Final matches: %r', final_matches)
    score = sum((scores[match] for match in final_matches))
    logger.info('Computed score %d', score)

    return score


class PatchedSubtitle(Subtitle):
    storage_path = None
    release_info = None
    matches = None

    def guess_encoding(self):
        """Guess encoding using the language, falling back on chardet.

        :return: the guessed encoding.
        :rtype: str

        """
        logger.info('Guessing encoding for language %s', self.language.alpha3)

        encodings = ['utf-8']

        # add language-specific encodings
        if self.language.alpha3 == 'zho':
            encodings.extend(['gb18030', 'big5'])
        elif self.language.alpha3 == 'jpn':
            encodings.append('shift-jis')
        elif self.language.alpha3 == 'tha':
            encodings.append('tis-620')

        # arabian/farsi
        elif self.language.alpha3 in ('ara', 'fas', 'per'):
            encodings.append('windows-1256')
        elif self.language.alpha3 == 'heb':
            encodings.append('windows-1255')
        elif self.language.alpha3 == 'tur':
            encodings.extend(['iso-8859-9', 'windows-1254'])

        # Greek
        elif self.language.alpha3 in ('grc', 'gre', 'ell'):
            encodings.extend(['windows-1253', 'cp1253', 'cp737', 'iso8859_7', 'cp875', 'cp869', 'iso2022_jp_2',
                              'mac_greek'])

        # Polish, Czech, Slovak, Hungarian, Slovene, Bosnian, Croatian, Serbian (Latin script),
        # Romanian (before 1993 spelling reform) and Albanian
        elif self.language.alpha3 in ('pol', 'cze', 'svk', 'hun', 'svn', 'bih', 'hrv', 'srb', 'rou', 'alb'):
            # Eastern European Group 1
            encodings.append('windows-1250')

        # Bulgarian, Serbian and Macedonian Patched by PACETO
        elif self.language.alpha3 in ('bul'):
            # Eastern European Group 2
            encodings.append('windows-1251')
        else:
            # Western European (windows-1252)
            encodings.append('latin-1')

        # try to decode
        logger.debug('Trying encodings %r', encodings)
        for encoding in encodings:
            try:
                self.content.decode(encoding)
            except UnicodeDecodeError:
                pass
            else:
                logger.info('Guessed encoding %s', encoding)
                return encoding

        logger.warning('Could not guess encoding from language')

        # fallback on chardet
        encoding = chardet.detect(self.content)['encoding']
        logger.info('Chardet found encoding %s', encoding)

        if not encoding:
            # fallback on bs4
            logger.info('Falling back to bs4 detection')
            a = UnicodeDammit(self.content)

            Log.Debug("bs4 detected encoding: %s" % a.original_encoding)

            if a.original_encoding:
                return a.original_encoding
            raise ValueError(u"Couldn't guess the proper encoding for %s" % self)

        return encoding

    def is_valid(self):
        """Check if a :attr:`text` is a valid SubRip format.

        :return: whether or not the subtitle is valid.
        :rtype: bool

        """
        if not self.text:
            return False

        # valid srt
        try:
            pysrt.from_string(self.text, error_handling=pysrt.ERROR_RAISE)
        except Exception, e:
            logger.error("PySRT-parsing failed: %s, trying pysubs2", e)
        else:
            return True

        # something else, try to return srt
        try:
            logger.debug("Trying parsing with PySubs2")
            subs = pysubs2.SSAFile.from_string(self.text)
            self.content = subs.to_string("srt")
        except:
            logger.exception("Couldn't convert subtitle %s to .srt format", self)
            return False

        return True
