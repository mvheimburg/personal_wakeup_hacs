def normalize_playlists(raw: str | list[str] | None) -> list[str]:
    """Turn a comma-separated string or list into a clean list of playlist IDs."""
    if isinstance(raw, list):
        return [p for p in raw if p]  # already a list
    if not raw:
        return []
    return [p.strip() for p in str(raw).split(",") if p.strip()]
