# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from babelfish import LanguageReverseConverter, language_converters


class SabbzConverter(LanguageReverseConverter):
    def __init__(self):
        self.alpha2_converter = language_converters['alpha2']
        self.from_sabbz = {'br': ('por', 'BR'), 'ua': ('ukr',), 'gr': ('ell',), 'cn': ('zho',), 'jp': ('jpn',),
                                 'cz': ('ces',)}
        self.to_sabbz = {v: k for k, v in self.from_sabbz.items()}
        self.codes = self.alpha2_converter.codes | set(self.from_sabbz.keys())

    def convert(self, alpha3, country=None, script=None):
        if (alpha3, country) in self.to_sabbz:
            return self.to_sabbz[(alpha3, country)]
        if (alpha3,) in self.to_sabbz:
            return self.to_sabbz[(alpha3,)]

        return self.alpha2_converter.convert(alpha3, country, script)

    def reverse(self, sabbz):
        if sabbz in self.from_sabbz:
            return self.from_sabbz[sabbz]

        return self.alpha2_converter.reverse(sabbz)
