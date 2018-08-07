# coding=utf-8
import logging

from babelfish import LanguageReverseConverter
from subliminal.exceptions import ConfigurationError

logger = logging.getLogger(__name__)


class TitloviConverter(LanguageReverseConverter):
    def __init__(self):
        self.from_titlovi = {'ba': ('bos',),
                             'en': ('eng',),
                             'hr': ('hrv',),
                             'mk': ('mkd',),
                             'rs': ('srp', None, 'Latn'),
                             'rsc': ('srp', None, 'Cyrl'),
                             'si': ('slv',),
                             }
        self.to_titlovi = {('bos',): 'bosanski',
                           ('eng',): 'english',
                           ('hrv',): 'hrvatski',
                           ('mkd',): 'makedonski',
                           ('srp', None, 'Latn'): 'srpski',
                           ('srp', None, 'Cyrl'): 'cirilica',
                           ('slv',): 'slovenski'
                           }
        self.codes = set(self.from_titlovi.keys())

    def convert(self, alpha3, country=None, script=None):
        if (alpha3, country, script) in self.to_titlovi:
            return self.to_titlovi[(alpha3, country, script)]
        if (alpha3,) in self.to_titlovi:
            return self.to_titlovi[(alpha3,)]

        logger.error(ConfigurationError('Unsupported language for titlovi: %s, %s, %s' % (alpha3, country, script)))

    def reverse(self, titlovi):
        if titlovi in self.from_titlovi:
            return self.from_titlovi[titlovi]

        logger.error(ConfigurationError('Unsupported language code for titlovi: %s' % titlovi))
