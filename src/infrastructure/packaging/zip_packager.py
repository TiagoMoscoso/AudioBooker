"""Packages the final audiobook into a ZIP (§32), writing to a
`<title>.partial.zip` first and renaming only after a fully successful write,
so a crash never leaves a ZIP that looks finished but isn't."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path


class ZipPackager:
    def package(self, files: dict[str, Path], manifest: dict, output_zip_path: Path) -> Path:
        output_zip_path.parent.mkdir(parents=True, exist_ok=True)
        partial_path = output_zip_path.parent / f"{output_zip_path.stem}.partial.zip"

        with zipfile.ZipFile(partial_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for arcname, path in files.items():
                zf.write(path, arcname)
            zf.writestr("audiobook.json", json.dumps(manifest, ensure_ascii=False, indent=2))

        partial_path.replace(output_zip_path)
        return output_zip_path
