# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from babelfish import LanguageReverseConverter, language_converters

class LegendasTVConverter(LanguageReverseConverter):
    def __init__(self):
        self.name_converter = language_converters['name']
        self.from_legendastv = {'Português-BR': ('por', 'BR'),
                                'Português-PT': ('por',),
                                'Espanhol': ('spa',),
								'Inglês': ('eng',),
                                'Alemão': ('deu',),
                                'Árabe': ('ara',),
                                'Búlgaro': ('bul',),
                                'Checo': ('ces',),
                                'Chinês': ('zho',),
                                'Coreano': ('kor',),
                                'Dinamarquês': ('dan',),
                                'Francês': ('fra',),
                                'Italiano': ('ita',),
                                'Japonês': ('jpn',),
                                'Norueguês': ('nor',),
                                'Polonês': ('pol',),
                                'Sueco': ('swe',)}
        self.to_legendastv = {('por', 'BR'): 'Português-BR',
                              ('por',): 'Português-PT',
                              ('spa',): 'Espanhol',
                              ('eng',): 'Inglês',
							  ('deu',): 'Alemão',
                              ('ara',): 'Árabe',
                              ('bul',): 'Búlgaro',
                              ('ces',): 'Checo',
                              ('zho',): 'Chinês',
                              ('kor',): 'Coreano',
                              ('dan',): 'Dinamarquês',
                              ('fra',): 'Francês',
                              ('ita',): 'Italiano',
                              ('jpn',): 'Japonês',
                              ('nor',): 'Norueguês',
                              ('pol',): 'Polonês',
                              ('swe',): 'Sueco'}
        self.codes = self.name_converter.codes | set(self.from_legendastv.keys())

    def convert(self, alpha3, country=None, script=None):
        if (alpha3, country, script) in self.to_legendastv:
            return self.to_legendastv[(alpha3, country, script)]
        if (alpha3, country) in self.to_legendastv:
            return self.to_legendastv[(alpha3, country)]
        if (alpha3,) in self.to_legendastv:
            return self.to_legendastv[(alpha3,)]

        return self.name_converter.convert(alpha3, country, script)

    def reverse(self, legendastv):
        if legendastv in self.from_legendastv:
            return self.from_legendastv[legendastv]

        return self.name_converter.reverse(legendastv)