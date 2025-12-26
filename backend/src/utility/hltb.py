import logging
import traceback

try:
    from howlongtobeatpy import HowLongToBeat
except ImportError as e:
    HowLongToBeat = None
    # print(f"HLTB Import failed: {e}") 

class HLTBFetcher:
    def __init__(self):
        self.logger = logging.getLogger("HLTB")
        self.hltb = None
        
        if HowLongToBeat:
            self.hltb = HowLongToBeat(0.0)
        else:
            # Try lazy import in case paths were updated
            try:
                from howlongtobeatpy import HowLongToBeat as HLTB_Lazy
                self.hltb = HLTB_Lazy(0.0)
            except Exception as e:
                self.logger.error(f"howlongtobeatpy import failed: {e}")

    def search(self, game_name):
        # Lazy Init Attempt 2
        if not self.hltb:
            try:
                from howlongtobeatpy import HowLongToBeat as HLTB_Lazy
                self.hltb = HLTB_Lazy(0.0)
            except ImportError:
                pass
            except Exception as e:
                self.logger.error(f"Late Init failed: {e}")

        if not self.hltb:
            self.logger.warning("howlongtobeatpy not available.")
            return None
            
        try:
            results = self.hltb.search(game_name)
            if results and len(results) > 0:
                best = max(results, key=lambda x: x.similarity)
                # Attributes in 1.0.19 are main_story, main_extra, completionist
                # They usually include the unit (e.g. "50 Hours") or just the number. 
                # If just number, we add Hours.
                
                def fmt(val):
                    if val == 0 or val is None or val == -1: return "N/A"
                    s = str(val)
                    if "Hours" not in s and "Mins" not in s:
                        return s + " Hours"
                    return s

                return {
                    "main": fmt(best.main_story),
                    "main_extra": fmt(best.main_extra),
                    "completionist": fmt(best.completionist),
                    "similarity": best.similarity
                }
            return None
        except Exception as e:
            self.logger.error(f"HLTB Search failed: {e}")
            return None