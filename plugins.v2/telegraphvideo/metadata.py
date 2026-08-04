from typing import Any, Dict, Iterable, List


EMPTY_VALUES = (None, "")


def compact(value: Any) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            normalized = compact(item)
            if normalized in EMPTY_VALUES or normalized == [] or normalized == {}:
                continue
            result[str(key)] = normalized
        return result
    if isinstance(value, (list, tuple, set)):
        result = [compact(item) for item in value]
        return [item for item in result if item not in EMPTY_VALUES and item != [] and item != {}]
    return value


def _media_type(value: Any) -> str:
    raw = value.value if hasattr(value, "value") else value
    text = str(raw or "").strip()
    return text if text in {"电影", "电视剧", "系列", "未知"} else "未知"


def _runtime_seconds(media_info: Dict[str, Any]) -> Any:
    value = media_info.get("runtime_seconds") or media_info.get("runtimeSeconds")
    if value not in EMPTY_VALUES:
        try:
            return round(float(value))
        except (TypeError, ValueError):
            return value
    value = media_info.get("runtime") or media_info.get("runtime_minutes")
    if value in EMPTY_VALUES:
        values = media_info.get("episode_run_time") or []
        value = values[0] if values else None
    if value in EMPTY_VALUES:
        return None
    try:
        return round(float(value) * 60)
    except (TypeError, ValueError):
        return None


def _profile_url(value: Any) -> Any:
    text = str(value or "").strip()
    if not text:
        return None
    if text.startswith(("http://", "https://")):
        return text
    if text.startswith("/"):
        return f"https://image.tmdb.org/t/p/original/{text.lstrip('/')}"
    return text


def _person(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    result = dict(value)
    profile = result.pop("profile_path", None) or result.pop("profilePath", None)
    if profile and not result.get("profile_url"):
        result["profile_url"] = _profile_url(profile)
    return compact(result)


def _dedupe_people(values: Iterable[Any], keys: Iterable[str]) -> List[Any]:
    result = []
    seen = set()
    for value in values:
        person = _person(value)
        if isinstance(person, dict):
            identity = tuple(str(person.get(key) or "").strip().lower() for key in keys)
        else:
            identity = (str(person or "").strip().lower(),)
        if not any(identity) or identity in seen:
            continue
        seen.add(identity)
        result.append(person)
    return result


def _crew_people(values: Iterable[Any], job: str) -> List[Any]:
    result = []
    for value in values:
        if isinstance(value, dict):
            result.append({**value, "job": value.get("job") or job})
        else:
            result.append({"name": value, "job": job})
    return result


def normalize_credits(media_info: Dict[str, Any]) -> Dict[str, Any]:
    credits = media_info.get("credits") if isinstance(media_info.get("credits"), dict) else {}
    cast = credits.get("cast") or media_info.get("actors") or []
    if not cast and isinstance(media_info.get("people"), list):
        cast = media_info["people"]
    crew = [
        *(credits.get("crew") or []),
        *_crew_people(media_info.get("directors") or [], "Director"),
        *_crew_people(media_info.get("writers") or [], "Writer"),
        *_crew_people(media_info.get("created_by") or [], "Creator"),
    ]
    return compact({
        "cast": _dedupe_people(cast, ("id", "name", "character")),
        "crew": _dedupe_people(crew, ("id", "name", "job")),
    })


def normalize_media_context(context: Any) -> Dict[str, Any]:
    if not context:
        return {}
    context_dict = compact(context)
    media_info = dict(context_dict.get("media_info") or {})
    meta_info = context_dict.get("meta_info") or {}
    provider_ids = media_info.get("provider_ids") or media_info.get("providerIds") or {}
    remaining_provider_ids = {
        key: value for key, value in provider_ids.items()
        if key not in {"tmdb", "imdb", "douban", "tvdb"}
    }

    canonical = {
        "title": media_info.get("title") or meta_info.get("title") or meta_info.get("name"),
        "original_title": media_info.get("original_title") or media_info.get("original_name") or media_info.get("en_title"),
        "year": media_info.get("year") or meta_info.get("year"),
        "media_type": _media_type(media_info.get("type") or media_info.get("media_type") or meta_info.get("type")),
        "tmdb_id": media_info.get("tmdb_id") or provider_ids.get("tmdb") or meta_info.get("tmdbid"),
        "imdb_id": media_info.get("imdb_id") or provider_ids.get("imdb"),
        "douban_id": media_info.get("douban_id") or provider_ids.get("douban") or meta_info.get("doubanid"),
        "tvdb_id": media_info.get("tvdb_id") or provider_ids.get("tvdb"),
        "season_number": media_info.get("season_number") or media_info.get("season") or meta_info.get("begin_season"),
        "episode_number": media_info.get("episode_number") or meta_info.get("begin_episode"),
        "poster_url": media_info.get("poster_url") or media_info.get("poster_path") or media_info.get("poster"),
        "backdrop_url": media_info.get("backdrop_url") or media_info.get("backdrop_path") or media_info.get("backdrop"),
        "logo_url": media_info.get("logo_url") or media_info.get("logo_path") or media_info.get("logo"),
        "fanart_url": media_info.get("fanart_url") or media_info.get("fanart_path") or media_info.get("fanart"),
        "clearlogo_url": media_info.get("clearlogo_url") or media_info.get("clearlogo_path") or media_info.get("clearlogo"),
        "thumb_url": media_info.get("thumb_url") or media_info.get("thumb_path") or media_info.get("thumb"),
        "landscape_url": media_info.get("landscape_url") or media_info.get("landscape_path") or media_info.get("landscape"),
        "art_url": media_info.get("art_url") or media_info.get("art_path") or media_info.get("art"),
        "clearart_url": media_info.get("clearart_url") or media_info.get("clearart_path") or media_info.get("clearart"),
        "banner_url": media_info.get("banner_url") or media_info.get("banner_path") or media_info.get("banner"),
        "trailer_url": media_info.get("trailer_url") or media_info.get("trailer"),
        "genres": media_info.get("genres") or media_info.get("genre"),
        "tags": media_info.get("tags") or media_info.get("tag"),
        "provider_ids": remaining_provider_ids,
        "overview": media_info.get("overview") or media_info.get("plot"),
        "premiere_date": media_info.get("premiere_date") or media_info.get("release_date") or media_info.get("first_air_date") or media_info.get("air_date"),
        "community_rating": media_info.get("community_rating") or media_info.get("vote_average") or media_info.get("rating"),
        "official_rating": media_info.get("official_rating") or media_info.get("content_rating"),
        "runtime_seconds": _runtime_seconds(media_info),
        "studios": media_info.get("studios") or media_info.get("production_companies"),
        "credits": normalize_credits(media_info),
    }

    aliases = {
        "type", "provider_ids", "providerIds", "season", "poster_path", "poster", "backdrop_path", "backdrop",
        "logo_path", "logo", "fanart_path", "fanart", "clearlogo_path", "clearlogo", "thumb_path", "thumb",
        "landscape_path", "landscape", "art_path", "art", "clearart_path", "clearart", "banner_path", "banner",
        "trailer", "plot", "release_date", "first_air_date", "air_date", "vote_average", "rating", "content_rating",
        "runtime", "runtime_minutes", "runtimeSeconds", "episode_run_time", "production_companies", "actors",
        "people", "directors", "writers", "created_by", "credits", "original_name", "genre", "tag", "title_year"
    }
    result = {key: value for key, value in media_info.items() if key not in aliases}
    result.update({key: value for key, value in canonical.items() if value not in EMPTY_VALUES and value != {} and value != []})
    recognition_info = {key: value for key, value in context_dict.items() if key not in {"media_info", "meta_info"}}
    recognition_meta = {
        key: value for key, value in meta_info.items()
        if key not in {
            "title", "name", "year", "type", "tmdbid", "doubanid", "begin_season", "begin_episode"
        }
    }
    if recognition_meta:
        recognition_info["meta_info"] = recognition_meta
    return compact({
        "schema_version": 2,
        "recognized": bool(result.get("title")),
        "media_info": result,
        "recognition_info": recognition_info,
    })


def remove_catalog_aliases(media_info: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(media_info or {})
    for key in {
        "seasons", "season_info", "season_years", "number_of_seasons",
        "number_of_episodes",
    }:
        result.pop(key, None)
    return result


def provider_metadata(value: Dict[str, Any], excluded: Iterable[str]) -> Dict[str, Any]:
    return compact({key: item for key, item in value.items() if key not in set(excluded)})
