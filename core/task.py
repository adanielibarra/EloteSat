"""Background download (QgsTask) into the stage folders of one cycle."""

import os

from qgis.core import QgsTask, QgsMessageLog, Qgis
from qgis.PyQt.QtCore import pyqtSignal

from . import phenology
from .downloader import (SceneSkipped, Cancelled, process_scene,
                         append_manifest, build_mosaics)
from .stac_client import PcSigner, qgis_post_json
from .i18n import tr

TAG = "EloteSat"


class DownloadTask(QgsTask):
    message = pyqtSignal(str)

    def __init__(self, scenes, aoi_wkt_4326, out_dir, cycle, year, calendar,
                 bands, min_clear, min_cover, buffer_m, mosaic=True,
                 creds=None, params=None, profile=None):
        super().__init__("EloteSat: descarga", QgsTask.CanCancel)
        self.scenes = scenes
        self.aoi = aoi_wkt_4326
        self.out_dir = out_dir
        self.cycle, self.year, self.calendar = cycle, year, calendar
        self.bands = bands  # {sensor: [band ids]}
        self.min_clear, self.min_cover = min_clear, min_cover
        self.buffer_m = buffer_m
        self.mosaic = mosaic
        self.creds = creds
        self.params = params or {}
        self.profile = profile  # (name, profile dict) or None
        self.records, self.outputs = [], []
        self.error = self.manifest = None
        self.cycle_dir = phenology.cycle_dir(out_dir, cycle, year)
        # QgsBlockingNetworkRequest is safe in worker threads and follows
        # the QGIS proxy settings
        self.signer = PcSigner(get_json=lambda u: qgis_post_json(u, None))

    def _log(self, msg):
        if self.isCanceled():
            raise Cancelled()
        QgsMessageLog.logMessage(msg, TAG, Qgis.Info)
        self.message.emit(msg)

    def run(self):
        n = len(self.scenes)
        touched = set()
        try:
            os.makedirs(self.cycle_dir, exist_ok=True)
            phenology.save_calendar(
                self.calendar, os.path.join(self.cycle_dir,
                                            "calendario.json"))
            self._write_params()
            if self.profile:
                import json
                name, prof = self.profile
                with open(os.path.join(self.cycle_dir, "perfil.json"), "w",
                          encoding="utf-8") as f:
                    json.dump(dict(prof, name=name), f, ensure_ascii=False,
                              indent=2)
            for i, sc in enumerate(self.scenes):
                if self.isCanceled():
                    return False
                self.setProgress(100.0 * i / max(n, 1))
                folder = phenology.stage_dir(self.out_dir, self.cycle,
                                             self.year, sc.stage, sc.sensor)
                try:
                    rec = process_scene(
                        sc, self.aoi, folder, self.bands[sc.sensor],
                        min_clear=self.min_clear, min_cover=self.min_cover,
                        buffer_m=self.buffer_m, feedback=self._log,
                        creds=self.creds, signer=self.signer,
                        cancel_check=self.isCanceled)
                    self.outputs.append(rec.pop("outputs"))
                    touched.add(folder)
                except SceneSkipped as e:
                    rec = e.args[1] if len(e.args) > 1 else {
                        "scene_id": sc.id, "sensor": sc.sensor,
                        "date": sc.date, "tile": sc.tile,
                        "collection": sc.collection}
                    rec["status"] = rec.get("status", "skipped")
                    rec["reason"] = e.args[0]
                    self._log(tr("core.skipped", sc.label, e.args[0]))
                except Cancelled:
                    return False
                except Exception as e:  # network or GDAL failure
                    rec = {"scene_id": sc.id, "sensor": sc.sensor,
                           "date": sc.date, "tile": sc.tile,
                           "collection": sc.collection, "status": "error",
                           "reason": str(e)}
                    QgsMessageLog.logMessage(tr("core.error", sc.id, e),
                                             TAG, Qgis.Warning)
                    self.message.emit(tr("core.error", sc.label, e))
                rec["stage"] = sc.stage
                self.records.append(rec)
            if self.mosaic:
                for d in sorted(touched):
                    build_mosaics(d, self._log)
            self.setProgress(100)
            return True
        except Cancelled:
            return False
        except Exception as e:
            self.error = str(e)
            return False
        finally:
            if self.records:
                try:
                    self.manifest = append_manifest(self.cycle_dir,
                                                    self.records)
                except Exception as e:
                    self.error = tr("core.manifest", e)

    def _write_params(self):
        p = os.path.join(self.cycle_dir, "parametros.txt")
        with open(p, "a", encoding="utf-8") as f:
            f.write("# EloteSat download\n")
            for k, v in sorted(self.params.items()):
                f.write("%s = %s\n" % (k, v))
            f.write("\n")


class FunctionTask(QgsTask):
    """Runs fn(feedback=...) in the background; result in .result."""
    message = pyqtSignal(str)

    def __init__(self, title, fn):
        super().__init__(title, QgsTask.CanCancel)
        self.fn = fn
        self.result = None
        self.error = None

    def _log(self, msg):
        if self.isCanceled():
            raise Cancelled()
        self.message.emit(msg)

    def run(self):
        try:
            self.result = self.fn(feedback=self._log)
            return True
        except Cancelled:
            return False
        except Exception as e:
            self.error = str(e)
            return False
