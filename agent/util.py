def safe_jsonify(obj, _seen=None):
    if _seen is None:
        _seen = set()
    if isinstance(obj, (dict, list)):
        oid = id(obj)
        if oid in _seen:
            return "<circular reference omitted>"
        _seen = _seen | {oid}
        if isinstance(obj, dict):
            return {str(k): safe_jsonify(v, _seen) for k, v in obj.items()}
        return [safe_jsonify(v, _seen) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)
