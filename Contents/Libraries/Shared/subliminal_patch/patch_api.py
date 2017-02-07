# coding=utf-8
import os
import logging
from bs4 import UnicodeDammit
from subliminal.api import io, defaultdict
from subliminal_patch.patch_provider_pool import PatchedProviderPool

logger = logging.getLogger(__name__)


def download_subtitles(subtitles, **kwargs):
    """Download :attr:`~subliminal.subtitle.Subtitle.content` of `subtitles`.

    All other parameters are passed onwards to the :class:`ProviderPool` constructor.

    :param subtitles: subtitles to download.
    :type subtitles: list of :class:`~subliminal.subtitle.Subtitle`

    """
    with PatchedProviderPool(**kwargs) as pool:
        for subtitle in subtitles:
            logger.info('Downloading subtitle %r', subtitle)
            pool.download_subtitle(subtitle)


def list_all_subtitles(videos, languages, **kwargs):
    """List all available subtitles.

    The `videos` must pass the `languages` check of :func:`check_video`.

    All other parameters are passed onwards to the :class:`ProviderPool` constructor.

    :param videos: videos to list subtitles for.
    :type videos: set of :class:`~subliminal.video.Video`
    :param languages: languages to search for.
    :type languages: set of :class:`~babelfish.language.Language`
    :return: found subtitles per video.
    :rtype: dict of :class:`~subliminal.video.Video` to list of :class:`~subliminal.subtitle.Subtitle`

    """
    listed_subtitles = defaultdict(list)

    # return immediatly if no video passed the checks
    if not videos:
        return listed_subtitles

    # list subtitles
    with PatchedProviderPool(**kwargs) as pool:
        for video in videos:
            logger.info('Listing subtitles for %r', video)
            subtitles = pool.list_subtitles(video, languages - video.subtitle_languages)
            listed_subtitles[video].extend(subtitles)
            logger.info('Found %d subtitle(s)', len(subtitles))

    return listed_subtitles


def get_subtitle_path(video_path, language=None, extension='.srt', forced_tag=False):
    """Get the subtitle path using the `video_path` and `language`.

    :param str video_path: path to the video.
    :param language: language of the subtitle to put in the path.
    :type language: :class:`~babelfish.language.Language`
    :param str extension: extension of the subtitle.
    :return: path of the subtitle.
    :rtype: str

    """
    subtitle_root = os.path.splitext(video_path)[0]

    if language:
        subtitle_root += '.' + str(language)

    if forced_tag:
        subtitle_root += ".forced"

    return subtitle_root + extension


def save_subtitles(video, subtitles, single=False, directory=None, encoding=None, encode_with=None, chmod=None,
                   forced_tag=False, path_decoder=None):
    """Save subtitles on filesystem.

    Subtitles are saved in the order of the list. If a subtitle with a language has already been saved, other subtitles
    with the same language are silently ignored.

    The extension used is `.lang.srt` by default or `.srt` is `single` is `True`, with `lang` being the IETF code for
    the :attr:`~subliminal.subtitle.Subtitle.language` of the subtitle.

    :param video: video of the subtitles.
    :type video: :class:`~subliminal.video.Video`
    :param subtitles: subtitles to save.
    :type subtitles: list of :class:`~subliminal.subtitle.Subtitle`
    :param bool single: save a single subtitle, default is to save one subtitle per language.
    :param str directory: path to directory where to save the subtitles, default is next to the video.
    :param str encoding: encoding in which to save the subtitles, default is to keep original encoding.
    :return: the saved subtitles
    :rtype: list of :class:`~subliminal.subtitle.Subtitle`

    patch: unicode path probems
    """
    saved_subtitles = []
    for subtitle in subtitles:
        # check content
        if subtitle.content is None:
            logger.error('Skipping subtitle %r: no content', subtitle)
            continue

        # check language
        if subtitle.language in set(s.language for s in saved_subtitles):
            logger.debug('Skipping subtitle %r: language already saved', subtitle)
            continue

        # create subtitle path
        subtitle_path = get_subtitle_path(video.name, None if single else subtitle.language, forced_tag=forced_tag)
        if directory is not None:
            subtitle_path = os.path.join(directory, os.path.split(subtitle_path)[1])

        if path_decoder:
            subtitle_path = path_decoder(subtitle_path)

        # force unicode
        subtitle_path = UnicodeDammit(subtitle_path).unicode_markup

        subtitle.storage_path = subtitle_path

        # save content as is or in the specified encoding
        logger.info('Saving %r to %r', subtitle, subtitle_path)
        has_encoder = callable(encode_with)

        if has_encoder:
            logger.info('Using encoder %s' % encode_with.__name__)

        # save normalized subtitle if encoder or no encoding is given
        if has_encoder or encoding is None:
            content = encode_with(subtitle.text) if has_encoder else subtitle.content
            with io.open(subtitle_path, 'wb') as f:
                f.write(content)

            # change chmod if requested
            if chmod:
                os.chmod(subtitle_path, chmod)

            if single:
                break
            continue

        # save subtitle if encoding given
        if encoding is not None:
            with io.open(subtitle_path, 'w', encoding=encoding) as f:
                f.write(subtitle.text)

        # change chmod if requested
        if chmod:
            os.chmod(subtitle_path, chmod)

        saved_subtitles.append(subtitle)

        # check single
        if single:
            break

    return saved_subtitles
