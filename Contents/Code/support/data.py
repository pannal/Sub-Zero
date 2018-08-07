# coding=utf-8
import traceback


def dispatch_migrate():
    try:
        migrate()
    except:
        Log.Error("Migration failed: %s" % traceback.format_exc())
        del Dict["subs"]
        Dict.Save()


def migrate():
    """
    some Dict/Data migrations here, no need for a more in-depth migration path for now
    :return:
    """

    # migrate subtitle history from Dict to Data
    if "history" in Dict and Dict["history"].get("history_items"):
        Log.Debug("Running migration for history data")
        from support.history import get_history
        history = get_history()

        for item in reversed(Dict["history"]["history_items"]):
            history.add(item.item_title, item.rating_key, item.section_title, subtitle=item.subtitle, mode=item.mode,
                        time=item.time)

        del Dict["history"]
        history.destroy()
        Dict.Save()

    # migrate subtitle storage from Dict to Data
    if "subs" in Dict:
        from support.storage import get_subtitle_storage
        from subzero.subtitle_storage import StoredSubtitle
        from support.plex_media import get_item

        subtitle_storage = get_subtitle_storage()

        for video_id, parts in Dict["subs"].iteritems():
            try:
                item = get_item(video_id)
            except:
                continue

            if not item:
                continue

            stored_subs = subtitle_storage.load_or_new(item)
            stored_subs.version = 1

            Log.Debug(u"Migrating %s" % video_id)

            stored_any = False
            for part_id, lang_dict in parts.iteritems():
                part_id = str(part_id)
                Log.Debug(u"Migrating %s, %s" % (video_id, part_id))

                for lang, subs in lang_dict.iteritems():
                    lang = str(lang)
                    if "current" in subs:
                        current_key = subs["current"]
                        provider_name, subtitle_id = current_key
                        sub = subs.get(current_key)
                        if sub and sub.get("title") and sub.get("mode"):  # ditch legacy data without sufficient info
                            stored_subs.title = sub["title"]
                            new_sub = StoredSubtitle(sub["score"], sub["storage"], sub["hash"], provider_name,
                                                     subtitle_id, date_added=sub["date_added"], mode=sub["mode"])

                            if part_id not in stored_subs.parts:
                                stored_subs.parts[part_id] = {}

                            if lang not in stored_subs.parts[part_id]:
                                stored_subs.parts[part_id][lang] = {}

                            Log.Debug(u"Migrating %s, %s, %s" % (video_id, part_id, current_key))

                            stored_subs.parts[part_id][lang][current_key] = new_sub
                            stored_subs.parts[part_id][lang]["current"] = current_key
                            stored_any = True

            if stored_any:
                subtitle_storage.save(stored_subs)

        subtitle_storage.destroy()
        del Dict["subs"]
        Dict.Save()
