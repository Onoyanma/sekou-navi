"""一時ファイルの後始末。"""

import os


def remove_temp_files(paths):
    """解析が終わった一時画像を削除する（失敗しても処理は止めない）。"""
    for path in paths:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError as e:
                print(f"temp file cleanup failed for {path}: {e}")
