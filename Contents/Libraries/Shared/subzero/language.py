# coding=utf-8
from babelfish.exceptions import LanguageError

from babelfish import Language as Language_


repl_map = {
    "dk": "da",
    "nld": "nl",
    "english": "en",
}


def language_from_stream(l):
    if not l:
        raise LanguageError()
    for method in ("fromietf", "fromalpha3t", "fromalpha3b"):
        try:
            return getattr(Language, method)(l)
        except (LanguageError, ValueError):
            pass
    raise LanguageError()


class Language(Language_):
    @classmethod
    def fromietf(cls, ietf):
        ietf_lower = ietf.lower()
        if ietf_lower in repl_map:
            ietf = repl_map[ietf_lower]

        return Language_.fromietf(ietf)

    @classmethod
    def fromalpha3b(cls, s):
        if s in repl_map:
            s = repl_map[s]
            return Language_.fromietf(s)

        return Language_.fromalpha3b(s)
