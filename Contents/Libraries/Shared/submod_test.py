# coding=utf-8

import logging
import sys
import codecs

from ftfy import fix_text

from subzero.language import Language
from subliminal_patch import Subtitle
from subliminal_patch.subtitle import ftfy_defaults

logger = logging.getLogger(__name__)

from subzero.modification import SubMod

fn = sys.argv[1]
debug = "--debug" in sys.argv

if debug:
    logging.basicConfig(level=logging.DEBUG)

#sub = Subtitle(Language.fromietf("eng:forced"), mods=["common", "remove_HI", "OCR_fixes", "fix_uppercase", "shift_offset(ms=-500)", "shift_offset(ms=500)", "shift_offset(s=2,ms=800)"])
sub = Subtitle(Language.fromietf("eng"), mods=["common", "remove_HI", "OCR_fixes", "fix_uppercase", "shift_offset(ms=0,s=1)", "fix_incremental", "fix_short"])
sub.content = open(fn).read()
sub.normalize()
sub.is_valid()
content = sub.get_modified_content(debug=True)

#submod = SubMod(debug=debug)
#submod.load(fn, language=Language.fromietf("pol"), encoding="utf-8")
#submod.modify("OCR_fixes", "common", "remove_tags", "OCR_fixes", "OCR_fixes")
#submod.modify("shift_offset(s=20)", "OCR_fixes")
#submod.modify("remove_HI", "OCR_fixes", "common", "OCR_fixes", "shift_offset(s=20)", "OCR_fixes", "color(name=white)", "shift_offset(s=-5, ms=-350)")

#srt = Subtitle.pysubs2_to_unicode(submod.f)
#content = fix_text(Subtitle.pysubs2_to_unicode(submod.f, format=format), **ftfy_defaults)\
#                .encode(encoding="utf-8")
#print submod.f.to_string("srt", encoding="utf-8")
#print repr(content)
f = codecs.open("testout.srt", "w+")
f.write(content)
f.close()
#print submod.f.to_string("srt")
#submod.modify("OCR_fixes")
#submod.modify("change_FPS(from=24,to=25)")
#submod.modify("common")

#print Subtitle.pysubs2_to_unicode(submod.f)
