# coding=utf-8

from subzero.lib.dict import DictProxy
from config import config


class ExcludeDict(DictProxy):
    store = "ignore"

    # single item keys returned by helpers.items.getItems mapped to their parents
    translate_keys = {
        "section": "sections",
        "show": "series",
        "movie": "videos",
        "episode": "videos",
        "season": "seasons",
    }

    # getItems types mapped to their verbose names
    keys_verbose = {
        "sections": "Section",
        "series": "Series",
        "videos": "Item",
        "seasons": "Season",
    }

    key_order = ("sections", "series", "videos", "seasons")

    def __len__(self):
        try:
            return sum(len(self.Dict[self.store][key]) for key in self.key_order)
        except KeyError:
            # old version
            self.Dict[self.store] = self.setup_defaults()
        return 0

    def translate_key(self, name):
        return self.translate_keys.get(name)

    def verbose(self, name):
        return self.keys_verbose.get(self.translate_key(name) or name)

    def get_title_key(self, kind, key):
        return "%s_%s" % (kind, key)

    def add_title(self, kind, key, title):
        self["titles"][self.get_title_key(kind, key)] = title

    def remove_title(self, kind, key):
        title_key = self.get_title_key(kind, key)
        if title_key in self.titles:
            del self.titles[title_key]

    def get_title(self, kind, key):
        title_key = self.get_title_key(kind, key)
        if title_key in self.titles:
            return self.titles[title_key]

    def save(self):
        Dict.Save()

    def setup_defaults(self):
        return {"sections": [], "series": [], "videos": [], "titles": {}, "seasons": []}


class IncludeDict(ExcludeDict):
    store = "include"


exclude_list = ExcludeDict(Dict)
include_list = IncludeDict(Dict)


def get_decision_list():
    return include_list if config.include else exclude_list
