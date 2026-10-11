import json
import logging
import math
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

logger = logging.getLogger(__name__)
POSTAL_CODE = re.compile(r"^\s*\d{3}\s?\d{2}\s+")


def _lookup(text, url):
    with urlopen(url + "?" + urlencode({"text": text}), timeout=10) as response:
        results = json.load(response)["results"]
    if not isinstance(results, list):
        raise ValueError("Invalid results")
    if not results:
        return None
    match = results[0]
    if not isinstance(match, dict) or any(
        not isinstance(match.get(key), (int, float)) or isinstance(match[key], bool)
        or not math.isfinite(match[key]) for key in ("lat", "lng")
    ):
        raise ValueError("Invalid coordinates")
    return match


def geocode_address(address):
    """Return (best city-level match, error); no match is not an extraction failure."""
    url = os.environ.get("GEOCODE_URL", "http://127.0.0.1:9112/api/geocode").rstrip("/") + "/"
    try:
        match = _lookup(address, url)
        if match is None and "," in address:
            # This API returns city coordinates. Street searches may yield no matches
            # even when the city is indexed; retry only an explicit city component.
            city = POSTAL_CODE.sub("", address.rsplit(",", 1)[-1]).strip()
            if city and city.casefold() != address.casefold() and any(char.isalpha() for char in city):
                match = _lookup(city, url)
        return (match, "") if match is not None else (None, "No geocoding match found.")
    except HTTPError as exc:
        return None, f"Geocoding service returned HTTP {exc.code}."
    except (URLError, TimeoutError, OSError) as exc:
        logger.warning("Geocoding service request failed: %s", exc)
        return None, "Geocoding service is unavailable."
    except (ValueError, TypeError, KeyError, IndexError):
        return None, "Geocoding service returned an invalid response."
