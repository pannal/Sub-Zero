# coding=utf-8

import traceback

import pysubs2
import logging
import time

from mods import EMPTY_TAG_PROCESSOR, EmptyEntryError
from registry import registry

logger = logging.getLogger(__name__)


class SubtitleModifications(object):
    debug = False
    language = None
    initialized_mods = {}
    f = None

    font_style_tag_start = u"{\\"

    def __init__(self, debug=False):
        self.debug = debug
        self.initialized_mods = {}

    def load(self, fn=None, content=None, language=None, encoding="utf-8"):
        """
        
        :param encoding: used for decoding the content when fn is given, not used in case content is given
        :param language: babelfish.Language language of the subtitle
        :param fn:  filename
        :param content: unicode 
        :return: 
        """
        self.language = language
        self.initialized_mods = {}
        try:
            if fn:
                self.f = pysubs2.load(fn, encoding=encoding)
            elif content:
                self.f = pysubs2.SSAFile.from_string(content)
        except (IOError,
                UnicodeDecodeError,
                pysubs2.exceptions.UnknownFPSError,
                pysubs2.exceptions.UnknownFormatIdentifierError,
                pysubs2.exceptions.FormatAutodetectionError):
            if fn:
                logger.exception("Couldn't load subtitle: %s: %s", fn, traceback.format_exc())
            elif content:
                logger.exception("Couldn't load subtitle: %s", traceback.format_exc())

        return bool(self.f)

    @classmethod
    def parse_identifier(cls, identifier):
        # simple identifier
        if identifier in registry.mods:
            return identifier, {}

        # identifier with params; identifier(param=value)
        split_args = identifier[identifier.find("(")+1:-1].split(",")
        args = dict((key, value) for key, value in [sub.split("=") for sub in split_args])
        return identifier[:identifier.find("(")], args

    @classmethod
    def get_mod_class(cls, identifier):
        identifier, args = cls.parse_identifier(identifier)
        return registry.mods[identifier]

    @classmethod
    def get_mod_signature(cls, identifier, **kwargs):
        return cls.get_mod_class(identifier).get_signature(**kwargs)

    def prepare_mods(self, *mods):
        parsed_mods = [SubtitleModifications.parse_identifier(mod) for mod in mods]
        final_mods = {}
        line_mods = []
        non_line_mods = []

        for identifier, args in parsed_mods:
            if identifier not in registry.mods:
                logger.error("Mod %s not loaded", identifier)
                continue

            mod_cls = registry.mods[identifier]
            # exclusive mod, kill old, use newest
            if identifier in final_mods and mod_cls.exclusive:
                final_mods.pop(identifier)

            # language-specific mod, check validity
            if mod_cls.languages and self.language not in mod_cls.languages:
                if self.debug:
                    logger.debug("Skipping %s, because %r is not a valid language for this mod",
                                 identifier, self.language)
                continue

            # merge args of duplicate mods if possible
            elif identifier in final_mods and mod_cls.args_mergeable:
                final_mods[identifier] = mod_cls.merge_args(final_mods[identifier], args)
                continue
            final_mods[identifier] = args

        # separate all mods into line and non-line mods
        for identifier, args in final_mods.iteritems():
            mod_cls = registry.mods[identifier]
            if mod_cls.modifies_whole_file:
                non_line_mods.append((identifier, args))
            else:
                line_mods.append((mod_cls.order, identifier, args))

            # initialize the mods
            if identifier not in self.initialized_mods:
                self.initialized_mods[identifier] = mod_cls(self)

        return line_mods, non_line_mods

    def modify(self, *mods):
        new_entries = []
        start = time.time()
        line_mods, non_line_mods = self.prepare_mods(*mods)

        # apply non-last file mods
        if non_line_mods:
            non_line_mods_start = time.time()
            self.apply_non_line_mods(non_line_mods)

            if self.debug:
                logger.debug("Non-Line mods took %ss", time.time() - non_line_mods_start)

        # sort line mods
        line_mods.sort(key=lambda x: (x is None, x))

        # apply line mods
        if line_mods:
            line_mods_start = time.time()
            self.apply_line_mods(new_entries, line_mods)

            if self.debug:
                logger.debug("Line mods took %ss", time.time() - line_mods_start)

            if new_entries:
                self.f.events = new_entries

        # apply last file mods
        if non_line_mods:
            non_line_mods_start = time.time()
            self.apply_non_line_mods(non_line_mods, only_last=True)

            if self.debug:
                logger.debug("Final Non-Line mods took %ss", time.time() - non_line_mods_start)

        if self.debug:
            logger.debug("Subtitle Modification took %ss", time.time() - start)

    def apply_non_line_mods(self, mods, only_last=False):
        for identifier, args in mods:
            mod = self.initialized_mods[identifier]
            if (not only_last and not mod.apply_last) or (only_last and mod.apply_last):
                if self.debug:
                    logger.debug("Applying %s", identifier)
                mod.modify(None, debug=self.debug, parent=self, **args)

    def apply_line_mods(self, new_entries, mods):
        for index, entry in enumerate(self.f, 1):
            applied_mods = []
            lines = []

            line_count = 0
            start_tags = []
            end_tags = []

            t = entry.text.strip()
            if not t:
                if self.debug:
                    logger.debug(u"Skipping empty line: %s", index)
                continue

            skip_entry = False
            for line in t.split(ur"\N"):
                # don't bother the mods with surrounding tags
                old_line = line
                line = line.strip()
                skip_line = False
                line_count += 1

                if not line:
                    continue

                # clean {\X0} tags before processing
                # fixme: handle nested tags?
                start_tag = u""
                end_tag = u""
                if line.startswith(self.font_style_tag_start):
                    start_tag = line[:5]
                    line = line[5:]
                if line[-5:-3] == self.font_style_tag_start:
                    end_tag = line[-5:]
                    line = line[:-5]

                for order, identifier, args in mods:
                    mod = self.initialized_mods[identifier]

                    try:
                        line = mod.modify(line.strip(), entry=entry.text, debug=self.debug, parent=self, index=index,
                                          **args)
                    except EmptyEntryError:
                        if self.debug:
                            logger.debug(u"%d: %s: %r -> ''", index, identifier, entry.text)
                        skip_entry = True
                        break

                    if not line:
                        if self.debug:
                            logger.debug(u"%d: %s: %r -> ''", index, identifier, old_line)
                        skip_line = True
                        break

                    applied_mods.append(identifier)

                if skip_entry:
                    lines = []
                    break

                if skip_line:
                    continue

                if start_tag:
                    start_tags.append(start_tag)

                if end_tag:
                    end_tags.append(end_tag)

                # append new line and clean possibly newly added empty tags
                cleaned_line = EMPTY_TAG_PROCESSOR.process(start_tag + line + end_tag, debug=self.debug).strip()
                if cleaned_line:
                    # we may have a single closing tag, if so, try appending it to the previous line
                    if len(cleaned_line) == 5 and cleaned_line.startswith("{\\") and cleaned_line.endswith("0}"):
                        if lines:
                            prev_line = lines.pop()
                            lines.append(prev_line + cleaned_line)
                            continue

                    lines.append(cleaned_line)
                else:
                    if self.debug:
                        logger.debug(u"%d: Ditching now empty line (%r)", index, line)

            if not lines:
                # don't bother logging when the entry only had one line
                if self.debug and line_count > 1:
                    logger.debug(u"%d: %r -> ''", index, entry.text)
                continue

            new_text = ur"\N".join(lines)

            # cheap man's approach to avoid open tags
            add_start_tags = []
            add_end_tags = []
            if len(start_tags) != len(end_tags):
                for tag in start_tags:
                    end_tag = tag.replace("1", "0")
                    if end_tag not in end_tags and new_text.count(tag) > new_text.count(end_tag):
                        add_end_tags.append(end_tag)
                for tag in end_tags:
                    start_tag = tag.replace("0", "1")
                    if start_tag not in start_tags and new_text.count(tag) > new_text.count(start_tag):
                        add_start_tags.append(start_tag)

                if add_end_tags or add_start_tags:
                    entry.text = u"".join(add_start_tags) + new_text + u"".join(add_end_tags)
                    if self.debug:
                        logger.debug(u"Fixing tags: %s (%r -> %r)", str(add_start_tags+add_end_tags), new_text,
                                     entry.text)
                else:
                    entry.text = new_text
            else:
                entry.text = new_text

            new_entries.append(entry)

SubMod = SubtitleModifications




