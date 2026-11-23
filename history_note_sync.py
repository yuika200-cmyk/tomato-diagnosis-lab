"""Update only the signed-in user's existing diagnosis note (never insert duplicates)."""
import inspect
import re
import history_cloud


def _table_name():
    """Reuse the table configured by the deployed history_cloud implementation."""
    for attr in ("HISTORY_TABLE", "HISTORY_TABLE_NAME", "TABLE_NAME", "RECORDS_TABLE", "DIAGNOSIS_TABLE"):
        value = getattr(history_cloud, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    # history_cloud may use a literal table name rather than a constant.
    for func in (getattr(history_cloud, "save", None), getattr(history_cloud, "list_history", None)):
        if func is None:
            continue
        try:
            code = inspect.getsource(func)
        except (OSError, TypeError):
            continue
        match = re.search(r"\.table\(\s*['\"]([^'\"]+)['\"]\s*\)", code)
        if match:
            return match.group(1)
    raise RuntimeError("history_cloud.pyの保存先テーブル名を特定できません")


def update_note(record_id, note: str):
    """Update record by both ID and logged-in user ID, respecting RLS."""
    user = history_cloud.user()
    if user is None or not getattr(user, "id", None):
        raise PermissionError("ログインが必要です")
    if record_id is None:
        raise ValueError("対象の記録IDがありません")
    table_name = _table_name()
    result = (history_cloud.client().table(table_name)
              .update({"observation_note": note})
              .eq("id", record_id)
              .eq("user_id", user.id)
              .execute())
    # Some PostgREST policies return zero rows rather than an exception.
    if not getattr(result, "data", None):
        raise RuntimeError("メモの更新対象がありません。DBの権限設定を確認してください")
    return result
