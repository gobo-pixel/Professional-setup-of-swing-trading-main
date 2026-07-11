import json
import os
import time
from datetime import datetime

import pandas as pd

from core.logger import get_logger


logger = get_logger(__name__)


class ReportGenerator:
    def generate(self, analytics: dict, portfolio: dict, risk: dict) -> dict:
        report = {
            "timestamp": time.time(),
            "analytics": analytics,
            "portfolio": portfolio,
            "risk": risk,
            "summary": {
                "equity": portfolio.get("equity", 0),
                "pnl": portfolio.get("pnl", 0),
                "risk_level": risk.get("grade", "UNKNOWN"),
            },
        }
        logger.info("Report generated")
        return report

    def save_json(self, report: dict, path: str = None):
        path = path or f"storage/reports/report_{int(time.time())}.json"

        with open(path, "w") as f:
            json.dump(report, f, indent=2)

        logger.info(f"Report saved at {path}")

    @staticmethod
    def append_to_master_report(results_list):
        file_path = "storage/reports/master_report.csv"

        # results_list se data extract kiya
        data = [r.__dict__ for r in results_list]
        df = pd.DataFrame(data)
        df["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        file_exists = os.path.isfile(file_path)

        df.to_csv(
            file_path,
            mode="a",
            index=False,
            header=not file_exists,
        )

        logger.info("Scan results appended to master_report.csv")
