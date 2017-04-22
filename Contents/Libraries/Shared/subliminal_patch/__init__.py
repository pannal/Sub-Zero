# coding=utf-8

import subliminal
import babelfish
import logging

# patch subliminal's subtitle and provider base
from .patch_subtitle import PatchedSubtitle
from .patch_providers import PatchedProvider
subliminal.subtitle.Subtitle = PatchedSubtitle
subliminal.providers.Provider = PatchedProvider
from subliminal.providers.addic7ed import Addic7edSubtitle, Addic7edProvider
from subliminal.providers.podnapisi import PodnapisiSubtitle, PodnapisiProvider
from subliminal.providers.tvsubtitles import TVsubtitlesSubtitle, TVsubtitlesProvider
from subliminal.providers.opensubtitles import OpenSubtitlesSubtitle, OpenSubtitlesProvider

# add our patched base classes
setattr(Addic7edSubtitle, "__bases__", (PatchedSubtitle,))
setattr(PodnapisiSubtitle, "__bases__", (PatchedSubtitle,))
setattr(TVsubtitlesSubtitle, "__bases__", (PatchedSubtitle,))
setattr(OpenSubtitlesSubtitle, "__bases__", (PatchedSubtitle,))
setattr(Addic7edProvider, "__bases__", (PatchedProvider,))
setattr(PodnapisiProvider, "__bases__", (PatchedProvider,))
setattr(TVsubtitlesProvider, "__bases__", (PatchedProvider,))
setattr(OpenSubtitlesProvider, "__bases__", (PatchedProvider,))

from .patch_provider_pool import PatchedProviderPool
from .patch_video import patched_search_external_subtitles, scan_video
from .patch_providers import addic7ed, podnapisi, tvsubtitles, opensubtitles
from .patch_api import save_subtitles, list_all_subtitles, download_subtitles

# patch subliminal's ProviderPool
subliminal.api.ProviderPool = PatchedProviderPool

# patch subliminal's functions
subliminal.api.save_subtitles = save_subtitles
subliminal.api.list_all_subtitles = list_all_subtitles
subliminal.api.download_subtitles = download_subtitles

# patch subliminal's subtitle classes
def subtitleRepr(self):
    link = self.page_link

    # specialcasing addic7ed; eww
    if self.__class__.__name__ == "Addic7edSubtitle":
        link = u"http://www.addic7ed.com/%s" % self.download_link
    return '<%s %r [%s]>' % (self.__class__.__name__, link, self.language)


subliminal.subtitle.Subtitle.__repr__ = subtitleRepr

# patch subliminal's providers
subliminal.providers.addic7ed.Addic7edProvider = addic7ed.PatchedAddic7edProvider
subliminal.providers.podnapisi.PodnapisiProvider = podnapisi.PatchedPodnapisiProvider
subliminal.providers.tvsubtitles.TVsubtitlesProvider = tvsubtitles.PatchedTVsubtitlesProvider
subliminal.providers.opensubtitles.OpenSubtitlesProvider = opensubtitles.PatchedOpenSubtitlesProvider

# add language converters
babelfish.language_converters.register('addic7ed = subliminal_patch.patch_language:PatchedAddic7edConverter')
babelfish.language_converters.register('tvsubtitles = subliminal.converters.tvsubtitles:TVsubtitlesConverter')
babelfish.language_converters.register('legendastv = subliminal.converters.legendastv:LegendasTVConverter')

# patch subliminal's external subtitles search algorithm
subliminal.video.search_external_subtitles = patched_search_external_subtitles

# patch subliminal's scan_video function
subliminal.video.scan_video = scan_video

subliminal.video.Episode.scores["title"] = 0
