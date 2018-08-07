# coding=utf-8

import re, os
import helpers

from config import config, SUBTITLE_EXTS, TEXT_SUBTITLE_EXTS
from bs4 import UnicodeDammit


class SubtitleHelper(object):
    def __init__(self, filename):
        self.filename = filename


def subtitle_helpers(filename):
    filename = helpers.unicodize(filename)
    helper_classes = [DefaultSubtitleHelper]

    if helpers.cast_bool(Prefs["subtitles.scan.exotic_ext"]):
        helper_classes.insert(0, VobSubSubtitleHelper)

    for cls in helper_classes:
        if cls.is_helper_for(filename):
            return cls(filename)
    return None


#####################################################################################################################

class VobSubSubtitleHelper(SubtitleHelper):
    @classmethod
    def is_helper_for(cls, filename):
        (file, file_extension) = os.path.splitext(filename)

        # We only support idx (and maybe sub)
        if not file_extension.lower() in ['.idx', '.sub']:
            return False

        # If we've been given a sub, we only support it if there exists a matching idx file
        return os.path.exists(file + '.idx')

    def process_subtitles(self, part):

        lang_sub_map = {}

        # We don't directly process the sub file, only the idx. Therefore if we are passed on of these files, we simply
        # ignore it.
        (file, ext) = os.path.splitext(self.filename)
        if ext == '.sub':
            return lang_sub_map

        # If we have an idx file, we need to confirm there is an identically names sub file before we can proceed.
        sub_filename = file + ".sub"
        if not os.path.exists(sub_filename):
            return lang_sub_map

        Log('Attempting to parse VobSub file: ' + self.filename)
        idx = Core.storage.load(os.path.join(self.filename))
        if idx.count('VobSub index file') == 0:
            Log('The idx file does not appear to be a VobSub, skipping...')
            return lang_sub_map

        languages = {}
        language_index = 0
        basename = os.path.basename(self.filename)
        for language in re.findall('\nid: ([A-Za-z]{2})', idx):

            if not languages.has_key(language):
                languages[language] = []

            Log('Found .idx subtitle file: ' + self.filename + ' language: ' + language + ' stream index: ' + str(language_index))
            languages[language].append(Proxy.LocalFile(self.filename, index=str(language_index), format="vobsub"))
            language_index += 1

            if not lang_sub_map.has_key(language):
                lang_sub_map[language] = []
            lang_sub_map[language].append(basename)

        for language, subs in languages.items():
            part.subtitles[language][basename] = subs

        return lang_sub_map


#####################################################################################################################


IETF_MATCH = ".+\.([^-.]+)(?:-[A-Za-z]+)?$"
ENDSWITH_LANGUAGECODE_RE = re.compile("\.([^-.]{2,3})(?:-[A-Za-z]{2,})?$")


def match_ietf_language(s):
    language_match = re.match(".+\.([^\.]+)$" if not helpers.cast_bool(Prefs["subtitles.language.ietf_display"])
                              else IETF_MATCH, s)
    if language_match and len(language_match.groups()) == 1:
        language = language_match.groups()[0]
        return language
    return s


class DefaultSubtitleHelper(SubtitleHelper):
    @classmethod
    def is_helper_for(cls, filename):
        (file, file_extension) = os.path.splitext(filename)
        return file_extension.lower()[1:] in SUBTITLE_EXTS

    def process_subtitles(self, part):

        lang_sub_map = {}

        if not os.path.exists(self.filename):
            return lang_sub_map

        basename = os.path.basename(self.filename)
        (file, ext) = os.path.splitext(self.filename)

        # Remove the initial '.' from the extension
        ext = ext[1:]

        forced = ''
        default = ''
        split_tag = file.rsplit('.', 1)
        if len(split_tag) > 1 and split_tag[1].lower() in ['forced', 'normal', 'default', 'embedded', 'embedded-forced',
                                                           'custom']:
            file = split_tag[0]
            sub_tag = split_tag[1].lower()
            # don't do anything with 'normal', we don't need it
            if 'forced' in sub_tag:
                forced = '1'
            elif 'default' == sub_tag:
                default = '1'

        # Attempt to extract the language from the filename (e.g. Avatar (2009).eng)
        # IETF support thanks to
        # https://github.com/hpsbranco/LocalMedia.bundle/commit/4fad9aefedece78a1fa96401304351347f644369
        lang_part = match_ietf_language(file)
        if lang_part != file:
            language = Locale.Language.Match(lang_part)
        elif config.only_one:
            language = Locale.Language.Match(list(config.lang_list)[0].alpha2)
        else:
            language = Locale.Language.Match("xx")

        # skip non-SRT if wanted
        if not config.exotic_ext and ext not in TEXT_SUBTITLE_EXTS:
            return lang_sub_map

        codec = None
        format = None
        if ext in ['txt', 'sub']:
            try:

                file_contents = Core.storage.load(self.filename)
                lines = [line.strip() for line in file_contents.splitlines(True)]
                if re.match('^\{[0-9]+\}\{[0-9]*\}', lines[1]):
                    format = 'microdvd'
                elif re.match('^[0-9]{1,2}:[0-9]{2}:[0-9]{2}[:=,]', lines[1]):
                    format = 'txt'
                elif '[SUBTITLE]' in lines[1]:
                    format = 'subviewer'
                else:
                    Log("The subtitle file does not have a known format, skipping... : " + self.filename)
                    return lang_sub_map
            except:
                Log("An error occurred while attempting to parse the subtitle file, skipping... : " + self.filename)
                return lang_sub_map

        # fixme: re-add vtt once Plex Inc. fixes this line in LocalMedia.bundle
        if codec is None and ext in ['ass', 'ssa', 'smi', 'srt', 'psb']:
            codec = ext.replace('ass', 'ssa')

        if format is None:
            format = codec

        Log('Found subtitle file: ' + self.filename + ' language: ' + language + ' codec: ' + str(
            codec) + ' format: ' + str(format) + ' default: ' + default + ' forced: ' + forced)
        part.subtitles[language][basename] = Proxy.LocalFile(self.filename, codec=codec, format=format, default=default,
                                                             forced=forced)

        lang_sub_map[language] = [basename]
        return lang_sub_map


def get_subtitles_from_metadata(part):
    subs = {}
    if hasattr(part, "subtitles") and part.subtitles:
        for language in part.subtitles:
            subs[language] = []
            for key, proxy in getattr(part.subtitles[language], "_proxies").iteritems():
                if not proxy or not len(proxy) >= 5:
                    Log.Debug("Can't parse metadata: %s" % repr(proxy))
                    continue

                p_type = proxy[0]

                if p_type == "Media":
                    # metadata subtitle
                    Log.Debug(u"Found metadata subtitle: %s, %s" % (language, repr(proxy)))
                    subs[language] = [key]
    return subs


def force_utf8(content):
    a = UnicodeDammit(content)

    if a.original_encoding:
        Log.Debug("detected encoding: %s (None: most likely already successfully decoded)" % a.original_encoding)
    else:
        Log.Debug("detected encoding: unicode (already decoded)")

    # easy way out - already utf-8
    if a.original_encoding and a.original_encoding == "utf-8":
        return content

    return (a.unicode_markup if a.unicode_markup else content.decode('ascii', 'replace')).encode("utf-8")
