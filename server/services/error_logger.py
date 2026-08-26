"""
MIA Error Logger — Centralized error logging utility.
"""

import json
import traceback
from datetime import datetime
from pathlib import Path
from server.config import config

class ErrorLogger:
    def __init__(self):
        # We store errors in data/error_log.json
        self.log_file = config.DATA_DIR / "error_log.json"
        self._ensure_file()

    def _ensure_file(self):
        """Ensure the log file exists."""
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_file.exists():
            with open(self.log_file, "w", encoding="utf-8") as f:
                json.dump([], f)

    def log_error(self, exception: Exception, context: str = "System"):
        """
        Log an exception to the persistent JSON file.
        Returns a short summary of the error.
        """
        short_message = f"{type(exception).__name__}: {str(exception)}"
        full_traceback = traceback.format_exc()
        
        # Determine a user-friendly short message if possible
        friendly_message = "An unexpected error occurred."
        if "Quota" in short_message or "429" in short_message or "rate limit" in short_message.lower():
            friendly_message = "API Quota Exceeded / Too Many Requests."
        elif "Connection" in short_message or "Timeout" in short_message:
            friendly_message = "Network Connection Error."
        elif "API key" in short_message.lower() or "auth" in short_message.lower() or "401" in short_message:
            friendly_message = "API Authentication Failed (Check your key)."
        else:
            friendly_message = short_message[:100] + ("..." if len(short_message) > 100 else "")

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "context": context,
            "short_message": friendly_message,
            "full_traceback": full_traceback
        }
        
        try:
            self._ensure_file()
            # Read existing
            with open(self.log_file, "r", encoding="utf-8") as f:
                try:
                    logs = json.load(f)
                except Exception:
                    logs = []
                    
            # Append and keep last 100
            logs.insert(0, log_entry)
            if len(logs) > 100:
                logs = logs[:100]
                
            # Save
            with open(self.log_file, "w", encoding="utf-8") as f:
                json.dump(logs, f, indent=2)
                
        except Exception as e:
            print(f"Failed to write to error log: {e}")
            
        return friendly_message
        
    def get_error_logs(self):
        """Retrieve the error logs."""
        try:
            self._ensure_file()
            with open(self.log_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
            
    def clear_logs(self):
        """Clear the error logs."""
        try:
            self._ensure_file()
            with open(self.log_file, "w", encoding="utf-8") as f:
                json.dump([], f)
        except Exception:
            pass

# Global instance
error_logger = ErrorLogger()
