import json
import os
import pandas as pd

class TradeStore:
    def __init__(self):
        self.path = "storage/trades"
        self.log_file = f"{self.path}/trades_journal.csv"
        os.makedirs(self.path, exist_ok=True)

    def save_trade(self, trade: dict):
        # JSON Save
        file = f"{self.path}/{trade['id']}.json"
        with open(file, "w") as f:
            json.dump(trade, f, indent=2)
        
        # CSV Append for Analytics
        df = pd.DataFrame([trade])
        df.to_csv(self.log_file, mode='a', index=False, header=not os.path.exists(self.log_file))
