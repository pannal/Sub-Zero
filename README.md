# Sub-Zero for Plex
[![](https://img.shields.io/github/release/pannal/Sub-Zero.bundle.svg?style=flat&label=stable)](https://github.com/pannal/Sub-Zero.bundle/releases/latest) 
[![master](https://img.shields.io/badge/master-stable-green.svg?maxAge=2592000)]()
[![Maintenance](https://img.shields.io/maintenance/yes/2023.svg)]()
[![Slack Status](https://szslack.fragstore.net/badge.svg)](https://szslack.fragstore.net)
[![FOSSA Status](https://app.fossa.io/api/projects/git%2Bgithub.com%2Fpannal%2FSub-Zero.bundle.svg?type=shield)](https://app.fossa.io/projects/git%2Bgithub.com%2Fpannal%2FSub-Zero.bundle?ref=badge_shield)

<img src="https://raw.githubusercontent.com/pannal/Sub-Zero.bundle/master/Contents/Resources/subzero.gif" align="left" height="100"> <font size="5"><b>Subtitles done right!</b></font><br />

Check out **[the Sub-Zero Wiki](https://github.com/pannal/Sub-Zero.bundle/wiki)** by [@ukdtom](https://github.com/ukdtom) and [@mmgoodnow](https://github.com/mmgoodnow) <br />
<br style="clear:left;"/>

<br />

## Legacy maintenance mode
This addon will not be developed any further. It still works and arguably is still the best for managing subtitles when using Plex. As long as Plex Inc. supports agents, Sub-Zero will be maintained to work with the latest PMS version.

---

**[Kitana is now required to have a UI](https://github.com/pannal/Kitana)**

---

**[The future of Sub-Zero](https://www.reddit.com/r/PleX/comments/9n9qjl/subzero_the_future/)**

---

## Helping development

If you like this, buy me a beer: <br>[![Donate](https://www.paypalobjects.com/en_US/i/btn/btn_donate_LG.gif)](https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=G9VKR2B8PMNKG) <br>or become a Patreon starting at **1 $ / month** <br><a href="https://www.patreon.com/subzero_plex" target="_blank"><img src="https://images.squarespace-cdn.com/content/v1/56c7831bf8baf3ae17ce9259/1561826418792-IJOMFASTOR6CW80N5W0Z/ke17ZwdGBToddI8pDm48kEycOuEejcFJqqLot0yQ4VVZw-zPPgdn4jUwVcJE1ZvWEtT5uBSRWt4vQZAgTJucoTqqXjS3CfNDSuuf31e0tVFrfGYmOrPFZFUXr1UxW4wA0PgPOjs31URy2JeWL9DdYhur-lC0WofN0YB1wFg-ZW0/footer-patreon.png?format=500w" height="54" /></a>

If you register with an anti-captcha service and you decide to use [Anti-Captcha.com](http://getcaptchasolution.com/kkvviom7nh), you can use [this affiliate link](http://getcaptchasolution.com/kkvviom7nh) to help development.

## Introduction
#### What's Sub-Zero?
Sub-Zero is a metadata agent and interface-plugin at the same time, for the popular Plex Media Server environment.

#### Why not use the builtin OpenSubtitles agent?
Because it doesn't deliver. Especially for very new media items it may pick up none or bad subtitles for your media. Also it doesn't know when "better" subtitles get released for your media file.

*Mostly all of the key-features listed below don't apply to the default OpenSubtitles subtitle agent in Plex.*

## Key-Features
This is just a tiny peek at the full feature-set of Sub-Zero.

#### Searching/Matching
It searches up to 10 individual subtitle provider sites and APIs, selects the best matching subtitle and downloads it for you.

The matching is done by looking at the filename of your media files, as well as media information inside the container.
Every subtitle gets a score assigned, based on the matching algorithm. The one with the highest score gets picked automatically. The more information your media filenames have, the better. `Moviename.mkv` has a higher chance of getting bad subtitles than `Moviename.2015.720p.BluRay-RLSGRP`. If you like renaming your media files, you want to have a look at [SZ refiners](https://github.com/pannal/Sub-Zero.bundle/wiki/Refiners).

#### Storage-Options
*You* can decide where Sub-Zero stores its downloaded subtitles. By default it saves the subtitles externally, as "sidecars", besides the actual media file.
Additionally you can specify a fixed location for *all* your subtitles, or pre-defined or custom sub-folders.

If you don't want SRT files lying around in your library, you also have the option to store subtitles inside the internal metadata storage of the Plex Media Server.

#### Automation
Sub-Zero comes with its own background task scheduler. It periodically searches for missing subtitles and better subtitles for your media files.

#### Personalization
Via the preferences you can configure almost every parameter Sub-Zero uses when handling your subtitles.

From an infinite number of different languages to search for, to hearing impaired settings, foreign/forced-only captions, embedded subtitle handling and many more.

#### Interface
The automatic matching Sub-Zero does has been improved massively over the last years and reaches an extremely high accuracy for recently-released items, in the first 6 hours. It still might be, that you want some manual managability over your library and its subtitles. This is where the interface comes into play.

It allows you to trigger background tasks, browse your library based on several different starting points, adds a recently-viewed menu for instant access to your recently played media and allows you to list and select available subtitles for any item in your library.

#### Modification and Fixing
With Sub-Zero 2.0 automatic and manual subtitle modifications have been included.
They currently consist of six individual mods:
- **Offset**: Your subtitle is out of sync? Manually adjust the timing of your subtitles
- **FPS**: Your subtitle is getting slower over time, or faster over time? Maybe the framerate is wrong. The FPS mod can fix that.
- **Hearing Impaired**: Removes HI-tags from subtitles (such as `(SIRENS WAIL)`, `DOCTOR: Rose!`)
- **Color**: Adds color to your subtitles (for playback devices/software that don't ship their own color modes; only works for players that support color tags)
- **Common**: Fixes common issues in subtitles, such as punctuation (`-- I don't know!` -> `... I don't know!`; `over 9 000!` -> `over 9000!`)
- **OCR**: Fixes problems in subtitles introduced by OCR (custom implementation of [SubtitleEdit](https://github.com/SubtitleEdit/subtitleedit)'s dictionaries) (`hands agaInst the waII!` -> `hands against the wall!`)
- **Remove Tags**: Removes any font style tags from the subtitles (bold, italic, underline, colors, ...)
- **Reverse RTL**: Reverses the punctuation in right-to-left subtitles for problematic playback devices
- **Fix Uppercase**: Tries to make subtitles that are completely uppercase readable

Hearing Impaired, Common, OCR, Fix Uppercase, Reverse RTL and Color can be applied automatically on every subtitle downloaded. All mods are manually managable via the interface.

Mods are applied on-the-fly, the original content of the subtitle stays available, so mods are completely reversible.

In addition to that Sub-Zero also fixes problems introduced by the subtitle creators themselves - badly changed encodings for example.
Ever had broken music icons in a subtitle? Nordic characters like `Å` which turned into `Ã¥`? Not anymore.

## Installation
[Please go to the wiki](https://github.com/pannal/Sub-Zero.bundle/wiki/Installation).

## Big thanks to the beta/i18n testing team (in no particular order)!
the.vbm, mmgoodnow, Vertig0ne, thliu78, tattoomees, ostman, count_confucius, eherberg, tywilliams_88, Swanny, Jippo, Joost1991 / joost, Marik, Jon, AmbyDK, Clay, Abenlog, michael, smikwily, shoghicp, Zuikkis, Isilorn, Jacob K, Ninjouz, chopeta, fvb, Uthman, Claus Møller, Semi Doludizgin, Rafael, sugarman402, Morpheus1333, Yamil.llanos, Notorius28 

## Changelog

2.6.5.3277
- core: fix enabled library/agents detection (Plex removed certain features)
  fix Plex agent integration; Plex Inc removed certain attributes; SZ is now limited to thetvdb, thetvdbdvdorder, hama, themoviedb, imdb)



2.6.5.3268
subscene, addic7ed
- either of those providers might impose a reCAPTCHA verification. In order to use those providers, please create an account at an AntiCaptcha service ([anti-captcha.com](http://getcaptchasolution.com/kkvviom7nh) or [deathbycaptcha.com](http://deathbycaptcha.com)), add funds, then supply your credentials/apikey in the configuration

Changelog
- clarify README
- core: fix custom folder handling; #761
- core: providers: screwzira: move to ktuvit and wizdom
- core: add option to not download subtitles for certain audio languages existing; and/or no audio stream; fix #756
- core: delay item refreshes after refresh call (default: 5 seconds; exposed in advanced settings)
- menu: allow extraction of embedded subtitles for whole tv shows

[older changes](CHANGELOG.md)


Subtitles provided by [OpenSubtitles.org](http://www.opensubtitles.org/), [Podnapisi.NET](https://www.podnapisi.net/), [TVSubtitles.net](http://www.tvsubtitles.net/), [Addic7ed.com](http://www.addic7ed.com/), [Legendas TV](http://legendas.tv/), [Napi Projekt](http://www.napiprojekt.pl/), [Shooter](http://shooter.cn/), [Titlovi](http://titlovi.com), [aRGENTeaM](http://argenteam.net), [SubScene](https://subscene.com/), [Hosszupuska](http://hosszupuskasub.com/), [Napisy24](https://napisy24.pl/)

[3rd party licenses](https://github.com/pannal/Sub-Zero.bundle/tree/master/Licenses)


## License
[![FOSSA Status](https://app.fossa.io/api/projects/git%2Bgithub.com%2Fpannal%2FSub-Zero.bundle.svg?type=large)](https://app.fossa.io/projects/git%2Bgithub.com%2Fpannal%2FSub-Zero.bundle?ref=badge_large)
