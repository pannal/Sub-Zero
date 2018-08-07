# addic7ed
python -c "import logging; logging.basicConfig(level=logging.DEBUG); logging.getLogger('rebulk').setLevel(logging.WARNING); import os; os.environ['U1pfT01EQl9LRVk'] = '789CF30DAC2C8B0AF433F5C9AD34290A712DF30D7135F12D0FB3E502006FDE081E'; import subliminal_patch, subliminal; from subliminal_patch.core import SZProviderPool; from babelfish import Language; subliminal.region.configure('dogpile.cache.memory'); from subzero.video import parse_video; video = parse_video('FILE_NAME', hints={'type': 'episode'}, dry_run=True); provider = SZProviderPool(providers=['addic7ed'], provider_configs={'addic7ed': {'use_random_agents': True}} )['addic7ed']; subtitle = provider.list_subtitles(video, languages=[Language('fra')]); provider.download_subtitle(subtitle[0]);"

# addic7ed download_best
python -c "import logging; logging.basicConfig(level=logging.DEBUG); logging.getLogger('rebulk').setLevel(logging.WARNING); import os; os.environ['U1pfT01EQl9LRVk'] = '789CF30DAC2C8B0AF433F5C9AD34290A712DF30D7135F12D0FB3E502006FDE081E'; import subliminal_patch, subliminal; from subliminal_patch.core import SZProviderPool, download_best_subtitles; from subliminal_patch.score import compute_score; from babelfish import Language; subliminal.region.configure('dogpile.cache.memory'); from subzero.video import parse_video; video = parse_video('FILE_NAME', hints={'type': 'episode'}, dry_run=True); download_best_subtitles([video], pool_class=SZProviderPool, compute_score=compute_score, providers=['addic7ed'], provider_configs={'addic7ed': {'use_random_agents': True}}, languages={Language('fra')} )"

# opensubtitles:list
python -c "import logging; logging.basicConfig(level=logging.DEBUG); logging.getLogger('rebulk').setLevel(logging.WARNING); import subliminal_patch, subliminal; subliminal.region.configure('dogpile.cache.memory'); from subliminal_patch.core import SZProviderPool; from babelfish import Language; from subzero.video import parse_video; SZProviderPool(providers=['opensubtitles'], )['opensubtitles'].list_subtitles(parse_video('FULL_PATH', {}, {'type': 'episode'}), languages=[Language('eng')])"

# opensubtitles:download
python -c "import logging; logging.basicConfig(level=logging.DEBUG); logging.getLogger('rebulk').setLevel(logging.WARNING); import subliminal_patch, subliminal; subliminal.region.configure('dogpile.cache.memory'); from subliminal_patch.core import SZProviderPool, download_best_subtitles; from subliminal_patch.score import compute_score; from babelfish import Language; from subzero.video import parse_video; video = parse_video('FILE_NAME', hints={'type': 'movie'}, dry_run=True); download_best_subtitles([video], pool_class=SZProviderPool, compute_score=compute_score, providers=['opensubtitles'], languages={Language('srp')} )"

# podnapisi
python -c "import logging; logging.basicConfig(level=logging.DEBUG); import subliminal_patch, subliminal; subliminal.region.configure('dogpile.cache.memory'); from subliminal_patch.core import SZProviderPool; from babelfish import Language; SZProviderPool(providers=['podnapisi'], )['podnapisi'].query([Language('eng')], 'Game of Thrones', season=2, episode=1)"

# tvsubtitles
python -c "import logging; logging.basicConfig(level=logging.DEBUG); import subliminal_patch, subliminal; subliminal.region.configure('dogpile.cache.memory'); from subliminal_patch.core import SZProviderPool; from babelfish import Language; SZProviderPool(providers=['tvsubtitles'], )['tvsubtitles'].query('Game of Thrones', 2, 1)"

# napiprojekt:list
python -c "import logging; logging.basicConfig(level=logging.DEBUG); logging.getLogger('rebulk').setLevel(logging.WARNING); import subliminal_patch, subliminal; subliminal.region.configure('dogpile.cache.memory'); from subliminal_patch.core import SZProviderPool; from babelfish import Language; from subliminal.core import scan_video; print SZProviderPool(providers=['napiprojekt'], )['napiprojekt'].list_subtitles(scan_video('FULL_PATH'), languages=[Language('pol')])"

# napiprojekt:download
python -c "import logging; logging.basicConfig(level=logging.DEBUG); logging.getLogger('rebulk').setLevel(logging.WARNING); import subliminal_patch, subliminal; subliminal.region.configure('dogpile.cache.memory'); from subliminal_patch.core import SZProviderPool; from subliminal_patch.score import compute_score; from subliminal import download_best_subtitles; from babelfish import Language; from subliminal.core import scan_video; subs = download_best_subtitles([scan_video('FULL_PATH')], languages={Language('eng')}, providers=['napiprojekt'], pool_class=SZProviderPool, compute_score=compute_score); print subs.values()[0][0].is_valid()"

# argenteam:list
python -c "import logging; logging.basicConfig(level=logging.DEBUG); logging.getLogger('rebulk').setLevel(logging.WARNING); import subliminal_patch, subliminal; subliminal.region.configure('dogpile.cache.memory'); from subliminal_patch.core import SZProviderPool; from babelfish import Language; from subzero.video import parse_video; video = parse_video('FILE_NAME', hints={'type': 'movie'}, dry_run=True); print SZProviderPool(providers=['argenteam'], )['argenteam'].list_subtitles(video, languages=[Language('spa')])"

# argenteam:download
python -c "import logging; logging.basicConfig(level=logging.DEBUG); logging.getLogger('rebulk').setLevel(logging.WARNING); import subliminal_patch, subliminal; subliminal.region.configure('dogpile.cache.memory'); from subliminal_patch.core import SZProviderPool, download_best_subtitles; from subliminal_patch.score import compute_score; from babelfish import Language; from subzero.video import parse_video; video = parse_video('FILE_NAME', hints={'type': 'movie'}, dry_run=True); download_best_subtitles([video], pool_class=SZProviderPool, compute_score=compute_score, providers=['argenteam'], languages={Language('spa')} )"

# hosszupuska:list
python -c "import logging; logging.basicConfig(level=logging.DEBUG); logging.getLogger('rebulk').setLevel(logging.WARNING); import subliminal_patch, subliminal; subliminal.region.configure('dogpile.cache.memory'); from subliminal_patch.core import SZProviderPool; from babelfish import Language; from subzero.video import parse_video; video = parse_video('FILE_NAME', hints={'type': 'episode'}, dry_run=True); print SZProviderPool(providers=['hosszupuska'], )['hosszupuska'].list_subtitles(video, languages=[Language('hun')])"

# hosszupuska:download
python -c "import logging; logging.basicConfig(level=logging.DEBUG); logging.getLogger('rebulk').setLevel(logging.WARNING); import subliminal_patch, subliminal; subliminal.region.configure('dogpile.cache.memory'); from subliminal_patch.core import SZProviderPool, download_best_subtitles; from subliminal_patch.score import compute_score; from babelfish import Language; from subzero.video import parse_video; video = parse_video('FILE_INFO', hints={'type': 'episode'}, dry_run=True); download_best_subtitles([video], pool_class=SZProviderPool, compute_score=compute_score, providers=['hosszupuska'], languages={Language('hun')} )"

# shooter:list
python -c "import logging; logging.basicConfig(level=logging.DEBUG); logging.getLogger('rebulk').setLevel(logging.WARNING); import subliminal_patch, subliminal; subliminal.region.configure('dogpile.cache.memory'); from subliminal_patch.core import SZProviderPool; from babelfish import Language; from subliminal.core import scan_video; print SZProviderPool(providers=['shooter'], )['shooter'].list_subtitles(scan_video('FULL_PATH'), languages=[Language('zho')])"

# subscenter:list
python -c "import logging; logging.basicConfig(level=logging.DEBUG); logging.getLogger('rebulk').setLevel(logging.WARNING); import subliminal_patch, subliminal; subliminal.region.configure('dogpile.cache.memory'); from subliminal_patch.core import SZProviderPool; from babelfish import Language; from subliminal.core import scan_video; print SZProviderPool(providers=['subscenter'], )['subscenter'].list_subtitles(scan_video('FULL_PATH'), languages=[Language('heb')])"


# refining
python -c "import logging; logging.basicConfig(level=logging.DEBUG); logging.getLogger('rebulk').setLevel(logging.WARNING); import os; os.environ['U1pfT01EQl9LRVk'] = '789CF30DAC2C8B0AF433F5C9AD34290A712DF30D7135F12D0FB3E502006FDE081E'; import subliminal_patch, subliminal; subliminal.region.configure('dogpile.cache.memory'); from subzero.video import parse_video, refine_video; video = parse_video('FILE_NAME', {'type': 'episode'}, dry_run=True); print refine_video(video)"

# full test with download
python -c "import logging; logging.basicConfig(level=logging.DEBUG); logging.getLogger('rebulk').setLevel(logging.WARNING); import os; os.environ['U1pfT01EQl9LRVk'] = '789CF30DAC2C8B0AF433F5C9AD34290A712DF30D7135F12D0FB3E502006FDE081E'; import subliminal_patch, subliminal; from subliminal_patch.core import SZProviderPool; from babelfish import Language; subliminal.region.configure('dogpile.cache.memory'); from subzero.video import parse_video; video = parse_video('FILE_NAME', hints={'type': 'episode'}, dry_run=True); subtitle = SZProviderPool(providers=['titlovi'], )['titlovi'].list_subtitles(video, languages=[Language('hrv')]); SZProviderPool(providers=['titlovi'], )['titlovi'].download_subtitle(subtitle[0]);"